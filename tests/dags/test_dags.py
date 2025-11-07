"""
Tests for DAG Validation

Tests that all DAGs are importable and have correct configurations.
"""
import pytest
from datetime import timedelta


class TestDAGImports:
    """Tests for DAG import validation."""

    def test_import_daily_property_ingestion(self):
        """Test that daily_property_ingestion DAG imports without errors."""
        try:
            from dags import daily_property_ingestion
            assert hasattr(daily_property_ingestion, 'dag')
        except ImportError as e:
            pytest.fail(f"Failed to import daily_property_ingestion DAG: {e}")

    def test_import_daily_transformation_pipeline(self):
        """Test that daily_transformation_pipeline DAG imports without errors."""
        try:
            from dags import daily_transformation_pipeline
            assert hasattr(daily_transformation_pipeline, 'dag')
        except ImportError as e:
            pytest.fail(f"Failed to import daily_transformation_pipeline DAG: {e}")

    def test_import_daily_lead_scoring(self):
        """Test that daily_lead_scoring DAG imports without errors."""
        try:
            from dags import daily_lead_scoring
            assert hasattr(daily_lead_scoring, 'dag')
        except ImportError as e:
            pytest.fail(f"Failed to import daily_lead_scoring DAG: {e}")

    def test_import_tier_a_alert_notifications(self):
        """Test that tier_a_alert_notifications DAG imports without errors."""
        try:
            from dags import tier_a_alert_notifications
            assert hasattr(tier_a_alert_notifications, 'dag')
        except ImportError as e:
            pytest.fail(f"Failed to import tier_a_alert_notifications DAG: {e}")

    def test_import_data_quality_checks(self):
        """Test that data_quality_checks DAG imports without errors."""
        try:
            from dags import data_quality_checks
            assert hasattr(data_quality_checks, 'dag')
        except ImportError as e:
            pytest.fail(f"Failed to import data_quality_checks DAG: {e}")


class TestDAGConfigurations:
    """Tests for DAG configuration validation."""

    def test_ingestion_dag_config(self):
        """Test daily_property_ingestion DAG configuration."""
        from dags.daily_property_ingestion import dag

        assert dag.dag_id == 'daily_property_ingestion'
        assert dag.schedule_interval == '0 2 * * *'  # 2:00 AM daily
        assert dag.catchup is False
        assert 'ingestion' in dag.tags

        # Check default args
        assert dag.default_args['retries'] == 3
        assert dag.default_args['retry_delay'] == timedelta(minutes=5)

    def test_transformation_dag_config(self):
        """Test daily_transformation_pipeline DAG configuration."""
        from dags.daily_transformation_pipeline import dag

        assert dag.dag_id == 'daily_transformation_pipeline'
        assert dag.schedule_interval == '0 3 * * *'  # 3:00 AM daily
        assert dag.catchup is False
        assert 'transformation' in dag.tags

        # Check depends_on_past
        assert dag.default_args['depends_on_past'] is True

    def test_scoring_dag_config(self):
        """Test daily_lead_scoring DAG configuration."""
        from dags.daily_lead_scoring import dag

        assert dag.dag_id == 'daily_lead_scoring'
        assert dag.schedule_interval == '0 4 * * *'  # 4:00 AM daily
        assert dag.catchup is False
        assert 'scoring' in dag.tags

    def test_alerts_dag_config(self):
        """Test tier_a_alert_notifications DAG configuration."""
        from dags.tier_a_alert_notifications import dag

        assert dag.dag_id == 'tier_a_alert_notifications'
        assert dag.schedule_interval == '0 5 * * *'  # 5:00 AM daily
        assert dag.catchup is False
        assert 'alerts' in dag.tags

    def test_quality_checks_dag_config(self):
        """Test data_quality_checks DAG configuration."""
        from dags.data_quality_checks import dag

        assert dag.dag_id == 'data_quality_checks'
        assert dag.schedule_interval == '0 6 * * *'  # 6:00 AM daily
        assert dag.catchup is False
        assert 'quality' in dag.tags


class TestDAGTasks:
    """Tests for DAG task structure."""

    def test_ingestion_dag_tasks(self):
        """Test that ingestion DAG has expected tasks."""
        from dags.daily_property_ingestion import dag

        task_ids = [task.task_id for task in dag.tasks]

        assert 'scrape_tax_sales' in task_ids
        assert 'scrape_foreclosures' in task_ids
        assert 'validate_ingestion' in task_ids

        # Should have 3 tasks total
        assert len(task_ids) == 3

    def test_transformation_dag_tasks(self):
        """Test that transformation DAG has expected tasks."""
        from dags.daily_transformation_pipeline import dag

        task_ids = [task.task_id for task in dag.tasks]

        assert 'wait_for_ingestion' in task_ids
        assert 'fetch_properties' in task_ids
        assert 'enrich_properties' in task_ids
        assert 'deduplicate_properties' in task_ids
        assert 'validate_transformation' in task_ids

        # Should have 5 tasks total
        assert len(task_ids) == 5

    def test_scoring_dag_tasks(self):
        """Test that scoring DAG has expected tasks."""
        from dags.daily_lead_scoring import dag

        task_ids = [task.task_id for task in dag.tasks]

        assert 'wait_for_transformation' in task_ids
        assert 'fetch_properties' in task_ids
        assert 'score_leads' in task_ids
        assert 'create_snapshots' in task_ids
        assert 'calculate_statistics' in task_ids
        assert 'validate_scoring' in task_ids

        # Should have 6 tasks total
        assert len(task_ids) == 6

    def test_alerts_dag_tasks(self):
        """Test that alerts DAG has expected tasks."""
        from dags.tier_a_alert_notifications import dag

        task_ids = [task.task_id for task in dag.tasks]

        assert 'wait_for_scoring' in task_ids
        assert 'fetch_tier_a_leads' in task_ids
        assert 'identify_new_leads' in task_ids
        assert 'send_slack_alerts' in task_ids
        assert 'send_email_alerts' in task_ids
        assert 'generate_report' in task_ids
        assert 'log_summary' in task_ids

        # Should have 7 tasks total
        assert len(task_ids) == 7

    def test_quality_checks_dag_tasks(self):
        """Test that quality checks DAG has expected tasks."""
        from dags.data_quality_checks import dag

        task_ids = [task.task_id for task in dag.tasks]

        assert 'check_db_stats' in task_ids
        assert 'check_completeness' in task_ids
        assert 'check_consistency' in task_ids
        assert 'check_postgis' in task_ids
        assert 'generate_report' in task_ids
        assert 'send_alerts' in task_ids
        assert 'log_summary' in task_ids

        # Should have 7 tasks total
        assert len(task_ids) == 7


class TestDAGTaskDependencies:
    """Tests for DAG task dependencies."""

    def test_ingestion_dependencies(self):
        """Test task dependencies in ingestion DAG."""
        from dags.daily_property_ingestion import dag

        # Get tasks
        validate = dag.get_task('validate_ingestion')
        scrape_tax_sales = dag.get_task('scrape_tax_sales')
        scrape_foreclosures = dag.get_task('scrape_foreclosures')

        # Validate depends on both scrape tasks
        upstream_ids = [t.task_id for t in validate.upstream_list]
        assert 'scrape_tax_sales' in upstream_ids
        assert 'scrape_foreclosures' in upstream_ids

    def test_transformation_dependencies(self):
        """Test task dependencies in transformation DAG."""
        from dags.daily_transformation_pipeline import dag

        # Check linear dependency
        wait = dag.get_task('wait_for_ingestion')
        fetch = dag.get_task('fetch_properties')
        enrich = dag.get_task('enrich_properties')
        dedup = dag.get_task('deduplicate_properties')
        validate = dag.get_task('validate_transformation')

        # wait → fetch → enrich → dedup → validate
        assert fetch.task_id in [t.task_id for t in wait.downstream_list]
        assert enrich.task_id in [t.task_id for t in fetch.downstream_list]
        assert dedup.task_id in [t.task_id for t in enrich.downstream_list]
        assert validate.task_id in [t.task_id for t in dedup.downstream_list]

    def test_scoring_dependencies(self):
        """Test task dependencies in scoring DAG."""
        from dags.daily_lead_scoring import dag

        # Check linear dependency
        wait = dag.get_task('wait_for_transformation')
        fetch = dag.get_task('fetch_properties')
        score = dag.get_task('score_leads')
        snapshots = dag.get_task('create_snapshots')
        stats = dag.get_task('calculate_statistics')
        validate = dag.get_task('validate_scoring')

        # wait → fetch → score → snapshots → stats → validate
        assert fetch.task_id in [t.task_id for t in wait.downstream_list]
        assert score.task_id in [t.task_id for t in fetch.downstream_list]
        assert snapshots.task_id in [t.task_id for t in score.downstream_list]
        assert stats.task_id in [t.task_id for t in snapshots.downstream_list]
        assert validate.task_id in [t.task_id for t in stats.downstream_list]

    def test_alerts_parallel_tasks(self):
        """Test that alerts DAG runs Slack/email/report in parallel."""
        from dags.tier_a_alert_notifications import dag

        identify = dag.get_task('identify_new_leads')
        slack = dag.get_task('send_slack_alerts')
        email = dag.get_task('send_email_alerts')
        report = dag.get_task('generate_report')

        # All three should be downstream of identify
        downstream_ids = [t.task_id for t in identify.downstream_list]
        assert 'send_slack_alerts' in downstream_ids
        assert 'send_email_alerts' in downstream_ids
        assert 'generate_report' in downstream_ids

        # Slack and email should not depend on each other
        slack_upstream = [t.task_id for t in slack.upstream_list]
        assert 'send_email_alerts' not in slack_upstream

    def test_quality_checks_parallel_tasks(self):
        """Test that quality checks run validation tasks in parallel."""
        from dags.data_quality_checks import dag

        db_stats = dag.get_task('check_db_stats')
        completeness = dag.get_task('check_completeness')
        consistency = dag.get_task('check_consistency')
        postgis = dag.get_task('check_postgis')
        report = dag.get_task('generate_report')

        # All checks should be upstream of report
        report_upstream = [t.task_id for t in report.upstream_list]
        assert 'check_db_stats' in report_upstream
        assert 'check_completeness' in report_upstream
        assert 'check_consistency' in report_upstream
        assert 'check_postgis' in report_upstream

        # Checks should not depend on each other
        assert len(db_stats.upstream_list) == 0
        assert len(completeness.upstream_list) == 0
        assert len(consistency.upstream_list) == 0
        assert len(postgis.upstream_list) == 0
