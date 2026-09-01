"""
Lead ranking strategies that operate on enriched seed records.

HybridBucketScorer is an adapter over the asset-agnostic engine in
``src.leadscore``, configured by the real estate profile in
``src.wholesaler.scoring.profiles.real_estate``. The scoring model lives in
that profile; this module only adapts it to the shape existing callers expect.

LogisticOpportunityScorer is still a standalone heuristic model. It has not been
moved onto the engine because it is a single logistic function rather than a
weighted bucket sum - a different shape, not a different configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import math

from src.wholesaler.scoring.profiles import real_estate


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


@dataclass
class BucketScores:
    """The real estate profile's buckets, as callers have always received them."""

    distress: float
    disposition: float
    equity: float
    profitability: float = 0.0


class HybridBucketScorer:
    """
    Weighted bucket scorer for distressed property leads.

    Thin adapter over :class:`src.leadscore.ScoringEngine` configured with the
    real estate profile. The model itself - buckets, weights, bonuses, the
    profitability guardrail and the tier bands - lives in
    ``src.wholesaler.scoring.profiles.real_estate``; scoring a different asset
    class means writing another profile rather than changing this class.

    The return shape is unchanged from the original implementation:
    ``total_score``, ``tier``, ``bucket_scores`` (a :class:`BucketScores`) and
    ``profitability``.
    """

    WEIGHTS = real_estate.WEIGHTS

    def __init__(self, engine=None):
        self.engine = engine or real_estate.build_engine()

    def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score one enriched seed record.

        Args:
            record: Enriched property record.

        Returns:
            Dict with total_score, tier, bucket_scores and profitability.
        """
        result = self.engine.score(record)
        profitability = dict(result.gate.detail)
        # An engine-level implementation detail; callers see the same four keys
        # the original returned.
        profitability.pop("min_profit_threshold", None)

        return {
            "total_score": result.total_score,
            "tier": result.tier,
            "bucket_scores": BucketScores(**result.bucket_scores),
            "profitability": profitability,
        }


class LogisticOpportunityScorer:
    """
    Simple logistic model using heuristically chosen coefficients.

    This is not trained on real labels yet but provides a tunable template for
    future ML calibration while remaining deterministic.
    """

    def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
        violation_count = record.get("violation_count") or record.get("nearby_violations") or 0
        has_tax_sale = 1 if record.get("tax_sale") else 0
        has_foreclosure = 1 if record.get("foreclosure") else 0
        equity_pct = (record.get("property_record") or {}).get("equity_percent") or record.get("equity_percent") or 0
        recent_violation = 1 if record.get("most_recent_violation") else 0

        x = (
            -2.0
            + 0.08 * violation_count
            + 1.8 * has_tax_sale
            + 1.2 * has_foreclosure
            + 0.01 * max(0, equity_pct - 100)
            + 0.5 * recent_violation
        )
        probability = _sigmoid(x)
        score = probability * 100

        return {
            "probability": probability,
            "score": score,
            "tier": self._tier(score),
        }

    @staticmethod
    def _tier(score: float) -> str:
        if score >= 70:
            return "A"
        if score >= 55:
            return "B"
        if score >= 40:
            return "C"
        return "D"
