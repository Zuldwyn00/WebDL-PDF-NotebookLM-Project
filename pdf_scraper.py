#!/usr/bin/env python3
"""
PDF and Video Content Scraper

A tool for scraping, processing, and organizing PDFs and video content
from web sources with automatic transcription and OCR capabilities for use with SmartAdvocate knowledge base. Organizes data and transcriptions into
an AI-friendly format for use with Google's NotebookLM by including references between sources and pages.

Author: Zuldwyn00 <zuldwyn@gmail.com>
Version: 2.0
Date: 2025-05-23
"""

# TODO:

# 1) Refactor redundant categorization method in trascribe_video, combine into using existing method in pdf_scraper.py
# Can check if type is mp4 and if so, categorize video into transcript_master
# Might have downside of making data not as readable to NotebookLM AI so probably best to keep as is

# 2) Potentially refactor to OOP, but not necessary here since code is not too complex, could at least refactor transcribe_video to be OOP to be a little cleaner

# 3) Docker Containerization, but again not necessary here since this is in-house personal code.

# 4) Could change to use a database instead of json file if we want to scale up.

__author__ = "Zuldwyn00 <zuldwyn@gmail.com>"
__version__ = "2.0"
__date__ = "2025-05-23"

# External imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from pathlib import Path
from tqdm import tqdm
from itertools import dropwhile
import os, base64
import json
import pymupdf, ocrmypdf
import logging

# Local imports
from transcribe_video import transcribe_video, combine_transcript
from utils import (
    setup_logger,
    load_config,
    ensure_directories,
    get_doc_size_bytes,
    get_highest_index,
    ScraperError,
    DownloadError,
    ProcessingError,
    ValidationError,
    ResourceNotFoundError,
)

# ─── LOGGER & CONFIG ────────────────────────────────────────────────────────────────
config = load_config()
logger = setup_logger(__name__, config)


# ─── CUSTOM LOGGING HANDLER ────────────────────────────────────────────────────────────────
class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            # Clear the current line and write the log message
            tqdm.write(msg, end="\n")
            self.flush()
        except Exception:
            self.handleError(record)


# ─── LOGGER SETUP ────────────────────────────────────────────────────────────────
# Create console handler with custom formatter
console_handler = TqdmLoggingHandler()
formatter = logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s"
)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Create file handler for logging to a file
log_dir = Path(__file__).resolve().parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"pdf_scraper_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Remove any existing handlers to avoid duplicate output
for handler in logger.handlers[:]:
    if not isinstance(handler, TqdmLoggingHandler) and not isinstance(
        handler, logging.FileHandler
    ):
        logger.removeHandler(handler)

# Log startup information
logger.info(f"PDF Scraper v{__version__} starting up")
logger.info(f"Log file created at: {log_file}")

# ─── GLOBAL VARIABLES ────────────────────────────────────────────────────────────────
GLOBAL_DRIVER = None  # initialize driver
WEBSITE_LINK = config["website"]["url"]

# ─── PATHS ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
DOWNLOAD_DIR = SCRIPT_DIR / config["directories"]["base"]
DATED_DOWNLOAD_DIR = DOWNLOAD_DIR / CURRENT_DATE
MASTER_DIR = DOWNLOAD_DIR / config["directories"]["master"]
TRANSCRIPT_MASTER_DIR = DOWNLOAD_DIR / config["directories"]["transcript_master"]

MAX_MASTER_PDF_SIZE = (
    config["pdf"]["max_master_size_mb"] * 1024 * 1024
)  # Convert MB to bytes

# ─── FILES ────────────────────────────────────────────────────────────────
URLS_FILE = SCRIPT_DIR / config["files"]["urls"]

# ─── DIRECTORY SETUP ────────────────────────────────────────────────────────────────
ensure_directories(
    [DATA_DIR, DOWNLOAD_DIR, DATED_DOWNLOAD_DIR, MASTER_DIR, TRANSCRIPT_MASTER_DIR]
)
if not URLS_FILE.exists():
    URLS_FILE.touch()
    logger.info(f"Created file: {URLS_FILE}")


# ─── DRIVER FUNCTIONS ────────────────────────────────────────────────────────────────
def initialize_driver(timeout: int = None) -> webdriver.Chrome:
    """Initializes and returns a Chrome WebDriver instance with headless configuration.

    Args:
        timeout (int, optional): Custom timeout value in seconds. If None, uses config value.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance.

    Raises:
        WebDriverException: If driver initialization fails.
    """
    global GLOBAL_DRIVER
    if GLOBAL_DRIVER is None:
        chrome_options = Options()

        prefs = {
            "download.default_directory": str(DATED_DOWNLOAD_DIR),
            "download.prompt_for_download": config["browser"]["download_prompt"],
            "download.directory_upgrade": True,
        }

        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_argument("--disable-gpu")
        if config["browser"]["headless"]:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument(f"--user-agent={config['website']['user_agent']}")

        GLOBAL_DRIVER = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        # Use timeout from config if not specified
        timeout = timeout or config["browser"]["timeout"]
        GLOBAL_DRIVER.wait = WebDriverWait(GLOBAL_DRIVER, timeout)

    return GLOBAL_DRIVER


def close_driver():
    """Closes and cleans up the WebDriver instance if it exists.

    This function safely closes the global WebDriver instance and sets it to None.
    Should be called when scraping is complete or if an error occurs.
    """
    global GLOBAL_DRIVER
    if GLOBAL_DRIVER:
        GLOBAL_DRIVER.quit()
        GLOBAL_DRIVER = None


# -------------------------------------------------------------------------------#


def get_links(website_url: str) -> dict:
    """Scrapes all article links and video links from the website, organized by category.

    Args:
        website_url (str): The base URL to scrape links from.

    Returns:
        dict: Dictionary containing links with their status and category information.
            Format: {
                "url": {
                    "status": str,  # "PEND", "FAIL", or "SUCC"
                    "category": str,
                    "type": str,    # "pdf" or "mp4"
                    "master_pdf": str | None,
                    "page_number": int | None
                }
            }

    Raises:
        WebDriverException: If web scraping fails.
        TimeoutException: If page loading times out.
    """
    driver = initialize_driver()
    logger.info("Beginning get_links from: %s", website_url)
    driver.get(website_url)
    wait_for_page_ready(driver)

    saved_links = _load_urls()

    # First, collect all category links from the main page
    category_links = set()
    for element in driver.find_elements(By.TAG_NAME, "a"):
        href = element.get_attribute("href") or ""
        if "category" in href and "subcategory" not in href:
            category_links.add(href)

    # Process each category
    total_categories = len(category_links)
    with tqdm(
        total=total_categories,
        desc="Processing Categories",
        unit="category",
        position=0,
        leave=True,
    ) as pbar:
        for category_url in category_links:
            try:
                # Open category page
                driver.get(category_url)
                wait_for_page_ready(driver)

                # Get category name
                category_name = driver.find_element(
                    By.CSS_SELECTOR, "span.text.ng-binding"
                ).text.strip()
                logger.info("Processing category: %s", category_name)

                # Get all article links from this category's subcategories
                article_elements = driver.find_elements(
                    By.CSS_SELECTOR, "ul.article-links a"
                )
                for article_element in article_elements:
                    try:
                        href = article_element.get_attribute("href")
                        if not href or "subcategory" in href:
                            continue

                        # Add new links or update existing ones
                        if href not in saved_links:
                            _add_url(
                                saved_links, href, status="PEND", category=category_name
                            )

                    except StaleElementReferenceException:
                        logger.debug("Stale article element, skipping...")
                        continue
                    except Exception as e:
                        logger.exception(
                            "Error processing article %s: %s", href, str(e)
                        )
                        continue

            except Exception as e:
                logger.exception(
                    "Error processing category %s: %s", category_url, str(e)
                )
                continue
            finally:
                pbar.update(1)
                pbar.set_postfix({"Processed": f"{pbar.n}/{total_categories}"})

    # Save all links and return
    _save_urls(saved_links)
    return saved_links


def wait_for_page_ready(driver):
    """Waits for the page to be fully loaded by checking spinner and image loading.

    Args:
        driver (webdriver.Chrome): The WebDriver instance to use.

    Returns:
        bool: True if page is ready, False otherwise.

    Raises:
        TimeoutException: If page elements don't load within timeout period.
    """
    wait = driver.wait
    # 1) wait for the spinner staleness
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".fa-spinner")))
        wait.until(EC.staleness_of(driver.find_element(By.CSS_SELECTOR, ".fa-spinner")))
    except TimeoutException:
        pass

    # 2) if images exist, wait for all to load
    try:
        imgs = driver.find_elements(By.TAG_NAME, "img")
        if imgs:
            js = """
                return Array.from(document.images)
                            .every(img => img.complete && img.naturalWidth > 0);
            """
            wait.until(lambda d: d.execute_script(js))
    except TimeoutException:
        pass

    return True


def download_pdfs(saved_links: dict) -> dict:
    """Downloads PDFs for all pending links and saves them to the dated directory.

    Args:
        saved_links (dict): Dictionary of links with their status and metadata.

    Returns:
        dict: Updated saved_links dictionary with new statuses.

    Raises:
        DownloadError: If PDF download or saving fails.
        ProcessingError: If PDF processing fails.
    """
    driver = initialize_driver()

    # Calculate total PDFs to download
    total_pdfs = len(
        [link for link, data in saved_links.items() if data["status"] not in {"SUCC"}]
    )
    processed_pdfs = 0

    with tqdm(
        total=total_pdfs, desc="Downloading PDFs", unit="pdf", position=0, leave=True
    ) as pbar:
        for link, data in saved_links.items():
            if data["status"] not in {"SUCC"}:
                try:
                    logger.info(f"Processing: {link}")
                    driver.get(link)
                    wait_for_page_ready(driver)

                    # Check if page has attachments and determine if it's a video
                    try:
                        # Find all video elements on the page
                        video_elements = driver.find_elements(
                            By.CSS_SELECTOR, "video source"
                        )
                        if video_elements:
                            data["type"] = "mp4"
                            data["video_urls"] = []  # Initialize list for video URLs
                            for video_source in video_elements:
                                video_url = video_source.get_attribute("src")
                                if video_url:
                                    logger.info(f"Found video in {link}: {video_url}")
                                    data["video_urls"].append(
                                        video_url
                                    )  # Add each video URL to the list
                                    # process mp4 types seperately after combining and categorizing PDFs to retain link to master_pdf,
                                    # process_transcripts in run_script

                    except Exception as e:
                        logger.debug(
                            "No videos found on page, proceeding with PDF processing"
                        )
                        pass

                    # Process PDF
                    pdf = driver.execute_cdp_cmd(
                        "Page.printToPDF",
                        {
                            "printBackground": True,
                            "paperWidth": 8.27,
                            "paperHeight": 11.7,
                        },
                    )
                    pdf_bytes = base64.b64decode(pdf["data"])

                    if len(pdf_bytes) <= 2 * 1024:
                        raise DownloadError(f"PDF too small for {link}")

                    parse = urlparse(link)
                    name = (parse.netloc + parse.path).strip("/").replace("/", "_")
                    finalname = name + ".pdf"

                    try:
                        with open(
                            os.path.join(DATED_DOWNLOAD_DIR, finalname), "wb"
                        ) as f:
                            f.write(pdf_bytes)
                        logger.info(
                            "Saved as -> %s filesize: %s", finalname, len(pdf_bytes)
                        )
                        if (
                            not data["type"] == "mp4"
                        ):  # if not mp4, then we can set status to SUCC
                            data["status"] = "SUCC"
                    except IOError as e:
                        raise DownloadError(f"Failed to save PDF {finalname}: {str(e)}")

                except TimeoutException as e:
                    logger.error("Timeout downloading %s: %s", link, str(e))
                    data["status"] = "FAIL"
                except DownloadError as e:
                    logger.error("Download failed for %s: %s", link, str(e))
                    data["status"] = "FAIL"
                except ProcessingError as e:
                    logger.error("Video processing failed for %s: %s", link, str(e))
                    data["status"] = "FAIL"
                except Exception as e:
                    logger.exception(
                        "Unexpected error downloading %s: %s", link, str(e)
                    )
                    data["status"] = "FAIL"
                finally:
                    _save_urls(saved_links)

                processed_pdfs += 1
                pbar.update(1)
                pbar.set_postfix({"Processed": f"{processed_pdfs}/{total_pdfs}"})

    _save_urls(saved_links)
    return saved_links


# ─── PDF MANIPULATION ──────────────────────────────────────────────────────


def _combine_categorize_pdfs() -> None:
    """Combines all PDFs from the dated download directory into master PDFs by category.

    This function:
    1. Groups PDFs by category
    2. Creates or updates master PDFs
    3. Applies OCR if needed
    4. Updates URL data with master PDF locations
    5. Splits master PDFs if they exceed size limit

    Raises:
        ProcessingError: If PDF combination or categorization fails.
        ResourceNotFoundError: If required directories or files are missing.
    """
    try:
        logger.info("Starting PDF combination and categorization")

        # ----------------------------------------------------------------------
        # SETUP: Create directories and get PDF files
        # ----------------------------------------------------------------------
        # Ensure master folder exists
        ensure_directories([MASTER_DIR])

        # Get all PDFs from the DATED_DOWNLOAD_DIR
        if not DATED_DOWNLOAD_DIR.exists():
            raise FileNotFoundError(f"No PDF folder at {DATED_DOWNLOAD_DIR}")

        pdf_files = sorted(DATED_DOWNLOAD_DIR.glob("*.pdf"))
        if not pdf_files:
            logger.exception(
                f"No PDF files in {DATED_DOWNLOAD_DIR}, skipping combination and categorization"
            )
            return

        logger.info(f"Found {len(pdf_files)} PDF files to process")

        # ----------------------------------------------------------------------
        # MATCH: Match PDFs with URL data
        # ----------------------------------------------------------------------
        # Load URL data
        pdf_dict = _load_urls()

        # Match PDFs with URLs in pdf_dict
        for pdf_path in pdf_files:
            # Convert filename to URL format
            url_key = "https://" + pdf_path.stem.replace("_", "/")

            if url_key in pdf_dict:
                pdf_dict[url_key]["path"] = pdf_path
            else:
                # Create a default entry with 'Unknown' category
                _add_url(pdf_dict, url_key, status="SUCC", category="Unknown")
                pdf_dict[url_key]["path"] = pdf_path

        # ----------------------------------------------------------------------
        # CATEGORIES: Get unique categories from matched PDFs
        # ----------------------------------------------------------------------
        # Get unique categories
        unique_categories = set()
        for url, data in pdf_dict.items():
            if "category" in data:
                unique_categories.add(data["category"])

        logger.info(f"Found {len(unique_categories)} categories to process")

        # ----------------------------------------------------------------------
        # PROCESS: Process each category and create master PDFs
        # ----------------------------------------------------------------------
        # Process each category
        for current_category in unique_categories:
            logger.info(f"Processing category: {current_category}")

            # Get PDFs for this category
            category_pdfs = []
            for url, data in pdf_dict.items():
                if data.get("category") == current_category and "path" in data:
                    # Only include PDFs from the current date's directory
                    if (
                        isinstance(data["path"], Path)
                        and DATED_DOWNLOAD_DIR in data["path"].parents
                    ):
                        category_pdfs.append(data["path"])

            if not category_pdfs:
                logger.info(f"No PDFs found for category: {current_category}")
                continue

            logger.debug(
                f"Found {len(category_pdfs)} PDFs for category: {current_category}"
            )

            # ------------------------------------------------------------------
            # Create or open master PDF for this category
            # ------------------------------------------------------------------
            # Check for existing master PDFs
            existing_masters = list(MASTER_DIR.glob(f"{current_category}_*.pdf"))
            current_index = get_highest_index(existing_masters, current_category) or 1

            # Open or create master PDF
            master_path = MASTER_DIR / f"{current_category}_{current_index}.pdf"
            if master_path.exists():
                master_doc = pymupdf.open(str(master_path))
                incremental = True
            else:
                logger.debug(f"Creating new master PDF: {master_path}")
                master_doc = pymupdf.open()
                master_doc.new_page()
                incremental = False

            try:
                # --------------------------------------------------------------
                # Add each PDF to the master document
                # --------------------------------------------------------------
                # Process each PDF in this category
                for pdf_path in tqdm(
                    category_pdfs,
                    desc=f"Processing PDFs for {current_category}",
                    unit="pdf",
                    position=0,
                    leave=True,
                ):
                    try:
                        logger.debug(f"Processing {pdf_path.name}")

                        # Apply OCR as in the original code
                        chunk = apply_ocr(pymupdf.open(str(pdf_path)))

                        try:
                            # Check size limit
                            if (
                                get_doc_size_bytes(master_doc)
                                + get_doc_size_bytes(chunk)
                                > MAX_MASTER_PDF_SIZE
                            ):
                                logger.debug(
                                    f"Size limit reached, creating new master PDF"
                                )

                                # Save current and create new master
                                master_doc.save(
                                    str(master_path),
                                    incremental=incremental,
                                    encryption=0,
                                )
                                master_doc.close()

                                current_index += 1
                                master_path = (
                                    MASTER_DIR
                                    / f"{current_category}_{current_index}.pdf"
                                )
                                master_doc = pymupdf.open()
                                master_doc.new_page()
                                incremental = False

                            # Add PDF to master
                            page_offset = master_doc.page_count
                            master_doc.insert_pdf(chunk)

                            # Record which pages in the master PDF this document occupies
                            url_key = "https://" + pdf_path.stem.replace("_", "/")
                            if url_key in pdf_dict:
                                pdf_dict[url_key]["master_pdf"] = str(master_path)
                                pdf_dict[url_key]["page_number"] = page_offset
                        finally:
                            chunk.close()
                            _update_categories_file(current_category)
                    except Exception as e:
                        logger.error(f"Error processing {pdf_path.name}: {str(e)}")

                # Save final master PDF
                logger.debug(f"Saving master PDF: {master_path}")
                master_doc.save(str(master_path), incremental=incremental, encryption=0)
            finally:
                master_doc.close()

        # ----------------------------------------------------------------------
        # FINALIZE: Save URL data and finish
        # ----------------------------------------------------------------------
        # Save updated URL data
        _save_urls(pdf_dict)
        logger.info("PDFs combined and categorized successfully")

    except Exception as e:
        logger.exception("Failed to combine and categorize PDFs: %s", str(e))
        raise ProcessingError(f"PDF processing failed: {str(e)}")


def process_transcripts() -> None:
    """Processes video transcripts and combines them into master transcript PDFs.

    This function:
    1. Identifies videos in the URL database
    2. Transcribes each video
    3. Creates PDF documents from transcripts
    4. Combines transcripts into master PDFs
    5. Updates URL data with transcript information

    Raises:
        ProcessingError: If transcription or PDF creation fails.
    """
    # seperate method so we can retain link to master_pdf, page_number
    pdf_dict = _load_urls()
    for url, data in pdf_dict.items():
        if data.get("type") == "mp4" and "video_urls" and not data["status"] == "SUCC":
            video_urls = data["video_urls"]
            logger.debug(
                f"Processing {len(video_urls)} video transcripts for page: {url}"
            )
            for video_url in video_urls:
                logger.debug(f"Processing video transcript for: {video_url}")
                try:
                    transcript_doc = transcribe_video(
                        video_url,
                        category=data["category"],
                        master=data["master_pdf"],
                        master_page=data["page_number"],
                    )
                    combine_transcript(transcript_doc)
                except Exception as e:
                    data["status"] = "FAIL"
                    raise ProcessingError(f"Transcription processing failed: {str(e)}")

        data["status"] = "SUCC"
    _save_urls(pdf_dict)


def apply_ocr(doc: pymupdf.Document) -> pymupdf.Document:
    """OCR a PyMuPDF Document object and return the OCRed version with searchable text.

    Args:
        doc (pymupdf.Document): The document to apply OCR to.

    Returns:
        pymupdf.Document: OCRed version of the document.

    Raises:
        ProcessingError: If OCR processing fails.
    """

    min_images = config["pdf"]["minimum_ocr_pages"]

    # Check if document has any images on any page
    image_count = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        images = page.get_images(full=True)
        image_count += len(images)
        if image_count >= min_images:
            break  # to avoid unnecessary processing break after hitting the minimum

    # Skip OCR if less than 2 images found
    if image_count < min_images:
        logger.debug(
            f"Less than {min_images} images found in document ({image_count} found), skipping OCR"
        )
        return doc

    temp_input = Path(DOWNLOAD_DIR) / "temp_ocr.pdf"
    temp_output = Path(DOWNLOAD_DIR) / "temp_output.pdf"

    try:
        doc.save(str(temp_input))

        ocrmypdf.ocr(
            input_file=str(temp_input), output_file=str(temp_output), redo_ocr=True
        )
        # Load OCRd doc bytes in memory so we can close the temp file
        with open(str(temp_output), "rb") as f:
            ocr_bytes = f.read()
        ocr_doc = pymupdf.open(stream=ocr_bytes, filetype="pdf")
        logger.info("OCR complete, returning new document")

        return ocr_doc

    except Exception as e:
        logger.error(f"Error during OCR: {e}")
        raise ProcessingError(f"OCR processing failed: {str(e)}")
    finally:
        # Clean up temp files
        if temp_input.exists():
            temp_input.unlink()
        if temp_output.exists():
            temp_output.unlink()


# TODO: Update urls.j
def remove_pdf(pdf_key: str, delete_from_json: bool = False) -> None:
    """Removes a PDF from its master file and optionally from the URL database.

    Args:
        pdf_key (str): The URL key of the PDF to remove.
        delete_from_json (bool, optional): Whether to delete the entry from urls.json.
            Defaults to False.

    Raises:
        KeyError: If PDF key is not found in URL database.
        ResourceNotFoundError: If master PDF is not found.
        ProcessingError: If PDF deletion fails.
    """
    pdf_dict = _load_urls()

    if pdf_key not in pdf_dict:
        raise KeyError(f"PDF key '{pdf_key}' not found in URL database")
    if not pdf_dict[pdf_key].get("master_pdf"):
        raise ResourceNotFoundError(f"No master PDF associated with key '{pdf_key}'")

    data = pdf_dict[pdf_key]
    if data.get("master_pdf"):
        start_page = data["page_number"]
        # create an iterator starting from the matching pdf_key (inclusive) to the end of pdf_dict
        keys_iter = dropwhile(lambda x: x[0] != pdf_key, pdf_dict.items())

        try:
            master_doc = pymupdf.open(str(data["master_pdf"]))
            end_page = master_doc.page_count - 1
            try:  # StopIteration is raised if there is no next pdf
                next(keys_iter)  # skip the current pdf (pdf_key)
                next_pdf_key = next(keys_iter)  # get the next pdf

                while next_pdf_key[1].get("master_pdf") != data.get("master_pdf"):
                    next_pdf_key = next(keys_iter)
                    logger.debug(
                        f"Next pdf_key contains different master_pdf: {next_pdf_key[1].get("master_pdf")}, skipping"
                    )
                    if (
                        next_pdf_key[1].get("master_pdf") == data.get("master_pdf")
                        and next_pdf_key[1].get("page_number") > start_page
                    ):
                        end_page = next_pdf_key[1]["page_number"] - 1
                        break

            except StopIteration:
                # if no next pdf, use default end_page
                pass

            (end_page == master_doc.page_count) and logger.debug(
                "pdf_key is last in master_file"
            )

            master_doc.delete_pages(start_page, end_page)
            master_doc.save(str(data["master_pdf"]), incremental=True, encryption=0)

        except ValueError as e:
            raise ValidationError(f"Invalid page range: {start_page} to {end_page}")
        except RuntimeError as e:
            raise RuntimeError(f"Failed to delete pages: {str(e)}")
        except TypeError as e:
            raise TypeError(f"Unexpected error: {str(e)}")
        except Exception as e:
            raise ProcessingError(f"Unexpected error: {str(e)}")
        finally:
            master_doc.close()

    if delete_from_json:
        del pdf_dict[pdf_key]
        logger.info(f"Deleted {pdf_key} from urls.json")
    else:
        pdf_dict[pdf_key]["status"] = "PEND"

    _save_urls(pdf_dict)
    logger.info(f"Deleted pages {start_page} to {end_page} from {data['master_pdf']}")


# ─── SAVING ────────────────────────────────────────────────────────────────


def _normalize_url(raw_url: str) -> str:
    """Normalizes a URL by standardizing format and removing unnecessary components.

    Args:
        raw_url (str): The URL to normalize.

    Returns:
        str: Normalized URL with:
            - Scheme in lowercase
            - Domain in lowercase
            - Path in lowercase
            - No trailing slash
            - No query parameters or fragments
    """
    # components of url, urlparse seperates into 6 fields
    parts = urlparse(raw_url, scheme="http")
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = (parts.path or "").lower()  # Safely handle None case
    params = ""
    query = ""
    fragment = ""
    if (
        path.endswith("/") and len(path) > 1
    ):  # remove ending (/), prevents duplicates if web developer is inconsistent with adding a (/) at the end of a link or not if it's the same link
        path = path[:-1]

    # scheme://netloc/path;params?query#fragment
    normalized = urlunparse((scheme, netloc, path, params, query, fragment))
    return normalized


def _add_url(
    saved_links: dict,
    raw_url: str,
    status: str = "PEND",
    category: str = "undefined",
    file_type: str = "pdf",
):
    """Adds a new URL to the saved_links dictionary with metadata.

    Args:
        saved_links (dict): Dictionary to add URL to.
        raw_url (str): The URL to add.
        status (str, optional): Status of the URL. Must be "PEND", "FAIL", or "SUCC".
            Defaults to "PEND".
        category (str, optional): Category of the content. Defaults to "undefined".
        file_type (str, optional): Type of file ("pdf" or "mp4"). Defaults to "pdf".

    Raises:
        ValidationError: If status is not valid.
    """
    status = status.upper()
    if status not in {"PEND", "FAIL", "SUCC"}:
        raise ValidationError("Status must be PEND, FAIL or SUCC")
    url = _normalize_url(raw_url)
    saved_links[url] = {
        "status": status,
        "category": category,
        "type": file_type,
        "master_pdf": None,  # Store which master PDF this page belongs to
        "page_number": None,  # Store the page number in the master PDF
        # video_urls - not needed here, only for mp4 types
    }


def _save_urls(saved_links: dict) -> None:
    """Saves the saved_links dictionary to the URLs file in JSON format.

    Args:
        saved_links (dict): Dictionary of URLs and their metadata to save.

    Raises:
        OSError: If saving to file fails.
    """
    try:
        # Convert Path objects to strings before saving to JSON
        json_safe_links = {}
        for url, data in saved_links.items():
            json_safe_links[url] = data.copy()
            if "path" in json_safe_links[url] and isinstance(
                json_safe_links[url]["path"], Path
            ):
                json_safe_links[url]["path"] = str(json_safe_links[url]["path"])

        with open(URLS_FILE, "w", encoding="utf8") as f:
            json.dump(json_safe_links, f, indent=2, sort_keys=True)
    except OSError as e:
        logger.error("Failed to save URLs to %s: %s", URLS_FILE, e)


def _load_urls() -> dict:
    """Loads the saved_links dictionary from the URLs file.

    Returns:
        dict: Dictionary of URLs and their metadata. Empty dict if file doesn't exist.
    """
    if (
        not URLS_FILE.exists() or URLS_FILE.stat().st_size == 0
    ):  # if empty, return blank set
        return {}
    try:
        with open(URLS_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _update_categories_file(updated_category: str) -> None:
    """Updates the categories file with newly processed categories.

    Args:
        updated_category (str): The category that has been updated.

    Raises:
        OSError: If writing to categories file fails.
    """
    categories_file = SCRIPT_DIR / config["files"]["updated_categories"]

    try:
        # Write the updated category to the file
        # Using 'w' mode automatically clears the file
        with open(categories_file, "w", encoding="utf-8") as f:
            f.write(f"{updated_category} - updated\n")

        logger.info(f"Updated categories file with category: {updated_category}")

    except OSError as e:
        logger.error(f"Error writing to categories file: {e}")
        raise  # Re-raise the OSError with its original traceback


def run_script():
    """Main function that orchestrates the PDF scraping process.

    This function:
    1. Scrapes links from the website
    2. Downloads PDFs
    3. Combines and categorizes PDFs
    4. Processes video transcripts
    5. Cleans up resources

    Raises:
        ScraperError: If any part of the scraping process fails.
    """
    try:
        all_links = get_links(WEBSITE_LINK)
        print(f"INFO: Links found - {len(all_links)}")
        download_pdfs(all_links)
        _combine_categorize_pdfs()
        process_transcripts()
    except Exception as e:
        logger.exception("An error occurred while running the script: %s", str(e))
        raise ScraperError(f"Script execution failed: {str(e)}")
    finally:
        close_driver()


def main():
    """Entry point for the PDF scraper script.

    Runs the main scraping process and handles any top-level exceptions.
    """
    run_script()


if __name__ == "__main__":
    main()
