"""
Guard against drift between the ORM models and the Alembic migrations.

The application reads and writes through the ORM, but a deployed database is
built by the migrations. When the two disagree, the test suite still passes -
it builds its schema from the models - while production fails on columns that
are not there. This test compares the two schemas directly so that divergence
shows up here instead of in a production write.
"""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text

from src.wholesaler.db.base import Base
from tests.conftest import get_test_database_url

IGNORED_TABLES = {"alembic_version"}


def _migrated_database_url() -> str:
    """A separate database so migrating does not disturb the shared fixture."""
    base = get_test_database_url()
    return os.environ.get("MIGRATION_TEST_DATABASE_URL", base + "_migrations")


@pytest.fixture(scope="module")
def migrated_engine():
    url = _migrated_database_url()
    admin_url, _, db_name = url.rpartition("/")

    admin = create_engine(admin_url + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.skip(f"Cannot provision the migration test database: {exc}")
    finally:
        admin.dispose()

    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    # alembic/env.py takes its URL from settings, not from the config object,
    # so the migration runs the way CI and deploys run it: as a subprocess with
    # DATABASE_URL set.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def model_engine():
    url = _migrated_database_url() + "_models"
    admin_url, _, db_name = url.rpartition("/")

    admin = create_engine(admin_url + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.skip(f"Cannot provision the model test database: {exc}")
    finally:
        admin.dispose()

    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    Base.metadata.create_all(engine)

    yield engine
    engine.dispose()


def _tables(engine):
    return {t for t in inspect(engine).get_table_names() if t not in IGNORED_TABLES}


def test_same_tables(migrated_engine, model_engine):
    assert _tables(migrated_engine) == _tables(model_engine)


def test_every_orm_column_exists_in_migrations(migrated_engine):
    """The ORM must not read or write a column a migrated database lacks.

    This is the failure that hid behind a schema built from the models: the
    loaders wrote data_source_timestamp, which the migrations never created, so
    every tax sale, foreclosure and property record write failed in production
    while the suite stayed green.
    """
    migrated = inspect(migrated_engine)
    missing = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in _tables(migrated_engine):
            continue
        in_migration = {c["name"] for c in migrated.get_columns(table_name)}
        for name in sorted(set(table.columns.keys()) - in_migration):
            missing.append(f"{table_name}.{name}")

    assert not missing, (
        "The ORM declares columns the migrations do not create, so reads and "
        "writes of these fail against a migrated database:\n  " + "\n  ".join(missing)
    )


def test_orm_can_write_every_required_column(migrated_engine):
    """A required column the ORM does not declare makes inserts impossible."""
    migrated = inspect(migrated_engine)
    unwritable = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in _tables(migrated_engine):
            continue
        declared = set(table.columns.keys())
        for column in migrated.get_columns(table_name):
            if column["nullable"] or column["default"] is not None:
                continue
            if column["name"] not in declared:
                unwritable.append(f"{table_name}.{column['name']}")

    assert not unwritable, (
        "Migrations require NOT NULL columns the ORM cannot populate, so every "
        "insert through the ORM fails against a migrated database:\n  "
        + "\n  ".join(unwritable)
    )


def test_reports_columns_the_orm_has_retired(migrated_engine, model_engine):
    """Columns left in the database that no model declares.

    Nullable leftovers are harmless - nothing reads them - so this reports
    rather than fails. It exists so retired columns stay visible instead of
    accumulating silently.
    """
    migrated, model = inspect(migrated_engine), inspect(model_engine)
    retired = []

    for table in sorted(_tables(migrated_engine) & _tables(model_engine)):
        in_model = {c["name"] for c in model.get_columns(table)}
        for column in migrated.get_columns(table):
            if column["name"] not in in_model:
                retired.append(f"{table}.{column['name']}")

    if retired:
        print("\nColumns present in the database but retired from the models:")
        for name in retired:
            print(f"  {name}")
