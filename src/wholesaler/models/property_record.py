"""
Property Record Data Models

Pydantic models for property records from Orange County Property Appraiser.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class PropertyRecord(BaseModel):
    """
    Property record from Orange County Property Appraiser ArcGIS API.

    Contains parcel information, valuation data, and tax assessments.

    Attributes:
        parcel_number: County parcel identifier
        situs_address: Property street address
        owner_name: Property owner name
        land_mkt: Land market value
        bldg_mkt: Building market value
        xfob_mkt: Extra features market value
        total_mkt: Total market value
        total_assd: Total assessed value
        total_xmpt: Total exempt value
        taxable: Taxable amount
        taxes: Annual tax amount
        exempt_code: Tax exemption code
        property_use: Property use classification
        year_built: Year property was built
        living_area: Living area square footage
        lot_size: Lot size in square feet
        latitude: WGS84 latitude coordinate
        longitude: WGS84 longitude coordinate
    """

    parcel_number: Optional[str] = Field(None, description="Parcel number")
    situs_address: Optional[str] = Field(None, description="Property address")
    owner_name: Optional[str] = Field(None, description="Owner name")
    land_mkt: Optional[float] = Field(None, description="Land market value", ge=0)
    bldg_mkt: Optional[float] = Field(None, description="Building market value", ge=0)
    xfob_mkt: Optional[float] = Field(None, description="Extra features value", ge=0)
    total_mkt: Optional[float] = Field(None, description="Total market value", ge=0)
    total_assd: Optional[float] = Field(None, description="Total assessed value", ge=0)
    total_xmpt: Optional[float] = Field(None, description="Total exempt value", ge=0)
    taxable: Optional[float] = Field(None, description="Taxable amount", ge=0)
    taxes: Optional[float] = Field(None, description="Annual taxes", ge=0)
    exempt_code: Optional[str] = Field(None, description="Exemption code")
    property_use: Optional[str] = Field(None, description="Property use")
    year_built: Optional[int] = Field(None, description="Year built", ge=1800, le=2100)

    @field_validator("year_built", mode="before")
    @classmethod
    def validate_year_built(cls, v):
        """Convert 0 to None for year_built."""
        if v == 0:
            return None
        return v
    living_area: Optional[float] = Field(None, description="Living area sqft", ge=0)
    lot_size: Optional[float] = Field(None, description="Lot size sqft", ge=0)
    latitude: Optional[float] = Field(None, description="Latitude", ge=-90, le=90)
    longitude: Optional[float] = Field(None, description="Longitude", ge=-180, le=180)

    @field_validator("parcel_number")
    @classmethod
    def normalize_parcel_number(cls, v: Optional[str]) -> Optional[str]:
        """Normalize parcel number format."""
        if v:
            return v.strip()
        return v

    @field_validator("situs_address")
    @classmethod
    def normalize_address(cls, v: Optional[str]) -> Optional[str]:
        """Normalize address format."""
        if v:
            return v.strip().upper()
        return v

    def has_coordinates(self) -> bool:
        """Check if property has valid coordinates."""
        return self.latitude is not None and self.longitude is not None

    def calculate_equity_percent(self) -> Optional[float]:
        """
        Calculate equity percentage (market value / assessed value).

        Returns:
            Equity percentage or None if insufficient data
        """
        if self.total_mkt and self.total_assd and self.total_assd > 0:
            return round((self.total_mkt / self.total_assd) * 100, 2)
        return None

    def calculate_tax_rate(self) -> Optional[float]:
        """
        Calculate effective tax rate (taxes / taxable amount).

        Returns:
            Tax rate percentage or None if insufficient data
        """
        if self.taxes and self.taxable and self.taxable > 0:
            return round((self.taxes / self.taxable) * 100, 4)
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "parcel_number": self.parcel_number,
            "situs_address": self.situs_address,
            "owner_name": self.owner_name,
            "land_mkt": self.land_mkt,
            "bldg_mkt": self.bldg_mkt,
            "xfob_mkt": self.xfob_mkt,
            "total_mkt": self.total_mkt,
            "total_assd": self.total_assd,
            "total_xmpt": self.total_xmpt,
            "taxable": self.taxable,
            "taxes": self.taxes,
            "exempt_code": self.exempt_code,
            "property_use": self.property_use,
            "year_built": self.year_built,
            "living_area": self.living_area,
            "lot_size": self.lot_size,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    class Config:
        """Pydantic model configuration."""
        str_strip_whitespace = True
        validate_assignment = True
