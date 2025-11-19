"""
Lead Qualification Model Training

Trains a classifier that predicts the likelihood of a lead being Tier A.

.. deprecated:: 2025-11
    This module is deprecated in favor of train_distress_classifier.py which uses
    the centralized FeatureStoreBuilder and predicts actual distress outcomes rather
    than heuristic-based tier assignments.

    Migration:
        from src.wholesaler.ml.training.train_distress_classifier import main as train_distress
        train_distress()

    The new module provides:
    - Centralized feature store integration
    - Calibrated probability outputs
    - Support for LightGBM/XGBoost with fallback
    - Better model versioning and artifact management
"""
import argparse
import warnings
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score
from xgboost import XGBClassifier

from src.wholesaler.ml.training.feature_builder import FeatureBuilder
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

warnings.warn(
    "train_lead_model.py is deprecated. Use train_distress_classifier.py instead.",
    DeprecationWarning,
    stacklevel=1,
)


def train_lead_model(
    output_path: Path,
    test_size: float = 0.2,
    random_state: int = 42,
    recent_days: int = 90,
):
    builder = FeatureBuilder()
    dataset = builder.build_lead_dataset(recent_days=recent_days)

    if dataset.empty:
        logger.error("lead_training_failed", reason="no_data")
        raise ValueError("No data available for lead training")

    # Data diagnostics - class distribution
    target = dataset["label_tier_a"]
    class_distribution = target.value_counts().to_dict()
    positive_rate = target.mean()

    logger.info(
        "lead_dataset_diagnostics",
        total_rows=len(dataset),
        tier_a_count=int(target.sum()),
        not_tier_a_count=int((~target).sum()),
        positive_rate=float(positive_rate),
        class_balance=f"{positive_rate:.1%}",
        null_count=dataset.isnull().sum().sum(),
    )
    feature_columns = [
        col
        for col in dataset.columns
        if col not in (
            "label_tier_a",
            "tier",
            "parcel_id_normalized",
            "parcel_id_original",
            "scored_at",
            "created_at",
            "updated_at",
        )
    ]

    features = dataset[feature_columns].select_dtypes(include=[np.number]).fillna(0)

    # Log feature statistics
    logger.info(
        "lead_feature_statistics",
        total_features=len(feature_columns),
        numeric_features=len(features.columns),
        missing_values_filled=dataset[feature_columns].isnull().sum().sum(),
    )

    # Check if we have enough positive examples
    positive_count = target.sum()
    if positive_count == 0:
        logger.warning("lead_training_no_positive_examples",
                      reason="no_tier_a_leads",
                      recommendation="Increase data or lower tier threshold")
        raise ValueError("No Tier A leads available for training. Need at least some positive examples.")

    if positive_count < 5:
        logger.warning("lead_training_few_positive_examples",
                      positive_count=positive_count,
                      recommendation="Consider lowering tier threshold or collecting more data")

    X_train, X_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=test_size,
        random_state=random_state,
        stratify=target,
    )

    # Calculate base_score from class distribution to avoid XGBoost error
    # base_score should be the probability of positive class (Tier A)
    # In logit space: logit(p) = log(p / (1-p))
    positive_rate = positive_count / len(target)

    # Ensure positive_rate is within valid bounds for logistic loss (0, 1)
    positive_rate = np.clip(positive_rate, 0.001, 0.999)

    model = XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.7,
        colsample_bytree=0.8,
        random_state=random_state,
        n_jobs=-1,
        eval_metric="logloss",
        base_score=positive_rate,  # Set base_score to class prior probability
    )

    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    roc_auc = roc_auc_score(y_test, proba)
    pr_auc = average_precision_score(y_test, proba)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": features.columns.tolist(),
            "version": "0.1.0",
            "metrics": {"roc_auc": float(roc_auc), "pr_auc": float(pr_auc)},
        },
        output_path,
    )

    logger.info(
        "lead_model_trained",
        artifact=str(output_path),
        rows=len(dataset),
        feature_count=len(features.columns),
        roc_auc=roc_auc,
        pr_auc=pr_auc,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Train lead qualification model")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/lead_model.joblib"),
        help="Path to save trained model",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--recent-days", type=int, default=90)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train_lead_model(
        output_path=args.output,
        test_size=args.test_size,
        random_state=args.random_state,
        recent_days=args.recent_days,
    )
