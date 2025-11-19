"""
Properties Router

Endpoints for property queries.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.api.schemas import PropertyDetail
from src.wholesaler.db.models import Property

router = APIRouter(prefix="/api/v1/properties", tags=["properties"])


@router.get("/{parcel_id}", response_model=PropertyDetail)
def get_property_detail(
    parcel_id: str,
    db: Session = Depends(get_db),
):
    """
    Get detailed information for a specific property.

    Args:
        parcel_id: Normalized parcel ID (e.g., "12-34-56-7890-01-001")
        db: Database session

    Returns:
        Detailed property information

    Raises:
        HTTPException: 404 if property not found
    """
    property_obj = (
        db.query(Property)
        .filter(Property.parcel_id_normalized == parcel_id)
        .filter(Property.is_active == True)
        .first()
    )

    if not property_obj:
        raise HTTPException(status_code=404, detail=f"Property not found: {parcel_id}")

    return property_obj
