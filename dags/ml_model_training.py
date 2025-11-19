"""
ML Model Training DAG

Weekly training and evaluation of ML models for lead scoring.
Trains distress classifier and sale probability models.

Schedule: Weekly on Sunday at 2:00 AM
"""
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor

from src.wholesaler.db.session import get_db_session
from src.wholesaler.ml.training.model_registry import ModelRegistryManager
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# DAG default arguments
default_args = {
    'owner': 'wholesaler',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=15),
    'execution_timeout': timedelta(hours=4),
}


def check_training_data(**context):
    """
    Check that sufficient training data is available.

    Returns:
        Training data statistics
    """
    logger.info("checking_training_data_availability")

    from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        df = builder.build_feature_dataframe()

        stats = {
            'total_samples': len(df),
            'feature_count': len(df.columns),
            'has_sufficient_data': len(df) >= 50,  # Minimum threshold
        }

        logger.info("training_data_check_completed", stats=stats)

        if not stats['has_sufficient_data']:
            logger.warning(
                "insufficient_training_data",
                samples=stats['total_samples'],
                minimum_required=50,
            )

        context['task_instance'].xcom_push(
            key='training_data_stats',
            value=stats
        )

        return stats


def train_distress_classifier(**context):
    """
    Train binary distress classifier model.

    Uses LightGBM with calibration for probability estimation.
    """
    logger.info("training_distress_classifier")

    from src.wholesaler.ml.training import train_distress_classifier as trainer

    try:
        model_data = trainer.main()

        metrics = model_data['metrics']
        model_path = model_data.get('model_path', 'models/distress_classifier.joblib')

        result = {
            'model_path': model_path,
            'metrics': {
                'roc_auc': metrics['roc_auc'],
                'pr_auc': metrics['pr_auc'],
                'accuracy': metrics['accuracy'],
            },
            'success': True,
        }

        logger.info("distress_classifier_trained", result=result)

        context['task_instance'].xcom_push(
            key='distress_classifier_result',
            value=result
        )

        return result

    except Exception as e:
        logger.error("distress_classifier_training_failed", error=str(e))
        result = {
            'success': False,
            'error': str(e),
        }
        context['task_instance'].xcom_push(
            key='distress_classifier_result',
            value=result
        )
        raise


def train_sale_probability(**context):
    """
    Train sale probability regression model.

    Uses logistic regression for probability estimation.
    """
    logger.info("training_sale_probability_model")

    from src.wholesaler.ml.training import train_sale_probability as trainer

    try:
        model_data = trainer.main()

        metrics = model_data['metrics']

        result = {
            'model_path': 'models/sale_probability.joblib',
            'metrics': {
                'roc_auc': metrics['roc_auc'],
                'brier_score': metrics['brier_score'],
                'log_loss': metrics['log_loss'],
                'mae': metrics['mae'],
            },
            'success': True,
        }

        logger.info("sale_probability_model_trained", result=result)

        context['task_instance'].xcom_push(
            key='sale_probability_result',
            value=result
        )

        return result

    except Exception as e:
        logger.error("sale_probability_training_failed", error=str(e))
        result = {
            'success': False,
            'error': str(e),
        }
        context['task_instance'].xcom_push(
            key='sale_probability_result',
            value=result
        )
        raise


def register_models(**context):
    """
    Register trained models in the model registry.

    Stores metadata and promotes models if they meet quality thresholds.
    """
    ti = context['task_instance']

    distress_result = ti.xcom_pull(
        task_ids='train_distress_classifier',
        key='distress_classifier_result'
    )
    probability_result = ti.xcom_pull(
        task_ids='train_sale_probability',
        key='sale_probability_result'
    )

    logger.info(
        "registering_models",
        distress_result=distress_result,
        probability_result=probability_result,
    )

    registration_results = []

    with get_db_session() as session:
        with ModelRegistryManager(session) as registry:

            # Register distress classifier
            if distress_result and distress_result.get('success'):
                version = datetime.now().strftime("%Y%m%d_%H%M%S")
                model_record = registry.register_model(
                    model_name='distress_classifier',
                    version=version,
                    artifact_path=distress_result['model_path'],
                    metrics=distress_result['metrics'],
                )

                # Promote if ROC-AUC > 0.7
                if distress_result['metrics']['roc_auc'] > 0.7:
                    registry.promote_model('distress_classifier', version)
                    logger.info(
                        "distress_classifier_promoted",
                        version=version,
                        roc_auc=distress_result['metrics']['roc_auc'],
                    )

                registration_results.append({
                    'model': 'distress_classifier',
                    'version': version,
                    'registered': True,
                })

            # Register sale probability model
            if probability_result and probability_result.get('success'):
                version = datetime.now().strftime("%Y%m%d_%H%M%S")
                model_record = registry.register_model(
                    model_name='sale_probability',
                    version=version,
                    artifact_path=probability_result['model_path'],
                    metrics=probability_result['metrics'],
                )

                # Promote if ROC-AUC > 0.6
                if probability_result['metrics']['roc_auc'] > 0.6:
                    registry.promote_model('sale_probability', version)
                    logger.info(
                        "sale_probability_model_promoted",
                        version=version,
                        roc_auc=probability_result['metrics']['roc_auc'],
                    )

                registration_results.append({
                    'model': 'sale_probability',
                    'version': version,
                    'registered': True,
                })

    context['task_instance'].xcom_push(
        key='registration_results',
        value=registration_results
    )

    logger.info("models_registered", results=registration_results)

    return registration_results


def cleanup_old_models(**context):
    """
    Clean up old model versions to save storage.

    Keeps the latest N versions and removes older ones.
    """
    logger.info("cleaning_up_old_model_versions")

    with get_db_session() as session:
        with ModelRegistryManager(session) as registry:
            # Cleanup distress classifier (keep 5 versions)
            distress_cleanup = registry.cleanup_old_versions(
                'distress_classifier',
                keep_versions=5
            )

            # Cleanup sale probability (keep 5 versions)
            probability_cleanup = registry.cleanup_old_versions(
                'sale_probability',
                keep_versions=5
            )

            cleanup_stats = {
                'distress_classifier': distress_cleanup,
                'sale_probability': probability_cleanup,
            }

            logger.info("old_models_cleaned_up", stats=cleanup_stats)

            context['task_instance'].xcom_push(
                key='cleanup_stats',
                value=cleanup_stats
            )

            return cleanup_stats


def validate_training_run(**context):
    """
    Validate that model training completed successfully.

    Checks model metrics and registration status.
    """
    ti = context['task_instance']

    training_data_stats = ti.xcom_pull(
        task_ids='check_data',
        key='training_data_stats'
    )
    distress_result = ti.xcom_pull(
        task_ids='train_distress_classifier',
        key='distress_classifier_result'
    )
    probability_result = ti.xcom_pull(
        task_ids='train_sale_probability',
        key='sale_probability_result'
    )
    registration_results = ti.xcom_pull(
        task_ids='register_models',
        key='registration_results'
    )

    logger.info(
        "validating_training_run",
        training_data_stats=training_data_stats,
        distress_result=distress_result,
        probability_result=probability_result,
        registration_results=registration_results,
    )

    validation_results = {
        'passed': True,
        'warnings': [],
        'models_trained': 0,
        'models_registered': 0,
    }

    # Check training data
    if training_data_stats and not training_data_stats.get('has_sufficient_data'):
        validation_results['warnings'].append("Training with limited data")

    # Check distress classifier
    if distress_result and distress_result.get('success'):
        validation_results['models_trained'] += 1
        roc_auc = distress_result['metrics'].get('roc_auc', 0)
        if roc_auc < 0.6:
            validation_results['warnings'].append(
                f"Low distress classifier ROC-AUC: {roc_auc:.4f}"
            )
    else:
        validation_results['warnings'].append("Distress classifier training failed")

    # Check sale probability model
    if probability_result and probability_result.get('success'):
        validation_results['models_trained'] += 1
        roc_auc = probability_result['metrics'].get('roc_auc', 0)
        if roc_auc < 0.5:
            validation_results['warnings'].append(
                f"Low sale probability ROC-AUC: {roc_auc:.4f}"
            )
    else:
        validation_results['warnings'].append("Sale probability training failed")

    # Check registration
    if registration_results:
        validation_results['models_registered'] = len(registration_results)

    # Fail if no models trained
    if validation_results['models_trained'] == 0:
        validation_results['passed'] = False

    logger.info("training_validation_completed", results=validation_results)

    if not validation_results['passed']:
        raise ValueError("Model training validation failed: No models were trained")

    return validation_results


# Define the DAG
with DAG(
    'ml_model_training',
    default_args=default_args,
    description='Weekly ML model training and registration',
    schedule='0 2 * * 0',  # 2:00 AM on Sundays
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['ml', 'training', 'models', 'weekly'],
) as dag:

    # Task 1: Check training data availability
    check_data_task = PythonOperator(
        task_id='check_data',
        python_callable=check_training_data,
    )

    # Task 2: Train distress classifier
    train_distress_task = PythonOperator(
        task_id='train_distress_classifier',
        python_callable=train_distress_classifier,
    )

    # Task 3: Train sale probability model
    train_probability_task = PythonOperator(
        task_id='train_sale_probability',
        python_callable=train_sale_probability,
    )

    # Task 4: Register models
    register_models_task = PythonOperator(
        task_id='register_models',
        python_callable=register_models,
    )

    # Task 5: Cleanup old models
    cleanup_task = PythonOperator(
        task_id='cleanup_old_models',
        python_callable=cleanup_old_models,
    )

    # Task 6: Validate training run
    validate_task = PythonOperator(
        task_id='validate_training',
        python_callable=validate_training_run,
    )

    # Define dependencies
    # Check data first, then train models in parallel
    check_data_task >> [train_distress_task, train_probability_task]
    # Register and cleanup after training
    [train_distress_task, train_probability_task] >> register_models_task >> cleanup_task >> validate_task
