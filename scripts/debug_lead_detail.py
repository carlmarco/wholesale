import sys
import os
from pathlib import Path
import logging

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import joinedload
from src.wholesaler.db.session import get_db_session
from src.wholesaler.db.models import LeadScore, Property, TaxSale, Foreclosure
from src.wholesaler.api.schemas import LeadScoreDetail
from src.wholesaler.api.routers.leads import _serialize_property_detail, _serialize_tax_sale, _serialize_foreclosure

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PARCEL_ID = "292307313900001"

def debug_lead_detail():
    logger.info(f"Debugging lead detail for {PARCEL_ID}...")
    
    with get_db_session() as session:
        # 1. Query DB
        logger.info("Querying database...")
        try:
            lead = (
                session.query(LeadScore)
                .join(Property)
                .outerjoin(TaxSale)
                .outerjoin(Foreclosure)
                .options(
                    joinedload(LeadScore.property),
                    joinedload(LeadScore.property).joinedload(Property.tax_sale),
                    joinedload(LeadScore.property).joinedload(Property.foreclosure),
                )
                .filter(LeadScore.parcel_id_normalized == PARCEL_ID)
                .first()
            )
        except Exception as e:
            logger.error(f"DB Query Failed: {e}")
            return

        if not lead:
            logger.error("Lead not found in DB!")
            return

        logger.info("Lead found. Inspecting attributes...")
        logger.info(f"Lead ID: {lead.id}")
        logger.info(f"Profitability Score: {lead.profitability_score} (Type: {type(lead.profitability_score)})")
        logger.info(f"ML Risk Score: {lead.ml_risk_score} (Type: {type(lead.ml_risk_score)})")
        
        if not lead.property:
            logger.error("Property is missing!")
            return

        # 2. Manual Serialization
        logger.info("Attempting manual serialization...")
        try:
            data = {
                "parcel_id_normalized": lead.parcel_id_normalized,
                "distress_score": float(lead.distress_score or 0.0),
                "value_score": float(lead.value_score or 0.0),
                "location_score": float(lead.location_score or 0.0),
                "urgency_score": float(lead.urgency_score or 0.0),
                "total_score": float(lead.total_score or 0.0),
                "tier": lead.tier,
                "scoring_reasons": lead.reasons or [],
                "property": _serialize_property_detail(lead.property),
                "tax_sale": _serialize_tax_sale(lead.property.tax_sale),
                "foreclosure": _serialize_foreclosure(lead.property.foreclosure),
                "scored_at": lead.scored_at,
                "created_at": lead.created_at,
                "updated_at": lead.updated_at,
                "profitability_score": float(lead.profitability_score) if lead.profitability_score is not None else None,
                "profitability_details": lead.profitability_details,
                "ml_risk_score": float(lead.ml_risk_score) if lead.ml_risk_score is not None else None,
                "ml_risk_tier": lead.ml_risk_tier,
                "ml_cluster_id": lead.ml_cluster_id,
                "ml_anomaly_score": float(lead.ml_anomaly_score) if lead.ml_anomaly_score is not None else None,
            }
            logger.info("Manual serialization successful.")
        except Exception as e:
            logger.error(f"Manual Serialization Failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # 3. Pydantic Validation
        logger.info("Attempting Pydantic validation...")
        try:
            model = LeadScoreDetail(**data)
            logger.info("Pydantic validation SUCCESS!")
            logger.info(model.model_dump_json(indent=2))
        except Exception as e:
            logger.error(f"Pydantic Validation Failed: {e}")
            # Print detailed validation errors
            if hasattr(e, 'errors'):
                import json
                logger.error(json.dumps(e.errors(), indent=2))

if __name__ == "__main__":
    debug_lead_detail()
