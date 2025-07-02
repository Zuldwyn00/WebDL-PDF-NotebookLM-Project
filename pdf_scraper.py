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

# 4) # Fix error where sometimes pages dont delete properly giving an invalid dict key mupdf error.

# 5) Clean up unneccesary try and except blocks to make code more readable, focus on if the error can be fixed, then use a try except block
#    if the error cannot be fixed, raise an exception instead of doing a whole try except block

# INPROGRESS:

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
from pathlib import Path
from tqdm import tqdm
from functools import wraps
from urllib.parse import urlparse
import os, base64, io
import pymupdf, ocrmypdf


# Local imports
from transcribe_video import transcribe_video, combine_transcript
from database import (
    get_session,
    Category,
    MasterPDF,
    PDF,
    UnprocessedPDF,
    DatabaseService,
    init_db,
)
import schemas
from utils import (
    PDFProcessingError,
    setup_logger,
    load_config,
    ensure_directories,
    get_doc_size_bytes,
    get_highest_index,
    ScraperError,
    DownloadError,
    ProcessingError,
    ValidationError,
    ResourceNotFound,
)

# ─── LOGGER & CONFIG ────────────────────────────────────────────────────────────────
config = load_config()
logger = setup_logger(__name__, config)

# Log startup information
logger.info("PDF Scraper v%s starting up", __version__)

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
    logger.info("Created file: %s", URLS_FILE)


# ─── WEB SCRAPING FUNCTIONS ─────────────────────────────────────────────────────────

def wait_for_page_ready(driver: webdriver.Chrome):
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


# ─── PDF MANIPULATION ───────────────────────────────────────────────────────────────
def with_pdf(pdf_key_arg: str | int):

    def decorator(func):
        @wraps(func)
        @with_session
        def wrapper(*args, **kwargs):

            pdf_key = kwargs.get(pdf_key_arg)
            if pdf_key is None:
                raise ValueError(f"'{pdf_key_arg}' must be provided as a keyword argument.")
            
            doc = None
            try:
               pdf_doc = None
            except:
                pass

def apply_ocr(pdf_bytes: bytes) -> bytes:
    """OCR a PDF's bytes and return the OCRed version with searchable text.

    Args:
        pdf_bytes (bytes): The document bytes to apply OCR to.

    Returns:
        bytes: OCRed version of the document as bytes.

    Raises:
        ProcessingError: If OCR processing fails.
    """

    min_images = config["pdf"]["minimum_ocr_pages"]

    # We need to open the document to check for images.
    doc = None
    try:
        doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        # Check if document has any images on any page
        image_count = 0
        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)
            image_count += len(images)
            if image_count >= min_images:
                break  # to avoid unnecessary processing break after hitting the minimum

        # Skip OCR if less than min_images images found
        if image_count < min_images:
            logger.debug(
                "Less than %d images found in document (%d found), skipping OCR",
                min_images,
                image_count,
            )
            return pdf_bytes
    except Exception as e:
        logger.warning(
            "Could not check for images in PDF, proceeding with OCR anyway. Error: %s", e
        )
    finally:
        if doc:
            doc.close()

    input_stream = io.BytesIO(pdf_bytes)
    output_stream = io.BytesIO()

    try:
        ocrmypdf.ocr(input_file=input_stream, output_file=output_stream, redo_ocr=True)
        logger.info("OCR complete, returning new document bytes")
        output_stream.seek(0)
        return output_stream.getvalue()

    except Exception as e:
        logger.error("Error during OCR: %s", e)
        raise ProcessingError(f"OCR processing failed: {e}")
    finally:
        # Clean up streams
        input_stream.close()
        output_stream.close()


def delete_pdf(pdf_key: str, status: str = "PEND", delete_from_database: bool = False) -> None:
    """Removes a PDF from its master file and optionally from the URL database.

    Args:
        pdf_key (str): The URL key of the PDF to remove.
        status (str): Defaults to changing status to PEND, can define as "PEND, SUCC, FAIL" otherwise.
        delete_from_database (bool, optional): Whether to delete the entry from urls.json.
            Defaults to False.

    Raises:
        KeyError: If PDF key is not found in URL database.
        ResourceNotFound: If master PDF is not found.
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
        raise ResourceNotFound(f"No master PDF associated with key '{pdf_key}'")

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
                    logger.debug("Found next PDF in master file: %s", next_url)
            
            (end_page == master_doc.page_count) and logger.debug(
                "pdf_key is last in master_file"
            )

            master_doc.delete_pages(start_page, end_page)
            try:
                logger.debug("Attempting incremental save...")
                master_doc.saveIncr()
            #sometimes the deletion fails because the pdf structure is broken or something im not sure why 
            # issue might be caused by how saveIncr works, it never deletes the pages, it appends information to the end of the
            # pdf saying that x-x pages are no longer in use, which actually increases the file size. 
            except pymupdf.mupdf.FzErrorSyntax as e:
                logger.warning(
                    "Incremental save failed for %s with error: %s. ",
                    found_data['master_pdf'], e
                )
                raise PDFProcessingError
        
        except ValueError as e:
            raise ValidationError(f"Invalid page range: {start_page} to {end_page}")
        except RuntimeError as e:
            raise RuntimeError(f"Failed to delete pages: {e}")
        except Exception as e:
            raise ProcessingError(f"Unexpected error: {e}")
        finally:
            master_doc.close()

    if delete_from_database:
        del pdf_dict[found_category][pdf_key]
        # Remove empty category if it was the last URL
        if not pdf_dict[found_category]:
            del pdf_dict[found_category]
        logger.info("Deleted %s from database", pdf_key)
    else:
        logger.info("Deleted pages %s to %s from %s", start_page, end_page, found_data['master_pdf'])
        pdf_dict[found_category][pdf_key]["page_number"] = None
        pdf_dict[found_category][pdf_key]["master_pdf"] = None
        pdf_dict[found_category][pdf_key]["status"] = status

    _save_urls(pdf_dict)

#TODO: IMPLEMENT THIS METHOD TO WORK WITH DB
def add_pdf(pdf_key: str) -> bool:
    """Adds a PDF from database into a master, can specify where with target_page which will shift all pages over to allow room
    returns True if successful, false if failure, uses page assignment logic in database to assign proper page this just handles the actual editing of the main PDF
    file to add the pages of the new PDF"""
    





    return False

# ─── SAVING ─────────────────────────────────────────────────────────────────────────
class Scraper:
    def __init__(self, db_service: DatabaseService, config: dict):
        self.db = db_service
        self.config = config
        self.driver = self._initialize_driver()

    def _initialize_driver(self) -> webdriver.Chrome:

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

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        # Use timeout from config if not specified
        timeout = config["browser"]["timeout"]
        self.driver.wait = WebDriverWait(self.driver, timeout)

        return self.driver
    
    def close_driver(self):
        if self.driver:
            self.driver.quit()

    def get_links(self, website_url: str) -> bool:
        """Scrapes all article links and video links from the website, organized by category.
            Creates a new category if existing one for found category is not present.

        Args:
            website_url (str): The base URL to scrape links from.

        Returns:
            bool(True) if successful, otherwises raises errors

        Raises:
            WebDriverException: If web scraping fails.
            TimeoutException: If page loading times out.
        """
        logger.info("Beginning get_links from: %s", website_url)
        self.driver.get(website_url)
        wait_for_page_ready(self.driver)

        # First, collect all category links from the main page
        category_links = set()
        for element in self.driver.find_elements(By.TAG_NAME, "a"):
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
                    self.driver.get(category_url)
                    wait_for_page_ready(self.driver)

                    # Get category name
                    category_name = (
                        self.driver.find_element(By.CSS_SELECTOR, "span.text.ng-binding")
                        .text.split("-", 1)[0] #website updated to have main categories that share same name like "User Manual - Administration" so we filter that out and combine them
                        .strip()
                    )
                    logger.info("Processing category: %s", category_name)
                    #create new category if category is not present already, add_resource handles check if the category already exists or not so no need to check here.
                    new_category = schemas.CategoryCreate(name=category_name)
                    self.db.add_resource(new_category)
                        
                    # get the subcategory first that contains the links we want
                    article_elements = self.driver.find_elements(
                        By.CSS_SELECTOR, "ul.article-links a"
                    )
                    # now process the subcategory to find all the links inside of it.
                    for article_element in article_elements:
                        try:
                            href = article_element.get_attribute("href")
                            if not href:
                                logger.debug("%s not href, skipping", href)
                                continue

                            # Add new links as unprocessed PDFs
                            logger.debug("link found: %s, with category %s.", href, category_name)
                            unprocessed = schemas.UnprocessedPDFCreate(url=href, category_value=category_name)
                            self.db.add_unprocessed_pdf(unprocessed)

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

        logger.info("Completed link discovery from %s", website_url)
        return True

    def download_pdf(self, unprocessed_pdf_data: schemas.UnprocessedPDFResponse) -> None:
        def _get_videos(driver: webdriver.Chrome) -> list:
            """Finds all video source URLs on the current page."""
            video_elements = driver.find_elements(By.CSS_SELECTOR, "video source")
            video_urls = []
            for video_source in video_elements:
                video_urls.append(video_source.get_attribute("src"))
            return video_urls
            
        self.driver.get(unprocessed_pdf_data.url)
        wait_for_page_ready(self.driver)
        video_urls = _get_videos(self.driver)
        try:
            pdf = self.driver.execute_cdp_cmd(
            "Page.printToPDF",
            {
                "printBackground": True,
                "paperWidth": 8.27,
                "paperHeight": 11.7,
            },
            )
            #make sure PDF file isn't too small to make sure it downloaded properly, small pdfs are probably blank
            pdf_bytes = base64.b64decode(pdf["data"])
            if len(pdf_bytes) <= 2 * 1024:
                raise DownloadError(f"PDF too small for {unprocessed_pdf_data.url}")
            
            pdf_bytes_ocr = apply_ocr(pdf_bytes)
            # Append video transciption data onto end of pdf.
            if video_urls:
                main_doc = pymupdf.open(stream=io.BytesIO(pdf_bytes_ocr), filetype="pdf")
                for video_url in video_urls:
                    transcription_doc = transcribe_video(video_url, category=(self.db.get_category(unprocessed_pdf_data.category_id)).name)
                    if transcription_doc:
                        main_doc.insert_pdf(transcription_doc)
                        transcription_doc.close()
                
                pdf_bytes_ocr = main_doc.tobytes()
                main_doc.close()

            parse = urlparse(unprocessed_pdf_data.url)
            name = (parse.netloc + parse.path).strip("/").replace("/", "_")
            final_file_name = name + ".pdf"
        
        except TimeoutException as e:
            logger.error("Timeout downloading %s: %s", unprocessed_pdf_data.url, str(e))
        except DownloadError as e:
            logger.error("Download failed for %s: %s", unprocessed_pdf_data.url, str(e))

        try:
            with open(
                os.path.join(DATED_DOWNLOAD_DIR, final_file_name), "wb"
            ) as f:
                f.write(pdf_bytes_ocr)
            logger.info(
                "Saved as -> %s filesize: %s", final_file_name, len(pdf_bytes_ocr)
            )
        except IOError as e:
            raise DownloadError(f"Failed to save PDF {final_file_name}: {e}")

        processed_pdf_data = {'id': unprocessed_pdf_data.id,
                              'url': unprocessed_pdf_data.url,
                              'file_path': final_file_name,
                              'category_value': unprocessed_pdf_data.category_id,
                            }
        update_unprocessed_pdf = schemas.UnprocessedPDFUpdate(**processed_pdf_data, video_links=video_urls)
        self.db.update_resource(update_unprocessed_pdf)
        
    def _combine_categorize_pdfs(self) -> None:
        """Combines all PDFs from the dated download directory into master PDFs by category.

        This function:
        1. Groups PDFs by category from database
        2. Creates or updates master PDFs
        3. Applies OCR if needed
        4. Updates database with master PDF locations and page numbers
        5. Splits master PDFs if they exceed size limit
        6. Moves processed PDFs from UnprocessedPDF to PDF table

        Raises:
            ProcessingError: If PDF combination or categorization fails.
            ResourceNotFoundError: If required directories or files are missing.
        """
        try:
            logger.info("Starting PDF combination and categorization")

            # ----------------------------------------------------------------------
            # SETUP: Create directories and query database for downloaded PDFs
            # ----------------------------------------------------------------------
            ensure_directories([MASTER_DIR])

            # Query unprocessed PDFs that have been downloaded (have file_path)
            unprocessed_pdfs = (
                self.db.session.query(UnprocessedPDF)
                .filter(UnprocessedPDF.file_path.isnot(None))
                .all()
            )

            if not unprocessed_pdfs:
                logger.info("No downloaded PDFs to process, skipping combination and categorization")
                return

            logger.info("Found %d downloaded PDFs to process", len(unprocessed_pdfs))

            # ----------------------------------------------------------------------
            # GROUP: Group PDFs by category
            # ----------------------------------------------------------------------
            # Group PDFs by category
            category_groups = {}
            for unprocessed_pdf in unprocessed_pdfs:
                category_name = unprocessed_pdf.category.name
                if category_name not in category_groups:
                    category_groups[category_name] = []
                
                # Build full file path
                pdf_path = DATED_DOWNLOAD_DIR / unprocessed_pdf.file_path
                if pdf_path.exists():
                    category_groups[category_name].append({
                        'unprocessed_pdf': unprocessed_pdf,
                        'file_path': pdf_path
                    })
                else:
                    logger.warning("PDF file not found: %s", pdf_path)

            # ----------------------------------------------------------------------
            # PROCESS: Process each category and create master PDFs
            # ----------------------------------------------------------------------
            for category_name, pdfs_data in category_groups.items():
                logger.info("Processing category: %s", category_name)

                if not pdfs_data:
                    logger.info("No valid PDF files for category: %s", category_name)
                    continue

                logger.debug("Found %d PDFs for category: %s", len(pdfs_data), category_name)

                # ------------------------------------------------------------------
                # Create or get master PDF for this category
                # ------------------------------------------------------------------
                # Check for existing master PDFs in database
                try:
                    category_obj = self.db.get_category(category_name)
                    existing_masters = (
                        self.db.session.query(MasterPDF)
                        .filter(MasterPDF.category_id == category_obj.id)
                        .all()
                    )
                    
                    # Find the latest master PDF or create new one
                    if existing_masters:
                        # Find the highest indexed master PDF
                        master_files = [Path(m.file_path) for m in existing_masters]
                        current_index = get_highest_index(master_files, category_name) or 1
                        
                        # Use the latest master PDF
                        current_master = next(
                            (m for m in existing_masters if str(current_index) in m.name),
                            existing_masters[-1]  # fallback to last one
                        )
                        master_path = Path(current_master.file_path)
                    else:
                        current_index = 1
                        master_path = MASTER_DIR / f"{category_name}_{current_index}.pdf"
                        current_master = None

                except ResourceNotFound:
                    logger.error("Category '%s' not found in database", category_name)
                    continue

                # Open or create master PDF document
                if master_path.exists() and current_master:
                    master_doc = pymupdf.open(str(master_path))
                    incremental = True
                    master_pdf_db = current_master
                else:
                    logger.debug("Creating new master PDF: %s", master_path)
                    master_doc = pymupdf.open()
                    master_doc.new_page()
                    incremental = False
                    
                    # Create master PDF in database
                    master_create = schemas.MasterPDFCreate(
                        name=f"{category_name}_{current_index}",
                        file_path=master_path,
                        category_value=category_name
                    )
                    self.db.add_masterpdf(master_create)
                    self.db.session.commit()  # Commit to get the ID
                    master_pdf_db = self.db.get_masterpdf(master_create.name)

                try:
                    # --------------------------------------------------------------
                    # Add each PDF to the master document
                    # --------------------------------------------------------------
                    processed_pdfs = []  # Track successfully processed PDFs
                    
                    for pdf_data in tqdm(
                        pdfs_data,
                        desc=f"Processing PDFs for {category_name}",
                        unit="pdf",
                        position=0,
                        leave=True,
                    ):
                        try:
                            unprocessed_pdf = pdf_data['unprocessed_pdf']
                            pdf_path = pdf_data['file_path']
                            
                            logger.debug("Processing %s", pdf_path.name)

                            # Apply OCR
                            chunk = apply_ocr(pymupdf.open(str(pdf_path)))

                            try:
                                # Check size limit
                                if (
                                    get_doc_size_bytes(master_doc)
                                    + get_doc_size_bytes(chunk)
                                    > MAX_MASTER_PDF_SIZE
                                ):
                                    logger.debug("Size limit reached, creating new master PDF")

                                    # Save current master
                                    master_doc.save(
                                        str(master_path),
                                        incremental=incremental,
                                        encryption=0,
                                    )
                                    master_doc.close()

                                    # Create new master PDF
                                    current_index += 1
                                    master_path = MASTER_DIR / f"{category_name}_{current_index}.pdf"
                                    master_doc = pymupdf.open()
                                    master_doc.new_page()
                                    incremental = False

                                    # Create new master PDF in database
                                    master_create = schemas.MasterPDFCreate(
                                        name=f"{category_name}_{current_index}",
                                        file_path=master_path,
                                        category_value=category_name
                                    )
                                    self.db.add_masterpdf(master_create)
                                    self.db.session.commit()
                                    master_pdf_db = self.db.get_masterpdf(master_create.name)

                                # Add PDF to master
                                page_offset = master_doc.page_count
                                master_doc.insert_pdf(chunk)

                                # Create PDF record in database
                                pdf_create = schemas.PDFCreate(
                                    url=unprocessed_pdf.url,
                                    file_path=pdf_path,
                                    master_pdf_value=master_pdf_db.name,
                                    status="SUCC",
                                    master_page_number=page_offset,
                                    video_links=unprocessed_pdf.video_links
                                )
                                self.db.add_pdf(pdf_create)
                                processed_pdfs.append(unprocessed_pdf)

                            finally:
                                chunk.close()

                        except Exception as e:
                            logger.error("Error processing %s: %s", pdf_path.name, e)
                            # Mark as failed but continue processing other PDFs
                            continue

                    # Save final master PDF
                    logger.debug("Saving master PDF: %s", master_path)
                    master_doc.save(str(master_path), incremental=incremental, encryption=0)
                    
                    # --------------------------------------------------------------
                    # CLEANUP: Remove processed PDFs from unprocessed table
                    # --------------------------------------------------------------
                    for unprocessed_pdf in processed_pdfs:
                        self.db.session.delete(unprocessed_pdf)
                    
                    self.db.session.commit()
                    logger.info("Successfully processed %d PDFs for category: %s", 
                              len(processed_pdfs), category_name)

                finally:
                    master_doc.close()

            logger.info("PDFs combined and categorized successfully")

        except Exception as e:
            logger.exception("Failed to combine and categorize PDFs: %s", str(e))
            self.db.session.rollback()
            raise ProcessingError(f"PDF processing failed: {e}")

    def process_unprocessed_pdfs(self):
        """Downloads all unprocessed PDFs that haven't been downloaded yet."""
        unprocessed_pdfs = (
            self.db.session.query(UnprocessedPDF)
            .filter(UnprocessedPDF.file_path.is_(None))
            .all()
        )
        
        if not unprocessed_pdfs:
            logger.info("No unprocessed PDFs to download")
            return
            
        logger.info("Found %d unprocessed PDFs to download", len(unprocessed_pdfs))
        
        for unprocessed_pdf in tqdm(unprocessed_pdfs, desc="Downloading PDFs", unit="pdf"):
            try:
                # Convert to response schema for download_pdf method
                unprocessed_response = schemas.UnprocessedPDFResponse.model_validate(unprocessed_pdf)
                self.download_pdf(unprocessed_response)
                logger.debug("Successfully downloaded %s", unprocessed_pdf.url)
            except Exception as e:
                logger.error("Failed to download %s: %s", unprocessed_pdf.url, e)
                continue


    def run(self):
        """
        Main execution method for the scraper.
        This method will orchestrate the scraping process, including:
        1. Discovering new article links.
        2. Downloading new content as PDFs.
        3. Combining PDFs into master files by category.
        """
        try:
            logger.info("Scraper run started.")
            
            # Step 1: Discover new links
            self.get_links(WEBSITE_LINK)
            
            # Step 2: Download unprocessed PDFs
            self.process_unprocessed_pdfs()

            self._combine_categorize_pdfs()
            
            
            
        except Exception as e:
            logger.exception("An error occurred during the scraper run: %s", e)
        finally:
            self.close_driver()
            logger.info("Scraper run finished and resources cleaned up.")

def main():
    """Entry point for the PDF scraper script.

    Runs the main scraping process and handles any top-level exceptions.
    """
    try:
        init_db()
        with get_session() as session:
            db_service = DatabaseService(session=session)
            scraper = Scraper(db_service=db_service, config=config)
            scraper.run()
    except ScraperError as e:
        logger.error("A critical error occurred: %s", e)
    except Exception as e:
        logger.error("An unexpected error occurred in main: %s", e)
    

if __name__ == "__main__":
    main()

