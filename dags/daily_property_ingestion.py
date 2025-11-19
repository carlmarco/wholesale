"""
Daily Property Ingestion DAG

Scrapes tax sales and foreclosures from ArcGIS APIs and loads them into the database.

Schedule: Daily at 2:00 AM
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper
from src.wholesaler.etl import TaxSaleLoader, ForeclosureLoader
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


def validate_ingestion(**context):
    """
    Validate that ingestion completed successfully.

    Checks that all data sources were loaded.
    """
    ti = context['task_instance']

    tax_sale_stats = ti.xcom_pull(task_ids='scrape_tax_sales', key='tax_sale_stats')
    foreclosure_stats = ti.xcom_pull(task_ids='scrape_foreclosures', key='foreclosure_stats')
    logger.info("ingestion_validation_started",
                tax_sale_stats=tax_sale_stats,
                foreclosure_stats=foreclosure_stats)

    # Check for failures
    if tax_sale_stats and tax_sale_stats.get('failed', 0) > 0:
        logger.warning("tax_sale_ingestion_has_failures", failed=tax_sale_stats['failed'])

    if foreclosure_stats and foreclosure_stats.get('failed', 0) > 0:
        logger.warning("foreclosure_ingestion_has_failures", failed=foreclosure_stats['failed'])

    # Check that at least some records were processed
    total_processed = (
        tax_sale_stats.get('processed', 0) +
        foreclosure_stats.get('processed', 0)
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
    schedule='0 2 * * *',  # 2:00 AM daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['ingestion', 'scraping', 'etl'],
) as dag:

    # Task 1: Scrape tax sales
    scrape_tax_sales_task = PythonOperator(
        task_id='scrape_tax_sales',
        python_callable=scrape_and_load_tax_sales,
    )

    # Task 2: Scrape foreclosures (runs in parallel with tax sales)
    scrape_foreclosures_task = PythonOperator(
        task_id='scrape_foreclosures',
        python_callable=scrape_and_load_foreclosures,
    )

    # Task 3: Validate ingestion
    validate_task = PythonOperator(
        task_id='validate_ingestion',
        python_callable=validate_ingestion,
    )

    # Define dependencies
    [scrape_tax_sales_task, scrape_foreclosures_task] >> validate_task
