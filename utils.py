
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml
from tqdm import tqdm
import io
import pymupdf

# ─── CUSTOM EXCEPTIONS ────────────────────────────────────────────────────────────────
class ScraperError(Exception):
    """Base exception for all scraper-related errors."""
    pass

class DownloadError(ScraperError):
    """Raised when downloading PDFs or videos fails."""
    pass

class ProcessingError(ScraperError):
    """Raised when processing PDFs, videos, or transcripts fails."""
    pass

class ValidationError(ScraperError):
    """Raised when input validation fails (e.g., invalid status, missing files)."""
    pass

class ResourceNotFoundError(ScraperError):
    """Raised when a required resource (PDF, video, file) is not found."""
    pass

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from config.yaml and sensitive_config.yaml files.

    This function loads and merges configuration data from both the main config file
    and an optional sensitive config file. If a sensitive config exists, it will be
    merged into the main config under the 'sensitive' key.

    Args:
        config_path (Optional[str]): Path to custom config file. If None, uses default location.

    Returns:
        Dict[str, Any]: Dictionary containing merged configuration data.

    Raises:
        FileNotFoundError: If required configuration files are not found.
        ValueError: If configuration files contain invalid YAML.

    Example:
        >>> config = load_config()
        >>> print(config['website']['base_url'])
    """
    if config_path:
        main_config_path = Path(config_path)
    else:
        main_config_path = Path(__file__).resolve().parent / "config" / "config.yaml"
    
    sensitive_path = Path(__file__).resolve().parent / "config" / "sensitive_config.yaml"
    
    try:
        # Load main config
        with open(main_config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        # Load sensitive config
        if sensitive_path.exists():
            with open(sensitive_path, "r", encoding="utf-8") as f:
                sensitive = yaml.safe_load(f)
                
            # Merge sensitive config into main config
            if sensitive:
                config["sensitive"] = sensitive
                
            # Construct user agent string if needed
            if "sensitive" in config and "user_agent" in config["sensitive"]:
                ua = config["sensitive"]["user_agent"]
                config["website"]["user_agent"] = (
                    f"{ua['name']}/{ua['version']}/{ua['organization']} "
                    f"(+mailto:{config['sensitive']['contact']['email']})"
                )
                
        return config
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Configuration file not found: {e}")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing configuration file: {e}")

# ─── LOGGER ────────────────────────────────────────────────────────────────
class TqdmLoggingHandler(logging.Handler):
    """
    Custom logging handler that works with tqdm progress bars.

    This handler ensures that log messages don't interfere with tqdm progress bars
    by using tqdm.write() instead of print().
    """
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record using tqdm.write to avoid interfering with progress bars.

        Args:
            record (logging.LogRecord): The log record to emit.

        Note:
            This method uses tqdm.write() to ensure compatibility with progress bars.
        """
        try:
            msg = self.format(record)
            tqdm.write(msg, end='\n')
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logger(name: str, config: Dict[str, Any], level: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger that works with tqdm progress bars.

    Sets up a logger with console output that won't interfere with progress bars.
    Uses a custom TqdmLoggingHandler for output.

    Args:
        name (str): Name of the logger (typically __name__).
        config (Dict[str, Any]): Configuration dictionary containing logger settings.
        level (Optional[str]): Optional log level override.

    Returns:
        logging.Logger: Configured logger instance.

    Example:
        >>> logger = setup_logger(__name__, config)
        >>> logger.info("Processing started")
    """
    logger = logging.getLogger(name)
    if level is None:
        logger.setLevel(getattr(logging, config["logger"]["level"]))
    else:
        logger.setLevel(getattr(logging, level))
    
    # Create console handler with custom formatter
    console_handler = TqdmLoggingHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

# ─── DIRECTORY MANAGEMENT ──────────────────────────────────────────────────
def ensure_directories(directories: List[Path]) -> None:
    """
    Ensure all specified directories exist, creating them if necessary.

    Creates directories and any necessary parent directories if they don't exist.
    If directories already exist, this function does nothing.

    Args:
        directories (List[Path]): List of Path objects representing directories to create.

    Example:
        >>> paths = [Path("data/pdfs"), Path("data/transcripts")]
        >>> ensure_directories(paths)
    """
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

# ─── PDF UTILITIES ─────────────────────────────────────────────────────────
def get_doc_size_bytes(doc: pymupdf.Document) -> int:
    """
    Calculate the total size of a PDF document in bytes.

    Saves the document to a temporary buffer to calculate its size.

    Args:
        doc (pymupdf.Document): PyMuPDF Document object to measure.

    Returns:
        int: Size of the document in bytes.

    Example:
        >>> doc = fitz.open("example.pdf")
        >>> size = get_doc_size_bytes(doc)
        >>> print(f"Document size: {size} bytes")
    """
    buf = io.BytesIO()
    doc.save(buf)
    return buf.tell()

def get_highest_index(paths: List[Path], prefix: str) -> int:
    """
    Find the highest index number from a list of PDF files with a given prefix.

    Searches through a list of paths for files matching the pattern "{prefix}_N.pdf"
    where N is a number, and returns the highest N found.

    Args:
        paths (List[Path]): List of Path objects to search through.
        prefix (str): Filename prefix to match (e.g., "master", "transcript").

    Returns:
        int: Highest index number found, or 0 if no matching files exist.

    Example:
        >>> paths = [Path("master_1.pdf"), Path("master_3.pdf"), Path("master_2.pdf")]
        >>> highest = get_highest_index(paths, "master")
        >>> print(highest)  # Output: 3
    """
    indices = []
    for p in paths:
        m = re.search(fr"{prefix}_(\d+)\.pdf$", p.name)
        if m:
            indices.append(int(m.group(1)))
    return max(indices) if indices else 0 

