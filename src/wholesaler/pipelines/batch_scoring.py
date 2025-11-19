"""
Batch scoring pipeline for Label-Free ML.
"""
import pandas as pd
from sqlalchemy.orm import Session
from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder
from src.wholesaler.models.clusterer import PropertyClusterer
from src.wholesaler.models.anomaly_detector import AnomalyDetector
from src.wholesaler.scoring.composite_scoring import CompositeRiskScorer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

class BatchScoringPipeline:
    """
    Orchestrates the end-to-end scoring process:
    1. Fetch features
    2. Run unsupervised models (Cluster, Anomaly)
    3. Compute composite scores
    4. (Optional) Persist results
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.feature_builder = FeatureStoreBuilder(session)
        self.clusterer = PropertyClusterer()
        self.anomaly_detector = AnomalyDetector()
        self.scorer = CompositeRiskScorer()
        
    def run(self, train_models: bool = True):
        """Run the batch pipeline."""
        logger.info("starting_batch_scoring")
        
        # 1. Get Data
        df = self.feature_builder.build_feature_dataframe()
        if df.empty:
            logger.warning("no_data_for_scoring")
            return
            
        # 2. Train/Apply Models
        if train_models:
            logger.info("training_unsupervised_models")
            self.clusterer.fit(df)
            self.anomaly_detector.fit(df)
            
        clusters = self.clusterer.predict(df)
        anomalies = self.anomaly_detector.score(df) # Raw scores
        # Normalize anomaly scores to 0-1 roughly?
        # IsolationForest decision_function: average 0.0, lower is anomalous.
        # Let's invert and scale: score = 0.5 - (raw / 2) clipped 0-1?
        # Simplified: just use raw for now or rank percentile.
        
        df["cluster_id"] = clusters
        df["anomaly_score_raw"] = anomalies
        
        # 3. Composite Scoring
        results = []
        for idx, row in df.iterrows():
            record = row.to_dict()
            # Reconstruct nested structure if needed by heuristic scorer
            # or update heuristic scorer to accept flat dict.
            # For now, assuming heuristic scorer handles flat or we map it.
            # Mapping flat features back to 'record' structure expected by heuristic:
            structured_record = self._map_flat_to_structured(record)
            
            # Cluster risk proxy: assume some clusters are riskier?
            # For now, 0.0.
            
            score_res = self.scorer.score(
                structured_record, 
                anomaly_score=0.5, # Placeholder normalization
                cluster_risk=0.0
            )
            results.append({
                "parcel_id_normalized": row["parcel_id_normalized"],
                "risk_score": score_res["composite_risk_score"],
                "tier": score_res["tier"],
                "cluster_id": int(row["cluster_id"])
            })
            
        result_df = pd.DataFrame(results)
        logger.info("batch_scoring_complete", count=len(result_df))
        return result_df

    def _map_flat_to_structured(self, row: dict) -> dict:
        """Helper to map flat feature row to nested dict for legacy scorers."""
        return {
            "violation_count": row.get("violation_count"),
            "open_violations": row.get("open_violation_count"),
            "most_recent_violation": None, # Date logic complex here
            "tax_sale": {"opening_bid": 0} if row.get("seed_type_tax_sale") else None,
            "foreclosure": {} if row.get("seed_type_foreclosure") else None,
            "property_record": {
                "total_mkt": row.get("total_market_value"),
                "living_area": 0, # Missing in feature store?
                "year_built": 2025 - (row.get("property_age_years") or 0)
            },
            "nearby_violations": row.get("nearby_violations_count"),
            "geo_nearest_violation_distance": row.get("nearest_violation_distance")
        }
