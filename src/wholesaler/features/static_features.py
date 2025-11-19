"""
Static property features extraction.
"""
from typing import Dict, Any, Optional
from datetime import date

def extract_static_features(record: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract static physical and zoning features.
    
    Args:
        record: Enriched property record
        
    Returns:
        Dictionary of numerical features
    """
    prop = record.get("property_record") or {}
    
    features = {}
    
    # Physical specs
    features["living_area_sqft"] = float(prop.get("living_area") or 0)
    features["lot_size_sqft"] = float(prop.get("lot_size") or 0)
    
    # Age
    year_built = prop.get("year_built")
    if year_built:
        features["property_age"] = float(date.today().year - year_built)
    else:
        features["property_age"] = -1.0
        
    # Financial
    features["assessed_value"] = float(prop.get("total_assd") or 0)
    features["market_value"] = float(prop.get("total_mkt") or 0)
    
    # Ratios
    if features["market_value"] > 0:
        features["assessed_to_market_ratio"] = features["assessed_value"] / features["market_value"]
    else:
        features["assessed_to_market_ratio"] = 0.0
        
    return features
