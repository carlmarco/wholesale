# Seed Pipeline Validation Checklist

**Before migrating to hybrid seed ingestion, follow this checklist to ensure no regression.**

## Current Status

✅ **Code Complete**: All seed-based components implemented and tested
- Database schema ([alembic migration](alembic/versions/5945bc7854d8_add_seed_support.py))
- EnrichedSeedLoader, SeedMerger, Seed-aware LeadScorer
- Airflow DAG for orchestration
- 20/20 unit tests passing

⚠️ **Integration Pending**: Full pipeline not yet run end-to-end

---

## Pre-Migration Validation Steps

### Phase 1: Environment Setup ✅ (Ready)

**Start Services:**
```bash
# Start database and all services
make start

# Verify services running
docker ps

# Expected: postgres, airflow-webserver, airflow-scheduler, api, dashboard
```

**Apply Database Migration:**
```bash
# Apply seed support schema
alembic upgrade head

# Verify migration applied
alembic current
# Should show: 5945bc7854d8 (add_seed_support)
```

---

### Phase 2: Legacy Baseline (Establish Ground Truth)

**Purpose:** Capture current system state before introducing seeds

**Run Legacy Pipeline:**
```bash
# Full legacy ingestion
make pipeline-full

# Or step-by-step:
make scrape-data      # Tax sales + foreclosures
make score-leads      # Score all properties
```

**Capture Baseline Metrics:**
```bash
# Run validation
python scripts/validate_seed_pipeline.py --check legacy

# Expected output:
# ✓ Properties: XXX
# ✓ Tax Sales: XXX
# ✓ Foreclosures: XXX
# ✓ Lead Scores: XXX
```

**Document Baseline:**
- Total properties: __________
- Tax sales: __________
- Foreclosures: __________
- Lead scores: __________
- Tier A leads: __________
- Tier B leads: __________
- Tier C leads: __________

**API Snapshot:**
```bash
# Capture current state
curl http://localhost:8000/api/v1/stats/dashboard > baseline_stats.json
curl "http://localhost:8000/api/v1/leads?tier=A&limit=10" > baseline_tier_a.json
```

---

### Phase 3: Seed Collection (New Pipeline)

**Run Seed Ingestion:**
```bash
# Collect seeds from all sources
make ingest-seeds

# Expected: Creates data/processed/seeds.json
```

**Validate Seed Output:**
```bash
# Check seed file
python scripts/validate_seed_pipeline.py --check seeds

# Expected output:
# ✓ Total seeds: XXX
#   - tax_sale: XXX
#   - code_violation: XXX
#   - foreclosure: XXX
```

**Manual Inspection:**
```bash
# View sample seeds
head -20 data/processed/seeds.json | jq .

# Verify:
# - Each seed has parcel_id
# - Each seed has seed_type
# - Coordinates present (if available)
```

**Quality Checks:**
- [ ] Seed count reasonable (not 0, not suspiciously low)
- [ ] All 3 seed types present (tax_sale, code_violation, foreclosure)
- [ ] Parcel IDs look valid (format matches)
- [ ] No obvious data corruption

---

### Phase 4: Enrichment

**Run Enrichment Pipeline:**
```bash
# Enrich all seeds
make enrich-seeds

# Expected: Creates data/processed/enriched_seeds.parquet
```

**Validate Enrichment:**
```bash
# Check enrichment output
python scripts/validate_seed_pipeline.py --check enrichment

# Expected output:
# ✓ Total enriched seeds: XXX
#   - tax_sale: XXX
#   - code_violation: XXX
#   - foreclosure: XXX
# ✓ With coordinates: XXX (XX%)
# ✓ With violations: XXX (XX%)
```

**Manual Inspection:**
```python
# In Python/Jupyter
import pandas as pd
df = pd.read_parquet('data/processed/enriched_seeds.parquet')

# Check sample
print(df.head())

# Verify columns
print(df.columns.tolist())
# Should include: parcel_id, seed_type, latitude, longitude, violation_count, etc.

# Check enrichment rates
print(f"Has parcel_id: {df['parcel_id'].notna().mean():.1%}")
print(f"Has coordinates: {(df['latitude'].notna() & df['longitude'].notna()).mean():.1%}")
print(f"Has violations: {df['violation_count'].notna().mean():.1%}")
```

**Quality Thresholds:**
- [ ] ≥70% parcel ID coverage (match rate)
- [ ] ≥50% coordinate coverage
- [ ] ≥30% violation coverage (for code_violation seeds should be >80%)

---

### Phase 5: Database Integration

**Load Enriched Seeds:**
```bash
# Load seeds into enriched_seeds staging table
python -c "
from src.wholesaler.db import get_db_session
from src.wholesaler.etl.loaders import EnrichedSeedLoader

with get_db_session() as session:
    loader = EnrichedSeedLoader()
    stats = loader.load_from_parquet(
        session,
        'data/processed/enriched_seeds.parquet',
        track_run=True
    )
    print(f'Loaded: {stats}')
"
```

**Validate Database Load:**
```bash
# Check database state
python scripts/validate_seed_pipeline.py --check database

# Expected output:
# ✓ enriched_seeds table exists: True
# ✓ properties.seed_type column exists: True
# ✓ Enriched seeds in DB: XXX
# ✓ Processed seeds: 0 (not yet merged)
```

**Merge Seeds to Properties:**
```bash
# Merge enriched_seeds into properties table
python -c "
from src.wholesaler.db import get_db_session
from src.wholesaler.etl.seed_merger import SeedMerger

with get_db_session() as session:
    merger = SeedMerger()
    stats = merger.merge_seeds(session, track_run=True)
    print(f'Merged: {stats}')
"
```

**Validate Merge:**
```bash
# Check database state after merge
python scripts/validate_seed_pipeline.py --check database

# Expected output:
# ✓ Enriched seeds in DB: XXX
# ✓ Processed seeds: XXX (should equal total seeds)
```

**SQL Verification:**
```sql
-- Check seed-based properties
SELECT seed_type, COUNT(*)
FROM properties
WHERE seed_type IS NOT NULL
GROUP BY seed_type;

-- Check for multi-source properties
SELECT seed_type, COUNT(*)
FROM properties
WHERE seed_type LIKE '%,%'
GROUP BY seed_type;
```

---

### Phase 6: Lead Scoring (Critical Integration Point)

**Re-Score All Leads:**
```bash
# Run scoring with seed awareness
python scripts/run_lead_scoring.py
```

**Validate Scoring:**
```bash
# Check scoring integration
python scripts/validate_seed_pipeline.py --check scoring

# Expected output:
# ✓ Seed-based properties: XXX
# ✓ Total lead scores: XXX
# ✓ Tier distribution:
#   - Tier A: XXX
#   - Tier B: XXX
#   - Tier C: XXX
#   - Tier D: XXX
```

**Compare to Baseline:**
```bash
# New stats
curl http://localhost:8000/api/v1/stats/dashboard > new_stats.json

# Compare
diff baseline_stats.json new_stats.json

# Verify:
# - Total properties increased (new seeds)
# - Tier A count reasonable (not 0, not 100%)
# - No dramatic drop in lead quality
```

**Quality Checks:**
- [ ] Seed-based properties > 0
- [ ] Seed-based scoring: __________ properties
- [ ] Legacy scoring: __________ properties
- [ ] Tier A leads increased or stable
- [ ] No properties scored as Tier D that were Tier A before

---

### Phase 7: Dashboard & API Verification

**Test API Endpoints:**
```bash
# Get dashboard stats
curl http://localhost:8000/api/v1/stats/dashboard | jq .

# Get Tier A leads (should include seed-based)
curl "http://localhost:8000/api/v1/leads?tier=A&limit=10" | jq .

# Filter by seed type (new functionality)
# TODO: Add this endpoint in Phase 5
```

**Test Dashboard:**
```bash
# Start dashboard
make dashboard

# Visit: http://localhost:8501
```

**Visual Checks:**
- [ ] Lead counts match database
- [ ] Map shows properties (coordinates from seeds)
- [ ] Tier distribution chart shows reasonable split
- [ ] Recent leads include seed-based properties

---

### Phase 8: Data Quality Metrics

**Run Data Quality Report:**
```bash
# Compute quality metrics
make data-quality

# Or:
python scripts/data_quality_report.py
```

**Review Metrics:**
- [ ] Seed collection rate by source
- [ ] Parcel match rate (seeds → parcel_id)
- [ ] Enrichment success rate
- [ ] Coordinate coverage
- [ ] Violation coverage

**Acceptable Thresholds:**
- Match rate: ≥70% (seeds with valid parcel_id)
- Enrichment success: ≥80% (seeds with property records)
- Coordinate coverage: ≥50%
- Violation coverage: ≥30% (overall), ≥80% (code_violation seeds)

---

### Phase 9: Regression Testing

**Run Full Test Suite:**
```bash
# Unit tests
PYTHONPATH=. .venv/bin/pytest tests/wholesaler/etl/test_seed_merger_unit.py \
                                 tests/wholesaler/pipelines/test_seed_based_scoring.py \
                                 -v

# All tests
make test
```

**Integration Test (Manual):**
```bash
# End-to-end: Seed → Score → API
1. Clear data:
   rm data/processed/seeds.json data/processed/enriched_seeds.parquet
   psql -d wholesaler -c "TRUNCATE enriched_seeds CASCADE;"

2. Run pipeline:
   make ingest-seeds
   make enrich-seeds
   python -c "<loader code from Phase 5>"
   python -c "<merger code from Phase 5>"
   python scripts/run_lead_scoring.py

3. Verify API:
   curl http://localhost:8000/api/v1/leads?tier=A | jq '.results | length'
   # Should show leads
```

---

### Phase 10: Parallel Operation Test

**Run Both Pipelines:**
```bash
# Legacy pipeline
make pipeline-full

# New seed pipeline (DAG)
# Trigger in Airflow UI: seed_based_ingestion DAG
```

**Verify No Conflicts:**
- [ ] Both pipelines complete successfully
- [ ] No database deadlocks
- [ ] No duplicate properties
- [ ] Lead counts additive (not conflicting)

---

## Migration Decision Criteria

### ✅ Ready to Migrate If:

1. **All validation checks pass** (validation script shows 🟢)
2. **Data quality meets thresholds:**
   - Match rate ≥70%
   - Enrichment success ≥80%
   - Coordinate coverage ≥50%
3. **No regression in lead quality:**
   - Tier A count stable or increased
   - No loss of tax sale coverage
4. **Tests passing:**
   - 20/20 unit tests ✅
   - Integration tests pass
5. **Dashboard functional:**
   - Shows all leads correctly
   - Maps render
   - Filters work

### ⚠️ Migration Risks (Review First):

- Match rate <70%: Many seeds lack parcel IDs
- Tier A leads decreased: Scoring may need tuning
- Coordinate coverage <30%: Maps will be sparse
- Database errors: Schema issues or conflicts

### 🔴 DO NOT Migrate If:

- Any validation check fails
- Database cannot connect
- Match rate <50%
- Scoring produces nonsensical results (all Tier D or all Tier A)
- Legacy pipeline broken (can't roll back)

---

## Post-Migration Monitoring

**After migration, monitor for 1 week:**

1. **Daily Metrics:**
   - Lead count (should increase as code violations flow in)
   - Tier distribution (should remain stable)
   - API response times (should not degrade)

2. **Weekly Review:**
   - Data quality metrics
   - User feedback (if applicable)
   - Airflow DAG success rate

3. **Rollback Plan:**
   - Keep legacy DAGs disabled but available
   - Document rollback procedure:
     ```bash
     # Disable seed DAG
     # Re-enable legacy DAGs
     # Truncate enriched_seeds table
     # Remove seed_type from properties
     ```

---

## Next Steps

1. **Start services:** `make start`
2. **Run validation:** `python scripts/validate_seed_pipeline.py --check all`
3. **Follow phases 2-10** as outlined above
4. **Document results** in each phase checkbox
5. **Make go/no-go decision** based on criteria

---

**Validation Script Location:** `scripts/validate_seed_pipeline.py`
**Results Location:** `data/validation_results.json`
**Test Coverage:** 20/20 tests passing (100%)
**Documentation:** This file + [Architecture Docs](docs/)
