"""
Train Distress Classifier

Binary classification model to predict if a property will experience a distress event
(tax sale, foreclosure, or similar). Uses LightGBM/XGBoost with proper calibration.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_recall_curve,
    roc_auc_score,
    average_precision_score,
)
from sklearn.model_selection import train_test_split

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


# Try to import LightGBM, fallback to XGBoost
try:
    from lightgbm import LGBMClassifier

    USE_LIGHTGBM = True
except ImportError:
    USE_LIGHTGBM = False

try:
    from xgboost import XGBClassifier

    USE_XGBOOST = True
except ImportError:
    USE_XGBOOST = False


def build_training_dataset() -> pd.DataFrame:
    """
    Build training dataset from feature store.

    Uses enriched seeds with labels. For initial training without actual outcomes,
    uses heuristic labels based on seed type (tax_sale/foreclosure = distressed).
    """
    logger.info("building_training_dataset")

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        df = builder.build_feature_dataframe()

    if df.empty:
        logger.error("empty_training_dataset")
        raise ValueError("No training data available. Run feature materialization first.")

    # Create target variable
    # Initially: properties with tax_sale or foreclosure seed are labeled as distressed
    df["target"] = (
        df["seed_type_tax_sale"].astype(int) | df["seed_type_foreclosure"].astype(int)
    ).astype(int)

    # Log class distribution
    distressed_count = df["target"].sum()
    total_count = len(df)
    logger.info(
        "training_data_prepared",
        total=total_count,
        distressed=distressed_count,
        ratio=f"{distressed_count/total_count:.2%}",
    )

    return df


def select_features(df: pd.DataFrame) -> list[str]:
    """Select feature columns for model training."""
    # Exclude non-feature columns
    exclude_cols = {
        "parcel_id_normalized",
        "computed_at",
        "target",
        "actual_distress_outcome",
        "actual_sale_price",
        "label_date",
    }

    feature_cols = [col for col in df.columns if col not in exclude_cols]

    logger.info("features_selected", count=len(feature_cols), features=feature_cols)

    return feature_cols


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
) -> dict:
    """
    Train distress classifier model.

    Uses LightGBM if available, otherwise XGBoost, with probability calibration.
    """
    logger.info("training_distress_classifier")

    # Select model
    if USE_LIGHTGBM:
        base_model = LGBMClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        model_type = "LightGBM"
    elif USE_XGBOOST:
        base_model = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            use_label_encoder=False,
            eval_metric="logloss",
            verbosity=0,
        )
        model_type = "XGBoost"
    else:
        from sklearn.ensemble import GradientBoostingClassifier

        base_model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
        )
        model_type = "GradientBoosting"

    # Train base model
    base_model.fit(X_train, y_train)

    # Calibrate probabilities using isotonic regression
    calibrated_model = CalibratedClassifierCV(
        base_model, method="isotonic", cv="prefit"
    )
    calibrated_model.fit(X_val, y_val)

    # Evaluate
    y_pred_proba = calibrated_model.predict_proba(X_val)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    # Metrics
    roc_auc = roc_auc_score(y_val, y_pred_proba)
    pr_auc = average_precision_score(y_val, y_pred_proba)
    accuracy = accuracy_score(y_val, y_pred)

    logger.info(
        "model_trained",
        model_type=model_type,
        roc_auc=f"{roc_auc:.4f}",
        pr_auc=f"{pr_auc:.4f}",
        accuracy=f"{accuracy:.4f}",
    )

    # Feature importance
    if hasattr(base_model, "feature_importances_"):
        importance = dict(zip(feature_names, base_model.feature_importances_))
        sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        logger.info("feature_importance", top_5=sorted_importance[:5])

    # Classification report
    report = classification_report(y_val, y_pred, output_dict=True)

    return {
        "model": calibrated_model,
        "base_model": base_model,
        "model_type": model_type,
        "metrics": {
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "accuracy": accuracy,
            "classification_report": report,
        },
        "feature_names": feature_names,
    }


def save_model(model_data: dict, output_dir: str = "models") -> str:
    """
    Save trained model to disk.

    Args:
        model_data: Dictionary containing model, metrics, and feature names.
        output_dir: Directory to save model artifacts.

    Returns:
        Path to saved model file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Version with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_file = output_path / f"distress_classifier_{timestamp}.joblib"

    # Save model artifact
    artifact = {
        "model": model_data["model"],
        "feature_names": model_data["feature_names"],
        "model_type": model_data["model_type"],
        "version": timestamp,
        "trained_at": datetime.now().isoformat(),
    }
    joblib.dump(artifact, model_file)

    # Save metrics separately
    metrics_file = output_path / f"distress_classifier_{timestamp}_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(model_data["metrics"], f, indent=2, default=str)

    # Create symlink to latest
    latest_link = output_path / "distress_classifier.joblib"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(model_file.name)

    logger.info(
        "model_saved",
        path=str(model_file),
        metrics_path=str(metrics_file),
        latest_link=str(latest_link),
    )

    return str(model_file)


def main():
    """Main training pipeline."""
    print("\n" + "=" * 60)
    print("DISTRESS CLASSIFIER TRAINING")
    print("=" * 60 + "\n")

    # Build dataset
    print("1. Building training dataset...")
    df = build_training_dataset()
    print(f"   Dataset size: {len(df)} samples")

    # Select features
    print("\n2. Selecting features...")
    feature_cols = select_features(df)
    print(f"   Using {len(feature_cols)} features")

    # Prepare data
    X = df[feature_cols].values
    y = df["target"].values

    # Handle missing values
    X = np.nan_to_num(X, nan=0.0)

    # Split data
    print("\n3. Splitting data...")
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"   Training set: {len(X_train)} samples")
    print(f"   Validation set: {len(X_val)} samples")

    # Train model
    print("\n4. Training model...")
    model_data = train_model(X_train, y_train, X_val, y_val, feature_cols)

    # Display metrics
    metrics = model_data["metrics"]
    print(f"\nModel Performance:")
    print(f"   ROC-AUC: {metrics['roc_auc']:.4f}")
    print(f"   PR-AUC:  {metrics['pr_auc']:.4f}")
    print(f"   Accuracy: {metrics['accuracy']:.4f}")

    # Save model
    print("\n5. Saving model...")
    model_path = save_model(model_data)
    print(f"   Model saved to: {model_path}")

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)

    return model_data


if __name__ == "__main__":
    main()
