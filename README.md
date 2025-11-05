# Real Estate Wholesaler - Automated Property Analysis System

Production-grade automated real estate wholesaling system that identifies undervalued properties using ML models and public data sources.

## Project Goal

Identify profitable wholesale opportunities where:
```
ARV * 0.7 - repair_costs - acquisition_cost > $15,000 profit
```

## Current Status

**Phase 1: Data Acquisition** - IN PROGRESS

- Tax sale property scraper (ArcGIS API) - COMPLETE
- Code enforcement violation data - COMPLETE
- Data enrichment pipeline - COMPLETE (with known issues)
- AWS infrastructure - PENDING
- Coordinate transformation - PENDING

See [PHASE_1_SUMMARY.md](PHASE_1_SUMMARY.md) for detailed status.

## Data Sources

1. **Tax Sale Properties**: Orange County ArcGIS REST API
   - 86 properties currently available
   - Sale date: 12/18/2025
   - Fields: TDA number, parcel ID, deed status, coordinates

2. **Code Enforcement Violations**: City of Orlando Socrata API
   - 50,000 violation records
   - 76% have parcel IDs
   - 81% have coordinates (State Plane format)

## Project Structure

```
wholesaler/
├── src/
│   └── data_ingestion/
│       ├── tax_sale_scraper.py      # Fetch tax sale properties
│       ├── enrichment.py            # Parcel ID-based enrichment
│       ├── geo_enrichment.py        # Geographic proximity enrichment
│       └── pipeline.py              # Integrated workflow
├── data/                            # Data files (gitignored)
├── requirements.txt                 # Python dependencies
├── PHASE_1_SUMMARY.md              # Detailed phase 1 report
└── README.md                        # This file
```

## Setup

### Prerequisites

- Python 3.13+
- Virtual environment

### Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create `data/work.py` with API credentials:
```python
API_SECRET = "your_socrata_secret"
API_KEY = "your_socrata_key"
APP_TOKEN = "your_socrata_app_token"
```

## Usage

### Fetch Tax Sale Properties

```python
from src.data_ingestion.tax_sale_scraper import TaxSaleScraper

scraper = TaxSaleScraper()
properties = scraper.fetch_properties(limit=10)
scraper.display_properties(properties)
```

### Run Enrichment Pipeline

```python
# Note: Currently blocked by coordinate transformation issue
# See PHASE_1_SUMMARY.md for details

from src.data_ingestion.pipeline import main
main()
```

## Known Issues

1. **Parcel ID Mismatch**: Tax sale and code enforcement use different parcel ID systems (0 matches found)
2. **Coordinate System**: Code enforcement data uses Florida State Plane (EPSG:2881), needs conversion to WGS84
3. **No Geographic Enrichment**: Blocked by coordinate conversion requirement

See [PHASE_1_SUMMARY.md](PHASE_1_SUMMARY.md) for detailed analysis.

## Roadmap

### Phase 1: Data Acquisition (Current)
- [x] Data source selection
- [x] Production scraper
- [x] Enrichment logic
- [ ] Coordinate transformation
- [ ] Unit tests
- [ ] AWS deployment (S3, RDS)

### Phase 2: ETL Pipeline
- [ ] Airflow orchestration
- [ ] Data quality (Great Expectations)
- [ ] Data versioning (DVC)

### Phase 3: ML Models
- [ ] Property valuation (regression)
- [ ] Deal scoring (classification)
- [ ] MLflow tracking
- [ ] Backtesting framework

### Phase 4: API & Serving
- [ ] FastAPI endpoints
- [ ] Redis caching
- [ ] Load testing

### Phase 5: Automation & Monitoring
- [ ] CloudWatch metrics
- [ ] Model drift detection
- [ ] Cost tracking

### Phase 6: Frontend
- [ ] Streamlit dashboard

## Technical Stack

- **Language**: Python 3.13
- **Data**: pandas, numpy
- **APIs**: requests, sodapy
- **Cloud**: AWS (S3, RDS, EC2, CloudWatch)
- **Orchestration**: Airflow
- **ML**: scikit-learn, MLflow
- **API**: FastAPI
- **Testing**: pytest
- **CI/CD**: GitHub Actions

## Development Principles

- Incremental development (test after every change)
- No file > 100 lines without testing
- Production-ready code from day 1
- Comprehensive documentation
- Professional error handling

## License

Private project - All rights reserved

## Contact

Carl Marco
