import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime
import pandas as pd

from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder
from src.wholesaler.db.models import EnrichedSeed, Property, PropertyRecord, TaxSale, Foreclosure

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def builder(mock_session):
    return FeatureStoreBuilder(mock_session)

def test_extract_features_from_seed(builder):
    """Test feature extraction logic."""
    today = date.today()
    
    # Mock EnrichedSeed
    seed = EnrichedSeed(
        parcel_id_normalized="12345",
        seed_type="tax_sale",
        enriched_data={
            "violation_count": 5,
            "nearby_open_violations": 2,
            "most_recent_violation": str(today),
            "geo_nearby_violations": 10,
            "geo_nearest_violation_distance": 0.1
        }
    )
    
    # Mock Property Map
    prop = Property(
        parcel_id_normalized="12345",
        city="ORLANDO",
        zip_code="32801",
        is_active=True
    )
    prop.property_record = PropertyRecord(
        total_mkt=200000,
        equity_percent=150,
        year_built=2000,
        tax_rate=1.5
    )
    prop.tax_sale = TaxSale(
        sale_date=today,
        raw_data={"opening_bid": 10000}
    )
    prop.foreclosure = None
    
    prop_map = {"12345": prop}
    
    features = builder._extract_features_from_seed(seed, prop_map, today)
    
    assert features is not None
    assert features["parcel_id_normalized"] == "12345"
    assert features["violation_count"] == 5
    assert features["open_violation_count"] == 2
    assert features["days_since_last_violation"] == 0
    assert features["seed_type_tax_sale"] is True
    assert features["total_market_value"] == 200000
    assert features["equity_percent"] == 150
    assert features["days_to_tax_sale"] == 0
    assert features["city"] == "ORLANDO"

def test_encode_categorical_features(builder):
    """Test categorical encoding."""
    df = pd.DataFrame({
        "city": ["ORLANDO", "MIAMI", "ORLANDO"],
        "zip_code": ["32801", "33101", "32801"],
        "value": [1, 2, 3]
    })
    
    encoded_df = builder._encode_categorical_features(df)
    
    assert "city_encoded" in encoded_df.columns
    assert "zip_code_encoded" in encoded_df.columns
    assert "city" not in encoded_df.columns  # Should be dropped
    
    # Orlando should have same code
    assert encoded_df.iloc[0]["city_encoded"] == encoded_df.iloc[2]["city_encoded"]
    # Miami should be different
    assert encoded_df.iloc[0]["city_encoded"] != encoded_df.iloc[1]["city_encoded"]

def test_compute_violation_severity(builder):
    """Test severity score logic."""
    today = date.today()
    
    # Case 1: High severity (many violations, recent, open)
    enriched_high = {
        "violation_count": 10,
        "most_recent_violation": str(today),
        "nearby_open_violations": 5
    }
    score_high = builder._compute_violation_severity(enriched_high, today)
    
    # Case 2: Low severity (few violations, old, closed)
    enriched_low = {
        "violation_count": 1,
        "most_recent_violation": "2000-01-01",
        "nearby_open_violations": 0
    }
    score_low = builder._compute_violation_severity(enriched_low, today)
    
    assert score_high > score_low
    assert score_high <= 100.0
