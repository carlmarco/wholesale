"""
Leads Router

Endpoints for lead score queries and filtering.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.api.schemas import LeadScoreListItem, LeadScoreDetail, LeadScoreHistory
from src.wholesaler.db.models import LeadScore, Property, TaxSale, Foreclosure
from src.wholesaler.db.models import LeadScoreHistory as LeadScoreHistoryModel

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


@router.get("/", response_model=List[LeadScoreListItem])
def list_leads(
    tier: str = Query(None, pattern="^[A-D]$", description="Filter by tier (A, B, C, D)"),
    min_score: float = Query(None, ge=0, le=100, description="Minimum total score"),
    max_score: float = Query(None, ge=0, le=100, description="Maximum total score"),
    city: str = Query(None, description="Filter by city"),
    zip_code: str = Query(None, description="Filter by ZIP code"),
    limit: int = Query(100, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query("total_score", pattern="^(total_score|scored_at|situs_address)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    """
    List lead scores with optional filtering and pagination.

    Args:
        tier: Filter by tier (A, B, C, D)
        min_score: Minimum total score
        max_score: Maximum total score
        city: Filter by city
        zip_code: Filter by ZIP code
        limit: Number of results (max 1000)
        offset: Pagination offset
        sort_by: Sort field (total_score, scored_at, situs_address)
        sort_order: Sort order (asc, desc)
        db: Database session

    Returns:
        List of lead scores with basic property info
    """
    # Build query with eager loading
    query = db.query(LeadScore).join(Property).options(joinedload(LeadScore.property))

    # Apply filters
    if tier:
        query = query.filter(LeadScore.tier == tier)

    if min_score is not None:
        query = query.filter(LeadScore.total_score >= min_score)

    if max_score is not None:
        query = query.filter(LeadScore.total_score <= max_score)

    if city:
        query = query.filter(Property.city.ilike(f"%{city}%"))

    if zip_code:
        query = query.filter(Property.zip_code == zip_code)

    # Apply sorting
    if sort_by == "total_score":
        sort_column = LeadScore.total_score
    elif sort_by == "scored_at":
        sort_column = LeadScore.scored_at
    elif sort_by == "situs_address":
        sort_column = Property.situs_address
    else:
        sort_column = LeadScore.total_score

    if sort_order == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    query = query.order_by(sort_column)

    # Apply pagination
    leads = query.offset(offset).limit(limit).all()

    return leads


@router.get("/{parcel_id}", response_model=LeadScoreDetail)
def get_lead_detail(
    parcel_id: str,
    db: Session = Depends(get_db),
):
    """
    Get detailed information for a specific lead.

    Args:
        parcel_id: Normalized parcel ID (e.g., "12-34-56-7890-01-001")
        db: Database session

    Returns:
        Detailed lead score with property, tax sale, and foreclosure info

    Raises:
        HTTPException: 404 if lead not found
    """
    # Query with eager loading of related data
    lead = (
        db.query(LeadScore)
        .join(Property)
        .outerjoin(TaxSale)
        .outerjoin(Foreclosure)
        .options(
            joinedload(LeadScore.property),
            joinedload(LeadScore.property).joinedload(Property.tax_sale),
            joinedload(LeadScore.property).joinedload(Property.foreclosure),
        )
        .filter(LeadScore.parcel_id_normalized == parcel_id)
        .first()
    )

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead not found: {parcel_id}")

    # Build response with nested relationships
    response = LeadScoreDetail(
        parcel_id_normalized=lead.parcel_id_normalized,
        distress_score=lead.distress_score,
        value_score=lead.value_score,
        location_score=lead.location_score,
        urgency_score=lead.urgency_score,
        total_score=lead.total_score,
        tier=lead.tier,
        scoring_reasons=lead.scoring_reasons or [],
        property=lead.property,
        tax_sale=lead.property.tax_sale if lead.property.tax_sale else None,
        foreclosure=lead.property.foreclosure if lead.property.foreclosure else None,
        scored_at=lead.scored_at,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )

    return response


@router.get("/{parcel_id}/history", response_model=List[LeadScoreHistory])
def get_lead_history(
    parcel_id: str,
    limit: int = Query(30, ge=1, le=100, description="Number of historical snapshots"),
    db: Session = Depends(get_db),
):
    """
    Get historical score snapshots for a lead.

    Args:
        parcel_id: Normalized parcel ID
        limit: Number of historical records to return (max 100)
        db: Database session

    Returns:
        List of historical lead score snapshots, ordered by date (newest first)

    Raises:
        HTTPException: 404 if lead not found
    """
    # First check if lead exists
    lead = db.query(LeadScore).filter(LeadScore.parcel_id_normalized == parcel_id).first()

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead not found: {parcel_id}")

    # Query history
    history = (
        db.query(LeadScoreHistoryModel)
        .filter(LeadScoreHistoryModel.lead_score_id == lead.id)
        .order_by(LeadScoreHistoryModel.snapshot_date.desc())
        .limit(limit)
        .all()
    )

    return history
