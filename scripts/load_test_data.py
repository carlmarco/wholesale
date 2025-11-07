"""
Load Test Data into Database

Loads the test data downloaded by download_test_data.py into the PostgreSQL database
using the ETL loaders.
"""
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScr

aper
from src.wholesaler.etl.loaders import TaxSaleLoader, ForeclosureLoader
from src.wholesaler.db.session import get_db_session
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Load test data into database."""
    logger.info("Starting test data loading...")

    # Download test data (small sample)
    logger.info("Fetching test data from APIs...")
    tax_scraper = TaxSaleScraper()
    tax_sales = tax_scraper.fetch_properties(limit=20)
    logger.info(f"Fetched {len(tax_sales)} tax sale properties")

    foreclosure_scraper = ForeclosureScraper()
    foreclosures = foreclosure_scraper.fetch_properties(limit=20)
    logger.info(f"Fetched {len(foreclosures)} foreclosure properties")

    # Load into database
    logger.info("Loading data into database...")
    with get_db_session() as session:
        # Load tax sales
        logger.info("Loading tax sales...")
        tax_loader = TaxSaleLoader()
        tax_stats = tax_loader.bulk_load(session, tax_sales, track_run=True)
        logger.info("Tax sales loaded", extra={"stats": tax_stats})

        # Load foreclosures
        logger.info("Loading foreclosures...")
        foreclosure_loader = ForeclosureLoader()
        fc_stats = foreclosure_loader.bulk_load(session, foreclosures, track_run=True)
        logger.info("Foreclosures loaded", extra={"stats": fc_stats})

    # Print summary
    print("\n" + "=" * 60)
    print("TEST DATA LOADING COMPLETE")
    print("=" * 60)
    print("\nTax Sales:")
    print(f"  Processed: {tax_stats['processed']}")
    print(f"  Inserted: {tax_stats['inserted']}")
    print(f"  Updated: {tax_stats['updated']}")
    print(f"  Failed: {tax_stats['failed']}")

    print("\nForeclosures:")
    print(f"  Processed: {fc_stats['processed']}")
    print(f"  Inserted: {fc_stats['inserted']}")
    print(f"  Updated: {fc_stats['updated']}")
    print(f"  Failed: {fc_stats['failed']}")

    print("\nNext steps:")
    print("1. Start FastAPI: python -m uvicorn src.wholesaler.api.main:app --reload")
    print("2. Start Streamlit: streamlit run src/wholesaler/frontend/app.py")
    print("3. Open browser: http://localhost:8501")


if __name__ == "__main__":
    main()
