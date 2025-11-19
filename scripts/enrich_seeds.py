"""
CLI helper to enrich collected seeds (and optionally load into the database).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Add parent directory to Python path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.wholesaler.enrichment import UnifiedEnrichmentPipeline
from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich candidate seeds with violation metrics and optional geo features.")
    parser.add_argument("--seeds-path", default="data/processed/seeds.json", help="Path to raw seed JSON produced by `make ingest-seeds`.")
    parser.add_argument("--output", default="data/processed/enriched_seeds.parquet", help="Destination parquet file.")
    parser.add_argument("--load", action="store_true", help="Load the enriched parquet into the database after writing it.")
    parser.add_argument("--disable-geo", action="store_true", help="Skip GeoPropertyEnricher (enabled by default).")
    parser.add_argument("--geo-csv", dest="geo_csv_path", help="Override code enforcement CSV for geo enrichment.")
    parser.add_argument("--geo-radius", dest="geo_radius", type=float, help="Radius (miles) for geo enrichment override.")
    return parser.parse_args()


def main():
    args = parse_args()

    seeds_path = Path(args.seeds_path)
    output_path = Path(args.output)

    if not seeds_path.exists():
        raise FileNotFoundError(f"{seeds_path} not found. Run `make ingest-seeds` first.")

    seeds_raw = json.loads(seeds_path.read_text())
    if not isinstance(seeds_raw, list):
        raise ValueError("Seeds JSON must be a list of records.")

    seeds = [
        SeedRecord(
            parcel_id=item.get("parcel_id"),
            seed_type=item["seed_type"],
            source_payload=item.get("source_payload") or {},
        )
        for item in seeds_raw
    ]

    pipeline = UnifiedEnrichmentPipeline(
        enable_geo=not args.disable_geo,
        geo_csv_path=args.geo_csv_path,
        geo_radius_miles=args.geo_radius,
    )

    enriched = pipeline.run(seeds)
    df = pd.DataFrame(enriched)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    logger.info("enriched_dataset_written", path=str(output_path), records=len(df))

    if args.load:
        from src.wholesaler.db.session import get_db_session
        from src.wholesaler.etl.loaders import EnrichedSeedLoader

        loader = EnrichedSeedLoader()
        with get_db_session() as session:
            stats = loader.load_from_parquet(session, str(output_path))
        logger.info("enriched_dataset_loaded", stats=stats)
        print(
            "\nEnriched seeds loaded:\n"
            f"  Processed: {stats['processed']}\n"
            f"  Inserted:  {stats['inserted']}\n"
            f"  Failed:    {stats['failed']}\n"
        )


if __name__ == "__main__":
    main()
