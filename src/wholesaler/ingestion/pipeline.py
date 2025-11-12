"""
Unified ingestion pipeline for collecting candidate properties from multiple sources.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional
import json
import argparse

from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper
from src.wholesaler.scrapers.code_violation_scraper import CodeViolationScraper
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class IngestionPipeline:
    """Collects seed records from configured data sources."""

    def __init__(
        self,
        tax_sale_scraper: TaxSaleScraper | None = None,
        foreclosure_scraper: ForeclosureScraper | None = None,
        code_violation_scraper: CodeViolationScraper | None = None,
    ):
        self.tax_sale_scraper = tax_sale_scraper or TaxSaleScraper()
        self.foreclosure_scraper = foreclosure_scraper or ForeclosureScraper()
        self.code_violation_scraper = code_violation_scraper or CodeViolationScraper()

    def collect_tax_sale_seeds(self, limit: Optional[int] = None) -> List[SeedRecord]:
        properties = self.tax_sale_scraper.fetch_properties(limit=limit)
        seeds: List[SeedRecord] = []
        for record in properties:
            seeds.append(
                SeedRecord(
                    parcel_id=record.parcel_id,
                    seed_type="tax_sale",
                    source_payload=record.to_dict(),
                )
            )
        logger.info("tax_sale_seeds_collected", count=len(seeds))
        return seeds

    def collect_foreclosure_seeds(self, limit: Optional[int] = None) -> List[SeedRecord]:
        properties = self.foreclosure_scraper.fetch_properties(limit=limit)
        seeds: List[SeedRecord] = []
        for record in properties:
            seeds.append(
                SeedRecord(
                    parcel_id=record.parcel_number,
                    seed_type="foreclosure",
                    source_payload=record.to_dict(),
                )
            )
        logger.info("foreclosure_seeds_collected", count=len(seeds))
        return seeds

    def collect_code_violation_seeds(self, limit: Optional[int] = None) -> List[SeedRecord]:
        df = self.code_violation_scraper.fetch_violations(limit=limit)
        seeds: List[SeedRecord] = []
        if df.empty:
            logger.warning("code_violation_fetch_empty")
            return seeds

        for _, row in df.iterrows():
            seeds.append(
                SeedRecord(
                    parcel_id=row.get("parcel_id"),
                    seed_type="code_violation",
                    source_payload=row.to_dict(),
                )
            )
        logger.info("code_violation_seeds_collected", count=len(seeds))
        return seeds

    def run(self, sources: Iterable[str], output_path: Optional[Path] = None, limit: Optional[int] = None) -> List[SeedRecord]:
        """Collect seeds from selected sources."""
        collection_map = {
            "tax_sales": self.collect_tax_sale_seeds,
            "foreclosures": self.collect_foreclosure_seeds,
            "code_violations": self.collect_code_violation_seeds,
        }

        normalized_sources = []
        for src in sources:
            if src not in collection_map:
                raise ValueError(f"Unknown source '{src}'. Valid options: {', '.join(collection_map)}")
            normalized_sources.append(src)

        all_records: List[SeedRecord] = []
        for src in normalized_sources:
            collector = collection_map[src]
            all_records.extend(collector(limit=limit))

        logger.info("total_seeds_collected", count=len(all_records), sources=normalized_sources)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump([seed.to_dict() for seed in all_records], f, indent=2)
            logger.info("seeds_written", path=str(output_path))

        return all_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified data ingestion pipeline")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["tax_sales", "foreclosures", "code_violations"],
        default=["tax_sales", "foreclosures", "code_violations"],
        help="Data sources to ingest",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional limit per source")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/seeds.json"),
        help="Where to write collected seed records",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    pipeline = IngestionPipeline()
    pipeline.run(sources=args.sources, output_path=args.output, limit=args.limit)
