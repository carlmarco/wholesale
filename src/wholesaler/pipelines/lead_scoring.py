"""
Lead Scoring Algorithm

Scores investment opportunities based on distress signals and property characteristics.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass

from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LeadScore:
    """
    Lead scoring result with breakdown.

    Attributes:
        total_score: Total lead score (0-100)
        distress_score: Distress indicators score
        value_score: Value/equity opportunity score
        location_score: Location/neighborhood score
        urgency_score: Time-sensitive urgency score
        tier: Lead tier (A, B, C, D)
        reasons: List of scoring reasons
    """
    total_score: float
    distress_score: float
    value_score: float
    location_score: float
    urgency_score: float
    tier: str
    reasons: List[str]


class LeadScorer:
    """
    Scores investment leads based on multiple distress and opportunity signals.

    Scoring factors:
    - Tax sale status
    - Foreclosure status
    - Code violations
    - Equity position
    - Property condition indicators
    - Time urgency
    """

    # Tier thresholds
    TIER_A_THRESHOLD = 75  # Hot leads
    TIER_B_THRESHOLD = 60  # Good leads
    TIER_C_THRESHOLD = 40  # Moderate leads
    # Below 40 = Tier D (Low priority)

    def __init__(self):
        """Initialize lead scorer."""
        logger.info("lead_scorer_initialized")

    def score_lead(self, merged_property: Dict) -> LeadScore:
        """
        Calculate lead score for a merged property.

        Args:
            merged_property: Merged property dictionary from deduplication

        Returns:
            LeadScore with detailed breakdown
        """
        reasons = []

        # Calculate component scores
        distress_score = self._calculate_distress_score(merged_property, reasons)
        value_score = self._calculate_value_score(merged_property, reasons)
        location_score = self._calculate_location_score(merged_property, reasons)
        urgency_score = self._calculate_urgency_score(merged_property, reasons)

        # Weighted total score
        total_score = (
            distress_score * 0.35 +
            value_score * 0.30 +
            location_score * 0.20 +
            urgency_score * 0.15
        )

        # Determine tier
        tier = self._determine_tier(total_score)

        result = LeadScore(
            total_score=round(total_score, 2),
            distress_score=round(distress_score, 2),
            value_score=round(value_score, 2),
            location_score=round(location_score, 2),
            urgency_score=round(urgency_score, 2),
            tier=tier,
            reasons=reasons
        )

        logger.debug(
            "lead_scored",
            parcel=merged_property.get('parcel_id_normalized'),
            total_score=result.total_score,
            tier=result.tier
        )

        return result

    def _calculate_distress_score(self, prop: Dict, reasons: List[str]) -> float:
        """
        Calculate distress indicator score (0-100).

        Factors:
        - Tax sale: +40 points
        - Foreclosure: +40 points
        - Code violations: Up to +20 points
        """
        score = 0.0

        # Tax sale indicator
        if 'tax_sale' in prop:
            score += 40
            reasons.append("Property in tax sale")

        # Foreclosure indicator
        if 'foreclosure' in prop:
            score += 40
            foreclosure = prop['foreclosure']

            if foreclosure.get('default_amount'):
                default = foreclosure['default_amount']
                if default > 100000:
                    score += 10
                    reasons.append(f"High default amount: ${default:,.0f}")

            if foreclosure.get('auction_date'):
                score += 5
                reasons.append(f"Auction scheduled: {foreclosure['auction_date']}")

        # Code violations
        if 'enrichment' in prop:
            enrichment = prop['enrichment']
            violations = enrichment.get('nearby_violations', 0)
            open_violations = enrichment.get('nearby_open_violations', 0)

            if violations > 0:
                violation_score = min(20, violations / 10)
                score += violation_score

                if violations >= 20:
                    reasons.append(f"High violation density: {violations} nearby")
                elif violations >= 5:
                    reasons.append(f"Moderate violations: {violations} nearby")

                if open_violations > 0:
                    score += 3
                    reasons.append(f"{open_violations} open violations nearby")

        return min(100, score)

    def _calculate_value_score(self, prop: Dict, reasons: List[str]) -> float:
        """
        Calculate value opportunity score (0-100).

        Factors:
        - High equity percentage
        - Low tax burden
        - Market value vs assessed value discrepancy
        """
        score = 0.0

        if 'property_record' not in prop:
            return 0.0

        record = prop['property_record']

        # Equity opportunity
        equity_pct = record.get('equity_percent')
        if equity_pct:
            if equity_pct > 200:
                score += 40
                reasons.append(f"Excellent equity: {equity_pct:.0f}%")
            elif equity_pct > 150:
                score += 30
                reasons.append(f"Good equity: {equity_pct:.0f}%")
            elif equity_pct > 120:
                score += 20
                reasons.append(f"Fair equity: {equity_pct:.0f}%")

        # Market value check
        total_mkt = record.get('total_mkt')
        if total_mkt:
            if 100000 <= total_mkt <= 400000:
                score += 30
                reasons.append(f"Target price range: ${total_mkt:,.0f}")
            elif total_mkt < 100000:
                score += 20
                reasons.append(f"Low entry price: ${total_mkt:,.0f}")

        # Tax burden
        taxes = record.get('taxes')
        if taxes and total_mkt:
            tax_rate = (taxes / total_mkt) * 100
            if tax_rate < 1.5:
                score += 15
                reasons.append(f"Low tax burden: {tax_rate:.2f}%")

        # Living area
        living_area = record.get('living_area')
        if living_area and living_area > 1000:
            score += 15
            reasons.append(f"Good size: {living_area:,.0f} sqft")

        return min(100, score)

    def _calculate_location_score(self, prop: Dict, reasons: List[str]) -> float:
        """
        Calculate location/neighborhood score (0-100).

        Factors:
        - Violation density in area
        - Distance to nearest violation
        - Neighborhood condition indicators
        """
        score = 50.0  # Neutral baseline

        if 'enrichment' not in prop:
            return score

        enrichment = prop['enrichment']
        violations = enrichment.get('nearby_violations', 0)
        nearest_distance = enrichment.get('nearest_violation_distance')

        # Violation density impact
        if violations == 0:
            score += 30
            reasons.append("Clean neighborhood: no violations nearby")
        elif violations < 5:
            score += 20
            reasons.append("Low distress area")
        elif violations < 20:
            score += 10
        elif violations >= 50:
            score -= 10
            reasons.append("High distress area")

        # Nearest violation distance
        if nearest_distance:
            if nearest_distance > 0.2:
                score += 10
            elif nearest_distance < 0.05:
                score -= 10
                reasons.append(f"Violation very close: {nearest_distance} mi")

        return max(0, min(100, score))

    def _calculate_urgency_score(self, prop: Dict, reasons: List[str]) -> float:
        """
        Calculate time urgency score (0-100).

        Factors:
        - Tax sale date proximity
        - Auction date proximity
        - Open violations
        """
        score = 0.0

        # Tax sale urgency
        if 'tax_sale' in prop:
            tax_sale = prop['tax_sale']
            if tax_sale.get('sale_date'):
                score += 40
                reasons.append(f"Tax sale date: {tax_sale['sale_date']}")

        # Foreclosure auction urgency
        if 'foreclosure' in prop:
            foreclosure = prop['foreclosure']
            if foreclosure.get('auction_date'):
                score += 50
                reasons.append("Foreclosure auction scheduled")

        # Open violations urgency
        if 'enrichment' in prop:
            enrichment = prop['enrichment']
            open_violations = enrichment.get('nearby_open_violations', 0)
            if open_violations > 0:
                score += min(10, open_violations * 2)

        return min(100, score)

    @staticmethod
    def _determine_tier(score: float) -> str:
        """Determine lead tier based on score."""
        if score >= LeadScorer.TIER_A_THRESHOLD:
            return "A"
        elif score >= LeadScorer.TIER_B_THRESHOLD:
            return "B"
        elif score >= LeadScorer.TIER_C_THRESHOLD:
            return "C"
        else:
            return "D"

    def rank_leads(self, scored_leads: List[tuple[Dict, LeadScore]]) -> List[tuple[Dict, LeadScore]]:
        """
        Rank leads by total score (descending).

        Args:
            scored_leads: List of (property, lead_score) tuples

        Returns:
            Sorted list of (property, lead_score) tuples
        """
        ranked = sorted(scored_leads, key=lambda x: x[1].total_score, reverse=True)

        logger.info(
            "leads_ranked",
            total_leads=len(ranked),
            tier_a=sum(1 for _, score in ranked if score.tier == "A"),
            tier_b=sum(1 for _, score in ranked if score.tier == "B"),
            tier_c=sum(1 for _, score in ranked if score.tier == "C"),
            tier_d=sum(1 for _, score in ranked if score.tier == "D")
        )

        return ranked
