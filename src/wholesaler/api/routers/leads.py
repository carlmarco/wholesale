"""
Leads Router

Endpoints for lead score queries and filtering.
"""
from typing import List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.api.schemas import LeadScoreListItem, LeadScoreDetail, LeadScoreHistory, PriorityLead
from src.wholesaler.db.models import LeadScore, Property, TaxSale, Foreclosure, EnrichedSeed
from src.wholesaler.db.models import LeadScoreHistory as LeadScoreHistoryModel
from src.wholesaler.services.priority_leads import PriorityLeadService
from src.wholesaler.scoring import HybridBucketScorer, LogisticOpportunityScorer

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
    view: str = Query("legacy", pattern="^(legacy|hybrid)$", description="Include ML scoring fields"),
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

    if view == "hybrid":
        _attach_hybrid_scores(leads, db)

    return leads


@router.get("/priority", response_model=List[PriorityLead])
def list_priority_leads(
    limit: int = Query(50, ge=1, le=500, description="Number of priority leads to return"),
    db: Session = Depends(get_db),
):
    """
    List priority leads derived from hybrid/logistic scoring.
    """
    service = PriorityLeadService(db)
    return service.get_priority_leads(limit=limit)


def _attach_hybrid_scores(leads: List[LeadScore], db: Session):
    if not leads:
        return

    parcel_ids = [lead.parcel_id_normalized for lead in leads]
    seed_query = (
        select(EnrichedSeed)
        .where(EnrichedSeed.parcel_id_normalized.in_(parcel_ids))
    )
    seed_rows = db.execute(seed_query).scalars().all()
    seed_map = {}
    for seed in seed_rows:
        if seed.enriched_data is None:
            continue
        record = seed.enriched_data
        if isinstance(record, str):
            try:
                record = json.loads(record)
            except json.JSONDecodeError:
                continue
        seed_map.setdefault(seed.parcel_id_normalized, record)

    hybrid = HybridBucketScorer()
    logistic = LogisticOpportunityScorer()

    for lead in leads:
        record = seed_map.get(lead.parcel_id_normalized)
        if record is None:
            record = _build_feature_dict_from_lead(lead)
        if not record:
            continue
        hybrid_view = hybrid.score(record)
        logistic_view = logistic.score(record)
        priority_score = 0.6 * hybrid_view["total_score"] + 0.4 * logistic_view["score"]
        
        setattr(lead, "hybrid_score", round(hybrid_view["total_score"], 2))
        setattr(lead, "hybrid_tier", hybrid_view["tier"])
        setattr(lead, "logistic_probability", round(logistic_view["probability"], 3))
        setattr(lead, "priority_score", round(priority_score, 2))
        
        # Phase 3.6/3.7
        # Extract profitability from hybrid result (it's now integrated)
        if "profitability" in hybrid_view:
            prof_data = hybrid_view["profitability"]
            setattr(lead, "profitability_score", hybrid_view["bucket_scores"].profitability)
            # We don't have full details here unless we re-run profitability scorer or it's in hybrid_view
            # hybrid_view["profitability"] has details!
            
        # ML Risk (Placeholder until batch pipeline populates DB)
        # If DB has values, they will be loaded automatically.
        # If we want to compute on the fly for 'hybrid' view:
        # We would need to instantiate CompositeRiskScorer here.
        # For now, let's rely on what's in the DB or what HybridScorer provides.
        pass


def _build_feature_dict_from_lead(lead: LeadScore) -> Optional[dict]:
    prop = lead.property
    if not prop:
        return None
    record = {
        "seed_type": getattr(prop, "seed_type", None),
    }
    if prop.tax_sale:
        record["tax_sale"] = {
            "sale_date": prop.tax_sale.sale_date,
            "deed_status": prop.tax_sale.deed_status,
        }
    if prop.foreclosure:
        record["foreclosure"] = {
            "auction_date": prop.foreclosure.auction_date,
            "default_amount": float(prop.foreclosure.default_amount) if prop.foreclosure.default_amount else None,
        }
    if prop.property_record:
        record["property_record"] = {
            "total_mkt": float(prop.property_record.total_mkt) if prop.property_record.total_mkt else None,
            "equity_percent": float(prop.property_record.equity_percent) if prop.property_record.equity_percent else None,
        }
    # approximate violation count using distress score
    record["violation_count"] = lead.distress_score / 5 if lead.distress_score else 0
    return record


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
    try:
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
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error querying lead detail for {parcel_id}: {str(e)}")
        # Check for common DB errors
        if "column" in str(e) and "does not exist" in str(e):
            raise HTTPException(
                status_code=500, 
                detail="Database schema mismatch. Please run 'make db-upgrade' to apply migrations."
            )
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead not found: {parcel_id}")

    # Build response with nested relationships
    if not lead.property:
        raise HTTPException(status_code=404, detail="Property record missing for lead")

    try:
        response = LeadScoreDetail(
            parcel_id_normalized=lead.parcel_id_normalized,
            distress_score=float(lead.distress_score or 0.0),
            value_score=float(lead.value_score or 0.0),
            location_score=float(lead.location_score or 0.0),
            urgency_score=float(lead.urgency_score or 0.0),
            total_score=float(lead.total_score or 0.0),
            tier=lead.tier,
            scoring_reasons=lead.reasons or [],
            property=_serialize_property_detail(lead.property),
            tax_sale=_serialize_tax_sale(lead.property.tax_sale),
            foreclosure=_serialize_foreclosure(lead.property.foreclosure),
            scored_at=lead.scored_at,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            # Phase 3.6/3.7
            profitability_score=float(lead.profitability_score) if lead.profitability_score is not None else None,
            profitability_details=lead.profitability_details,
            ml_risk_score=float(lead.ml_risk_score) if lead.ml_risk_score is not None else None,
            ml_risk_tier=lead.ml_risk_tier,
            ml_cluster_id=lead.ml_cluster_id,
            ml_anomaly_score=float(lead.ml_anomaly_score) if lead.ml_anomaly_score is not None else None,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error serializing lead detail for {parcel_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Serialization Error: {str(e)}")

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


def _serialize_property_detail(property_obj: Property) -> dict:
    return {
        "parcel_id_normalized": property_obj.parcel_id_normalized,
        "parcel_id_original": property_obj.parcel_id_original,
        "situs_address": property_obj.situs_address,
        "city": property_obj.city,
        "state": property_obj.state,
        "zip_code": property_obj.zip_code,
        "latitude": float(property_obj.latitude) if property_obj.latitude is not None else None,
        "longitude": float(property_obj.longitude) if property_obj.longitude is not None else None,
        "seed_type": property_obj.seed_type,
        "is_active": property_obj.is_active,
        "created_at": property_obj.created_at,
        "updated_at": property_obj.updated_at,
    }


def _serialize_tax_sale(tax_sale: Optional[TaxSale]) -> Optional[dict]:
    if not tax_sale:
        return None
    return {
        "tda_number": tax_sale.tda_number,
        "sale_date": tax_sale.sale_date,
        "deed_status": tax_sale.deed_status,
        "latitude": float(tax_sale.latitude) if tax_sale.latitude is not None else None,
        "longitude": float(tax_sale.longitude) if tax_sale.longitude is not None else None,
    }


def _serialize_foreclosure(foreclosure: Optional[Foreclosure]) -> Optional[dict]:
    if not foreclosure:
        return None
    return {
        "borrowers_name": foreclosure.borrowers_name,
        "situs_address": foreclosure.situs_address,
        "default_amount": float(foreclosure.default_amount) if foreclosure.default_amount is not None else None,
        "opening_bid": float(foreclosure.opening_bid) if foreclosure.opening_bid is not None else None,
        "auction_date": foreclosure.auction_date,
        "lender_name": foreclosure.lender_name,
        "property_type": foreclosure.property_type,
        "latitude": float(foreclosure.latitude) if foreclosure.latitude is not None else None,
        "longitude": float(foreclosure.longitude) if foreclosure.longitude is not None else None,
    }
