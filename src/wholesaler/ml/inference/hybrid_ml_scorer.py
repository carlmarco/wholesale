"""
Hybrid ML Scorer

Combines ML model predictions with heuristic scores for lead prioritization.
Loads trained models and performs real-time inference.
"""
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MLPrediction:
    """ML model prediction result."""

    probability: float  # Distress probability (0-1)
    expected_return: float  # Expected ROI in dollars
    confidence: float  # Model confidence (0-1)
    priority_flag: bool  # High priority recommendation
    tier_recommendation: str  # Suggested tier (A/B/C/D)
    reasons: list[str]  # Explanation of ML factors


class HybridMLScorer:
    """
    ML-based scorer that combines trained models with heuristic features.

    Loads distress classifier and sale probability models to provide:
    - Distress probability prediction
    - Expected return estimation
    - Priority flag recommendation
    - Confidence scoring
    """

    def __init__(
        self,
        models_dir: str = "models",
        distress_model_file: str = "distress_classifier.joblib",
        probability_model_file: str = "sale_probability.joblib",
    ):
        """
        Initialize scorer with model paths.

        Args:
            models_dir: Directory containing model artifacts.
            distress_model_file: Filename for distress classifier.
            probability_model_file: Filename for sale probability model.
        """
        self.models_dir = Path(models_dir)
        self.distress_model_path = self.models_dir / distress_model_file
        self.probability_model_path = self.models_dir / probability_model_file

        self._distress_model = None
        self._probability_model = None
        self._feature_names = None

        # Load models on initialization
        self._load_models()

    def _load_models(self):
        """Load ML models from disk."""
        # Load distress classifier
        if self.distress_model_path.exists():
            try:
                model_data = joblib.load(self.distress_model_path)
                if isinstance(model_data, dict):
                    self._distress_model = model_data.get("model")
                    self._feature_names = model_data.get("feature_names", [])
                else:
                    self._distress_model = model_data
                logger.info("distress_model_loaded", path=str(self.distress_model_path))
            except Exception as e:
                logger.warning("distress_model_load_failed", error=str(e))
        else:
            logger.warning("distress_model_not_found", path=str(self.distress_model_path))

        # Load sale probability model
        if self.probability_model_path.exists():
            try:
                model_data = joblib.load(self.probability_model_path)
                if isinstance(model_data, dict):
                    self._probability_model = model_data.get("model")
                else:
                    self._probability_model = model_data
                logger.info("probability_model_loaded", path=str(self.probability_model_path))
            except Exception as e:
                logger.warning("probability_model_load_failed", error=str(e))
        else:
            logger.warning("probability_model_not_found", path=str(self.probability_model_path))

    def score(self, enriched_data: dict) -> MLPrediction:
        """
        Score a property using ML models.

        Args:
            enriched_data: Dictionary containing enriched seed data and property info.

        Returns:
            MLPrediction with probability, expected return, and recommendations.
        """
        # Build feature vector
        features = self._build_feature_vector(enriched_data)
        reasons = []

        # Get distress probability
        if self._distress_model is not None:
            probability = self._predict_distress_probability(features)
            reasons.append(f"ML distress probability: {probability:.2%}")
        else:
            # Fallback heuristic
            probability = self._heuristic_probability(enriched_data)
            reasons.append(f"Heuristic probability (no model): {probability:.2%}")

        # Get expected return
        if self._probability_model is not None:
            expected_return = self._predict_expected_return(features, enriched_data)
            reasons.append(f"ML expected return: ${expected_return:,.0f}")
        else:
            expected_return = self._heuristic_expected_return(enriched_data)
            reasons.append(f"Heuristic expected return: ${expected_return:,.0f}")

        # Compute confidence based on feature completeness and model availability
        confidence = self._compute_confidence(features, enriched_data)

        # Determine priority flag
        priority_flag = self._determine_priority(probability, expected_return, confidence)
        if priority_flag:
            reasons.append("HIGH PRIORITY: Strong ML signals")

        # Recommend tier based on ML outputs
        tier_recommendation = self._recommend_tier(probability, expected_return, confidence)
        reasons.append(f"ML tier recommendation: {tier_recommendation}")

        return MLPrediction(
            probability=probability,
            expected_return=expected_return,
            confidence=confidence,
            priority_flag=priority_flag,
            tier_recommendation=tier_recommendation,
            reasons=reasons,
        )

    def _build_feature_vector(self, enriched_data: dict) -> np.ndarray:
        """
        Build feature vector from enriched data for model inference.

        Returns numpy array in the order expected by trained models.
        """
        today = date.today()

        # Extract features in consistent order
        features = []

        # Violation features
        violation_count = enriched_data.get("violation_count", 0) or 0
        features.append(violation_count)

        # Open violations
        open_violations = self._count_open_violations(enriched_data)
        features.append(open_violations)

        # Days since last violation
        days_since = self._compute_days_since_violation(enriched_data, today)
        features.append(days_since if days_since is not None else 365)

        # Property record features
        prop_record = enriched_data.get("property_record", {})
        features.append(prop_record.get("total_mkt", 0) or 0)
        features.append(prop_record.get("equity_percent", 50) or 50)

        # Year built / age
        year_built = prop_record.get("year_built")
        if year_built:
            features.append(today.year - year_built)
        else:
            features.append(30)  # Default 30 years old

        # Seed type encoding
        seed_type = enriched_data.get("seed_type", "code_violation")
        features.append(1 if seed_type == "tax_sale" else 0)
        features.append(1 if seed_type == "foreclosure" else 0)
        features.append(1 if seed_type == "code_violation" else 0)

        # Geo features
        features.append(enriched_data.get("geo_nearby_violations", 0) or 0)

        return np.array(features).reshape(1, -1)

    def _predict_distress_probability(self, features: np.ndarray) -> float:
        """Predict distress probability using trained classifier."""
        try:
            if hasattr(self._distress_model, "predict_proba"):
                proba = self._distress_model.predict_proba(features)
                return float(proba[0][1])  # Probability of positive class
            else:
                pred = self._distress_model.predict(features)
                return float(pred[0])
        except Exception as e:
            logger.warning("distress_prediction_failed", error=str(e))
            return 0.5

    def _predict_expected_return(self, features: np.ndarray, enriched_data: dict) -> float:
        """Predict expected return using sale probability model."""
        try:
            if hasattr(self._probability_model, "predict"):
                # Get probability or score from model
                score = self._probability_model.predict(features)[0]

                # Estimate ROI based on market value and distress indicators
                market_value = enriched_data.get("property_record", {}).get("total_mkt", 100000)
                if not market_value:
                    market_value = 100000

                # Expected return = potential discount * market value * sale probability
                potential_discount = 0.3  # Assume 30% discount on distressed properties
                return float(score * potential_discount * market_value)
            else:
                return self._heuristic_expected_return(enriched_data)
        except Exception as e:
            logger.warning("expected_return_prediction_failed", error=str(e))
            return self._heuristic_expected_return(enriched_data)

    def _heuristic_probability(self, enriched_data: dict) -> float:
        """Fallback heuristic probability when no model available."""
        score = 0.3  # Base probability

        # Violation boost
        violations = enriched_data.get("violation_count", 0) or 0
        score += min(0.3, violations * 0.05)

        # Seed type boost
        seed_type = enriched_data.get("seed_type", "")
        if seed_type == "tax_sale":
            score += 0.25
        elif seed_type == "foreclosure":
            score += 0.20
        elif seed_type == "code_violation":
            score += 0.10

        # Equity penalty (low equity = higher distress)
        equity = enriched_data.get("property_record", {}).get("equity_percent", 50)
        if equity and equity < 30:
            score += 0.15

        return min(1.0, score)

    def _heuristic_expected_return(self, enriched_data: dict) -> float:
        """Fallback heuristic expected return calculation."""
        market_value = enriched_data.get("property_record", {}).get("total_mkt", 100000)
        if not market_value:
            market_value = 100000

        # Base expected return is 10% of market value
        base_return = market_value * 0.1

        # Adjust based on seed type
        seed_type = enriched_data.get("seed_type", "")
        if seed_type == "tax_sale":
            base_return *= 1.5
        elif seed_type == "foreclosure":
            base_return *= 1.3

        return base_return

    def _count_open_violations(self, enriched_data: dict) -> int:
        """Count open violations from enriched data."""
        violation_types = enriched_data.get("violation_types", [])
        if isinstance(violation_types, list):
            return len([v for v in violation_types if "OPEN" in str(v).upper()])
        return 0

    def _compute_days_since_violation(self, enriched_data: dict, today: date) -> Optional[int]:
        """Compute days since most recent violation."""
        most_recent = enriched_data.get("most_recent_violation")
        if not most_recent:
            return None

        if isinstance(most_recent, str):
            try:
                most_recent = date.fromisoformat(most_recent[:10])
            except (ValueError, TypeError):
                return None

        delta = today - most_recent
        return max(0, delta.days)

    def _compute_confidence(self, features: np.ndarray, enriched_data: dict) -> float:
        """
        Compute confidence score based on feature completeness and model availability.
        """
        confidence = 0.5  # Base confidence

        # Boost for having ML models
        if self._distress_model is not None:
            confidence += 0.2
        if self._probability_model is not None:
            confidence += 0.1

        # Boost for complete features
        prop_record = enriched_data.get("property_record", {})
        if prop_record.get("total_mkt"):
            confidence += 0.1
        if prop_record.get("equity_percent"):
            confidence += 0.05
        if prop_record.get("year_built"):
            confidence += 0.05

        return min(1.0, confidence)

    def _determine_priority(
        self, probability: float, expected_return: float, confidence: float
    ) -> bool:
        """Determine if property should be flagged as high priority."""
        # High probability of distress
        if probability >= 0.7 and confidence >= 0.6:
            return True

        # High expected return
        if expected_return >= 50000 and confidence >= 0.5:
            return True

        # Strong combination
        if probability >= 0.5 and expected_return >= 30000:
            return True

        return False

    def _recommend_tier(
        self, probability: float, expected_return: float, confidence: float
    ) -> str:
        """Recommend tier based on ML outputs."""
        # Weighted score
        ml_score = (probability * 60) + (min(expected_return / 1000, 40))

        # Confidence adjustment
        adjusted_score = ml_score * (0.5 + confidence * 0.5)

        if adjusted_score >= 55:
            return "A"
        elif adjusted_score >= 40:
            return "B"
        elif adjusted_score >= 25:
            return "C"
        else:
            return "D"

    def blend_with_heuristic(
        self,
        ml_prediction: MLPrediction,
        heuristic_score: float,
        heuristic_tier: str,
        weight_ml: float = 0.4,
    ) -> dict:
        """
        Blend ML prediction with heuristic scoring.

        Args:
            ml_prediction: ML model prediction result.
            heuristic_score: Total score from heuristic scorer (0-100).
            heuristic_tier: Tier from heuristic scorer (A/B/C/D).
            weight_ml: Weight for ML score (0-1).

        Returns:
            Dictionary with blended results.
        """
        weight_heuristic = 1.0 - weight_ml

        # Convert ML probability to 0-100 scale
        ml_score = ml_prediction.probability * 100

        # Blend scores
        blended_score = (heuristic_score * weight_heuristic) + (ml_score * weight_ml)

        # Determine final tier
        if blended_score >= 60:
            final_tier = "A"
        elif blended_score >= 45:
            final_tier = "B"
        elif blended_score >= 32:
            final_tier = "C"
        else:
            final_tier = "D"

        # Priority flag: use ML recommendation or upgrade based on confidence
        priority_flag = ml_prediction.priority_flag or (
            ml_prediction.probability >= 0.65 and ml_prediction.confidence >= 0.7
        )

        return {
            "blended_score": round(blended_score, 2),
            "final_tier": final_tier,
            "priority_flag": priority_flag,
            "ml_probability": ml_prediction.probability,
            "expected_return": ml_prediction.expected_return,
            "ml_confidence": ml_prediction.confidence,
            "heuristic_score": heuristic_score,
            "heuristic_tier": heuristic_tier,
            "ml_tier_recommendation": ml_prediction.tier_recommendation,
            "reasons": ml_prediction.reasons,
        }
