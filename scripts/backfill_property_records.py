"""
Backfill Property Records Script

One-time script to fetch property records for all existing properties in the database.
This populates the property_records table with valuation and ownership data needed for lead scoring.

Usage:
    python scripts/backfill_property_records.py [--batch-size 100] [--dry-run]
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
from typing import List
import time

from src.wholesaler.scrapers.property_scraper import PropertyScraper
from src.wholesaler.etl import PropertyRecordLoader
from src.wholesaler.db import get_db_session
from src.wholesaler.db.models import Property, PropertyRecord
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def get_parcels_needing_records(session, batch_size: int = None) -> List[str]:
    """
    Get list of parcel IDs that don't have property records yet.

    Args:
        session: Database session
        batch_size: Max number of parcels to return (None for all)

    Returns:
        List of parcel ID strings
    """
    # Query properties that don't have property records
    query = (
        session.query(Property.parcel_id_normalized)
        .outerjoin(PropertyRecord, Property.parcel_id_normalized == PropertyRecord.parcel_id_normalized)
        .filter(PropertyRecord.parcel_id_normalized == None)
        .filter(Property.parcel_id_normalized != None)
    )

    if batch_size:
        query = query.limit(batch_size)

    parcels = query.all()
    return [p.parcel_id_normalized for p in parcels]


def backfill_property_records(batch_size: int = 100, dry_run: bool = False):
    """
    Backfill property records for all existing properties.

    Args:
        batch_size: Number of records to fetch per batch
        dry_run: If True, only print what would be done without making changes
    """
    logger.info("backfill_property_records_started", batch_size=batch_size, dry_run=dry_run)

    total_processed = 0
    total_inserted = 0
    total_updated = 0
    total_failed = 0

    while True:
        # Get batch of parcels needing records
        with get_db_session() as session:
            parcel_ids = get_parcels_needing_records(session, batch_size=batch_size)

        if not parcel_ids:
            logger.info("no_more_parcels_to_process")
            break

        logger.info("processing_batch", count=len(parcel_ids))

        if dry_run:
            logger.info("dry_run_mode_would_fetch", parcels=parcel_ids[:5])
            break

        try:
            # Fetch property records for this batch
            scraper = PropertyScraper()
            property_records = scraper.fetch_properties(parcel_numbers=parcel_ids)

            logger.info("batch_fetched", scraped=len(property_records), requested=len(parcel_ids))

            # Load to database
            with get_db_session() as session:
                loader = PropertyRecordLoader()
                stats = loader.bulk_load(session, property_records, track_run=True)

                total_processed += stats.get('processed', 0)
                total_inserted += stats.get('inserted', 0)
                total_updated += stats.get('updated', 0)
                total_failed += stats.get('failed', 0)

            logger.info("batch_loaded", stats=stats)

            # Small delay to avoid overwhelming API
            time.sleep(2)

        except Exception as e:
            logger.error("batch_failed", error=str(e), parcel_count=len(parcel_ids))
            total_failed += len(parcel_ids)
            # Continue to next batch

    # Final summary
    summary = {
        'total_processed': total_processed,
        'total_inserted': total_inserted,
        'total_updated': total_updated,
        'total_failed': total_failed
    }

    logger.info("backfill_completed", summary=summary)
    print("\n" + "="*60)
    print("BACKFILL SUMMARY")
    print("="*60)
    print(f"Total Processed: {total_processed}")
    print(f"Total Inserted:  {total_inserted}")
    print(f"Total Updated:   {total_updated}")
    print(f"Total Failed:    {total_failed}")
    print("="*60 + "\n")

    return summary


def main():
    """Main entry point for backfill script."""
    parser = argparse.ArgumentParser(
        description="Backfill property records for existing properties"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of records to process per batch (default: 100)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without making changes'
    )

    args = parser.parse_args()

    print("\n" + "="*60)
    print("PROPERTY RECORDS BACKFILL SCRIPT")
    print("="*60)
    print(f"Batch Size: {args.batch_size}")
    print(f"Dry Run: {args.dry_run}")
    print("="*60 + "\n")

    if args.dry_run:
        print("*** DRY RUN MODE - No changes will be made ***\n")

    try:
        backfill_property_records(
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        print("\n✓ Backfill completed successfully!\n")

    except KeyboardInterrupt:
        print("\n\n! Backfill interrupted by user\n")
        logger.warning("backfill_interrupted_by_user")

    except Exception as e:
        print(f"\n\n✗ Backfill failed: {e}\n")
        logger.error("backfill_failed", error=str(e))
        raise


if __name__ == "__main__":
    main()
