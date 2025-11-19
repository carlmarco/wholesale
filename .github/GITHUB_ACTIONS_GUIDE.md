# GitHub Actions CI/CD Guide

This document explains the automated CI/CD pipeline configured for the Wholesaler project.

## Overview

The pipeline runs automatically on:
- ✅ **Push to `main` or `develop` branches**
- ✅ **Pull requests to `main` or `develop`**
- ✅ **Manual workflow dispatch** (via GitHub Actions UI)

## Workflow Jobs

### 1. Test (`test`)

**Purpose**: Run all unit tests with code coverage

**What it does**:
- Sets up PostgreSQL and Redis services
- Installs Python 3.13 and dependencies
- Runs database migrations via Alembic
- Executes pytest with coverage reporting
- Uploads coverage reports to Codecov (if configured)

**Duration**: ~3-5 minutes

**Requirements**:
- PostgreSQL 15+
- Redis 7+
- All tests passing (115+ tests)

### 2. API Health Check (`api-health-check`)

**Purpose**: Verify API endpoints are functional

**What it does**:
- Starts FastAPI server on port 8000
- Tests core endpoints:
  - `/health` - Health check
  - `/` - Root endpoint
  - `/docs` - OpenAPI documentation
- Stops server after tests

**Duration**: ~2-3 minutes

**Depends on**: `test` job must pass

### 3. Streamlit Validation (`streamlit-validation`)

**Purpose**: Validate Streamlit dashboard code

**What it does**:
- Syntax checks on `app.py` and all page files
- Validates Streamlit configuration
- Ensures no import errors

**Duration**: ~1-2 minutes

**Depends on**: `test` job must pass

### 4. Code Quality (`lint`)

**Purpose**: Enforce code quality standards

**What it does**:
- Runs `flake8` for syntax errors and undefined names
- Checks code formatting with `black`
- Validates import sorting with `isort`

**Duration**: ~1 minute

**Note**: Currently non-blocking (warnings only)

### 5. Build Summary (`build-summary`)

**Purpose**: Report overall build status

**What it does**:
- Checks results of all previous jobs
- Reports pass/fail for each job
- Fails build if any critical job fails

**Duration**: <30 seconds

**Depends on**: All previous jobs

## Setting Up Secrets

Some features require GitHub secrets to be configured:

### Required Secrets

Navigate to: **Repository → Settings → Secrets and variables → Actions → New repository secret**

1. **`SOCRATA_API_KEY`** (Optional for tests)
   - Socrata API key for code enforcement data
   - Tests will use mock data if not provided

2. **`SOCRATA_API_SECRET`** (Optional for tests)
   - Socrata API secret

3. **`SOCRATA_APP_TOKEN`** (Optional for tests)
   - Socrata app token

### Optional Secrets

4. **`CODECOV_TOKEN`** (Optional)
   - For uploading coverage reports to Codecov
   - Get from [codecov.io](https://codecov.io)

## Viewing Workflow Results

### In Pull Requests

Status checks appear at the bottom of PR:

```
✅ test - All checks have passed
✅ api-health-check - All checks have passed
✅ streamlit-validation - All checks have passed
✅ lint - All checks have passed
```

### In Actions Tab

1. Go to **Actions** tab in GitHub repo
2. Click on specific workflow run
3. View job logs and artifacts

## Manual Triggering

### Via GitHub UI

1. Go to **Actions** tab
2. Select "CI/CD Pipeline" workflow
3. Click "Run workflow" dropdown
4. Select branch (main/develop)
5. Click "Run workflow"

### Via GitHub CLI

```bash
# Install GitHub CLI
brew install gh  # macOS

# Trigger workflow
gh workflow run ci.yml --ref main
```

## Troubleshooting

### ❌ Test Job Failing

**Common Causes**:
- Database migration failed
- Test database connection issues
- Missing dependencies
- Actual test failures

**Solution**:
```bash
# Run tests locally first
make test

# Check database migrations
alembic upgrade head

# View detailed logs in GitHub Actions
```

### ❌ API Health Check Failing

**Common Causes**:
- API server failed to start
- Port 8000 already in use
- Database connection timeout
- Missing environment variables

**Solution**:
```bash
# Test API locally
python -m uvicorn src.wholesaler.api.main:app --port 8000

# Check health endpoint
curl http://localhost:8000/health
```

### ❌ Streamlit Validation Failing

**Common Causes**:
- Syntax errors in `.py` files
- Missing imports
- Invalid Streamlit configuration

**Solution**:
```bash
# Test Streamlit app locally
streamlit run src/wholesaler/frontend/app.py

# Check for syntax errors
python -m py_compile src/wholesaler/frontend/app.py
```

### ❌ Lint Job Failing

**Common Causes**:
- Code formatting issues
- Import sorting problems
- Flake8 violations

**Solution**:
```bash
# Auto-fix formatting
black src/ tests/

# Auto-fix imports
isort src/ tests/

# Check flake8
flake8 src/ tests/
```

## Optimizing Workflow Performance

### Caching

The workflow uses pip caching to speed up dependency installation:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: '3.13'
    cache: 'pip'  # ← Caches pip dependencies
```

### Parallel Execution

Jobs run in parallel when possible:

```
test ──┬──> api-health-check ──┐
       ├──> streamlit-validation┼──> build-summary
       └──> lint ───────────────┘
```

### Skip CI

Add `[skip ci]` to commit message to skip workflow:

```bash
git commit -m "Update README [skip ci]"
```

## Local Testing (Before Push)

Run these commands locally to catch issues before CI:

```bash
# 1. Run all tests
make test

# 2. Check API health
make api-health-check  # (custom target, see Makefile)

# 3. Validate Streamlit
python -m py_compile src/wholesaler/frontend/app.py

# 4. Run linters
make lint
```

## Continuous Deployment

### Streamlit Cloud

When workflow passes on `main` branch:
- Streamlit Cloud automatically deploys the dashboard
- No manual intervention needed

### API Backend

For API deployment, you can extend the workflow:

```yaml
# Example: Deploy to Railway.app after tests pass
deploy-api:
  needs: [test, api-health-check]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Deploy to Railway
      run: |
        npm i -g @railway/cli
        railway up --service api
      env:
        RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

## Workflow Badge

Add to README.md:

```markdown
![CI/CD](https://github.com/carlmarco/wholesaler/workflows/CI%2FCD%20Pipeline/badge.svg)
```

## Cost Considerations

GitHub Actions:
- **Free tier**: 2,000 minutes/month for private repos
- **Public repos**: Unlimited

Current workflow usage per run: ~10-15 minutes

Estimated monthly usage:
- 20 pushes/month × 15 min = 300 minutes
- Well within free tier ✅

## Advanced Configuration

### Matrix Testing

Test multiple Python versions:

```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12', '3.13']
```

### Conditional Jobs

Run jobs only on specific branches:

```yaml
if: github.ref == 'refs/heads/main'
```

### Scheduled Runs

Run workflow on schedule:

```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
```

## Support

- **GitHub Actions Docs**: [docs.github.com/actions](https://docs.github.com/actions)
- **Workflow Syntax**: [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions)

---

**Last Updated**: November 19, 2025
**Maintained By**: Carl Marco
