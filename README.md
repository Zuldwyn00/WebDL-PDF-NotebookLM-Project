# PDF and Video Content Scraper

A Python-based tool for scraping, processing, and organizing PDFs and video content from web sources. This tool is specifically designed to work with SmartAdvocate's knowledge base. It is meant to be used with Google's NotebookLM in order to summarize, find, and organize the information from the SmartAdvocate knowledge base.

## Features

- 🔄 **Automated Content Scraping**: Automatically scrapes PDFs and videos from specified web pages
- 📑 **Smart Organization**: Categorizes content based on their source categories
- 🔍 **OCR Processing**: Automatically applies OCR to PDFs with images
- 📚 **Master Document Creation**: Combines related PDFs and video transcripts into master documents
- 📊 **Size Management**: Automatically splits master documents when they exceed size limits
- 🎥 **Video Transcription**: Automatically transcribes video content using OpenAI's Whisper
- 📝 **Detailed Logging**: Comprehensive logging of all operations with custom handlers
- 📈 **Progress Tracking**: Visual progress bars for long-running operations
- ⚙️ **Configurable**: Easy configuration through YAML files

## Prerequisites

- Python 3.7+
- Chrome browser installed
- Internet connection
- FFmpeg (for video processing)
- Tesseract OCR (for PDF processing)

## Installation

1. Clone this repository:
```bash
#git clone [repository-url] 
#cd [repository-name]
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

## Project Structure

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

The script will:
1. Scrape all available content from the configured website using Selenium
2. Download and process each PDF and check if page contains videos
3. Apply OCR to PDFs where necessary
4. Transcribe video content using Whisper
5. Combine content into master documents by category
6. Generate detailed logs of the process

## Config

The application is configured through YAML files:

- `config/config.yaml`: Main configuration file containing:
  - Website settings
  - Directory paths
  - PDF size limits
  - Transcription settings
  - Logging configuration

- `config/sensitive_config.yaml`: Sensitive configuration containing:
  - User agent information
  - Contact details
  - Other sensitive settings

## Logging

Logs are stored in the `logs` directory with timestamps. Each run creates a new log file with detailed information about the scraping process. The logging system includes:
- Custom handlers for progress bar integration
- File and console output
- Detailed error tracking
- Operation timing information

## Error Handling

The application includes comprehensive error handling with custom exceptions for:
- Download failures
- PDF processing errors
- OCR failures
- Video processing errors
- Transcription failures
- File system operations

## Contributing

Contributions are not needed, thank you!

## License

[Add your license information here]

## Author

Zuldwyn00 <zuldwyn@gmail.com>

## Version

Current version: 2.0
Last updated: 2025-05-23 