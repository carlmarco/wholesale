import pytest
from src.wholesaler.scoring.profitability_scorer import ConservativeProfitabilityBucket

@pytest.fixture
def scorer():
    return ConservativeProfitabilityBucket()

def test_profitable_tax_sale(scorer):
    """Test a clear winner tax sale."""
    record = {
        "total_mkt": 300000,  # ARV approx 300k
        "property_record": {
            "living_area": 1500,
            "year_built": 2000
        },
        "tax_sale": {
            "opening_bid": 20000
        },
        "violation_count": 0
    }
    
    # ARV = 300,000
    # Repairs = 1500 * 25 = 37,500
    # End Buyer Price = (300k * 0.7) - 37.5k = 210k - 37.5k = 172,500
    # Acquisition = 20,000
    # Profit = 172,500 - 20,000 = 152,500
    # Should be profitable
    
    result = scorer.score(record)
    assert result.is_profitable is True
    assert result.projected_profit > 100000

def test_unprofitable_heavy_repairs(scorer):
    """Test a property with heavy repairs killing the deal."""
    record = {
        "total_mkt": 100000,
        "property_record": {
            "living_area": 2000,
            "year_built": 1950 # Old -> +10/sqft
        },
        "violation_count": 10, # Heavy distress -> +15/sqft
        # Base 25 + 10 + 15 = 50/sqft repairs
        # Repairs = 2000 * 50 = 100,000
        
        "foreclosure": {
            "default_amount": 50000
        }
    }
    
    # ARV = 100,000
    # End Buyer Price = (70k) - 100k = -30k
    # Profit = -30k - 50k = -80k
    
    result = scorer.score(record)
    assert result.is_profitable is False
    assert result.projected_profit < 0

def test_marginal_deal(scorer):
    """Test a deal right on the edge."""
    # We want Profit ~ 15k
    # Profit = EndBuyer - Acq
    # 15k = EndBuyer - 100k  => EndBuyer = 115k
    # EndBuyer = ARV*0.7 - Repairs
    # 115k = ARV*0.7 - 25k (assuming 1000sqft * 25)
    # 140k = ARV*0.7 => ARV = 200k
    
    record = {
        "total_mkt": 200000,
        "property_record": {
            "living_area": 1000,
            "year_built": 2000
        },
        "foreclosure": {
            "default_amount": 100000
        }
    }
    
    # ARV 200k
    # Repairs 25k
    # End Buyer = 140k - 25k = 115k
    # Profit = 115k - 100k = 15k
    
    result = scorer.score(record)
    # Might be slightly off due to floats, but should be close
    assert result.projected_profit >= 15000
    assert result.is_profitable is True

def test_no_data_fallback(scorer):
    """Test behavior when data is missing."""
    record = {}
    # ARV 0
    # Repairs Min 15k
    # End Buyer -15k
    # Acq 0
    # Profit -15k
    
    result = scorer.score(record)
    assert result.is_profitable is False
