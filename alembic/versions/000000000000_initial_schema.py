"""initial_schema

Revision ID: 000000000000
Revises: 
Create Date: 2025-11-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision: str = '000000000000'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Create properties table
    op.create_table(
        'properties',
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=False, comment='Normalized parcel ID (digits only)'),
        sa.Column('parcel_id_original', sa.String(length=50), nullable=False, comment='Original parcel ID format'),
        sa.Column('situs_address', sa.String(length=255), nullable=True, comment='Standardized property address'),
        sa.Column('city', sa.String(length=100), nullable=True, comment='City name'),
        sa.Column('state', sa.String(length=2), nullable=True, comment='State abbreviation (FL)'),
        sa.Column('zip_code', sa.String(length=10), nullable=True, comment='5-digit ZIP code'),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True, comment='Latitude'),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True, comment='Longitude'),
        sa.Column('coordinates', Geography(geometry_type='POINT', srid=4326), nullable=True, comment='WGS84 coordinates (PostGIS)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('TRUE'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('parcel_id_normalized'),
        sa.CheckConstraint('latitude >= -90 AND latitude <= 90', name='check_latitude_range'),
        sa.CheckConstraint('longitude >= -180 AND longitude <= 180', name='check_longitude_range')
    )
    op.create_index('idx_properties_situs_address', 'properties', ['situs_address'], unique=False)
    op.create_index('idx_properties_city', 'properties', ['city'], unique=False)
    op.create_index('idx_properties_zip_code', 'properties', ['zip_code'], unique=False)
    op.create_index('idx_properties_is_active', 'properties', ['is_active'], unique=False)
    # GeoAlchemy2 automatically creates index for coordinates

    # Create tax_sales table
    op.create_table(
        'tax_sales',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=False, comment='References properties table'),
        sa.Column('tda_number', sa.String(length=50), nullable=True, comment='Tax deed application number'),
        sa.Column('sale_date', sa.Date(), nullable=True, comment='Scheduled tax sale date'),
        sa.Column('deed_status', sa.String(length=100), nullable=True, comment='Deed status'),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Raw API response'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('source_system', sa.String(length=50), nullable=False, comment='Source system name'),
        sa.Column('source_id', sa.String(length=100), nullable=True, comment='ID in source system'),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['parcel_id_normalized'], ['properties.parcel_id_normalized'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parcel_id_normalized')
    )
    op.create_index('idx_tax_sales_sale_date', 'tax_sales', ['sale_date'], unique=False)
    op.create_index('idx_tax_sales_tda_number', 'tax_sales', ['tda_number'], unique=False)

    # Create foreclosures table
    op.create_table(
        'foreclosures',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=False, comment='References properties table'),
        sa.Column('borrowers_name', sa.String(length=255), nullable=True, comment='Borrower name'),
        sa.Column('situs_address', sa.String(length=255), nullable=True, comment='Property address from API'),
        sa.Column('default_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='Amount in default'),
        sa.Column('opening_bid', sa.Numeric(precision=12, scale=2), nullable=True, comment='Opening bid amount'),
        sa.Column('auction_date', sa.Date(), nullable=True, comment='Foreclosure auction date'),
        sa.Column('lender_name', sa.String(length=255), nullable=True, comment='Lender/bank name'),
        sa.Column('property_type', sa.String(length=100), nullable=True, comment='Property type'),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Raw API response'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('source_system', sa.String(length=50), nullable=False, comment='Source system name'),
        sa.Column('source_id', sa.String(length=100), nullable=True, comment='ID in source system'),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['parcel_id_normalized'], ['properties.parcel_id_normalized'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parcel_id_normalized')
    )
    op.create_index('idx_foreclosures_auction_date', 'foreclosures', ['auction_date'], unique=False)
    op.create_index('idx_foreclosures_default_amount', 'foreclosures', ['default_amount'], unique=False)
    op.create_index('idx_foreclosures_raw_data', 'foreclosures', ['raw_data'], unique=False, postgresql_using='gin')

    # Create property_records table
    op.create_table(
        'property_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=False, comment='References properties table'),
        sa.Column('owner_name', sa.String(length=255), nullable=True, comment='Property owner name'),
        sa.Column('total_mkt', sa.Numeric(precision=12, scale=2), nullable=True, comment='Total market value'),
        sa.Column('total_assd', sa.Numeric(precision=12, scale=2), nullable=True, comment='Total assessed value'),
        sa.Column('taxable', sa.Numeric(precision=12, scale=2), nullable=True, comment='Taxable value'),
        sa.Column('taxes', sa.Numeric(precision=12, scale=2), nullable=True, comment='Annual taxes'),
        sa.Column('year_built', sa.Integer(), nullable=True, comment='Year built'),
        sa.Column('living_area', sa.Integer(), nullable=True, comment='Living area (sq ft)'),
        sa.Column('lot_size', sa.Integer(), nullable=True, comment='Lot size (sq ft)'),
        sa.Column('equity_percent', sa.Numeric(precision=6, scale=2), nullable=True, comment='Calculated equity percentage'),
        sa.Column('tax_rate', sa.Numeric(precision=6, scale=4), nullable=True, comment='Calculated tax rate percentage'),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Raw API response'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('source_system', sa.String(length=50), nullable=False, comment='Source system name'),
        sa.Column('source_id', sa.String(length=100), nullable=True, comment='ID in source system'),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['parcel_id_normalized'], ['properties.parcel_id_normalized'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parcel_id_normalized'),
        sa.CheckConstraint('year_built IS NULL OR year_built >= 1800', name='check_year_built_valid')
    )
    op.create_index('idx_property_records_total_mkt', 'property_records', ['total_mkt'], unique=False)
    op.create_index('idx_property_records_equity_percent', 'property_records', ['equity_percent'], unique=False)
    op.create_index('idx_property_records_year_built', 'property_records', ['year_built'], unique=False)

    # Create code_violations table
    op.create_table(
        'code_violations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=True, comment='References properties table'),
        sa.Column('case_number', sa.String(length=100), nullable=False, comment='Violation case number'),
        sa.Column('violation_type', sa.String(length=255), nullable=True, comment='Type of violation'),
        sa.Column('status', sa.String(length=50), nullable=True, comment='OPEN or CLOSED'),
        sa.Column('opened_date', sa.Date(), nullable=True, comment='Date violation opened'),
        sa.Column('closed_date', sa.Date(), nullable=True, comment='Date violation closed'),
        sa.Column('coordinates', Geography(geometry_type='POINT', srid=4326), nullable=True, comment='WGS84 coordinates'),
        sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Raw API/CSV data'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('source_system', sa.String(length=50), nullable=False, comment='Source system name'),
        sa.Column('source_id', sa.String(length=100), nullable=True, comment='ID in source system'),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['parcel_id_normalized'], ['properties.parcel_id_normalized'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_number')
    )
    op.create_index('idx_code_violations_parcel_id', 'code_violations', ['parcel_id_normalized'], unique=False)
    op.create_index('idx_code_violations_status', 'code_violations', ['status'], unique=False)
    op.create_index('idx_code_violations_opened_date', 'code_violations', ['opened_date'], unique=False)

    # Create lead_scores table
    op.create_table(
        'lead_scores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=False, comment='References properties table'),
        sa.Column('total_score', sa.Numeric(precision=5, scale=2), nullable=False, comment='Total lead score (0-100)'),
        sa.Column('distress_score', sa.Numeric(precision=5, scale=2), nullable=False, comment='Distress component (35%)'),
        sa.Column('value_score', sa.Numeric(precision=5, scale=2), nullable=False, comment='Value component (30%)'),
        sa.Column('location_score', sa.Numeric(precision=5, scale=2), nullable=False, comment='Location component (20%)'),
        sa.Column('urgency_score', sa.Numeric(precision=5, scale=2), nullable=False, comment='Urgency component (15%)'),
        sa.Column('tier', sa.String(length=1), nullable=False, comment='Lead tier (A/B/C/D)'),
        sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='List of scoring reasons'),
        sa.Column('scored_at', sa.DateTime(timezone=True), nullable=False, comment='When score was calculated'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['parcel_id_normalized'], ['properties.parcel_id_normalized'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parcel_id_normalized'),
        sa.CheckConstraint('total_score >= 0 AND total_score <= 100', name='check_total_score_range'),
        sa.CheckConstraint("tier IN ('A', 'B', 'C', 'D')", name='check_tier_valid')
    )
    op.create_index('idx_lead_scores_total_score', 'lead_scores', ['total_score'], unique=False, postgresql_ops={'total_score': 'DESC'})
    op.create_index('idx_lead_scores_tier', 'lead_scores', ['tier'], unique=False)
    op.create_index('idx_lead_scores_scored_at', 'lead_scores', ['scored_at'], unique=False)
    op.create_index('idx_lead_scores_reasons', 'lead_scores', ['reasons'], unique=False, postgresql_using='gin')

    # Create lead_score_history table
    op.create_table(
        'lead_score_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_score_id', sa.Integer(), nullable=False, comment='References lead_scores table'),
        sa.Column('parcel_id_normalized', sa.String(length=50), nullable=False, comment='Denormalized parcel ID'),
        sa.Column('total_score', sa.Numeric(precision=5, scale=2), nullable=False, comment='Historical total score'),
        sa.Column('tier', sa.String(length=1), nullable=False, comment='Historical tier'),
        sa.Column('snapshot_date', sa.Date(), nullable=False, comment='Date of snapshot'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['lead_score_id'], ['lead_scores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lead_score_id', 'snapshot_date', name='uq_lead_score_snapshot')
    )
    op.create_index('idx_lead_score_history_lead_score_id', 'lead_score_history', ['lead_score_id'], unique=False)
    op.create_index('idx_lead_score_history_parcel_id', 'lead_score_history', ['parcel_id_normalized'], unique=False)
    op.create_index('idx_lead_score_history_snapshot_date', 'lead_score_history', ['snapshot_date'], unique=False, postgresql_ops={'snapshot_date': 'DESC'})

    # Create data_ingestion_runs table
    op.create_table(
        'data_ingestion_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False, comment='Source type: tax_sales, foreclosures, property_records, code_violations'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='Job status: success, failure, partial'),
        sa.Column('records_processed', sa.Integer(), nullable=False, default=0, comment='Total records processed'),
        sa.Column('records_inserted', sa.Integer(), nullable=False, default=0, comment='Records inserted'),
        sa.Column('records_updated', sa.Integer(), nullable=False, default=0, comment='Records updated'),
        sa.Column('records_failed', sa.Integer(), nullable=False, default=0, comment='Records failed'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Error details if failed'),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Structured error data'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, comment='Job start time'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='Job completion time'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('running', 'success', 'failure', 'partial')", name='check_status_valid')
    )
    op.create_index('idx_data_ingestion_runs_source_type', 'data_ingestion_runs', ['source_type'], unique=False)
    op.create_index('idx_data_ingestion_runs_status', 'data_ingestion_runs', ['status'], unique=False)
    op.create_index('idx_data_ingestion_runs_started_at', 'data_ingestion_runs', ['started_at'], unique=False, postgresql_ops={'started_at': 'DESC'})


def downgrade() -> None:
    op.drop_table('data_ingestion_runs')
    op.drop_table('lead_score_history')
    op.drop_table('lead_scores')
    op.drop_table('code_violations')
    op.drop_table('property_records')
    op.drop_table('foreclosures')
    op.drop_table('tax_sales')
    op.drop_table('properties')
