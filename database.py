#TODO
#1) Finish assign_page_number()
#Add method to reorganize PDF if user chooses to choose a target_page for the _assign_page_number() function
#Test the method to make sure it works

#2) Finish _validate_lookup_value()
# Make the method also look if a value already exists so we can handle that with one method instead of checking if a value
#exists already in every method.

from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List
from utils import ResourceNotFoundError, load_config, setup_logger
from sqlalchemy.orm import Session
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker
from functools import wraps

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

def with_session(func):
    """
    A decorator to provide a SQLAlchemy session to database functions.

    This decorator inspects the keyword arguments of the function it wraps.
    If a `session` keyword argument is already provided and is not None, it
    uses that session. Otherwise, it creates a new session using the
    `get_db_session` context manager and injects it into the keyword
    arguments as `session`.

    This pattern ensures that database functions can either participate in an
    existing transaction or manage their own, without repetitive boilerplate.
    
    The wrapped function must accept `session` as a keyword argument.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'session' in kwargs and kwargs.get('session') is not None:
            return func(*args, **kwargs)
        else:
            with get_db_session() as new_session:
                kwargs['session'] = new_session
                return func(*args, **kwargs)
    
    return wrapper

    
# ─── UTILITY FUNCTIONS ────────────────────────────────────────────────────────────────
def _validate_lookup_value(value) -> None:
    """
    Validate that a lookup value is not empty or undefined.

    Args:
        value: The value to validate.

    Raises:
        ValueError: If the value is empty or undefined.
    """
    if not value or (isinstance(value, str) and not value.strip()):
        raise ValueError("Value cannot be empty or undefined.")
    
@with_session
def _assign_page_number(master_pdf_id: int, session: Session, target_page: Optional[int] = None) -> int:
    """
    Assigns a page number for a new PDF in relation to existing PDFs in the master document.
    
    This function handles page number assignment with special consideration for PDFs that span
    multiple pages. When inserting at a specific target page, it ensures no content is overwritten
    by shifting existing PDFs forward.
    
    Args:
        master_pdf_id (int): ID of the master PDF document
        session (Session): Database session
        target_page (Optional[int]): Desired page number for insertion. If None, appends to end.
        
    Returns:
        int: The assigned page number
        
    Note:
        When inserting between existing PDFs, the target page is adjusted to avoid splitting
        existing PDFs. For example, if inserting at page 13 between PDFs spanning pages 10-14
        and 15-20, the insertion point is adjusted to page 15 to maintain PDF integrity.
    """
    master_pdf = get_db_masterpdf(master_pdf_id, session=session)
    existing_pdfs = sorted(master_pdf.PDF, key=lambda x: x.master_page_number, reverse=True)
    existing_page_numbers = [p.master_page_number for p in existing_pdfs]
    
    highest_page = max(existing_page_numbers)

    if not existing_pdfs:
        return 0
    if target_page is None or target_page > highest_page:
        if target_page and target_page > highest_page:
            logger.info(f"Target page '{target_page}' creates a gap. "
            f"Assinging as next available page at: '{highest_page + 1}'")
        return highest_page + 1

    #check if target_page is within the already existing range of pages
    pdfs_to_shift = [pdf for pdf in existing_pdfs if pdf.master_page_number >= target_page]
    if pdfs_to_shift:
        # Important: We set target_page to the start of the next PDF to avoid splitting existing PDFs
        # For example, if inserting at page 13 between PDFs at pages 10-14 and 15-20,
        # we insert at page 15 to maintain PDF integrity
        target_page = pdfs_to_shift[0].master_page_number
        logger.info(f"Page number '{target_page}' requires shifting {len(pdfs_to_shift)} pdfs.")
        for pdf in pdfs_to_shift:
            pdf.master_page_number += 1
        
    return target_page

        #return page, and call insert_pages() for adding page


    

# ─── DATABASE OPERATIONS ────────────────────────────────────────────────────────────────

@with_session
def add_db_category(name:str, session: Session) -> bool:
    """
    Add a new category to the database if it doesn't already exist.
    
    Args:
        name (str): The name of the category to add.
        session (Session): An existing SQLAlchemy session. If not provided, a new session
                           is created by the `@with_session` decorator.
        
    Returns:
        bool: True if category was added, False if it already existed.
    """
    if not name or not name.strip():
            raise ValueError("Category name cannot be empty.")
    
    category = session.query(Category).filter(Category.name == name).first()
    if category:
        logger.info("Category already exists, cannot add.")
        return False
    new_category = Category(name=name)
    session.add(new_category)
    return True

@with_session
def get_db_category(value: str | int, session: Session) -> Category:
    """
    Get a category from the database by name.
    
    Args:
        value (str | int): The name or ID of the category.
        session (Session): An existing SQLAlchemy session. If not provided, a new session
                           is created by the `@with_session` decorator.
        
    Returns:
        Category: The category object if found.
        
    Raises:
        ResourceNotFoundError: If the category does not exist.
    """
    _validate_lookup_value(value)
    logger.debug("Attempting to retrieve category:")

    column = Category.id if isinstance(value, int) else Category.name
    category = session.query(Category).filter(column == value).first()
    
    if category:
        return category
    raise ResourceNotFoundError(f"Category '{value}' not found.")

    
@with_session
def add_db_masterpdf(name:str, category_name:str, file_path:str, session: Session) -> bool:
    """
    Adds a new master PDF to the database.

    Args:
        name (str): The name of the master PDF.
        category_name (str): The name of the category it belongs to.
        file_path (str): The file path for the master PDF.
        session (Session): An existing SQLAlchemy session. If not provided, a new session
                           is created by the `@with_session` decorator.

    Returns:
        bool: True if the master PDF was added, False otherwise.
    """
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

@with_session
def get_db_masterpdf(value: str | int, session: Session) -> MasterPDF:
    """
    Get a master PDF from the database by name or ID.

    Args:
        value (str | int): The name or ID of the master PDF.
        session (Session): An existing SQLAlchemy session. If not provided, a new session
                           is created by the `@with_session` decorator.

    Returns:
        MasterPDF: The master PDF object if found.

    Raises:
        ValueError: If the value is empty or undefined.
        ResourceNotFoundError: If the master PDF does not exist.
    """
    _validate_lookup_value(value)
    
    logger.debug("Attempting to retrieve MasterPDF:")

    column = MasterPDF.id if isinstance(value, int) else MasterPDF.name
    master_pdf = session.query(MasterPDF).filter(column == value).first()

    if master_pdf:
        return master_pdf
    raise ResourceNotFoundError(f"MasterPDF '{value}' not found.")

@with_session
def add_db_pdf(name: str, 
               master_pdf_value: str | int, 
               file_path: str, 
               session: Session,
               master_page_number: Optional[int] = None,
               file_type: Optional[str] = None,
                ) -> bool:
    """
    Add a new PDF to the database, associated with a master PDF.
    
    Args:
        name (str): The name of the PDF.
        master_pdf_value (str | int): The name or ID of the master PDF this PDF belongs to.
        file_path (str): The file path of the PDF.
        session (Session): An existing SQLAlchemy session. If not provided, a new session
                           is created by the `@with_session` decorator.
        master_page_number (Optional[int]): The page number in the master PDF.
        file_type (Optional[str]): The type of file (optional).
        
    Returns:
        bool: True if PDF was added successfully, False if master PDF doesn't exist.
    """
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

@with_session
def get_db_pdf(value: str | int, session: Session) -> PDF:
    """
    Get a PDF from the database by name or ID.

    Args:
        value (str | int): The name or ID of the PDF.
        session (Session): An existing SQLAlchemy session. If not provided, a new session
                           is created by the `@with_session` decorator.

    Returns:
        PDF: The PDF object if found.

    Raises:
        ValueError: If the value is empty or undefined.
        ResourceNotFoundError: If the PDF does not exist.
    """
    _validate_lookup_value(value)

    logger.debug("Attempting to retrieve PDF:")

    column = PDF.id if isinstance(value, int) else PDF.name
    pdf = session.query(PDF).filter(column == value).first()

    if pdf:
        return pdf
    raise ResourceNotFoundError(f"PDF '{value}' not found.")
