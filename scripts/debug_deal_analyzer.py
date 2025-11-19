import sys
import os
from pathlib import Path
import logging

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.db.models import LeadScore, Property, TaxSale, Foreclosure
from src.wholesaler.ml.models import PropertyFeatures, get_deal_analysis
from src.wholesaler.api.routers.analysis import DealAnalysisResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PARCEL_ID = "292307313900001"

def debug_deal_analyzer():
    logger.info(f"Debugging Deal Analyzer for {PARCEL_ID}...")
    
    with get_db_session() as session:
        # 1. Query DB (Same logic as API)
        logger.info("Querying database...")
        try:
            lead = (
                session.query(LeadScore)
                .join(Property)
                .filter(LeadScore.parcel_id_normalized == PARCEL_ID)
                .first()
            )
            
            if not lead:
                logger.error("Lead not found!")
                return

            tax_sale = (
                session.query(TaxSale)
                .filter(TaxSale.parcel_id_normalized == PARCEL_ID)
                .first()
            )

            foreclosure = (
                session.query(Foreclosure)
                .filter(Foreclosure.parcel_id_normalized == PARCEL_ID)
                .first()
            )
        except Exception as e:
            logger.error(f"DB Query Failed: {e}")
            return

        logger.info("DB Query successful.")

        # 2. Build PropertyFeatures
        logger.info("Building PropertyFeatures...")
        try:
            # Logic from API
            property_use = lead.property.foreclosure.property_type if lead.property.foreclosure else "Single Family"
            
            features = PropertyFeatures(
                parcel_id=PARCEL_ID,
                city=lead.property.city or "Orlando",
                zip_code=lead.property.zip_code,
                property_use=property_use,
                total_score=float(lead.total_score or 0.0),
                distress_score=float(lead.distress_score or 0.0),
                value_score=float(lead.value_score or 0.0),
                location_score=float(lead.location_score or 0.0),
                has_tax_sale=tax_sale is not None,
                has_foreclosure=foreclosure is not None,
                tax_sale_opening_bid=float(tax_sale.opening_bid) if tax_sale and tax_sale.opening_bid else None,
                foreclosure_judgment=float(foreclosure.default_amount) if foreclosure and foreclosure.default_amount else None,
            )
            logger.info(f"Features built: {features}")
        except Exception as e:
            logger.error(f"PropertyFeatures Construction Failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # 3. Run Analysis
        logger.info("Running get_deal_analysis...")
        try:
            analysis = get_deal_analysis(features)
            logger.info("Analysis successful.")
        except Exception as e:
            logger.error(f"Analysis Failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # 4. Pydantic Response
        logger.info("Constructing Response...")
        try:
            response = DealAnalysisResponse(
                parcel_id=analysis.parcel_id,
                estimated_arv=analysis.estimated_arv,
                estimated_repair_costs=analysis.estimated_repair_costs,
                max_offer_price=analysis.max_offer_price,
                potential_profit=analysis.potential_profit,
                roi_percentage=analysis.roi_percentage,
                confidence_level=analysis.confidence_level,
                risk_factors=analysis.risk_factors,
                opportunity_factors=analysis.opportunity_factors,
                recommendation=analysis.recommendation,
            )
            logger.info("Response construction SUCCESS!")
            logger.info(response.model_dump_json(indent=2))
        except Exception as e:
            logger.error(f"Response Construction Failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_deal_analyzer()
