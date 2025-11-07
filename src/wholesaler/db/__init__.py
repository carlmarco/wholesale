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
    with_retry,
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
from src.wholesaler.db.repository import (
    BaseRepository,
    PropertyRepository,
    TaxSaleRepository,
    ForeclosureRepository,
    PropertyRecordRepository,
    LeadScoreRepository,
    DataIngestionRunRepository,
)
from src.wholesaler.db import utils as db_utils

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
    "with_retry",
    # Models
    "Property",
    "TaxSale",
    "Foreclosure",
    "PropertyRecord",
    "CodeViolation",
    "LeadScore",
    "LeadScoreHistory",
    "DataIngestionRun",
    # Repositories
    "BaseRepository",
    "PropertyRepository",
    "TaxSaleRepository",
    "ForeclosureRepository",
    "PropertyRecordRepository",
    "LeadScoreRepository",
    "DataIngestionRunRepository",
    # Utilities
    "db_utils",
]
