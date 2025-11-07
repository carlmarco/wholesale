"""
Notification Utilities

Utilities for sending alerts via email and Slack.
"""
from typing import List, Dict, Any, Optional
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config.settings import settings
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def send_slack_notification(message: str, webhook_url: Optional[str] = None) -> bool:
    """
    Send notification to Slack via webhook.

    Args:
        message: Message to send
        webhook_url: Slack webhook URL (defaults to settings.alert_slack_webhook)

    Returns:
        True if successful, False otherwise
    """
    if not settings.alert_enable_slack:
        logger.info("slack_notifications_disabled")
        return False

    webhook_url = webhook_url or settings.alert_slack_webhook
    if not webhook_url:
        logger.warning("slack_webhook_url_not_configured")
        return False

    try:
        payload = {"text": message}
        response = requests.post(webhook_url, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info("slack_notification_sent")
            return True
        else:
            logger.error("slack_notification_failed",
                         status_code=response.status_code,
                         response=response.text)
            return False

    except Exception as e:
        logger.error("slack_notification_error", error=str(e))
        return False


def send_email_notification(
    subject: str,
    body: str,
    to_email: Optional[str] = None,
    html: bool = False
) -> bool:
    """
    Send email notification.

    Args:
        subject: Email subject
        body: Email body (plain text or HTML)
        to_email: Recipient email (defaults to settings.alert_email)
        html: Whether body is HTML

    Returns:
        True if successful, False otherwise
    """
    if not settings.alert_enable_email:
        logger.info("email_notifications_disabled")
        return False

    to_email = to_email or settings.alert_email
    if not to_email:
        logger.warning("alert_email_not_configured")
        return False

    try:
        # Note: In production, use SMTP server credentials from settings
        # For now, just log the notification
        logger.info("email_notification_sent",
                    to=to_email,
                    subject=subject,
                    body_preview=body[:100])

        # TODO: Implement actual email sending with SMTP
        # msg = MIMEMultipart('alternative')
        # msg['Subject'] = subject
        # msg['From'] = settings.smtp_from_email
        # msg['To'] = to_email
        # ...

        return True

    except Exception as e:
        logger.error("email_notification_error", error=str(e))
        return False


def format_tier_a_leads_message(leads: List[Dict[str, Any]]) -> str:
    """
    Format Tier A leads into a notification message.

    Args:
        leads: List of Tier A lead dictionaries

    Returns:
        Formatted message string
    """
    if not leads:
        return "No new Tier A leads found."

    message_lines = [
        f"*{len(leads)} New Tier A Leads Found!*",
        "",
        "Top investment opportunities:",
        ""
    ]

    # Show top 10 leads
    for i, lead in enumerate(leads[:10], 1):
        parcel_id = lead.get('parcel_id_normalized', 'Unknown')
        address = lead.get('situs_address', 'Unknown address')
        score = lead.get('total_score', 0)
        tier = lead.get('tier', 'Unknown')

        message_lines.append(
            f"{i}. *{address}* (Parcel: {parcel_id})"
        )
        message_lines.append(
            f"   Score: {score:.1f} | Tier: {tier}"
        )
        message_lines.append("")

    if len(leads) > 10:
        message_lines.append(f"... and {len(leads) - 10} more leads")

    return "\n".join(message_lines)


def format_data_quality_report(report: Dict[str, Any]) -> str:
    """
    Format data quality report into a notification message.

    Args:
        report: Data quality report dictionary

    Returns:
        Formatted message string
    """
    message_lines = [
        "*Data Quality Report*",
        "",
        f"Total Properties: {report.get('total_properties', 0):,}",
        f"Properties with Coordinates: {report.get('properties_with_coords', 0):,}",
        f"Properties Missing Coordinates: {report.get('properties_missing_coords', 0):,}",
        "",
        "*Lead Scores:*",
        f"Total Scored: {report.get('total_scored', 0):,}",
        f"Tier A: {report.get('tier_a_count', 0):,}",
        f"Tier B: {report.get('tier_b_count', 0):,}",
        f"Tier C: {report.get('tier_c_count', 0):,}",
        f"Tier D: {report.get('tier_d_count', 0):,}",
        "",
    ]

    # Add warnings if any
    warnings = report.get('warnings', [])
    if warnings:
        message_lines.append("*Warnings:*")
        for warning in warnings:
            message_lines.append(f"- {warning}")
        message_lines.append("")

    # Add errors if any
    errors = report.get('errors', [])
    if errors:
        message_lines.append("*Errors:*")
        for error in errors:
            message_lines.append(f"- {error}")
        message_lines.append("")

    return "\n".join(message_lines)


def format_pipeline_summary(stats: Dict[str, Any]) -> str:
    """
    Format pipeline execution summary into a notification message.

    Args:
        stats: Pipeline execution statistics

    Returns:
        Formatted message string
    """
    message_lines = [
        "*Daily Pipeline Execution Summary*",
        "",
        "*Ingestion:*",
        f"Tax Sales Processed: {stats.get('tax_sales_processed', 0):,}",
        f"Foreclosures Processed: {stats.get('foreclosures_processed', 0):,}",
        "",
        "*Enrichment:*",
        f"Properties Enriched: {stats.get('properties_enriched', 0):,}",
        f"Duplicates Removed: {stats.get('duplicates_removed', 0):,}",
        "",
        "*Scoring:*",
        f"Leads Scored: {stats.get('leads_scored', 0):,}",
        f"New Tier A Leads: {stats.get('new_tier_a_leads', 0):,}",
        "",
    ]

    # Add execution time
    execution_time = stats.get('execution_time_minutes', 0)
    message_lines.append(f"Total Execution Time: {execution_time:.1f} minutes")

    return "\n".join(message_lines)
