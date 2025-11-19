"""
Composite Risk Scoring.
Combines Heuristic, Anomaly, and Graph scores.
"""
from typing import Dict, Any
from src.wholesaler.scoring.heuristic_scoring import HeuristicRiskScorer

class CompositeRiskScorer:
    """
    Aggregates multiple risk signals into a final score.
    """
    
    def __init__(self):
        self.heuristic = HeuristicRiskScorer()
        
    def score(self, record: Dict[str, Any], anomaly_score: float = 0.0, cluster_risk: float = 0.0) -> Dict[str, Any]:
        """
        Compute composite risk score.
        
        Args:
            record: Property record
            anomaly_score: Score from AnomalyDetector (normalized 0-1 preferred)
            cluster_risk: Risk index of the assigned cluster
            
        Returns:
            Dict with final score and components
        """
        # 1. Heuristic Score (0-1)
        h_score = self.heuristic.score(record)
        
        # 2. Anomaly Score Integration
        # If anomaly_score is high (meaning normal), risk is low?
        # Or if anomaly_score is low (outlier), risk is high?
        # Assuming anomaly_score is 0-1 where 1 = highly anomalous/risky
        a_score = anomaly_score
        
        # 3. Composite Calculation
        # Weights: Heuristic=0.6, Anomaly=0.2, Cluster=0.2
        final_score = (h_score * 0.6) + (a_score * 0.2) + (cluster_risk * 0.2)
        
        return {
            "composite_risk_score": round(final_score, 4),
            "components": {
                "heuristic": h_score,
                "anomaly": a_score,
                "cluster": cluster_risk
            },
            "tier": self._tier(final_score)
        }
        
    def _tier(self, score: float) -> str:
        if score >= 0.8: return "A" # High Risk/Distress
        if score >= 0.6: return "B"
        if score >= 0.4: return "C"
        return "D"
