# ML Model Training Guide

## Overview

This guide documents the complete ML training infrastructure for the Wholesaler Lead Management System, including data preparation, model training, and deployment workflows.

## Current Status

### Dataset Summary
- **Total Properties**: 186
- **Property Records** (with market values): 100
- **Tax Sales**: 86
- **Foreclosures**: 100

### Lead Tier Distribution
| Tier | Count | Percentage | Avg Score | Score Range |
|------|-------|------------|-----------|-------------|
| A    | 13    | 7.0%       | 45.00     | 45.00       |
| B    | 29    | 15.6%      | 40.76     | 36-42       |
| C    | 134   | 72.0%      | 30.94     | 30-33       |
| D    | 10    | 5.4%       | 24.00     | 24.00       |

**Total**: 186 leads scored

### Trained Models

#### ARV Model ✓
- **Type**: Random Forest Regressor
- **Status**: Successfully trained
- **Metrics**:
  - R² Score: 0.073
  - MAE: $76,188
  - Training samples: 93 properties
  - Features: 50
- **Artifact**: `models/arv_model.joblib`

#### Lead Qualification Model ✓
- **Type**: XGBoost Classifier (binary)
- **Status**: Successfully trained
- **Metrics**:
  - ROC-AUC: 0.80
  - PR-AUC: 0.51
  - Training samples: 186 leads (13 Tier A, 173 not Tier A)
  - Class balance: 7.0% Tier A
  - Features: 7
- **Artifact**: `models/lead_model.joblib`

## Training Workflow

### Automated Training Script

Use the automated training script for production workflows:

```bash
./scripts/train_models.sh
```

This script:
1. Trains both ARV and lead models with versioning
2. Creates timestamped model artifacts
3. Updates symlinks to latest versions
4. Logs comprehensive metrics
5. Handles failures gracefully
6. Cleans up old model versions (keeps last 5)

### Manual Training

#### Train ARV Model
```bash
.venv/bin/python -m src.wholesaler.ml.training.train_arv_model \
  --output models/arv_model.joblib \
  --min-market-value 50000 \
  --max-market-value 800000
```

#### Train Lead Model
```bash
.venv/bin/python -m src.wholesaler.ml.training.train_lead_model \
  --output models/lead_model.joblib \
  --recent-days 90
```

## Data Diagnostics

Both training scripts now include comprehensive diagnostics:

### ARV Model Diagnostics
```python
{
  "total_rows": 93,
  "min_value": 167300.00,
  "max_value": 778380.00,
  "median_value": 331710.00,
  "null_count": 1488,
  "total_features": 50,
  "numeric_features": 50
}
```

### Lead Model Diagnostics
```python
{
  "total_rows": 186,
  "tier_a_count": 13,
  "not_tier_a_count": 173,
  "positive_rate": 0.0699,
  "class_balance": "7.0%",
  "null_count": 4696,
  "total_features": 7,
  "numeric_features": 7
}
```

## Tier Threshold Configuration

Lead scoring thresholds can be adjusted in `src/wholesaler/pipelines/lead_scoring.py`:

```python
# Current optimized thresholds
TIER_A_THRESHOLD = 43  # Hot leads (top ~7%)
TIER_B_THRESHOLD = 35  # Good leads (~15%)
TIER_C_THRESHOLD = 28  # Moderate leads (~72%)
# Below 28 = Tier D (~5%)
```

### Adjusting Thresholds

To produce more Tier A leads:
1. Lower `TIER_A_THRESHOLD` (e.g., from 43 to 40)
2. Re-run lead scoring: `.venv/bin/python scripts/run_lead_scoring.py`
3. Verify distribution: `docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler -c "SELECT tier, COUNT(*) FROM lead_scores GROUP BY tier;"`
4. Re-train lead model: `./scripts/train_models.sh`

## ML Fallback Logic

The system uses a **two-tier prediction strategy**:

### 1. ARV Estimation
```python
# Primary: ML model prediction
arv_result = estimate_arv(features)
if arv_result["prediction_method"] == "ml_model":
    # Using trained Random Forest model
    pass
else:
    # Fallback to heuristic-based estimation
    pass
```

### 2. Lead Qualification
```python
# Primary: XGBoost classifier prediction
ml_probability = predict_lead_probability(features)
if ml_probability is not None:
    # Blend ML prediction with heuristic score
    adjusted_score = heuristic_score + (ml_probability - 0.5) * 40
else:
    # Use heuristic score only
    adjusted_score = heuristic_score
```

### Logging
- **ML model used**: `logger.debug("arv_prediction_using_ml_model")`
- **Fallback mode**: `logger.info("arv_prediction_fallback_to_heuristic", reason="ml_model_unavailable")`

## Model Versioning

Models are versioned with timestamps and symlinks:

```
models/
├── arv_model.joblib           → arv_model_20251107_141806.joblib
├── lead_model.joblib          → lead_model_20251107_141806.joblib
├── arv_model_20251107_141806.joblib    (1.3 MB)
├── lead_model_20251107_141806.joblib   (327 KB)
└── training_metrics_20251107_141806.json
```

### Metrics File Format
```json
{
  "timestamp": "20251107_141806",
  "models": {
    "arv": {
      "status": "success",
      "artifact": "arv_model_20251107_141806.joblib"
    },
    "lead": {
      "status": "success",
      "artifact": "lead_model_20251107_141806.joblib"
    }
  }
}
```

## Common Issues & Solutions

### Issue: "No Tier A leads available for training"

**Cause**: Dataset has 0 Tier A examples

**Solutions**:
1. Lower tier thresholds (recommended):
   ```python
   TIER_A_THRESHOLD = 40  # From 43
   ```

2. Download more data:
   ```bash
   # Edit scripts/download_complete_data.py
   # Change limit=100 to limit=500
   .venv/bin/python scripts/download_complete_data.py
   .venv/bin/python scripts/load_complete_data.py
   .venv/bin/python scripts/run_lead_scoring.py
   ```

3. Backfill synthetic labels (for testing):
   ```sql
   UPDATE lead_scores
   SET tier = 'A'
   WHERE total_score >= (
     SELECT PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY total_score)
     FROM lead_scores
   );
   ```

### Issue: XGBoost base_score error

**Cause**: Class imbalance with default base_score

**Solution**: Already fixed in `train_lead_model.py`:
```python
positive_rate = np.clip(positive_count / len(target), 0.001, 0.999)
model = XGBClassifier(base_score=positive_rate, ...)
```

### Issue: Low ARV model R² score (0.073)

**Cause**: Limited training data (93 samples), high variance in property values

**Solutions**:
1. Collect more property records with market values
2. Add more features (property age, living area, lot size, etc.)
3. Use ensemble methods or feature engineering
4. Accept lower R² for MVP and improve iteratively

**Note**: Model is still functional for relative comparisons and the 70% rule calculations

## Best Practices

### 1. Regular Retraining
- Retrain models monthly or when new data reaches 20% of current dataset
- Use automated training script for consistency
- Monitor metrics for drift

### 2. Model Validation
```bash
# Check model artifacts exist
ls -lh models/*.joblib

# Verify metrics logged
cat models/training_metrics_*.json | jq .

# Test predictions
.venv/bin/python -c "
from src.wholesaler.ml.models import PropertyFeatures, estimate_arv
features = PropertyFeatures(parcel_id='TEST', city='Orlando', total_score=45)
result = estimate_arv(features)
print(f'Method: {result[\"prediction_method\"]}')
print(f'ARV: ${result[\"estimated_arv\"]:,.0f}')
"
```

### 3. A/B Testing
- Keep previous model version for comparison
- Log which model version produced each prediction
- Monitor business metrics (conversion rate, ROI) per model

### 4. Data Quality Checks
Before training:
```bash
# Check data completeness
docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler -c "
SELECT
  COUNT(*) as total_properties,
  SUM(CASE WHEN total_mkt IS NOT NULL THEN 1 ELSE 0 END) as with_market_value,
  SUM(CASE WHEN equity_percent IS NOT NULL THEN 1 ELSE 0 END) as with_equity
FROM property_records;
"
```

## API Integration

Models are automatically loaded by the API at startup:

```python
# In src/wholesaler/ml/models.py
@lru_cache()
def _load_arv_model():
    return _load_artifact(settings.arv_model_filename)

@lru_cache()
def _load_lead_model():
    return _load_artifact(settings.lead_model_filename)
```

Cache is cleared on application restart. To force reload:
```bash
# Restart FastAPI
# Models will be reloaded from disk
```

## Monitoring & Alerting

### Recommended Metrics to Track
1. **Model Performance**:
   - ARV MAE trend over time
   - Lead model AUC trend
   - Prediction confidence scores

2. **Data Quality**:
   - % of properties with complete features
   - Tier distribution stability
   - Null value counts

3. **Business Metrics**:
   - Conversion rate by tier
   - Actual vs predicted ARV accuracy
   - ROI on properties acquired using model predictions

### Logging Best Practices
```python
# All model predictions logged with:
logger.debug("arv_prediction_using_ml_model",
             parcel_id=...,
             prediction=...,
             confidence=...)

# Aggregate logs for monitoring:
# grep "arv_prediction" logs/*.log | jq -s 'group_by(.prediction_method) | map({method: .[0].prediction_method, count: length})'
```

## Next Steps

1. **Collect More Data**: Target 500+ properties for robust training
2. **Feature Engineering**: Add property age, neighborhood stats, market trends
3. **Hyperparameter Tuning**: Grid search for optimal model parameters
4. **Model Ensembling**: Combine multiple models for better predictions
5. **Real-time Retraining**: Airflow DAGs for automated weekly retraining
6. **Prediction Explainability**: SHAP values for model interpretability

## References

- Training scripts: `src/wholesaler/ml/training/`
- Feature builder: `src/wholesaler/ml/training/feature_builder.py`
- Model predictions: `src/wholesaler/ml/models.py`
- Lead scoring: `src/wholesaler/pipelines/lead_scoring.py`
