"""
Test suite for pdf_scraper module.

This module contains unit tests for the PDF scraper functionality,

Test Classes:
    TestNormalizeURL: Tests for URL normalization functionality
    TestAddURL: Tests for URL addition to dictionary functionality
"""

import pytest
from pdf_scraper import _normalize_url, _add_url, ScraperExceptions, apply_ocr
import pymupdf


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
        """Test that _add_url raises StatusError for invalid status values.
        
        Given: A dictionary and URL with invalid status value
        When: _add_url is called with an invalid status
        Then: A StatusError should be raised with appropriate message
        """
        # ARRANGE: Set up our test data
        saved_links = {}
        test_url = "https://example.com/test"
        exc_expected = ScraperExceptions.StatusError("Status must be PEND, FAIL or SUCC")

        # ACT & ASSERT: Check that the function raises the correct error
        with pytest.raises(ScraperExceptions.StatusError) as exc_result:
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

    def test_apply_ocr_with_images(self): #TODO: Add test for apply_ocr with images
        """Test that apply_ocr applies OCR to a document with images.
        
        Given: A pymupdf.Document object with at least 2 images
        When: apply_ocr is called
        Then: The document should be OCRed and returned
        """
        return
