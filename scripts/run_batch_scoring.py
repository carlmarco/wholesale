import sys
import os
from pathlib import Path
import logging
from sqlalchemy import update

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.db.models import LeadScore
from src.wholesaler.pipelines.batch_scoring import BatchScoringPipeline
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

def main():
    logger.info("Starting Batch Scoring Pipeline...")
    
    with get_db_session() as session:
        pipeline = BatchScoringPipeline(session)
        
        try:
            results_df = pipeline.run(train_models=True)
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            import traceback
            traceback.print_exc()
            return

        if results_df is None or results_df.empty:
            logger.warning("No results generated.")
            return

        logger.info(f"Generated scores for {len(results_df)} leads. Saving to DB...")
        
        updated_count = 0
        for _, row in results_df.iterrows():
            stmt = (
                update(LeadScore)
                .where(LeadScore.parcel_id_normalized == row["parcel_id_normalized"])
                .values(
                    ml_risk_score=float(row["risk_score"]),
                    ml_risk_tier=row["tier"],
                    ml_cluster_id=int(row["cluster_id"]),
                    # anomaly score is not in result_df yet, need to update pipeline or add it here
                    # For now, let's assume pipeline returns it or we skip it
                )
            )
            result = session.execute(stmt)
            updated_count += result.rowcount
            
        session.commit()
        logger.info(f"Successfully updated {updated_count} lead scores in database.")

if __name__ == "__main__":
    main()
