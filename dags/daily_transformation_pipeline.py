"""
Daily Transformation Pipeline DAG

Enriches properties with geographic data and deduplicates across sources.

Schedule: Daily at 3:00 AM (after ingestion completes)
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.dates import days_ago

from src.wholesaler.enrichers.geographic_enricher import GeographicEnricher
from src.wholesaler.transformers.deduplicator import PropertyDeduplicator
from src.wholesaler.etl import PropertyLoader, PropertyRecordLoader
from src.wholesaler.db import PropertyRepository, get_db_session
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


def fetch_properties_for_enrichment(**context):
    """
    Fetch properties from database that need enrichment.

    Returns:
        List of properties missing coordinates or property records
    """
    logger.info("fetching_properties_for_enrichment")

    with get_db_session() as session:
        repo = PropertyRepository()

        # Get properties without coordinates
        properties_without_coords = repo.get_all(session, limit=10000)
        properties_needing_enrichment = [
            p for p in properties_without_coords
            if p.latitude is None or p.longitude is None
        ]

        logger.info("properties_fetched_for_enrichment",
                    count=len(properties_needing_enrichment))

        # Store property IDs for downstream tasks
        property_ids = [p.parcel_id_normalized for p in properties_needing_enrichment]
        context['task_instance'].xcom_push(key='property_ids', value=property_ids)

        return len(properties_needing_enrichment)


def enrich_properties(**context):
    """
    Enrich properties with geographic data (coordinates, nearby violations).

    Processes properties from the database and updates them with enriched data.
    """
    ti = context['task_instance']
    property_ids = ti.xcom_pull(task_ids='fetch_properties', key='property_ids')

    if not property_ids:
        logger.info("no_properties_to_enrich")
        return {'processed': 0, 'enriched': 0, 'failed': 0}

    logger.info("property_enrichment_started", count=len(property_ids))

    enricher = GeographicEnricher()
    stats = {'processed': 0, 'enriched': 0, 'failed': 0}

    with get_db_session() as session:
        repo = PropertyRepository()
        loader = PropertyLoader()

        for parcel_id in property_ids:
            try:
                # Get property from database
                property_obj = repo.get_by_parcel(session, parcel_id)
                if not property_obj:
                    logger.warning("property_not_found", parcel_id=parcel_id)
                    stats['failed'] += 1
                    continue

                # Convert to TaxSaleProperty for enrichment
                from src.wholesaler.models.property import TaxSaleProperty
                tax_sale_prop = TaxSaleProperty(
                    parcel_id=property_obj.parcel_id_original,
                    tda_number=None,
                    situs_address=property_obj.situs_address,
                    city=property_obj.city,
                    state=property_obj.state,
                    zip_code=property_obj.zip_code,
                )

                # Enrich property
                enriched = enricher.enrich_property(tax_sale_prop)

                if enriched:
                    # Update property with enriched data
                    property_data = loader.load_from_enriched(session, enriched)
                    repo.upsert(session, property_data)
                    stats['enriched'] += 1
                else:
                    stats['failed'] += 1

                stats['processed'] += 1

            except Exception as e:
                logger.error("property_enrichment_failed",
                             parcel_id=parcel_id, error=str(e))
                stats['failed'] += 1

        session.commit()

    logger.info("property_enrichment_completed", stats=stats)
    context['task_instance'].xcom_push(key='enrichment_stats', value=stats)

    return stats


def deduplicate_properties(**context):
    """
    Deduplicate properties across tax sales and foreclosures.

    Identifies duplicate properties and merges their data.
    """
    logger.info("property_deduplication_started")

    deduplicator = PropertyDeduplicator()
    stats = {'processed': 0, 'duplicates_found': 0, 'merged': 0}

    with get_db_session() as session:
        repo = PropertyRepository()

        # Get all active properties
        properties = repo.get_active_properties(session)
        logger.info("properties_loaded_for_deduplication", count=len(properties))

        # Group properties by normalized address
        address_groups = {}
        for prop in properties:
            address_key = deduplicator._normalize_address(prop.situs_address or "")
            if address_key not in address_groups:
                address_groups[address_key] = []
            address_groups[address_key].append(prop)

        # Find and merge duplicates
        for address_key, props in address_groups.items():
            stats['processed'] += len(props)

            if len(props) > 1:
                stats['duplicates_found'] += len(props) - 1

                # Keep the first property, mark others as duplicates
                primary_prop = props[0]
                for duplicate_prop in props[1:]:
                    logger.info("duplicate_property_found",
                                primary=primary_prop.parcel_id_normalized,
                                duplicate=duplicate_prop.parcel_id_normalized)

                    # Soft delete duplicate
                    repo.soft_delete(session, duplicate_prop.parcel_id_normalized)
                    stats['merged'] += 1

        session.commit()

    logger.info("property_deduplication_completed", stats=stats)
    context['task_instance'].xcom_push(key='dedup_stats', value=stats)

    return stats


def validate_transformation(**context):
    """
    Validate that transformation pipeline completed successfully.
    """
    ti = context['task_instance']

    enrichment_stats = ti.xcom_pull(task_ids='enrich_properties', key='enrichment_stats')
    dedup_stats = ti.xcom_pull(task_ids='deduplicate_properties', key='dedup_stats')

    logger.info("transformation_validation_started",
                enrichment_stats=enrichment_stats,
                dedup_stats=dedup_stats)

    # Check enrichment success rate
    if enrichment_stats:
        processed = enrichment_stats.get('processed', 0)
        failed = enrichment_stats.get('failed', 0)

        if processed > 0:
            failure_rate = failed / processed
            if failure_rate > 0.5:
                logger.warning("high_enrichment_failure_rate", failure_rate=failure_rate)

    # Check deduplication
    if dedup_stats:
        duplicates = dedup_stats.get('duplicates_found', 0)
        logger.info("duplicates_removed", count=duplicates)

    logger.info("transformation_validation_passed")


# Define the DAG
with DAG(
    'daily_transformation_pipeline',
    default_args=default_args,
    description='Daily enrichment and deduplication of property data',
    schedule_interval='0 3 * * *',  # 3:00 AM daily (1 hour after ingestion)
    start_date=days_ago(1),
    catchup=False,
    tags=['transformation', 'enrichment', 'deduplication', 'etl'],
) as dag:

    # Wait for ingestion DAG to complete
    wait_for_ingestion = ExternalTaskSensor(
        task_id='wait_for_ingestion',
        external_dag_id='daily_property_ingestion',
        external_task_id='validate_ingestion',
        timeout=3600,  # 1 hour timeout
        mode='reschedule',
    )

    # Task 1: Fetch properties needing enrichment
    fetch_properties_task = PythonOperator(
        task_id='fetch_properties',
        python_callable=fetch_properties_for_enrichment,
        provide_context=True,
    )

    # Task 2: Enrich properties with geographic data
    enrich_properties_task = PythonOperator(
        task_id='enrich_properties',
        python_callable=enrich_properties,
        provide_context=True,
    )

    # Task 3: Deduplicate properties
    deduplicate_task = PythonOperator(
        task_id='deduplicate_properties',
        python_callable=deduplicate_properties,
        provide_context=True,
    )

    # Task 4: Validate transformation
    validate_task = PythonOperator(
        task_id='validate_transformation',
        python_callable=validate_transformation,
        provide_context=True,
    )

    # Define dependencies
    wait_for_ingestion >> fetch_properties_task >> enrich_properties_task >> deduplicate_task >> validate_task
