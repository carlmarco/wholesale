"""
Shared pytest fixtures.

The ORM models are Postgres-specific: they use JSONB, PostGIS ``Geography``
columns, and ``sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update``
in the repository layer. Running them against SQLite silently changes behaviour
and fails on JSONB binding, so database-backed tests run against a real
PostGIS-enabled Postgres instance.

Point ``TEST_DATABASE_URL`` at that instance (CI and docker-compose already
provide one). Each test runs inside a transaction that is rolled back on
teardown, so tests share one schema without leaking state between them.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.wholesaler.db.base import Base

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg2://wholesaler_user:wholesaler_pass@localhost:5432/wholesaler_test"
)


def get_test_database_url() -> str:
    """Resolve the database URL used by database-backed tests."""
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def db_engine():
    """
    Create the schema once per test session against a real Postgres database.

    Fails loudly rather than skipping: these tests assert on behaviour that only
    Postgres provides, so a missing database is a broken environment, not a
    reason to report success.
    """
    url = get_test_database_url()
    engine = create_engine(url)

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.fail(
            f"Could not connect to the test database at {url!r}: {exc}\n"
            "Database-backed tests require a PostGIS-enabled Postgres instance. "
            "Start one with `docker compose up -d postgres` or set TEST_DATABASE_URL."
        )

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(db_engine):
    """
    Provide a session bound to a transaction that is rolled back after the test.

    Committing inside a test is safe: the session joins an outer transaction
    that is discarded on teardown.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def session(test_db):
    """Alias for :func:`test_db`, for tests that name the fixture ``session``."""
    return test_db
