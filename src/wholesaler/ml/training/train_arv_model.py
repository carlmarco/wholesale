"""
ARV Model Training Script

Builds a regression model to estimate After Repair Value (ARV)
using features extracted from the operational database.

.. deprecated:: 2025-11
    This module is deprecated. ARV prediction can now be derived from the centralized
    FeatureStoreBuilder which includes market value features. Consider using:
    - train_sale_probability.py for probability/expected return models
    - train_distress_classifier.py for distress classification

    The new modules provide better integration with the enriched seed pipeline
    and centralized feature management.
"""
import argparse
import warnings
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from src.wholesaler.ml.training.feature_builder import FeatureBuilder
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

warnings.warn(
    "train_arv_model.py is deprecated. Consider train_sale_probability.py or the centralized FeatureStoreBuilder.",
    DeprecationWarning,
    stacklevel=1,
)


def train_arv_model(
    output_path: Path,
    test_size: float = 0.2,
    random_state: int = 42,
    min_market_value: float = 50000,
    max_market_value: float = 800000,
):
    builder = FeatureBuilder()
    dataset = builder.build_arv_dataset(
        min_market_value=min_market_value,
        max_market_value=max_market_value,
    )

    if dataset.empty:
        logger.error("arv_training_failed", reason="no_data")
        raise ValueError("No data available for ARV training")

    # Data diagnostics
    logger.info(
        "arv_dataset_diagnostics",
        total_rows=len(dataset),
        min_value=dataset["total_mkt"].min(),
        max_value=dataset["total_mkt"].max(),
        median_value=dataset["total_mkt"].median(),
        null_count=dataset.isnull().sum().sum(),
    )

    target = dataset["total_mkt"].astype(float)

    feature_columns = [
        col
        for col in dataset.columns
        if col not in ("total_mkt", "parcel_id_normalized", "parcel_id_original")
    ]

    features = dataset[feature_columns].select_dtypes(include=[np.number]).fillna(0)

    # Log feature statistics
    logger.info(
        "arv_feature_statistics",
        total_features=len(feature_columns),
        numeric_features=len(features.columns),
        missing_values_filled=dataset[feature_columns].isnull().sum().sum(),
    )

    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=test_size, random_state=random_state
    )

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        n_jobs=-1,
        random_state=random_state,
    )

    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": feature_columns,
            "version": "0.1.0",
            "metrics": {"mae": float(mae), "r2": float(r2)},
        },
        output_path,
    )

    logger.info(
        "arv_model_trained",
        artifact=str(output_path),
        rows=len(dataset),
        feature_count=len(feature_columns),
        mae=mae,
        r2=r2,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Train ARV regression model")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/arv_model.joblib"),
        help="Path to save trained model",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--min-market-value", type=float, default=50000)
    parser.add_argument("--max-market-value", type=float, default=800000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train_arv_model(
        output_path=args.output,
        test_size=args.test_size,
        random_state=args.random_state,
        min_market_value=args.min_market_value,
        max_market_value=args.max_market_value,
    )

