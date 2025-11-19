"""
Unified enrichment pipeline for all seed sources.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Union
import pandas as pd
from pydantic import ValidationError

from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.enrichment.property_enricher import PropertyEnricher
from src.wholesaler.scrapers.code_violation_scraper import CodeViolationScraper
from src.wholesaler.enrichers.geo_enricher import GeoPropertyEnricher
from src.wholesaler.models.property import TaxSaleProperty
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class UnifiedEnrichmentPipeline:
    """
    Enriches seed records with violation metrics and metadata.

    At present this pipeline reuses the legacy PropertyEnricher for code-violation metrics
    while aggregating additional context for non-tax-sale seeds.
    """

    def __init__(
        self,
        violation_df: Optional[Union[pd.DataFrame, List[Dict]]] = None,
        enable_geo: bool = False,
        geo_csv_path: Optional[str] = None,
        geo_radius_miles: Optional[float] = None,
    ):
        if violation_df is None:
            violation_df = CodeViolationScraper().fetch_violations(limit=50000)
        self.enricher = PropertyEnricher(violation_df)
        self.standardizer = AddressStandardizer()
        self.geo_enricher = GeoPropertyEnricher(
            code_enforcement_csv_path=geo_csv_path,
            radius_miles=geo_radius_miles
        ) if enable_geo else None

    def run(self, seeds: List[SeedRecord]) -> List[Dict[str, Any]]:
        tax_sale_payloads = [
            seed.source_payload for seed in seeds if seed.seed_type == "tax_sale"
        ]
        tax_enriched = self.enricher.enrich_properties(tax_sale_payloads)
        tax_enriched_map = {
            rec.get("parcel_id_normalized"): rec
            for rec in tax_enriched
            if rec.get("parcel_id_normalized")
        }
        geo_map = self._geo_metrics_for_tax_sales(tax_sale_payloads) if self.geo_enricher else {}
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
                match = tax_enriched_map.get(normalized_parcel)
                geo_metrics = geo_map.get(normalized_parcel)
                if match or geo_metrics:
                    merged = {**base_record}
                    if match:
                        merged.update(match)
                    if geo_metrics:
                        merged.update(self._format_geo_metrics(geo_metrics))
                    enriched_records.append(merged)
                    continue

            # For non-tax seeds (or if enrichment missing) create a lightweight record
            violations = violation_summary.get(normalized_parcel, {})
            source_payload = seed.source_payload

            # For code_violation seeds, the violation IS the seed itself
            violation_count = violations.get("count", 0)
            most_recent = violations.get("most_recent")
            violation_types = violations.get("types", [])

            if seed.seed_type == "code_violation" and source_payload:
                # This seed represents a violation, so count it
                violation_count = max(1, violation_count)  # At least 1 (the seed itself)

                # Extract case date as most recent if available
                case_date = source_payload.get("casedt")
                if case_date:
                    # If already have a most_recent, keep the newer one
                    if isinstance(case_date, str):
                        case_date = case_date.split('T')[0]
                    if not most_recent or (case_date and case_date > str(most_recent)):
                        most_recent = case_date

                # Add case type
                case_type = source_payload.get("casetype") or source_payload.get("case_type")
                if case_type and case_type not in violation_types:
                    violation_types = list(violation_types) + [case_type]

                # Track if it's open
                case_status = source_payload.get("caseinfostatus")
                open_violations = violations.get("open_count", 0)
                if case_status and case_status.lower() == "open":
                    open_violations = max(1, open_violations)
            else:
                open_violations = violations.get("open_count", 0)

            base_record.update(
                {
                    "violation_count": violation_count,
                    "most_recent_violation": most_recent,
                    "violation_types": violation_types,
                    "nearby_open_violations": open_violations,
                    "raw_source": source_payload,
                }
            )
            enriched_records.append(base_record)

        logger.info("enriched_records_built", count=len(enriched_records))
        return enriched_records

    def _geo_metrics_for_tax_sales(self, tax_sale_payloads: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not self.geo_enricher or not tax_sale_payloads:
            return {}

        tax_models: List[TaxSaleProperty] = []
        for payload in tax_sale_payloads:
            try:
                tax_models.append(TaxSaleProperty(**payload))
            except ValidationError:
                continue

        if not tax_models:
            return {}

        geo_results = self.geo_enricher.enrich_properties(tax_models)
        metrics = {}
        for result in geo_results:
            normalized = self.standardizer.normalize_parcel_id(result.parcel_id) or ""
            metrics[normalized] = result.to_dict()
        return metrics

    @staticmethod
    def _format_geo_metrics(geo_entry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "geo_nearby_violations": geo_entry.get("nearby_violations"),
            "geo_nearby_open_violations": geo_entry.get("nearby_open_violations"),
            "geo_nearest_violation_distance": geo_entry.get("nearest_violation_distance"),
            "geo_avg_violation_distance": geo_entry.get("avg_violation_distance"),
            "geo_violation_types_nearby": geo_entry.get("violation_types_nearby"),
        }

    def _summarize_violations(self) -> Dict[str, Dict[str, Any]]:
        """Build a quick lookup for violation counts by parcel."""
        df = self.enricher.violations_df
        if df.empty:
            return {}

        # Add case_status column if not present for open count
        if "case_status" not in df.columns and "caseinfostatus" in df.columns:
            df["case_status"] = df["caseinfostatus"]

        grouped = (
            df.groupby("parcel_id_normalized")
            .agg(
                count=("parcel_id_normalized", "size"),
                most_recent=("casedt", "max"),
                types=("case_type", lambda vals: sorted(set(filter(None, vals)))),
                open_count=(
                    "case_status",
                    lambda vals: sum(
                        1
                        for v in vals
                        if pd.notna(v) and str(v).lower() in ("open", "pending")
                    ),
                ),
            )
            .reset_index()
        )
        summary = {}
        for _, row in grouped.iterrows():
            # Handle most_recent date - could be string or datetime
            most_recent_val = row["most_recent"]
            if pd.notna(most_recent_val):
                if isinstance(most_recent_val, str):
                    # Already a string, extract just the date part
                    most_recent = most_recent_val.split('T')[0] if 'T' in most_recent_val else most_recent_val
                else:
                    # datetime object, format it
                    most_recent = most_recent_val.strftime("%Y-%m-%d")
            else:
                most_recent = None

            summary[row["parcel_id_normalized"]] = {
                "count": int(row["count"]),
                "most_recent": most_recent,
                "types": row["types"],
                "open_count": int(row["open_count"]),
            }
        return summary
