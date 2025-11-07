"""
Pydantic Schemas for API Request/Response Models

These schemas define the JSON structure for API endpoints.
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


class PropertyBase(BaseModel):
    """Base property schema."""
    parcel_id_normalized: str
    situs_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PropertyDetail(PropertyBase):
    """Detailed property schema with all fields."""
    parcel_id_original: Optional[str] = None
    county: Optional[str] = None
    property_use: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaxSaleInfo(BaseModel):
    """Tax sale information."""
    tda_number: Optional[str] = None
    sale_date: Optional[date] = None
    deed_status: Optional[str] = None
    opening_bid: Optional[float] = None

    class Config:
        from_attributes = True


class ForeclosureInfo(BaseModel):
    """Foreclosure information."""
    case_number: Optional[str] = None
    filing_date: Optional[date] = None
    auction_date: Optional[date] = None
    judgment_amount: Optional[float] = None
    foreclosure_status: Optional[str] = None

    class Config:
        from_attributes = True


class LeadScoreBase(BaseModel):
    """Base lead score schema."""
    parcel_id_normalized: str
    distress_score: float = Field(..., ge=0, le=100)
    value_score: float = Field(..., ge=0, le=100)
    location_score: float = Field(..., ge=0, le=100)
    urgency_score: float = Field(..., ge=0, le=100)
    total_score: float = Field(..., ge=0, le=100)
    tier: str = Field(..., pattern="^[A-D]$")
    scoring_reasons: List[str] = Field(default_factory=list)


class LeadScoreListItem(LeadScoreBase):
    """Lead score for list views."""
    property: PropertyBase
    scored_at: datetime

    class Config:
        from_attributes = True


class LeadScoreDetail(LeadScoreBase):
    """Detailed lead score with property, tax sale, and foreclosure info."""
    property: PropertyDetail
    tax_sale: Optional[TaxSaleInfo] = None
    foreclosure: Optional[ForeclosureInfo] = None
    scored_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeadScoreHistory(BaseModel):
    """Historical lead score snapshot."""
    snapshot_date: datetime
    total_score: float
    tier: str
    distress_score: float
    value_score: float
    location_score: float
    urgency_score: float

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    """Dashboard statistics."""
    total_leads: int
    tier_a_count: int
    tier_b_count: int
    tier_c_count: int
    tier_d_count: int
    avg_score_tier_a: Optional[float] = None
    avg_score_tier_b: Optional[float] = None
    avg_score_tier_c: Optional[float] = None
    avg_score_tier_d: Optional[float] = None
    total_properties: int
    properties_with_tax_sales: int
    properties_with_foreclosures: int
    recent_tier_a_count: int = Field(..., description="Tier A leads scored in last 7 days")


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "0.3.0"
    database: str = "connected"
    timestamp: datetime


class LeadFilters(BaseModel):
    """Query parameters for filtering leads."""
    tier: Optional[str] = Field(None, pattern="^[A-D]$")
    min_score: Optional[float] = Field(None, ge=0, le=100)
    max_score: Optional[float] = Field(None, ge=0, le=100)
    city: Optional[str] = None
    zip_code: Optional[str] = None
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    sort_by: str = Field("total_score", pattern="^(total_score|scored_at|situs_address)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")
