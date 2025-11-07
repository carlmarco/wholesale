"""
Download Test Data from Orange County APIs

Downloads a small sample of real data for testing:
- 20 tax sale properties
- 20 foreclosure properties

Data is saved to JSON files for inspection before loading into database.
"""
import sys
import json
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Download test data from APIs."""
    logger.info("Starting test data download...")

    # Create data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Download tax sales
    logger.info("Fetching tax sale properties...")
    tax_scraper = TaxSaleScraper()
    tax_sales = tax_scraper.fetch_properties(limit=20)
    logger.info(f"Downloaded {len(tax_sales)} tax sale properties")

    # Download foreclosures
    logger.info("Fetching foreclosure properties...")
    foreclosure_scraper = ForeclosureScraper()
    foreclosures = foreclosure_scraper.fetch_properties(limit=20)
    logger.info(f"Downloaded {len(foreclosures)} foreclosure properties")

    # Save to JSON files
    tax_file = data_dir / "test_tax_sales.json"
    with open(tax_file, "w") as f:
        json.dump([p.model_dump() for p in tax_sales], f, indent=2, default=str)
    logger.info(f"Saved tax sales to {tax_file}")

    fc_file = data_dir / "test_foreclosures.json"
    with open(fc_file, "w") as f:
        json.dump([p.model_dump() for p in foreclosures], f, indent=2, default=str)
    logger.info(f"Saved foreclosures to {fc_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("TEST DATA DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"Tax Sales: {len(tax_sales)} properties")
    print(f"Foreclosures: {len(foreclosures)} properties")
    print(f"\nFiles saved to:")
    print(f"  - {tax_file}")
    print(f"  - {fc_file}")
    print("\nNext step: Run scripts/load_test_data.py to load into database")


if __name__ == "__main__":
    main()
