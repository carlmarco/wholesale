"""
Daily Lead Scoring DAG

Scores properties and ranks them as A/B/C/D tier leads.

Schedule: Daily at 4:00 AM (after transformation completes)
"""
from datetime import datetime, timedelta, date
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.dates import days_ago

from src.wholesaler.pipelines.lead_scorer import LeadScorer
from src.wholesaler.etl import LeadScoreLoader
from src.wholesaler.db import PropertyRepository, LeadScoreRepository, get_db_session
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': True,  # Wait for previous run to complete
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=1),
}


def fetch_properties_for_scoring(**context):
    """
    Fetch all active properties from database for scoring.

    Returns:
        Count of properties to score
    """
    logger.info("fetching_properties_for_scoring")

    with get_db_session() as session:
        repo = PropertyRepository()

        # Get all active properties with coordinates
        properties = repo.get_with_coordinates(session)

        logger.info("properties_fetched_for_scoring", count=len(properties))

        # Store property IDs for downstream tasks
        property_ids = [p.parcel_id_normalized for p in properties]
        context['task_instance'].xcom_push(key='property_ids', value=property_ids)

        return len(properties)


def score_all_leads(**context):
    """
    Score all properties and calculate A/B/C/D tiers.

    Processes all active properties and saves lead scores to database.
    """
    ti = context['task_instance']
    property_ids = ti.xcom_pull(task_ids='fetch_properties', key='property_ids')

    if not property_ids:
        logger.info("no_properties_to_score")
        return {'processed': 0, 'scored': 0, 'failed': 0}

    logger.info("lead_scoring_started", count=len(property_ids))

    scorer = LeadScorer()
    stats = {'processed': 0, 'scored': 0, 'failed': 0}
    scored_leads = []

    with get_db_session() as session:
        property_repo = PropertyRepository()

        for parcel_id in property_ids:
            try:
                # Get property from database
                property_obj = property_repo.get_by_parcel(session, parcel_id)
                if not property_obj:
                    logger.warning("property_not_found_for_scoring", parcel_id=parcel_id)
                    stats['failed'] += 1
                    continue

                # Convert to EnrichedProperty for scoring
                from src.wholesaler.models.property import EnrichedProperty
                enriched_prop = EnrichedProperty(
                    parcel_id=property_obj.parcel_id_original,
                    tda_number=None,
                    situs_address=property_obj.situs_address,
                    city=property_obj.city,
                    state=property_obj.state,
                    zip_code=property_obj.zip_code,
                    latitude=property_obj.latitude,
                    longitude=property_obj.longitude,
                    nearby_violations=[],  # Would be loaded from DB if needed
                )

                # Score the lead
                lead_score = scorer.score_lead(enriched_prop)

                if lead_score:
                    scored_leads.append((enriched_prop, lead_score))
                    stats['scored'] += 1
                else:
                    stats['failed'] += 1

                stats['processed'] += 1

            except Exception as e:
                logger.error("lead_scoring_failed",
                             parcel_id=parcel_id, error=str(e))
                stats['failed'] += 1

    # Rank leads (assigns tiers A/B/C/D)
    ranked_leads = scorer.rank_leads(scored_leads)

    # Load scored leads to database
    with get_db_session() as session:
        loader = LeadScoreLoader()
        load_stats = loader.bulk_load(
            session,
            ranked_leads,
            create_history=True,
            track_run=True
        )

        logger.info("lead_scores_loaded", load_stats=load_stats)

    logger.info("lead_scoring_completed", stats=stats)
    context['task_instance'].xcom_push(key='scoring_stats', value=stats)

    return stats


def create_history_snapshots(**context):
    """
    Create daily history snapshots for all lead scores.

    Tracks how scores change over time for trending analysis.
    """
    logger.info("history_snapshot_creation_started")

    stats = {'snapshots_created': 0, 'failed': 0}
    snapshot_date = date.today()

    with get_db_session() as session:
        lead_repo = LeadScoreRepository()

        # Get all lead scores
        all_scores = lead_repo.get_all(session, limit=100000)

        logger.info("creating_history_snapshots", count=len(all_scores))

        for lead_score in all_scores:
            try:
                lead_repo.create_history_snapshot(
                    session,
                    lead_score.id,
                    snapshot_date=snapshot_date
                )
                stats['snapshots_created'] += 1
            except Exception as e:
                logger.error("snapshot_creation_failed",
                             lead_score_id=lead_score.id, error=str(e))
                stats['failed'] += 1

        session.commit()

    logger.info("history_snapshot_creation_completed", stats=stats)
    context['task_instance'].xcom_push(key='snapshot_stats', value=stats)

    return stats


def calculate_tier_statistics(**context):
    """
    Calculate and log tier distribution statistics.

    Provides insights into lead quality distribution.
    """
    logger.info("calculating_tier_statistics")

    with get_db_session() as session:
        repo = LeadScoreRepository()

        # Get tier counts
        tier_counts = repo.get_tier_counts(session)

        # Calculate percentages
        total = sum(tier_counts.values())
        tier_percentages = {
            tier: (count / total * 100) if total > 0 else 0
            for tier, count in tier_counts.items()
        }

        stats = {
            'tier_counts': tier_counts,
            'tier_percentages': tier_percentages,
            'total_leads': total,
        }

        logger.info("tier_statistics_calculated", stats=stats)

        # Push to XCom for alerting
        context['task_instance'].xcom_push(key='tier_stats', value=stats)

        return stats


def validate_scoring(**context):
    """
    Validate that lead scoring completed successfully.
    """
    ti = context['task_instance']

    scoring_stats = ti.xcom_pull(task_ids='score_leads', key='scoring_stats')
    snapshot_stats = ti.xcom_pull(task_ids='create_snapshots', key='snapshot_stats')
    tier_stats = ti.xcom_pull(task_ids='calculate_statistics', key='tier_stats')

    logger.info("scoring_validation_started",
                scoring_stats=scoring_stats,
                snapshot_stats=snapshot_stats,
                tier_stats=tier_stats)

    # Check scoring success rate
    if scoring_stats:
        processed = scoring_stats.get('processed', 0)
        failed = scoring_stats.get('failed', 0)

        if processed > 0:
            failure_rate = failed / processed
            if failure_rate > 0.5:
                logger.warning("high_scoring_failure_rate", failure_rate=failure_rate)

    # Check that we have Tier A leads
    if tier_stats:
        tier_counts = tier_stats.get('tier_counts', {})
        tier_a_count = tier_counts.get('A', 0)

        logger.info("tier_a_leads_available", count=tier_a_count)

        if tier_a_count == 0:
            logger.warning("no_tier_a_leads_found")

    logger.info("scoring_validation_passed")


# Define the DAG
with DAG(
    'daily_lead_scoring',
    default_args=default_args,
    description='Daily lead scoring and ranking of properties',
    schedule_interval='0 4 * * *',  # 4:00 AM daily (1 hour after transformation)
    start_date=days_ago(1),
    catchup=False,
    tags=['scoring', 'leads', 'ranking', 'etl'],
) as dag:

    # Wait for transformation DAG to complete
    wait_for_transformation = ExternalTaskSensor(
        task_id='wait_for_transformation',
        external_dag_id='daily_transformation_pipeline',
        external_task_id='validate_transformation',
        timeout=3600,  # 1 hour timeout
        mode='reschedule',
    )

    # Task 1: Fetch properties for scoring
    fetch_properties_task = PythonOperator(
        task_id='fetch_properties',
        python_callable=fetch_properties_for_scoring,
        provide_context=True,
    )

    # Task 2: Score all leads
    score_leads_task = PythonOperator(
        task_id='score_leads',
        python_callable=score_all_leads,
        provide_context=True,
    )

    # Task 3: Create history snapshots
    create_snapshots_task = PythonOperator(
        task_id='create_snapshots',
        python_callable=create_history_snapshots,
        provide_context=True,
    )

    # Task 4: Calculate tier statistics
    calculate_statistics_task = PythonOperator(
        task_id='calculate_statistics',
        python_callable=calculate_tier_statistics,
        provide_context=True,
    )

    # Task 5: Validate scoring
    validate_task = PythonOperator(
        task_id='validate_scoring',
        python_callable=validate_scoring,
        provide_context=True,
    )

    # Define dependencies
    wait_for_transformation >> fetch_properties_task >> score_leads_task >> create_snapshots_task >> calculate_statistics_task >> validate_task
