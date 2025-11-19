"""add_ml_feature_store_and_model_registry

Add ML Feature Store and Model Registry tables for ML pipeline infrastructure.

Changes:
- Add ML prediction columns to lead_scores table
- Create ml_feature_store table for materialized features
- Create model_registry table for model versioning

Revision ID: 6f01226d28f2
Revises: 5945bc7854d8
Create Date: 2025-11-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6f01226d28f2'
down_revision: Union[str, Sequence[str], None] = '5945bc7854d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add ML Feature Store and Model Registry."""

    # Add ML prediction columns to lead_scores table
    op.add_column(
        'lead_scores',
        sa.Column(
            'ml_probability',
            sa.Numeric(precision=5, scale=4),
            nullable=True,
            comment='ML model distress probability (0-1)'
        )
    )
    op.add_column(
        'lead_scores',
        sa.Column(
            'expected_return',
            sa.Numeric(precision=12, scale=2),
            nullable=True,
            comment='ML predicted expected return in dollars'
        )
    )
    op.add_column(
        'lead_scores',
        sa.Column(
            'ml_confidence',
            sa.Numeric(precision=5, scale=4),
            nullable=True,
            comment='ML model confidence score (0-1)'
        )
    )
    op.add_column(
        'lead_scores',
        sa.Column(
            'priority_flag',
            sa.Boolean(),
            nullable=True,
            server_default=sa.text('FALSE'),
            comment='High priority flag from ML/hybrid scoring'
        )
    )

    # Create indexes for ML columns
    op.create_index(
        'idx_lead_scores_ml_probability',
        'lead_scores',
        ['ml_probability']
    )
    op.create_index(
        'idx_lead_scores_priority_flag',
        'lead_scores',
        ['priority_flag']
    )

    # Create ml_feature_store table
    op.create_table(
        'ml_feature_store',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            'parcel_id_normalized',
            sa.String(length=50),
            nullable=False,
            unique=True,
            comment='Normalized parcel ID (digits only)'
        ),
        sa.Column(
            'computed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='When features were last computed'
        ),
        # Seed type features (one-hot encoded)
        sa.Column('seed_type_tax_sale', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('seed_type_foreclosure', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('seed_type_code_violation', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        # Violation metrics
        sa.Column('violation_count', sa.Integer(), nullable=True, comment='Number of code violations'),
        sa.Column('days_since_last_violation', sa.Integer(), nullable=True, comment='Days since most recent violation'),
        sa.Column('open_violation_count', sa.Integer(), nullable=True, comment='Number of open violations'),
        # Property record features
        sa.Column('total_mkt', sa.Numeric(precision=12, scale=2), nullable=True, comment='Total market value'),
        sa.Column('equity_percent', sa.Numeric(precision=5, scale=2), nullable=True, comment='Equity percentage'),
        sa.Column('year_built', sa.Integer(), nullable=True, comment='Year property was built'),
        sa.Column('property_age_years', sa.Integer(), nullable=True, comment='Age of property in years'),
        sa.Column('taxes', sa.Numeric(precision=10, scale=2), nullable=True, comment='Annual taxes'),
        sa.Column('living_area', sa.Integer(), nullable=True, comment='Living area in sqft'),
        sa.Column('lot_size', sa.Numeric(precision=12, scale=2), nullable=True, comment='Lot size'),
        # Foreclosure features
        sa.Column('default_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='Foreclosure default amount'),
        sa.Column('opening_bid', sa.Numeric(precision=12, scale=2), nullable=True, comment='Foreclosure opening bid'),
        sa.Column('days_to_auction', sa.Integer(), nullable=True, comment='Days until foreclosure auction'),
        # Tax sale features
        sa.Column('has_tax_sale', sa.Boolean(), nullable=False, server_default=sa.text('FALSE'), comment='Has tax sale record'),
        sa.Column('tax_sale_deed_status', sa.String(length=50), nullable=True, comment='Tax sale deed status'),
        # Geo enrichment features
        sa.Column('nearby_violations', sa.Integer(), nullable=True, comment='Number of nearby violations from geo enrichment'),
        sa.Column('nearby_open_violations', sa.Integer(), nullable=True, comment='Number of nearby open violations'),
        # Location features (encoded)
        sa.Column('city_encoded', sa.Integer(), nullable=True, comment='City label encoded'),
        sa.Column('zip_code_encoded', sa.Integer(), nullable=True, comment='ZIP code label encoded'),
        # Derived features
        sa.Column('distress_score', sa.Numeric(precision=5, scale=4), nullable=True, comment='Computed distress score'),
        sa.Column('equity_risk_ratio', sa.Numeric(precision=8, scale=4), nullable=True, comment='Equity to risk ratio'),
    )

    # Indexes for ml_feature_store
    op.create_index(
        'idx_ml_feature_store_parcel',
        'ml_feature_store',
        ['parcel_id_normalized']
    )
    op.create_index(
        'idx_ml_feature_store_computed_at',
        'ml_feature_store',
        ['computed_at']
    )

    # Create model_registry table
    op.create_table(
        'model_registry',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            'model_name',
            sa.String(length=100),
            nullable=False,
            comment='Name of the ML model (e.g., distress_classifier, sale_probability)'
        ),
        sa.Column(
            'version',
            sa.String(length=50),
            nullable=False,
            comment='Model version identifier (timestamp or semantic version)'
        ),
        sa.Column(
            'artifact_path',
            sa.String(length=500),
            nullable=False,
            comment='Path to model artifact file (joblib/pickle)'
        ),
        sa.Column(
            'metrics',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Training and validation metrics'
        ),
        sa.Column(
            'hyperparameters',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Model hyperparameters used during training'
        ),
        sa.Column(
            'feature_names',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='List of feature names used by the model'
        ),
        sa.Column(
            'training_date',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='When the model was trained'
        ),
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('FALSE'),
            comment='Whether this model version is currently active for inference'
        ),
        sa.Column(
            'promoted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When the model was promoted to production'
        ),
        sa.Column(
            'retired_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When the model was retired from production'
        ),
        sa.Column(
            'created_by',
            sa.String(length=100),
            nullable=True,
            comment='User or system that created this model'
        ),
        sa.Column(
            'notes',
            sa.Text(),
            nullable=True,
            comment='Additional notes about this model version'
        ),
        # Unique constraint: one version per model
        sa.UniqueConstraint('model_name', 'version', name='uq_model_registry_name_version')
    )

    # Indexes for model_registry
    op.create_index(
        'idx_model_registry_name',
        'model_registry',
        ['model_name']
    )
    op.create_index(
        'idx_model_registry_active',
        'model_registry',
        ['model_name', 'is_active']
    )
    op.create_index(
        'idx_model_registry_training_date',
        'model_registry',
        ['training_date']
    )


def downgrade() -> None:
    """Downgrade schema to remove ML Feature Store and Model Registry."""

    # Drop model_registry table
    op.drop_table('model_registry')

    # Drop ml_feature_store table
    op.drop_table('ml_feature_store')

    # Drop ML columns from lead_scores
    op.drop_index('idx_lead_scores_priority_flag', table_name='lead_scores')
    op.drop_index('idx_lead_scores_ml_probability', table_name='lead_scores')
    op.drop_column('lead_scores', 'priority_flag')
    op.drop_column('lead_scores', 'ml_confidence')
    op.drop_column('lead_scores', 'expected_return')
    op.drop_column('lead_scores', 'ml_probability')
