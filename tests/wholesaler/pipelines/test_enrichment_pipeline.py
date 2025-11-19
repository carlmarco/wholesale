import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.enrichment import UnifiedEnrichmentPipeline


def build_seed(parcel_id, seed_type, payload=None):
    return SeedRecord(parcel_id=parcel_id, seed_type=seed_type, source_payload=payload or {})


def test_unified_enrichment_pipeline_merges_tax_sale_and_distress():
    violation_df = pd.DataFrame(
        [
            {
                "parcel_id": "12-34-56-7890-01-001",
                "parcel_id_normalized": "123456789001001",
                "caseinfostatus": "Open",
                "case_type": "Lot",
                "casedt": datetime.utcnow(),
                "days_to_resolve": 10,
            },
            {
                "parcel_id": "99-99-99-9999-99-999",
                "parcel_id_normalized": "999999999999999",
                "caseinfostatus": "Closed",
                "case_type": "Housing",
                "casedt": datetime.utcnow(),
                "days_to_resolve": 5,
            },
        ]
    )

    tax_seed = build_seed(
        parcel_id="12-34-56-7890-01-001",
        seed_type="tax_sale",
        payload={
            "parcel_id": "12-34-56-7890-01-001",
            "tda_number": "2024-001",
            "longitude": -81.0,
            "latitude": 28.0,
        },
    )

    code_seed = build_seed(parcel_id="99-99-99-9999-99-999", seed_type="code_violation")

    pipeline = UnifiedEnrichmentPipeline(violation_df=violation_df)
    enriched = pipeline.run([tax_seed, code_seed])

    assert len(enriched) == 2
    parcel_ids = {rec["parcel_id_normalized"] for rec in enriched}
    assert "123456789001001" in parcel_ids
    assert "999999999999999" in parcel_ids

    tax_record = next(rec for rec in enriched if rec["seed_type"] == "tax_sale")
    assert tax_record["violation_count"] >= 1 or tax_record.get("has_violations")

    code_record = next(rec for rec in enriched if rec["seed_type"] == "code_violation")
    assert code_record["violation_count"] == 1


def test_unified_enrichment_pipeline_applies_geo_metrics():
    violation_df = pd.DataFrame(
        [
            {
                "parcel_id": "12-34-56-7890-01-001",
                "parcel_id_normalized": "123456789001001",
                "caseinfostatus": "Closed",
                "case_type": "Lot",
                "casedt": datetime.utcnow(),
                "days_to_resolve": 12,
            }
        ]
    )

    tax_seed = build_seed(
        parcel_id="12-34-56-7890-01-001",
        seed_type="tax_sale",
        payload={
            "parcel_id": "12-34-56-7890-01-001",
            "tda_number": "2024-001",
            "longitude": -81.0,
            "latitude": 28.0,
        },
    )

    pipeline = UnifiedEnrichmentPipeline(violation_df=violation_df)

    class DummyGeoResult:
        def __init__(self, parcel_id):
            self.parcel_id = parcel_id

        def to_dict(self):
            return {
                "nearby_violations": 5,
                "nearby_open_violations": 2,
                "nearest_violation_distance": 0.5,
                "avg_violation_distance": 1.25,
                "violation_types_nearby": ["Lot"],
            }

    class DummyGeoEnricher:
        def enrich_properties(self, tax_models):
            return [DummyGeoResult(model.parcel_id) for model in tax_models]

    pipeline.geo_enricher = DummyGeoEnricher()
    enriched = pipeline.run([tax_seed])

    assert len(enriched) == 1
    record = enriched[0]
    assert record["geo_nearby_violations"] == 5
    assert record["geo_nearest_violation_distance"] == 0.5
