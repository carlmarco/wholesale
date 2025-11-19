"""
Deal Analysis Router

Endpoints for ML-powered deal analysis and valuations.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.api.cache import cache_result
from src.wholesaler.db.models import LeadScore, Property, TaxSale, Foreclosure
from src.wholesaler.ml.models import (
    PropertyFeatures,
    get_deal_analysis,
    estimate_arv,
    estimate_repair_costs,
    calculate_roi,
)
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


class DealAnalysisResponse(BaseModel):
    """Deal analysis response model."""
    parcel_id: str
    estimated_arv: float
    estimated_repair_costs: float
    max_offer_price: float
    potential_profit: float
    roi_percentage: float
    confidence_level: str
    risk_factors: List[str]
    opportunity_factors: List[str]
    recommendation: str


class ARVResponse(BaseModel):
    """ARV estimation response model."""
    parcel_id: str
    estimated_arv: float
    arv_low: float
    arv_high: float
    confidence: float


class RepairCostResponse(BaseModel):
    """Repair cost estimation response model."""
    parcel_id: str
    estimated_repair_cost: float
    repair_low: float
    repair_high: float
    repair_level: str
    confidence: float


@router.get("/{parcel_id}", response_model=DealAnalysisResponse)
@cache_result("analysis", ttl=600)  # Cache for 10 minutes
async def get_property_analysis(
    parcel_id: str,
    db: Session = Depends(get_db),
):
    """
    Get comprehensive deal analysis for a property.

    Args:
        parcel_id: Normalized parcel ID
        db: Database session

    Returns:
        Complete deal analysis with ML-powered estimates

    Raises:
        HTTPException: 404 if property not found
    """
    # Get lead score and property data
    lead = (
        db.query(LeadScore)
        .join(Property)
        .filter(LeadScore.parcel_id_normalized == parcel_id)
        .first()
    )

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead not found: {parcel_id}")

    # Get tax sale info
    tax_sale = (
        db.query(TaxSale)
        .filter(TaxSale.parcel_id_normalized == parcel_id)
        .first()
    )

    # Get foreclosure info
    foreclosure = (
        db.query(Foreclosure)
        .filter(Foreclosure.parcel_id_normalized == parcel_id)
        .first()
    )

    # Build property features
    features = PropertyFeatures(
        parcel_id=parcel_id,
        city=lead.property.city or "Orlando",
        zip_code=lead.property.zip_code,
        property_use=lead.property.foreclosure.property_type if lead.property.foreclosure else "Single Family",
        total_score=float(lead.total_score or 0.0),
        distress_score=float(lead.distress_score or 0.0),
        value_score=float(lead.value_score or 0.0),
        location_score=float(lead.location_score or 0.0),
        has_tax_sale=tax_sale is not None,
        has_foreclosure=foreclosure is not None,
        tax_sale_opening_bid=float(tax_sale.opening_bid) if tax_sale and tax_sale.opening_bid else None,
        foreclosure_judgment=float(foreclosure.default_amount) if foreclosure and foreclosure.default_amount else None,
    )

    # Get ML analysis
    analysis = get_deal_analysis(features)

    return DealAnalysisResponse(
        parcel_id=analysis.parcel_id,
        estimated_arv=analysis.estimated_arv,
        estimated_repair_costs=analysis.estimated_repair_costs,
        max_offer_price=analysis.max_offer_price,
        potential_profit=analysis.potential_profit,
        roi_percentage=analysis.roi_percentage,
        confidence_level=analysis.confidence_level,
        risk_factors=analysis.risk_factors,
        opportunity_factors=analysis.opportunity_factors,
        recommendation=analysis.recommendation,
    )


@router.get("/{parcel_id}/arv", response_model=ARVResponse)
@cache_result("arv", ttl=600)
async def get_arv_estimate(
    parcel_id: str,
    db: Session = Depends(get_db),
):
    """
    Get After Repair Value (ARV) estimate for a property.

    Args:
        parcel_id: Normalized parcel ID
        db: Database session

    Returns:
        ARV estimation with confidence bounds
    """
    lead = (
        db.query(LeadScore)
        .join(Property)
        .filter(LeadScore.parcel_id_normalized == parcel_id)
        .first()
    )

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead not found: {parcel_id}")

    features = PropertyFeatures(
        parcel_id=parcel_id,
        city=lead.property.city or "Orlando",
        zip_code=lead.property.zip_code,
        property_use=lead.property.foreclosure.property_type if lead.property.foreclosure else "Single Family",
        location_score=float(lead.location_score or 0.0),
    )

    result = estimate_arv(features)

    return ARVResponse(
        parcel_id=parcel_id,
        estimated_arv=result["estimated_arv"],
        arv_low=result["arv_low"],
        arv_high=result["arv_high"],
        confidence=result["confidence"],
    )


@router.get("/{parcel_id}/repair-costs", response_model=RepairCostResponse)
@cache_result("repair_costs", ttl=600)
async def get_repair_cost_estimate(
    parcel_id: str,
    db: Session = Depends(get_db),
):
    """
    Get repair cost estimate for a property.

    Args:
        parcel_id: Normalized parcel ID
        db: Database session

    Returns:
        Repair cost estimation with level classification
    """
    lead = (
        db.query(LeadScore)
        .join(Property)
        .filter(LeadScore.parcel_id_normalized == parcel_id)
        .first()
    )

    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead not found: {parcel_id}")

    # Check for tax sale and foreclosure
    has_tax_sale = db.query(TaxSale).filter(
        TaxSale.parcel_id_normalized == parcel_id
    ).first() is not None

    has_foreclosure = db.query(Foreclosure).filter(
        Foreclosure.parcel_id_normalized == parcel_id
    ).first() is not None

    features = PropertyFeatures(
        parcel_id=parcel_id,
        city=lead.property.city or "Orlando",
        distress_score=float(lead.distress_score or 0.0),
        has_tax_sale=has_tax_sale,
        has_foreclosure=has_foreclosure,
    )

    result = estimate_repair_costs(features)

    return RepairCostResponse(
        parcel_id=parcel_id,
        estimated_repair_cost=result["estimated_repair_cost"],
        repair_low=result["repair_low"],
        repair_high=result["repair_high"],
        repair_level=result["repair_level"],
        confidence=result["confidence"],
    )
