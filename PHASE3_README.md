# Phase 3: Frontend + API

This phase implements a REST API and interactive web dashboard for the Wholesaler Lead Management System.

## Architecture

### Phase 3A: FastAPI REST API
- **Location**: `src/wholesaler/api/`
- **Port**: 8000
- **Features**:
  - 5 core endpoints (leads, properties, stats, health)
  - Filtering, sorting, and pagination
  - Pydantic schemas for request/response validation
  - CORS enabled for Streamlit frontend

### Phase 3B: Streamlit Dashboard
- **Location**: `src/wholesaler/frontend/`
- **Port**: 8501
- **Pages**:
  1. **Home (Dashboard)**: Overview stats and tier distribution
  2. **Leads List**: Filterable table with CSV export
  3. **Lead Detail**: Comprehensive property info and score breakdown
  4. **Map View**: Interactive geographic visualization
  5. **Reports**: Analytics charts and statistics

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- **FastAPI** (0.115.0): REST API framework
- **Uvicorn** (0.32.0): ASGI server for FastAPI
- **Streamlit** (1.39.0): Frontend framework
- **Plotly** (5.24.1): Interactive charts
- **PyDeck** (0.9.1): Map visualizations

### 2. Start PostgreSQL

Ensure Docker is running, then start the database:

```bash
docker-compose up -d postgres
```

### 3. Run Database Migrations (Optional)

If the database tables are not created:

```bash
alembic upgrade head
```

*Note: There's currently a known issue with PostGIS spatial indexes. Tables can be created manually if needed.*

## Running the Application

### Step 1: Start the FastAPI Server

```bash
# From project root
python -m src.wholesaler.api.main
```

Or using uvicorn directly:

```bash
uvicorn src.wholesaler.api.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Step 2: Start the Streamlit Dashboard

In a **separate terminal**:

```bash
# From project root
streamlit run src/wholesaler/frontend/app.py
```

The dashboard will open automatically at:
- **Dashboard**: http://localhost:8501

## API Endpoints

### Lead Endpoints

- `GET /api/v1/leads/` - List leads with filtering
  - Query params: `tier`, `min_score`, `max_score`, `city`, `zip_code`, `limit`, `offset`, `sort_by`, `sort_order`
- `GET /api/v1/leads/{parcel_id}` - Get lead detail
- `GET /api/v1/leads/{parcel_id}/history` - Get score history

### Property Endpoints

- `GET /api/v1/properties/{parcel_id}` - Get property detail

### Statistics Endpoints

- `GET /api/v1/stats/dashboard` - Get dashboard statistics

### Health Endpoints

- `GET /health` - Health check
- `GET /` - API root information

## Dashboard Features

###  Home (Dashboard)
- Total leads count
- Tier distribution metrics
- Recent Tier A leads (last 7 days)
- Average scores by tier
- Total properties, tax sales, foreclosures

###  Leads List
- **Filtering**:
  - By tier (A, B, C, D)
  - By score range (0-100)
  - By city
  - By ZIP code
- **Sorting**:
  - By total score (high/low)
  - By date scored (newest/oldest)
  - By address (A-Z)
- **Features**:
  - Paginated results (50 per page)
  - Color-coded tier badges
  - CSV export
  - Tier distribution chart

###  Lead Detail
- Property information table
- Score breakdown chart (distress, value, location, urgency)
- Scoring reasons list
- Tax sale information
- Foreclosure information
- Score history trend chart
- Map location (if coordinates available)

###  Map View
- Interactive map with PyDeck
- Color-coded markers by tier:
  -  Green = Tier A
  -  Blue = Tier B
  -  Yellow = Tier C
  -  Gray = Tier D
- Click markers for lead details
- Filter by tier, score, location
- Multiple map styles (streets, satellite, light, dark)
- Shows up to 500 leads on map

###  Reports
- **Tier Distribution**: Pie chart with percentages
- **Score Distribution**: Histogram by tier
- **Average Scores**: Bar chart by tier
- **Statistical Summary**: Mean, median, standard deviation
- **Recent Activity**: New Tier A leads (last 7 days)
- **Data Quality Metrics**: Coverage percentages

## Testing the Frontend (Without Database)

If the database is not set up yet, you can still test the frontend:

1. Start the FastAPI server (it will show connection errors, but endpoints will work for empty data)
2. Start the Streamlit dashboard
3. You'll see empty states and error messages, but the UI components will render

To fully test the frontend, you'll need:
- PostgreSQL running with PostGIS
- Database tables created (via Alembic or manual SQL)
- Sample data loaded (via ETL pipelines or test data)

## File Structure

```
src/wholesaler/
 api/
    __init__.py
    main.py              # FastAPI app
    dependencies.py      # DB session dependency
    schemas.py           # Pydantic models
    routers/
        __init__.py
        leads.py         # Lead endpoints
        properties.py    # Property endpoints
        stats.py         # Statistics endpoints

 frontend/
     __init__.py
     app.py               # Main Streamlit app (Home)
     pages/
        1__Leads_List.py
        2__Lead_Detail.py
        3__Map_View.py
        4__Reports.py
     components/
        __init__.py
        filters.py       # Filter widgets
        charts.py        # Plotly charts
        tables.py        # Data tables
     utils/
         __init__.py
         api_client.py    # API HTTP client
         formatting.py    # Display formatters
```

## Configuration

### API Settings

Edit `src/wholesaler/config.py` to configure:
- Database connection string
- API host/port
- CORS settings

### Frontend Settings

The frontend automatically connects to:
- API: `http://localhost:8000`
- No additional configuration required

To change the API URL, edit `src/wholesaler/frontend/utils/api_client.py`:

```python
api_client = APIClient(base_url="http://your-api-url:8000")
```

## Troubleshooting

### API won't start
- **Error**: `ModuleNotFoundError: No module named 'fastapi'`
- **Solution**: `pip install fastapi uvicorn`

### Dashboard shows connection errors
- **Error**: `Failed to connect to API`
- **Solution**: Make sure FastAPI is running on port 8000
- **Check**: Visit http://localhost:8000/health

### Empty dashboard (no data)
- **Cause**: Database is empty or not connected
- **Solution**: Run ETL pipelines to populate data, or load test data

### Map not showing
- **Cause**: Leads don't have valid coordinates
- **Solution**: Ensure properties have `latitude` and `longitude` values

### Import errors in frontend
- **Error**: `ModuleNotFoundError: No module named 'streamlit'`
- **Solution**: `pip install streamlit plotly pydeck`

## Next Steps (Phase 3C+)

Future enhancements:
- JWT authentication for API
- Redis caching for frequently accessed data
- ML features (ARV estimation, repair costs, ROI calculator)
- Email/Slack notifications from dashboard
- Export to PDF reports
- Mobile-responsive design
- Real-time updates with WebSockets

## Version

**Phase 3A + 3B**: v0.3.0
- FastAPI REST API with 5 core endpoints
- Streamlit dashboard with 5 pages
- Full CRUD operations for leads and properties
- Interactive charts and map visualizations
