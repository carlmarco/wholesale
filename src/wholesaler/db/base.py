"""
SQLAlchemy Base and Mixins

Provides declarative base and reusable mixins for database models.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr
from sqlalchemy import event
from sqlalchemy.types import String, Text
from geoalchemy2 import Geography
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """
    Base class for all database models.

    Provides common functionality and type hints for SQLAlchemy models.
    """

    # Type annotation for primary keys
    id: Any


class TimestampMixin:
    """
    Mixin to add created_at and updated_at timestamp columns.

    Automatically tracks when records are created and last updated.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when record was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Timestamp when record was last updated"
    )


class SoftDeleteMixin:
    """
    Mixin to add soft delete functionality.

    Uses is_active flag instead of hard deleting records.
    """

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Soft delete flag - False indicates deleted record"
    )


class TableNameMixin:
    """
    Mixin to automatically generate table names from class names.

    Converts CamelCase class names to snake_case table names.
    Example: PropertyRecord → property_records
    """

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """
        Generate table name from class name.

        Converts CamelCase to snake_case and adds 's' for pluralization.
        """
        # Convert CamelCase to snake_case
        import re
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', cls.__name__)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

        # Add 's' for plural (simple pluralization)
        if not name.endswith('s'):
            name += 's'

        return name


class DataSourceMixin:
    """
    Mixin to track data source information.

    Stores when data was scraped from external APIs.
    """

    data_source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when data was scraped from external API"
    )


# Import all models to ensure they're registered with Base
# This is used by Alembic for auto-generating migrations
def import_all_models():
    """
    Import all models to register them with SQLAlchemy Base.

    This function should be called before running Alembic migrations
    to ensure all models are discovered.
    """
    from src.wholesaler.db import models  # noqa: F401
@event.listens_for(Base.metadata, "before_create")
def adapt_special_columns(metadata, connection, **kwargs):
    """Replace unsupported column types when using SQLite."""
    if connection.engine.name != "sqlite":
        return

    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Geography):
                column.type = String(64)
            elif isinstance(column.type, JSONB):
                column.type = Text()
