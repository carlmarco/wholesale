"""
Service for deriving priority leads using hybrid/logistic scorers.
"""
from __future__ import annotations

import json
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.wholesaler.db.models import EnrichedSeed
from src.wholesaler.scoring import HybridBucketScorer, LogisticOpportunityScorer


class PriorityLeadService:
    def __init__(self, session: Session):
        self.session = session
        self.hybrid = HybridBucketScorer()
        self.logistic = LogisticOpportunityScorer()

    def get_priority_leads(self, limit: int = 100) -> List[dict]:
        seeds = self._fetch_enriched_seeds(limit * 5)
        leads = []
        for seed in seeds:
            record = seed.enriched_data
            if record is None:
                continue
            if isinstance(record, str):
                try:
                    record = json.loads(record)
                except json.JSONDecodeError:
                    continue

            hybrid_view = self.hybrid.score(record)
            logistic_view = self.logistic.score(record)
            priority_score = 0.6 * hybrid_view["total_score"] + 0.4 * logistic_view["score"]
            priority_flag = (
                hybrid_view["tier"] in ("A", "B") or logistic_view["probability"] >= 0.65
            )
            if not priority_flag:
                continue

            leads.append(
                {
                    "parcel_id_normalized": seed.parcel_id_normalized,
                    "seed_type": seed.seed_type,
                    "priority_score": round(priority_score, 2),
                    "hybrid_score": round(hybrid_view["total_score"], 2),
                    "hybrid_tier": hybrid_view["tier"],
                    "logistic_probability": round(logistic_view["probability"], 3),
                    "violation_count": record.get("violation_count") or record.get("nearby_violations"),
                    "situs_address": record.get("situs_address"),
                    "city": record.get("city"),
                    "raw_enriched": record,
                }
            )

        leads.sort(key=lambda lead: lead["priority_score"], reverse=True)
        return leads[:limit]

    def _fetch_enriched_seeds(self, limit: int):
        query = (
            select(EnrichedSeed)
            .where(EnrichedSeed.enriched_data.isnot(None))
            .order_by(EnrichedSeed.created_at.desc())
            .limit(limit)
        )
        return self.session.execute(query).scalars().all()
