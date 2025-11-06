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

    # Logging settings
    log_level: str = "INFO"
    log_format: str = "json"

    # Application settings
    environment: str = "development"
    debug: bool = False


# Singleton instance
settings = Settings()
