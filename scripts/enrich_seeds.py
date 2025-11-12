"""
CLI helper to enrich collected seeds.
"""
import sys
from pathlib import Path
import json
import pandas as pd

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.pipelines.enrichment import UnifiedEnrichmentPipeline
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    seeds_path = Path("data/processed/seeds.json")
    output_path = Path("data/processed/enriched_seeds.parquet")

    if not seeds_path.exists():
        raise FileNotFoundError(f"{seeds_path} not found. Run `make ingest-seeds` first.")

    seeds_data = json.loads(seeds_path.read_text())
    seeds = [SeedRecord(parcel_id=item.get("parcel_id"), seed_type=item["seed_type"], source_payload=item["source_payload"]) for item in seeds_data]

    pipeline = UnifiedEnrichmentPipeline()
    enriched = pipeline.run(seeds)
    df = pd.DataFrame(enriched)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)

    logger.info("enriched_dataset_written", path=str(output_path), records=len(df))


if __name__ == "__main__":
    main()
