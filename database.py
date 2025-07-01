#TODO
#1) Finish assign_page_number()
#Add method to reorganize PDF if user chooses to choose a target_page for the _assign_page_number() function
#Test the method to make sure it works

#2) Finish _validate_lookup_value()
# Make the method also look if a value already exists so we can handle that with one method instead of checking if a value
#exists already in every method.

#3) Make one method that handles adding categories, pdfs, and masters

#4) Use a @validate_value decorator to make all commands go through it to validate their values are acceptable instead

from sqlalchemy import create_engine, ForeignKey, JSON
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker
from functools import wraps
from urllib.parse import urlparse, urlunparse

#Local Imports
import schemas
from utils import (ValidationError, 
                   load_config, 
                   setup_logger,
                   ResourceNotFoundError,
                   ValidationError,
)

# ─── LOGGER & CONFIG ────────────────────────────────────────────────────────────────
config = load_config()
logger = setup_logger(__name__, config, level="DEBUG")

# ─── DATABASE CONFIGURATION ────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    master_PDF: Mapped[List["MasterPDF"]] = relationship(back_populates="category")

class MasterPDF(Base):
    __tablename__ = "master_PDF"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    category: Mapped["Category"] = relationship(back_populates="master_PDF")
    PDF: Mapped[List["PDF"]] = relationship(back_populates="master_pdf")

class PDF(Base):
    __tablename__ = "PDF"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("master_PDF.id"), nullable=False)

    url: Mapped[str] = mapped_column(nullable=False, unique=True)
    file_path: Mapped[Optional[str]] = mapped_column()
    master_page_number: Mapped[Optional[int]] = mapped_column()
    status: Mapped[str] = mapped_column()
    video_links: Mapped[Optional[List[str]]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    master_pdf: Mapped["MasterPDF"] = relationship(back_populates="PDF")

class UnprocessedPDF(Base):
    __tablename__ = "unprocessed_pdf"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    
    url: Mapped[str] = mapped_column(nullable=False, unique=True)
    file_path: Mapped[Optional[str]] = mapped_column()
    video_links: Mapped[Optional[List[str]]] = mapped_column(JSON)


    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    category: Mapped["Category"] = relationship("Category")
    


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
    #add global session as default, get_session() can be used with an optional engine param to make a new session with that engine
    SessionFactory = sessionmaker(bind=engine)
    
    return engine

# ─── SESSION MANAGEMENT ────────────────────────────────────────────────────────────────
@contextmanager
def get_session(engine=None):
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
    `get_session` context manager and injects it into the keyword
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
            with get_session() as new_session:
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
    
    def _validate_status(status):
        if status not in {"PEND", "FAIL", "SUCC"}:
            raise ValidationError("Status must be PEND, FAIL or SUCC")

def normalize_url(raw_url: str) -> str:
    """Normalizes a URL by standardizing format and removing unnecessary components.

    Args:
        raw_url (str): The URL to normalize.

    Returns:
        str: Normalized URL with:
            - Scheme in lowercase
            - Domain in lowercase
            - Path is preserved as is
            - No trailing slash
            - No query parameters or fragments
    """
    # components of url, urlparse seperates into 6 fields
    parts = urlparse(raw_url, scheme="http")
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = (parts.path or "")  # Safely handle None case
    params = ""
    query = ""
    fragment = ""
    if (
        path.endswith("/") and len(path) > 1
    ):  # remove ending (/), prevents duplicates if web developer is inconsistent with adding a (/) at the end of a link or not if it's the same link
        path = path[:-1]

    # scheme://netloc/path;params?query#fragment
    normalized = urlunparse((scheme, netloc, path, params, query, fragment))
    return normalized

# ─── DATABASE OPERATIONS ───────────────────────────────────────────────────────────────
    

class DatabaseService:
    def __init__(self, session: Session):
        self.session = session

    def add_resource(self, object_data: schemas.CategoryCreate | schemas.MasterPDFCreate | schemas.PDFCreate | schemas.UnprocessedPDFCreate):
        """Adds a new Category, MasterPDF, PDF, or UnprocessedPDF resource to the database."""
        try:
            if isinstance(object_data, schemas.CategoryCreate):
                self.add_category(object_data)
            elif isinstance(object_data, schemas.MasterPDFCreate):
                self.add_masterpdf(object_data)
            elif isinstance(object_data, schemas.PDFCreate):
                self.add_pdf(object_data)
            elif isinstance(object_data, schemas.UnprocessedPDFCreate):
                self.add_unprocessed_pdf(object_data)

        except Exception as e:
            logger.error("Problem adding %s to database: %s", type(object_data).__name__, e)

    def update_resource(self, object_data: schemas.CategoryUpdate | schemas.MasterPDFUpdate | schemas.PDFUpdate | schemas.UnprocessedPDFUpdate):
        """Updates an existing Category, MasterPDF, PDF, or UnprocessedPDF resource in the database."""
        try:
            if isinstance(object_data, schemas.CategoryUpdate):
                self.update_category(object_data)
            elif isinstance(object_data, schemas.MasterPDFUpdate):
                self.update_masterpdf(object_data)
            elif isinstance(object_data, schemas.PDFUpdate):
                self.update_pdf(object_data)
            elif isinstance(object_data, schemas.UnprocessedPDFUpdate):
                self.update_unprocessed_pdf(object_data)
        except Exception as e:
            logger.error("Problem updating %s in database: %s", type(object_data).__name__, e)

    def update_category(self, category_data: schemas.CategoryUpdate) -> bool:
        """Updates an existing category."""
        category_orm = self.session.query(Category).filter(Category.id == category_data.id).first()
        if not category_orm:
            raise ResourceNotFoundError(f"Category with id {category_data.id} not found.")

        if category_data.name is not None:
            category_orm.name = category_data.name
        
        return True

    def update_masterpdf(self, masterpdf_data: schemas.MasterPDFUpdate) -> bool:
        """Updates an existing MasterPDF."""
        masterpdf_orm = self.session.query(MasterPDF).filter(MasterPDF.id == masterpdf_data.id).first()
        if not masterpdf_orm:
            raise ResourceNotFoundError(f"MasterPDF with id {masterpdf_data.id} not found.")

        update_data = masterpdf_data.model_dump(exclude_unset=True)
        
        if 'category_value' in update_data:
            category = self.get_category(update_data['category_value'])
            masterpdf_orm.category_id = category.id
        
        for key, value in update_data.items():
            if hasattr(masterpdf_orm, key) and key not in ['id', 'category_value']:
                setattr(masterpdf_orm, key, value)
        
        return True

    def update_pdf(self, pdf_data: schemas.PDFUpdate) -> bool:
        """Updates an existing PDF."""
        pdf_orm = self.session.query(PDF).filter(PDF.id == pdf_data.id).first()
        if not pdf_orm:
            raise ResourceNotFoundError(f"PDF with id {pdf_data.id} not found.")

        update_data = pdf_data.model_dump(exclude_unset=True)

        if 'master_pdf_value' in update_data:
            master_pdf = self.get_masterpdf(update_data['master_pdf_value'])
            pdf_orm.master_id = master_pdf.id
        
        if 'url' in update_data:
            update_data['url'] = normalize_url(update_data['url'])

        for key, value in update_data.items():
            if hasattr(pdf_orm, key) and key not in ['id', 'master_pdf_value']:
                setattr(pdf_orm, key, value)

        return True

    def update_unprocessed_pdf(self, unprocessed_pdf_data: schemas.UnprocessedPDFUpdate) -> bool:
        """Updates an existing unprocessed PDF."""
        unprocessed_pdf_orm = self.session.query(UnprocessedPDF).filter(UnprocessedPDF.id == unprocessed_pdf_data.id).first()
        if not unprocessed_pdf_orm:
            raise ResourceNotFoundError(f"UnprocessedPDF with id {unprocessed_pdf_data.id} not found.")

        update_data = unprocessed_pdf_data.model_dump(exclude_unset=True)

        if 'category_value' in update_data:
            category = self.get_category(update_data['category_value'])
            unprocessed_pdf_orm.category_id = category.id

        if 'url' in update_data:
            update_data['url'] = normalize_url(update_data['url'])

        for key, value in update_data.items():
            if hasattr(unprocessed_pdf_orm, key) and key not in ['id', 'category_value']:
                setattr(unprocessed_pdf_orm, key, value)

        return True

    def _assign_page_number(self, master_pdf_id: str | int, target_page: Optional[int] = None) -> int:
        """
        Assigns a page number for a new PDF in relation to existing PDFs in the master document.
        
        This function handles page number assignment with special consideration for PDFs that span
        multiple pages. When inserting at a specific target page, it ensures no content is overwritten
        by shifting existing PDFs forward.
        
        Args:
            master_pdf_id (int): Name or ID of the master PDF document
            target_page (Optional[int]): Desired page number for insertion. If None, appends to end.
            
        Returns:
            int: The assigned page number
            
        Note:
            When inserting between existing PDFs, the target page is adjusted to avoid splitting
            existing PDFs. For example, if inserting at page 13 between PDFs spanning pages 10-14
            and 15-20, the insertion point is adjusted to page 15 to maintain PDF integrity.
        """
        _validate_lookup_value(master_pdf_id)

        master_pdf = self.get_masterpdf(master_pdf_id)
        existing_pdfs = self.session.query(PDF).filter(PDF.master_id == master_pdf.id).order_by(PDF.master_page_number).all()
        if not existing_pdfs:
            return 0

        highest_page = existing_pdfs[-1].master_page_number

        if target_page is None or target_page > highest_page:
            if target_page and target_page > highest_page:
                logger.info(f"Target page '{target_page}' creates a gap. "
                f"Assinging as next available page at: '{highest_page + 1}'")
            return highest_page + 1

        # Check if target_page requires shifting existing PDFs
        pdfs_to_shift = [pdf for pdf in existing_pdfs if pdf.master_page_number >= target_page]
        if not pdfs_to_shift:
            
            return highest_page + 1
        else:
            # Important: We set target_page to the start of the next PDF to avoid splitting existing PDFs
            # For example, if inserting at page 13 between PDFs at pages 10-14 and 15-20,
            # we insert at page 15 to maintain PDF integrity
            new_target_page = pdfs_to_shift[0].master_page_number
            logger.info(f"Page number '{target_page}' requires shifting {len(pdfs_to_shift)} pdfs. New target page is {new_target_page}")

            for pdf in reversed(pdfs_to_shift):
                pdf.master_page_number += 1
            
            return new_target_page

    def add_category(self, category_data: schemas.CategoryCreate) -> bool:
        """Adds a new category to the database if it does not already exist.

        Args:
            category_data (schemas.CategoryCreate): A Pydantic model containing the data 
                for the new category.
                - name (str): The name of the category.

        Returns:
            bool: True if the category was successfully added, False if it already exists.
        """
        category = (
            self.session.query(Category)
            .filter(Category.name == category_data.name)
            .first()
        )

        if category:
            logger.info("Category already exists, cannot add.")
            return False
        
        new_category = Category(name=category_data.name)
        self.session.add(new_category)

        return True

    def get_category(self, value: str | int) -> schemas.CategoryResponse:
        """Retrieves a single category from the database by its ID or name.

        Args:
            value (str | int): The ID (integer) or name (string) of the category to retrieve.

        Raises:
            ResourceNotFoundError: If no category is found with the specified ID or name.

        Returns:
            schemas.CategoryResponse: A Pydantic model representing the retrieved category.
        """
        _validate_lookup_value(value)
        logger.debug("Attempting to retrieve category:")

        column = Category.id if isinstance(value, int) else Category.name
        category_orm = self.session.query(Category).filter(column == value).first()
        
        if category_orm:
            return schemas.CategoryResponse.model_validate(category_orm)
        else:
            raise ResourceNotFoundError(f"Category '{value}' not found.")

    def add_masterpdf(self, masterpdf_data: schemas.MasterPDFCreate) -> bool:
        """Adds a new master PDF to the database.

        Ensures the associated category exists and that the master PDF name is unique.

        Args:
            masterpdf_data (schemas.MasterPDFCreate): A Pydantic model with the master PDF data.
                - name (str): The name of the master PDF.
                - category_value (str | int): The name or ID of the category it belongs to.
                - file_path (str): The file path for the master PDF.

        Returns:
            bool: True if the master PDF was added, False if it already exists.

        Raises:
            ResourceNotFoundError: If the specified category does not exist.
        """
        try:
            category = self.get_category(masterpdf_data.category_value)
        except ResourceNotFoundError: 
            logger.error(f"Category '{masterpdf_data.category_value}' not found, cannot add.")
            return False


        try:
            existing_master = self.get_masterpdf(masterpdf_data.name)
            if existing_master:
                logger.info(f"Master PDF '{masterpdf_data.name}' already exists, cannot add.")
                return False
        except ResourceNotFoundError:
            #this is expected behavior, so pass and proceed
            pass
        
        new_master_pdf = MasterPDF(
            name=masterpdf_data.name,
            file_path=str(masterpdf_data.file_path), #convert filepath into a string
            category_id=category.id,
        )
        self.session.add(new_master_pdf)

        return True

    def get_masterpdf(self, value: str | int) -> schemas.MasterPDFResponse:
        """Retrieries a single master PDF from the database by its ID or name.

        Args:
            value (str | int): The ID (integer) or name (string) of the master PDF to retrieve.

        Raises:
            ResourceNotFoundError: If no master PDF is found with the specified ID or name.

        Returns:
            schemas.MasterPDFResponse: A Pydantic model representing the retrieved master PDF.
        """
        _validate_lookup_value(value)
        
        logger.debug("Attempting to retrieve MasterPDF:")

        column = MasterPDF.id if isinstance(value, int) else MasterPDF.name
        masterpdf_orm = self.session.query(MasterPDF).filter(column == value).first()

        if masterpdf_orm:
            return schemas.MasterPDFResponse.model_validate(masterpdf_orm)
        else:
            raise ResourceNotFoundError(f"MasterPDF '{value}' not found.")

    def add_pdf(self, pdf_data: schemas.PDFCreate) -> bool:
        """Adds a new PDF to the database, associated with a master PDF.

        This method validates the master PDF, assigns a page number, normalizes the
        PDF's URL, and creates a new PDF record in the database. If the specified
        master PDF does not exist, the operation will fail.

        Args:
            pdf_data (schemas.PDFCreate): A Pydantic model containing the PDF data:
                - master_pdf_value (str | int): Name or ID of the parent master PDF.
                - url (HttpUrl): The source URL of the PDF.
                - file_path (FilePath): The local file path where the PDF is stored.
                - status (Literal["PEND", "FAIL", "SUCC"]): The processing status.
                - master_page_number (Optional[int]): The desired starting page number
                  within the master PDF. If None, it's appended to the end.
                - file_type (Literal["pdf", "mp4"]): The type of the file.

        Returns:
            bool: True if the PDF was added successfully, False if the master PDF
                  was not found.
        """
        
        master_pdf = self.get_masterpdf(pdf_data.master_pdf_value)
        if not master_pdf:
            logger.error(f"Master PDF '{pdf_data.master_pdf_value}' does not exist, cannot add PDF.")
            return False
            
        page_number = self._assign_page_number(master_pdf_id=master_pdf.id, target_page=pdf_data.master_page_number)

        new_pdf = PDF(
            url=normalize_url(str(pdf_data.url)),
            master_id=master_pdf.id,
            file_path=str(pdf_data.file_path) if pdf_data.file_path is not None else None,
            master_page_number=page_number,
            file_type=pdf_data.file_type,
            status=pdf_data.status,
            video_links=[str(url) for url in pdf_data.video_links] if pdf_data.video_links else None
        )
        self.session.add(new_pdf)
        return True

    def get_pdf(self, value: str | int) -> schemas.PDFResponse:
        """Retrieves a single PDF from the database by its ID or name.

        Args:
            value (str | int): The ID (integer) or name (string) of the PDF to retrieve.

        Raises:
            ResourceNotFoundError: If no PDF is found with the specified ID or name.

        Returns:
            schemas.PDFResponse: A Pydantic model representing the retrieved PDF.
        """
        _validate_lookup_value(value)
        logger.debug("Attempting to retrieve PDF:")
        
        column = PDF.id if isinstance(value, int) else PDF.url
        if isinstance(value, str):
            value = normalize_url(value)
            
        pdf_orm = self.session.query(PDF).filter(column == value).first()

        if pdf_orm:
            return schemas.PDFResponse.model_validate(pdf_orm)
        else:
            raise ResourceNotFoundError(f"PDF '{value}' not found.")

    def add_unprocessed_pdf(self, data: schemas.UnprocessedPDFCreate) -> bool:
        """Adds a new unprocessed PDF to temporary storage."""
        category = self.get_category(data.category_value)
        normalized_url = normalize_url(data.url)
        
        existing = self.session.query(UnprocessedPDF).filter(UnprocessedPDF.url == normalized_url).first()
        if existing:
            return False

        new_unprocessed = UnprocessedPDF(url=normalized_url, category_id=category.id)
        self.session.add(new_unprocessed)
        return True
        
    def update_pdf_master(self, pdf_to_update: str | int, master_name: str):
        """Updates the master_pdf field for a specified PDF.

        Args:
            pdf_to_update (str | int): The ID (integer) or URL (string) of the PDF to update.
            master_name (str): The name of the master PDF to associate with this PDF.

        Returns:
            bool: True if the update was successful.

        Raises:
            ResourceNotFoundError: If no PDF is found with the specified ID or URL.
            ResourceNotFoundError: If no master PDF is found with the specified name.
        """
        logger.debug("Attempting to update PDF master association:")
        
        # Find the PDF to update using existing get_pdf method
        pdf_response = self.get_pdf(pdf_to_update)
        
        # Find the master PDF by name
        master_pdf = self.session.query(MasterPDF).filter(MasterPDF.name == master_name).first()
        if not master_pdf:
            raise ResourceNotFoundError(f"Master PDF '{master_name}' not found.")
        
        # Get the actual PDF ORM object to update
        pdf_orm = self.session.query(PDF).filter(PDF.id == pdf_response.id).first()
        
        # Update the master_id
        pdf_orm.master_id = master_pdf.id
        return True