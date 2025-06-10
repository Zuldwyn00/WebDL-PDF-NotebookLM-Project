#TODO
#Add check to make sure page_number is not in already used range for the add_pdf() function


from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List
from utils import ResourceNotFoundError, load_config, setup_logger
from sqlalchemy.orm import Session
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker
import random

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

    master_pdfs: Mapped[List["MasterPDF"]] = relationship(back_populates="category")


class MasterPDF(Base):
    __tablename__ = "master_pdfs"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    category: Mapped["Category"] = relationship(back_populates="master_pdfs")
    pdfs: Mapped[List["PDFs"]] = relationship(back_populates="master_pdf")


class PDFs(Base):
    __tablename__ = "pdfs"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("master_pdfs.id"), nullable=False)
    name: Mapped[Optional[str]] = mapped_column()
    file_path: Mapped[str] = mapped_column()
    master_page_number: Mapped[int] = mapped_column(nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    master_pdf: Mapped["MasterPDF"] = relationship(back_populates="pdfs")


def init_db(db_path: str = "pdf_scraper.db", db_type: str = "sqlite" , givenengine=None):
    """
    Initialize the database engine and session factory.
    Should be called once at application startup.
    """
    if givenengine is None:
        global engine, SessionFactory
    else:
        global SessionFactory
        engine = givenengine

    
    if db_type != "sqlite":
        raise ValueError(f"Unsupported database type: {db_type}. Only 'sqlite' is currently supported.")

    # Create engine at module level
    engine = create_engine(f"{db_type}:///{db_path}", echo=True)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    
    return engine

# ─── SESSION MANAGEMENT ────────────────────────────────────────────────────────────────
@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    Uses the global session factory.
    """
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
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
    with get_db_session() as session:
        category = session.query(Category).filter(Category.name == name).first()
        if category:
            logger.info("Category already exists, cannot add.")
            return False
        
        new_category = Category(name=name)
        session.add(new_category)
        return True
    
def get_db_category(name: str) -> Category:
    """
    Get a category from the database by name.
    
    Args:
        name (str): The name of the category to retrieve
        
    Returns:
        Category: The category object if found
        
    Raises:
        ResourceNotFoundError: If the category does not exist
    """
    if not name or not name.strip():
        raise ValueError("Category name cannot be empty.")

    with get_db_session() as session:
        logger.debug("Attempting to retrieve category:")
        category = session.query(Category).filter(Category.name == name).first()
        if category:
            return category
        
        raise ResourceNotFoundError(f"Category '{name}' not found.")
    
def add_db_masterpdf(name:str, category_name:str, file_path:str):
    with get_db_session() as session:
        category = session.query(Category).filter(Category.name == category_name).first()

        if not category:
            logger.error(f"Category '{category_name}' does not exist, cannot add.")
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

def add_db_pdf(name: str, master_pdf_name: str, file_path: str, master_page_number: int, file_type: Optional[str] = None):
    """
    Add a new PDF to the database, associated with a master PDF.
    
    Args:
        name (str): The name of the PDF
        master_pdf_name (str): The name of the master PDF this PDF belongs to
        file_path (str): The file path of the PDF
        master_page_number (int): The page number in the master PDF
        file_type (Optional[str]): The type of file (optional)
        
    Returns:
        bool: True if PDF was added successfully, False if master PDF doesn't exist
    """
    with get_db_session() as session:
        master_pdf = session.query(MasterPDF).filter(MasterPDF.name == master_pdf_name).first()
        
        if not master_pdf:
            logger.error(f"Master PDF '{master_pdf_name}' does not exist, cannot add PDF.")
            return False
            
        new_pdf = PDFs(
            name=name,
            master_id=master_pdf.id,
            file_path=file_path,
            master_page_number=master_page_number,
            file_type=file_type
        )
        session.add(new_pdf)
        return True