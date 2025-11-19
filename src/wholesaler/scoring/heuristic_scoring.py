"""
Heuristic scoring model for label-free risk assessment.
"""
from typing import Dict, Any
from src.wholesaler.features.static_features import extract_static_features
from src.wholesaler.features.event_features import extract_event_features
from src.wholesaler.features.geo_features import extract_geo_features

class HeuristicRiskScorer:
    """
    Computes a composite risk score based on heuristic sub-scores.
    """
    
    def score(self, record: Dict[str, Any]) -> float:
        """
        Calculate risk score (0.0 to 1.0).
        Higher score = Higher risk/distress.
        """
        static = extract_static_features(record)
        events = extract_event_features(record)
        geo = extract_geo_features(record)
        
        # 1. Code Enforcement Score (0-1)
        score_ce = min(1.0, (events["violation_count"] * 0.1) + (events["open_violation_count"] * 0.2))
        if events["days_since_violation"] < 90:
            score_ce = min(1.0, score_ce + 0.2)
            
        # 2. Tax/Legal Score (0-1)
        score_legal = 0.0
        if events["has_tax_sale"]:
            score_legal = 1.0
        elif events["has_foreclosure"]:
            score_legal = 0.8
            
        # 3. Geo Distress Score (0-1)
        score_geo = min(1.0, geo["nearby_violations_count"] * 0.05)
        if geo["dist_to_nearest_violation"] < 0.1:
            score_geo = min(1.0, score_geo + 0.1)
            
        # 4. Value/Equity Score (0-1)
        # Low equity or low value = higher distress potential (sometimes)
        # But for wholesaling, we want HIGH equity.
        # Let's define this as "Deal Attractiveness" rather than just distress?
        # The prompt says "distress_score", so let's stick to distress.
        # Low value properties are often more distressed.
        score_value = 0.0
        if static["market_value"] < 100000:
            score_value = 0.3
        if static["property_age"] > 40:
            score_value += 0.2
            
        # Weighted Sum
        # Weights: CE=0.4, Legal=0.4, Geo=0.1, Value=0.1
        final_score = (
            (score_ce * 0.4) +
            (score_legal * 0.4) +
            (score_geo * 0.1) +
            (score_value * 0.1)
        )
        
        return round(final_score, 4)
