#!/bin/bash
#
# Train ML Models Script
#
# Trains both ARV and lead qualification models with versioning and metrics logging.
# Models are saved with timestamps and symlinks point to the latest versions.
#
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_ROOT/models"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ML Model Training Pipeline${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Timestamp: $TIMESTAMP"
echo "Models directory: $MODELS_DIR"
echo ""

# Ensure models directory exists
mkdir -p "$MODELS_DIR"

# Store metrics
METRICS_FILE="$MODELS_DIR/training_metrics_${TIMESTAMP}.json"
echo "{" > "$METRICS_FILE"
echo "  \"timestamp\": \"$TIMESTAMP\"," >> "$METRICS_FILE"
echo "  \"models\": {" >> "$METRICS_FILE"

# Track success
ARV_SUCCESS=0
LEAD_SUCCESS=0

# 1. Train ARV Model
echo -e "${YELLOW}[1/2] Training ARV model...${NC}"
ARV_OUTPUT="$MODELS_DIR/arv_model_${TIMESTAMP}.joblib"

if $PROJECT_ROOT/.venv/bin/python -m src.wholesaler.ml.training.train_arv_model --output "$ARV_OUTPUT"; then
    echo -e "${GREEN}✓ ARV model trained successfully${NC}"

    # Create symlink to latest
    ln -sf "arv_model_${TIMESTAMP}.joblib" "$MODELS_DIR/arv_model.joblib"
    echo "  Symlink created: arv_model.joblib -> arv_model_${TIMESTAMP}.joblib"

    ARV_SUCCESS=1
    echo "    \"arv\": {" >> "$METRICS_FILE"
    echo "      \"status\": \"success\"," >> "$METRICS_FILE"
    echo "      \"artifact\": \"arv_model_${TIMESTAMP}.joblib\"" >> "$METRICS_FILE"
    echo "    }," >> "$METRICS_FILE"
else
    echo -e "${RED}✗ ARV model training failed${NC}"
    echo "    \"arv\": {" >> "$METRICS_FILE"
    echo "      \"status\": \"failed\"," >> "$METRICS_FILE"
    echo "      \"artifact\": null" >> "$METRICS_FILE"
    echo "    }," >> "$METRICS_FILE"
fi

echo ""

# 2. Train Lead Model
echo -e "${YELLOW}[2/2] Training lead qualification model...${NC}"
LEAD_OUTPUT="$MODELS_DIR/lead_model_${TIMESTAMP}.joblib"

if $PROJECT_ROOT/.venv/bin/python -m src.wholesaler.ml.training.train_lead_model --output "$LEAD_OUTPUT" 2>&1 | tee /tmp/lead_training.log; then
    echo -e "${GREEN}✓ Lead model trained successfully${NC}"

    # Create symlink to latest
    ln -sf "lead_model_${TIMESTAMP}.joblib" "$MODELS_DIR/lead_model.joblib"
    echo "  Symlink created: lead_model.joblib -> lead_model_${TIMESTAMP}.joblib"

    LEAD_SUCCESS=1
    echo "    \"lead\": {" >> "$METRICS_FILE"
    echo "      \"status\": \"success\"," >> "$METRICS_FILE"
    echo "      \"artifact\": \"lead_model_${TIMESTAMP}.joblib\"" >> "$METRICS_FILE"
    echo "    }" >> "$METRICS_FILE"
else
    echo -e "${YELLOW}⚠ Lead model training skipped (check logs for details)${NC}"

    # Check if it failed due to insufficient data
    if grep -q "No Tier A leads" /tmp/lead_training.log; then
        echo "  Reason: Insufficient Tier A examples in dataset"
        echo "  Recommendation: Adjust tier thresholds or collect more high-quality data"
    fi

    echo "    \"lead\": {" >> "$METRICS_FILE"
    echo "      \"status\": \"skipped\"," >> "$METRICS_FILE"
    echo "      \"artifact\": null," >> "$METRICS_FILE"
    echo "      \"reason\": \"insufficient_tier_a_examples\"" >> "$METRICS_FILE"
    echo "    }" >> "$METRICS_FILE"
fi

# Close metrics JSON
echo "  }" >> "$METRICS_FILE"
echo "}" >> "$METRICS_FILE"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Training Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "ARV Model:  $([ $ARV_SUCCESS -eq 1 ] && echo -e "${GREEN}✓ Success${NC}" || echo -e "${RED}✗ Failed${NC}")"
echo "Lead Model: $([ $LEAD_SUCCESS -eq 1 ] && echo -e "${GREEN}✓ Success${NC}" || echo -e "${YELLOW}⚠ Skipped${NC}")"
echo ""
echo "Metrics saved to: $METRICS_FILE"
echo ""

# List all models
echo "Available model artifacts:"
ls -lh "$MODELS_DIR"/*.joblib 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""

# Cleanup old models (keep last 5 versions)
echo "Cleaning up old model versions (keeping last 5)..."
cd "$MODELS_DIR"
ls -t arv_model_*.joblib 2>/dev/null | tail -n +6 | xargs -r rm
ls -t lead_model_*.joblib 2>/dev/null | tail -n +6 | xargs -r rm
echo ""

# Exit with success if at least one model trained
if [ $ARV_SUCCESS -eq 1 ] || [ $LEAD_SUCCESS -eq 1 ]; then
    echo -e "${GREEN}Training pipeline completed successfully!${NC}"
    exit 0
else
    echo -e "${RED}Training pipeline failed - no models were trained${NC}"
    exit 1
fi
