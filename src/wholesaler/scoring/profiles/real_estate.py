"""
Real estate asset profile.

Everything the scoring engine needs to rank distressed property leads: which
fields carry signal, how each maps to a 0-100 sub-score, what makes a lead worth
acting on, and where the tier boundaries sit.

This reproduces the original HybridBucketScorer exactly. The constants below
were inline magic numbers in that class; naming them here is the point of the
profile - retuning the model is an edit to this file, and scoring a different
asset class is a new file beside it rather than a change to the engine.
"""
from __future__ import annotations

from typing import Any, Mapping

from src.leadscore import Bonus, Bucket, GateResult, Record, ScoringEngine, TierBands
from src.wholesaler.scoring.profitability_scorer import ConservativeProfitabilityBucket

# --- Distress: how much trouble the property is in --------------------------
POINTS_PER_VIOLATION = 10
POINTS_PER_OPEN_VIOLATION = 12
RECENT_VIOLATION_POINTS = 25

# --- Disposition: how likely it is to actually change hands -----------------
TAX_SALE_POINTS = 60
FORECLOSURE_POINTS = 45
CODE_VIOLATION_SEED_POINTS = 25
# Larger judgments signal a more motivated lender, up to a ceiling.
FORECLOSURE_DEBT_POINTS_PER_100K = 5
FORECLOSURE_DEBT_POINTS_MAX = 20

# --- Equity: whether there is room to transact ------------------------------
EQUITY_BANDS = ((200, 50), (150, 35), (120, 20))  # (equity_percent, points)
# The price band this operator actually buys in; outside it, deals stall.
PRICE_BAND = (80_000, 450_000)
IN_PRICE_BAND_POINTS = 30
BELOW_PRICE_BAND_POINTS = 10

# --- Profitability: scaled from the viability gate's projected profit -------
PROFITABLE_BASE_POINTS = 50
PROFIT_SCALE_CEILING = 35_000  # profit above the minimum that earns full marks

WEIGHTS = {
    "distress": 0.55,
    "disposition": 0.15,
    "equity": 0.10,
    "profitability": 0.20,
}

# Applied after the weighted sum: these signals matter beyond their bucket.
TAX_SALE_BONUS = 15
FORECLOSURE_BONUS = 10

TIER_BANDS = TierBands(bands=(("A", 60), ("B", 45), ("C", 32)), fallback="D")

# An unprofitable lead is never worth acting on, however distressed it is: it is
# capped at C, and on a stricter threshold than the viable banding uses, so a
# lead only just clearing C on signal alone drops to D once it fails the gate.
NON_VIABLE_TIER_BANDS = TierBands(bands=(("C", 40),), fallback="D")


def _first_present(record: Record, *keys: str) -> Any:
    """
    Return the first key with a truthy value, checking property_record first.

    Enrichment sometimes nests appraiser fields under ``property_record`` and
    sometimes flattens them onto the record, so both shapes are read.
    """
    nested = record.get("property_record") or {}
    for key in keys:
        value = nested.get(key) or record.get(key)
        if value:
            return value
    return None


def distress_score(record: Record, gate: GateResult) -> float:
    """Score code enforcement pressure on the property."""
    violations = record.get("violation_count") or record.get("nearby_violations") or 0
    open_violations = record.get("open_violations") or record.get("nearby_open_violations") or 0

    score = violations * POINTS_PER_VIOLATION
    score += open_violations * POINTS_PER_OPEN_VIOLATION
    if record.get("most_recent_violation"):
        score += RECENT_VIOLATION_POINTS
    return score


def disposition_score(record: Record, gate: GateResult) -> float:
    """Score how close the property is to a forced sale."""
    score = 0.0
    foreclosure = record.get("foreclosure") or {}

    if record.get("tax_sale"):
        score += TAX_SALE_POINTS

    if foreclosure:
        score += FORECLOSURE_POINTS
        default_amount = foreclosure.get("default_amount")
        if default_amount:
            score += min(
                FORECLOSURE_DEBT_POINTS_MAX,
                default_amount / 100_000 * FORECLOSURE_DEBT_POINTS_PER_100K,
            )

    if record.get("seed_type") == "code_violation":
        score += CODE_VIOLATION_SEED_POINTS

    return score


def equity_score(record: Record, gate: GateResult) -> float:
    """Score the owner's room to sell and the property's price band."""
    score = 0.0

    equity_percent = _first_present(record, "equity_percent")
    if equity_percent:
        for threshold, points in EQUITY_BANDS:
            if equity_percent >= threshold:
                score += points
                break

    market_value = _first_present(record, "total_mkt")
    if market_value:
        low, high = PRICE_BAND
        if low <= market_value <= high:
            score += IN_PRICE_BAND_POINTS
        elif market_value < low:
            score += BELOW_PRICE_BAND_POINTS

    return score


def profitability_score(record: Record, gate: GateResult) -> float:
    """
    Scale the gate's projected profit into a sub-score.

    Reuses the gate's result rather than recomputing the profitability model,
    which is the most expensive part of scoring a record.
    """
    if not gate.viable:
        return 0.0

    minimum = gate.detail.get("min_profit_threshold", 0)
    surplus = max(0.0, gate.detail.get("projected_profit", 0.0) - minimum)
    return PROFITABLE_BASE_POINTS + (surplus / PROFIT_SCALE_CEILING * PROFITABLE_BASE_POINTS)


class ProfitabilityGate:
    """
    Viability rule for property: can this be resold at an acceptable profit?

    Wraps :class:`ConservativeProfitabilityBucket` so the engine sees only a
    viable/not-viable verdict plus the evidence behind it.
    """

    def __init__(self, scorer: ConservativeProfitabilityBucket | None = None) -> None:
        self.scorer = scorer or ConservativeProfitabilityBucket()

    def evaluate(self, record: Record) -> GateResult:
        result = self.scorer.score(record)
        return GateResult(
            viable=result.is_profitable,
            detail={
                "projected_profit": result.projected_profit,
                "is_profitable": result.is_profitable,
                "roi_percent": result.roi_percent,
                "details": result.details,
                "min_profit_threshold": self.scorer.MIN_PROFIT_THRESHOLD,
            },
        )


def build_engine(weights: Mapping[str, float] | None = None) -> ScoringEngine:
    """
    Build the scoring engine for distressed residential property.

    Args:
        weights: Optional override of the bucket weights, which must still sum
            to 1. Useful for retuning without editing this module.

    Returns:
        A configured engine. Its scores match the original HybridBucketScorer.
    """
    resolved = dict(WEIGHTS)
    if weights:
        resolved.update(weights)

    return ScoringEngine(
        buckets=[
            Bucket("distress", resolved["distress"], distress_score),
            Bucket("disposition", resolved["disposition"], disposition_score),
            Bucket("equity", resolved["equity"], equity_score),
            Bucket("profitability", resolved["profitability"], profitability_score),
        ],
        tiers=TIER_BANDS,
        gate=ProfitabilityGate(),
        bonuses=[
            Bonus("tax_sale", TAX_SALE_BONUS, lambda r: bool(r.get("tax_sale"))),
            Bonus("foreclosure", FORECLOSURE_BONUS, lambda r: bool(r.get("foreclosure"))),
        ],
        non_viable_tiers=NON_VIABLE_TIER_BANDS,
    )
