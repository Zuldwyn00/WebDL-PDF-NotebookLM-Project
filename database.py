#TODO
#Add check to make sure page_number is not in already used range for the add_pdf() function


from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List, Union
from utils import ResourceNotFoundError, load_config, setup_logger
from sqlalchemy.orm import Session
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker

# ─── LOGGER & CONFIG ────────────────────────────────────────────────────────────────
config = load_config()
logger = setup_logger(__name__, config, level="DEBUG")

# ─── DATABASE CONFIGURATION ────────────────────────────────────────────────────────────────
# Create engine and session factory at module level
engine = None
SessionFactory = None

class Base(DeclarativeBase):
    pass

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    master_PDF: Mapped[List["MasterPDF"]] = relationship(back_populates="category")


class MasterPDF(Base):
    __tablename__ = "master_PDF"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    name: Mapped[str] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    category: Mapped["Category"] = relationship(back_populates="master_PDF")
    PDF: Mapped[List["PDF"]] = relationship(back_populates="master_pdf")


class PDF(Base):
    __tablename__ = "PDF"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("master_PDF.id"), nullable=False)

    name: Mapped[str] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column()
    master_page_number: Mapped[int] = mapped_column()
    file_type: Mapped[Optional[str]] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    master_pdf: Mapped["MasterPDF"] = relationship(back_populates="PDF")


def init_db(db_type: str = "sqlite", db_path: str = "pdf_scraper.db"):
    """
    Initialize the database engine and session factory for the application.
    
    This function should be called once at application startup to set up the database
    connection and create the session factory. It creates a global engine and session
    factory that will be used throughout the application.
    
    Args:
        db_type (str): Type of database to use. Currently only supports "sqlite".
                       Defaults to "sqlite".
        db_path (str): Path to the SQLite database file. Defaults to "pdf_scraper.db".
    
    Returns:
        Engine: The created SQLAlchemy engine instance.
    
    Raises:
        ValueError: If db_type is not "sqlite", as other database types are not supported.
    
    Note:
        This function modifies global variables 'engine' and 'SessionFactory'.
        It should only be called once at application startup.
    """
    global engine, SessionFactory
    
    if db_type != "sqlite":
        raise ValueError(f"Unsupported database type: {db_type}. Only 'sqlite' is currently supported.")

    engine = create_engine(f"{db_type}:///{db_path}", echo=True)
    Base.metadata.create_all(engine)
    #add global session as default, get_db_session() can be used with an optional engine param to make a new session with that engine
    SessionFactory = sessionmaker(bind=engine)
    
    return engine

# ─── SESSION MANAGEMENT ────────────────────────────────────────────────────────────────
@contextmanager
def get_db_session(engine=None):
    """
    Context manager for database sessions.
    Uses the global session factory or a provided engine.
    
    Args:
        engine: Optional SQLAlchemy engine. If provided, creates a new session with this engine.
               If None, uses the global session factory.
    """
    if engine:
        session = sessionmaker(bind=engine)()
    else:
        session = SessionFactory()
        
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def add_db_category(name:str):
    """
    Add a new category to the database if it doesn't already exist.
    
    Args:
        name (str): The name of the category to add
        
    Returns:
        bool: True if category was added, False if it already existed
    """
    if not name or not name.strip():
            raise ValueError("Category name cannot be empty.")
    
    with get_db_session() as session:
        category = session.query(Category).filter(Category.name == name).first()
        if category:
            logger.info("Category already exists, cannot add.")
            return False
        
        new_category = Category(name=name)
        session.add(new_category)
        return True
    
# ─── UTILITY FUNCTIONS ────────────────────────────────────────────────────────────────
def _validate_lookup_value(value: str | int) -> None:
    """
    Validate that a lookup value is not empty or undefined.

    Args:
        value (str | int): The value to validate.

    Raises:
        ValueError: If the value is empty or undefined.
    """
    if not value or (isinstance(value, str) and not value.strip()):
        raise ValueError("Value cannot be empty or undefined.")
    
def _validate_page_range(master_pdf_id: int, page_number: int) -> bool:
    """
    Validates if a given page number is the next sequential page for a master PDF.

    This function ensures that new pages are added sequentially by checking if the provided
    page number is exactly one more than the highest existing page number. This prevents
    gaps in page numbering and maintains a continuous sequence. Returns False if the master
    PDF doesn't exist.

    Args:
        master_pdf_id (int): The ID of the master PDF to validate against.
        page_number (int): The page number to validate.

    Returns:
        bool: True if the page number is the next sequential page (highest_page + 1),
              False if the master PDF doesn't exist or if the page number is not sequential.
    """
    # Get the master PDF and its associated PDFs through the relationship
    master_pdf = get_db_masterpdf(master_pdf_id)
    if not master_pdf:
        return False
    
    # Get the highest page number from the associated PDFs
    highest_page = max((pdf.master_page_number for pdf in master_pdf.PDF), default=0)
    
    return page_number == highest_page + 1

def _assign_page_number(master_pdf_id: int, target_page: Optional[int] = None) -> int:
    master_pdf = get_db_masterpdf(master_pdf_id)

    pdfs = sorted(master_pdf.PDF, key=lambda x: x.master_page_number, reverse=True)
    


# ─── DATABASE OPERATIONS ────────────────────────────────────────────────────────────────
def get_db_category(value: str | int) -> Category:
    """
    Get a category from the database by name.
    
    Args:
        value (str | int): The value can either be the name of the category, or the ID of the category
        
    Returns:
        Category: The category object if found
        
    Raises:
        ResourceNotFoundError: If the category does not exist
    """
    _validate_lookup_value(value)

    with get_db_session() as session:
        logger.debug("Attempting to retrieve category:")

        column = Category.id if isinstance(value, int) else Category.name
        category = session.query(Category).filter(column == value).first()
        
        if category:
            return category
        raise ResourceNotFoundError(f"Category '{value}' not found.")
    

def add_db_masterpdf(name:str, category_name:str, file_path:str) -> bool:
    with get_db_session() as session:
        #find the category to add to
        category = session.query(Category).filter(Category.name == category_name).first()

        if not category:
            logger.error(f"Category '{category_name}' not found, cannot add.")
            return False

        if session.query(MasterPDF).filter(MasterPDF.name == name).first():
            logger.info(f"Master PDF '{name}' already exists, cannot add.")
            return False

        new_master_pdf = MasterPDF(
            name=name,
            category_id=category.id,
            file_path=file_path
        )
        session.add(new_master_pdf)
        return True

def get_db_masterpdf(value: str | int) -> MasterPDF:
    """
    Get a master PDF from the database by name or ID.

    Args:
        value (str | int): The value can either be the name of the master PDF, or the ID of the master PDF.

    Returns:
        MasterPDF: The master PDF object if found.

    Raises:
        ValueError: If the value is empty or undefined.
        ResourceNotFoundError: If the master PDF does not exist.
    """
    _validate_lookup_value(value)
    
    with get_db_session() as session:
        logger.debug("Attempting to retrieve MasterPDF:")

        column = MasterPDF.id if isinstance(value, int) else MasterPDF.name
        master_pdf = session.query(MasterPDF).filter(column == value).first()

        if master_pdf:
            return master_pdf
        raise ResourceNotFoundError(f"MasterPDF '{value}' not found.")

def add_db_pdf(name: str, 
               master_pdf_value: str | int, 
               file_path: str, 
               master_page_number: Optional[int] = None,
               file_type: Optional[str] = None
               ) -> bool:
    """
    Add a new PDF to the database, associated with a master PDF.
    
    Args:
        name (str): The name of the PDF
        master_pdf_value (str | int): The name or ID of the master PDF this PDF belongs to
        file_path (str): The file path of the PDF
        master_page_number (int): The page number in the master PDF
        file_type (Optional[str]): The type of file (optional)
        
    Returns:
        bool: True if PDF was added successfully, False if master PDF doesn't exist
    """
    with get_db_session() as session:

        column = MasterPDF.id if isinstance(master_pdf_value, int) else MasterPDF.name
        master_pdf = session.query(MasterPDF).filter(column == master_pdf_value).first()
        
        if not master_pdf:
            logger.error(f"Master PDF '{master_pdf}' does not exist, cannot add PDF.")
            return False
            
        new_pdf = PDF(
            name=name,
            master_id=master_pdf.id,
            file_path=file_path,
            master_page_number=master_page_number,
            file_type=file_type
        )
        session.add(new_pdf)
        return True
    
def get_db_pdf(value: str | int) -> PDF:
    """
    Get a PDF from the database by name or ID.

    Args:
        value (str | int): The value can either be the name of the PDF, or the ID of the PDF.

    Returns:
        PDF: The PDF object if found.

    Raises:
        ValueError: If the value is empty or undefined.
        ResourceNotFoundError: If the PDF does not exist.
    """
    _validate_lookup_value(value)

    with get_db_session() as session:
        logger.debug("Attempting to retrieve PDF:")

        column = PDF.id if isinstance(value, int) else PDF.name
        pdf = session.query(PDF).filter(column == value).first()

        if pdf:
            return pdf
        raise ResourceNotFoundError(f"PDF '{value}' not found.")
