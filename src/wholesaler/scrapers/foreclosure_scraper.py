"""
Foreclosure Property Scraper

Fetches foreclosure data from Orange County ArcGIS Public_Dynamic MapServer.
"""
import requests
from typing import List, Optional
from pydantic import ValidationError

from config.settings import settings
from src.wholesaler.utils.logger import get_logger
from src.wholesaler.models.foreclosure import ForeclosureProperty

logger = get_logger(__name__)


class ForeclosureScraper:
    """
    Scraper for foreclosure property data from Orange County ArcGIS REST API.

    Fetches lis pendens and foreclosure auction data from the Public_Dynamic
    MapServer Layer 44.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the foreclosure scraper.

        Args:
            base_url: Override the default API URL (for testing)
        """
        self.base_url = base_url or settings.arcgis_foreclosure_url
        self.session = requests.Session()
        logger.info("foreclosure_scraper_initialized", base_url=self.base_url)

    def fetch_foreclosures(
        self,
        limit: Optional[int] = None,
        year: Optional[int] = None
    ) -> List[ForeclosureProperty]:
        """
        Fetch foreclosure properties from ArcGIS API.

        Args:
            limit: Maximum number of properties to fetch (None for all)
            year: Filter by specific year (None for all years)

        Returns:
            List of validated ForeclosureProperty instances
        """
        logger.info(
            "fetching_foreclosures",
            limit=limit if limit else "all",
            year=year if year else "all"
        )

        where_clause = "1=1"
        if year:
            where_clause = f"YEAR={year}"

        params = {
            "where": where_clause,
            "outFields": "*",
            "outSR": 4326,
            "f": "json",
            "returnGeometry": "true"
        }

        if limit:
            params["resultRecordCount"] = limit

        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            json_data = response.json()

            logger.info(
                "api_request_successful",
                status_code=response.status_code,
                features_count=len(json_data.get("features", []))
            )

        except requests.RequestException as e:
            logger.error(
                "api_request_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return []

        properties = self._parse_response(json_data)

        logger.info(
            "fetch_complete",
            total_properties=len(properties),
            with_coordinates=sum(1 for p in properties if p.has_coordinates()),
            with_auction_dates=sum(1 for p in properties if p.has_auction_date())
        )

        return properties

    def _parse_response(self, json_data: dict) -> List[ForeclosureProperty]:
        """
        Parse ArcGIS JSON response into validated ForeclosureProperty instances.

        Args:
            json_data: Raw JSON response from API

        Returns:
            List of validated property records
        """
        properties = []
        validation_errors = 0

        for idx, feature in enumerate(json_data.get("features", [])):
            try:
                attrs = feature.get("attributes", {})
                geometry = feature.get("geometry", {})

                lon, lat = None, None
                if geometry:
                    lon = geometry.get("x")
                    lat = geometry.get("y")

                property_data = {
                    "borrowers_name": attrs.get("BORROWERS_NAME"),
                    "situs_address": attrs.get("SITUS_ADDRESS"),
                    "situs_city": attrs.get("SITUS_CITY"),
                    "situs_state": attrs.get("SITUS_STATE"),
                    "situs_zip": attrs.get("SITUS_ZIP"),
                    "situs_county": attrs.get("SITUS_COUNTY"),
                    "transfer_date": self._parse_timestamp(attrs.get("TRANSFER_DATE")),
                    "transfer_amount": attrs.get("TRANSFER_AMOUNT"),
                    "default_amount": attrs.get("DEFAULT_AMOUNT"),
                    "opening_bid": attrs.get("OPENING_BID"),
                    "recording_date": self._parse_timestamp(attrs.get("RECORDING_DATE")),
                    "entered_date": self._parse_timestamp(attrs.get("ENTERED_DATE")),
                    "auction_date": self._parse_timestamp(attrs.get("AUCTION_DATE")),
                    "trustee_name": attrs.get("TRUSTEE_NAME"),
                    "lender_name": attrs.get("LENDER_NAME"),
                    "lender_phone": attrs.get("LENDER_PHONE"),
                    "property_type": attrs.get("PROPERTY_TYPE"),
                    "record_type_description": attrs.get("RECORD_TYPE_DESCRIPTION"),
                    "parcel_number": attrs.get("PARCEL_NUMBER"),
                    "year": attrs.get("YEAR"),
                    "longitude": lon,
                    "latitude": lat
                }

                property_obj = ForeclosureProperty(**property_data)
                properties.append(property_obj)

            except ValidationError as e:
                validation_errors += 1
                logger.warning(
                    "property_validation_failed",
                    feature_index=idx,
                    error=str(e)
                )
                continue

        if validation_errors > 0:
            logger.warning(
                "validation_errors_occurred",
                total_errors=validation_errors,
                success_count=len(properties)
            )

        return properties

    @staticmethod
    def _parse_timestamp(timestamp_ms: Optional[int]) -> Optional[str]:
        """
        Convert ArcGIS timestamp (milliseconds since epoch) to ISO date string.

        Args:
            timestamp_ms: Timestamp in milliseconds

        Returns:
            ISO format date string or None
        """
        if timestamp_ms is None:
            return None

        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None

    def display_foreclosures(
        self,
        properties: List[ForeclosureProperty],
        detailed: bool = True
    ):
        """
        Display foreclosures in a clean, readable format.

        Args:
            properties: List of ForeclosureProperty instances
            detailed: If True, show all fields; if False, show summary
        """
        print(f"\n{'='*80}")
        print(f"FORECLOSURE PROPERTIES - Total: {len(properties)}")
        print(f"{'='*80}\n")

        for idx, prop in enumerate(properties, 1):
            print(f"[Property {idx}]")
            print(f"  Address:        {prop.situs_address}")
            print(f"  City:           {prop.situs_city}, {prop.situs_state} {prop.situs_zip}")
            print(f"  Parcel:         {prop.parcel_number}")
            print(f"  Borrower:       {prop.borrowers_name}")
            print(f"  Property Type:  {prop.property_type}")

            if prop.has_auction_date():
                print(f"  Auction Date:   {prop.auction_date}")

            if prop.opening_bid:
                print(f"  Opening Bid:    ${prop.opening_bid:,.2f}")

            if prop.default_amount:
                print(f"  Default Amt:    ${prop.default_amount:,.2f}")

            print(f"  Lender:         {prop.lender_name}")

            if prop.has_coordinates():
                print(f"  Coordinates:    ({prop.latitude:.6f}, {prop.longitude:.6f})")

            print()

        print(f"{'='*80}\n")


def main():
    """Main execution function - fetch and display foreclosures."""
    from src.wholesaler.utils.logger import setup_logging

    setup_logging()
    logger.info("starting_foreclosure_scraper_main")

    scraper = ForeclosureScraper()
    foreclosures = scraper.fetch_foreclosures(limit=10)

    if foreclosures:
        scraper.display_foreclosures(foreclosures)
        logger.info("main_execution_complete", foreclosures_fetched=len(foreclosures))
    else:
        logger.error("no_foreclosures_fetched")


if __name__ == "__main__":
    main()
