"""
FastAPI Dependencies

Provides dependency injection for database sessions and settings.
"""
from typing import Generator
from sqlalchemy.orm import Session

from src.wholesaler.db.session import SessionLocal
from src.wholesaler.config import settings


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency.

    Yields:
        SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_settings():
    """
    Settings dependency.

    Returns:
        Application settings
    """
    return settings
