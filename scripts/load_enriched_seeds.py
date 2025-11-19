"""
CLI helper to load enriched seeds to database.
"""
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.etl.loaders import EnrichedSeedLoader
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    enriched_path = Path("data/processed/enriched_seeds.parquet")

    if not enriched_path.exists():
        raise FileNotFoundError(f"{enriched_path} not found. Run `make enrich-seeds` first.")

    loader = EnrichedSeedLoader()

    with get_db_session() as session:
        stats = loader.load_from_parquet(session, str(enriched_path))
        logger.info("load_complete", stats=stats)
        print(f"\nEnriched seeds loaded successfully:")
        print(f"  Processed: {stats['processed']}")
        print(f"  Inserted:  {stats['inserted']}")
        print(f"  Failed:    {stats['failed']}")


if __name__ == "__main__":
    main()
