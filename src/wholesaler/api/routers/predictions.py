"""
ML Predictions Router

Endpoints for ML model predictions and analysis.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.db.models import Property, EnrichedSeed, LeadScore
from src.wholesaler.ml.inference.hybrid_ml_scorer import HybridMLScorer
from src.wholesaler.ml.training.model_registry import ModelRegistryManager

router = APIRouter(prefix="/api/v1/ml", tags=["ml-predictions"])


# Response schemas
class MLPredictionResponse(BaseModel):
    """ML prediction result for a single property."""

    parcel_id_normalized: str
    probability: float
    expected_return: float
    confidence: float
    priority_flag: bool
    tier_recommendation: str
    reasons: List[str]


class BatchPredictionRequest(BaseModel):
    """Request for batch predictions."""

    parcel_ids: List[str]


class BatchPredictionResponse(BaseModel):
    """Response for batch predictions."""

    predictions: List[MLPredictionResponse]
    total: int
    successful: int
    failed: int


class ModelInfoResponse(BaseModel):
    """Information about a registered model."""

    model_name: str
    version: str
    artifact_path: str
    is_active: bool
    training_date: str
    metrics: Optional[dict] = None


# Initialize ML scorer (cached at module level)
_ml_scorer = None


def get_ml_scorer() -> HybridMLScorer:
    """Get or create ML scorer instance."""
    global _ml_scorer
    if _ml_scorer is None:
        _ml_scorer = HybridMLScorer()
    return _ml_scorer


@router.get("/predict/{parcel_id}", response_model=MLPredictionResponse)
def predict_single(
    parcel_id: str,
    db: Session = Depends(get_db),
):
    """
    Get ML prediction for a single property.

    Args:
        parcel_id: Normalized parcel ID.
        db: Database session.

    Returns:
        ML prediction with probability, expected return, and recommendations.
    """
    # Get property and enriched data
    property_obj = (
        db.query(Property)
        .filter(Property.parcel_id_normalized == parcel_id)
        .first()
    )

    if not property_obj:
        raise HTTPException(status_code=404, detail=f"Property {parcel_id} not found")

    # Build enriched data dict for scoring
    enriched_data = _build_enriched_data(property_obj, db)

    # Get ML prediction
    ml_scorer = get_ml_scorer()
    prediction = ml_scorer.score(enriched_data)

    return MLPredictionResponse(
        parcel_id_normalized=parcel_id,
        probability=prediction.probability,
        expected_return=prediction.expected_return,
        confidence=prediction.confidence,
        priority_flag=prediction.priority_flag,
        tier_recommendation=prediction.tier_recommendation,
        reasons=prediction.reasons,
    )


@router.post("/batch_predict", response_model=BatchPredictionResponse)
def predict_batch(
    request: BatchPredictionRequest,
    db: Session = Depends(get_db),
):
    """
    Get ML predictions for multiple properties.

    Args:
        request: List of parcel IDs.
        db: Database session.

    Returns:
        Batch prediction results with success/failure counts.
    """
    predictions = []
    successful = 0
    failed = 0

    ml_scorer = get_ml_scorer()

    for parcel_id in request.parcel_ids:
        try:
            property_obj = (
                db.query(Property)
                .filter(Property.parcel_id_normalized == parcel_id)
                .first()
            )

            if not property_obj:
                failed += 1
                continue

            enriched_data = _build_enriched_data(property_obj, db)
            prediction = ml_scorer.score(enriched_data)

            predictions.append(
                MLPredictionResponse(
                    parcel_id_normalized=parcel_id,
                    probability=prediction.probability,
                    expected_return=prediction.expected_return,
                    confidence=prediction.confidence,
                    priority_flag=prediction.priority_flag,
                    tier_recommendation=prediction.tier_recommendation,
                    reasons=prediction.reasons,
                )
            )
            successful += 1

        except Exception:
            failed += 1

    return BatchPredictionResponse(
        predictions=predictions,
        total=len(request.parcel_ids),
        successful=successful,
        failed=failed,
    )


@router.get("/priority_leads", response_model=List[MLPredictionResponse])
def get_priority_leads(
    min_probability: float = Query(0.5, ge=0, le=1, description="Minimum ML probability"),
    min_expected_return: float = Query(10000, ge=0, description="Minimum expected return"),
    limit: int = Query(50, ge=1, le=500, description="Number of results"),
    db: Session = Depends(get_db),
):
    """
    Get properties flagged as high priority by ML models.

    Args:
        min_probability: Minimum ML probability threshold.
        min_expected_return: Minimum expected return threshold.
        limit: Number of results to return.
        db: Database session.

    Returns:
        List of high-priority properties with ML predictions.
    """
    # Query properties with ML scores above thresholds
    query = (
        db.query(LeadScore)
        .filter(LeadScore.ml_probability >= min_probability)
        .filter(LeadScore.expected_return >= min_expected_return)
        .filter(LeadScore.priority_flag == True)
        .order_by(LeadScore.ml_probability.desc())
        .limit(limit)
    )

    results = []
    ml_scorer = get_ml_scorer()

    for lead_score in query.all():
        property_obj = lead_score.property
        enriched_data = _build_enriched_data(property_obj, db)
        prediction = ml_scorer.score(enriched_data)

        results.append(
            MLPredictionResponse(
                parcel_id_normalized=lead_score.parcel_id_normalized,
                probability=lead_score.ml_probability or prediction.probability,
                expected_return=lead_score.expected_return or prediction.expected_return,
                confidence=lead_score.ml_confidence or prediction.confidence,
                priority_flag=lead_score.priority_flag or prediction.priority_flag,
                tier_recommendation=prediction.tier_recommendation,
                reasons=prediction.reasons,
            )
        )

    return results


@router.get("/models", response_model=List[ModelInfoResponse])
def list_models(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    db: Session = Depends(get_db),
):
    """
    List registered ML models.

    Args:
        model_name: Optional filter by model name.
        db: Database session.

    Returns:
        List of registered models with metadata.
    """
    with ModelRegistryManager(db) as registry:
        models = registry.list_models(model_name)

    return [
        ModelInfoResponse(
            model_name=model.model_name,
            version=model.version,
            artifact_path=model.artifact_path,
            is_active=model.is_active,
            training_date=model.training_date.isoformat(),
            metrics=model.metrics,
        )
        for model in models
    ]


@router.get("/models/active/{model_name}", response_model=ModelInfoResponse)
def get_active_model(
    model_name: str,
    db: Session = Depends(get_db),
):
    """
    Get the currently active model for a given name.

    Args:
        model_name: Name of the model.
        db: Database session.

    Returns:
        Active model information.
    """
    with ModelRegistryManager(db) as registry:
        model = registry.get_active_model(model_name)

    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"No active model found for {model_name}",
        )

    return ModelInfoResponse(
        model_name=model.model_name,
        version=model.version,
        artifact_path=model.artifact_path,
        is_active=model.is_active,
        training_date=model.training_date.isoformat(),
        metrics=model.metrics,
    )


def _build_enriched_data(property_obj: Property, db: Session) -> dict:
    """
    Build enriched data dictionary for ML scoring from property object.

    Args:
        property_obj: Property model instance.
        db: Database session.

    Returns:
        Dictionary with enriched data for ML scorer.
    """
    # Try to get enriched seed data
    enriched_data = {
        "seed_type": property_obj.seed_type.split(",")[0] if property_obj.seed_type else "code_violation",
        "violation_count": 0,
        "property_record": {},
    }

    # Get enriched seed if available
    if property_obj.seed_type:
        primary_seed_type = property_obj.seed_type.split(",")[0]
        enriched_seed = (
            db.query(EnrichedSeed)
            .filter(
                EnrichedSeed.parcel_id_normalized == property_obj.parcel_id_normalized,
                EnrichedSeed.seed_type == primary_seed_type,
            )
            .first()
        )

        if enriched_seed and enriched_seed.enriched_data:
            # Merge enriched seed data
            enriched_data.update(enriched_seed.enriched_data)

    # Add property record data
    if property_obj.property_record:
        enriched_data["property_record"] = {
            "total_mkt": (
                float(property_obj.property_record.total_mkt)
                if property_obj.property_record.total_mkt
                else None
            ),
            "equity_percent": (
                float(property_obj.property_record.equity_percent)
                if property_obj.property_record.equity_percent
                else None
            ),
            "year_built": property_obj.property_record.year_built,
            "taxes": (
                float(property_obj.property_record.taxes)
                if property_obj.property_record.taxes
                else None
            ),
        }

    return enriched_data
