"""
Unit tests for property_scraper module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.wholesaler.scrapers.property_scraper import PropertyScraper
from src.wholesaler.models.property_record import PropertyRecord


class TestPropertyScraper:
    """Tests for PropertyScraper class"""

    def test_scraper_initialization(self):
        """Test that scraper initializes correctly"""
        scraper = PropertyScraper()
        assert scraper.base_url is not None
        assert scraper.session is not None

    def test_scraper_initialization_with_custom_url(self):
        """Test scraper initialization with custom base URL"""
        custom_url = "https://example.com/api"
        scraper = PropertyScraper(base_url=custom_url)
        assert scraper.base_url == custom_url

    @patch('src.wholesaler.scrapers.property_scraper.requests.Session')
    def test_fetch_properties_with_limit(self, mock_session):
        """Test fetching properties with a limit"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "features": [
                {
                    "attributes": {
                        "PARCEL": "123456789",
                        "SITUS": "123 Main St",
                        "NAME1": "John Doe",
                        "TOTAL_MKT": 250000,
                        "TOTAL_ASSD": 250000,
                        "TAXES": 4000,
                        "AYB": 2000,
                        "LIVING_AREA": 1500,
                        "LATITUDE": 28.5,
                        "LONGITUDE": -81.5
                    },
                    "geometry": {
                        "x": -81.5,
                        "y": 28.5
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        scraper = PropertyScraper()
        scraper.session = mock_session_instance

        properties = scraper.fetch_properties(limit=1)

        assert len(properties) == 1
        assert isinstance(properties[0], PropertyRecord)
        assert properties[0].parcel_number == "123456789"

    @patch('src.wholesaler.scrapers.property_scraper.requests.Session')
    def test_fetch_properties_with_parcel_filter(self, mock_session):
        """Test fetching properties with parcel number filter"""
        mock_response = Mock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        scraper = PropertyScraper()
        scraper.session = mock_session_instance

        properties = scraper.fetch_properties(parcel_numbers=["123", "456"])

        call_args = mock_session_instance.get.call_args
        assert "PARCEL IN" in call_args[1]["params"]["where"]

    def test_parse_response_valid_data(self):
        """Test parsing valid response data"""
        scraper = PropertyScraper()

        json_data = {
            "features": [
                {
                    "attributes": {
                        "PARCEL": "987654321",
                        "SITUS": "456 Oak Ave",
                        "NAME1": "Jane Smith",
                        "NAME2": "John Smith",
                        "TOTAL_MKT": 350000,
                        "TOTAL_ASSD": 340000,
                        "TAXABLE": 340000,
                        "TAXES": 5500,
                        "AYB": 1995,
                        "LIVING_AREA": 2000,
                        "ACREAGE": 0.25,
                        "LATITUDE": 28.6,
                        "LONGITUDE": -81.6
                    },
                    "geometry": {
                        "x": -81.6,
                        "y": 28.6
                    }
                }
            ]
        }

        properties = scraper._parse_response(json_data)

        assert len(properties) == 1
        assert properties[0].parcel_number == "987654321"
        assert properties[0].situs_address == "456 OAK AVE"
        assert "Jane Smith / John Smith" in properties[0].owner_name
        assert properties[0].total_mkt == 350000
        assert properties[0].year_built == 1995

    def test_parse_response_year_built_zero(self):
        """Test parsing response with year_built = 0"""
        scraper = PropertyScraper()

        json_data = {
            "features": [
                {
                    "attributes": {
                        "PARCEL": "111222333",
                        "SITUS": "789 Pine St",
                        "NAME1": "Test Owner",
                        "TOTAL_MKT": 100000,
                        "AYB": 0,
                        "LATITUDE": 28.5,
                        "LONGITUDE": -81.5
                    },
                    "geometry": {}
                }
            ]
        }

        properties = scraper._parse_response(json_data)

        assert len(properties) == 1
        assert properties[0].year_built is None

    def test_fetch_by_parcel(self):
        """Test fetching single property by parcel number"""
        scraper = PropertyScraper()

        with patch.object(scraper, 'fetch_properties') as mock_fetch:
            mock_property = PropertyRecord(
                parcel_number="123456",
                situs_address="Test St"
            )
            mock_fetch.return_value = [mock_property]

            result = scraper.fetch_by_parcel("123456")

            assert result is not None
            assert result.parcel_number == "123456"
            mock_fetch.assert_called_once_with(parcel_numbers=["123456"])

    def test_fetch_by_parcel_not_found(self):
        """Test fetching property that doesn't exist"""
        scraper = PropertyScraper()

        with patch.object(scraper, 'fetch_properties') as mock_fetch:
            mock_fetch.return_value = []

            result = scraper.fetch_by_parcel("999999")

            assert result is None

    def test_fetch_properties_api_error(self):
        """Test handling of API errors"""
        import requests

        scraper = PropertyScraper()
        scraper.session = MagicMock()
        scraper.session.get.side_effect = requests.RequestException("API Error")

        properties = scraper.fetch_properties(limit=10)

        assert properties == []

    def test_property_has_coordinates(self):
        """Test has_coordinates method"""
        prop_with_coords = PropertyRecord(
            parcel_number="123",
            latitude=28.5,
            longitude=-81.5
        )
        assert prop_with_coords.has_coordinates() is True

        prop_without_coords = PropertyRecord(
            parcel_number="456"
        )
        assert prop_without_coords.has_coordinates() is False

    def test_property_calculate_equity_percent(self):
        """Test equity percentage calculation"""
        prop = PropertyRecord(
            parcel_number="123",
            total_mkt=300000,
            total_assd=250000
        )

        equity = prop.calculate_equity_percent()
        assert equity == 120.0

    def test_property_calculate_equity_percent_no_data(self):
        """Test equity calculation with missing data"""
        prop = PropertyRecord(parcel_number="123")

        equity = prop.calculate_equity_percent()
        assert equity is None

    def test_property_calculate_tax_rate(self):
        """Test tax rate calculation"""
        prop = PropertyRecord(
            parcel_number="123",
            taxes=5000,
            taxable=250000
        )

        tax_rate = prop.calculate_tax_rate()
        assert tax_rate == 2.0

    def test_property_calculate_tax_rate_no_data(self):
        """Test tax rate calculation with missing data"""
        prop = PropertyRecord(parcel_number="123")

        tax_rate = prop.calculate_tax_rate()
        assert tax_rate is None

    def test_property_to_dict(self):
        """Test to_dict method for backward compatibility"""
        prop = PropertyRecord(
            parcel_number="123456789",
            situs_address="123 Main St",
            owner_name="John Doe",
            total_mkt=250000,
            latitude=28.5,
            longitude=-81.5
        )

        prop_dict = prop.to_dict()

        assert isinstance(prop_dict, dict)
        assert prop_dict["parcel_number"] == "123456789"
        assert prop_dict["total_mkt"] == 250000


@pytest.mark.integration
class TestPropertyScraperIntegration:
    """Integration tests that hit the real API"""

    def test_fetch_real_properties(self):
        """Test fetching from real API (requires internet)"""
        scraper = PropertyScraper()
        properties = scraper.fetch_properties(limit=5)

        assert len(properties) > 0
        assert len(properties) <= 5

        prop = properties[0]
        assert isinstance(prop, PropertyRecord)
        assert prop.parcel_number is not None
