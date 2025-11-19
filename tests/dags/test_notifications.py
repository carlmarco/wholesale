"""
Tests for Notification Utilities

Tests Slack and email notification formatting and sending.
"""
import pytest
from unittest.mock import patch, MagicMock

from dags.utils.notifications import (
    send_slack_notification,
    send_email_notification,
    format_tier_a_leads_message,
    format_data_quality_report,
    format_pipeline_summary,
)


class TestSlackNotifications:
    """Tests for Slack notification functions."""

    @patch('dags.utils.notifications.requests.post')
    @patch('dags.utils.notifications.settings')
    def test_send_slack_notification_success(self, mock_settings, mock_post):
        """Test sending Slack notification successfully."""
        # Configure mock settings
        mock_settings.alert_enable_slack = True
        mock_settings.alert_slack_webhook = "https://hooks.slack.com/test"

        # Configure mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Send notification
        result = send_slack_notification("Test message")

        assert result is True
        mock_post.assert_called_once()

        # Verify payload
        call_args = mock_post.call_args
        assert call_args[1]["json"]["text"] == "Test message"

    @patch('dags.utils.notifications.settings')
    def test_send_slack_notification_disabled(self, mock_settings):
        """Test that notification returns False when Slack is disabled."""
        mock_settings.alert_enable_slack = False

        result = send_slack_notification("Test message")

        assert result is False

    @patch('dags.utils.notifications.requests.post')
    @patch('dags.utils.notifications.settings')
    def test_send_slack_notification_failure(self, mock_settings, mock_post):
        """Test handling Slack API failure."""
        mock_settings.alert_enable_slack = True
        mock_settings.alert_slack_webhook = "https://hooks.slack.com/test"

        # Configure mock to return failure
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        result = send_slack_notification("Test message")

        assert result is False


class TestEmailNotifications:
    """Tests for email notification functions."""

    @patch('dags.utils.notifications.settings')
    def test_send_email_notification_disabled(self, mock_settings):
        """Test that notification returns False when email is disabled."""
        mock_settings.alert_enable_email = False

        result = send_email_notification(
            subject="Test Subject",
            body="Test body"
        )

        assert result is False

    @patch('dags.utils.notifications.settings')
    def test_send_email_notification_no_recipient(self, mock_settings):
        """Test that notification returns False when no email is configured."""
        mock_settings.alert_enable_email = True
        mock_settings.alert_email = None

        result = send_email_notification(
            subject="Test Subject",
            body="Test body"
        )

        assert result is False

    @patch('dags.utils.notifications.smtplib.SMTP')
    @patch('dags.utils.notifications.settings')
    def test_send_email_notification_success(self, mock_settings, mock_smtp):
        """Test sending email notification (currently logs only)."""
        mock_settings.alert_enable_email = True
        mock_settings.alert_email = "test@example.com"
        mock_settings.smtp_host = "smtp.test"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.smtp_from_email = "alerts@test.com"
        mock_settings.smtp_use_tls = True

        smtp_instance = mock_smtp.return_value.__enter__.return_value
        smtp_instance.send_message.return_value = {}

        result = send_email_notification(
            subject="Test Subject",
            body="Test body",
            html=False
        )

        # Currently, email just logs and returns True
        assert result is True


class TestTierALeadsFormatting:
    """Tests for Tier A leads message formatting."""

    def test_format_empty_leads(self):
        """Test formatting message with no leads."""
        message = format_tier_a_leads_message([])

        assert "No new Tier A leads found" in message

    def test_format_single_lead(self):
        """Test formatting message with single lead."""
        leads = [
            {
                "parcel_id_normalized": "12-34-56-7890-01-001",
                "situs_address": "123 Main St",
                "total_score": 85.5,
                "tier": "A",
            }
        ]

        message = format_tier_a_leads_message(leads)

        assert "1 New Tier A Leads Found" in message
        assert "123 Main St" in message
        assert "12-34-56-7890-01-001" in message
        assert "85.5" in message

    def test_format_multiple_leads(self):
        """Test formatting message with multiple leads."""
        leads = [
            {
                "parcel_id_normalized": f"12-34-56-7890-01-00{i}",
                "situs_address": f"{i*100} Main St",
                "total_score": 80.0 + i,
                "tier": "A",
            }
            for i in range(1, 4)
        ]

        message = format_tier_a_leads_message(leads)

        assert "3 New Tier A Leads Found" in message
        assert "100 Main St" in message
        assert "200 Main St" in message
        assert "300 Main St" in message

    def test_format_limits_to_top_10(self):
        """Test that formatting limits display to top 10 leads."""
        leads = [
            {
                "parcel_id_normalized": f"12-34-56-7890-01-0{i:02d}",
                "situs_address": f"{i*100} Main St",
                "total_score": 80.0 + i,
                "tier": "A",
            }
            for i in range(1, 16)  # 15 leads
        ]

        message = format_tier_a_leads_message(leads)

        assert "15 New Tier A Leads Found" in message
        assert "... and 5 more leads" in message


class TestDataQualityReportFormatting:
    """Tests for data quality report formatting."""

    def test_format_basic_report(self):
        """Test formatting basic quality report."""
        report = {
            "total_properties": 1000,
            "properties_with_coords": 950,
            "properties_missing_coords": 50,
            "total_scored": 980,
            "tier_a_count": 45,
            "tier_b_count": 120,
            "tier_c_count": 300,
            "tier_d_count": 515,
            "warnings": [],
            "errors": [],
        }

        message = format_data_quality_report(report)

        assert "Data Quality Report" in message
        assert "1,000" in message
        assert "950" in message
        assert "Tier A: 45" in message

    def test_format_report_with_warnings(self):
        """Test formatting report with warnings."""
        report = {
            "total_properties": 1000,
            "properties_with_coords": 800,
            "properties_missing_coords": 200,
            "total_scored": 900,
            "tier_a_count": 50,
            "tier_b_count": 150,
            "tier_c_count": 300,
            "tier_d_count": 400,
            "warnings": [
                "20% of properties missing coordinates",
                "High failure rate in enrichment",
            ],
            "errors": [],
        }

        message = format_data_quality_report(report)

        assert "Warnings:" in message
        assert "20% of properties missing coordinates" in message
        assert "High failure rate in enrichment" in message

    def test_format_report_with_errors(self):
        """Test formatting report with errors."""
        report = {
            "total_properties": 1000,
            "properties_with_coords": 950,
            "properties_missing_coords": 50,
            "total_scored": 980,
            "tier_a_count": 45,
            "tier_b_count": 120,
            "tier_c_count": 300,
            "tier_d_count": 515,
            "warnings": [],
            "errors": [
                "5 properties with invalid geometry",
                "PostGIS extension not installed",
            ],
        }

        message = format_data_quality_report(report)

        assert "Errors:" in message
        assert "5 properties with invalid geometry" in message
        assert "PostGIS extension not installed" in message


class TestPipelineSummaryFormatting:
    """Tests for pipeline summary formatting."""

    def test_format_pipeline_summary(self):
        """Test formatting pipeline execution summary."""
        stats = {
            "tax_sales_processed": 150,
            "foreclosures_processed": 85,
            "properties_enriched": 200,
            "duplicates_removed": 15,
            "leads_scored": 220,
            "new_tier_a_leads": 12,
            "execution_time_minutes": 45.5,
        }

        message = format_pipeline_summary(stats)

        assert "Daily Pipeline Execution Summary" in message
        assert "Tax Sales Processed: 150" in message
        assert "Foreclosures Processed: 85" in message
        assert "Properties Enriched: 200" in message
        assert "Duplicates Removed: 15" in message
        assert "Leads Scored: 220" in message
        assert "New Tier A Leads: 12" in message
        assert "45.5 minutes" in message

    def test_format_pipeline_summary_with_zeros(self):
        """Test formatting summary with zero values."""
        stats = {
            "tax_sales_processed": 0,
            "foreclosures_processed": 0,
            "properties_enriched": 0,
            "duplicates_removed": 0,
            "leads_scored": 0,
            "new_tier_a_leads": 0,
            "execution_time_minutes": 2.3,
        }

        message = format_pipeline_summary(stats)

        assert "Tax Sales Processed: 0" in message
        assert "New Tier A Leads: 0" in message
        assert "2.3 minutes" in message
