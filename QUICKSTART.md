# Wholesaler System - Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Setup
```bash
make setup
```
This will:
- Create `.env` file from template
- Install Python dependencies in virtual environment
- Create necessary directories

**Next**: Edit `.env` and add your API credentials

### 2. Launch Dashboard
```bash
make dashboard
```
This starts:
- PostgreSQL database (port 5432)
- Redis cache (port 6379)
- Airflow scheduler & webserver (port 8080)
- Streamlit dashboard (port 8501)

**Access Dashboard**: http://localhost:8501
**Airflow UI**: http://localhost:8080 (admin/admin)

### 3. Load Initial Data
```bash
make pipeline-full
```
This will:
- Download data from APIs (tax sales, foreclosures, properties)
- Load into database
- Score all leads (A/B/C/D tiers)

---

## Common Workflows

### Daily Operations

```bash
# Start the system
make start

# Check everything is healthy
make health

# View database stats
make stats

# View logs
make logs-dashboard    # Dashboard logs only
make logs-airflow      # Airflow logs only
make logs              # All logs

# Stop the system
make stop
```

### Data Pipeline

```bash
# Run complete pipeline (download → load → score)
make pipeline-full

# Or run individual steps
make scrape-data       # Download fresh data
make load-data         # Load to database
make score-leads       # Score leads

# New hybrid ingestion workflow
make ingest-seeds      # Collect seeds from tax sales + distress signals
make enrich-seeds      # Normalize and enrich collected seeds
make data-quality      # Review seed counts & match rates

# Train ML models (ARV + lead qualification)
make train-models
```

### Database Operations

```bash
# Open PostgreSQL shell
make db-shell

# Check database statistics
make stats

# Backup database
make backup-db

# Run migrations
make db-upgrade
```

### Airflow DAGs

```bash
# List all DAGs
make airflow-list

# Trigger all DAGs manually
make airflow-trigger-all

# Enable automatic scheduling
make airflow-unpause
```

The system runs 5 automated DAGs daily:
- **2:00 AM** - Property ingestion (scrape APIs)
- **3:00 AM** - Transformation (enrich + dedupe)
- **4:00 AM** - Lead scoring (A/B/C/D tiers)
- **5:00 AM** - Tier A alerts (email + Slack)
- **6:30 AM** - Data quality checks

### Development

```bash
# Run tests
make test

# Run tests with coverage
make test-cov

# Format code
make format

# Lint code
make lint

# Open Python shell
make shell
```

---

## Troubleshooting

### Dashboard not loading?

```bash
# Check service status
make status

# Check health
make health

# Restart services
make restart

# View logs for errors
make logs-dashboard
```

### No data in dashboard?

```bash
# Load initial data
make pipeline-full

# Check database
make stats

# Should show:
# - total_properties: 186+
# - tax_sales: 86+
# - foreclosures: 100+
# - scored_leads: 186+
# - tier_a_leads: 13+
```

### Airflow not running DAGs?

```bash
# Enable automatic scheduling
make airflow-unpause

# Or manually trigger
make airflow-trigger-all

# View Airflow UI
open http://localhost:8080
```

### Database errors?

```bash
# Run migrations
make db-upgrade

# Reset database (WARNING: deletes all data)
make db-reset
```

---

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **Dashboard** | http://localhost:8501 | None |
| **Airflow UI** | http://localhost:8080 | admin/admin |
| **PostgreSQL** | localhost:5432 | wholesaler_user/wholesaler_pass |
| **Redis** | localhost:6379 | None |

---

## Documentation

- **[README.md](README.md)** - Complete project overview
- **[ML Training Guide](docs/setup/ml_training_guide.md)** - ML model training
- **[Alerts Setup](docs/setup/alerts_setup.md)** - Email & Slack alerts
- **[Testing Guide](docs/guides/testing_guide.md)** - Testing documentation
- **[Database Schema](docs/guides/database_schema.md)** - Database structure
- **[Phase 4 Overview](PHASE_4_OVERVIEW.md)** - AI-agent outreach system

---

## Production Deployment

```bash
# Complete development setup
make dev-setup

# Deploy to production
make prod-deploy

# Backup database
make backup-db

# Monitor health
make health
```

---

## Need Help?

```bash
# View all available commands
make help

# Clean temporary files
make clean

# Complete cleanup (removes models, data, volumes)
make clean-all
```

---

## Success Checklist

- [ ] `.env` file configured with API credentials
- [ ] `make setup` completed successfully
- [ ] `make dashboard` starts all services
- [ ] Dashboard accessible at http://localhost:8501
- [ ] `make pipeline-full` loads initial data
- [ ] Database shows 186+ properties (`make stats`)
- [ ] 13+ Tier A leads visible in dashboard
- [ ] ML models trained (`make train-models`)
- [ ] Airflow DAGs enabled (`make airflow-unpause`)
- [ ] Email/Slack alerts configured (optional - see [Alerts Setup](docs/setup/alerts_setup.md))

---
