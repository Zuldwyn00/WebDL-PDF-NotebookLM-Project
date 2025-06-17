import pytest
import pymupdf

#local imports
from pdf_scraper import *
from utils import *
from database import *




class TestNormalizeURL:
    """Test cases for the _normalize_url function.

    The _normalize_url function should:
    - Remove trailing slashes from URLs
    - Convert URLs to lowercase
    - Handle URLs with and without paths correctly
    """

    def test_removes_trailing_slash(self):
        """Test that _normalize_url removes trailing slashes from URLs.

        Given: A URL with a trailing slash
        When: _normalize_url is called
        Then: The trailing slash should be removed
        """
        # ARRANGE: Set up our test data
        input_url = "https://example.com/path/"
        expected_result = "https://example.com/path"

        # ACT: Call the function we're testing
        actual_result = _normalize_url(input_url)

        # ASSERT: Check if we got what we expected
        assert actual_result == expected_result

        print(f"✅ Input: {input_url}")
        print(f"✅ Expected: {expected_result}")
        print(f"✅ Got: {actual_result}")

    def test_converts_to_lowercase(self):
        """Test that _normalize_url converts the entire URL to lowercase.

        Given: A URL with mixed case characters
        When: _normalize_url is called
        Then: The entire URL should be converted to lowercase
        """
        # ARRANGE: Set up our test data
        input_url = "https://Example.com/pAth"
        expected_result = "https://example.com/path"

        # ACT: Call the function we're testing
        actual_result = _normalize_url(input_url)

        # ASSERT: Check if we got what we expected
        assert actual_result == expected_result

    def test_converts_path_to_lowercase(self):
        """Test that _normalize_url converts file paths and extensions to lowercase.

        Given: A URL with mixed case path and file extension
        When: _normalize_url is called
        Then: The path and file extension should be converted to lowercase
        """
        # ARRANGE: Set up our test data
        input_url = "https://Example.com/Path/File.PDF"
        expected_result = "https://example.com/path/file.pdf"

        # ACT: Call the function we're testing
        actual_result = _normalize_url(input_url)

        # ASSERT: Check if we got what we expected
        assert actual_result == expected_result

        print(f"✅ Input: {input_url}")
        print(f"✅ Expected: {expected_result}")
        print(f"✅ Got: {actual_result}")

    def test_handles_url_without_path(self):
        """Test that _normalize_url handles URLs without paths correctly.

        Given: A URL with only domain (no path)
        When: _normalize_url is called
        Then: Only the domain should be converted to lowercase
        """
        # ARRANGE: Set up our test data
        input_url = "http://Example.com"
        expected_result = "http://example.com"

        # ACT: Call the function we're testing
        actual_result = _normalize_url(input_url)

        # ASSERT: Check if we got what we expected
        assert actual_result == expected_result

        print(f"✅ Input: {input_url}")
        print(f"✅ Expected: {expected_result}")
        print(f"✅ Got: {actual_result}")


class TestAddURL:
    """Test cases for the _add_url function.

    The _add_url function should:
    - Add URLs to the saved_links dictionary with proper metadata
    - Validate status values and raise appropriate exceptions
    - Store category and file type information correctly
    """

    def test_adds_url_to_dictionary(self):
        """Test that _add_url correctly adds a URL with metadata to the dictionary.

        Given: An empty dictionary and valid URL parameters
        When: _add_url is called with valid status, category, and file_type
        Then: The URL should be added as a key with correct metadata values
        """
        # ARRANGE: Set up our test data
        saved_links = {}  # Start with empty dictionary
        test_url = "https://example.com/test"

        # ACT: Call the function
        _add_url(saved_links, test_url, status="PEND", category="Test", file_type="mp3")

        # ASSERT: Check that the dictionary was modified correctly
        assert test_url in saved_links  # URL should be added as a key
        assert saved_links[test_url]["status"] == "PEND"
        assert saved_links[test_url]["category"] == "Test"
        assert saved_links[test_url]["type"] == "mp3"

        print(f"✅ Dictionary after adding URL: {saved_links}")

    def test_invalid_status_raises_error(self):
        """Test that _add_url raises ValidationError for invalid status values.

        Given: A dictionary and URL with invalid status value
        When: _add_url is called with an invalid status
        Then: A ValidationError should be raised with appropriate message
        """
        # ARRANGE: Set up our test data
        saved_links = {}
        test_url = "https://example.com/test"
        exc_expected = ValidationError("Status must be PEND, FAIL or SUCC")

        # ACT & ASSERT: Check that the function raises the correct error
        with pytest.raises(ValidationError) as exc_result:
            _add_url(saved_links, test_url, status="INVALID")

        # Verify the error message
        assert str(exc_result.value) == str(exc_expected)
        print(f"✅ Got expected error: {exc_result.value}")


class TestOCR:
    """Test cases for the apply_ocr function.

    the apply_ocr function should:
    - Check if the document has at least 2 images
    - If it does, apply OCR to the document by creating a temp file and running ocrmypdf
    - Return the OCRed document
    """

    def test_apply_ocr_with_images(self):  # TODO: Add test for apply_ocr with images
        """Test that apply_ocr applies OCR to a document with images.

        Given: A pymupdf.Document object with at least 2 images
        When: apply_ocr is called
        Then: The document should be OCRed and returned
        """
        return


class TestRemovePDF:
    """Test cases for the remove_pdf function.

    The remove_pdf function should:
    - Delete a PDF from the master_file it is found in by getting the start and end page numbers of the PDF in the dict based on the given key.
    """

    def test_delete_pdf_in_safe_page_range(self):
        """Test the remove_pdf function using a safe pdf_key

        Given: A PDF that is known have a pdf after it so that the page range doesnt go out of bounds
        When: remove_pdf is called with the key of the PDF
        Then: The PDF should be deleted from the master_file and the page range should be updated in the dictionary - still to be added

        Run with: python -m pytest tests/test_scraper.py::TestRemovePDF::test_delete_pdf_in_safe_page_range -v
        """
        pdf_dict = _load_urls()
        input_key = "https://smartadvocate.na4.teamsupport.com/knowledgeBase/21938490"

        with pymupdf.open(pdf_dict[input_key]["master_pdf"]) as master_doc:
            starting_total_master_pages = master_doc.page_count

        with pymupdf.open(pdf_dict[input_key]["path"]) as input_doc:
            expected_total_master_pages = (
                starting_total_master_pages - input_doc.page_count
            )

        remove_pdf(input_key)

        with pymupdf.open(pdf_dict[input_key]["master_pdf"]) as master_doc:
            actual_total_master_pages = master_doc.page_count

        assert actual_total_master_pages == expected_total_master_pages

    def test_delete_last_pdf_in_dict(self):
        """Test the remove_pdf function using an unsafe pdf_key where it is the last pdf in the dictionary and the end of the master_file so there is
            no pdf after it to use as a page range reference. Error testing for if there is a pdf after but from different master_file is seperate test.

        Given: A PDF that is key that is at the end of the master_file, known to have no pdf after it so that the page range goes out of bounds
        When: remove_pdf is called with the key of the PDF
        Then: The PDF should be deleted from the master_file and should handle the page not having a next pdf

        Run with: python -m pytest tests/test_scraper.py::TestRemovePDF::test_delete_last_pdf_in_dict -v
        """
        pdf_dict = _load_urls()
        input_key = "https://smartadvocate.na4.teamsupport.com/knowledgebase/21992632"

        with pymupdf.open(pdf_dict[input_key]["master_pdf"]) as master_doc:
            starting_total_master_pages = master_doc.page_count

        with pymupdf.open(pdf_dict[input_key]["path"]) as input_doc:
            expected_total_master_pages = (
                starting_total_master_pages - input_doc.page_count
            )

        remove_pdf(input_key)

        with pymupdf.open(pdf_dict[input_key]["master_pdf"]) as master_doc:
            actual_total_master_pages = master_doc.page_count

        assert actual_total_master_pages == expected_total_master_pages

    def test_delete_pdf_where_next_dict_item_is_from_different_master_file(self):
        """Test the remove_pdf function where the next dict item is from a different master_file

        Given: A PDF that is key that where the next dict item is from a different master_file
        When: remove_pdf is called with the key of the PDF
        Then: The PDF should be deleted from the master_file and should should not delete from the other master_file or use the wrong page range

        Run with: python -m pytest tests/test_scraper.py::TestRemovePDF::test_delete_pdf_where_next_dict_item_is_from_different_master_file -v
        """
        pdf_dict = _load_urls()
        input_key = "https://smartadvocate.na4.teamsupport.com/knowledgeBase/21691968"

        with pymupdf.open(pdf_dict[input_key]["master_pdf"]) as master_doc:
            starting_total_master_pages = master_doc.page_count

        with pymupdf.open(pdf_dict[input_key]["path"]) as input_doc:
            expected_total_master_pages = (
                starting_total_master_pages - input_doc.page_count
            )

        remove_pdf(input_key)

        with pymupdf.open(pdf_dict[input_key]["master_pdf"]) as master_doc:
            actual_total_master_pages = master_doc.page_count

        assert actual_total_master_pages == expected_total_master_pages

    def test_delete_pdf_where_pdfkey_is_not_in_dictionary(self):
        """Test the remove_pdf function where the given pdf_key is not in the dictionary

        Given: A pdf_key that is not in the dictionary
        When: remove_pdf is called with the key of the PDF
        Then: The function should raise a PDFNotFoundError

        Run with: python -m pytest tests/test_scraper.py::TestRemovePDF::test_delete_pdf_where_pdfkey_is_not_in_dictionary -v
        """
        pdf_dict = _load_urls()
        input_key = "https://smartadvocate.na4.teamsupport.com/knowledgebase/99999999"

        with pytest.raises(KeyError):
            remove_pdf(input_key)

    def test_delete_pdf_where_master_file_doesnt_exist(self):
        """Test the remove_pdf function where the master_file is empty

        Given: A master_file that is empty
        When: remove_pdf is called with the key of the PDF
        Then: The function should raise a PDFNotFoundError

        Run with: python -m pytest tests/test_scraper.py::TestRemovePDF::test_delete_pdf_where_master_file_is_empty -v
        """
        pdf_dict = _load_urls()
        input_key = "https://smartadvocate.na4.teamsupport.com/knowledgebase/21992632"

        with pytest.raises(ResourceNotFoundError):
            remove_pdf(input_key)


class TestDB:
    """
    Test cases for the databases functions
    """
    @pytest.fixture(scope="function")
    def test_db(self):
        """Fixture to create a fresh in-memory database for each test."""
        # Initialize in-memory database
        engine = init_db(db_path=":memory:", db_type="sqlite")
        return engine
        # Cleanup happens automatically when the in-memory database is closed
        
    def test_add_db_category_where_category_doesnt_exist_already(self, test_db):
        """Test that add_db_category correctly adds a new category to the database.

        Given: A database and a new category name
        When: add_db_category is called with the category name
        Then: The category should be added to the database and return True
             If the category already exists, it should return False

        Run with: python -m pytest tests/test_scraper.py::TestDB::test_add_db_category_where_category_doesnt_exist_already -v
        """
        expected_category = "Knowledge_Base"
        
        # Use a session context manager to keep the session open while accessing the category
        with get_db_session(test_db) as session:
            add_db_category(name="Knowledge_Base", session=session)
            returned_category = session.query(Category).filter(Category.name == "Knowledge_Base").first()
            assert returned_category.name == expected_category

    def test_add_db_category_where_category_already_exists(self, test_db):
        """Test that add_db_category returns False when category already exists.

        Given: A database with an existing category
        When: add_db_category is called with the same category name
        Then: The function should return False

        Run with: python -m pytest tests/test_scraper.py::TestDB::test_add_db_category_where_category_already_exists -v
        """
        
        category_name = "Test_Category"
        # First add the category
        with get_db_session(test_db) as session:
            first_result = add_db_category(name=category_name, session=session)
            assert first_result is True

            category_count = session.query(Category).filter(Category.name == category_name).count()
            assert category_count == 1

            # Try to add it again
            second_result = add_db_category(name=category_name, session=session)
            assert second_result is False

            category_count = session.query(Category).filter(Category.name == category_name).count()
            assert category_count == 1

    def test_add_db_category_where_category_is_empty(self, test_db):
        """Test that add_db_category handles empty category names correctly.

        Given: A database with an existing category
        When: add_db_category is called with an empty category name (whitespace)
        Then: The function should return False and not add the empty category

        Run with: python -m pytest tests/test_scraper.py::TestDB::test_add_db_category_where_category_is_empty -v
        """
        category_name = " "

        with get_db_session(test_db) as session:
            with pytest.raises(ValueError):
                add_db_category(category_name, session=session)

    def test_add_masterpdf_where_pdf_doesnt_exist_already(self, test_db):
        """Test that add_db_masterpdf correctly adds a new master PDF to the database.

        Given: A database and a new master PDF name
        When: add_db_masterpdf is called with the master PDF name
        Then: The master PDF should be added to the database and the returned record
             should match the expected name

        Run with: python -m pytest tests/test_scraper.py::TestDB::test_add_masterpdf_where_pdf_doesnt_exist_already_and_category_exists -v
        """
        expected_master_name = "Test_Master"
        expected_category_name = "Test_Category"
        expected_master_filepath = "T:/Test/Testing/Test.pdf"

        with get_db_session(test_db) as session:
            first_result = add_db_masterpdf(name=expected_master_name, category_name=expected_category_name, file_path=expected_master_filepath, session=session)
            assert first_result is False

            category_count = session.query(MasterPDF).filter(MasterPDF.name == expected_master_name).count()
            assert category_count == 0

            add_db_category(expected_category_name)
            second_result = add_db_masterpdf(name=expected_master_name, category_name=expected_category_name, file_path=expected_master_filepath, session=session)
            assert second_result is True

            category_count = session.query(MasterPDF).filter(MasterPDF.name == expected_master_name).count()
            assert category_count == 1
            
    def test_add_masterpdf_where_pdf_exists_already(self, test_db):
        """Test that add_db_masterpdf prevents duplicate master PDFs from being added.

        Given: A database with an existing master PDF
        When: add_db_masterpdf is called with the same name
        Then: The function should return False and not add a duplicate entry

        Run with: python -m pytest tests/test_scraper.py::TestDB::test_add_masterpdf_where_pdf_exists_already -v
        """

        expected_master_name = "Test_Master"
        expected_category_name = "Test_Category"
        expected_master_filepath = "T:/Test/Testing/Test.pdf"

        with get_db_session(test_db) as session:
            add_db_masterpdf(name=expected_master_name, category_name=expected_category_name, file_path=expected_master_filepath, session=session)

            first_result = add_db_masterpdf(name=expected_master_name, category_name=expected_category_name, file_path=expected_master_filepath, session=session)
            assert first_result is False

            category_count = session.query(MasterPDF).filter(MasterPDF.name == expected_master_name).count()
            assert category_count == 0
        
    def test_assign_page_number_where_no_targetpage_is_given(self, test_db):

        given_master_name = "Test_Master"
        given_category_name = "Test_Category"
        given_master_filepath = "T:/Test/Testing/Test_Master.pdf"

        with get_db_session(test_db) as session:
            assert add_db_category(given_category_name, session=session)
            assert add_db_masterpdf(given_master_name, given_category_name, given_master_filepath, session=session)
        
            assert add_db_pdf("Test_PDF1", given_master_name, file_path=None, session=session)
            page1 = get_db_pdf("Test_PDF1", session=session).master_page_number
            assert page1 == 0

            assert add_db_pdf("Test_PDF2", given_master_name, file_path=None, session=session)
            page2 = get_db_pdf("Test_PDF2", session=session).master_page_number
            assert page2 == 1