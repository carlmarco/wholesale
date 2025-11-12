"""
Property Records Scraper

Fetches property parcel data from Orange County Property Appraiser ArcGIS API.
"""
import requests
from typing import List, Optional
from pydantic import ValidationError

from config.settings import settings
from src.wholesaler.utils.logger import get_logger
from src.wholesaler.models.property_record import PropertyRecord

logger = get_logger(__name__)


class PropertyScraper:
    """
    Scraper for property parcel data from Orange County Property Appraiser.

    Fetches parcel information including ownership, valuations, and tax data
    from the Public_Dynamic MapServer Layer 216.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the property scraper.

        Args:
            base_url: Override the default API URL (for testing)
        """
        self.base_url = base_url or settings.arcgis_parcels_url
        self.session = requests.Session()
        logger.info("property_scraper_initialized", base_url=self.base_url)

    def fetch_properties(
        self,
        limit: Optional[int] = None,
        parcel_numbers: Optional[List[str]] = None,
        bbox: Optional[tuple] = None
    ) -> List[PropertyRecord]:
        """
        Fetch property records from ArcGIS API.

        Args:
            limit: Maximum number of properties to fetch (None for all)
            parcel_numbers: List of specific parcel numbers to fetch
            bbox: Bounding box tuple (xmin, ymin, xmax, ymax) for spatial filter

        Returns:
            List of validated PropertyRecord instances
        """
        logger.info(
            "fetching_properties",
            limit=limit if limit else "all",
            parcel_filter=len(parcel_numbers) if parcel_numbers else "none",
            spatial_filter="bbox" if bbox else "none"
        )

        # If parcel list is large, chunk into smaller batches to avoid 403 errors
        if parcel_numbers and len(parcel_numbers) > 25:
            logger.info("chunking_large_parcel_list", total=len(parcel_numbers), chunk_size=25)
            all_properties = []
            for i in range(0, len(parcel_numbers), 25):
                chunk = parcel_numbers[i:i + 25]
                logger.info("fetching_chunk", chunk_num=i//25 + 1, chunk_size=len(chunk))
                chunk_properties = self._fetch_batch(chunk, bbox, None)
                all_properties.extend(chunk_properties)
                # Small delay to avoid rate limiting
                import time
                time.sleep(0.5)

            logger.info(
                "fetch_complete",
                total_properties=len(all_properties),
                with_coordinates=sum(1 for p in all_properties if p.has_coordinates()),
                with_valuations=sum(1 for p in all_properties if p.total_mkt)
            )
            return all_properties

        return self._fetch_batch(parcel_numbers, bbox, limit)

    def _fetch_batch(
        self,
        parcel_numbers: Optional[List[str]] = None,
        bbox: Optional[tuple] = None,
        limit: Optional[int] = None
    ) -> List[PropertyRecord]:
        """
        Fetch a single batch of properties from the API.

        Args:
            parcel_numbers: List of parcel numbers to fetch
            bbox: Bounding box filter
            limit: Result limit

        Returns:
            List of PropertyRecord instances
        """
        where_clause = "1=1"
        if parcel_numbers:
            parcel_list = "','".join(parcel_numbers)
            where_clause = f"PARCEL IN ('{parcel_list}')"

        params = {
            "where": where_clause,
            "outFields": (
                "PARCEL,SITUS,SITUS_CITY,SITUS_ZIP,NAME1,NAME2,"
                "LAND_MKT,BLDG_MKT,XFOB_MKT,TOTAL_MKT,TOTAL_ASSD,TOTAL_XMPT,"
                "TAXABLE,TAXES,LIVING_AREA,ACREAGE,AYB,"
                "BEDS,BATH,POOL,ZONING_CODE,LATITUDE,LONGITUDE"
            ),
            "outSR": 4326,
            "f": "json",
            "returnGeometry": "true"
        }

        if bbox:
            params["geometry"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            params["geometryType"] = "esriGeometryEnvelope"
            params["spatialRel"] = "esriSpatialRelIntersects"

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

        return self._parse_response(json_data)

    def _parse_response(self, json_data: dict) -> List[PropertyRecord]:
        """
        Parse ArcGIS JSON response into validated PropertyRecord instances.

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

                lon = attrs.get("LONGITUDE") or geometry.get("x")
                lat = attrs.get("LATITUDE") or geometry.get("y")

                owner_name = attrs.get("NAME1")
                if attrs.get("NAME2"):
                    owner_name = f"{owner_name} / {attrs.get('NAME2')}"

                property_data = {
                    "parcel_number": attrs.get("PARCEL"),
                    "situs_address": attrs.get("SITUS"),
                    "owner_name": owner_name,
                    "land_mkt": attrs.get("LAND_MKT"),
                    "bldg_mkt": attrs.get("BLDG_MKT"),
                    "xfob_mkt": attrs.get("XFOB_MKT"),
                    "total_mkt": attrs.get("TOTAL_MKT"),
                    "total_assd": attrs.get("TOTAL_ASSD"),
                    "total_xmpt": attrs.get("TOTAL_XMPT"),
                    "taxable": attrs.get("TAXABLE"),
                    "taxes": attrs.get("TAXES"),
                    "exempt_code": None,
                    "property_use": attrs.get("ZONING_CODE"),
                    "year_built": attrs.get("AYB"),
                    "living_area": attrs.get("LIVING_AREA"),
                    "lot_size": attrs.get("ACREAGE"),
                    "longitude": lon,
                    "latitude": lat
                }

                property_obj = PropertyRecord(**property_data)
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

    def fetch_by_parcel(self, parcel_number: str) -> Optional[PropertyRecord]:
        """
        Fetch a single property by parcel number.

        Args:
            parcel_number: County parcel identifier

        Returns:
            PropertyRecord or None if not found
        """
        logger.info("fetching_single_property", parcel_number=parcel_number)

        properties = self.fetch_properties(parcel_numbers=[parcel_number])

        if properties:
            logger.info("property_found", parcel_number=parcel_number)
            return properties[0]
        else:
            logger.warning("property_not_found", parcel_number=parcel_number)
            return None

    def display_properties(
        self,
        properties: List[PropertyRecord],
        detailed: bool = True
    ):
        """
        Display properties in a clean, readable format.

        Args:
            properties: List of PropertyRecord instances
            detailed: If True, show all fields; if False, show summary
        """
        print(f"\n{'='*80}")
        print(f"PROPERTY RECORDS - Total: {len(properties)}")
        print(f"{'='*80}\n")

        for idx, prop in enumerate(properties, 1):
            print(f"[Property {idx}]")
            print(f"  Parcel:         {prop.parcel_number}")
            print(f"  Address:        {prop.situs_address}")
            print(f"  Owner:          {prop.owner_name}")

            if prop.total_mkt:
                print(f"  Market Value:   ${prop.total_mkt:,.0f}")

            if prop.total_assd:
                print(f"  Assessed Value: ${prop.total_assd:,.0f}")

            if prop.taxes:
                print(f"  Annual Taxes:   ${prop.taxes:,.2f}")

            if prop.year_built:
                print(f"  Year Built:     {prop.year_built}")

            if prop.living_area:
                print(f"  Living Area:    {prop.living_area:,.0f} sqft")

            equity_pct = prop.calculate_equity_percent()
            if equity_pct:
                print(f"  Equity:         {equity_pct:.1f}%")

            if prop.has_coordinates():
                print(f"  Coordinates:    ({prop.latitude:.6f}, {prop.longitude:.6f})")

            print()

        print(f"{'='*80}\n")


def main():
    """Main execution function - fetch and display properties."""
    from src.wholesaler.utils.logger import setup_logging

    setup_logging()
    logger.info("starting_property_scraper_main")

    scraper = PropertyScraper()
    properties = scraper.fetch_properties(limit=10)

    if properties:
        scraper.display_properties(properties)
        logger.info("main_execution_complete", properties_fetched=len(properties))
    else:
        logger.error("no_properties_fetched")


if __name__ == "__main__":
    main()
