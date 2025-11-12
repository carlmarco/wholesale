"""
Unified enrichment pipeline for all seed sources.
"""
from __future__ import annotations

from typing import List, Dict, Any
import pandas as pd

from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.data_ingestion.enrichment import PropertyEnricher  # legacy module still hosts the enricher
from src.wholesaler.scrapers.code_violation_scraper import CodeViolationScraper
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class UnifiedEnrichmentPipeline:
    """
    Enriches seed records with violation metrics and metadata.

    At present this pipeline reuses the legacy PropertyEnricher for code-violation metrics
    while aggregating additional context for non-tax-sale seeds.
    """

    def __init__(self, violation_df: pd.DataFrame | None = None):
        if violation_df is None:
            violation_df = CodeViolationScraper().fetch_violations(limit=50000)
        self.enricher = PropertyEnricher(violation_df)
        self.standardizer = AddressStandardizer()

    def run(self, seeds: List[SeedRecord]) -> List[Dict[str, Any]]:
        tax_sale_payloads = [
            seed.source_payload for seed in seeds if seed.seed_type == "tax_sale"
        ]
        tax_enriched = self.enricher.enrich_properties(tax_sale_payloads)
        enriched_records: List[Dict[str, Any]] = []

        # Map parcel -> violation summary for quick lookup
        violation_summary = self._summarize_violations()

        for seed in seeds:
            normalized_parcel = self.standardizer.normalize_parcel_id(seed.parcel_id) or ""
            base_record: Dict[str, Any] = {
                "parcel_id": seed.parcel_id,
                "parcel_id_normalized": normalized_parcel,
                "seed_type": seed.seed_type,
                "ingested_at": seed.ingested_at.isoformat(),
            }

            if seed.seed_type == "tax_sale":
                # Look up enriched tax record by parcel
                match = next(
                    (rec for rec in tax_enriched if rec.get("parcel_id_normalized") == normalized_parcel),
                    None,
                )
                if match:
                    merged = {**base_record, **match}
                    enriched_records.append(merged)
                    continue

            # For non-tax seeds (or if enrichment missing) create a lightweight record
            violations = violation_summary.get(normalized_parcel, {})
            source_payload = seed.source_payload
            base_record.update(
                {
                    "violation_count": violations.get("count", 0),
                    "most_recent_violation": violations.get("most_recent"),
                    "violation_types": violations.get("types", []),
                    "raw_source": source_payload,
                }
            )
            enriched_records.append(base_record)

        logger.info("enriched_records_built", count=len(enriched_records))
        return enriched_records

    def _summarize_violations(self) -> Dict[str, Dict[str, Any]]:
        """Build a quick lookup for violation counts by parcel."""
        df = self.enricher.violations_df
        if df.empty:
            return {}

        grouped = (
            df.groupby("parcel_id_normalized")
            .agg(
                count=("parcel_id_normalized", "size"),
                most_recent=("casedt", "max"),
                types=("case_type", lambda vals: sorted(set(filter(None, vals)))),
            )
            .reset_index()
        )
        summary = {}
        for _, row in grouped.iterrows():
            summary[row["parcel_id_normalized"]] = {
                "count": int(row["count"]),
                "most_recent": row["most_recent"].strftime("%Y-%m-%d") if pd.notna(row["most_recent"]) else None,
                "types": row["types"],
            }
        return summary
