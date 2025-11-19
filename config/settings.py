"""
Configuration Settings

Centralized configuration management using Pydantic and environment variables.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All sensitive values should be stored in .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Socrata API credentials (for code enforcement data)
    socrata_api_key: Optional[str] = None
    socrata_api_secret: Optional[str] = None
    socrata_app_token: Optional[str] = None
    socrata_domain: str = "data.cityoforlando.net"
    socrata_code_violations_dataset: str = "k6e8-nw6w"

    # ArcGIS API settings
    arcgis_base_url: str = "https://services1.arcgis.com/0U8EQ1FrumPeIqDb/arcgis/rest/services/Tax_Sale_Data/FeatureServer/0/query"
    arcgis_foreclosure_url: str = "https://ocgis4.ocfl.net/arcgis/rest/services/Public_Dynamic/MapServer/44/query"
    arcgis_parcels_url: str = "https://ocgis4.ocfl.net/arcgis/rest/services/Public_Dynamic/MapServer/216/query"

    # Geographic settings
    search_radius_miles: float = 0.25
    florida_state_plane_epsg: int = 2881
    wgs84_epsg: int = 4326

    # Data file paths
    code_enforcement_csv: str = "data/code_enforcement_data.csv"

    # Database settings (Phase 2)
    database_url: str = "postgresql+psycopg2://wholesaler_user:wholesaler_pass@localhost:5432/wholesaler"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600
    database_echo: bool = False  # Set to True for SQL query logging

    # Airflow settings (Phase 2)
    airflow_home: Optional[str] = None
    airflow_dags_folder: str = "dags"
    airflow_database_url: str = "postgresql+psycopg2://wholesaler_user:wholesaler_pass@localhost:5432/airflow"

    # Redis settings (Phase 2)
    redis_url: str = "redis://localhost:6379/0"

    # ETL settings (Phase 2)
    etl_batch_size: int = 1000
    etl_enable_incremental: bool = True
    etl_retention_days: int = 365
    etl_max_retries: int = 3
    etl_retry_delay_seconds: int = 60

    # Alert settings (Phase 2)
    alert_email: Optional[str] = None
    alert_slack_webhook: Optional[str] = None
    alert_enable_email: bool = False
    alert_enable_slack: bool = False

    # SMTP settings for email alerts
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_use_tls: bool = True

    # Logging settings
    log_level: str = "INFO"
    log_format: str = "json"

    # Application settings
    environment: str = "development"
    debug: bool = False

    # ML settings
    ml_models_dir: str = "models"
    arv_model_filename: str = "arv_model.joblib"
    lead_model_filename: str = "lead_model.joblib"
    
    # Profitability Guardrails
    profitability_min_profit: float = 15000.0


# Singleton instance
settings = Settings()
