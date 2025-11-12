"""
Daily Property Ingestion DAG

Scrapes tax sales and foreclosures from ArcGIS APIs and loads them into the database.

Schedule: Daily at 2:00 AM
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper
from src.wholesaler.scrapers.property_scraper import PropertyScraper
from src.wholesaler.scrapers.code_violation_scraper import CodeViolationScraper
from src.wholesaler.etl import TaxSaleLoader, ForeclosureLoader, PropertyRecordLoader
from src.wholesaler.db import get_db_session
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=30),
}


def scrape_and_load_tax_sales(**context):
    """
    Scrape tax sales from ArcGIS API and load into database.

    Returns:
        Dict with stats (processed, inserted, updated, failed)
    """
    logger.info("tax_sale_ingestion_started")

    try:
        # Scrape tax sales
        scraper = TaxSaleScraper()
        tax_sales = scraper.fetch_properties()
        logger.info("tax_sales_scraped", count=len(tax_sales))

        # Load to database
        with get_db_session() as session:
            loader = TaxSaleLoader()
            stats = loader.bulk_load(session, tax_sales, track_run=True)

        logger.info("tax_sale_ingestion_completed", stats=stats)

        # Push stats to XCom for downstream tasks
        context['task_instance'].xcom_push(key='tax_sale_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("tax_sale_ingestion_failed", error=str(e))
        raise


def scrape_and_load_foreclosures(**context):
    """
    Scrape foreclosures from ArcGIS API and load into database.

    Returns:
        Dict with stats (processed, inserted, updated, failed)
    """
    logger.info("foreclosure_ingestion_started")

    try:
        # Scrape foreclosures
        scraper = ForeclosureScraper()
        foreclosures = scraper.fetch_properties()
        logger.info("foreclosures_scraped", count=len(foreclosures))

        # Load to database
        with get_db_session() as session:
            loader = ForeclosureLoader()
            stats = loader.bulk_load(session, foreclosures, track_run=True)

        logger.info("foreclosure_ingestion_completed", stats=stats)

        # Push stats to XCom for downstream tasks
        context['task_instance'].xcom_push(key='foreclosure_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("foreclosure_ingestion_failed", error=str(e))
        raise


def scrape_and_load_property_records(**context):
    """
    Scrape property records from ArcGIS API and load into database.

    Fetches property records for parcels that exist in database from tax sales or foreclosures.

    Returns:
        Dict with stats (processed, inserted, updated, failed)
    """
    logger.info("property_record_ingestion_started")

    try:
        # Get existing parcel IDs from database to enrich
        with get_db_session() as session:
            from src.wholesaler.db.models import Property
            existing_parcels = session.query(Property.parcel_id_normalized).all()
            parcel_ids = [p.parcel_id_normalized for p in existing_parcels if p.parcel_id_normalized]

        logger.info("fetching_property_records_for_existing_parcels", count=len(parcel_ids))

        # Scrape property records for existing parcels
        scraper = PropertyScraper()
        # Fetch in batches to avoid overwhelming API
        property_records = scraper.fetch_properties(parcel_numbers=parcel_ids[:1000])
        logger.info("property_records_scraped", count=len(property_records))

        # Load to database
        with get_db_session() as session:
            loader = PropertyRecordLoader()
            stats = loader.bulk_load(session, property_records, track_run=True)

        logger.info("property_record_ingestion_completed", stats=stats)

        # Push stats to XCom for downstream tasks
        context['task_instance'].xcom_push(key='property_record_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("property_record_ingestion_failed", error=str(e))
        raise


def scrape_and_load_code_violations(**context):
    """
    Scrape code violations from Socrata API and load into database.

    Returns:
        Dict with stats (processed, inserted, updated, failed)
    """
    logger.info("code_violation_ingestion_started")

    try:
        # Scrape code violations
        scraper = CodeViolationScraper()
        violations = scraper.fetch_violations()
        logger.info("code_violations_scraped", count=len(violations))

        # Load to database
        with get_db_session() as session:
            from src.wholesaler.etl.loaders import CodeViolationLoader
            loader = CodeViolationLoader()
            stats = loader.bulk_load(session, violations, track_run=True)

        logger.info("code_violation_ingestion_completed", stats=stats)

        # Push stats to XCom for downstream tasks
        context['task_instance'].xcom_push(key='code_violation_stats', value=stats)

        return stats

    except Exception as e:
        logger.error("code_violation_ingestion_failed", error=str(e))
        raise


def validate_ingestion(**context):
    """
    Validate that ingestion completed successfully.

    Checks that all data sources were loaded.
    """
    ti = context['task_instance']

    tax_sale_stats = ti.xcom_pull(task_ids='scrape_tax_sales', key='tax_sale_stats')
    foreclosure_stats = ti.xcom_pull(task_ids='scrape_foreclosures', key='foreclosure_stats')
    property_record_stats = ti.xcom_pull(task_ids='scrape_property_records', key='property_record_stats')
    code_violation_stats = ti.xcom_pull(task_ids='scrape_code_violations', key='code_violation_stats')

    logger.info("ingestion_validation_started",
                tax_sale_stats=tax_sale_stats,
                foreclosure_stats=foreclosure_stats,
                property_record_stats=property_record_stats,
                code_violation_stats=code_violation_stats)

    # Check for failures
    if tax_sale_stats and tax_sale_stats.get('failed', 0) > 0:
        logger.warning("tax_sale_ingestion_has_failures", failed=tax_sale_stats['failed'])

    if foreclosure_stats and foreclosure_stats.get('failed', 0) > 0:
        logger.warning("foreclosure_ingestion_has_failures", failed=foreclosure_stats['failed'])

    if property_record_stats and property_record_stats.get('failed', 0) > 0:
        logger.warning("property_record_ingestion_has_failures", failed=property_record_stats['failed'])

    if code_violation_stats and code_violation_stats.get('failed', 0) > 0:
        logger.warning("code_violation_ingestion_has_failures", failed=code_violation_stats['failed'])

    # Check that at least some records were processed
    total_processed = (
        tax_sale_stats.get('processed', 0) +
        foreclosure_stats.get('processed', 0) +
        property_record_stats.get('processed', 0) +
        code_violation_stats.get('processed', 0)
    )

    if total_processed == 0:
        raise ValueError("No properties were processed in ingestion")

    logger.info("ingestion_validation_passed",
                total_processed=total_processed)


# Define the DAG
with DAG(
    'daily_property_ingestion',
    default_args=default_args,
    description='Daily ingestion of tax sales, foreclosures, property records, and code violations',
    schedule_interval='0 2 * * *',  # 2:00 AM daily
    start_date=days_ago(1),
    catchup=False,
    tags=['ingestion', 'scraping', 'etl'],
) as dag:

    # Task 1: Scrape tax sales
    scrape_tax_sales_task = PythonOperator(
        task_id='scrape_tax_sales',
        python_callable=scrape_and_load_tax_sales,
        provide_context=True,
    )

    # Task 2: Scrape foreclosures (runs in parallel with tax sales)
    scrape_foreclosures_task = PythonOperator(
        task_id='scrape_foreclosures',
        python_callable=scrape_and_load_foreclosures,
        provide_context=True,
    )

    # Task 3: Scrape property records (runs after tax sales and foreclosures to get parcel IDs)
    scrape_property_records_task = PythonOperator(
        task_id='scrape_property_records',
        python_callable=scrape_and_load_property_records,
        provide_context=True,
    )

    # Task 4: Scrape code violations (can run in parallel with property records)
    scrape_code_violations_task = PythonOperator(
        task_id='scrape_code_violations',
        python_callable=scrape_and_load_code_violations,
        provide_context=True,
    )

    # Task 5: Validate ingestion (runs after all complete)
    validate_task = PythonOperator(
        task_id='validate_ingestion',
        python_callable=validate_ingestion,
        provide_context=True,
    )

    # Define dependencies
    # 1. Tax sales and foreclosures run in parallel
    # 2. Property records runs after both (needs parcel IDs from database)
    # 3. Code violations can run in parallel with property records
    # 4. Validation runs after all complete
    [scrape_tax_sales_task, scrape_foreclosures_task] >> scrape_property_records_task
    [scrape_tax_sales_task, scrape_foreclosures_task] >> scrape_code_violations_task
    [scrape_property_records_task, scrape_code_violations_task] >> validate_task
