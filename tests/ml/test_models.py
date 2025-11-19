import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.ml import models
from src.wholesaler.ml.models import PropertyFeatures


def test_estimate_arv_ml(monkeypatch):
    def mock_load():
        class MockModel:
            def predict(self, X):
                return [300000]
        return {"model": MockModel(), "features": ["total_score"]}

    monkeypatch.setattr(models, "_load_arv_model", mock_load)
    features = PropertyFeatures(parcel_id="123", city="Orlando", total_score=80)
    result = models.estimate_arv(features)
    assert result["estimated_arv"] == 300000


def test_estimate_arv_fallback(monkeypatch):
    monkeypatch.setattr(models, "_load_arv_model", lambda: None)
    features = PropertyFeatures(parcel_id="123", city="Orlando", total_score=80)
    result = models.estimate_arv(features)
    assert result["estimated_arv"] > 0


def test_predict_lead_probability(monkeypatch):
    class MockModel:
        def predict_proba(self, X):
            return [[0.2, 0.8]]

    monkeypatch.setattr(models, "_load_lead_model", lambda: {"model": MockModel(), "features": ["total_score"]})

    features = PropertyFeatures(parcel_id="123", city="Orlando", total_score=80)
    proba = models.predict_lead_probability(features)
    assert proba == pytest.approx(0.8)
