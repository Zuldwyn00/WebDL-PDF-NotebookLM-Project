# Database Refactoring Plan: `pdf_scraper.py`

This document outlines the necessary steps to refactor `pdf_scraper.py` from using a JSON file (`urls.json`) to a SQLite database managed by `database.py`.

---

## Primary Goals
1.  Replace all file I/O for `urls.json` with database transactions.
2.  Improve data integrity, consistency, and scalability.
3.  Make the data management process more robust and less error-prone.
4.  Fix linter errors and incomplete functions in `database.py`.

---

## I. Database Schema and Setup (`database.py`)

-   [ ] **Add `status` column to `PDF` model:** This is critical for tracking the state (`PEND`, `SUCC`, `FAIL`) of each scraped URL.
    -   `status: Mapped[str] = mapped_column(default="PEND")`
-   [ ] **Add `video_urls` column to `PDF` model:** To store video URLs associated with a PDF. Using a `JSON` type is recommended.
    -   Import `from sqlalchemy import JSON`.
    -   `video_urls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)`
-   [ ] **Make `master_id` and `master_page_number` nullable in `PDF` model:** A PDF record must be able to exist before it's assigned to a master PDF.
    -   `master_id: Mapped[Optional[int]] = mapped_column(ForeignKey("master_PDF.id"), nullable=True)`
    -   `master_page_number: Mapped[Optional[int]] = mapped_column(nullable=True)`
-   [ ] **Fix syntax errors in `process_new_pdf`:** Correct the `except someerrorhere:` block and the unclosed parenthesis in `add_db_pdf`.
-   [ ] **Complete `process_new_pdf` implementation:** Flesh out this function to be a high-level orchestrator for adding new PDFs, handling category/master PDF creation, and adding the final PDF record.

---

## II. Core Data Function Replacement

-   [ ] **Deprecate `urls.json`:**
    -   Remove the `URLS_FILE` constant in `pdf_scraper.py`.
    -   Remove the file creation logic for `URLS_FILE`.
-   [ ] **Remove old data handling functions in `pdf_scraper.py`:**
    -   [ ] `_load_urls()`
    -   [ ] `_save_urls()`
    -   [ ] `_add_url()`
    -   [ ] `sort_urls_by_page_number()` (sorting will be handled by SQLAlchemy queries).

---

## III. Refactor `pdf_scraper.py` Functions

-   [ ] **Initialize Database:**
    -   In `run_script()` or `main()`, call `init_db()` from `database.py` at startup.

-   [ ] **Refactor `get_links()`:**
    -   Replace `_load_urls()` with a database query to fetch all existing PDF names (URLs) to prevent duplicates.
    -   When a new link is found, use a database session to:
        1.  Check if the `Category` exists with `get_db_category()`. If not, create it with `add_db_category()`.
        2.  Create a new `PDF` record with `add_db_pdf()`, setting the `name` to the URL and `status` to `PEND`.

-   [ ] **Refactor `download_pdfs()`:**
    -   Fetch all `PDF` records from the database where `status != 'SUCC'`.
    -   On successful download of a PDF, update the corresponding `PDF` record's `status` to `'SUCC'`.
    -   If videos are found, update the `file_type` to `'mp4'` and populate the `video_urls` field.
    -   On failure, update the `status` to `'FAIL'`.

-   [ ] **Refactor `_combine_categorize_pdfs()`:**
    -   Query the database for all `PDF` records that have been successfully downloaded (`status = 'SUCC'`) but not yet assigned to a master PDF (`master_id IS NULL`).
    -   Group the results by category.
    -   For each category:
        1.  Query for an existing `MasterPDF` or create a new one using `add_db_masterpdf()`.
        2.  As each PDF is processed and added to the `pymupdf` document, update its `PDF` record in the database with the `master_id` and the correct `master_page_number`.

-   [ ] **Refactor `_process_transcripts()`:**
    -   Query the database for `PDF` records where `file_type == 'mp4'` and `status != 'SUCC'`.
    -   Use the `video_urls` from the record for transcription.
    -   After processing, update the `status` of the `PDF` record to `'SUCC'`.

-   [ ] **Refactor `delete_pdf()`:**
    -   Use `get_db_pdf()` to find the PDF record by its `pdf_key` (URL/name).
    -   Retrieve `master_pdf.file_path` and `master_page_number` from the record.
    -   Perform the `pymupdf` page deletion logic.
    -   Update the `PDF` record: set `master_id` and `master_page_number` to `None` and update `status`. If `delete_from_database` is true, delete the record entirely.

---

## IV. Testing

-   [ ] **Create `tests/test_database.py`:**
    -   Write unit tests for all functions in `database.py`.
    -   Use an in-memory SQLite database for testing to ensure tests are fast and isolated.
-   [*] **Update `tests/test_scraper.py`:**
    -   Mock the database session and return values to test the logic in `pdf_scraper.py` without needing a live database.

---

## V. Final Cleanup

-   [ ] Remove all dead code related to the old JSON system.
-   [ ] Update docstrings in `pdf_scraper.py` to reflect the new database interactions and remove references to `saved_links` dict.
-   [ ] Review all logging messages to ensure they are still relevant.
    [ ] Update requirements.txt with new imports from database and schemas