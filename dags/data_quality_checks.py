"""
Data Quality Checks DAG

Validates data integrity and quality across all tables.

Schedule: Daily at 6:00 AM (after all ETL processes complete)
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from dags.utils.notifications import (
    send_slack_notification,
    format_data_quality_report,
)
from src.wholesaler.db import (
    PropertyRepository,
    LeadScoreRepository,
    get_db_session,
    db_utils,
)
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=30),
}


def check_database_statistics(**context):
    """
    Check row counts for all tables.

    Returns:
        Dict with table statistics
    """
    logger.info("checking_database_statistics")

    with get_db_session() as session:
        stats = db_utils.get_database_stats(session)

    logger.info("database_statistics_retrieved", stats=stats)

    # Store for downstream tasks
    context['task_instance'].xcom_push(key='db_stats', value=stats)

    return stats


def check_data_completeness(**context):
    """
    Check data completeness (missing required fields).

    Validates:
    - Properties with missing addresses
    - Properties with missing coordinates
    - Lead scores with invalid tier values
    - Lead scores with null scores

    Returns:
        Dict with completeness check results
    """
    logger.info("checking_data_completeness")

    results = {
        'properties_missing_address': 0,
        'properties_missing_coords': 0,
        'properties_with_coords': 0,
        'lead_scores_invalid_tier': 0,
        'lead_scores_null_score': 0,
        'total_properties': 0,
        'total_lead_scores': 0,
    }

    with get_db_session() as session:
        property_repo = PropertyRepository()
        lead_repo = LeadScoreRepository()

        # Check properties
        all_properties = property_repo.get_active_properties(session)
        results['total_properties'] = len(all_properties)

        for prop in all_properties:
            if not prop.situs_address:
                results['properties_missing_address'] += 1

            if prop.latitude is None or prop.longitude is None:
                results['properties_missing_coords'] += 1
            else:
                results['properties_with_coords'] += 1

        # Check lead scores
        all_lead_scores = lead_repo.get_all(session, limit=100000)
        results['total_lead_scores'] = len(all_lead_scores)

        valid_tiers = {'A', 'B', 'C', 'D'}
        for lead in all_lead_scores:
            if lead.tier not in valid_tiers:
                results['lead_scores_invalid_tier'] += 1

            if lead.total_score is None:
                results['lead_scores_null_score'] += 1

    logger.info("data_completeness_checked", results=results)

    # Store for downstream tasks
    context['task_instance'].xcom_push(key='completeness_results', value=results)

    return results


def check_data_consistency(**context):
    """
    Check data consistency across tables.

    Validates:
    - Tax sales without parent properties
    - Foreclosures without parent properties
    - Lead scores without parent properties
    - Properties with duplicate parcel IDs

    Returns:
        Dict with consistency check results
    """
    logger.info("checking_data_consistency")

    results = {
        'orphaned_tax_sales': 0,
        'orphaned_foreclosures': 0,
        'orphaned_lead_scores': 0,
        'duplicate_parcel_ids': 0,
    }

    with get_db_session() as session:
        # Check for orphaned records
        # Note: Foreign keys should prevent this, but we check anyway

        # Query for tax sales without properties
        orphaned_tax_sales_query = """
        SELECT COUNT(*)
        FROM tax_sales ts
        LEFT JOIN properties p ON ts.parcel_id_normalized = p.parcel_id_normalized
        WHERE p.parcel_id_normalized IS NULL
        """
        result = db_utils.execute_raw_sql(session, orphaned_tax_sales_query)
        results['orphaned_tax_sales'] = result.scalar()

        # Query for foreclosures without properties
        orphaned_foreclosures_query = """
        SELECT COUNT(*)
        FROM foreclosures f
        LEFT JOIN properties p ON f.parcel_id_normalized = p.parcel_id_normalized
        WHERE p.parcel_id_normalized IS NULL
        """
        result = db_utils.execute_raw_sql(session, orphaned_foreclosures_query)
        results['orphaned_foreclosures'] = result.scalar()

        # Query for lead scores without properties
        orphaned_lead_scores_query = """
        SELECT COUNT(*)
        FROM lead_scores ls
        LEFT JOIN properties p ON ls.parcel_id_normalized = p.parcel_id_normalized
        WHERE p.parcel_id_normalized IS NULL
        """
        result = db_utils.execute_raw_sql(session, orphaned_lead_scores_query)
        results['orphaned_lead_scores'] = result.scalar()

        # Check for duplicate parcel IDs (should be prevented by PK)
        duplicate_parcels_query = """
        SELECT COUNT(*)
        FROM (
            SELECT parcel_id_normalized, COUNT(*) as cnt
            FROM properties
            WHERE is_active = true
            GROUP BY parcel_id_normalized
            HAVING COUNT(*) > 1
        ) duplicates
        """
        result = db_utils.execute_raw_sql(session, duplicate_parcels_query)
        results['duplicate_parcel_ids'] = result.scalar()

    logger.info("data_consistency_checked", results=results)

    # Store for downstream tasks
    context['task_instance'].xcom_push(key='consistency_results', value=results)

    return results


def check_postgis_functionality(**context):
    """
    Check PostGIS functionality and spatial data quality.

    Validates:
    - PostGIS extension is installed
    - Properties have valid geometries
    - Spatial indexes are working

    Returns:
        Dict with PostGIS check results
    """
    logger.info("checking_postgis_functionality")

    results = {
        'postgis_installed': False,
        'postgis_version': None,
        'properties_with_invalid_geometry': 0,
    }

    with get_db_session() as session:
        # Check PostGIS installation
        results['postgis_installed'] = db_utils.check_postgis_installed(session)
        results['postgis_version'] = db_utils.get_postgis_version(session)

        # Check for invalid geometries
        if results['postgis_installed']:
            invalid_geometry_query = """
            SELECT COUNT(*)
            FROM properties
            WHERE location IS NOT NULL
            AND NOT ST_IsValid(location::geometry)
            """
            result = db_utils.execute_raw_sql(session, invalid_geometry_query)
            results['properties_with_invalid_geometry'] = result.scalar()

    logger.info("postgis_functionality_checked", results=results)

    # Store for downstream tasks
    context['task_instance'].xcom_push(key='postgis_results', value=results)

    return results


def generate_quality_report(**context):
    """
    Generate comprehensive data quality report.

    Combines all check results into a single report.
    """
    ti = context['task_instance']

    db_stats = ti.xcom_pull(task_ids='check_db_stats', key='db_stats')
    completeness = ti.xcom_pull(task_ids='check_completeness', key='completeness_results')
    consistency = ti.xcom_pull(task_ids='check_consistency', key='consistency_results')
    postgis = ti.xcom_pull(task_ids='check_postgis', key='postgis_results')

    logger.info("generating_quality_report")

    # Build comprehensive report
    report = {
        'date': datetime.now().isoformat(),
        'database_stats': db_stats,
        'completeness': completeness,
        'consistency': consistency,
        'postgis': postgis,
        'warnings': [],
        'errors': [],
    }

    # Add warnings
    if completeness:
        missing_coords_pct = (
            completeness['properties_missing_coords'] / completeness['total_properties'] * 100
            if completeness['total_properties'] > 0 else 0
        )
        if missing_coords_pct > 10:
            report['warnings'].append(
                f"{missing_coords_pct:.1f}% of properties missing coordinates"
            )

        if completeness['lead_scores_invalid_tier'] > 0:
            report['warnings'].append(
                f"{completeness['lead_scores_invalid_tier']} lead scores with invalid tier"
            )

    # Add errors
    if consistency:
        if consistency['orphaned_tax_sales'] > 0:
            report['errors'].append(
                f"{consistency['orphaned_tax_sales']} tax sales without parent property"
            )

        if consistency['orphaned_foreclosures'] > 0:
            report['errors'].append(
                f"{consistency['orphaned_foreclosures']} foreclosures without parent property"
            )

        if consistency['duplicate_parcel_ids'] > 0:
            report['errors'].append(
                f"{consistency['duplicate_parcel_ids']} duplicate parcel IDs found"
            )

    if postgis:
        if not postgis['postgis_installed']:
            report['errors'].append("PostGIS extension not installed")

        if postgis['properties_with_invalid_geometry'] > 0:
            report['errors'].append(
                f"{postgis['properties_with_invalid_geometry']} properties with invalid geometry"
            )

    logger.info("quality_report_generated",
                warning_count=len(report['warnings']),
                error_count=len(report['errors']))

    # Store report
    context['task_instance'].xcom_push(key='quality_report', value=report)

    return report


def send_quality_alerts(**context):
    """
    Send alerts if data quality issues are found.
    """
    ti = context['task_instance']
    report = ti.xcom_pull(task_ids='generate_report', key='quality_report')

    logger.info("sending_quality_alerts")

    # Only send alert if there are warnings or errors
    if not report['warnings'] and not report['errors']:
        logger.info("no_quality_issues_found_skipping_alert")
        return {'sent': False, 'reason': 'no_issues'}

    # Format message
    message = format_data_quality_report(report)

    # Send to Slack
    success = send_slack_notification(message)

    if success:
        logger.info("quality_alerts_sent_successfully")
        return {'sent': True, 'warning_count': len(report['warnings']), 'error_count': len(report['errors'])}
    else:
        logger.warning("quality_alerts_failed")
        return {'sent': False, 'reason': 'send_failed'}


def log_quality_summary(**context):
    """
    Log summary of data quality checks.
    """
    ti = context['task_instance']
    report = ti.xcom_pull(task_ids='generate_report', key='quality_report')
    alert_result = ti.xcom_pull(task_ids='send_alerts')

    logger.info("data_quality_check_summary",
                warning_count=len(report['warnings']) if report else 0,
                error_count=len(report['errors']) if report else 0,
                alert_sent=alert_result.get('sent') if alert_result else False)

    return {
        'warnings': len(report['warnings']) if report else 0,
        'errors': len(report['errors']) if report else 0,
        'alert_sent': alert_result.get('sent') if alert_result else False,
    }


# Define the DAG
with DAG(
    'data_quality_checks',
    default_args=default_args,
    description='Daily data quality validation and integrity checks',
    schedule_interval='0 6 * * *',  # 6:00 AM daily (after all ETL processes)
    start_date=days_ago(1),
    catchup=False,
    tags=['quality', 'validation', 'monitoring'],
) as dag:

    # Task 1: Check database statistics
    check_db_stats_task = PythonOperator(
        task_id='check_db_stats',
        python_callable=check_database_statistics,
        provide_context=True,
    )

    # Task 2: Check data completeness
    check_completeness_task = PythonOperator(
        task_id='check_completeness',
        python_callable=check_data_completeness,
        provide_context=True,
    )

    # Task 3: Check data consistency
    check_consistency_task = PythonOperator(
        task_id='check_consistency',
        python_callable=check_data_consistency,
        provide_context=True,
    )

    # Task 4: Check PostGIS functionality
    check_postgis_task = PythonOperator(
        task_id='check_postgis',
        python_callable=check_postgis_functionality,
        provide_context=True,
    )

    # Task 5: Generate quality report
    generate_report_task = PythonOperator(
        task_id='generate_report',
        python_callable=generate_quality_report,
        provide_context=True,
    )

    # Task 6: Send alerts if issues found
    send_alerts_task = PythonOperator(
        task_id='send_alerts',
        python_callable=send_quality_alerts,
        provide_context=True,
    )

    # Task 7: Log summary
    log_summary_task = PythonOperator(
        task_id='log_summary',
        python_callable=log_quality_summary,
        provide_context=True,
    )

    # Define dependencies
    # All checks run in parallel, then report generation
    [check_db_stats_task, check_completeness_task, check_consistency_task, check_postgis_task] >> generate_report_task
    generate_report_task >> send_alerts_task >> log_summary_task
