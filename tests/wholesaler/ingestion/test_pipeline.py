import pytest
import pandas as pd
import numpy as np
import json
from unittest.mock import MagicMock
from src.wholesaler.ingestion.pipeline import IngestionPipeline
from src.wholesaler.scrapers.code_violation_scraper import CodeViolationScraper

def test_collect_code_violation_seeds_numpy_types():
    """Test that numpy types in DataFrame are converted to native Python types."""
    # Create a DataFrame with numpy types
    df = pd.DataFrame({
        "parcel_id": ["123"],
        "violation_count": [np.int64(5)],
        "fine_amount": [np.float64(100.50)],
        "is_open": [np.bool_(True)]
    })
    
    # Mock scraper
    mock_scraper = MagicMock(spec=CodeViolationScraper)
    mock_scraper.fetch_violations.return_value = df
    
    # Init pipeline with mock
    pipeline = IngestionPipeline(code_violation_scraper=mock_scraper)
    
    # Run collection
    seeds = pipeline.collect_code_violation_seeds()
    
    assert len(seeds) == 1
    seed = seeds[0]
    payload = seed.source_payload
    
    # Verify types are native
    assert isinstance(payload["violation_count"], int)
    assert not isinstance(payload["violation_count"], np.integer)
    
    assert isinstance(payload["fine_amount"], float)
    assert not isinstance(payload["fine_amount"], np.floating)
    
    assert isinstance(payload["is_open"], bool)
    assert not isinstance(payload["is_open"], np.bool_)
    
    # Verify JSON serialization works (would raise TypeError if numpy types remained)
    json_str = json.dumps(payload)
    assert "100.5" in json_str
