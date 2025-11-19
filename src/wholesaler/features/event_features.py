"""
Event-based features extraction (violations, tax sales, etc).
"""
from typing import Dict, Any
from datetime import date, timedelta

def extract_event_features(record: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract event counts and recency.
    
    Args:
        record: Enriched property record
        
    Returns:
        Dictionary of numerical features
    """
    features = {}
    today = date.today()
    
    # Code Violations
    features["violation_count"] = float(record.get("violation_count") or 0)
    features["open_violation_count"] = float(record.get("open_violations") or 0)
    
    most_recent = record.get("most_recent_violation")
    if most_recent:
        try:
            if isinstance(most_recent, str):
                d = date.fromisoformat(most_recent[:10])
            else:
                d = most_recent
            features["days_since_violation"] = float((today - d).days)
        except (ValueError, TypeError):
            features["days_since_violation"] = 9999.0
    else:
        features["days_since_violation"] = 9999.0
        
    # Tax Sale
    tax_sale = record.get("tax_sale")
    features["has_tax_sale"] = 1.0 if tax_sale else 0.0
    
    # Foreclosure
    foreclosure = record.get("foreclosure")
    features["has_foreclosure"] = 1.0 if foreclosure else 0.0
    
    return features
