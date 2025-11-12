# Alert System Setup Guide

## Overview

The Wholesaler Lead Management System includes automated alerting for new Tier A leads via email and Slack. This guide covers complete setup and configuration.

## Alert Types

### 1. Tier A Lead Alerts
- **Trigger**: New properties classified as Tier A (hot leads)
- **Schedule**: Daily at 5:00 AM (after lead scoring completes)
- **Channels**: Email + Slack (configurable)
- **Content**: Top 10 new Tier A leads with scores and addresses

### 2. Data Quality Alerts
- **Trigger**: Data quality issues detected
- **Schedule**: Daily at 6:30 AM (after all pipelines complete)
- **Channels**: Email + Slack
- **Content**: Missing coordinates, scoring failures, data gaps

## Email Configuration (SMTP)

### Step 1: Enable Email Alerts

Edit `.env` file:

```bash
# Enable email notifications
ALERT_ENABLE_EMAIL=true

# Set recipient email
ALERT_EMAIL=your-email@example.com
```

### Step 2: Configure SMTP Server

#### Option A: Gmail (Recommended for Testing)

1. **Create an App Password** (required for Gmail with 2FA):
   - Go to: https://myaccount.google.com/apppasswords
   - Select app: "Mail"
   - Select device: "Other (Custom name)"
   - Enter name: "Wholesaler Alerts"
   - Click "Generate"
   - Copy the 16-character password

2. **Update `.env` file**:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_USE_TLS=true
```

#### Option B: SendGrid (Recommended for Production)

1. **Create SendGrid Account**: https://signup.sendgrid.com/
2. **Generate API Key**:
   - Go to Settings → API Keys
   - Click "Create API Key"
   - Name: "Wholesaler Alerts"
   - Permissions: "Mail Send"
   - Copy the API key

3. **Update `.env` file**:

```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
SMTP_FROM_EMAIL=alerts@yourdomain.com
SMTP_USE_TLS=true
```

#### Option C: AWS SES (Enterprise Production)

1. **Verify Email Address** in AWS SES Console
2. **Create SMTP Credentials**:
   - Go to AWS SES Console → SMTP Settings
   - Click "Create My SMTP Credentials"
   - Download credentials

3. **Update `.env` file**:

```bash
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-aws-smtp-username
SMTP_PASSWORD=your-aws-smtp-password
SMTP_FROM_EMAIL=alerts@yourdomain.com
SMTP_USE_TLS=true
```

## Slack Configuration

### Step 1: Create Slack Webhook

1. **Go to**: https://api.slack.com/messaging/webhooks
2. **Click**: "Create your Slack app"
3. **Choose**: "From scratch"
4. **Name**: "Wholesaler Alerts"
5. **Select Workspace**: Your workspace
6. **Activate Incoming Webhooks**: Toggle to ON
7. **Add New Webhook to Workspace**:
   - Select channel: `#real-estate-leads` (or create it)
   - Click "Allow"
8. **Copy Webhook URL**: Should look like:
   ```
   https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
   ```

### Step 2: Enable Slack Alerts

Edit `.env` file:

```bash
# Enable Slack notifications
ALERT_ENABLE_SLACK=true

# Set webhook URL
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## Testing Alerts

### Test Email Configuration

```bash
# Enter Python environment
.venv/bin/python

# Test email sending
from dags.utils.notifications import send_email_notification
result = send_email_notification(
    subject="Test Alert from Wholesaler System",
    body="This is a test email to verify SMTP configuration."
)
print(f"Email sent: {result}")
```

### Test Slack Configuration

```bash
# Test Slack webhook
from dags.utils.notifications import send_slack_notification
result = send_slack_notification(
    "Test message from Wholesaler System - Slack integration is working!"
)
print(f"Slack sent: {result}")
```

### Trigger Manual Alert (for testing)

```bash
# Manually trigger Tier A alert DAG
docker exec -it wholesaler_airflow_scheduler \
  airflow dags trigger tier_a_alert_notifications
```

Check the Airflow UI at http://localhost:8080 to monitor execution.

## Complete `.env` Example

```bash
# Alert Settings
ALERT_ENABLE_EMAIL=true
ALERT_ENABLE_SLACK=true
ALERT_EMAIL=john@example.com
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX

# SMTP Settings (Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=john@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
SMTP_FROM_EMAIL=john@gmail.com
SMTP_USE_TLS=true
```

## Troubleshooting

### Email Alerts Not Sending

1. **Check SMTP credentials**:
   ```bash
   # Verify credentials in .env are correct
   cat .env | grep SMTP
   ```

2. **Check logs**:
   ```bash
   docker logs wholesaler_airflow_scheduler | grep smtp
   ```

3. **Common errors**:
   - `SMTPAuthenticationError`: Wrong username/password
     - For Gmail: Use app password, not regular password
   - `SMTPConnectError`: Wrong host/port
     - Verify SMTP_HOST and SMTP_PORT
   - `Certificate verify failed`: Network/firewall issue
     - Try SMTP_PORT=465 with SSL instead of TLS

### Slack Alerts Not Sending

1. **Verify webhook URL**:
   ```bash
   # Test webhook with curl
   curl -X POST -H 'Content-type: application/json' \
     --data '{"text":"Test from command line"}' \
     YOUR_WEBHOOK_URL
   ```

2. **Check webhook expiration**:
   - Slack webhooks can be revoked
   - Recreate webhook if necessary

3. **Check channel permissions**:
   - Ensure webhook has permission to post to channel
   - Try selecting a different channel

### No Tier A Leads in Alerts

If you receive empty alert emails (0 new Tier A leads):

1. **Check tier distribution**:
   ```sql
   docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler -c \
     "SELECT tier, COUNT(*) FROM lead_scores GROUP BY tier ORDER BY tier;"
   ```

2. **If no Tier A leads exist**, adjust thresholds:
   - Edit `src/wholesaler/pipelines/lead_scoring.py`
   - Lower `TIER_A_THRESHOLD` (current: 43)
   - Re-run scoring: `docker exec wholesaler_airflow_scheduler airflow dags trigger daily_lead_scoring`

3. **Check history population**:
   - New leads are detected by comparing with yesterday's history
   - On first run, all Tier A leads will be "new"
   - Subsequent runs will only alert on truly new Tier A properties

## Alert Schedule

The complete daily alert schedule:

```
2:00 AM  - daily_property_ingestion (scrape new data)
3:00 AM  - daily_transformation_pipeline (enrich + dedupe)
4:00 AM  - daily_lead_scoring (score + rank + create history)
5:00 AM  - tier_a_alert_notifications (send alerts for NEW Tier A leads)
6:30 AM  - data_quality_checks (send quality reports)
```

All times in server timezone (UTC by default).

## Customizing Alert Content

### Email Template

Edit `dags/utils/notifications.py`, function `format_tier_a_leads_message()`:

```python
def format_tier_a_leads_message(leads: List[Dict[str, Any]]) -> str:
    # Customize message format here
    # Current: Shows top 10 leads with address, score, tier
    # Can add: property type, estimated ARV, profit potential
```

### Alert Frequency

Edit DAG schedule in `dags/tier_a_alert_notifications.py`:

```python
# Current: Daily at 5:00 AM
schedule_interval='0 5 * * *'

# Options:
# Twice daily: '0 5,17 * * *'  (5 AM and 5 PM)
# Hourly: '0 * * * *'
# Weekly: '0 5 * * 1'  (Mondays at 5 AM)
```

## Security Best Practices

1. **Never commit `.env` file** to version control
   - Already in `.gitignore`

2. **Use app passwords** for Gmail, not account password
   - Limits access scope
   - Can be revoked independently

3. **Rotate credentials** periodically (every 90 days)

4. **Use separate email** for production vs development
   - Prevents accidental spam to real users

5. **Enable Slack webhook restrictions**:
   - Go to Slack App Settings → "Basic Information"
   - Add "Allowed IP Addresses" (your server IP)

## Production Checklist

- [ ] SMTP credentials configured in `.env`
- [ ] Slack webhook configured in `.env`
- [ ] Test email sent successfully
- [ ] Test Slack message sent successfully
- [ ] Tier A leads exist in database (or thresholds adjusted)
- [ ] LeadScoreHistory table is being populated (check after first daily run)
- [ ] Alerts received for first manual trigger
- [ ] Alert schedule confirmed (check Airflow DAG runs)
- [ ] Credentials stored securely (not in git)
- [ ] Production email/Slack channels configured
- [ ] Team members added to alert recipient list

## Support

For alert system issues:
- Check Airflow logs: http://localhost:8080 → DAG Runs → tier_a_alert_notifications
- Check application logs: `docker logs wholesaler_airflow_scheduler`
- Review DAG source: `dags/tier_a_alert_notifications.py`
- Review notification utils: `dags/utils/notifications.py`

## References

- Airflow External Task Sensor: https://airflow.apache.org/docs/apache-airflow/stable/howto/operator/external_task_sensor.html
- Gmail App Passwords: https://support.google.com/accounts/answer/185833
- Slack Webhooks: https://api.slack.com/messaging/webhooks
- SendGrid SMTP: https://docs.sendgrid.com/for-developers/sending-email/integrating-with-the-smtp-api
- AWS SES SMTP: https://docs.aws.amazon.com/ses/latest/dg/send-email-smtp.html
