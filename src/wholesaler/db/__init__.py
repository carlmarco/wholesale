"""
Database Package

Database models, connection management, and data persistence layer.
"""
from src.wholesaler.db.base import Base
from src.wholesaler.db.session import (
    engine,
    SessionLocal,
    get_db_session,
    get_db,
    health_check,
    close_connections,
    create_all_tables,
    drop_all_tables,
)
from src.wholesaler.db.models import (
    Property,
    TaxSale,
    Foreclosure,
    PropertyRecord,
    CodeViolation,
    LeadScore,
    LeadScoreHistory,
    DataIngestionRun,
)

__all__ = [
    # Base
    "Base",
    # Session management
    "engine",
    "SessionLocal",
    "get_db_session",
    "get_db",
    "health_check",
    "close_connections",
    "create_all_tables",
    "drop_all_tables",
    # Models
    "Property",
    "TaxSale",
    "Foreclosure",
    "PropertyRecord",
    "CodeViolation",
    "LeadScore",
    "LeadScoreHistory",
    "DataIngestionRun",
]
