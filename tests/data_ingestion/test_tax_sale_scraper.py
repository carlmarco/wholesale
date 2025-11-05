"""
Unit tests for tax_sale_scraper module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.data_ingestion.tax_sale_scraper import TaxSaleScraper


class TestTaxSaleScraper:
    """Tests for TaxSaleScraper class"""

    def test_scraper_initialization(self):
        """Test that scraper initializes correctly"""
        scraper = TaxSaleScraper()
        assert scraper.BASE_URL == "https://services1.arcgis.com/0U8EQ1FrumPeIqDb/arcgis/rest/services/Tax_Sale_Data/FeatureServer/0/query"
        assert scraper.session is not None

    @patch('src.data_ingestion.tax_sale_scraper.requests.Session')
    def test_fetch_properties_with_limit(self, mock_session):
        """Test fetching properties with a limit"""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "USER_TDA_NUM": "2023-1234",
                        "USER_Sale_Date": "12/18/2025",
                        "USER_Deed_Status": "Active Sale",
                        "USER_PARCEL": "12-34-56-7890-12-345"
                    },
                    "geometry": {
                        "coordinates": [-81.5, 28.5]
                    }
                },
                {
                    "properties": {
                        "USER_TDA_NUM": "2023-5678",
                        "USER_Sale_Date": "12/18/2025",
                        "USER_Deed_Status": "Active Sale",
                        "USER_PARCEL": "12-34-56-7890-12-346"
                    },
                    "geometry": {
                        "coordinates": [-81.6, 28.6]
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        scraper = TaxSaleScraper()
        scraper.session = mock_session_instance

        # Fetch with limit of 1
        properties = scraper.fetch_properties(limit=1)

        assert len(properties) == 1
        assert properties[0]['tda_number'] == "2023-1234"

    @patch('src.data_ingestion.tax_sale_scraper.requests.Session')
    def test_fetch_properties_without_limit(self, mock_session):
        """Test fetching all properties without limit"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "USER_TDA_NUM": "2023-1234",
                        "USER_Sale_Date": "12/18/2025",
                        "USER_Deed_Status": "Active Sale",
                        "USER_PARCEL": "12-34-56-7890-12-345"
                    },
                    "geometry": {
                        "coordinates": [-81.5, 28.5]
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        scraper = TaxSaleScraper()
        scraper.session = mock_session_instance

        properties = scraper.fetch_properties(limit=None)

        assert len(properties) == 1

    def test_parse_geojson_valid_data(self):
        """Test parsing valid GeoJSON data"""
        scraper = TaxSaleScraper()

        geojson_data = {
            "features": [
                {
                    "properties": {
                        "USER_TDA_NUM": "2023-1234",
                        "USER_Sale_Date": "12/18/2025",
                        "USER_Deed_Status": "Active Sale",
                        "USER_PARCEL": "12-34-56-7890-12-345"
                    },
                    "geometry": {
                        "coordinates": [-81.5, 28.5]
                    }
                }
            ]
        }

        properties = scraper._parse_geojson(geojson_data)

        assert len(properties) == 1
        assert properties[0]['tda_number'] == "2023-1234"
        assert properties[0]['sale_date'] == "12/18/2025"
        assert properties[0]['deed_status'] == "Active Sale"
        assert properties[0]['parcel_id'] == "12-34-56-7890-12-345"
        assert properties[0]['longitude'] == -81.5
        assert properties[0]['latitude'] == 28.5

    def test_parse_geojson_missing_geometry(self):
        """Test parsing GeoJSON with missing geometry"""
        scraper = TaxSaleScraper()

        geojson_data = {
            "features": [
                {
                    "properties": {
                        "USER_TDA_NUM": "2023-1234",
                        "USER_Sale_Date": "12/18/2025",
                        "USER_Deed_Status": "Active Sale",
                        "USER_PARCEL": "12-34-56-7890-12-345"
                    },
                    "geometry": {}
                }
            ]
        }

        properties = scraper._parse_geojson(geojson_data)

        assert len(properties) == 1
        assert properties[0]['longitude'] is None
        assert properties[0]['latitude'] is None

    def test_parse_geojson_empty_features(self):
        """Test parsing GeoJSON with no features"""
        scraper = TaxSaleScraper()

        geojson_data = {"features": []}

        properties = scraper._parse_geojson(geojson_data)

        assert len(properties) == 0

    def test_fetch_properties_api_error(self):
        """Test handling of API errors"""
        import requests

        scraper = TaxSaleScraper()

        # Mock the session to raise a requests.RequestException
        scraper.session = MagicMock()
        scraper.session.get.side_effect = requests.RequestException("API Error")

        properties = scraper.fetch_properties(limit=10)

        assert properties == []

    def test_parse_geojson_with_attributes_key(self):
        """Test parsing GeoJSON that uses 'attributes' instead of 'properties'"""
        scraper = TaxSaleScraper()

        geojson_data = {
            "features": [
                {
                    "attributes": {
                        "USER_TDA_NUM": "2023-1234",
                        "USER_Sale_Date": "12/18/2025",
                        "USER_Deed_Status": "Active Sale",
                        "USER_PARCEL": "12-34-56-7890-12-345"
                    },
                    "geometry": {
                        "coordinates": [-81.5, 28.5]
                    }
                }
            ]
        }

        properties = scraper._parse_geojson(geojson_data)

        assert len(properties) == 1
        assert properties[0]['tda_number'] == "2023-1234"


@pytest.mark.integration
class TestTaxSaleScraperIntegration:
    """Integration tests that hit the real API"""

    def test_fetch_real_properties(self):
        """Test fetching from real API (requires internet)"""
        scraper = TaxSaleScraper()
        properties = scraper.fetch_properties(limit=5)

        # Should get at least 1 property
        assert len(properties) > 0
        assert len(properties) <= 5

        # Verify structure
        prop = properties[0]
        assert 'tda_number' in prop
        assert 'sale_date' in prop
        assert 'deed_status' in prop
        assert 'parcel_id' in prop
        assert 'longitude' in prop
        assert 'latitude' in prop
