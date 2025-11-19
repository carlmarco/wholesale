# Phase 3.6 → Beyond: Execution Plan

## Overview
With Phase 3.5 delivering a unified seed ingestion → enrichment → scoring pipeline, Phase 3.6 focuses on tightening profitability logic, operationalizing the feature store + ML retraining, and hardening score-serving/monitoring ahead of agent integration.

---

## 1. Profitability Guardrails (docs/profitability package)

| Objective | Implementation | Inclusion Rationale | Success Metrics |
|-----------|----------------|---------------------|------------------|
| Enforce conservative buy-box | - Port `ConservativeProfitabilityBucket` into scoring pipeline<br>- Wire carrying-cost + buyer-margin logic into `run_lead_scoring.py` and API endpoints | Eliminates legacy optimism; ensures agent outreach only pursues $20K+ spread candidates | - 95% reduction in false-positive Tier A leads<br>- ≥85% of recommended leads meet $20K profit test<br>- Snapshot report showing drop from ~55 → ~25 actionable leads (QUICK_REFERENCE targets) |

---

## 2. Feature Store + Training Loop

| Objective | Implementation | Inclusion Rationale | Success Metrics |
|-----------|----------------|---------------------|------------------|
| Materialize ML features | - Use `FeatureStoreBuilder` to export nightly parquet + persist to `ml_feature_store` table via Airflow DAG<br>- Switch to joined fetch (already implemented) to ensure property context is cached | Provides canonical, reproducible feature vectors for DS/ML + agent scoring | - Nightly DAG writes ≥95% of processed seeds to feature store<br>- Feature parity test passes (columns match spec) |
| Automated training | - Create `train_distress_classifier.py` + `train_sale_probability.py` using feature store outputs<br>- Store artifacts + metadata (AUC, precision@k) in `models/` with version tags<br>- Add Airflow `ml_training` DAG (weekly) | Keeps models in sync with latest market data | - Training DAG success rate 100%/week<br>- Baseline ROC-AUC ≥0.75; logged in metadata |
| Online feature access | - Wrap feature extraction via API/CLI helper (e.g., `FeatureStoreClient`) for real-time scoring | Ensures agents/automation use identical features as training | - Latency <200 ms for feature fetch<br>- Cache hit rate >80% when scoring batches |

---

## 3. Hybrid/ML Scoring Integration

| Objective | Implementation | Inclusion Rationale | Success Metrics |
|-----------|----------------|---------------------|------------------|
| Replace legacy-only scoring | - Use `score_property` helper (Phase 3.5) as canonical path<br>- Inject ML probability + expected value into `lead_scores` table (new columns via alembic) | Aligns tiering with ML outputs; supports downstream prioritization | - `lead_scores` rows populated with `ml_probability`, `priority_score` for ≥95% active parcels<br>- Tier A accuracy improves: ≥70% of contacted leads progress to negotiation |
| API/dashboard updates | - Extend `/api/v1/leads` & `/api/v1/leads/{parcel}` responses with ML attributes (already partly visible); ensure Streamlit toggles persist view selection | Gives ops team transparency into ML scores | - Dashboard “Hybrid + Priority” view becomes default; adoption tracked ( >80% usage ) |

---

## 4. Lead Prioritization & Profitability Surfacing

| Objective | Implementation | Inclusion Rationale | Success Metrics |
|-----------|----------------|---------------------|------------------|
| Priority queue | - Update `PriorityLeadService` to factor conservative profit score + ML probability<br>- Expose `/api/v1/leads/priority` + dashboard toggle | Ensures agents focus on best ROIs | - 90th percentile priority score corresponds to ≥$35K projected profit |
| Profitability audit trail | - Persist profitability calculations per parcel (JSON column) for review; add CLI/Streamlit drill-down | Supports underwriting + compliance | - 100% of Tier A leads have downloadable profitability report |

---

## 5. Monitoring & Data Quality

| Objective | Implementation | Inclusion Rationale | Success Metrics |
|-----------|----------------|---------------------|------------------|
| Airflow/DAG observability | - Add DAG-level metrics (success counts, processed rows) to logging/Prometheus<br>- Implement SLA alerts for ingestion/scoring DAGs | Early detection of pipeline regressions | - SLA breaches <2% per month |
| Data-quality extensions | - Expand `data_quality_checks` DAG to validate feature store completeness, ML score coverage, and profitability report freshness | Keeps ML + scoring aligned with new logic | - Check DAG passes 100% nightly; alerts triggered if coverage <95% |

---

## Execution Timeline (High-Level)

1. **Week 1** – Integrate conservative profitability scorer into scoring pipeline + API, run regression tests, update documentation.
2. **Week 2** – Wire feature store DAG + nightly export, finish alembic migration for new scoring columns, update dashboard views.
3. **Week 3** – Implement training scripts + Airflow ML DAG, log metrics, finalize monitoring hooks.
4. **Week 4** – Roll out priority-lead API/UI enhancements, run end-to-end validation (profitability reports, ML adoption), hand off to agent-integration team.

---
_This plan assumes Phase 3.5 architecture (unified ingestion + hybrid scoring) is stable; adjust sequencing if any prerequisite work resurfaces._
