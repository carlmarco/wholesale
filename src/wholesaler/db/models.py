"""
SQLAlchemy ORM Models

Database models mirroring the Pydantic models from Phase 1.
All models use the parcel_id_normalized as the primary relationship key.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, Boolean, Text,
    ForeignKey, CheckConstraint, UniqueConstraint, Index, Enum as SQLEnum, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geography

from src.wholesaler.db.base import (
    Base, TimestampMixin, SoftDeleteMixin, DataSourceMixin
)


class Property(Base, TimestampMixin, SoftDeleteMixin):
    """
    Master property table.

    One record per unique parcel. All other property-related tables
    reference this table via parcel_id_normalized.
    """
    __tablename__ = "properties"

    # Primary key
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        comment="Normalized parcel ID (digits only)"
    )

    # Address and location
    parcel_id_original: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Original parcel ID format"
    )
    situs_address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Standardized property address"
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="City name"
    )
    state: Mapped[Optional[str]] = mapped_column(
        String(2),
        nullable=True,
        comment="State abbreviation (FL)"
    )
    zip_code: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="5-digit ZIP code"
    )

    # Spatial data (PostGIS)
    latitude: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 7),
        nullable=True,
        comment="Latitude"
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 7),
        nullable=True,
        comment="Longitude"
    )

    # Seed tracking (for multi-source deduplication)
    seed_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Comma-separated list of seed types that identified this property"
    )

    # Relationships (1:1 with tax_sales, foreclosures, property_records, lead_scores)
    tax_sale: Mapped[Optional["TaxSale"]] = relationship(
        "TaxSale",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan"
    )
    foreclosure: Mapped[Optional["Foreclosure"]] = relationship(
        "Foreclosure",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan"
    )
    property_record: Mapped[Optional["PropertyRecord"]] = relationship(
        "PropertyRecord",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan"
    )
    lead_score: Mapped[Optional["LeadScore"]] = relationship(
        "LeadScore",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Relationships (1:many with code_violations)
    code_violations: Mapped[list["CodeViolation"]] = relationship(
        "CodeViolation",
        back_populates="property",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="check_latitude_range"
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="check_longitude_range"
        ),
        Index("idx_properties_situs_address", "situs_address"),
        Index("idx_properties_city", "city"),
        Index("idx_properties_zip_code", "zip_code"),
        Index("idx_properties_is_active", "is_active"),
        # Note: GeoAlchemy2 Geography type automatically creates GIST index on coordinates
    )

    def __repr__(self) -> str:
        return f"<Property(parcel_id={self.parcel_id_normalized}, address={self.situs_address})>"


class TaxSale(Base, TimestampMixin, DataSourceMixin):
    """Tax sale property records (1:1 with properties)."""
    __tablename__ = "tax_sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to properties
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("properties.parcel_id_normalized", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="References properties table"
    )

    # Tax sale data
    tda_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Tax deed application number"
    )
    sale_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Scheduled tax sale date"
    )
    deed_status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Deed status"
    )

    # Original API coordinates
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)

    # Raw API data
    raw_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw API response"
    )

    # Relationship
    property: Mapped["Property"] = relationship("Property", back_populates="tax_sale")

    # Indexes
    __table_args__ = (
        Index("idx_tax_sales_sale_date", "sale_date"),
        Index("idx_tax_sales_tda_number", "tda_number"),
    )

    def __repr__(self) -> str:
        return f"<TaxSale(parcel_id={self.parcel_id_normalized}, tda={self.tda_number})>"


class Foreclosure(Base, TimestampMixin, DataSourceMixin):
    """Foreclosure property records (1:1 with properties)."""
    __tablename__ = "foreclosures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to properties
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("properties.parcel_id_normalized", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="References properties table"
    )

    # Foreclosure data
    borrowers_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Borrower name"
    )
    situs_address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Property address from API"
    )
    default_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Amount in default"
    )
    opening_bid: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Opening bid amount"
    )
    auction_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Foreclosure auction date"
    )
    lender_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Lender/bank name"
    )
    property_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Property type"
    )

    # Original API coordinates
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)

    # Raw API data
    raw_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw API response"
    )

    # Relationship
    property: Mapped["Property"] = relationship("Property", back_populates="foreclosure")

    # Indexes
    __table_args__ = (
        Index("idx_foreclosures_auction_date", "auction_date"),
        Index("idx_foreclosures_default_amount", "default_amount"),
        Index("idx_foreclosures_raw_data", "raw_data", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Foreclosure(parcel_id={self.parcel_id_normalized}, borrower={self.borrowers_name})>"


class PropertyRecord(Base, TimestampMixin, DataSourceMixin):
    """Property appraiser valuation records (1:1 with properties)."""
    __tablename__ = "property_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to properties
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("properties.parcel_id_normalized", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="References properties table"
    )

    # Property owner and valuation
    owner_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Property owner name"
    )
    total_mkt: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Total market value"
    )
    total_assd: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Total assessed value"
    )
    taxable: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Taxable value"
    )
    taxes: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Annual taxes"
    )

    # Property characteristics
    year_built: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Year built"
    )
    living_area: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Living area (sq ft)"
    )
    lot_size: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Lot size (sq ft)"
    )

    # Calculated fields
    equity_percent: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Calculated equity percentage"
    )
    tax_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 4),
        nullable=True,
        comment="Calculated tax rate percentage"
    )

    # Original API coordinates
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)

    # Raw API data
    raw_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw API response"
    )

    # Relationship
    property: Mapped["Property"] = relationship("Property", back_populates="property_record")

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "year_built IS NULL OR year_built >= 1800",
            name="check_year_built_valid"
        ),
        Index("idx_property_records_total_mkt", "total_mkt"),
        Index("idx_property_records_equity_percent", "equity_percent"),
        Index("idx_property_records_year_built", "year_built"),
    )

    def __repr__(self) -> str:
        return f"<PropertyRecord(parcel_id={self.parcel_id_normalized}, value=${self.total_mkt})>"


class CodeViolation(Base, TimestampMixin, DataSourceMixin):
    """Code enforcement violations (many:1 with properties)."""
    __tablename__ = "code_violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to properties (nullable - violations may not match properties)
    parcel_id_normalized: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("properties.parcel_id_normalized", ondelete="CASCADE"),
        nullable=True,
        comment="References properties table"
    )

    # Violation data
    case_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        comment="Violation case number"
    )
    violation_type: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Type of violation"
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="OPEN or CLOSED"
    )
    opened_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Date violation opened"
    )
    closed_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Date violation closed"
    )

    # Spatial data (PostGIS)
    coordinates: Mapped[Optional[str]] = mapped_column(
        Geography(geometry_type='POINT', srid=4326),
        nullable=True,
        comment="WGS84 coordinates"
    )
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)

    # Raw data
    raw_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw API/CSV data"
    )

    # Relationship
    property: Mapped[Optional["Property"]] = relationship(
        "Property",
        back_populates="code_violations"
    )

    # Indexes
    __table_args__ = (
        Index("idx_code_violations_parcel_id", "parcel_id_normalized"),
        # Note: GeoAlchemy2 Geography type automatically creates GIST index for coordinates
        Index("idx_code_violations_status", "status"),
        Index("idx_code_violations_opened_date", "opened_date"),
    )

    def __repr__(self) -> str:
        return f"<CodeViolation(case={self.case_number}, status={self.status})>"


class LeadScore(Base, TimestampMixin):
    """Current lead scores for properties (1:1 with properties)."""
    __tablename__ = "lead_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to properties
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("properties.parcel_id_normalized", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="References properties table"
    )

    # Score components
    total_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Total lead score (0-100)"
    )
    distress_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Distress component (35%)"
    )
    value_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Value component (30%)"
    )
    location_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Location component (20%)"
    )
    urgency_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Urgency component (15%)"
    )

    # Tier classification
    tier: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        comment="Lead tier (A/B/C/D)"
    )

    # Scoring reasons (JSONB array)
    reasons: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of scoring reasons"
    )

    # ML-based predictions
    ml_probability: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="ML model distress probability (0-1)"
    )
    expected_return: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="ML predicted expected return in dollars"
    )
    ml_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="ML model confidence score (0-1)"
    )
    priority_flag: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        default=False,
        comment="High priority flag from ML/hybrid scoring"
    )
    
    # Phase 3.6 Profitability
    profitability_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Profitability bucket score (0-100)"
    )
    profitability_details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Detailed profitability metrics (projected_profit, roi, etc)"
    )
    
    # Phase 3.7 Label-Free ML
    ml_risk_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Composite risk score (0-1)"
    )
    ml_risk_tier: Mapped[Optional[str]] = mapped_column(
        String(1),
        nullable=True,
        comment="Risk tier (A/B/C/D)"
    )
    ml_cluster_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Unsupervised cluster ID"
    )
    ml_anomaly_score: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4),
        nullable=True,
        comment="Anomaly detection score"
    )

    # When scored
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When score was calculated"
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="lead_score")
    history: Mapped[list["LeadScoreHistory"]] = relationship(
        "LeadScoreHistory",
        back_populates="lead_score",
        cascade="all, delete-orphan"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "total_score >= 0 AND total_score <= 100",
            name="check_total_score_range"
        ),
        CheckConstraint(
            "tier IN ('A', 'B', 'C', 'D')",
            name="check_tier_valid"
        ),
        Index("idx_lead_scores_total_score", "total_score", postgresql_ops={"total_score": "DESC"}),
        Index("idx_lead_scores_tier", "tier"),
        Index("idx_lead_scores_scored_at", "scored_at"),
        Index("idx_lead_scores_reasons", "reasons", postgresql_using="gin"),
        Index("idx_lead_scores_tier_score", "tier", "total_score", postgresql_ops={"total_score": "DESC"}),
    )

    def __repr__(self) -> str:
        return f"<LeadScore(parcel_id={self.parcel_id_normalized}, score={self.total_score}, tier={self.tier})>"


class LeadScoreHistory(Base, TimestampMixin):
    """Historical snapshots of lead scores for trending analysis."""
    __tablename__ = "lead_score_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to lead_scores
    lead_score_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead_scores.id", ondelete="CASCADE"),
        nullable=False,
        comment="References lead_scores table"
    )

    # Denormalized for faster queries
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Denormalized parcel ID"
    )

    # Historical scores
    total_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Historical total score"
    )
    tier: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        comment="Historical tier"
    )

    # Snapshot date
    snapshot_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date of snapshot"
    )

    # Relationship
    lead_score: Mapped["LeadScore"] = relationship("LeadScore", back_populates="history")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("lead_score_id", "snapshot_date", name="uq_lead_score_snapshot"),
        Index("idx_lead_score_history_lead_score_id", "lead_score_id"),
        Index("idx_lead_score_history_parcel_id", "parcel_id_normalized"),
        Index("idx_lead_score_history_snapshot_date", "snapshot_date", postgresql_ops={"snapshot_date": "DESC"}),
    )

    def __repr__(self) -> str:
        return f"<LeadScoreHistory(parcel_id={self.parcel_id_normalized}, date={self.snapshot_date}, score={self.total_score})>"


class EnrichedSeed(Base):
    """Staging table for enriched seed records from UnifiedEnrichmentPipeline."""
    __tablename__ = "enriched_seeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Normalized parcel ID (digits only)"
    )

    seed_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Seed source: tax_sale, code_violation, foreclosure"
    )

    violation_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
        comment="Number of nearby violations found during enrichment"
    )

    most_recent_violation: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Date of most recent violation"
    )

    enriched_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full enriched record from UnifiedEnrichmentPipeline"
    )

    # Only created_at - no updated_at (matches migration schema)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When seed was enriched"
    )

    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether seed has been merged into properties table"
    )

    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When seed was processed into properties table"
    )

    __table_args__ = (
        UniqueConstraint('parcel_id_normalized', 'seed_type', name='uq_enriched_seeds_parcel_type'),
        Index('idx_enriched_seeds_parcel', 'parcel_id_normalized'),
        Index('idx_enriched_seeds_type', 'seed_type'),
        Index('idx_enriched_seeds_processed', 'processed'),
        Index('idx_enriched_seeds_created', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<EnrichedSeed(parcel={self.parcel_id_normalized}, type={self.seed_type}, processed={self.processed})>"


class DataIngestionRun(Base, TimestampMixin):
    """ETL job execution metadata and tracking."""
    __tablename__ = "data_ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Job metadata
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Source type: tax_sales, foreclosures, property_records, code_violations"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Job status: success, failure, partial"
    )

    # Record counts
    records_processed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total records processed"
    )
    records_inserted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Records inserted"
    )
    records_updated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Records updated"
    )
    records_failed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Records failed"
    )

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if failed"
    )
    error_details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured error data"
    )

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Job start time"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Job completion time"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failure', 'partial')",
            name="check_status_valid"
        ),
        Index("idx_data_ingestion_runs_source_type", "source_type"),
        Index("idx_data_ingestion_runs_status", "status"),
        Index("idx_data_ingestion_runs_started_at", "started_at", postgresql_ops={"started_at": "DESC"}),
    )

    def __repr__(self) -> str:
        return f"<DataIngestionRun(source={self.source_type}, status={self.status}, processed={self.records_processed})>"


class MLFeatureStore(Base):
    """
    Materialized feature store for ML training and inference.

    Flattened, normalized features computed from enriched_seeds and related tables.
    Each row represents a point-in-time feature vector for a parcel.
    """
    __tablename__ = "ml_feature_store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Normalized parcel ID"
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When features were computed"
    )

    # Distress features
    violation_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
        comment="Total number of violations"
    )
    open_violation_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
        comment="Number of open/active violations"
    )
    days_since_last_violation: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Days since most recent violation"
    )
    max_violation_severity: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Maximum violation severity score"
    )

    # Financial features
    total_market_value: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Total market value"
    )
    equity_percent: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Equity percentage"
    )
    tax_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 4),
        nullable=True,
        comment="Property tax rate"
    )
    default_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Foreclosure default amount"
    )
    opening_bid: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Foreclosure opening bid"
    )

    # Temporal features
    days_to_auction: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Days until foreclosure auction"
    )
    days_to_tax_sale: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Days until tax sale"
    )
    property_age_years: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Property age in years"
    )

    # Categorical features (one-hot encoded)
    seed_type_tax_sale: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Is tax sale seed"
    )
    seed_type_foreclosure: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Is foreclosure seed"
    )
    seed_type_code_violation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Is code violation seed"
    )

    # Location features (encoded)
    city_encoded: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="City label encoded"
    )
    zip_code_encoded: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ZIP code label encoded"
    )

    # Geo features
    nearby_violations_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
        comment="Number of nearby violations (geo radius)"
    )
    nearest_violation_distance: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        comment="Distance to nearest violation in miles"
    )

    # Target labels (when available for training)
    actual_distress_outcome: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="Did this property actually experience distress event"
    )
    actual_sale_price: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Actual sale price if sold"
    )
    label_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Date when label was recorded"
    )

    __table_args__ = (
        UniqueConstraint('parcel_id_normalized', 'computed_at', name='uq_ml_features_parcel_time'),
        Index('idx_ml_features_parcel', 'parcel_id_normalized'),
        Index('idx_ml_features_computed_at', 'computed_at'),
        Index('idx_ml_features_has_outcome', 'actual_distress_outcome'),
    )

    def __repr__(self) -> str:
        return f"<MLFeatureStore(parcel={self.parcel_id_normalized}, computed_at={self.computed_at})>"


class ModelRegistry(Base, TimestampMixin):
    """
    Registry for ML model artifacts and metadata.

    Tracks model versions, training metrics, and deployment status.
    """
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model name (e.g., distress_classifier, sale_probability)"
    )
    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Model version (e.g., v1.0.0, 20241114_120000)"
    )
    artifact_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Path to model artifact file (joblib)"
    )

    # Training metadata
    training_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When model was trained"
    )
    training_samples: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of training samples"
    )
    feature_names: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of feature names used"
    )
    hyperparameters: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Model hyperparameters"
    )

    # Performance metrics
    metrics: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Training/validation metrics (ROC-AUC, PR-AUC, MAE, etc.)"
    )
    validation_metrics: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Hold-out validation metrics"
    )

    # Deployment status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Is this the currently active/deployed model"
    )
    promoted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When model was promoted to production"
    )
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When model was deprecated"
    )

    # Notes
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Model description and notes"
    )

    __table_args__ = (
        UniqueConstraint('model_name', 'version', name='uq_model_name_version'),
        Index('idx_model_registry_name', 'model_name'),
        Index('idx_model_registry_active', 'is_active'),
        Index('idx_model_registry_training_date', 'training_date'),
    )

    def __repr__(self) -> str:
        return f"<ModelRegistry(name={self.model_name}, version={self.version}, active={self.is_active})>"
