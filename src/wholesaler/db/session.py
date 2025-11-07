"""
Database Session Management

Provides database connection pooling and session management.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, exc, pool
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine

from config.settings import settings
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


# Create database engine with connection pooling
engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.database_echo,  # Log SQL queries if enabled
)


# Event listeners for connection management
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """
    Event listener for new database connections.

    Logs connection establishment and sets connection parameters.
    """
    logger.debug("database_connection_established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """
    Event listener for connection checkout from pool.

    Logs when a connection is retrieved from the pool.
    """
    logger.debug("database_connection_checkout")


@event.listens_for(pool.Pool, "invalidate")
def receive_invalidate(dbapi_conn, connection_record, exception):
    """
    Event listener for connection invalidation.

    Logs when a connection is marked as invalid and removed from pool.
    """
    logger.warning(
        "database_connection_invalidated",
        exception=str(exception) if exception else None
    )


# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Get database session with automatic cleanup.

    Usage:
        with get_db_session() as session:
            # Perform database operations
            result = session.query(Model).all()

    Yields:
        Database session

    Raises:
        Exception: Re-raises any exception after rollback
    """
    session = SessionLocal()
    try:
        logger.debug("database_session_created")
        yield session
        session.commit()
        logger.debug("database_session_committed")
    except exc.SQLAlchemyError as e:
        session.rollback()
        logger.error(
            "database_session_rollback",
            error=str(e),
            error_type=type(e).__name__
        )
        raise
    except Exception as e:
        session.rollback()
        logger.error(
            "database_session_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise
    finally:
        session.close()
        logger.debug("database_session_closed")


def get_db() -> Session:
    """
    Get database session without context manager.

    WARNING: Caller is responsible for closing the session.
    Prefer using get_db_session() context manager instead.

    Returns:
        Database session
    """
    logger.debug("database_session_created_manual")
    return SessionLocal()


def health_check() -> bool:
    """
    Check database connection health.

    Returns:
        True if database is accessible, False otherwise
    """
    try:
        with get_db_session() as session:
            # Execute simple query
            session.execute("SELECT 1")
            logger.info("database_health_check_success")
            return True
    except Exception as e:
        logger.error(
            "database_health_check_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


def close_connections():
    """
    Close all database connections and dispose of the engine.

    Should be called on application shutdown.
    """
    logger.info("closing_database_connections")
    engine.dispose()
    logger.info("database_connections_closed")


def create_all_tables():
    """
    Create all database tables defined in models.

    WARNING: Use Alembic migrations instead in production.
    This is only for testing and initial setup.
    """
    from src.wholesaler.db.base import Base, import_all_models

    logger.info("creating_database_tables")

    # Import all models to register them
    import_all_models()

    # Create tables
    Base.metadata.create_all(bind=engine)

    logger.info("database_tables_created")


def drop_all_tables():
    """
    Drop all database tables.

    WARNING: This will delete all data! Only use in development/testing.
    """
    from src.wholesaler.db.base import Base, import_all_models

    logger.warning("dropping_all_database_tables")

    # Import all models
    import_all_models()

    # Drop tables
    Base.metadata.drop_all(bind=engine)

    logger.warning("all_database_tables_dropped")


# Retry decorator for transient database errors
def with_retry(max_retries: int = 3, retry_delay: int = 1):
    """
    Decorator to retry database operations on transient failures.

    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Usage:
        @with_retry(max_retries=3)
        def my_database_operation(session):
            # Perform operation
            pass
    """
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (exc.OperationalError, exc.DisconnectionError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            "database_operation_retry",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            error=str(e)
                        )
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    else:
                        logger.error(
                            "database_operation_failed_after_retries",
                            max_retries=max_retries,
                            error=str(e)
                        )

            raise last_exception

        return wrapper
    return decorator
