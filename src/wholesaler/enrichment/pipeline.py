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
from src.wholesaler.scrapers.property_scraper import PropertyScraper
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
        self.property_scraper = PropertyScraper()

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
        
        # Batch fetch property records for seeds that need them (tax_sale, foreclosure)
        # Skip code_violations as they already have address data
        all_parcels = {
            self.standardizer.normalize_parcel_id(seed.parcel_id) 
            for seed in seeds 
            if seed.parcel_id and seed.seed_type in ("tax_sale", "foreclosure")
        }
        # Remove None/Empty
        all_parcels = {p for p in all_parcels if p}
        
        logger.info(
            "property_lookup_scope",
            total_seeds=len(seeds),
            parcels_to_lookup=len(all_parcels)
        )
        
        property_records_map = {}
        if all_parcels:
            try:
                records = self.property_scraper.fetch_properties(parcel_numbers=list(all_parcels))
                for rec in records:
                    norm_pid = self.standardizer.normalize_parcel_id(rec.parcel_number)
                    if norm_pid:
                        property_records_map[norm_pid] = rec
                        
                # For seeds not found by parcel ID, try coordinate-based lookup
                found_parcels = set(property_records_map.keys())
                missing_parcels = all_parcels - found_parcels
                
                if missing_parcels:
                    logger.info("attempting_coordinate_lookup", missing_count=len(missing_parcels))
                    # Build map of parcel -> coordinates
                    parcel_coords = {}
                    for seed in seeds:
                        norm_pid = self.standardizer.normalize_parcel_id(seed.parcel_id)
                        if norm_pid in missing_parcels:
                            # Get coordinates from source_payload
                            payload = seed.source_payload or {}
                            # Tax sales have geometry in GeoJSON format, foreclosures have lat/lon
                            if seed.seed_type == "tax_sale" and "geometry" in payload:
                                coords = payload["geometry"].get("coordinates")
                                if coords and len(coords) == 2:
                                    parcel_coords[norm_pid] = {"lon": coords[0], "lat": coords[1]}
                            elif "latitude" in payload and "longitude" in payload:
                                parcel_coords[norm_pid] = {
                                    "lat": payload["latitude"],
                                    "lon": payload["longitude"]
                                }
                    
                    # Fetch by coordinates
                    for parcel_id, coords in parcel_coords.items():
                        try:
                            rec = self.property_scraper.fetch_by_coordinates(
                                latitude=coords["lat"],
                                longitude=coords["lon"],
                                radius_meters=50
                            )
                            if rec:
                                property_records_map[parcel_id] = rec
                                logger.info("property_found_by_coordinates", parcel=parcel_id)
                        except Exception as coord_err:
                            logger.warning("coordinate_lookup_failed", parcel=parcel_id, error=str(coord_err))
                            
            except Exception as e:
                logger.error("property_fetch_failed", error=str(e))

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
                    
                    # Add property record data if available
                    prop_record = property_records_map.get(normalized_parcel)
                    if prop_record:
                        if not merged.get("situs_address"):
                            merged["situs_address"] = prop_record.situs_address
                        if not merged.get("city") and prop_record.situs_city:
                            merged["city"] = prop_record.situs_city
                        if not merged.get("zip_code") and prop_record.situs_zip:
                            merged["zip_code"] = prop_record.situs_zip
                        merged["property_record"] = prop_record.to_dict()
                        if not merged.get("latitude") and prop_record.latitude:
                            merged["latitude"] = prop_record.latitude
                            merged["longitude"] = prop_record.longitude
                    
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
            
            # For code violations, extract address from source payload
            if seed.seed_type == "code_violation" and source_payload:
                derived_addr = source_payload.get("derived_address")
                if derived_addr and not base_record.get("situs_address"):
                    # Parse "1218 W SMITH ST  ORLANDO FL" format
                    parts = derived_addr.strip().split()
                    if len(parts) >= 2:
                        # Extract city (usually second-to-last or last before state)
                        if len(parts) >= 3:
                            # Assume format: ADDRESS CITY STATE
                            # Find where city starts (after street address)
                            # Simple heuristic: last 2-3 words are city/state
                            if parts[-1] in ['FL', 'FLORIDA']:
                                # City is everything between address and FL
                                city_parts = []
                                street_ended = False
                                for i, part in enumerate(parts[:-1]):  # Exclude FL
                                    # Heuristic: if we see ST, AVE, DR, etc., street has ended
                                    if part in ['ST', 'AVE', 'DR', 'RD', 'LN', 'CT', 'CIR', 'BLVD', 'PL']:
                                        street_ended = True
                                        continue
                                    if street_ended:
                                        city_parts.append(part)
                                
                                if city_parts:
                                    base_record["city"] = " ".join(city_parts)
                        
                        # Store full address
                        base_record["situs_address"] = derived_addr
                
                # Extract property value data if available
                # Code violations include parassdvalue (assessed value)
                if not base_record.get("property_record"):
                    cv_property_data = {}
                    
                    if source_payload.get("parassdvalue"):
                        try:
                            assd_val = float(source_payload["parassdvalue"])
                            cv_property_data["total_assd"] = assd_val
                            # Estimate market value as 110% of assessed (rough heuristic)
                            cv_property_data["total_mkt"] = assd_val * 1.1
                        except (ValueError, TypeError):
                            pass
                    
                    if cv_property_data:
                        base_record["property_record"] = cv_property_data
            
            # Merge Property Record Data (Address, Market Value, etc.)
            prop_record = property_records_map.get(normalized_parcel)
            if prop_record:
                # Top-level address fields if missing
                if not base_record.get("situs_address"):
                    base_record["situs_address"] = prop_record.situs_address
                
                if not base_record.get("city") and prop_record.situs_city:
                    base_record["city"] = prop_record.situs_city
                    
                if not base_record.get("zip_code") and prop_record.situs_zip:
                    base_record["zip_code"] = prop_record.situs_zip

                # Add full property record for scorer
                base_record["property_record"] = prop_record.to_dict()
                
                # If we have coordinates from property record and not from seed, use them
                if not base_record.get("latitude") and prop_record.latitude:
                    base_record["latitude"] = prop_record.latitude
                    base_record["longitude"] = prop_record.longitude

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
