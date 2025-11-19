# Streamlit Cloud Deployment Guide

This guide covers deploying the Wholesaler Dashboard to Streamlit Cloud without Docker.

## Prerequisites

1. **GitHub Repository**: Code must be in a GitHub repository
2. **Streamlit Cloud Account**: Sign up at [streamlit.io/cloud](https://streamlit.io/cloud)
3. **Backend API**: Deploy FastAPI backend separately (Heroku, Railway, Render, etc.)

## Architecture

```
┌─────────────────────┐
│  Streamlit Cloud    │
│  (Dashboard UI)     │ ──HTTP──> │  FastAPI Backend  │
│  Port: 8501         │           │  (API Server)     │
└─────────────────────┘           │  Port: 8000       │
                                  └───────────────────┘
                                           │
                                           ▼
                                  ┌───────────────────┐
                                  │   PostgreSQL DB   │
                                  │   + Redis Cache   │
                                  └───────────────────┘
```

## Step 1: Deploy FastAPI Backend

Before deploying the dashboard, deploy the FastAPI backend to a cloud provider:

### Option A: Railway.app (Recommended)

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Create new project
railway init

# Add PostgreSQL and Redis
railway add --service postgresql
railway add --service redis

# Set environment variables
railway vars set DATABASE_URL=<postgres-url>
railway vars set REDIS_URL=<redis-url>

# Deploy API
railway up
```

### Option B: Render.com

1. Connect GitHub repository to Render
2. Create new Web Service
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn src.wholesaler.api.main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL and Redis services
6. Set environment variables in Render dashboard

### Option C: Heroku

```bash
# Install Heroku CLI
brew install heroku/brew/heroku  # macOS

# Login
heroku login

# Create app
heroku create wholesaler-api

# Add PostgreSQL and Redis
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# Set environment variables
heroku config:set SOCRATA_API_KEY=xxx
heroku config:set SOCRATA_API_SECRET=xxx

# Deploy
git push heroku main
```

**Note the API URL** (e.g., `https://wholesaler-api.railway.app`) - you'll need this for Step 3.

## Step 2: Configure Streamlit Cloud

### 2.1 Connect Repository

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select your GitHub repository: `carlmarco/wholesaler`
4. Set main file path: `src/wholesaler/frontend/app.py`
5. Choose branch: `main`

### 2.2 Configure App Settings

In the Streamlit Cloud dashboard:

**Advanced Settings**:
- Python version: `3.13`
- Main file path: `src/wholesaler/frontend/app.py`

### 2.3 Add Secrets

Click "Advanced settings" → "Secrets" and paste:

```toml
# API Configuration
API_BASE_URL = "https://your-api-url.railway.app"  # Replace with your API URL

# Database (if direct access needed)
[connections.postgresql]
dialect = "postgresql"
host = "your-db-host.railway.app"
port = 5432
database = "railway"
username = "postgres"
password = "your-db-password"

# Optional: Socrata credentials (if dashboard makes direct API calls)
[socrata]
api_key = "your_api_key"
api_secret = "your_api_secret"
app_token = "your_app_token"
```

## Step 3: Deploy Dashboard

1. Click "Deploy!" in Streamlit Cloud
2. Wait for build to complete (2-5 minutes)
3. Your dashboard will be live at: `https://<app-name>.streamlit.app`

## Step 4: Test Deployment

Visit your Streamlit Cloud URL and verify:

1. ✅ Dashboard loads without errors
2. ✅ API connection successful (check lead data loads)
3. ✅ All pages accessible (Lead Browser, Analytics, etc.)
4. ✅ Filters and search work correctly

## Troubleshooting

### Issue: "Cannot connect to API"

**Solution**: Verify `API_BASE_URL` in Streamlit secrets:

```python
# In src/wholesaler/frontend/utils/api_client.py
import streamlit as st

# Should read from secrets in production
api_url = st.secrets.get("API_BASE_URL", "http://localhost:8000")
```

### Issue: "Module not found" errors

**Solution**: Check dependencies are in `requirements.txt`:

```bash
# For Streamlit Cloud, use requirements-streamlit.txt (lighter)
# Rename it to requirements.txt or update Streamlit Cloud settings
```

### Issue: Database connection timeout

**Solution**: Streamlit Cloud has limited database connection pooling:

```python
# Use connection pooling wisely
@st.cache_resource
def get_db_connection():
    return create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
```

### Issue: Geospatial library errors (pyproj)

**Solution**: System dependencies are defined in `packages.txt`:

```txt
libgdal-dev
libgeos-dev
proj-bin
```

Streamlit Cloud automatically installs these before Python packages.

## GitHub Actions Integration

The CI/CD pipeline (`.github/workflows/ci.yml`) automatically:

1. ✅ Runs tests on every push
2. ✅ Validates API health
3. ✅ Checks Streamlit syntax
4. ✅ Runs code quality checks

**Note**: Streamlit Cloud auto-deploys when you push to `main` branch.

## Environment Variables

### Required for API Backend

```env
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0
SOCRATA_API_KEY=xxx
SOCRATA_API_SECRET=xxx
SOCRATA_APP_TOKEN=xxx
```

### Required for Streamlit Dashboard

```toml
API_BASE_URL = "https://your-api.com"
```

## Performance Optimization

### 1. Use Streamlit Caching

```python
@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_leads():
    return api_client.get("/api/v1/leads")
```

### 2. Lazy Load Pages

```python
# Only import page modules when accessed
if selected_page == "Lead Detail":
    from pages import lead_detail
    lead_detail.render()
```

### 3. Reduce Database Queries

```python
# Fetch once, filter in memory
@st.cache_data(ttl=600)
def get_all_leads():
    return api_client.get("/api/v1/leads?limit=1000")

# Client-side filtering
filtered = [l for l in leads if l['tier'] == 'A']
```

## Monitoring

### Streamlit Cloud Metrics

Available in Streamlit Cloud dashboard:
- App uptime
- Resource usage (RAM, CPU)
- Error logs
- Request count

### Custom Logging

```python
import structlog

logger = structlog.get_logger()

# Logs appear in Streamlit Cloud logs
logger.info("lead_loaded", parcel_id=parcel_id, tier=tier)
```

## Cost Estimation

### Streamlit Cloud
- **Free Tier**: 1 app, public, community support
- **Starter**: $20/month, 1 private app
- **Teams**: $250/month, unlimited apps

### API Backend (Railway.app)
- **Starter**: $5/month (500 hours)
- **Pro**: $20/month (unlimited)
- **PostgreSQL**: $5-10/month
- **Redis**: $3-5/month

**Total Monthly Cost**: ~$25-50 for production deployment

## Security Considerations

1. **Never commit secrets**: Use `.streamlit/secrets.toml` (gitignored)
2. **API Authentication**: Implement JWT tokens for API access
3. **CORS Configuration**: Only allow Streamlit Cloud domain
4. **Database**: Use SSL for database connections
5. **Environment Variables**: Store sensitive data in Streamlit secrets

## Alternative: Self-Hosted Deployment

If Streamlit Cloud doesn't fit your needs:

### Docker Compose (Full Stack)

```bash
# Use existing docker-compose.yml
docker-compose up -d

# Access dashboard at http://localhost:8501
```

### Kubernetes (Production)

See `k8s/` directory for Kubernetes manifests (if available)

## Support

- **Streamlit Docs**: [docs.streamlit.io](https://docs.streamlit.io)
- **Railway Docs**: [docs.railway.app](https://docs.railway.app)
- **GitHub Actions**: [docs.github.com/actions](https://docs.github.com/actions)

## Next Steps

1. ✅ Deploy API backend to Railway/Render/Heroku
2. ✅ Note the API URL
3. ✅ Configure Streamlit Cloud with GitHub repo
4. ✅ Add secrets (API_BASE_URL, database credentials)
5. ✅ Deploy and test
6. 📧 Set up email alerts (optional)
7. 📊 Configure monitoring (optional)

---

**Last Updated**: November 19, 2025
**Maintained By**: Carl Marco
