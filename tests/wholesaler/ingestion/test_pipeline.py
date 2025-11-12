import sys
from pathlib import Path
from datetime import datetime

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.ingestion.pipeline import IngestionPipeline
from src.wholesaler.ingestion.seed_models import SeedRecord


class DummyTaxSaleScraper:
    def fetch_properties(self, limit=None):
        class Obj:
            def __init__(self, parcel_id):
                self.parcel_id = parcel_id

            def to_dict(self):
                return {"parcel_id": self.parcel_id}

        return [Obj("12-34-56-7890-01-001")]


class DummyForeclosureScraper:
    def fetch_properties(self, limit=None):
        class Obj:
            def __init__(self, parcel_number):
                self.parcel_number = parcel_number

            def to_dict(self):
                return {"parcel_number": self.parcel_number}

        return [Obj("98-76-54-3210-00-111")]


class DummyCodeViolationScraper:
    def fetch_violations(self, limit=None):
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "parcel_id": "123",
                    "caseinfostatus": "Open",
                    "case_type": "Lot",
                    "casedt": datetime.utcnow(),
                }
            ]
        )


def test_ingestion_pipeline_collects_all_sources():
    pipeline = IngestionPipeline(
        tax_sale_scraper=DummyTaxSaleScraper(),
        foreclosure_scraper=DummyForeclosureScraper(),
        code_violation_scraper=DummyCodeViolationScraper(),
    )

    seeds = pipeline.run(sources=["tax_sales", "foreclosures", "code_violations"], output_path=None)
    assert len(seeds) == 3
    assert sorted(seed.seed_type for seed in seeds) == ["code_violation", "foreclosure", "tax_sale"]
