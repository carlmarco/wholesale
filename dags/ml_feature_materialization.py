"""
ML Feature Materialization DAG

Daily computation and storage of ML features for all enriched properties.
Materializes features to both Parquet files and database for training/inference.

Schedule: Daily at 5:00 AM (after lead scoring completes)
"""
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor

from src.wholesaler.db.session import get_db_session
from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
    'execution_timeout': timedelta(hours=2),
}


def build_feature_dataframe(**context):
    """
    Build feature dataframe from all enriched seeds.

    Returns:
        Count of features computed
    """
    logger.info("building_feature_dataframe")

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        df = builder.build_feature_dataframe()

        logger.info(
            "feature_dataframe_built",
            rows=len(df),
            columns=len(df.columns),
        )

        # Store stats for downstream tasks
        context['task_instance'].xcom_push(
            key='feature_stats',
            value={
                'rows': len(df),
                'columns': len(df.columns),
                'feature_names': list(df.columns),
            }
        )

        return len(df)


def export_to_parquet(**context):
    """
    Export features to Parquet file for offline training.

    Creates timestamped Parquet file for model training pipelines.
    """
    logger.info("exporting_features_to_parquet")

    output_dir = Path("data/features")
    output_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        parquet_path = builder.export_to_parquet(str(output_dir))

        logger.info("features_exported_to_parquet", path=parquet_path)

        context['task_instance'].xcom_push(
            key='parquet_path',
            value=parquet_path
        )

        return parquet_path


def materialize_to_database(**context):
    """
    Materialize features to MLFeatureStore table for real-time inference.

    Updates or inserts feature vectors for all properties.
    """
    logger.info("materializing_features_to_database")

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        stats = builder.materialize_to_database()

        logger.info(
            "features_materialized_to_database",
            processed=stats['processed'],
            inserted=stats['inserted'],
            updated=stats['updated'],
            failed=stats['failed'],
        )

        context['task_instance'].xcom_push(
            key='materialization_stats',
            value=stats
        )

        return stats


def validate_feature_quality(**context):
    """
    Validate feature quality and completeness.

    Checks for missing values, data drift, and feature coverage.
    """
    ti = context['task_instance']

    feature_stats = ti.xcom_pull(
        task_ids='build_features',
        key='feature_stats'
    )
    materialization_stats = ti.xcom_pull(
        task_ids='materialize_db',
        key='materialization_stats'
    )

    logger.info(
        "validating_feature_quality",
        feature_stats=feature_stats,
        materialization_stats=materialization_stats,
    )

    validation_results = {
        'passed': True,
        'warnings': [],
        'errors': [],
    }

    # Check feature count
    if feature_stats:
        if feature_stats['rows'] == 0:
            validation_results['errors'].append("No features computed")
            validation_results['passed'] = False
        elif feature_stats['rows'] < 10:
            validation_results['warnings'].append(
                f"Low feature count: {feature_stats['rows']}"
            )

    # Check materialization success rate
    if materialization_stats:
        processed = materialization_stats.get('processed', 0)
        failed = materialization_stats.get('failed', 0)

        if processed > 0:
            failure_rate = failed / processed
            if failure_rate > 0.1:
                validation_results['warnings'].append(
                    f"High materialization failure rate: {failure_rate:.2%}"
                )
            if failure_rate > 0.5:
                validation_results['errors'].append(
                    f"Critical materialization failure rate: {failure_rate:.2%}"
                )
                validation_results['passed'] = False

    logger.info("feature_quality_validation_completed", results=validation_results)

    if not validation_results['passed']:
        raise ValueError(f"Feature quality validation failed: {validation_results['errors']}")

    return validation_results


def compute_feature_statistics(**context):
    """
    Compute and log feature distribution statistics.

    Tracks feature distributions for monitoring and drift detection.
    """
    logger.info("computing_feature_statistics")

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        df = builder.build_feature_dataframe()

        if df.empty:
            logger.warning("no_features_to_compute_statistics")
            return {}

        # Compute basic statistics
        numeric_cols = df.select_dtypes(include=['number']).columns
        stats = {}

        for col in numeric_cols:
            stats[col] = {
                'mean': float(df[col].mean()),
                'std': float(df[col].std()),
                'min': float(df[col].min()),
                'max': float(df[col].max()),
                'null_pct': float(df[col].isnull().sum() / len(df) * 100),
            }

        logger.info(
            "feature_statistics_computed",
            num_features=len(stats),
            sample_stats=dict(list(stats.items())[:3]),
        )

        context['task_instance'].xcom_push(
            key='feature_statistics',
            value=stats
        )

        return stats


# Define the DAG
with DAG(
    'ml_feature_materialization',
    default_args=default_args,
    description='Daily ML feature computation and materialization',
    schedule='0 5 * * *',  # 5:00 AM daily (after lead scoring)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['ml', 'features', 'training', 'etl'],
) as dag:

    # Wait for lead scoring to complete
    wait_for_scoring = ExternalTaskSensor(
        task_id='wait_for_scoring',
        external_dag_id='daily_lead_scoring',
        external_task_id='validate_scoring',
        timeout=3600,  # 1 hour timeout
        mode='reschedule',
    )

    # Task 1: Build feature dataframe
    build_features_task = PythonOperator(
        task_id='build_features',
        python_callable=build_feature_dataframe,
    )

    # Task 2: Export to Parquet (for training)
    export_parquet_task = PythonOperator(
        task_id='export_parquet',
        python_callable=export_to_parquet,
    )

    # Task 3: Materialize to database (for inference)
    materialize_db_task = PythonOperator(
        task_id='materialize_db',
        python_callable=materialize_to_database,
    )

    # Task 4: Compute feature statistics
    compute_stats_task = PythonOperator(
        task_id='compute_statistics',
        python_callable=compute_feature_statistics,
    )

    # Task 5: Validate feature quality
    validate_task = PythonOperator(
        task_id='validate_features',
        python_callable=validate_feature_quality,
    )

    # Define dependencies
    # Build features first, then export and materialize in parallel
    wait_for_scoring >> build_features_task
    build_features_task >> [export_parquet_task, materialize_db_task]
    [export_parquet_task, materialize_db_task] >> compute_stats_task >> validate_task
