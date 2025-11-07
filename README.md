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

## Project Goal

Identify profitable wholesale opportunities where:
```
ARV * 0.7 - repair_costs - acquisition_cost > $15,000 profit
```

## Current Status

**Phase 1: COMPLETE** - Foundation & Core Pipeline

- Tax sale property scraper (ArcGIS API)
- Foreclosure data scraper (ArcGIS API)
- Property records scraper (Property Appraiser API)
- Code enforcement violation data (Socrata API)
- Geographic enrichment with coordinate transformation
- Address standardization
- Data deduplication pipeline
- Lead scoring algorithm
- Comprehensive unit tests (115 passing)
- Structured logging with structlog
- Configuration management with Pydantic

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
│   ├── wholesaler/              # New modular architecture
│   │   ├── scrapers/            # Data ingestion from APIs
│   │   │   ├── tax_sale_scraper.py
│   │   │   ├── foreclosure_scraper.py
│   │   │   └── property_scraper.py
│   │   ├── enrichers/           # Data enrichment
│   │   │   └── geo_enricher.py  # Geographic proximity matching
│   │   ├── transformers/        # Data transformation
│   │   │   ├── coordinate_transformer.py  # State Plane → WGS84
│   │   │   └── address_standardizer.py    # Address normalization
│   │   ├── models/              # Pydantic data models
│   │   │   ├── property.py      # TaxSaleProperty, EnrichedProperty
│   │   │   ├── foreclosure.py   # ForeclosureProperty
│   │   │   └── property_record.py  # PropertyRecord
│   │   ├── pipelines/           # Data pipelines
│   │   │   ├── deduplication.py    # Merge by parcel ID
│   │   │   └── lead_scoring.py     # Score investment opportunities
│   │   └── utils/               # Shared utilities
│   │       ├── logger.py        # Structured logging
│   │       ├── geo_utils.py     # Distance calculations
│   │       └── adapters.py      # Backward compatibility
│   └── data_ingestion/          # Legacy code (maintained for compatibility)
├── tests/                       # 115 unit tests
│   ├── wholesaler/              # Tests for new architecture
│   └── data_ingestion/          # Tests for legacy code
├── data/                        # Data files (gitignored)
├── .env                         # Environment variables (gitignored)
├── .env.example                 # Template for configuration
├── requirements.txt             # Python dependencies
├── pytest.ini                   # Test configuration
└── README.md                    # This file
```

### Data Pipeline Flow

```
1. Data Ingestion (Scrapers)
   ├── Tax Sales (86 properties)
   ├── Foreclosures (active lis pendens)
   ├── Property Records (valuations, taxes)
   └── Code Violations (40K+ records)
          ↓
2. Coordinate Transformation
   └── State Plane (EPSG:2881) → WGS84 (EPSG:4326)
          ↓
3. Geographic Enrichment
   └── Find violations within 0.25 mile radius
          ↓
4. Address Standardization
   └── Normalize addresses, parcel IDs
          ↓
5. Data Deduplication
   └── Merge sources by normalized parcel ID
          ↓
6. Lead Scoring (0-100, Tiers A/B/C/D)
   ├── Distress Score (35%): tax sale, foreclosure, violations
   ├── Value Score (30%): equity, market value, tax burden
   ├── Location Score (20%): neighborhood condition
   └── Urgency Score (15%): auction dates, timelines
          ↓
7. Ranked Investment Opportunities
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

### Components (Weighted)

1. **Distress Score (35%)**
   - Tax sale status: +40 points
   - Foreclosure status: +40 points
   - Code violations nearby: up to +20 points
   - Open violations: +3 points

2. **Value Score (30%)**
   - High equity (>200%): +40 points
   - Target price range ($100K-$400K): +30 points
   - Low tax burden: +15 points
   - Good size: +15 points

3. **Location Score (20%)**
   - Clean neighborhood: +30 points
   - Violation density: ±20 points
   - Proximity to issues: ±10 points

4. **Urgency Score (15%)**
   - Foreclosure auction scheduled: +50 points
   - Tax sale date set: +40 points
   - Open violations: +10 points

### Tier System

- **Tier A (75-100):** Hot leads requiring immediate action
- **Tier B (60-74):** Good leads, high priority
- **Tier C (40-59):** Moderate leads, review
- **Tier D (0-39):** Low priority, passive monitoring

## Technical Stack

**Core:**
- Python 3.13
- Pydantic 2.10.4 (data validation)
- Pydantic-settings 2.7.1 (configuration)
- Structlog 25.1.0 (logging)

**Data Processing:**
- pandas 2.3.3
- numpy 2.3.4
- pyproj 3.7.2 (coordinate transformation)

**APIs & Scraping:**
- requests 2.32.5
- sodapy 2.2.0

**Testing:**
- pytest 8.4.2
- pytest-cov 7.0.0

## Development Principles

- Incremental development with testing after each change
- No file > 100 lines without testing
- Production-ready code from day 1
- Structured logging throughout
- Type-safe models with Pydantic
- Comprehensive documentation
- Configuration via environment variables

## Roadmap

### Phase 2: ETL Pipeline & Persistence
- [ ] Database schema design (PostgreSQL)
- [ ] SQLAlchemy ORM models
- [ ] Data persistence layer
- [ ] Airflow orchestration
- [ ] Scheduled job execution

### Phase 3: Advanced Features
- [ ] Property valuation ML model
- [ ] Repair cost estimation
- [ ] Comp analysis integration
- [ ] ARV calculations
- [ ] ROI projections

### Phase 4: API & Serving
- [ ] FastAPI endpoints
- [ ] Redis caching
- [ ] Authentication/authorization
- [ ] Rate limiting

### Phase 5: Frontend & Monitoring
- [ ] Streamlit dashboard
- [ ] CloudWatch metrics
- [ ] Alert system for Tier A leads
- [ ] Performance monitoring

### Phase 6: AWS Deployment
- [ ] RDS for database
- [ ] S3 for data storage
- [ ] EC2/Lambda for compute
- [ ] CloudWatch logging

## Key Features

**Multi-source data integration** from 4 different APIs
**Coordinate transformation** from State Plane to WGS84
**Geographic proximity matching** with Haversine distance
**Address standardization** across all data sources
**Smart deduplication** by normalized parcel ID
**Lead scoring algorithm** with 4-component weighting
**Production logging** with structured JSON output
**Type-safe models** with Pydantic validation
**Comprehensive testing** with 115 unit tests

## License

Private project - All rights reserved

## Contact

Carl Marco
