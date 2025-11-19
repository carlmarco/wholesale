# Real Estate Wholesaler - Automated Property Analysis System

Production-grade automated real estate wholesaling system for identifying undervalued investment opportunities in Orlando, FL using public data sources and distress signal analysis.

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd wholesaler
make setup

# Launch the dashboard
make dashboard
```

Dashboard will be available at **http://localhost:8501**

For all available commands, run `make help`

> **Note:** The Streamlit dashboard reads the FastAPI endpoint from the `API_BASE_URL` environment variable.  
> - Local development defaults to `http://localhost:8000`.  
> - Inside Docker (compose), it should be set to `http://api:8000` so the container can reach the API service.

## Project Goal

Identify profitable wholesale opportunities where:
```
ARV * 0.7 - repair_costs - acquisition_cost > $15,000 profit
```

## Current Status

**Phase 3.6: COMPLETE** - Profitability Validation & ML Infrastructure

### Phase 1-3.5 Completed Features
- Multi-source seed ingestion (tax sales, foreclosures, code violations)
- Geographic enrichment with coordinate transformation
- Address standardization and data deduplication
- PostgreSQL database with SQLAlchemy ORM
- Airflow orchestration for daily ETL pipelines
- FastAPI REST API with authentication
- Streamlit dashboard with interactive lead analysis
- Comprehensive unit tests (115+ passing)
- Structured logging with structlog
- Configuration management with Pydantic

### Phase 3.6 New Features (Conservative Profitability Guardrails)
- **Profitability Bucket Scoring** - 4-bucket weighted system with profit validation
- **Conservative ARV Estimation** - Market value-based estimates (no MLS dependency)
- **Repair Cost Modeling** - Violation-based repair estimates with property age adjustments
- **Acquisition Cost Analysis** - Seed-type aware cost estimation (tax sale, foreclosure, direct)
- **Tier Guardrails** - Unprofitable properties cannot achieve Tier A/B status
- **ML Feature Store** - Automated feature engineering and materialization
- **Model Registry** - Version tracking and lifecycle management for ML models
- **Hybrid Scoring** - Blends heuristic bucket scores with ML predictions

## Data Sources

1. **Tax Sale Properties**: Orange County ArcGIS REST API
   - 86 properties with TDA numbers, sale dates, parcel IDs, coordinates

2. **Foreclosures**: Orange County Public MapServer Layer 44
   - Active foreclosures with borrower names, default amounts, auction dates

3. **Property Records**: Orange County Property Appraiser Layer 216
   - 700K+ parcels with market values, assessed values, taxes, living area

4. **Code Enforcement Violations**: City of Orlando Socrata API
   - 40K+ violations with State Plane coordinates (converted to WGS84)
   - 99.3% successful coordinate transformation rate

## Architecture

### Project Structure

```
wholesaler/
├── config/
│   ├── settings.py              # Pydantic configuration management
│   └── __init__.py
├── src/
│   ├── wholesaler/              # Main application package
│   │   ├── scrapers/            # Data ingestion from APIs
│   │   │   ├── tax_sale_scraper.py
│   │   │   ├── foreclosure_scraper.py
│   │   │   └── property_scraper.py
│   │   ├── enrichers/           # Data enrichment
│   │   │   └── geo_enricher.py  # Geographic proximity matching
│   │   ├── transformers/        # Data transformation
│   │   │   ├── coordinate_transformer.py  # State Plane → WGS84
│   │   │   └── address_standardizer.py    # Address normalization
│   │   ├── db/                  # Database layer
│   │   │   ├── models.py        # SQLAlchemy ORM models
│   │   │   ├── repository.py    # Data access layer
│   │   │   └── session.py       # Database sessions
│   │   ├── etl/                 # ETL loaders and transformers
│   │   │   ├── loaders.py       # Bulk data loading
│   │   │   └── seed_merger.py   # Seed deduplication
│   │   ├── scoring/             # Lead scoring engines
│   │   │   ├── scorers.py       # HybridBucketScorer
│   │   │   └── profitability_scorer.py  # ConservativeProfitabilityBucket
│   │   ├── ml/                  # Machine learning infrastructure
│   │   │   ├── features/        # Feature engineering
│   │   │   │   └── feature_store.py  # FeatureStoreBuilder
│   │   │   ├── training/        # Model training
│   │   │   │   ├── train_distress_classifier.py
│   │   │   │   ├── train_sale_probability.py
│   │   │   │   └── model_registry.py  # Model versioning
│   │   │   └── inference/       # Model serving
│   │   │       └── hybrid_ml_scorer.py  # Production ML inference
│   │   ├── api/                 # FastAPI application
│   │   │   ├── main.py          # API entry point
│   │   │   ├── routers/         # API endpoints
│   │   │   │   ├── leads.py
│   │   │   │   ├── predictions.py
│   │   │   │   └── stats.py
│   │   │   └── schemas.py       # Pydantic request/response models
│   │   ├── frontend/            # Streamlit dashboard
│   │   │   ├── app.py           # Dashboard entry point
│   │   │   ├── components/      # UI components
│   │   │   └── pages/           # Multi-page sections
│   │   └── utils/               # Shared utilities
│   │       ├── logger.py        # Structured logging
│   │       └── geo_utils.py     # Distance calculations
│   └── data_ingestion/          # Legacy code (maintained for compatibility)
├── dags/                        # Airflow DAGs
│   ├── daily_property_ingestion.py
│   ├── daily_lead_scoring.py
│   ├── ml_feature_materialization.py
│   ├── ml_model_training.py
│   └── tier_a_alert_notifications.py
├── tests/                       # 115+ unit tests
│   ├── wholesaler/              # Tests for main package
│   │   ├── scoring/             # Scoring tests
│   │   ├── etl/                 # ETL tests
│   │   └── pipelines/           # Pipeline tests
│   └── dags/                    # DAG tests
├── alembic/                     # Database migrations
│   └── versions/                # Migration scripts
├── scripts/                     # Utility scripts
│   ├── enrich_seeds.py          # Seed enrichment CLI
│   ├── run_lead_scoring.py      # Manual scoring runner
│   └── load_enriched_seeds.py   # Data loading helper
├── docs/                        # Documentation
│   ├── phases/                  # Phase planning docs
│   ├── profitability/           # Profitability analysis
│   ├── summaries/               # Executive summaries
│   └── architecture/            # Architecture docs
├── data/                        # Data files (gitignored)
│   ├── raw/                     # Raw scraped data
│   ├── processed/               # Enriched datasets (parquet)
│   └── features/                # ML feature snapshots
├── models/                      # Trained ML models (gitignored)
├── .env                         # Environment variables (gitignored)
├── .env.example                 # Template for configuration
├── requirements.txt             # Python dependencies
├── docker-compose.yml           # Docker services
├── Makefile                     # Development commands
├── pytest.ini                   # Test configuration
└── README.md                    # This file
```

### Data Pipeline Flow

```
1. Seed Collection (Dual Pools)
   ├── Tax Sale Candidates (ArcGIS)
   └── Distress Candidates (Code Violations + Foreclosures)
          ↓
2. Unified Enrichment Pipeline
   ├── Coordinate transformation + address normalization
   ├── Code violation proximity metrics
   └── Merge with property records & tax/foreclosure data
          ↓
3. Data Deduplication & Storage
   └── One record per normalized parcel ID with seed_type metadata
          ↓
4. Lead Scoring (0-100, Tiers A/B/C/D with Profitability Guardrails)
   ├── Distress Bucket (55%): Violations, recency, severity
   ├── Disposition Bucket (15%): Tax sale, foreclosure signals
   ├── Equity Bucket (10%): Market value, equity ratio
   └── Profitability Bucket (20%): ARV-based profit calculation ← NEW!
          ↓
5. Profitability Validation (Conservative Guardrails)
   ├── ARV Estimation (market value + seed-type multiplier)
   ├── Repair Cost Estimation (violation-based + age adjustments)
   ├── Acquisition Cost Analysis (seed-type specific)
   └── 70% Rule Validation: (ARV × 0.70) - Repairs - Acquisition > $15K
          ↓
6. ML Feature Engineering & Inference
   ├── Feature Store Materialization (25+ features)
   ├── Model Registry (distress classifier, sale probability)
   └── Hybrid ML Scoring (blends heuristics + predictions)
          ↓
7. Ranked Investment Opportunities
   └── Tier A/B leads guaranteed profitable by conservative math
```

## Setup

### Prerequisites

- Python 3.13+
- Docker & Docker Compose (for full system)
- Make (optional, for simplified commands)

### Quick Setup (Recommended)

Using the Makefile for automated setup:

```bash
# Complete setup (creates .env, installs dependencies, creates directories)
make setup

# Edit .env file with your credentials
nano .env

# Launch the complete system (database, Airflow, dashboard)
make start

# View dashboard
open http://localhost:8501
```

### Manual Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env and add your credentials
nano .env

# Start Docker services
docker-compose up -d
```

### Configuration

1. **API Credentials** - Add to `.env`:
```bash
SOCRATA_API_KEY=your_key_here
SOCRATA_API_SECRET=your_secret_here
SOCRATA_APP_TOKEN=your_token_here
```

2. **Alert Settings** (optional) - See [ALERTS_SETUP.md](ALERTS_SETUP.md):
```bash
ALERT_ENABLE_EMAIL=true
ALERT_EMAIL=your-email@example.com
SMTP_HOST=smtp.gmail.com
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

## Makefile Commands

The Makefile provides convenient shortcuts for all common operations:

```bash
# View all available commands
make help

# Dashboard & Services
make dashboard          # Launch dashboard (starts all services)
make stop              # Stop all services
make restart           # Restart all services
make status            # Show service status

# Data Pipeline
make scrape-data       # Download fresh data from APIs
make load-data         # Load data into database
make score-leads       # Run lead scoring
make pipeline-full     # Run complete pipeline
make ingest-seeds      # Collect hybrid seed pools (tax sales, foreclosures, violations)
make enrich-seeds      # Enrich seeds, write parquet, and load staging tables
make load-enriched-seeds # Reload enriched_seeds.parquet into the database

# Machine Learning
make train-models      # Train ARV and lead models

# Database
make db-shell          # Open PostgreSQL shell
make db-migrate        # Create new migration
make db-upgrade        # Run migrations
make stats             # Show database statistics

# Testing & Development
make test              # Run all tests
make test-cov          # Run tests with coverage
make lint              # Run code linting
make format            # Auto-format code

# Monitoring
make logs              # View all logs
make logs-dashboard    # View dashboard logs
make logs-airflow      # View Airflow logs
make health            # Check service health

# Airflow
make airflow-trigger-all  # Manually trigger all DAGs
make airflow-unpause      # Enable automatic scheduling
make airflow-list         # List all DAGs

# Cleanup
make clean             # Remove temporary files
make clean-all         # Remove all generated files
```

## Airflow Workflows

The system runs 7 automated DAGs for daily ETL, scoring, and ML training:

### Daily Workflows

1. **daily_property_ingestion** (2:00 AM)
   - Fetches fresh data from all APIs (tax sales, foreclosures, violations)
   - Saves raw data to staging tables
   - Dependencies: None (runs first)

2. **daily_transformation_pipeline** (3:00 AM)
   - Enriches properties with geo proximity metrics
   - Merges data sources by parcel ID
   - Loads deduplicated data to main tables
   - Dependencies: Waits for daily_property_ingestion

3. **daily_lead_scoring** (4:00 AM)
   - Scores all properties using HybridBucketScorer
   - Applies profitability validation
   - Ranks leads into Tiers A/B/C/D
   - Creates daily history snapshots
   - Dependencies: Waits for daily_transformation_pipeline

4. **ml_feature_materialization** (5:00 AM)
   - Extracts 25+ features from enriched properties
   - Exports to Parquet for offline training
   - Materializes to ml_feature_store table for real-time inference
   - Dependencies: Waits for daily_lead_scoring

5. **tier_a_alert_notifications** (6:00 AM)
   - Identifies new Tier A leads since yesterday
   - Sends email alerts with lead details
   - Filters out already-contacted leads
   - Dependencies: Waits for daily_lead_scoring

### Weekly Workflows

6. **ml_model_training** (Sunday 2:00 AM)
   - Trains distress classifier (LightGBM)
   - Trains sale probability model (Logistic Regression)
   - Registers models in model_registry table
   - Promotes models if metrics exceed thresholds
   - Cleans up old model versions
   - Dependencies: None (runs weekly)

7. **seed_based_ingestion** (Manual trigger)
   - Alternative ingestion using seed-based strategy
   - Fetches seeds → enriches → merges → scores
   - Used for custom data scenarios
   - Dependencies: None

**Monitoring:**
- View DAG status: `make airflow-list`
- Trigger all DAGs: `make airflow-trigger-all`
- Enable scheduling: `make airflow-unpause`
- View logs: `make logs-airflow`

## Usage

### Fetch Tax Sale Properties

```python
from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper

scraper = TaxSaleScraper()
properties = scraper.fetch_properties(limit=10)
scraper.display_properties(properties)
```

### Fetch Foreclosures

```python
from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper

scraper = ForeclosureScraper()
foreclosures = scraper.fetch_foreclosures(limit=10)
scraper.display_foreclosures(foreclosures)
```

### Fetch Property Records by Parcel

```python
from src.wholesaler.scrapers.property_scraper import PropertyScraper

scraper = PropertyScraper()
property = scraper.fetch_by_parcel("123456789012345")
```

### Seed-Based Enrichment Pipeline

```bash
# Step 1: collect fresh seeds from every ingestion source
make ingest-seeds

# Step 2: enrich seeds (includes geo proximity metrics), write parquet, and load staging tables
make enrich-seeds

# (Optional) Reload an existing parquet without re-enriching
make load-enriched-seeds
```

The enrichment CLI mirrors the Airflow DAG. You can run it manually for custom scenarios:

```bash
.venv/bin/python scripts/enrich_seeds.py \
  --seeds-path data/processed/seeds.json \
  --output data/processed/enriched_seeds.parquet \
  --geo-csv data/code_enforcement_data.csv \
  --geo-radius 0.5 \
  --load
```

Flags:
- `--load`: immediately push the parquet rows into `enriched_seeds`, `properties`, `tax_sales`, and `foreclosures`.
- `--disable-geo`: opt-out of geo proximity metrics (enabled by default). Override data/radius with `--geo-csv` / `--geo-radius`.
- `--output` / `--seeds-path`: customize file locations if you are testing alternate datasets.

### Geographic Enrichment

```python
from src.wholesaler.enrichers.geo_enricher import GeoPropertyEnricher

enricher = GeoPropertyEnricher('data/code_enforcement_data.csv', radius_miles=0.25)
enriched_properties = enricher.enrich_properties(tax_sale_properties)
enricher.display_summary_stats(enriched_properties)
```

### Lead Scoring

```python
from src.wholesaler.pipelines.deduplication import PropertyDeduplicator
from src.wholesaler.pipelines.lead_scoring import LeadScorer

# Merge data sources
deduplicator = PropertyDeduplicator()
merged = deduplicator.merge_sources(
    tax_sales=tax_sales,
    foreclosures=foreclosures,
    property_records=property_records
)

# Score leads
scorer = LeadScorer()
scored_leads = [(prop, scorer.score_lead(prop)) for prop in merged]
ranked_leads = scorer.rank_leads(scored_leads)

# Top tier A leads
tier_a_leads = [lead for lead in ranked_leads if lead[1].tier == "A"]
```

### Priority Leads API

The API exposes an additional endpoint that surfaces high-probability leads using the new hybrid/logistic scoring blend:

```
GET /api/v1/leads/priority?limit=50
```

Each item includes `priority_score`, the hybrid tier, and logistic probability so the dashboard/team can focus on the most actionable properties even when legacy tiers remain low.

The Streamlit dashboard also includes a **Priority Leads** tab that surfaces the same data with download support.

## Testing

```bash
# Run all unit tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run specific module tests
pytest tests/wholesaler/scrapers/test_foreclosure_scraper.py -v

# Skip integration tests (require internet)
pytest tests/ -v -m "not integration"
```

**Test Results:**
- 115 unit tests
- 0 failures
- 58% code coverage (focus on business logic)

## Lead Scoring Algorithm

### 4-Bucket Weighted System (Phase 3.6)

The scoring system uses weighted buckets with conservative profitability validation:

1. **Distress Bucket (55% weight)**
   - Violation count: 10 points per violation (clamped 0-100)
   - Open violations: +12 points each
   - Recent violations: +25 points for recency
   - Measures: Property distress signals and maintenance issues

2. **Disposition Bucket (15% weight)**
   - Tax sale status: +60 points
   - Foreclosure status: +45 points
   - Default amount bonus: up to +20 points based on debt size
   - Code violation seed type: +25 points
   - Measures: Forced sale likelihood and urgency

3. **Equity Bucket (10% weight)**
   - High equity (200%+): +50 points
   - Medium equity (150-199%): +35 points
   - Low equity (120-149%): +20 points
   - Target price range ($80K-$450K): +30 points
   - Measures: Financial leverage and deal feasibility

4. **Profitability Bucket (20% weight)** ← NEW in Phase 3.6
   - Conservative ARV estimation using market value
   - Repair cost calculation based on violations + property age
   - Acquisition cost based on seed type (tax sale, foreclosure, direct)
   - **70% Rule**: `(ARV × 0.70) - Repairs - Acquisition`
   - Score 50-100 if profit ≥ $15K, otherwise 0
   - Measures: Actual deal profitability with conservative assumptions

**Additional Bonuses:**
- Tax sale status: +15 points
- Foreclosure status: +10 points

### Tier System with Profitability Guardrails

- **Tier A (60+):** Premium leads - **MUST be profitable** (profit ≥ $15K)
- **Tier B (45-59):** Strong leads - **MUST be profitable** (profit ≥ $15K)
- **Tier C (32-44):** Moderate leads - Profitability optional
- **Tier D (<32):** Low priority - Passive monitoring

**Guardrail Logic:**
If a property scores 60+ but fails profitability validation (profit < $15K), it is automatically downgraded to Tier C or D. This prevents high-distress but unprofitable properties from consuming team resources.

### Conservative Profitability Calculation

Phase 3.6 implements conservative "guardrail" math to ensure Tier A/B leads are actually profitable:

**ARV Estimation (Conservative, No MLS Dependency):**
- Tax Sale properties: Market Value × 1.10 (10% upside)
- Foreclosure properties: Market Value × 1.12 (12% upside)
- Direct/Code Violation: Market Value × 1.06 (6% upside)
- Fallback: Assessed Value × 1.25 if market value unavailable

**Repair Cost Estimation:**
- Base cost: $25/sqft for cosmetic rehab (minimum $15K)
- Light distress (<5 violations): +$5/sqft
- Heavy distress (5+ violations): +$15/sqft
- Pre-1980 properties: +$10/sqft for age-related issues

**Acquisition Cost:**
- Tax Sale: Opening bid or taxes owed
- Foreclosure: Default amount or opening bid
- Direct: Assumes 50% of ARV (conservative negotiation estimate)

**Profit Calculation:**
```python
end_buyer_price = (ARV × 0.70) - repair_costs
projected_profit = end_buyer_price - acquisition_cost
is_profitable = projected_profit >= $15,000
```

**Example:**
```
Property: 123 Main St (Tax Sale, 5 violations, built 1975)
├─ Market Value: $200,000
├─ ARV Estimate: $200K × 1.10 = $220,000
├─ Repair Costs: 1,500 sqft × ($25 + $15 + $10) = $75,000
├─ Acquisition: $50,000 (opening bid)
├─ End Buyer Price: ($220K × 0.70) - $75K = $79,000
├─ Projected Profit: $79K - $50K = $29,000 ✅
└─ Result: PROFITABLE - Eligible for Tier A/B
```

## Technical Stack

**Core:**
- Python 3.13
- Pydantic 2.10.4 (data validation)
- Pydantic-settings 2.7.1 (configuration)
- Structlog 25.1.0 (logging)

**Database & ORM:**
- PostgreSQL 15+
- SQLAlchemy 2.0+ (ORM)
- Alembic (migrations)

**Data Processing:**
- pandas 2.3.3
- numpy 2.3.4
- pyproj 3.7.2 (coordinate transformation)

**Machine Learning:**
- scikit-learn 1.5+ (training & inference)
- LightGBM / XGBoost (gradient boosting)
- joblib (model serialization)

**Orchestration & ETL:**
- Apache Airflow 2.10+ (workflow orchestration)
- Celery (task queue)

**Web Framework:**
- FastAPI (REST API)
- Streamlit (dashboard)
- Uvicorn (ASGI server)

**APIs & Scraping:**
- requests 2.32.5
- sodapy 2.2.0

**Testing:**
- pytest 8.4.2
- pytest-cov 7.0.0

**Infrastructure:**
- Docker & Docker Compose
- Redis (caching & Celery broker)
- Nginx (reverse proxy)

## Development Principles

- Incremental development with testing after each change
- No file > 100 lines without testing
- Production-ready code from day 1
- Structured logging throughout
- Type-safe models with Pydantic
- Comprehensive documentation
- Configuration via environment variables

## Roadmap

### Phase 1: Foundation ✅ COMPLETE
- ✅ Multi-source data scrapers (tax sales, foreclosures, property records, violations)
- ✅ Geographic enrichment and coordinate transformation
- ✅ Address standardization and normalization
- ✅ Data deduplication by parcel ID
- ✅ Initial lead scoring algorithm
- ✅ Comprehensive unit tests (115+ tests)

### Phase 2: ETL Pipeline & Persistence ✅ COMPLETE
- ✅ Database schema design (PostgreSQL)
- ✅ SQLAlchemy ORM models
- ✅ Data persistence layer with repositories
- ✅ Airflow orchestration (7 DAGs)
- ✅ Scheduled job execution (daily ingestion, scoring, notifications)

### Phase 3: Advanced Features ✅ COMPLETE
- ✅ Seed-based ingestion (dual-pool strategy)
- ✅ Unified enrichment pipeline
- ✅ Repair cost estimation (violation-based with age adjustments)
- ✅ Conservative ARV calculations (market value multipliers)
- ✅ Profitability validation (70% rule)
- ✅ ML Feature Store (25+ features, automated materialization)
- ✅ Model Registry (version tracking, promotion, lifecycle management)

### Phase 4: API & Serving ✅ COMPLETE
- ✅ FastAPI endpoints (properties, leads, predictions, stats)
- ✅ Redis caching
- ✅ Authentication/authorization
- ✅ Rate limiting
- ✅ OpenAPI documentation

### Phase 5: Frontend & Monitoring ✅ COMPLETE
- ✅ Streamlit dashboard (lead browsing, analytics, exports)
- ✅ Alert system for Tier A leads (email notifications)
- ✅ Performance monitoring (structured logging)
- ✅ Airflow monitoring UI

### Phase 6: Enhancement Opportunities 🔜 NEXT
- [ ] **Phase 3.6.B**: MLS/Zillow integration for comp-based ARV (optional)
- [ ] **Phase 4**: Advanced ML features
  - [ ] Sale probability regression (more training data needed)
  - [ ] Expected return estimation
  - [ ] Market trend analysis
- [ ] **Production Deployment**
  - [ ] AWS RDS for database
  - [ ] S3 for data storage
  - [ ] EC2/Lambda for compute
  - [ ] CloudWatch metrics & logging
- [ ] **Data Quality**
  - [ ] Automated data validation pipelines
  - [ ] Feature drift detection
  - [ ] Model performance monitoring

## Key Features

**Multi-source data integration** from 4 different APIs with dual-pool seeding strategy
**Coordinate transformation** from State Plane to WGS84 with 99.3% success rate
**Geographic proximity matching** with Haversine distance for violation enrichment
**Address standardization** across all data sources
**Smart deduplication** by normalized parcel ID with seed_type tracking
**4-bucket lead scoring** with conservative profitability guardrails
**Profitability validation** using 70% rule with conservative ARV estimates
**ML Feature Store** with automated feature engineering and materialization
**Model Registry** for version tracking and model lifecycle management
**Hybrid ML scoring** blending heuristic buckets with ML predictions
**Production logging** with structured JSON output via structlog
**Type-safe models** with Pydantic validation
**Comprehensive testing** with 115+ unit tests
**Automated workflows** with 7 Airflow DAGs for daily ETL and weekly model training
**Real-time API** with FastAPI serving lead predictions and analytics
**Interactive dashboard** with Streamlit for lead browsing and analysis

## License

Private project - All rights reserved

## Contact

Carl Marco
