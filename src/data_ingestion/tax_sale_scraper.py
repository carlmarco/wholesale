"""
Tax Sale Property Scraper
Fetches property data from Orlando/Orange County ArcGIS Tax Sale API
"""
import requests
import json
from typing import List, Dict, Optional
from datetime import datetime


class TaxSaleScraper:
    """Scraper for tax sale property data from ArcGIS REST API"""

    BASE_URL = "https://services1.arcgis.com/0U8EQ1FrumPeIqDb/arcgis/rest/services/Tax_Sale_Data/FeatureServer/0/query"

    def __init__(self):
        self.session = requests.Session()

    def fetch_properties(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch tax sale properties from ArcGIS API

        Args:
            limit: Maximum number of properties to fetch (None for all)

        Returns:
            List of property dictionaries with standardized fields
        """
        params = {
            "where": "1=1",
            "outFields": "USER_TDA_NUM,USER_Sale_Date,USER_Deed_Status,USER_PARCEL",
            "outSR": 4326,  # WGS84 coordinate system
            "f": "geojson"
        }

        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            geojson_data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching data: {e}")
            return []

        properties = self._parse_geojson(geojson_data)

        if limit:
            properties = properties[:limit]

        return properties

    def _parse_geojson(self, geojson_data: Dict) -> List[Dict]:
        """
        Parse GeoJSON response into structured property dictionaries

        Args:
            geojson_data: Raw GeoJSON response from API

        Returns:
            List of cleaned property records
        """
        properties = []

        for feature in geojson_data.get("features", []):
            # Extract attributes/properties
            attrs = feature.get("properties", {}) or feature.get("attributes", {})

            # Extract geometry (coordinates)
            geometry = feature.get("geometry", {})
            lon, lat = None, None
            if isinstance(geometry, dict) and "coordinates" in geometry:
                lon, lat = geometry["coordinates"]

            # Create standardized property record
            property_record = {
                "tda_number": attrs.get("USER_TDA_NUM"),
                "sale_date": attrs.get("USER_Sale_Date"),
                "deed_status": attrs.get("USER_Deed_Status"),
                "parcel_id": attrs.get("USER_PARCEL"),
                "longitude": lon,
                "latitude": lat
            }

            properties.append(property_record)

        return properties

    def display_properties(self, properties: List[Dict], detailed: bool = True):
        """
        Display properties in a clean, readable format

        Args:
            properties: List of property dictionaries
            detailed: If True, show all fields; if False, show summary
        """
        print(f"\n{'='*80}")
        print(f"TAX SALE PROPERTIES - Total: {len(properties)}")
        print(f"{'='*80}\n")

        for idx, prop in enumerate(properties, 1):
            print(f"[Property {idx}]")
            print(f"  TDA Number:    {prop['tda_number']}")
            print(f"  Sale Date:     {prop['sale_date']}")
            print(f"  Deed Status:   {prop['deed_status']}")
            print(f"  Parcel ID:     {prop['parcel_id']}")
            print(f"  Coordinates:   ({prop['latitude']:.6f}, {prop['longitude']:.6f})")
            print()

        print(f"{'='*80}\n")


def main():
    """Main execution function - fetch and display 10 properties"""
    print("Initializing Tax Sale Scraper...")
    scraper = TaxSaleScraper()

    print("Fetching 10 tax sale properties...")
    properties = scraper.fetch_properties(limit=10)

    if properties:
        scraper.display_properties(properties)

        # Also show as JSON for verification
        print("\nJSON Format (first property):")
        print(json.dumps(properties[0], indent=2))
    else:
        print("No properties fetched. Check API connection.")


if __name__ == "__main__":
    main()
