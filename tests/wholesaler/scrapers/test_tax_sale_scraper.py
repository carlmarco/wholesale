"""
Unit tests for migrated tax_sale_scraper module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.wholesaler.scrapers.tax_sale_scraper import TaxSaleScraper
from src.wholesaler.models.property import TaxSaleProperty


class TestTaxSaleScraper:
    """Tests for migrated TaxSaleScraper class"""

    def test_scraper_initialization(self):
        """Test that scraper initializes correctly with config"""
        scraper = TaxSaleScraper()
        assert scraper.base_url is not None
        assert scraper.session is not None

    def test_scraper_initialization_with_custom_url(self):
        """Test scraper initialization with custom base URL"""
        custom_url = "https://example.com/api"
        scraper = TaxSaleScraper(base_url=custom_url)
        assert scraper.base_url == custom_url

    @patch('src.wholesaler.scrapers.tax_sale_scraper.requests.Session')
    def test_fetch_properties_with_limit(self, mock_session):
        """Test fetching properties with a limit"""
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

        properties = scraper.fetch_properties(limit=1)

        assert len(properties) == 1
        assert isinstance(properties[0], TaxSaleProperty)
        assert properties[0].tda_number == "2023-1234"

    @patch('src.wholesaler.scrapers.tax_sale_scraper.requests.Session')
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
        assert isinstance(properties[0], TaxSaleProperty)

    def test_parse_geojson_valid_data(self):
        """Test parsing valid GeoJSON data returns TaxSaleProperty instances"""
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
        assert isinstance(properties[0], TaxSaleProperty)
        assert properties[0].tda_number == "2023-1234"
        assert properties[0].sale_date == "12/18/2025"
        assert properties[0].deed_status == "Active Sale"
        assert properties[0].parcel_id == "12-34-56-7890-12-345"
        assert properties[0].longitude == -81.5
        assert properties[0].latitude == 28.5

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
        assert properties[0].longitude is None
        assert properties[0].latitude is None
        assert not properties[0].has_coordinates()

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
        assert properties[0].tda_number == "2023-1234"

    def test_property_has_coordinates(self):
        """Test has_coordinates method on TaxSaleProperty"""
        prop_with_coords = TaxSaleProperty(
            tda_number="2023-1234",
            latitude=28.5,
            longitude=-81.5
        )
        assert prop_with_coords.has_coordinates() is True

        prop_without_coords = TaxSaleProperty(
            tda_number="2023-5678",
            latitude=None,
            longitude=None
        )
        assert prop_without_coords.has_coordinates() is False

    def test_property_to_dict(self):
        """Test to_dict method for backward compatibility"""
        prop = TaxSaleProperty(
            tda_number="2023-1234",
            sale_date="12/18/2025",
            deed_status="Active Sale",
            parcel_id="12-34-56-7890-12-345",
            latitude=28.5,
            longitude=-81.5
        )

        prop_dict = prop.to_dict()

        assert isinstance(prop_dict, dict)
        assert prop_dict["tda_number"] == "2023-1234"
        assert prop_dict["latitude"] == 28.5
        assert prop_dict["longitude"] == -81.5


@pytest.mark.integration
class TestTaxSaleScraperIntegration:
    """Integration tests that hit the real API"""

    def test_fetch_real_properties(self):
        """Test fetching from real API (requires internet)"""
        scraper = TaxSaleScraper()
        properties = scraper.fetch_properties(limit=5)

        assert len(properties) > 0
        assert len(properties) <= 5

        prop = properties[0]
        assert isinstance(prop, TaxSaleProperty)
        assert prop.tda_number is not None
        assert prop.sale_date is not None
        assert prop.deed_status is not None
        assert prop.parcel_id is not None
