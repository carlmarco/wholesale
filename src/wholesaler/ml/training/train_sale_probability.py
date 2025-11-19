"""
Train Sale Probability Model

Regression model to predict probability of sale within N months or expected profit.
Uses logistic regression for probability estimation with feature engineering.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score,
    mean_absolute_error,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def build_training_dataset() -> pd.DataFrame:
    """
    Build training dataset with sale probability targets.

    Creates synthetic probability targets based on distress indicators
    until real outcome data is available.
    """
    logger.info("building_sale_probability_dataset")

    with get_db_session() as session:
        builder = FeatureStoreBuilder(session)
        df = builder.build_feature_dataframe()

    if df.empty:
        logger.error("empty_training_dataset")
        raise ValueError("No training data available. Run feature materialization first.")

    # Create synthetic probability target
    # This should be replaced with actual sale outcome data when available
    df["sale_probability"] = calculate_synthetic_probability(df)

    logger.info(
        "sale_probability_dataset_prepared",
        total=len(df),
        mean_probability=f"{df['sale_probability'].mean():.4f}",
    )

    return df


def calculate_synthetic_probability(df: pd.DataFrame) -> pd.Series:
    """
    Calculate synthetic sale probability based on distress indicators.

    This is a placeholder until real outcome data is available.
    Uses a logistic-like transformation of distress signals.
    """
    # Base probability
    prob = np.zeros(len(df))

    # Tax sale indicator (strong signal)
    if "seed_type_tax_sale" in df.columns:
        prob += df["seed_type_tax_sale"].astype(float) * 0.4

    # Foreclosure indicator
    if "seed_type_foreclosure" in df.columns:
        prob += df["seed_type_foreclosure"].astype(float) * 0.35

    # Code violation indicator
    if "seed_type_code_violation" in df.columns:
        prob += df["seed_type_code_violation"].astype(float) * 0.15

    # Violation count boost (diminishing returns)
    if "violation_count" in df.columns:
        violation_boost = np.minimum(df["violation_count"].fillna(0) * 0.05, 0.25)
        prob += violation_boost

    # Low equity boost
    if "equity_percent" in df.columns:
        equity = df["equity_percent"].fillna(50)
        low_equity_boost = ((100 - equity) / 100) * 0.15
        prob += low_equity_boost

    # Days to auction urgency
    if "days_to_auction" in df.columns:
        days = df["days_to_auction"].fillna(365)
        urgency_boost = np.where(days < 30, 0.1, np.where(days < 90, 0.05, 0))
        prob += urgency_boost

    # Normalize to 0-1 range
    prob = np.clip(prob, 0, 1)

    # Add small noise for realism
    noise = np.random.normal(0, 0.05, len(prob))
    prob = np.clip(prob + noise, 0.01, 0.99)

    return pd.Series(prob, index=df.index)


def select_features(df: pd.DataFrame) -> list[str]:
    """Select feature columns for probability model."""
    exclude_cols = {
        "parcel_id_normalized",
        "computed_at",
        "sale_probability",
        "target",
        "actual_distress_outcome",
        "actual_sale_price",
        "label_date",
    }

    feature_cols = [col for col in df.columns if col not in exclude_cols]

    logger.info("features_selected", count=len(feature_cols))

    return feature_cols


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
) -> dict:
    """
    Train sale probability model using logistic regression.

    Predicts probability scores that can be interpreted as sale likelihood.
    """
    logger.info("training_sale_probability_model")

    # Standardize features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)

    # Convert continuous probability to binary for logistic regression
    # Threshold at median probability
    y_train_binary = (y_train >= np.median(y_train)).astype(int)
    y_val_binary = (y_val >= np.median(y_val)).astype(int)

    # Train logistic regression
    model = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
        solver="lbfgs",
    )
    model.fit(X_train_scaled, y_train_binary)

    # Get probability predictions
    y_pred_proba = model.predict_proba(X_val_scaled)[:, 1]

    # Evaluate
    roc_auc = roc_auc_score(y_val_binary, y_pred_proba)
    brier = brier_score_loss(y_val_binary, y_pred_proba)
    logloss = log_loss(y_val_binary, y_pred_proba)

    # Compare predicted probability distribution to actual
    mae = mean_absolute_error(y_val, y_pred_proba)

    logger.info(
        "sale_probability_model_trained",
        roc_auc=f"{roc_auc:.4f}",
        brier_score=f"{brier:.4f}",
        log_loss=f"{logloss:.4f}",
        mae=f"{mae:.4f}",
    )

    # Feature coefficients
    coefficients = dict(zip(feature_names, model.coef_[0]))
    sorted_coef = sorted(coefficients.items(), key=lambda x: abs(x[1]), reverse=True)
    logger.info("feature_coefficients", top_5=sorted_coef[:5])

    return {
        "model": model,
        "scaler": scaler,
        "model_type": "LogisticRegression",
        "metrics": {
            "roc_auc": roc_auc,
            "brier_score": brier,
            "log_loss": logloss,
            "mae": mae,
            "coefficients": coefficients,
        },
        "feature_names": feature_names,
    }


def save_model(model_data: dict, output_dir: str = "models") -> str:
    """
    Save trained model to disk.

    Args:
        model_data: Dictionary containing model, scaler, metrics, and feature names.
        output_dir: Directory to save model artifacts.

    Returns:
        Path to saved model file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Version with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_file = output_path / f"sale_probability_{timestamp}.joblib"

    # Save model artifact with scaler
    artifact = {
        "model": model_data["model"],
        "scaler": model_data["scaler"],
        "feature_names": model_data["feature_names"],
        "model_type": model_data["model_type"],
        "version": timestamp,
        "trained_at": datetime.now().isoformat(),
    }
    joblib.dump(artifact, model_file)

    # Save metrics separately
    metrics_file = output_path / f"sale_probability_{timestamp}_metrics.json"

    # Convert coefficients to serializable format
    metrics_to_save = model_data["metrics"].copy()
    metrics_to_save["coefficients"] = {
        k: float(v) for k, v in metrics_to_save["coefficients"].items()
    }

    with open(metrics_file, "w") as f:
        json.dump(metrics_to_save, f, indent=2, default=str)

    # Create symlink to latest
    latest_link = output_path / "sale_probability.joblib"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(model_file.name)

    logger.info(
        "sale_probability_model_saved",
        path=str(model_file),
        metrics_path=str(metrics_file),
        latest_link=str(latest_link),
    )

    return str(model_file)


def main():
    """Main training pipeline for sale probability model."""
    print("\n" + "=" * 60)
    print("SALE PROBABILITY MODEL TRAINING")
    print("=" * 60 + "\n")

    # Build dataset
    print("1. Building training dataset...")
    df = build_training_dataset()
    print(f"   Dataset size: {len(df)} samples")
    print(f"   Mean probability: {df['sale_probability'].mean():.4f}")

    # Select features
    print("\n2. Selecting features...")
    feature_cols = select_features(df)
    print(f"   Using {len(feature_cols)} features")

    # Prepare data
    X = df[feature_cols].values
    y = df["sale_probability"].values

    # Handle missing values
    X = np.nan_to_num(X, nan=0.0)

    # Split data
    print("\n3. Splitting data...")
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
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
    print(f"   Brier Score: {metrics['brier_score']:.4f}")
    print(f"   Log Loss: {metrics['log_loss']:.4f}")
    print(f"   MAE: {metrics['mae']:.4f}")

    # Top feature coefficients
    print("\nTop Feature Coefficients:")
    sorted_coef = sorted(metrics["coefficients"].items(), key=lambda x: abs(x[1]), reverse=True)
    for feat, coef in sorted_coef[:5]:
        print(f"   {feat}: {coef:.4f}")

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
