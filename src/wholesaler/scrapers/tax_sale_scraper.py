"""
Tax Sale Property Scraper

Fetches property data from Orlando/Orange County ArcGIS Tax Sale API.
Migrated version with structured logging and configuration management.
"""
import requests
from typing import List, Optional
from pydantic import ValidationError

from config.settings import settings
from src.wholesaler.utils.logger import get_logger
from src.wholesaler.models.property import TaxSaleProperty

logger = get_logger(__name__)


class TaxSaleScraper:
    """
    Scraper for tax sale property data from ArcGIS REST API.

    Uses structured logging and centralized configuration for production readiness.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the tax sale scraper.

        Args:
            base_url: Override the default API URL (for testing)
        """
        self.base_url = base_url or settings.arcgis_base_url
        self.session = requests.Session()
        logger.info("tax_sale_scraper_initialized", base_url=self.base_url)

    def fetch_properties(self, limit: Optional[int] = None) -> List[TaxSaleProperty]:
        """
        Fetch tax sale properties from ArcGIS API.

        Args:
            limit: Maximum number of properties to fetch (None for all)

        Returns:
            List of validated TaxSaleProperty instances
        """
        logger.info(
            "fetching_tax_sale_properties",
            limit=limit if limit else "all"
        )

        params = {
            "where": "1=1",
            "outFields": "USER_TDA_NUM,USER_Sale_Date,USER_Deed_Status,USER_PARCEL",
            "outSR": 4326,
            "f": "geojson"
        }

        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            geojson_data = response.json()

            logger.info(
                "api_request_successful",
                status_code=response.status_code,
                features_count=len(geojson_data.get("features", []))
            )

        except requests.RequestException as e:
            logger.error(
                "api_request_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return []

        properties = self._parse_geojson(geojson_data)

        if limit:
            properties = properties[:limit]
            logger.info("properties_limited", total=len(properties), limit=limit)

        logger.info(
            "fetch_complete",
            total_properties=len(properties),
            with_coordinates=sum(1 for p in properties if p.has_coordinates())
        )

        return properties

    def _parse_geojson(self, geojson_data: dict) -> List[TaxSaleProperty]:
        """
        Parse GeoJSON response into validated TaxSaleProperty instances.

        Args:
            geojson_data: Raw GeoJSON response from API

        Returns:
            List of validated property records
        """
        properties = []
        validation_errors = 0

        for idx, feature in enumerate(geojson_data.get("features", [])):
            try:
                attrs = feature.get("properties", {}) or feature.get("attributes", {})
                geometry = feature.get("geometry", {})

                lon, lat = None, None
                if isinstance(geometry, dict) and "coordinates" in geometry:
                    lon, lat = geometry["coordinates"]

                property_data = {
                    "tda_number": attrs.get("USER_TDA_NUM"),
                    "sale_date": attrs.get("USER_Sale_Date"),
                    "deed_status": attrs.get("USER_Deed_Status"),
                    "parcel_id": attrs.get("USER_PARCEL"),
                    "longitude": lon,
                    "latitude": lat
                }

                property_obj = TaxSaleProperty(**property_data)
                properties.append(property_obj)

            except ValidationError as e:
                validation_errors += 1
                logger.warning(
                    "property_validation_failed",
                    feature_index=idx,
                    error=str(e),
                    raw_data=property_data
                )
                continue

        if validation_errors > 0:
            logger.warning(
                "validation_errors_occurred",
                total_errors=validation_errors,
                success_count=len(properties)
            )

        return properties

    def display_properties(self, properties: List[TaxSaleProperty], detailed: bool = True):
        """
        Display properties in a clean, readable format.

        Args:
            properties: List of TaxSaleProperty instances
            detailed: If True, show all fields; if False, show summary
        """
        print(f"\n{'='*80}")
        print(f"TAX SALE PROPERTIES - Total: {len(properties)}")
        print(f"{'='*80}\n")

        for idx, prop in enumerate(properties, 1):
            print(f"[Property {idx}]")
            print(f"  TDA Number:    {prop.tda_number}")
            print(f"  Sale Date:     {prop.sale_date}")
            print(f"  Deed Status:   {prop.deed_status}")
            print(f"  Parcel ID:     {prop.parcel_id}")

            if prop.has_coordinates():
                print(f"  Coordinates:   ({prop.latitude:.6f}, {prop.longitude:.6f})")
            else:
                print(f"  Coordinates:   (None, None)")
            print()

        print(f"{'='*80}\n")


def main():
    """Main execution function - fetch and display 10 properties."""
    from src.wholesaler.utils.logger import setup_logging

    setup_logging()
    logger.info("starting_tax_sale_scraper_main")

    scraper = TaxSaleScraper()
    properties = scraper.fetch_properties(limit=10)

    if properties:
        scraper.display_properties(properties)
        logger.info("main_execution_complete", properties_fetched=len(properties))
    else:
        logger.error("no_properties_fetched")


if __name__ == "__main__":
    main()
