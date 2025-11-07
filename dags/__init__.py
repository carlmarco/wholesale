"""
Airflow DAGs Package

Contains all DAG definitions for the Real Estate Wholesaler automated pipeline.

DAGs:
- daily_property_ingestion: Scrape tax sales and foreclosures (2:00 AM)
- daily_transformation_pipeline: Enrich and deduplicate (3:00 AM)
- daily_lead_scoring: Score and rank leads (4:00 AM)
- tier_a_alert_notifications: Alert on hot leads (5:00 AM)
- data_quality_checks: Validate data integrity (6:00 AM)
"""
