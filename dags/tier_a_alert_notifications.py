"""
Tier A Alert Notifications DAG

Sends alerts when new Tier A leads are identified.

Schedule: Daily at 5:00 AM (after scoring completes)
"""
from datetime import datetime, timedelta, date
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.dates import days_ago

from dags.utils.notifications import (
    send_slack_notification,
    send_email_notification,
    format_tier_a_leads_message,
)
from src.wholesaler.db import LeadScoreRepository, PropertyRepository, get_db_session
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': True,  # Wait for previous run to complete
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=3),
    'execution_timeout': timedelta(minutes=30),
}


def fetch_tier_a_leads(**context):
    """
    Fetch all Tier A leads from database.

    Returns:
        List of Tier A lead dictionaries
    """
    logger.info("fetching_tier_a_leads")

    with get_db_session() as session:
        lead_repo = LeadScoreRepository()
        property_repo = PropertyRepository()

        # Get Tier A leads
        tier_a_leads = lead_repo.get_tier_a_leads(session)

        logger.info("tier_a_leads_fetched", count=len(tier_a_leads))

        # Build lead details with property info
        lead_details = []
        for lead in tier_a_leads:
            # Get property details
            property_obj = property_repo.get_by_parcel(session, lead.parcel_id_normalized)

            if property_obj:
                lead_detail = {
                    'parcel_id_normalized': lead.parcel_id_normalized,
                    'situs_address': property_obj.situs_address,
                    'city': property_obj.city,
                    'state': property_obj.state,
                    'zip_code': property_obj.zip_code,
                    'total_score': lead.total_score,
                    'tier': lead.tier,
                    'distress_score': lead.distress_score,
                    'value_score': lead.value_score,
                    'location_score': lead.location_score,
                    'urgency_score': lead.urgency_score,
                    'scored_at': lead.scored_at.isoformat() if lead.scored_at else None,
                }
                lead_details.append(lead_detail)

        # Store for downstream tasks
        context['task_instance'].xcom_push(key='tier_a_leads', value=lead_details)

        return len(lead_details)


def identify_new_tier_a_leads(**context):
    """
    Identify leads that became Tier A today (new hot leads).

    Compares today's scores with yesterday's history to find new Tier A leads.

    Returns:
        List of new Tier A lead dictionaries
    """
    ti = context['task_instance']
    all_tier_a_leads = ti.xcom_pull(task_ids='fetch_tier_a_leads', key='tier_a_leads')

    logger.info("identifying_new_tier_a_leads", total_tier_a=len(all_tier_a_leads))

    # In production, we would compare with yesterday's history
    # For now, consider all Tier A leads as "new" for notification purposes
    new_tier_a_leads = all_tier_a_leads

    # TODO: Query lead_score_history to find leads that weren't Tier A yesterday
    # with get_db_session() as session:
    #     yesterday = date.today() - timedelta(days=1)
    #     # Query history and filter for new Tier A leads

    logger.info("new_tier_a_leads_identified", count=len(new_tier_a_leads))

    # Store for downstream tasks
    context['task_instance'].xcom_push(key='new_tier_a_leads', value=new_tier_a_leads)

    return len(new_tier_a_leads)


def send_slack_alerts(**context):
    """
    Send Slack notifications for new Tier A leads.
    """
    ti = context['task_instance']
    new_tier_a_leads = ti.xcom_pull(task_ids='identify_new_leads', key='new_tier_a_leads')

    if not new_tier_a_leads:
        logger.info("no_new_tier_a_leads_to_notify")
        return {'sent': False, 'reason': 'no_new_leads'}

    logger.info("sending_slack_alerts", count=len(new_tier_a_leads))

    # Format message
    message = format_tier_a_leads_message(new_tier_a_leads)

    # Send to Slack
    success = send_slack_notification(message)

    if success:
        logger.info("slack_alerts_sent_successfully")
        return {'sent': True, 'count': len(new_tier_a_leads)}
    else:
        logger.warning("slack_alerts_failed")
        return {'sent': False, 'reason': 'send_failed'}


def send_email_alerts(**context):
    """
    Send email notifications for new Tier A leads.
    """
    ti = context['task_instance']
    new_tier_a_leads = ti.xcom_pull(task_ids='identify_new_leads', key='new_tier_a_leads')

    if not new_tier_a_leads:
        logger.info("no_new_tier_a_leads_to_email")
        return {'sent': False, 'reason': 'no_new_leads'}

    logger.info("sending_email_alerts", count=len(new_tier_a_leads))

    # Format message
    subject = f"Real Estate Wholesaler: {len(new_tier_a_leads)} New Tier A Leads"
    body = format_tier_a_leads_message(new_tier_a_leads)

    # Send email
    success = send_email_notification(subject, body)

    if success:
        logger.info("email_alerts_sent_successfully")
        return {'sent': True, 'count': len(new_tier_a_leads)}
    else:
        logger.warning("email_alerts_failed")
        return {'sent': False, 'reason': 'send_failed'}


def generate_lead_report(**context):
    """
    Generate detailed lead report with analysis.

    Creates a comprehensive report of all Tier A leads with scoring details.
    """
    ti = context['task_instance']
    all_tier_a_leads = ti.xcom_pull(task_ids='fetch_tier_a_leads', key='tier_a_leads')
    new_tier_a_leads = ti.xcom_pull(task_ids='identify_new_leads', key='new_tier_a_leads')

    logger.info("generating_lead_report",
                total_tier_a=len(all_tier_a_leads),
                new_tier_a=len(new_tier_a_leads))

    # Calculate statistics
    if all_tier_a_leads:
        avg_score = sum(lead['total_score'] for lead in all_tier_a_leads) / len(all_tier_a_leads)
        avg_distress = sum(lead['distress_score'] for lead in all_tier_a_leads) / len(all_tier_a_leads)
        avg_value = sum(lead['value_score'] for lead in all_tier_a_leads) / len(all_tier_a_leads)
    else:
        avg_score = avg_distress = avg_value = 0

    report = {
        'date': date.today().isoformat(),
        'total_tier_a_leads': len(all_tier_a_leads),
        'new_tier_a_leads': len(new_tier_a_leads),
        'avg_total_score': avg_score,
        'avg_distress_score': avg_distress,
        'avg_value_score': avg_value,
        'top_10_leads': all_tier_a_leads[:10],
    }

    logger.info("lead_report_generated", report=report)

    # Store report
    context['task_instance'].xcom_push(key='lead_report', value=report)

    return report


def log_alert_summary(**context):
    """
    Log summary of alert notifications sent.
    """
    ti = context['task_instance']

    slack_result = ti.xcom_pull(task_ids='send_slack_alerts')
    email_result = ti.xcom_pull(task_ids='send_email_alerts')
    report = ti.xcom_pull(task_ids='generate_report', key='lead_report')

    logger.info("alert_notification_summary",
                slack_sent=slack_result.get('sent') if slack_result else False,
                email_sent=email_result.get('sent') if email_result else False,
                total_tier_a_leads=report.get('total_tier_a_leads') if report else 0,
                new_tier_a_leads=report.get('new_tier_a_leads') if report else 0)

    return {
        'slack_sent': slack_result.get('sent') if slack_result else False,
        'email_sent': email_result.get('sent') if email_result else False,
        'tier_a_count': report.get('total_tier_a_leads') if report else 0,
        'new_tier_a_count': report.get('new_tier_a_leads') if report else 0,
    }


# Define the DAG
with DAG(
    'tier_a_alert_notifications',
    default_args=default_args,
    description='Send alerts for new Tier A leads',
    schedule_interval='0 5 * * *',  # 5:00 AM daily (1 hour after scoring)
    start_date=days_ago(1),
    catchup=False,
    tags=['alerts', 'notifications', 'leads', 'tier-a'],
) as dag:

    # Wait for scoring DAG to complete
    wait_for_scoring = ExternalTaskSensor(
        task_id='wait_for_scoring',
        external_dag_id='daily_lead_scoring',
        external_task_id='validate_scoring',
        timeout=3600,  # 1 hour timeout
        mode='reschedule',
    )

    # Task 1: Fetch all Tier A leads
    fetch_tier_a_task = PythonOperator(
        task_id='fetch_tier_a_leads',
        python_callable=fetch_tier_a_leads,
        provide_context=True,
    )

    # Task 2: Identify new Tier A leads
    identify_new_leads_task = PythonOperator(
        task_id='identify_new_leads',
        python_callable=identify_new_tier_a_leads,
        provide_context=True,
    )

    # Task 3: Send Slack alerts (runs in parallel with email)
    send_slack_task = PythonOperator(
        task_id='send_slack_alerts',
        python_callable=send_slack_alerts,
        provide_context=True,
    )

    # Task 4: Send email alerts (runs in parallel with Slack)
    send_email_task = PythonOperator(
        task_id='send_email_alerts',
        python_callable=send_email_alerts,
        provide_context=True,
    )

    # Task 5: Generate detailed report
    generate_report_task = PythonOperator(
        task_id='generate_report',
        python_callable=generate_lead_report,
        provide_context=True,
    )

    # Task 6: Log alert summary
    log_summary_task = PythonOperator(
        task_id='log_summary',
        python_callable=log_alert_summary,
        provide_context=True,
    )

    # Define dependencies
    wait_for_scoring >> fetch_tier_a_task >> identify_new_leads_task
    identify_new_leads_task >> [send_slack_task, send_email_task, generate_report_task]
    [send_slack_task, send_email_task, generate_report_task] >> log_summary_task
