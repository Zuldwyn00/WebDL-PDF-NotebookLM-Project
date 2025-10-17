SmartAdvocate Data Extraction and Processing Tool

Overview

This application automates the extraction and organization of knowledgebase content from SmartAdvocate’s online resources. It retrieves web pages, documents, and videos, converts them into structured, searchable files, and prepares them for AI-assisted systems within the firm.

How It Works

    Data Collection

        The tool crawls SmartAdvocate’s internal knowledgebase and retrieves both page and document data.

        Each page is downloaded, cleaned, and categorized by topic.

        Large files are automatically split and organized into “master” PDFs, each within a set size limit to maintain readability and quick access.

    Video Transcription

        Videos from the knowledgebase are transcribed and saved as searchable text documents.

        These transcripts are included in the same folder structure as related knowledgebase content for full coverage across media types.

    Categorization and File Management

        Extracted files are grouped by subject and jurisdictional relevance.

        The system tracks processed files in a JSON registry to prevent duplicates and support incremental updates.

        File paths and categories are dynamically managed for reuse in downstream tools and applications.

    Integration with Firm Systems

        Processed data serves as the foundation for internal AI tools such as the Legal Notebook and Lead Scoring system.

        The export structure is consistent, making it easy to ingest the data into other AI or database-driven applications.

Key Features

    Automated retrieval and categorization of SmartAdvocate knowledgebase data

    PDF merging system with automatic rollover for size limits

    Video-to-text transcription and inclusion in unified datasets

    Duplicate prevention via tracked JSON registry

    Configurable file paths and categories for flexible integration

    Designed to run independently or as a background process feeding other firm tools

Usage

Run the application via the included .bat file or directly from the main Python entry script. The tool automatically checks for new or updated pages and only processes unindexed content, minimizing bandwidth and runtime.

Notes

This project was developed for internal firm use to support automation and knowledgebase expansion. It focuses on reliability, transparency, and easy integration into existing workflows without altering SmartAdvocate’s native systems.
