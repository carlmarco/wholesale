"""
Property Data Models

Pydantic models for property data validation and serialization.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class CodeViolation(BaseModel):
    """
    Code enforcement violation record.

    Attributes:
        apno: Application number (unique identifier)
        case_status: Status of the case (Open, Closed)
        latitude: WGS84 latitude coordinate
        longitude: WGS84 longitude coordinate
        case_type: Type of violation (Lot, Housing, Sign, etc.)
        case_date: Date violation was filed
    """

    apno: Optional[str] = Field(None, description="Application number")
    case_status: Optional[str] = Field(None, description="Case status")
    latitude: Optional[float] = Field(None, description="WGS84 latitude", ge=-90, le=90)
    longitude: Optional[float] = Field(None, description="WGS84 longitude", ge=-180, le=180)
    case_type: Optional[str] = Field(None, description="Type of violation")
    case_date: Optional[str] = Field(None, description="Case filing date")

    def has_coordinates(self) -> bool:
        """Check if violation has valid coordinates."""
        return self.latitude is not None and self.longitude is not None


class ProximityMetrics(BaseModel):
    """
    Metrics for nearby violations within a search radius.

    Attributes:
        nearby_violations: Total count of violations within radius
        nearby_open_violations: Count of open violations within radius
        nearest_violation_distance: Distance to nearest violation in miles
        avg_violation_distance: Average distance to all violations in miles
        violation_types_nearby: List of violation types found nearby
    """

    nearby_violations: int = Field(0, description="Total violations within radius")
    nearby_open_violations: int = Field(0, description="Open violations within radius")
    nearest_violation_distance: Optional[float] = Field(None, description="Distance to nearest in miles")
    avg_violation_distance: Optional[float] = Field(None, description="Average distance in miles")
    violation_types_nearby: List[str] = Field(default_factory=list, description="Types of violations found")


class EnrichedProperty(BaseModel):
    """
    Tax sale property enriched with geographic violation data.

    Combines TaxSaleProperty with ProximityMetrics.
    """

    tda_number: Optional[str] = Field(None, description="Tax Deed Application number")
    sale_date: Optional[str] = Field(None, description="Sale date")
    deed_status: Optional[str] = Field(None, description="Deed status")
    parcel_id: Optional[str] = Field(None, description="County parcel ID")
    longitude: Optional[float] = Field(None, description="WGS84 longitude", ge=-180, le=180)
    latitude: Optional[float] = Field(None, description="WGS84 latitude", ge=-90, le=90)

    nearby_violations: int = Field(0, description="Total violations within radius")
    nearby_open_violations: int = Field(0, description="Open violations within radius")
    nearest_violation_distance: Optional[float] = Field(None, description="Distance to nearest in miles")
    avg_violation_distance: Optional[float] = Field(None, description="Average distance in miles")
    violation_types_nearby: List[str] = Field(default_factory=list, description="Types of violations found")

    def has_coordinates(self) -> bool:
        """Check if property has valid coordinates."""
        return self.latitude is not None and self.longitude is not None

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "tda_number": self.tda_number,
            "sale_date": self.sale_date,
            "deed_status": self.deed_status,
            "parcel_id": self.parcel_id,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "nearby_violations": self.nearby_violations,
            "nearby_open_violations": self.nearby_open_violations,
            "nearest_violation_distance": self.nearest_violation_distance,
            "avg_violation_distance": self.avg_violation_distance,
            "violation_types_nearby": self.violation_types_nearby,
        }

    class Config:
        """Pydantic model configuration."""
        str_strip_whitespace = True
        validate_assignment = True


class TaxSaleProperty(BaseModel):
    """
    Tax sale property record from Orange County ArcGIS API.

    Attributes:
        tda_number: Tax Deed Application number (unique identifier)
        sale_date: Scheduled sale date
        deed_status: Status of the deed (e.g., 'Active Sale', 'Sold')
        parcel_id: County parcel identifier
        longitude: WGS84 longitude coordinate
        latitude: WGS84 latitude coordinate
    """

    tda_number: Optional[str] = Field(None, description="Tax Deed Application number")
    sale_date: Optional[str] = Field(None, description="Sale date (MM/DD/YYYY format)")
    deed_status: Optional[str] = Field(None, description="Deed status")
    parcel_id: Optional[str] = Field(None, description="County parcel ID")
    longitude: Optional[float] = Field(None, description="WGS84 longitude", ge=-180, le=180)
    latitude: Optional[float] = Field(None, description="WGS84 latitude", ge=-90, le=90)

    @field_validator("tda_number")
    @classmethod
    def validate_tda_number(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize TDA number format."""
        if v:
            return v.strip()
        return v

    @field_validator("parcel_id")
    @classmethod
    def validate_parcel_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize parcel ID format."""
        if v:
            return v.strip()
        return v

    def has_coordinates(self) -> bool:
        """Check if property has valid coordinates."""
        return self.latitude is not None and self.longitude is not None

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "tda_number": self.tda_number,
            "sale_date": self.sale_date,
            "deed_status": self.deed_status,
            "parcel_id": self.parcel_id,
            "longitude": self.longitude,
            "latitude": self.latitude,
        }

    class Config:
        """Pydantic model configuration."""
        str_strip_whitespace = True
        validate_assignment = True
