"""
Seed-Based Ingestion DAG

Orchestrates the hybrid seed ingestion pipeline:
1. Collect seeds from multiple sources (tax sales, code violations, foreclosures)
2. Enrich seeds using UnifiedEnrichmentPipeline
3. Load enriched seeds to database
4. Merge seeds into properties table
5. Score new seed-based properties

Schedule: Daily at 3:00 AM (runs after daily_property_ingestion)
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
import json

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.wholesaler.db import get_db_session
from src.wholesaler.enrichment import UnifiedEnrichmentPipeline
from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.etl.loaders import EnrichedSeedLoader
from src.wholesaler.etl.seed_merger import SeedMerger
from src.wholesaler.scoring import LeadScorer
from src.wholesaler.db.repository import EnrichedSeedRepository, LeadScoreRepository
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': False,
    'email_on_failure': True,
    'email': ['alerts@wholesaler.com'],
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# File paths
DATA_DIR = Path(__file__).parent.parent / "data"
SEEDS_FILE = DATA_DIR / "processed" / "seeds.json"
ENRICHED_SEEDS_FILE = DATA_DIR / "processed" / "enriched_seeds.parquet"


def collect_seeds(**context):
    """
    Step 1: Collect seeds from all sources.

    Runs IngestionPipeline to collect tax sales, code violations, and foreclosures.

    Returns:
        Dict with seed collection stats
    """
    logger.info("seed_collection_started")

    try:
        from src.wholesaler.ingestion.pipeline import IngestionPipeline

        # Initialize pipeline
        pipeline = IngestionPipeline()

        # Collect seeds (writes to seeds.json)
        stats = pipeline.run(output_path=str(SEEDS_FILE))

        logger.info("seed_collection_completed", stats=stats)

        # Push stats to XCom
        context['task_instance'].xcom_push(key='collection_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("seed_collection_failed", error=str(e))
        raise


def enrich_seeds(**context):
    """
    Step 2: Enrich seeds with property records and code violations.

    Runs UnifiedEnrichmentPipeline to enrich the collected seeds and writes
    `enriched_seeds.parquet` used by downstream loaders.

    Returns:
        Dict with enrichment stats
    """
    logger.info("seed_enrichment_started")

    try:
        if not SEEDS_FILE.exists():
            raise FileNotFoundError(f"{SEEDS_FILE} not found. Run seed collection first.")

        seeds_raw = json.loads(SEEDS_FILE.read_text())
        if not isinstance(seeds_raw, list):
            raise ValueError("Seeds JSON must be a list of records.")

        seeds: List[SeedRecord] = []
        skipped = 0
        for item in seeds_raw:
            seed_type = item.get("seed_type")
            if not seed_type:
                skipped += 1
                continue
            seeds.append(
                SeedRecord(
                    parcel_id=item.get("parcel_id"),
                    seed_type=seed_type,
                    source_payload=item.get("source_payload") or {},
                )
            )

        if not seeds:
            raise ValueError("No valid seeds to enrich.")

        # Initialize pipeline
        pipeline = UnifiedEnrichmentPipeline(
            enable_geo=True,
            geo_csv_path=str(DATA_DIR / "code_enforcement_data.csv"),
        )

        enriched = pipeline.run(seeds)
        df = pd.DataFrame(enriched)
        ENRICHED_SEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(ENRICHED_SEEDS_FILE, index=False)

        stats = {
            'records': len(enriched),
            'output_path': str(ENRICHED_SEEDS_FILE),
            'skipped': skipped,
        }

        logger.info("seed_enrichment_completed", stats=stats)

        # Push stats to XCom
        context['task_instance'].xcom_push(key='enrichment_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("seed_enrichment_failed", error=str(e))
        raise


def load_enriched_seeds_to_db(**context):
    """
    Step 3: Load enriched seeds to database staging table.

    Reads enriched_seeds.parquet and loads to enriched_seeds table.

    Returns:
        Dict with load stats
    """
    logger.info("enriched_seed_loading_started")

    try:
        with get_db_session() as session:
            loader = EnrichedSeedLoader()
            stats = loader.load_from_parquet(
                session=session,
                parquet_path=str(ENRICHED_SEEDS_FILE),
                track_run=True
            )

        logger.info("enriched_seed_loading_completed", stats=stats)

        # Push stats to XCom
        context['task_instance'].xcom_push(key='load_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("enriched_seed_loading_failed", error=str(e))
        raise


def merge_seeds_to_properties(**context):
    """
    Step 4: Merge enriched seeds into properties table.

    Processes unprocessed seeds and merges them into main properties table.

    Returns:
        Dict with merge stats
    """
    logger.info("seed_merge_started")

    try:
        with get_db_session() as session:
            merger = SeedMerger()
            stats = merger.merge_seeds(
                session=session,
                track_run=True
            )

        logger.info("seed_merge_completed", stats=stats)

        # Push stats to XCom
        context['task_instance'].xcom_push(key='merge_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("seed_merge_failed", error=str(e))
        raise


def score_seed_based_properties(**context):
    """
    Step 5: Score newly merged seed-based properties.

    Scores properties that came from seeds and don't have scores yet.

    Returns:
        Dict with scoring stats
    """
    logger.info("seed_scoring_started")

    try:
        from src.wholesaler.db.repository import PropertyRepository
        from sqlalchemy import and_, or_

        stats = {
            'processed': 0,
            'scored': 0,
            'failed': 0,
        }

        with get_db_session() as session:
            # Get seed-based properties without scores
            from src.wholesaler.db.models import Property, LeadScore, EnrichedSeed
            from sqlalchemy import select

            query = select(Property).where(
                and_(
                    Property.seed_type.isnot(None),
                    Property.is_active == True
                )
            ).outerjoin(
                LeadScore,
                Property.parcel_id_normalized == LeadScore.parcel_id_normalized
            ).where(
                or_(
                    LeadScore.id.is_(None),
                    LeadScore.scored_at < Property.updated_at
                )
            ).limit(1000)  # Process in batches

            properties = session.execute(query).scalars().all()

            logger.info("properties_to_score", count=len(properties))

            scorer = LeadScorer()
            score_repo = LeadScoreRepository()
            seed_repo = EnrichedSeedRepository()

            for prop in properties:
                try:
                    # Get primary seed type
                    primary_seed_type = prop.seed_type.split(',')[0]

                    # Get enriched seed data
                    query = select(EnrichedSeed).where(
                        and_(
                            EnrichedSeed.parcel_id_normalized == prop.parcel_id_normalized,
                            EnrichedSeed.seed_type == primary_seed_type
                        )
                    )
                    enriched_seed = session.execute(query).scalar_one_or_none()

                    if not enriched_seed or not enriched_seed.enriched_data:
                        stats['failed'] += 1
                        continue

                    # Score using seed-based method
                    lead_score = scorer.score_seed_based_lead(
                        enriched_data=enriched_seed.enriched_data,
                        seed_type=primary_seed_type
                    )

                    # Save score
                    score_data = {
                        'parcel_id_normalized': prop.parcel_id_normalized,
                        'total_score': lead_score.total_score,
                        'distress_score': lead_score.distress_score,
                        'value_score': lead_score.value_score,
                        'location_score': lead_score.location_score,
                        'urgency_score': lead_score.urgency_score,
                        'tier': lead_score.tier,
                        'reasons': lead_score.reasons,
                        'scored_at': datetime.utcnow()
                    }
                    score_repo.upsert_by_parcel(session, score_data)

                    stats['processed'] += 1
                    stats['scored'] += 1

                except Exception as e:
                    logger.error(
                        "property_scoring_failed",
                        parcel_id=prop.parcel_id_normalized,
                        error=str(e)
                    )
                    stats['failed'] += 1

        logger.info("seed_scoring_completed", stats=stats)

        # Push stats to XCom
        context['task_instance'].xcom_push(key='scoring_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("seed_scoring_failed", error=str(e))
        raise


# Define the DAG
with DAG(
    'seed_based_ingestion',
    default_args=default_args,
    description='Hybrid seed ingestion pipeline for tax sales, code violations, and foreclosures',
    schedule='0 3 * * *',  # Daily at 3:00 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['ingestion', 'seeds', 'hybrid'],
) as dag:

    # Task 1: Collect seeds
    collect_seeds_task = PythonOperator(
        task_id='collect_seeds',
        python_callable=collect_seeds,
    )

    # Task 2: Enrich seeds
    enrich_seeds_task = PythonOperator(
        task_id='enrich_seeds',
        python_callable=enrich_seeds,
    )

    # Task 3: Load to database
    load_to_db_task = PythonOperator(
        task_id='load_enriched_seeds',
        python_callable=load_enriched_seeds_to_db,
    )

    # Task 4: Merge to properties
    merge_seeds_task = PythonOperator(
        task_id='merge_seeds_to_properties',
        python_callable=merge_seeds_to_properties,
    )

    # Task 5: Score new properties
    score_properties_task = PythonOperator(
        task_id='score_seed_properties',
        python_callable=score_seed_based_properties,
    )

    # Define task dependencies
    collect_seeds_task >> enrich_seeds_task >> load_to_db_task >> merge_seeds_task >> score_properties_task
