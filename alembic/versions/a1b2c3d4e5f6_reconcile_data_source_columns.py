"""Reconcile source-tracking columns with the ORM models

The initial schema gave the source tables source_system, source_id and
ingested_at, but DataSourceMixin declares a single data_source_timestamp. No
application code references the three migration-only columns, while the ETL
loaders write data_source_timestamp on every tax sale, foreclosure and property
record - a column that did not exist in a migrated database. source_system was
also NOT NULL and never set by the ORM, so every insert through the ORM failed.

This adds the column the ORM writes and drops the NOT NULL constraint that made
those inserts impossible. The unused columns are left in place: they carry no
readers, and dropping them would discard data from existing deployments. Removing
them is a separate, deliberate migration.

Revision ID: a1b2c3d4e5f6
Revises: cd4eec9402a8
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'cd4eec9402a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables carrying DataSourceMixin in the ORM.
SOURCE_TABLES = ('tax_sales', 'foreclosures', 'property_records', 'code_violations')


def upgrade() -> None:
    """Upgrade schema."""
    for table in SOURCE_TABLES:
        op.add_column(
            table,
            sa.Column(
                'data_source_timestamp',
                sa.DateTime(timezone=True),
                nullable=True,
                comment='Timestamp when data was scraped from external API',
            ),
        )
        # Preserve what the old column recorded so the new one is not empty
        # for rows that predate it.
        op.execute(f'UPDATE {table} SET data_source_timestamp = ingested_at')

        # The ORM does not declare source_system, so a NOT NULL constraint on
        # it rejects every ORM insert.
        op.alter_column(
            table,
            'source_system',
            existing_type=sa.String(length=50),
            nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in SOURCE_TABLES:
        op.execute(f"UPDATE {table} SET source_system = 'unknown' WHERE source_system IS NULL")
        op.alter_column(
            table,
            'source_system',
            existing_type=sa.String(length=50),
            nullable=False,
        )
        op.drop_column(table, 'data_source_timestamp')
