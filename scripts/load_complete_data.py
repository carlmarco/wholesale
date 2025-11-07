"""
Load Complete Dataset into Database

Loads comprehensive data downloaded from Orange County APIs:
- Tax sales
- Foreclosures
- Property records (for ARV training)

This provides the full dataset needed for training ML models.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from src.wholesaler.db.session import get_db_session
from src.wholesaler.etl.loaders import (
    TaxSaleLoader,
    ForeclosureLoader,
    PropertyLoader,
    PropertyRecordLoader,
)
from src.wholesaler.models.property import TaxSaleProperty
from src.wholesaler.models.foreclosure import ForeclosureProperty
from src.wholesaler.models.property_record import PropertyRecord
from src.wholesaler.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def main():
    """Load complete dataset into database."""
    logger.info("Starting complete data load...")

    data_dir = Path(__file__).parent.parent / "data" / "test"

    # Load tax sales from JSON
    logger.info("Loading tax sales from JSON...")
    with open(data_dir / "tax_sales.json", 'r') as f:
        tax_sales_data = json.load(f)
    tax_sales = [TaxSaleProperty(**ts) for ts in tax_sales_data]
    logger.info(f"Loaded {len(tax_sales)} tax sales from file")

    # Load foreclosures from JSON
    logger.info("Loading foreclosures from JSON...")
    with open(data_dir / "foreclosures.json", 'r') as f:
        foreclosures_data = json.load(f)
    foreclosures = [ForeclosureProperty(**fc) for fc in foreclosures_data]
    logger.info(f"Loaded {len(foreclosures)} foreclosures from file")

    # Load property records from JSON
    logger.info("Loading property records from JSON...")
    with open(data_dir / "properties.json", 'r') as f:
        properties_data = json.load(f)
    properties = [PropertyRecord(**p) for p in properties_data]
    logger.info(f"Loaded {len(properties)} property records from file")

    with get_db_session() as session:
        # 1. Load tax sales
        logger.info("Loading tax sales into database...")
        tax_sale_loader = TaxSaleLoader()
        tax_sale_loader.bulk_load(session, tax_sales)
        session.commit()
        logger.info(f"✓ Loaded {len(tax_sales)} tax sales")

        # 2. Load foreclosures
        logger.info("Loading foreclosures into database...")
        foreclosure_loader = ForeclosureLoader()
        foreclosure_loader.bulk_load(session, foreclosures)
        session.commit()
        logger.info(f"✓ Loaded {len(foreclosures)} foreclosures")

        # 3. Load property records (critical for ARV training)
        logger.info("Loading property records into database...")
        property_record_loader = PropertyRecordLoader()
        property_record_loader.bulk_load(session, properties)
        session.commit()
        logger.info(f"✓ Loaded {len(properties)} property records")

        # 4. Create Property records from tax sales
        logger.info("Creating property records from tax sales...")
        property_loader = PropertyLoader()

        # Load from tax sales
        for ts in tax_sales:
            property_loader.load_from_tax_sale(session, ts)

        session.commit()
        logger.info("✓ Created property records from tax sales")

    # Print summary
    print("\n" + "="*80)
    print("DATA LOAD COMPLETE")
    print("="*80)
    print(f"\nLoaded into database:")
    print(f"  - {len(tax_sales)} tax sales")
    print(f"  - {len(foreclosures)} foreclosures")
    print(f"  - {len(properties)} property records (with market values!)")
    print(f"\nNext steps:")
    print("  1. Run lead scoring: .venv/bin/python scripts/run_lead_scoring.py")
    print("  2. Train ARV model: .venv/bin/python -m src.wholesaler.ml.training.train_arv_model --output models/arv_model.joblib")
    print("  3. Train lead model: .venv/bin/python -m src.wholesaler.ml.training.train_lead_model --output models/lead_model.joblib")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
