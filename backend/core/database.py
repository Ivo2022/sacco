# backend/core/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import logging
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)


def is_sqlite(url: str) -> bool:
    """Check if database URL is SQLite"""
    return url.startswith("sqlite:///")


def is_postgresql(url: str) -> bool:
    """Check if database URL is PostgreSQL"""
    return url.startswith("postgresql://") or url.startswith("postgres://")


def ensure_sqlite_directory(db_url: str) -> None:
    """Ensure the directory for SQLite database exists"""
    if is_sqlite(db_url):
        db_path = db_url.replace("sqlite:///", "")
        db_dir = Path(db_path).parent
        if db_dir:
            db_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured SQLite directory exists: {db_dir}")


def configure_sqlite_for_production(engine):
    """Configure SQLite for production-like performance"""
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA cache_size=-20000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()
            logger.debug("SQLite pragmas configured")
        except Exception as e:
            logger.warning(f"Failed to configure SQLite pragmas: {e}")


def create_db_engine():
    """Create database engine with appropriate settings"""
    database_url = settings.DATABASE_URL
    
    # Ensure database directory exists for SQLite
    ensure_sqlite_directory(database_url)
    
    if is_sqlite(database_url):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        configure_sqlite_for_production(engine)
        logger.info(f"SQLite engine created: {database_url}")
        
    elif is_postgresql(database_url):
        engine = create_engine(
            database_url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=settings.DEBUG
        )
        logger.info(f"PostgreSQL engine created with pool size {settings.DB_POOL_SIZE}")
        
    else:
        engine = create_engine(
            database_url,
            echo=settings.DEBUG
        )
        logger.info(f"Generic database engine created")
    
    return engine


# Create engine
engine = create_db_engine()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def init_db() -> None:
    """
    Initialize database - create all tables.
    WARNING: In production, use Alembic migrations instead.
    """
    if settings.is_production:
        logger.warning("Running init_db() in production - this should only be used for initial setup!")
        logger.warning("Consider using Alembic migrations for schema changes")
    
    try:
        # Import models inside function to avoid circular imports
        from ..models import (
            User, Sacco, Saving, Loan, LoanPayment,
            PendingDeposit, ExternalLoan, ExternalLoanPayment,
            Log, SystemSetting, ReferralCommission
        )
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Verify tables were created
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Database initialized successfully with tables: {tables}")
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """Get a database session (for use outside dependencies)"""
    return SessionLocal()