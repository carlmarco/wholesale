"""
CLI script to merge enriched seeds from staging table into properties table.
"""
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import SessionLocal
from src.wholesaler.etl.seed_merger import SeedMerger
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Run seed merge operation."""
    merger = SeedMerger()

    with SessionLocal() as session:
        logger.info("starting_seed_merge")

        # Merge all unprocessed seeds
        stats = merger.merge_seeds(
            session=session,
            seed_type=None,  # Process all types
            limit=None,  # No limit
            track_run=True
        )

        logger.info("seed_merge_complete", stats=stats)
        print(f"\n{'='*60}")
        print("SEED MERGE RESULTS")
        print(f"{'='*60}")
        print(f"Processed: {stats['processed']:,}")
        print(f"Created:   {stats['created']:,}")
        print(f"Updated:   {stats['updated']:,}")
        print(f"Failed:    {stats['failed']:,}")
        print(f"{'='*60}\n")

        # Get merge statistics
        merge_stats = merger.get_merge_stats(session)
        print(f"\n{'='*60}")
        print("PROPERTIES BY SEED TYPE")
        print(f"{'='*60}")
        for seed_type, count in merge_stats['properties_by_seed_type'].items():
            print(f"{seed_type}: {count:,}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
