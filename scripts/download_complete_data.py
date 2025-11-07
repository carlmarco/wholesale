"""
Download Complete Dataset for ML Training

Fetches comprehensive data from Orange County APIs:
- Tax sales (distressed properties)
- Foreclosures (distressed properties)
- Property records (for ARV and enrichment)
- Code violations (optional, for additional distress signals)

This provides sufficient data for training both ARV and lead qualification models.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper
from src.wholesaler.scrapers.property_scraper import PropertyScraper
from src.wholesaler.scrapers.code_violation_scraper import CodeViolationScraper
from src.wholesaler.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def main():
    """Download complete dataset for ML training."""
    logger.info("Starting complete data download...")

    data_dir = Path(__file__).parent.parent / "data" / "test"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Download tax sales (distressed properties)
    logger.info("Fetching tax sales...")
    tax_sale_scraper = TaxSaleScraper()
    tax_sales = tax_sale_scraper.fetch_properties(limit=100)

    tax_sales_file = data_dir / "tax_sales.json"
    with open(tax_sales_file, 'w') as f:
        json.dump([ts.model_dump() for ts in tax_sales], f, indent=2, default=str)
    logger.info(f"Saved {len(tax_sales)} tax sales to {tax_sales_file}")

    # 2. Download foreclosures (distressed properties)
    logger.info("Fetching foreclosures...")
    foreclosure_scraper = ForeclosureScraper()
    foreclosures = foreclosure_scraper.fetch_foreclosures(limit=100)

    foreclosures_file = data_dir / "foreclosures.json"
    with open(foreclosures_file, 'w') as f:
        json.dump([fc.model_dump() for fc in foreclosures], f, indent=2, default=str)
    logger.info(f"Saved {len(foreclosures)} foreclosures to {foreclosures_file}")

    # 3. Download property records (for ARV and enrichment)
    # Fetch properties for all parcels we found in tax sales and foreclosures
    logger.info("Fetching property records...")
    property_scraper = PropertyScraper()

    # Get unique parcel numbers from tax sales and foreclosures
    parcel_numbers = set()
    for ts in tax_sales:
        if ts.parcel_id:
            parcel_numbers.add(ts.parcel_id)
    for fc in foreclosures:
        if fc.parcel_number:
            parcel_numbers.add(fc.parcel_number)

    logger.info(f"Found {len(parcel_numbers)} unique parcels to enrich")

    # Fetch property records in batches
    properties = []
    batch_size = 50
    parcel_list = list(parcel_numbers)

    for i in range(0, len(parcel_list), batch_size):
        batch = parcel_list[i:i+batch_size]
        logger.info(f"Fetching property batch {i//batch_size + 1}/{(len(parcel_list)-1)//batch_size + 1}")
        batch_properties = property_scraper.fetch_properties(parcel_numbers=batch)
        properties.extend(batch_properties)

    properties_file = data_dir / "properties.json"
    with open(properties_file, 'w') as f:
        json.dump([p.model_dump() for p in properties], f, indent=2, default=str)
    logger.info(f"Saved {len(properties)} property records to {properties_file}")

    # 4. Download code violations (optional - for additional distress signals)
    logger.info("Fetching code violations...")
    violation_scraper = CodeViolationScraper()
    violations_df = violation_scraper.fetch_violations(limit=200)

    violations_file = data_dir / "code_violations.csv"
    violations_df.to_csv(violations_file, index=False)
    logger.info(f"Saved {len(violations_df)} code violations to {violations_file}")

    # Print summary
    print("\n" + "="*80)
    print("DATA DOWNLOAD COMPLETE")
    print("="*80)
    print(f"\nDownloaded:")
    print(f"  - {len(tax_sales)} tax sales")
    print(f"  - {len(foreclosures)} foreclosures")
    print(f"  - {len(properties)} property records")
    print(f"  - {len(violations_df)} code violations")
    print(f"\nTotal unique parcels: {len(parcel_numbers)}")
    print(f"\nFiles saved to: {data_dir}")
    print("\nNext step:")
    print("  python scripts/load_complete_data.py")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
