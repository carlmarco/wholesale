.PHONY: help setup start stop restart logs clean dashboard db-migrate db-upgrade test lint train-models scrape-data score-leads

# Default target
.DEFAULT_GOAL := help

# Colors for terminal output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

##@ General

help: ## Display this help message
	@echo "$(GREEN)Wholesaler Lead Management System$(NC)"
	@echo ""
	@echo "$(BLUE)Available targets:$(NC)"
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup & Installation

setup: ## Initial project setup (install dependencies, create .env)
	@echo "$(GREEN)Setting up Wholesaler Lead Management System...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env file from template...$(NC)"; \
		cp .env.example .env; \
		echo "$(GREEN)✓ .env file created$(NC)"; \
		echo "$(YELLOW)⚠ Please edit .env and add your API credentials$(NC)"; \
	else \
		echo "$(GREEN)✓ .env file already exists$(NC)"; \
	fi
	@echo "$(YELLOW)Installing Python dependencies...$(NC)"
	@python3 -m venv .venv
	@.venv/bin/pip install --upgrade pip
	@.venv/bin/pip install -r requirements.txt
	@echo "$(GREEN)✓ Python dependencies installed$(NC)"
	@echo "$(YELLOW)Creating models directory...$(NC)"
	@mkdir -p models
	@echo "$(GREEN)✓ Setup complete!$(NC)"
	@echo ""
	@echo "$(BLUE)Next steps:$(NC)"
	@echo "  1. Edit .env file with your credentials"
	@echo "  2. Run 'make start' to launch the system"

##@ Docker Operations

start: ## Start all services (database, Airflow, dashboard)
	@echo "$(GREEN)Starting Wholesaler system...$(NC)"
	@docker-compose up -d
	@echo "$(GREEN)✓ All services started!$(NC)"
	@echo ""
	@echo "$(BLUE)Service URLs:$(NC)"
	@echo "  Dashboard:    $(YELLOW)http://localhost:8501$(NC)"
	@echo "  Airflow UI:   $(YELLOW)http://localhost:8080$(NC) (admin/admin)"
	@echo "  PostgreSQL:   $(YELLOW)localhost:5432$(NC) (wholesaler_user/wholesaler_pass)"
	@echo "  Redis:        $(YELLOW)localhost:6379$(NC)"
	@echo ""
	@echo "$(YELLOW)Waiting for services to be ready...$(NC)"
	@sleep 10
	@docker-compose ps

stop: ## Stop all services
	@echo "$(YELLOW)Stopping Wholesaler system...$(NC)"
	@docker-compose down
	@echo "$(GREEN)✓ All services stopped$(NC)"

restart: ## Restart all services
	@echo "$(YELLOW)Restarting Wholesaler system...$(NC)"
	@docker-compose restart
	@echo "$(GREEN)✓ All services restarted$(NC)"

##@ Dashboard

dashboard: ## Launch the dashboard (builds and starts all services)
	@echo "$(GREEN)Building and starting Wholesaler system...$(NC)"
	@docker-compose up -d --build api dashboard
	@echo "$(GREEN)✓ Dashboard services started!$(NC)"
	@echo ""
	@echo "$(BLUE)Service URLs:$(NC)"
	@echo "  Dashboard:    $(YELLOW)http://localhost:8501$(NC)"
	@echo "  API:          $(YELLOW)http://localhost:8000/docs$(NC)"
	@echo ""
	@echo "$(YELLOW)Waiting for services to be ready...$(NC)"
	@sleep 5
	@docker-compose ps api dashboard
	@echo ""
	@echo "$(GREEN)Dashboard is ready! Open http://localhost:8501$(NC)"

dashboard-dev: ## Run dashboard in development mode (hot reload)
	@echo "$(GREEN)Starting dashboard in development mode...$(NC)"
	@.venv/bin/streamlit run src/wholesaler/dashboard/app.py --server.port=8501

##@ Database

db-shell: ## Open PostgreSQL shell
	@docker exec -it wholesaler_postgres psql -U wholesaler_user -d wholesaler

db-migrate: ## Create new database migration
	@echo "$(YELLOW)Creating new migration...$(NC)"
	@read -p "Migration message: " msg; \
	.venv/bin/alembic revision --autogenerate -m "$$msg"
	@echo "$(GREEN)✓ Migration created$(NC)"

db-upgrade: ## Run database migrations
	@echo "$(YELLOW)Running database migrations...$(NC)"
	@.venv/bin/alembic upgrade head
	@echo "$(GREEN)✓ Database upgraded$(NC)"

db-downgrade: ## Rollback last migration
	@echo "$(YELLOW)Rolling back last migration...$(NC)"
	@.venv/bin/alembic downgrade -1
	@echo "$(GREEN)✓ Migration rolled back$(NC)"

db-reset: ## Reset database (WARNING: destroys all data)
	@echo "$(RED)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker-compose down -v; \
		docker-compose up -d wholesaler_postgres; \
		sleep 5; \
		.venv/bin/alembic upgrade head; \
		echo "$(GREEN)✓ Database reset complete$(NC)"; \
	else \
		echo "$(YELLOW)Aborted$(NC)"; \
	fi

##@ Data Pipeline

scrape-data: ## Download fresh data from APIs
	@echo "$(YELLOW)Downloading fresh data from APIs...$(NC)"
	@.venv/bin/python scripts/download_complete_data.py
	@echo "$(GREEN)✓ Data downloaded$(NC)"

load-data: ## Load downloaded data into database
	@echo "$(YELLOW)Loading data into database...$(NC)"
	@.venv/bin/python scripts/load_complete_data.py
	@echo "$(GREEN)✓ Data loaded$(NC)"

score-leads: ## Run lead scoring on all properties
	@echo "$(YELLOW)Scoring leads...$(NC)"
	@.venv/bin/python scripts/run_lead_scoring.py
	@echo "$(GREEN)✓ Lead scoring complete$(NC)"

pipeline-full: scrape-data load-data score-leads ## Run complete pipeline (scrape → load → score)
	@echo "$(GREEN)✓ Full pipeline complete!$(NC)"

##@ Machine Learning

train-models: ## Train ARV and lead qualification models
	@echo "$(YELLOW)Training ML models...$(NC)"
	@bash scripts/train_models.sh
	@echo "$(GREEN)✓ Model training complete$(NC)"
	@ls -lh models/*.joblib

##@ Airflow

airflow-trigger-all: ## Trigger all Airflow DAGs manually
	@echo "$(YELLOW)Triggering all Airflow DAGs...$(NC)"
	@docker exec wholesaler_airflow_scheduler airflow dags trigger daily_property_ingestion
	@docker exec wholesaler_airflow_scheduler airflow dags trigger daily_transformation_pipeline
	@docker exec wholesaler_airflow_scheduler airflow dags trigger daily_lead_scoring
	@docker exec wholesaler_airflow_scheduler airflow dags trigger tier_a_alert_notifications
	@docker exec wholesaler_airflow_scheduler airflow dags trigger data_quality_checks
	@echo "$(GREEN)✓ All DAGs triggered$(NC)"
	@echo "$(BLUE)Monitor progress at http://localhost:8080$(NC)"

airflow-list: ## List all Airflow DAGs
	@docker exec wholesaler_airflow_scheduler airflow dags list

airflow-unpause: ## Unpause all DAGs (enable automatic scheduling)
	@echo "$(YELLOW)Unpausing all DAGs...$(NC)"
	@docker exec wholesaler_airflow_scheduler airflow dags unpause daily_property_ingestion
	@docker exec wholesaler_airflow_scheduler airflow dags unpause daily_transformation_pipeline
	@docker exec wholesaler_airflow_scheduler airflow dags unpause daily_lead_scoring
	@docker exec wholesaler_airflow_scheduler airflow dags unpause tier_a_alert_notifications
	@docker exec wholesaler_airflow_scheduler airflow dags unpause data_quality_checks
	@echo "$(GREEN)✓ All DAGs unpaused - automatic scheduling enabled$(NC)"

##@ Logs

logs: ## View logs from all services
	@docker-compose logs -f

logs-dashboard: ## View dashboard logs
	@docker-compose logs -f dashboard

logs-airflow: ## View Airflow scheduler logs
	@docker-compose logs -f airflow_scheduler

logs-db: ## View database logs
	@docker-compose logs -f wholesaler_postgres

##@ Testing

test: ## Run all tests
	@echo "$(YELLOW)Running tests...$(NC)"
	@.venv/bin/pytest tests/ -v
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-cov: ## Run tests with coverage report
	@echo "$(YELLOW)Running tests with coverage...$(NC)"
	@.venv/bin/pytest tests/ -v --cov=src/wholesaler --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated$(NC)"
	@echo "$(BLUE)Open htmlcov/index.html to view detailed report$(NC)"

lint: ## Run code linting
	@echo "$(YELLOW)Running linters...$(NC)"
	@.venv/bin/black src/ tests/ --check
	@.venv/bin/ruff check src/ tests/
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Auto-format code
	@echo "$(YELLOW)Formatting code...$(NC)"
	@.venv/bin/black src/ tests/
	@.venv/bin/ruff check src/ tests/ --fix
	@echo "$(GREEN)✓ Code formatted$(NC)"

##@ Monitoring

status: ## Show status of all services
	@echo "$(BLUE)Service Status:$(NC)"
	@docker-compose ps

health: ## Check health of all services
	@echo "$(BLUE)Health Check:$(NC)"
	@echo ""
	@echo "$(YELLOW)Database:$(NC)"
	@docker exec wholesaler_postgres pg_isready -U wholesaler_user || echo "$(RED)✗ Database not ready$(NC)"
	@echo ""
	@echo "$(YELLOW)Redis:$(NC)"
	@docker exec wholesaler_redis redis-cli ping || echo "$(RED)✗ Redis not ready$(NC)"
	@echo ""
	@echo "$(YELLOW)Airflow Scheduler:$(NC)"
	@docker exec wholesaler_airflow_scheduler airflow version || echo "$(RED)✗ Airflow not ready$(NC)"
	@echo ""
	@echo "$(YELLOW)Dashboard:$(NC)"
	@curl -s http://localhost:8501/_stcore/health > /dev/null && echo "$(GREEN)✓ Dashboard healthy$(NC)" || echo "$(RED)✗ Dashboard not responding$(NC)"

stats: ## Show database statistics
	@echo "$(BLUE)Database Statistics:$(NC)"
	@docker exec wholesaler_postgres psql -U wholesaler_user -d wholesaler -c "\
		SELECT \
			(SELECT COUNT(*) FROM properties) as total_properties, \
			(SELECT COUNT(*) FROM tax_sales) as tax_sales, \
			(SELECT COUNT(*) FROM foreclosures) as foreclosures, \
			(SELECT COUNT(*) FROM lead_scores) as scored_leads, \
			(SELECT COUNT(*) FROM lead_scores WHERE tier='A') as tier_a_leads; \
	"

##@ Cleanup

clean: ## Remove temporary files
	@echo "$(YELLOW)Cleaning temporary files...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf .pytest_cache htmlcov .ruff_cache 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clean-all: clean ## Remove all generated files (models, data, docker volumes)
	@echo "$(RED)WARNING: This will remove all models, data, and docker volumes!$(NC)"
	@read -p "Are you sure? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker-compose down -v; \
		rm -rf models/*.joblib; \
		rm -rf data/test/; \
		echo "$(GREEN)✓ Complete cleanup done$(NC)"; \
	else \
		echo "$(YELLOW)Aborted$(NC)"; \
	fi

##@ Production

prod-deploy: ## Deploy to production (build & start with optimizations)
	@echo "$(GREEN)Deploying to production...$(NC)"
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
	@echo "$(GREEN)✓ Production deployment complete$(NC)"

backup-db: ## Backup PostgreSQL database
	@echo "$(YELLOW)Backing up database...$(NC)"
	@mkdir -p backups
	@docker exec wholesaler_postgres pg_dump -U wholesaler_user wholesaler > backups/wholesaler_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✓ Database backed up to backups/$(NC)"

restore-db: ## Restore database from backup (provide BACKUP_FILE=path/to/backup.sql)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "$(RED)Error: Please specify BACKUP_FILE=path/to/backup.sql$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Restoring database from $(BACKUP_FILE)...$(NC)"
	@docker exec -i wholesaler_postgres psql -U wholesaler_user wholesaler < $(BACKUP_FILE)
	@echo "$(GREEN)✓ Database restored$(NC)"

##@ Development

dev-setup: setup db-upgrade pipeline-full train-models ## Complete development setup
	@echo "$(GREEN)✓ Development environment ready!$(NC)"
	@echo ""
	@echo "$(BLUE)Quick start:$(NC)"
	@echo "  make dashboard  - Launch the dashboard"
	@echo "  make test       - Run tests"
	@echo "  make help       - See all available commands"

shell: ## Open Python shell with project loaded
	@.venv/bin/python

ipython: ## Open IPython shell with project loaded
	@.venv/bin/ipython

##@ Documentation

docs-serve: ## Serve documentation locally
	@echo "$(YELLOW)Serving documentation...$(NC)"
	@echo "$(BLUE)Available documentation:$(NC)"
	@echo "  - README.md"
	@echo "  - ML_TRAINING_GUIDE.md"
	@echo "  - ALERTS_SETUP.md"
	@echo "  - TESTING_GUIDE.md"
	@echo "  - PHASE3C_README.md"
