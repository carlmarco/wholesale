"""
ML Models for Property Valuation and Deal Analysis

Provides machine learning models and rule-based heuristics for:
- After Repair Value (ARV) estimation
- Repair cost estimation
- ROI calculation
- Deal analysis
"""
from typing import Dict, Optional, List
from dataclasses import dataclass
import numpy as np


@dataclass
class PropertyFeatures:
    """Property features for ML models."""
    parcel_id: str
    city: str
    zip_code: Optional[str] = None
    property_use: Optional[str] = None
    total_score: float = 0.0
    distress_score: float = 0.0
    value_score: float = 0.0
    location_score: float = 0.0
    has_tax_sale: bool = False
    has_foreclosure: bool = False
    tax_sale_opening_bid: Optional[float] = None
    foreclosure_judgment: Optional[float] = None


@dataclass
class DealAnalysis:
    """Complete deal analysis result."""
    parcel_id: str
    estimated_arv: float
    estimated_repair_costs: float
    max_offer_price: float
    potential_profit: float
    roi_percentage: float
    confidence_level: str  # "high", "medium", "low"
    risk_factors: List[str]
    opportunity_factors: List[str]
    recommendation: str  # "strong_buy", "buy", "hold", "pass"


def estimate_arv(features: PropertyFeatures) -> Dict[str, float]:
    """
    Estimate After Repair Value (ARV) using rule-based heuristics.

    In production, this would use trained ML models with historical sales data.
    For now, we use heuristics based on property characteristics.

    Args:
        features: Property features

    Returns:
        Dictionary with ARV estimate and confidence bounds
    """
    # Base ARV estimation using location and property characteristics
    # These are example values - in production, use real market data

    # City-based base values (Florida markets)
    city_base_values = {
        "Orlando": 250000,
        "Winter Park": 350000,
        "Altamonte Springs": 220000,
        "Kissimmee": 200000,
        "Sanford": 180000,
        "Apopka": 190000,
        "Ocoee": 210000,
        "Clermont": 230000,
    }

    base_arv = city_base_values.get(features.city, 200000)

    # Adjust based on location score (higher score = better location)
    location_multiplier = 1.0 + (features.location_score / 100) * 0.3  # Up to 30% boost

    # Adjust based on property use
    property_use_multipliers = {
        "Single Family": 1.0,
        "Multi Family": 1.2,
        "Condo": 0.85,
        "Townhouse": 0.9,
        "Commercial": 1.5,
        "Land": 0.6,
    }
    use_multiplier = property_use_multipliers.get(features.property_use or "Single Family", 1.0)

    # Calculate estimated ARV
    estimated_arv = base_arv * location_multiplier * use_multiplier

    # Add confidence bounds (+/- 15%)
    confidence_range = estimated_arv * 0.15

    return {
        "estimated_arv": round(estimated_arv, 2),
        "arv_low": round(estimated_arv - confidence_range, 2),
        "arv_high": round(estimated_arv + confidence_range, 2),
        "confidence": 0.85 if features.location_score > 70 else 0.70,
    }


def estimate_repair_costs(features: PropertyFeatures) -> Dict[str, float]:
    """
    Estimate repair costs using distress indicators.

    Higher distress score indicates more severe issues and higher repair costs.

    Args:
        features: Property features

    Returns:
        Dictionary with repair cost estimates
    """
    # Base repair cost multiplier based on distress score
    # Distress score 0-100: 0 = pristine, 100 = severe distress

    distress_ratio = features.distress_score / 100

    # Base repair costs for different distress levels
    if distress_ratio < 0.2:
        # Minor cosmetic repairs
        base_repair = 15000
        repair_level = "cosmetic"
    elif distress_ratio < 0.4:
        # Moderate repairs (flooring, paint, minor updates)
        base_repair = 30000
        repair_level = "moderate"
    elif distress_ratio < 0.6:
        # Significant repairs (kitchen, bathroom, HVAC)
        base_repair = 50000
        repair_level = "significant"
    elif distress_ratio < 0.8:
        # Major repairs (structural, roof, plumbing/electrical)
        base_repair = 75000
        repair_level = "major"
    else:
        # Extensive repairs (gut rehab)
        base_repair = 100000
        repair_level = "extensive"

    # Add foreclosure/tax sale penalty (typically need more work)
    if features.has_foreclosure:
        base_repair *= 1.15
    if features.has_tax_sale:
        base_repair *= 1.10

    # Confidence range (+/- 20%)
    confidence_range = base_repair * 0.20

    return {
        "estimated_repair_cost": round(base_repair, 2),
        "repair_low": round(base_repair - confidence_range, 2),
        "repair_high": round(base_repair + confidence_range, 2),
        "repair_level": repair_level,
        "confidence": 0.75,
    }


def calculate_roi(
    arv: float,
    purchase_price: float,
    repair_costs: float,
    holding_costs: float = 0.0,
    transaction_costs: float = 0.0
) -> Dict[str, float]:
    """
    Calculate Return on Investment (ROI) for a real estate deal.

    Uses the 70% rule and standard wholesaling metrics.

    Args:
        arv: After Repair Value
        purchase_price: Property purchase price
        repair_costs: Estimated repair costs
        holding_costs: Monthly holding costs (taxes, insurance, utilities)
        transaction_costs: Closing costs, realtor fees, etc.

    Returns:
        Dictionary with ROI metrics
    """
    # Total investment
    total_investment = purchase_price + repair_costs + holding_costs + transaction_costs

    # Expected sale price (ARV)
    expected_sale_price = arv

    # Gross profit
    gross_profit = expected_sale_price - total_investment

    # ROI percentage
    roi_percentage = (gross_profit / total_investment) * 100 if total_investment > 0 else 0

    # 70% Rule: Max offer should be 70% of ARV minus repairs
    max_offer_70_rule = (arv * 0.70) - repair_costs

    # Profit if bought at max offer
    profit_at_max_offer = expected_sale_price - max_offer_70_rule - repair_costs

    return {
        "total_investment": round(total_investment, 2),
        "expected_sale_price": round(expected_sale_price, 2),
        "gross_profit": round(gross_profit, 2),
        "roi_percentage": round(roi_percentage, 2),
        "max_offer_70_rule": round(max_offer_70_rule, 2),
        "profit_at_max_offer": round(profit_at_max_offer, 2),
        "meets_70_rule": purchase_price <= max_offer_70_rule,
    }


def get_deal_analysis(features: PropertyFeatures) -> DealAnalysis:
    """
    Perform comprehensive deal analysis.

    Args:
        features: Property features

    Returns:
        Complete deal analysis with recommendations
    """
    # Get ARV estimate
    arv_result = estimate_arv(features)
    estimated_arv = arv_result["estimated_arv"]

    # Get repair cost estimate
    repair_result = estimate_repair_costs(features)
    estimated_repairs = repair_result["estimated_repair_cost"]

    # Determine acquisition price (use tax sale/foreclosure if available)
    if features.tax_sale_opening_bid:
        acquisition_price = features.tax_sale_opening_bid
    elif features.foreclosure_judgment:
        acquisition_price = features.foreclosure_judgment * 0.70  # Typically sell at 70% of judgment
    else:
        # Estimate market value for offer calculation
        acquisition_price = estimated_arv * 0.60  # Conservative 60% of ARV

    # Calculate max offer using 70% rule
    max_offer = (estimated_arv * 0.70) - estimated_repairs

    # Calculate ROI
    roi_result = calculate_roi(
        arv=estimated_arv,
        purchase_price=acquisition_price,
        repair_costs=estimated_repairs,
        holding_costs=6000,  # Assume 6 months at $1k/month
        transaction_costs=estimated_arv * 0.08,  # 8% for realtor + closing
    )

    # Calculate potential profit
    potential_profit = roi_result["gross_profit"]
    roi_percentage = roi_result["roi_percentage"]

    # Determine confidence level
    avg_confidence = (arv_result["confidence"] + repair_result["confidence"]) / 2
    if avg_confidence >= 0.80:
        confidence_level = "high"
    elif avg_confidence >= 0.70:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    # Identify risk factors
    risk_factors = []
    if features.distress_score > 80:
        risk_factors.append("Very high distress - extensive repairs needed")
    if repair_result["repair_level"] in ["major", "extensive"]:
        risk_factors.append(f"Repair level: {repair_result['repair_level']}")
    if not roi_result["meets_70_rule"]:
        risk_factors.append("Purchase price exceeds 70% rule")
    if features.location_score < 50:
        risk_factors.append("Below-average location score")
    if confidence_level == "low":
        risk_factors.append("Low confidence in valuations")

    # Identify opportunity factors
    opportunity_factors = []
    if features.has_tax_sale:
        opportunity_factors.append("Tax sale acquisition opportunity")
    if features.has_foreclosure:
        opportunity_factors.append("Foreclosure acquisition opportunity")
    if features.location_score > 80:
        opportunity_factors.append("Excellent location score")
    if roi_percentage > 50:
        opportunity_factors.append(f"High ROI potential: {roi_percentage:.1f}%")
    if features.value_score > 80:
        opportunity_factors.append("High value score - underpriced property")

    # Make recommendation
    if roi_percentage > 40 and len(risk_factors) <= 2:
        recommendation = "strong_buy"
    elif roi_percentage > 25 and len(risk_factors) <= 3:
        recommendation = "buy"
    elif roi_percentage > 15:
        recommendation = "hold"
    else:
        recommendation = "pass"

    return DealAnalysis(
        parcel_id=features.parcel_id,
        estimated_arv=estimated_arv,
        estimated_repair_costs=estimated_repairs,
        max_offer_price=max_offer,
        potential_profit=potential_profit,
        roi_percentage=roi_percentage,
        confidence_level=confidence_level,
        risk_factors=risk_factors,
        opportunity_factors=opportunity_factors,
        recommendation=recommendation,
    )
