#!/usr/bin/env python3

# TODO:
#


import os
import sys
import tempfile
import time
from datetime import timedelta
import requests
import whisper
from tqdm import tqdm
from moviepy.editor import VideoFileClip
import pymupdf
from pathlib import Path
import json
from utils import (
    setup_logger,
    load_config,
    ensure_directories,
    get_doc_size_bytes,
    get_highest_index,
    ProcessingError,
    PDFProcessingError,
)

# ─── LOGGER & CONFIG ────────────────────────────────────────────────────────────────
config = load_config()
logger = setup_logger(__name__, config)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = SCRIPT_DIR / config["directories"]["base"]
TRANSCRIPT_MASTER_DIR = DOWNLOAD_DIR / config["directories"]["transcript_master"]
MAX_MASTER_PDF_SIZE = (
    config["pdf"]["max_master_size_mb"] * 1024 * 1024
)  # Convert MB to bytes
CHUNK_DURATION_MINUTES = config["transcript"]["chunk_duration_minutes"]
WHISPER_MODEL = config["transcript"]["model"]

# ─── DIRECTORY SETUP ────────────────────────────────────────────────────────────────
ensure_directories([TRANSCRIPT_MASTER_DIR])


def download_video(url, output_path):
    """Downloads a video from a direct URL to a local file.

    Args:
        url (str): The direct URL to the video file.
        output_path (str): Local path where the video should be saved.

    Returns:
        str: Path to the downloaded video file.

    Raises:
        requests.exceptions.RequestException: If video download fails.
    """
    logger.info(f"Downloading video from {url}...")
    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024  # 1 Kibibyte

    with open(output_path, "wb") as file, tqdm(
        desc="Downloading",
        total=total_size,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(block_size):
            size = file.write(data)
            bar.update(size)

    logger.debug(f"Video downloaded to {output_path}")
    return output_path


def extract_audio(video_path, audio_path):
    """Extracts audio track from a video file.

    Args:
        video_path (str): Path to the input video file.
        audio_path (str): Path where the extracted audio should be saved.

    Returns:
        str: Path to the extracted audio file.

    Raises:
        IOError: If audio extraction fails.
    """
    logger.debug("Extracting audio from video...")
    video = VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path, verbose=False, logger=None)
    video.close()
    logger.debug(f"Audio extracted to {audio_path}")
    return audio_path


def format_timestamp(seconds):
    """Formats a duration in seconds to a human-readable timestamp.

    Args:
        seconds (float): Duration in seconds.

    Returns:
        str: Formatted timestamp in HH:MM:SS format.
    """
    return str(timedelta(seconds=round(seconds)))


def transcribe_audio(audio_path, chunk_duration=CHUNK_DURATION_MINUTES * 60):
    """Transcribes an audio file using OpenAI's Whisper model.

    Processes the audio in chunks to handle long recordings efficiently.

    Args:
        audio_path (str): Path to the audio file to transcribe.
        chunk_duration (int, optional): Duration of each chunk in seconds.
            Defaults to CHUNK_DURATION_MINUTES*60.

    Returns:
        list: List of dictionaries containing transcribed segments with timestamps.
            Each segment has 'start', 'end', and 'text' keys.

    Raises:
        ProcessingError: If transcription fails.
    """
    logger.debug(f"Loading Whisper model ({WHISPER_MODEL})...")
    model = whisper.load_model(WHISPER_MODEL)

    logger.info("Starting transcription...")
    audio = whisper.load_audio(audio_path)
    audio_duration = len(audio) / whisper.audio.SAMPLE_RATE

    logger.info(f"Audio duration: {format_timestamp(audio_duration)}")

    # Calculate the number of chunks
    chunk_size = chunk_duration * whisper.audio.SAMPLE_RATE
    num_chunks = int(len(audio) / chunk_size) + 1

    full_transcript = []

    for i in range(num_chunks):
        start_sample = int(i * chunk_size)
        end_sample = min(int((i + 1) * chunk_size), len(audio))

        if start_sample >= len(audio):
            break

        start_time = start_sample / whisper.audio.SAMPLE_RATE
        end_time = end_sample / whisper.audio.SAMPLE_RATE

        logger.debug(
            f"Transcribing chunk {i+1}/{num_chunks} [{format_timestamp(start_time)} - {format_timestamp(end_time)}]"
        )

        audio_chunk = audio[start_sample:end_sample]
        result = model.transcribe(audio_chunk)

        # Adjust timestamps to account for chunk position
        for segment in result["segments"]:
            segment["start"] += start_time
            segment["end"] += start_time
            full_transcript.append(segment)

    return full_transcript


def save_transcript(transcript, output_file):
    """Saves a transcript to a text file in a readable format.

    Args:
        transcript (list): List of transcribed segments with timestamps.
        output_file (str): Path where the transcript should be saved.

    Raises:
        IOError: If saving transcript fails.
    """
    with open(output_file, "w", encoding="utf-8") as f:
        for segment in transcript:
            start_time = format_timestamp(segment["start"])
            end_time = format_timestamp(segment["end"])
            text = segment["text"]
            f.write(f"[{start_time} - {end_time}] {text}\n")

    logger.info(f"Transcript saved to {output_file}")


def transcribe_video(
    url, chunk_duration_minutes=5, category=None, master=None, master_page=None
):
    """Transcribes a video from a URL and creates a PDF document.

    Downloads video, extracts audio, transcribes speech, and formats result as PDF
    with metadata and timestamps.

    Args:
        url (str): Direct URL to the video file.
        chunk_duration_minutes (int, optional): Duration of chunks in minutes. Defaults to 10.
        category (str, optional): Category of the video content. Defaults to None.
        master (str, optional): Path to master PDF source. Defaults to None.
        master_page (int, optional): Page number in master PDF. Defaults to None.

    Returns:
        pymupdf.Document: PDF document containing transcribed text and metadata.

    Raises:
        ProcessingError: If video transcription fails at any stage.
    """
    start_time = time.time()

    # Load metadata from urls.json
    metadata = {}
    filename = "transcript"  # Default values
    try:
        with open("data/urls.json", "r") as f:
            urls_data = json.load(f)
            if url in urls_data:
                metadata = urls_data[url]
                # Use category from urls.json if not provided
                if not category:
                    category = metadata.get("category")
                # Get filename from path in urls.json
                filename = Path(metadata.get("path", "")).stem
    except Exception as e:
        logger.warning(f"Could not load metadata from urls.json: {e}")

    # Create a temporary directory for files
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Download the video
            video_path = os.path.join(temp_dir, "video.mp4")
            download_video(url, video_path)

            # Extract audio
            audio_path = os.path.join(temp_dir, "audio.wav")
            extract_audio(video_path, audio_path)

            # Transcribe the audio
            transcript = transcribe_audio(
                audio_path, chunk_duration=chunk_duration_minutes * 60
            )

            # First save as text file (like the working version)
            text_path = os.path.join(temp_dir, "transcript.txt")
            save_transcript(transcript, text_path)
            try:
                # Create a new PDF document
                doc = pymupdf.open()
                # Set page dimensions to A4 (in points, 8.27 x 11.7 inches) to match scraper
                page = doc.new_page(width=595.44, height=842.4)

                # Add metadata to document
                doc.set_metadata({"title": filename, "subject": "Video Transcript"})

                # Add title and metadata to first page
                title_font = pymupdf.Font("helv")
                text_font = pymupdf.Font("helv")

                # Add title
                page.insert_text((50, 50), f"Transcript for video(s) contained within above document: {filename}", fontsize=16)

                # Add custom information at the start
                y_pos = 100
                page.insert_text(
                    (50, y_pos), f"Category: {category or 'Unknown'}", fontsize=12
                )

                y_pos += 20
                page.insert_text((50, y_pos), f"Type: Video", fontsize=12)
                y_pos += 20
                page.insert_text((50, y_pos), f"Master PDF Source: {master}", fontsize=12)
                y_pos += 20
                page.insert_text(
                    (50, y_pos), f"Master PDF Page Number: {master_page}", fontsize=12
                )

                # Add transcript content from the text file
                y_pos += 40
            except Exception as e:
                logger.error("Issue creating custom content to insert in PDF failed in transcribe_video() process.")
                raise PDFProcessingError(f"custom PDF content creation failed: {e}")


            with open(text_path, "r", encoding="utf-8") as f:
                for line in f:
                    # Add text
                    page.insert_text((50, y_pos), line.strip(), fontsize=12)
                    y_pos += 20

                    # Create new page if needed
                    if y_pos > page.rect.height - 50:
                        page = doc.new_page()
                        y_pos = 50

            logger.info("Transcription completed successfully!")
            elapsed_time = time.time() - start_time
            logger.debug("Total processing time: %s", format_timestamp(elapsed_time))
            
            return doc

        except Exception as e:
            logger.error("transcribe_video() process failed, %s", e)
            raise ProcessingError(f"Video transcription failed: {e}")


def main():
    """Example usage of the transcribe_video function.

    Demonstrates how to transcribe a video from a URL.
    """
    # Example URL - replace with your video URL
    #video_url = "https://example.com/video.mp4"
    #transcribe_video(video_url)


if __name__ == "__main__":
    main()

