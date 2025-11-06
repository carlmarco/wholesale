"""
Foreclosure Data Models

Pydantic models for foreclosure records from Orange County.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ForeclosureProperty(BaseModel):
    """
    Foreclosure property record from Orange County ArcGIS API.

    Attributes:
        borrowers_name: Name of borrower(s) in foreclosure
        situs_address: Property street address
        situs_city: Property city
        situs_state: Property state
        situs_zip: Property zip code
        situs_county: Property county
        transfer_date: Date of property transfer
        transfer_amount: Sale amount
        default_amount: Outstanding default balance
        opening_bid: Auction opening bid amount
        recording_date: Date recorded with county
        entered_date: Date entered into system
        auction_date: Scheduled auction date
        trustee_name: Trustee handling foreclosure
        lender_name: Lender/bank name
        lender_phone: Lender contact phone
        property_type: Type of property
        record_type_description: Classification of record
        parcel_number: County parcel identifier
        year: Year of record
        latitude: WGS84 latitude coordinate
        longitude: WGS84 longitude coordinate
    """

    borrowers_name: Optional[str] = Field(None, description="Borrower name(s)")
    situs_address: Optional[str] = Field(None, description="Property address")
    situs_city: Optional[str] = Field(None, description="City")
    situs_state: Optional[str] = Field(None, description="State")
    situs_zip: Optional[str] = Field(None, description="Zip code")
    situs_county: Optional[str] = Field(None, description="County")
    transfer_date: Optional[str] = Field(None, description="Transfer date")
    transfer_amount: Optional[float] = Field(None, description="Transfer amount")
    default_amount: Optional[float] = Field(None, description="Default amount")
    opening_bid: Optional[float] = Field(None, description="Opening bid")
    recording_date: Optional[str] = Field(None, description="Recording date")
    entered_date: Optional[str] = Field(None, description="Entry date")
    auction_date: Optional[str] = Field(None, description="Auction date")
    trustee_name: Optional[str] = Field(None, description="Trustee name")
    lender_name: Optional[str] = Field(None, description="Lender name")
    lender_phone: Optional[str] = Field(None, description="Lender phone")
    property_type: Optional[str] = Field(None, description="Property type")
    record_type_description: Optional[str] = Field(None, description="Record type")
    parcel_number: Optional[str] = Field(None, description="Parcel number")
    year: Optional[int] = Field(None, description="Record year")
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

    def has_auction_date(self) -> bool:
        """Check if property has scheduled auction."""
        return self.auction_date is not None

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "borrowers_name": self.borrowers_name,
            "situs_address": self.situs_address,
            "situs_city": self.situs_city,
            "situs_state": self.situs_state,
            "situs_zip": self.situs_zip,
            "situs_county": self.situs_county,
            "transfer_date": self.transfer_date,
            "transfer_amount": self.transfer_amount,
            "default_amount": self.default_amount,
            "opening_bid": self.opening_bid,
            "recording_date": self.recording_date,
            "entered_date": self.entered_date,
            "auction_date": self.auction_date,
            "trustee_name": self.trustee_name,
            "lender_name": self.lender_name,
            "lender_phone": self.lender_phone,
            "property_type": self.property_type,
            "record_type_description": self.record_type_description,
            "parcel_number": self.parcel_number,
            "year": self.year,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    class Config:
        """Pydantic model configuration."""
        str_strip_whitespace = True
        validate_assignment = True
