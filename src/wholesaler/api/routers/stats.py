"""
Statistics Router

Endpoints for dashboard statistics and aggregations.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.api.schemas import DashboardStats
from src.wholesaler.db.models import LeadScore, Property, TaxSale, Foreclosure

router = APIRouter(prefix="/api/v1/stats", tags=["statistics"])


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
):
    """
    Get dashboard statistics including tier counts and averages.

    Args:
        db: Database session

    Returns:
        Dashboard statistics
    """
    # Total leads
    total_leads = db.query(func.count(LeadScore.id)).scalar() or 0

    # Tier counts
    tier_counts = (
        db.query(LeadScore.tier, func.count(LeadScore.id))
        .group_by(LeadScore.tier)
        .all()
    )

    tier_count_dict = {tier: count for tier, count in tier_counts}
    tier_a_count = tier_count_dict.get("A", 0)
    tier_b_count = tier_count_dict.get("B", 0)
    tier_c_count = tier_count_dict.get("C", 0)
    tier_d_count = tier_count_dict.get("D", 0)

    # Average scores by tier
    avg_scores = (
        db.query(LeadScore.tier, func.avg(LeadScore.total_score))
        .group_by(LeadScore.tier)
        .all()
    )

    avg_score_dict = {tier: float(avg) for tier, avg in avg_scores}
    avg_score_tier_a = avg_score_dict.get("A")
    avg_score_tier_b = avg_score_dict.get("B")
    avg_score_tier_c = avg_score_dict.get("C")
    avg_score_tier_d = avg_score_dict.get("D")

    # Total properties
    total_properties = (
        db.query(func.count(Property.id))
        .filter(Property.is_active == True)
        .scalar() or 0
    )

    # Properties with tax sales
    properties_with_tax_sales = (
        db.query(func.count(func.distinct(TaxSale.parcel_id_normalized)))
        .scalar() or 0
    )

    # Properties with foreclosures
    properties_with_foreclosures = (
        db.query(func.count(func.distinct(Foreclosure.parcel_id_normalized)))
        .scalar() or 0
    )

    # Recent Tier A leads (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_tier_a_count = (
        db.query(func.count(LeadScore.id))
        .filter(
            and_(
                LeadScore.tier == "A",
                LeadScore.scored_at >= seven_days_ago
            )
        )
        .scalar() or 0
    )

    return DashboardStats(
        total_leads=total_leads,
        tier_a_count=tier_a_count,
        tier_b_count=tier_b_count,
        tier_c_count=tier_c_count,
        tier_d_count=tier_d_count,
        avg_score_tier_a=avg_score_tier_a,
        avg_score_tier_b=avg_score_tier_b,
        avg_score_tier_c=avg_score_tier_c,
        avg_score_tier_d=avg_score_tier_d,
        total_properties=total_properties,
        properties_with_tax_sales=properties_with_tax_sales,
        properties_with_foreclosures=properties_with_foreclosures,
        recent_tier_a_count=recent_tier_a_count,
    )
