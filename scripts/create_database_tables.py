"""
Create Database Tables Using SQLAlchemy

This script creates all database tables directly using SQLAlchemy's create_all()
method. This bypasses Alembic migrations and is useful for testing or when
migrations have issues.
"""
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import engine, create_all_tables
from src.wholesaler.db.base import import_all_models
from src.wholesaler.utils.logger import get_logger
import sqlalchemy as sa

logger = get_logger(__name__)


def main():
    """Create all database tables."""
    logger.info("Starting database table creation...")

    # Ensure PostGIS extension is enabled
    logger.info("Enabling PostGIS extension...")
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis_topology"))
        conn.commit()

    # Import all models to register them with Base
    logger.info("Importing all models...")
    import_all_models()

    # Create all tables
    logger.info("Creating database tables...")
    create_all_tables()

    # Verify tables were created
    logger.info("Verifying tables...")
    with engine.connect() as conn:
        result = conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        ))
        tables = [row[0] for row in result]

    logger.info(f"Successfully created {len(tables)} tables:")
    for table in tables:
        logger.info(f"  - {table}")

    # Verify indexes
    with engine.connect() as conn:
        result = conn.execute(sa.text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' "
            "ORDER BY indexname"
        ))
        indexes = [row[0] for row in result]

    logger.info(f"Created {len(indexes)} indexes")

    logger.info("Database setup complete!")


if __name__ == "__main__":
    main()
