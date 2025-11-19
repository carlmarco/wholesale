# Copilot Instructions for Wholesaler Codebase

This document guides AI agents to be immediately productive in the real estate wholesaler system.

## Architecture Overview

**Purpose**: Automated real estate lead identification, scoring, and outreach system for Orlando, FL.

**Data Flow**:
1. **Ingestion**: Four scrapers collect raw seed data (tax sales, foreclosures, code violations, property records)
2. **Enrichment**: Normalize addresses, transform coordinates, compute violation proximity metrics
3. **Deduplication**: Merge by normalized parcel ID, dedupe across sources
4. **Scoring**: Weighted bucket scoring (distress 65%, disposition 20%, equity 15%) produces A/B/C/D tiers
5. **Database**: PostgreSQL persists deduplicated, scored properties
6. **API**: FastAPI serves leads to frontend and third-party systems
7. **UI**: Streamlit multi-page dashboard for visualization and deal analysis

## Directory Structure & Responsibilities

```
src/wholesaler/
├── ingestion/              → Collect raw seed records from multiple sources
├── enrichment/             → Add violation metrics, property context, geo data (NEW - Nov 2025)
├── scoring/                → Lead ranking algorithms (HybridBucketScorer, LogisticOpportunityScorer)
├── scrapers/               → API clients for tax sales, foreclosures, violations, properties
├── transformers/           → Address standardization, coordinate transformation
├── enrichers/              → Specialized enrichment (geo proximity, violation metrics)
├── pipelines/              → Data transformation (PropertyDeduplicator only, reduced scope)
├── etl/                    → Database loaders (EnrichedSeedLoader, PropertyLoader)
├── db/                     → SQLAlchemy ORM models, session management, repository pattern
├── api/                    → FastAPI routers, schemas, dependencies (auth, leads, properties, stats)
├── frontend/               → Streamlit multi-page dashboard (app.py + pages/ + components/)
├── services/               → Business logic (PriorityLeadService)
├── models/                 → Pydantic data models (not DB models)
├── ml/                     → ML model training and inference (ARV, lead qualification)
├── monitoring/             → Data quality checks
└── utils/                  → Shared utilities (logger, geo_utils, adapters)
```

**Critical**: As of Nov 2025, the codebase underwent major reorganization. See `FINAL_ARCHITECTURE.md` for migration details.

## Key Patterns & Conventions

### 1. Pydantic Models for All Data Contracts

**Location**: `src/wholesaler/models/`, `src/wholesaler/ingestion/seed_models.py`, API schemas

**Pattern**: Use type-safe `@dataclass` or Pydantic models for all domain objects.

```python
# Example: SeedRecord from ingestion
from src.wholesaler.ingestion.seed_models import SeedRecord

seed = SeedRecord(
    parcel_id="123456789012345",
    seed_type="tax_sale",
    source_payload={...},
    ingested_at=datetime.now()
)
```

**Why**: Prevents silent data inconsistencies; enables IDE autocomplete; validates at boundaries.

### 2. Structured Logging Throughout

**Location**: `src/wholesaler/utils/logger.py`

**Pattern**: Use `get_logger(__name__)` and log events with structured context.

```python
from src.wholesaler.utils.logger import get_logger
logger = get_logger(__name__)

logger.info("tax_sale_seeds_collected", count=len(seeds), time_ms=elapsed)
logger.warning("code_violation_fetch_empty")  # No traceback needed
logger.error("database_connection_failed", error=str(e), retrying=True)
```

**Why**: Enables event-based alerting; automatic context merging (environment, timestamp); easier querying in logs.

### 3. Repository Pattern for Database Access

**Location**: `src/wholesaler/db/repository.py`

**Pattern**: Use `Repository[Model]` generic class for all DB queries (never raw SQL).

```python
from src.wholesaler.db.repository import Repository
from src.wholesaler.db.models import Property

repo = Repository[Property](session)
properties = repo.find_by_query({"tier": "A"}, limit=50)
high_equity = repo.find_by_query({"equity_percent": {"$gt": 200}})
```

**Why**: Decouples API layer from schema changes; enables caching; consistent error handling.

### 4. Dependency Injection via FastAPI `Depends()`

**Location**: `src/wholesaler/api/main.py`, `src/wholesaler/api/routers/`

**Pattern**: Request database sessions, configuration, services via `Depends()`.

```python
from fastapi import FastAPI, Depends
from src.wholesaler.api.dependencies import get_db
from sqlalchemy.orm import Session

@router.get("/leads/")
def list_leads(tier: str = "A", db: Session = Depends(get_db)):
    repo = Repository[LeadScore](db)
    return repo.find_by_query({"tier": tier})
```

**Why**: Enables easy testing (mock dependencies); automatic session lifecycle management; configuration injection.

### 5. Dual-Seed Ingestion Model

**Location**: `src/wholesaler/ingestion/pipeline.py`, `dags/`

**Pattern**: Collect "tax sale" seeds (from tax sales + property records) and "distress" seeds (foreclosures + violations) separately, then merge.

```python
pipeline = IngestionPipeline()
tax_seeds = pipeline.collect_tax_sale_seeds()           # High-equity, active auctions
distress_seeds = pipeline.collect_foreclosure_seeds()   # Financial distress
violation_seeds = pipeline.collect_code_violation_seeds() # Maintenance issues

# Later unified in enrichment pipeline
enriched = UnifiedEnrichmentPipeline().run(tax_seeds + distress_seeds)
```

**Why**: Avoids gating all leads on tax sale status; violations alone can create viable leads; better segment-specific messaging.

### 6. Weighted Bucket Scoring (Not Legacy Tiers)

**Location**: `src/wholesaler/scoring/scorers.py`

**Pattern**: Use `HybridBucketScorer` for new scoring (legacy `LeadScorer` deprecated).

```python
from src.wholesaler.scoring import HybridBucketScorer

scorer = HybridBucketScorer()
result = scorer.score(enriched_record)  # Returns {total_score, tier, bucket_scores}

# Weights: distress=0.65, disposition=0.20, equity=0.15
# Bonus: +15 if tax_sale, +10 if foreclosure
```

**Why**: Violations alone create Tier B leads (distress ≥65 points); disposition/equity are boosters, not gatekeepers.

### 7. Normalized Parcel IDs as Primary Key

**Location**: `src/wholesaler/transformers/address_standardizer.py`, all DB models

**Pattern**: Always normalize parcel IDs to digits-only format; use as foreign key across tables.

```python
from src.wholesaler.transformers.address_standardizer import AddressStandardizer

standardizer = AddressStandardizer()
normalized = standardizer.normalize_parcel_id("123-456-789-012-345")  # → "123456789012345"

# Database uses parcel_id_normalized as primary key
# property.parcel_id_normalized → tax_sales.parcel_id_normalized
```

**Why**: Deduplication across sources; consistent joins; handles formatting variants.

### 8. Geographic Enrichment via Haversine Distance

**Location**: `src/wholesaler/enrichers/geo_enricher.py`

**Pattern**: Compute proximity to code violations using Haversine formula; include in enrichment.

```python
from src.wholesaler.enrichers.geo_enricher import GeoPropertyEnricher

enricher = GeoPropertyEnricher(
    code_enforcement_csv_path="data/code_enforcement_data.csv",
    radius_miles=0.5
)
metrics = enricher.enrich_properties(tax_properties)
# Returns: nearby_violations, nearby_open_violations, violation_distance_miles, etc.
```

**Why**: Identifies properties with documented maintenance issues; strong distress signal.

### 9. Async Task Queue for Airflow DAGs

**Location**: `dags/`, `src/wholesaler/etl/loaders.py`

**Pattern**: DAGs orchestrate Python functions; functions use database repository for persistence.

```python
from airflow import DAG
from src.wholesaler.ingestion.pipeline import IngestionPipeline
from src.wholesaler.enrichment.pipeline import UnifiedEnrichmentPipeline
from src.wholesaler.etl.loaders import EnrichedSeedLoader

def dag_task_enrich_and_load(**context):
    seeds = IngestionPipeline().collect_all_seeds()
    enriched = UnifiedEnrichmentPipeline().run(seeds)
    EnrichedSeedLoader().load_enriched_seeds(enriched)
```

**Why**: Airflow handles scheduling/retry; Python handles data logic; decoupled from scheduler complexity.

### 10. Environment Variables via Pydantic Settings

**Location**: `config/settings.py`, `.env`

**Pattern**: All configuration centralized in `Settings` class; loaded from `.env`.

```python
from config.settings import settings

# Use anywhere in code
api_key = settings.socrata_api_key
db_url = settings.database_url
log_level = settings.log_level

# Not: os.environ["SOCRATA_API_KEY"]  ← Never do this
```

**Why**: Type-safe; runtime validation; easy to swap environments; no secrets in code.

## Critical Workflows

### Adding a New Data Source

1. **Create scraper** in `src/wholesaler/scrapers/new_source_scraper.py` inheriting from base class
2. **Add to ingestion** in `src/wholesaler/ingestion/pipeline.py` (new `collect_*_seeds()` method)
3. **Define enrichment** in `src/wholesaler/enrichment/` (if needs custom logic)
4. **Add to DAG** in `dags/daily_property_ingestion.py` calling new scraper
5. **Test** in `tests/wholesaler/scrapers/test_new_source_scraper.py` (mock API responses)

### Adding a New Scoring Signal

1. **Compute in enrichment** (e.g., proximity to violations, tax burden) → add to enriched record
2. **Add bucket weight** in `src/wholesaler/scoring/scorers.py` → update `HybridBucketScorer._bucket_scores()`
3. **Test** in `tests/wholesaler/scoring/test_scorers.py` with known records
4. **Validate** tiers via `make data-quality` (check tier distribution)

### Adding an API Endpoint

1. **Define Pydantic schema** in `src/wholesaler/api/schemas.py`
2. **Create router** in `src/wholesaler/api/routers/new_feature.py`
3. **Inject in main.py**: `app.include_router(new_feature.router)`
4. **Test** in `tests/wholesaler/api/` using `TestClient`

### Debugging Data Quality Issues

```bash
# Check lead counts by tier
make stats

# Generate detailed report
make data-quality

# Inspect database directly
make db-shell
SELECT * FROM lead_scores WHERE tier = 'A' LIMIT 5;

# Check logs for pipeline errors
make logs-airflow
```

## Testing Conventions

**Location**: `tests/wholesaler/` (mirrors `src/wholesaler/` structure)

**Markers**:
- `@pytest.mark.unit` - Fast, no I/O
- `@pytest.mark.integration` - Requires services (DB, API)
- `@pytest.mark.slow` - Skipped in CI

**Example**:
```python
# tests/wholesaler/scoring/test_scorers.py
import pytest
from src.wholesaler.scoring import HybridBucketScorer

@pytest.mark.unit
def test_hybrid_bucket_scorer_tier_a():
    scorer = HybridBucketScorer()
    record = {
        "violation_count": 8,  # Distress = 80
        "open_violations": 2,  # +24
        "most_recent_violation": "2025-11-01",  # +25
        "market_value": 150000,
        "tax_sale": True,  # +15 bonus
    }
    result = scorer.score(record)
    assert result["tier"] == "A"
    assert result["total_score"] >= 75
```

**Run tests**:
```bash
make test           # All tests
make test-cov       # With coverage
pytest tests/wholesaler/scoring/ -v -m unit  # Specific subset
```

## Making Changes Safely

1. **Read FINAL_ARCHITECTURE.md** - Understand module roles and migration status
2. **Prefer new modules** - Use `enrichment/`, `scoring/`, not deprecated `pipelines/`
3. **Update imports** - Old paths like `from src.wholesaler.pipelines.scoring import` → deprecated, use `from src.wholesaler.scoring import`
4. **Test first** - Run `make test` before committing
5. **Check logs** - Use structured logging, not print statements
6. **Database migrations** - Create Alembic migration for schema changes: `make db-migrate "add_field_to_properties"`

## External Dependencies & Integration Points

| Component | Tool | Location |
|-----------|------|----------|
| **Configuration** | Pydantic Settings | `config/settings.py` |
| **Database** | PostgreSQL + SQLAlchemy | `docker-compose.yml`, `src/wholesaler/db/` |
| **Orchestration** | Apache Airflow | `dags/`, `docker-compose.yml` |
| **Cache** | Redis | `docker-compose.yml`, `src/wholesaler/api/cache.py` |
| **Web Framework** | FastAPI | `src/wholesaler/api/main.py` |
| **Dashboard** | Streamlit | `src/wholesaler/frontend/app.py` |
| **Task Queue** | Celery (future) | Not yet implemented |
| **ML Models** | scikit-learn + joblib | `models/`, `src/wholesaler/ml/` |

## Known Limitations & Future Work

- `src/data_ingestion/` module deprecated (PropertyEnricher still used temporarily)
- No async scrapers yet (performance OK for current volume)
- Skip-trace API not yet implemented (Phase 4C)
- Multi-market expansion planned but not active (Phase 4G)
- No real-time model retraining (batch weekly)

## When in Doubt

1. **Check FINAL_ARCHITECTURE.md** - Most questions answered there
2. **Read examples** - Scrapers, enrichers, scorers all follow same pattern
3. **Run tests** - `make test` validates your changes
4. **Check logs** - Structured logging shows exactly what happened
5. **Ask via README** - If pattern not documented, it's not discoverable → needs documentation

---

**Last Updated**: 2025-11-15  
**Current Phase**: Phase 3.5 (Ingestion/Enrichment pipeline refinement)  
**Branch**: phase-3.5-ingestion-fixing
