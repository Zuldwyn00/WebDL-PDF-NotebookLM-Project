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

# 1) Overhaul and refactor status indication, currently doesn't really work as it puts things as SUCC when they arent complete and puts things as PEND like mp4s if the mp4 hasnt
# been processed but the PDF has been added to the master, so if it get run again before that completes it will double up the PDF in the master

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

# Log startup information
logger.info(f"PDF Scraper v{__version__} starting up")

# ─── GLOBAL VARIABLES ────────────────────────────────────────────────────────────────
GLOBAL_DRIVER = None  # initialize driver
WEBSITE_LINK = config["website"]["url"]
# ─── PATHS ──────────────────────────────────────────────────────────────────────────
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

# ─── FILES ──────────────────────────────────────────────────────────────────────────
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


# ─── WEB SCRAPING FUNCTIONS ─────────────────────────────────────────────────────────


def get_links(website_url: str) -> dict:
    """Scrapes all article links and video links from the website, organized by category.

    Args:
        website_url (str): The base URL to scrape links from.

    Returns:
        dict: Dictionary containing categories with their URLs and metadata.
            Format: {
                "category": {
                    "url": {
                        "status": str,  # "PEND", "FAIL", or "SUCC"
                        "type": str,    # "pdf" or "mp4"
                        "master_pdf": str | None,
                        "page_number": int | None
                    }
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
                category_name = (
                    driver.find_element(By.CSS_SELECTOR, "span.text.ng-binding")
                    .text.split("-", 1)[0] #website updated to have main categories that share same name like "User Manual - Administration" so we filter that out and combine them
                    .strip()
                )
                logger.info("Processing category: %s", category_name)

                if not category_name:
                    logger.warning("Category name is empty after processing.")

                # get the subcategory first that contains the links we want
                article_elements = driver.find_elements(
                    By.CSS_SELECTOR, "ul.article-links a"
                )
                # now process the subcategory to find all the links inside of it.
                for article_element in article_elements:
                    try:
                        href = article_element.get_attribute("href")
                        if not href:
                            logger.debug(f"{href} not href, skipping")
                            continue

                        # Add new links using _add_url
                        if href not in saved_links.get(category_name, {}):
                            logger.debug(f"New link found: {href}, adding to {category_name}.")
                            _add_url(saved_links, category_name, href, status="PEND", file_type="pdf")
                        else: 
                            logger.debug(f"Link already exists: {href}, skipping.")

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
        saved_links (dict): Dictionary of categories containing URLs with their status and metadata.

    Returns:
        dict: Updated saved_links dictionary with new statuses.

    Raises:
        DownloadError: If PDF download or saving fails.
        ProcessingError: If PDF processing fails.
    """
    driver = initialize_driver()

    # Calculate total PDFs to download across all categories
    total_pdfs = sum(
        len([url for url, data in urls.items() if data["status"] not in {"SUCC"}])
        for urls in saved_links.values()
    )
    processed_pdfs = 0

    with tqdm(
        total=total_pdfs, desc="Downloading PDFs", unit="pdf", position=0, leave=True
    ) as pbar:
        for category, urls in saved_links.items():
            for link, data in urls.items():
                if data["status"] not in {"SUCC"}:
                    try:
                        logger.info(f"Processing {category}: {link}")
                        driver.get(link)
                        wait_for_page_ready(driver)

                        # Check if page has attachments and determine if it's a video
                        try:
                            # Find all video elements on the page
                            video_elements = driver.find_elements(
                                By.CSS_SELECTOR, "video source"
                            )
                            if video_elements:
                                # Update type and add video URLs
                                data["type"] = "mp4"
                                data["video_urls"] = []
                                for video_source in video_elements:
                                    video_url = video_source.get_attribute("src")
                                    if video_url:
                                        logger.info(f"Found video in {link}: {video_url}")
                                        data["video_urls"].append(video_url)

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
                            if not data["type"] == "mp4":  # if not mp4, then we can set status to SUCC
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


# ─── PDF MANIPULATION ───────────────────────────────────────────────────────────────


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
            
            # Find which category this URL belongs to
            for category, urls in pdf_dict.items():
                if url_key in urls:
                    pdf_dict[category][url_key]["path"] = pdf_path
                    break
            else:
                # Add to Unknown category using _add_url
                _add_url(pdf_dict, "Unknown", url_key, status="SUCC", file_type="pdf")
                pdf_dict["Unknown"][url_key]["path"] = pdf_path

        # ----------------------------------------------------------------------
        # PROCESS: Process each category and create master PDFs
        # ----------------------------------------------------------------------
        # Process each category
        for category, urls in pdf_dict.items():
            logger.info(f"Processing category: {category}")

            # Get PDFs for this category
            category_pdfs = []
            for url, data in urls.items():
                if "path" in data:
                    # Only include PDFs from the current date's directory
                    if (
                        isinstance(data["path"], Path)
                        and DATED_DOWNLOAD_DIR in data["path"].parents
                    ):
                        category_pdfs.append(data["path"])

            if not category_pdfs:
                logger.info(f"No PDFs found for category: {category}")
                continue

            logger.debug(
                f"Found {len(category_pdfs)} PDFs for category: {category}"
            )

            # ------------------------------------------------------------------
            # Create or open master PDF for this category
            # ------------------------------------------------------------------
            # Check for existing master PDFs
            existing_masters = list(MASTER_DIR.glob(f"{category}_*.pdf"))
            current_index = get_highest_index(existing_masters, category) or 1

            # Open or create master PDF
            master_path = MASTER_DIR / f"{category}_{current_index}.pdf"
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
                    desc=f"Processing PDFs for {category}",
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
                                    / f"{category}_{current_index}.pdf"
                                )
                                master_doc = pymupdf.open()
                                master_doc.new_page()
                                incremental = False

                            # Add PDF to master
                            page_offset = master_doc.page_count
                            master_doc.insert_pdf(chunk)

                            # Record which pages in the master PDF this document occupies
                            url_key = "https://" + pdf_path.stem.replace("_", "/")
                            # Update the URL data in the correct category
                            pdf_dict[category][url_key]["master_pdf"] = str(master_path)
                            pdf_dict[category][url_key]["page_number"] = page_offset

                        finally:
                            chunk.close()
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


def _process_transcripts() -> None:
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
    # separate method so we can retain link to master_pdf, page_number
    pdf_dict = _load_urls()
    
    for category, urls in pdf_dict.items():
        logger.info(f"Processing transcripts for category: {category}")
        for url, data in urls.items():
            if data.get("type") == "mp4" and data.get("video_urls") and not data["status"] == "SUCC":
                video_urls = data["video_urls"]
                logger.debug(
                    f"Processing {len(video_urls)} video transcripts for page: {url}"
                )
                try:
                    for video_url in video_urls:
                        logger.debug(f"Processing video transcript for: {video_url}")
                        try:
                            transcript_doc = transcribe_video(
                                video_url,
                                category=category,
                                master=data["master_pdf"],
                                master_page=data["page_number"],
                            )
                            combine_transcript(transcript_doc)
                        except Exception as e:
                            logger.error(f"Failed to process video {video_url}: {str(e)}")
                            data["status"] = "FAIL"
                            raise ProcessingError(f"Video processing failed: {str(e)}")
                    
                    # Only update status to SUCC if all videos were processed successfully
                    data["status"] = "SUCC"
                    logger.info(f"Successfully processed all videos for {url}")
                except Exception as e:
                    logger.error(f"Failed to process videos for {url}: {str(e)}")
                    data["status"] = "FAIL"
                    raise ProcessingError(f"Transcription processing failed: {str(e)}")
    
    _save_urls(pdf_dict)
    logger.info("Completed processing all video transcripts")


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
    
    # Find the category and data for the given pdf_key
    found_category = None
    found_data = None
    for category, urls in pdf_dict.items():
        if pdf_key in urls:
            found_category = category
            found_data = urls[pdf_key]
            break
    
    if not found_category:
        raise KeyError(f"PDF key '{pdf_key}' not found in URL database")
    if not found_data.get("master_pdf"):
        raise ResourceNotFoundError(f"No master PDF associated with key '{pdf_key}'")

    if found_data.get("master_pdf"):
        start_page = found_data["page_number"]
        
        # Create a flattened list of all URLs in the same master PDF
        master_pdf_urls = []
        for category, urls in pdf_dict.items():
            for url, data in urls.items():
                if data.get("master_pdf") == found_data["master_pdf"]:
                    master_pdf_urls.append((url, data))
        
        # Sort by page number to maintain order
        master_pdf_urls.sort(key=lambda x: x[1].get("page_number", float('inf')))
        
        try:
            master_doc = pymupdf.open(str(found_data["master_pdf"]))
            end_page = master_doc.page_count - 1
            # Find the next PDF in the same master file
            current_index = next(i for i, (url, _) in enumerate(master_pdf_urls) if url == pdf_key)
            if current_index < len(master_pdf_urls) - 1:
                next_url, next_data = master_pdf_urls[current_index + 1]
                if next_data.get("page_number") > start_page:
                    end_page = next_data["page_number"] - 1
                    logger.debug(f"Found next PDF in master file: {next_url}")
            
            (end_page == master_doc.page_count) and logger.debug(
                "pdf_key is last in master_file"
            )

            master_doc.delete_pages(start_page, end_page)
            master_doc.save(str(found_data["master_pdf"]), incremental=True, encryption=0)

        except ValueError as e:
            raise ValidationError(f"Invalid page range: {start_page} to {end_page}")
        except RuntimeError as e:
            raise RuntimeError(f"Failed to delete pages: {str(e)}")
        except Exception as e:
            raise ProcessingError(f"Unexpected error: {str(e)}")
        finally:
            master_doc.close()

    if delete_from_json:
        del pdf_dict[found_category][pdf_key]
        # Remove empty category if it was the last URL
        if not pdf_dict[found_category]:
            del pdf_dict[found_category]
        logger.info(f"Deleted {pdf_key} from urls.json")
    else:
        pdf_dict[found_category][pdf_key]["status"] = "PEND"

    _save_urls(pdf_dict)
    logger.info(f"Deleted pages {start_page} to {end_page} from {found_data['master_pdf']}")


# ─── SAVING ─────────────────────────────────────────────────────────────────────────


def _normalize_url(raw_url: str) -> str:
    """Normalizes a URL by standardizing format and removing unnecessary components.

    Args:
        raw_url (str): The URL to normalize.

    Returns:
        str: Normalized URL with:
            - Scheme in lowercase
            - Domain in lowercase
            - Path is preserved as is
            - No trailing slash
            - No query parameters or fragments
    """
    # components of url, urlparse seperates into 6 fields
    parts = urlparse(raw_url, scheme="http")
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = (parts.path or "")  # Safely handle None case
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


def _add_url(saved_links: dict, category: str, url: str, status: str = "PEND", file_type: str = "pdf") -> None:
    """Adds a new URL to the saved_links dictionary under the specified category.

    Args:
        saved_links (dict): Dictionary of categories containing URLs and their metadata.
        category (str): The category to add the URL under.
        url (str): The URL to add.
        status (str, optional): Status of the URL. Must be "PEND", "FAIL", or "SUCC". Defaults to "PEND".
        file_type (str, optional): Type of file. Defaults to "pdf".

    Raises:
        ValidationError: If status is invalid or URL already exists in category.
    """
    status = status.upper()
    if status not in {"PEND", "FAIL", "SUCC"}:
        raise ValidationError("Status must be PEND, FAIL or SUCC")
    url = _normalize_url(url)

    if category not in saved_links:
        saved_links[category] = {}

    if url in saved_links[category]:
        raise ValidationError(f"URL {url} already exists in category {category}")
    else:
        saved_links[category][url] = {
            "type": file_type,
            "master_pdf": None,
            "page_number": None,
            "status": status,
            #"video_urls": [] defined in process_transcripts, 
        }


def _save_urls(saved_links: dict) -> None:
    """Saves the saved_links dictionary to the URLs file in JSON format.

    Args:
        saved_links (dict): Dictionary of categories containing URLs and their metadata to save.
            Format: {
                "category": {
                    "url": {
                        "type": str,
                        "master_pdf": str | None,
                        "page_number": int | None,
                        "status": str
                        "path": str
                    }
                }
            }

    Raises:
        OSError: If saving to file fails.
    """
    try:
        # Create a JSON-safe copy of the dictionary
        json_safe_links = {
            category: {
                url: {
                    **data,
                    "path": str(data.get("path", ""))  # Always convert path to string
                }
                for url, data in urls.items()
            }
            for category, urls in saved_links.items()
        }

        with open(URLS_FILE, "w", encoding="utf8") as f:
            json.dump(json_safe_links, f, indent=2, sort_keys=True)
            
        logger.debug(f"Successfully saved {len(saved_links)} categories to {URLS_FILE}")
            
    except OSError as e:
        logger.error(f"Failed to save URLs to {URLS_FILE}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while saving URLs: {e}")
        raise


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
        # Count URLs with PEND status
        pend_count = 0
        for category, urls in all_links.items():
            for url, data in urls.items():
                if data["status"] == "PEND":
                    pend_count += 1
        print(f"PENDING URL COUNT: - {pend_count}")

        download_pdfs(all_links)
        _combine_categorize_pdfs()
        _process_transcripts()
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
