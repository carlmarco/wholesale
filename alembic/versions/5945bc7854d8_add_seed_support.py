"""add_seed_support

Add hybrid seed ingestion support to database schema.

Changes:
- Add seed_type column to properties table to track primary seed source
- Create enriched_seeds staging table for ETL pipeline
- Add indexes for efficient querying

Revision ID: 5945bc7854d8
Revises:
Create Date: 2025-11-11 21:37:26.776794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5945bc7854d8'
down_revision: Union[str, Sequence[str], None] = '000000000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to support hybrid seed ingestion."""

    # Add seed_type column to properties table
    op.add_column(
        'properties',
        sa.Column(
            'seed_type',
            sa.String(length=100),
            nullable=True,
            comment='Primary seed source(s): tax_sale, code_violation, foreclosure (comma-separated for multi-source)'
        )
    )

    # Create index on seed_type for efficient filtering
    op.create_index(
        'idx_properties_seed_type',
        'properties',
        ['seed_type']
    )

    # Create enriched_seeds staging table for ETL pipeline
    op.create_table(
        'enriched_seeds',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            'parcel_id_normalized',
            sa.String(length=50),
            nullable=False,
            comment='Normalized parcel ID (digits only)'
        ),
        sa.Column(
            'seed_type',
            sa.String(length=50),
            nullable=False,
            comment='Seed source: tax_sale, code_violation, foreclosure'
        ),
        sa.Column(
            'violation_count',
            sa.Integer(),
            nullable=True,
            default=0,
            comment='Number of nearby violations found during enrichment'
        ),
        sa.Column(
            'most_recent_violation',
            sa.Date(),
            nullable=True,
            comment='Date of most recent violation'
        ),
        sa.Column(
            'enriched_data',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Full enriched record from UnifiedEnrichmentPipeline'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='When seed was enriched'
        ),
        sa.Column(
            'processed',
            sa.Boolean(),
            server_default=sa.text('FALSE'),
            nullable=False,
            comment='Whether seed has been merged into properties table'
        ),
        sa.Column(
            'processed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When seed was processed into properties table'
        ),
        # Unique constraint: one enriched seed per (parcel, seed_type) combination
        sa.UniqueConstraint('parcel_id_normalized', 'seed_type', name='uq_enriched_seeds_parcel_type')
    )

    # Indexes for enriched_seeds table
    op.create_index(
        'idx_enriched_seeds_parcel',
        'enriched_seeds',
        ['parcel_id_normalized']
    )

    op.create_index(
        'idx_enriched_seeds_type',
        'enriched_seeds',
        ['seed_type']
    )

    op.create_index(
        'idx_enriched_seeds_processed',
        'enriched_seeds',
        ['processed']
    )

    op.create_index(
        'idx_enriched_seeds_created',
        'enriched_seeds',
        ['created_at']
    )


def downgrade() -> None:
    """Downgrade schema to remove seed support."""

    # Drop enriched_seeds table (includes all its indexes)
    op.drop_table('enriched_seeds')

    # Drop seed_type index and column from properties
    op.drop_index('idx_properties_seed_type', table_name='properties')
    op.drop_column('properties', 'seed_type')
