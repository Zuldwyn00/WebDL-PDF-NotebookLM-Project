# PDF and Video Content Scraper

A Python-based tool for scraping, processing, and organizing PDFs and video content from web sources. This tool is specifically designed to work with SmartAdvocate's knowledge base and integrates with Google's NotebookLM for summarizing, finding, and organizing information from the SmartAdvocate knowledge base.

## Features

- Automated Content Scraping: Automatically scrapes PDFs and videos from specified web pages
- Smart Organization: Categorizes content based on their source categories
- OCR Processing: Automatically applies OCR to PDFs with images
- Master Document Creation: Combines related PDFs and video transcripts into master documents
- Size Management: Automatically splits master documents when they exceed size limits
- Video Transcription: Automatically transcribes video content using OpenAI's Whisper
- Detailed Logging: Comprehensive logging of all operations with custom handlers
- Progress Tracking: Visual progress bars for long-running operations
- Configurable: Easy configuration through YAML files

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Configuration](#configuration)
- [Logging](#logging)
- [Error Handling](#error-handling)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)
- [Version](#version)

## Prerequisites

- Python 3.7+
- Chrome browser
- Internet connection
- FFmpeg (for video processing)
- Tesseract OCR (for PDF processing)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/Zuldwyn00/NoteBookLM_Project
cd NoteBookLM_Project
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

3. Install FFmpeg:
   - Windows: Download from [FFmpeg website](https://ffmpeg.org/download.html)
   - Linux: `sudo apt-get install ffmpeg`
   - macOS: `brew install ffmpeg`

4. Install Tesseract OCR:
   - Windows: Download and install from [Tesseract GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
   - Linux: `sudo apt-get install tesseract-ocr`
   - macOS: `brew install tesseract`

## Project Structures

```
PDFScraper/
├── PDFs/
│   ├── master/              # Combined master PDFs
│   ├── transcript_master/   # Combined video transcripts
│   └── YYYY-MM-DD/         # Current dated downloaded content
├── config/
│   ├── config.yaml         # Main configuration
│   └── sensitive_config.yaml # Sensitive configuration
├── logs/                   # Log files
├── data/
│   └── urls.json          # URL tracking database
├── pdf_scraper.py         # Main PDF scraping script
├── transcribe_video.py    # Video transcription module
└── utils.py              # Utility functions
```

## Usage

1. Configure the application:
   - Copy `config/config.yaml.example` to `config/config.yaml`
   - Copy `config/sensitive_config.yaml.example` to `config/sensitive_config.yaml`
   - Update the configuration files with your settings

2. Run the main script:
```bash
python pdf_scraper.py
```

The script performs the following operations:
1. Scrapes all available content from the configured website using Selenium
2. Downloads and processes each PDF and checks if pages contain videos
3. Applies OCR to PDFs where necessary
4. Transcribes video content using Whisper
5. Combines content into master documents by category
6. Generates detailed logs of the process

## Configuration

The application uses two YAML configuration files:

### Main Configuration (`config/config.yaml`)
- Website settings
- Directory paths
- PDF size limits
- Transcription settings
- Logging configuration

### Sensitive Configuration (`config/sensitive_config.yaml`)
- User agent information
- Contact details
- Other sensitive settings

## Logging

The application maintains detailed logs in the `logs` directory. Each run creates a new timestamped log file containing:
- Operation details and timing
- Error tracking and debugging information
- Progress updates
- File and console output

## Error Handling

The application implements comprehensive error handling for:
- Download failures
- PDF processing errors
- OCR failures
- Video processing errors
- Transcription failures
- File system operations

## Contributing

This is a private project and is not accepting contributions at this time.

## License

[License information pending]

## Contact

Author: Zuldwyn00  
Email: zuldwyn@gmail.com

## Version

Version: 2.1.0
Last updated: 2025-05-30