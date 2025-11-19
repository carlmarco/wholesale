"""
Lead ranking strategies that operate on enriched seed records.

These scorers are independent of the legacy lead scoring pipeline and are
designed to work directly with enriched seed dictionaries produced by the
new dual-seed ingestion flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import math


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


@dataclass
class BucketScores:
    distress: float
    disposition: float
    equity: float
    profitability: float = 0.0

    def total(self, weights: Dict[str, float]) -> float:
        return (
            self.distress * weights.get("distress", 0)
            + self.disposition * weights.get("disposition", 0)
            + self.equity * weights.get("equity", 0)
            + self.profitability * weights.get("profitability", 0)
        )


class HybridBucketScorer:
    """
    Weighted bucket scorer.

    - Distress bucket emphasises code violations and recency.
    - Disposition bucket emphasises tax sale / foreclosure signals but does not gate scoring.
    - Equity bucket measures ability to transact (positive equity, price band).
    - Profitability bucket (NEW) measures projected profit margin.

    Updated to allow code violations to independently create Tier B/C leads.
    """

    # Adjusted weights to include profitability (total 1.0)
    # Distress: 0.55, Disposition: 0.15, Equity: 0.10, Profitability: 0.20
    WEIGHTS = {"distress": 0.55, "disposition": 0.15, "equity": 0.10, "profitability": 0.20}

    def __init__(self):
        from src.wholesaler.scoring.profitability_scorer import ConservativeProfitabilityBucket
        self.profitability_scorer = ConservativeProfitabilityBucket()

    def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
        buckets = self._bucket_scores(record)
        total = buckets.total(self.WEIGHTS)
        if record.get("tax_sale"):
            total += 15
        if record.get("foreclosure"):
            total += 10
        total = _clamp(total)
        
        # Get detailed profitability result for metadata
        prof_result = self.profitability_scorer.score(record)
        
        tier = self._tier(total, prof_result.is_profitable)
        
        return {
            "total_score": total,
            "tier": tier,
            "bucket_scores": buckets,
            "profitability": {
                "projected_profit": prof_result.projected_profit,
                "is_profitable": prof_result.is_profitable,
                "roi_percent": prof_result.roi_percent,
                "details": prof_result.details
            }
        }

    def _bucket_scores(self, record: Dict[str, Any]) -> BucketScores:
        violation_count = record.get("violation_count") or record.get("nearby_violations") or 0
        open_violations = record.get("open_violations") or record.get("nearby_open_violations") or 0
        most_recent = record.get("most_recent_violation")

        # Increased multipliers to allow violations to create higher-tier leads
        distress = violation_count * 10
        distress += open_violations * 12
        if most_recent:
            distress += 25  # recency boost (increased from 20)
        distress = _clamp(distress, 0, 100)

        disposition = 0.0
        seed_type = record.get("seed_type")
        tax_sale = record.get("tax_sale") or {}
        foreclosure = record.get("foreclosure") or {}

        if tax_sale:
            disposition += 60
        if foreclosure:
            disposition += 45
            if foreclosure.get("default_amount"):
                disposition += min(20, foreclosure["default_amount"] / 100000 * 5)
        if seed_type == "code_violation":
            disposition += 25  # increased to allow code violations to compete
        disposition = _clamp(disposition, 0, 100)

        property_record = record.get("property_record") or {}
        equity_pct = property_record.get("equity_percent") or record.get("equity_percent")
        total_mkt = property_record.get("total_mkt") or record.get("total_mkt")

        equity = 0.0
        if equity_pct:
            if equity_pct >= 200:
                equity += 50
            elif equity_pct >= 150:
                equity += 35
            elif equity_pct >= 120:
                equity += 20

        if total_mkt:
            if 80000 <= total_mkt <= 450000:
                equity += 30
            elif total_mkt < 80000:
                equity += 10
        equity = _clamp(equity, 0, 100)
        
        # Profitability Bucket
        prof_result = self.profitability_scorer.score(record)
        profitability = 0.0
        if prof_result.is_profitable:
            # Scale score based on profit amount (15k -> 50, 50k -> 100)
            profit_surplus = max(0, prof_result.projected_profit - 15000)
            profitability = 50 + (profit_surplus / 35000 * 50)
        else:
            # Penalize unprofitable deals
            profitability = 0.0
            
        profitability = _clamp(profitability, 0, 100)

        return BucketScores(
            distress=distress, 
            disposition=disposition, 
            equity=equity,
            profitability=profitability
        )

    @staticmethod
    def _tier(score: float, is_profitable: bool = True) -> str:
        # Guardrail: If not profitable, cannot be Tier A or B
        if not is_profitable:
            if score >= 40:
                return "C"
            return "D"
            
        # Adjusted thresholds to allow code violations to reach higher tiers
        if score >= 60:
            return "A"
        if score >= 45:
            return "B"
        if score >= 32:
            return "C"
        return "D"


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
