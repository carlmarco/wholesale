"""
Generate simple data-quality report for the latest seeds file.
"""
from pathlib import Path
import json

from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.monitoring.data_quality import compute_seed_metrics
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    seeds_path = Path("data/processed/seeds.json")
    if not seeds_path.exists():
        raise FileNotFoundError("Seeds file not found. Run `make ingest-seeds` first.")

    seeds_data = json.loads(seeds_path.read_text())
    seeds = [
        SeedRecord(parcel_id=item.get("parcel_id"), seed_type=item["seed_type"], source_payload=item["source_payload"])
        for item in seeds_data
    ]

    metrics = compute_seed_metrics(seeds)
    counts = metrics["counts"]
    with_parcel = metrics["with_parcel_id"]

    logger.info("seed_counts", **counts)
    logger.info("seed_with_parcel_ids", **with_parcel)

    print("Seed counts:")
    for seed_type, count in counts.items():
        print(f"  {seed_type}: {count}")

    print("\nSeeds with parcel IDs:")
    for seed_type, count in with_parcel.items():
        print(f"  {seed_type}: {count}")


if __name__ == "__main__":
    main()
