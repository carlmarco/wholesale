import sys
from pathlib import Path
from datetime import datetime
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.ml.training.feature_builder import FeatureBuilder


class DummyModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class StubRepo:
    def __init__(self, rows):
        self.rows = rows

    def get_all(self, session, **kwargs):
        return self.rows


@pytest.fixture
def feature_builder(monkeypatch):
    builder = FeatureBuilder()

    now = datetime.utcnow()

    lead_rows = [
        DummyModel(
            parcel_id_normalized="123",
            parcel_id_original="123",
            tier="A",
            scored_at=now,
            total_score=80,
        )
    ]
    property_rows = [
        DummyModel(parcel_id_normalized="123", city="Orlando", zip_code="32801")
    ]
    record_rows = [
        DummyModel(parcel_id_normalized="123", total_mkt=200000, equity_percent=150)
    ]

    builder.lead_repo = StubRepo(lead_rows)
    builder.property_repo = StubRepo(property_rows)
    builder.property_record_repo = StubRepo(record_rows)
    builder.tax_sale_repo = StubRepo([])
    builder.foreclosure_repo = StubRepo([])

    return builder


def test_build_lead_dataset(feature_builder):
    fake_session = object()
    df = feature_builder.build_lead_dataset(session=fake_session, recent_days=7)
    assert not df.empty
    assert "label_tier_a" in df.columns
    assert df["label_tier_a"].iloc[0] == 1
