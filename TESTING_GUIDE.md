# End-to-End Testing Guide

This guide walks you through testing the complete Wholesaler Lead Management System from data ingestion to dashboard visualization.

## Prerequisites

1. **Docker Desktop** installed and running
2. **Python 3.11+** installed
3. **Git** repository cloned

## Step 1: Install Dependencies

```bash
# Install all required Python packages
pip install -r requirements.txt
```

This installs:
- Core dependencies (pandas, numpy, requests, etc.)
- Database (SQLAlchemy, psycopg2, Alembic, GeoAlchemy2)
- API (FastAPI, uvicorn)
- Frontend (Streamlit, plotly, pydeck)
- Authentication (python-jose, passlib)
- Caching (redis, hiredis)
- ML (scikit-learn, xgboost)

## Step 2: Start PostgreSQL with PostGIS

```bash
# Start the database container
docker-compose up -d postgres

# Wait for database to be ready (10-15 seconds)
docker-compose ps postgres

# Verify PostGIS is enabled
docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler \
  -c "SELECT postgis_version();"
```

**Expected output:**
```
postgis_version
---------------------------------------
 3.5 USE_GEOS=1 USE_PROJ=1 USE_STATS=1
```

## Step 3: Create Database Tables

```bash
# Run the database setup script
python scripts/create_database_tables.py
```

**Expected output:**
```
Successfully created 8 tables:
  - code_violations
  - data_ingestion_runs
  - foreclosures
  - lead_score_history
  - lead_scores
  - properties
  - property_records
  - tax_sales
```

**Troubleshooting:**
- If you get ModuleNotFoundError: Run `pip install -r requirements.txt`
- If tables already exist: Script will skip creation
- If PostGIS errors: Verify PostgreSQL container is running

## Step 4: Download Test Data

```bash
# Download 20 tax sales + 20 foreclosures from Orange County
python scripts/download_test_data.py
```

**Expected output:**
```
TEST DATA DOWNLOAD COMPLETE
Tax Sales: 20 properties
Foreclosures: 20 properties

Files saved to:
  - data/test_tax_sales.json
  - data/test_foreclosures.json
```

**Optional:** Inspect the JSON files to verify data quality:
```bash
cat data/test_tax_sales.json | head -50
```

## Step 5: Load Data into Database

```bash
# Load test data via ETL pipeline
python scripts/load_test_data.py
```

**Expected output:**
```
TEST DATA LOADING COMPLETE

Tax Sales:
  Processed: 20
  Inserted: 20
  Updated: 0
  Failed: 0

Foreclosures:
  Processed: 20
  Inserted: 20
  Updated: 0
  Failed: 0
```

**Verify data was loaded:**
```bash
docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler \
  -c "SELECT COUNT(*) FROM properties;"
```

## Step 6: Start Redis (Optional for Caching)

```bash
# Start Redis container
docker-compose up -d redis

# Verify Redis is running
docker-compose ps redis

# Test Redis connection
docker exec wholesaler_redis redis-cli ping
```

**Expected:** `PONG`

**Note:** Redis is optional. If not running, the API will work without caching.

## Step 7: Start FastAPI Server

```bash
# Terminal 1: Start API server
python -m uvicorn src.wholesaler.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Verify API is running:**
```bash
curl http://localhost:8000/health | jq
```

**Expected response:**
```json
{
  "status": "healthy",
  "version": "0.3.1",
  "database": "connected",
  "timestamp": "2025-11-07T..."
}
```

## Step 8: Test API Endpoints

### Get Authentication Token
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=secret" | jq -r '.access_token')

echo "Token: $TOKEN"
```

### Get Dashboard Stats
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/stats/dashboard | jq
```

### List Leads
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/leads?limit=5" | jq
```

### Get Lead Detail
```bash
# Replace PARCEL_ID with an actual ID from the leads list
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/leads/PARCEL_ID | jq
```

### Get ML Deal Analysis
```bash
# Get comprehensive deal analysis
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/analysis/PARCEL_ID | jq

# Get ARV estimate only
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/analysis/PARCEL_ID/arv | jq

# Get repair cost estimate only
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/analysis/PARCEL_ID/repair-costs | jq
```

## Step 9: Start Streamlit Dashboard

```bash
# Terminal 2: Start Streamlit
streamlit run src/wholesaler/frontend/app.py --server.port 8501
```

**Expected output:**
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.1.x:8501
```

**Browser will automatically open to:** `http://localhost:8501`

## Step 10: Test Dashboard Features

### Home Page (Dashboard)
- [ ] API connection status shows "API Connected"
- [ ] Total leads count displays
- [ ] Tier distribution metrics show (A, B, C, D counts)
- [ ] Recent Tier A leads count displays
- [ ] Quick stats show property, tax sale, foreclosure counts

### Leads List Page
- [ ] Table displays 20+ properties
- [ ] Sidebar filters work (tier, score range, city, ZIP)
- [ ] Sort dropdown changes order
- [ ] Pagination buttons work
- [ ] CSV export downloads file
- [ ] Tier distribution chart displays

### Lead Detail Page
- [ ] Parcel ID input accepts normalized IDs
- [ ] Property details table displays
- [ ] Score breakdown chart shows 4 components
- [ ] Scoring reasons list displays
- [ ] Tax sale/foreclosure info shows (if available)
- [ ] Map displays property location (if coordinates available)

### Map View Page
- [ ] Interactive map displays with property markers
- [ ] Markers are color-coded by tier (Green/Blue/Yellow/Gray)
- [ ] Clicking markers shows tooltips with property info
- [ ] Map style selector works
- [ ] Geographic distribution stats display

### Reports Page
- [ ] Tier distribution pie chart displays
- [ ] Score distribution histogram shows
- [ ] Average scores bar chart displays
- [ ] Statistical summary shows (mean, median, std dev)
- [ ] Recent activity metrics display

### Deal Analyzer Page
- [ ] Parcel ID input works
- [ ] Recommendation badge displays (STRONG BUY/BUY/HOLD/PASS)
- [ ] Key metrics show (ARV, Repair Costs, Max Offer, ROI)
- [ ] Opportunity factors list displays
- [ ] Risk factors list displays
- [ ] Confidence level indicator shows
- [ ] Deal breakdown with formulas displays

## Step 11: Test Authentication

### Login via API
```bash
# Get token
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=secret"
```

### Test Protected Endpoints
```bash
# Without token (should work - endpoints not protected by default)
curl http://localhost:8000/api/v1/stats/dashboard

# With token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/auth/users/me
```

## Step 12: Test Caching

### Test Cache Performance
```bash
# First request (cache miss)
time curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/stats/dashboard > /dev/null

# Second request (cache hit - should be much faster)
time curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/stats/dashboard > /dev/null
```

### Check Cache Stats
```python
from src.wholesaler.api.cache import get_cache_stats
print(get_cache_stats())
```

**Expected output:**
```python
{
  'available': True,
  'total_keys': 5,
  'hits': 10,
  'misses': 3,
  'hit_rate': 76.9
}
```

## Troubleshooting

### Database Connection Errors

**Error:** `could not connect to server`

**Solution:**
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Restart if needed
docker-compose restart postgres
```

### Module Not Found Errors

**Error:** `ModuleNotFoundError: No module named 'X'`

**Solution:**
```bash
# Reinstall all dependencies
pip install --upgrade -r requirements.txt
```

### PostGIS Errors

**Error:** `function postgis_version() does not exist`

**Solution:**
```bash
# Enable PostGIS extension manually
docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler \
  -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Recreate tables
python scripts/create_database_tables.py
```

### API 500 Errors

**Check API logs:**
```bash
# API should be running in Terminal 1 with --reload flag
# Logs will show errors in real-time
```

**Common causes:**
- Database tables don't exist: Run `scripts/create_database_tables.py`
- Redis connection failed: Start Redis or API will work without caching
- Missing dependencies: Run `pip install -r requirements.txt`

### Dashboard Not Loading

**Check Streamlit logs:**
```bash
# Streamlit should be running in Terminal 2
# Logs will show errors
```

**Common causes:**
- API not running: Start FastAPI on port 8000
- Wrong API URL: Check `src/wholesaler/frontend/utils/api_client.py`
- Port conflict: Use different port with `--server.port 8502`

### No Data in Dashboard

**Verify data was loaded:**
```bash
docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler <<'EOF'
SELECT COUNT(*) FROM properties;
SELECT COUNT(*) FROM tax_sales;
SELECT COUNT(*) FROM foreclosures;
EOF
```

**If counts are 0, reload data:**
```bash
python scripts/load_test_data.py
```

## Success Criteria Checklist

- [ ] PostgreSQL container running with PostGIS
- [ ] 8 database tables created
- [ ] 20+ properties loaded into database
- [ ] FastAPI health check returns "healthy"
- [ ] JWT authentication works
- [ ] Dashboard loads without errors
- [ ] All 6 pages display correctly
- [ ] ML analysis returns estimates
- [ ] Redis caching improves performance (if enabled)
- [ ] No errors in API or Streamlit logs

## Performance Benchmarks

**Expected Performance:**
- API health check: < 100ms
- Dashboard stats query: 150ms (first) / 5ms (cached)
- Lead list query: 200ms
- ML deal analysis: 50ms
- Dashboard page load: < 2 seconds
- Map view render: < 3 seconds

## Next Steps After Testing

1. **Run Full ETL Pipeline:**
   ```bash
   # Load all tax sales (not just 20)
   python -m src.wholesaler.scrapers.tax_sale_scraper
   ```

2. **Run Lead Scoring:**
   ```bash
   # Score all properties
   python -m src.wholesaler.pipelines.lead_scoring
   ```

3. **Setup Airflow (Phase 2):**
   ```bash
   docker-compose up -d airflow-init
   docker-compose up -d airflow-webserver airflow-scheduler airflow-worker
   ```

4. **Production Deployment:**
   - Configure environment variables
   - Set up HTTPS
   - Enable authentication on all endpoints
   - Configure Redis persistence
   - Set up monitoring and logging

## Support

For issues or questions:
1. Check logs in Terminal 1 (API) and Terminal 2 (Streamlit)
2. Verify all containers are running: `docker-compose ps`
3. Check database connectivity: `docker exec wholesaler_postgres pg_isready`
4. Review PHASE3C_README.md for feature documentation

## Version

**Testing Guide Version:** 1.0
**System Version:** v0.3.1 (Phase 3C)
**Last Updated:** 2025-11-07
