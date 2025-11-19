"""
Geographic features extraction.
"""
from typing import Dict, Any

def extract_geo_features(record: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract geographic context features.
    
    Args:
        record: Enriched property record
        
    Returns:
        Dictionary of numerical features
    """
    features = {}
    
    # Nearby distress
    features["nearby_violations_count"] = float(record.get("nearby_violations") or 0)
    features["nearby_open_violations"] = float(record.get("nearby_open_violations") or 0)
    
    # Distance
    dist = record.get("geo_nearest_violation_distance")
    if dist is not None:
        features["dist_to_nearest_violation"] = float(dist)
    else:
        features["dist_to_nearest_violation"] = 99.0 # Max distance proxy
        
    return features
