"""
Unit tests for foreclosure_scraper module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.wholesaler.scrapers.foreclosure_scraper import ForeclosureScraper
from src.wholesaler.models.foreclosure import ForeclosureProperty


class TestForeclosureScraper:
    """Tests for ForeclosureScraper class"""

    def test_scraper_initialization(self):
        """Test that scraper initializes correctly"""
        scraper = ForeclosureScraper()
        assert scraper.base_url is not None
        assert scraper.session is not None

    def test_scraper_initialization_with_custom_url(self):
        """Test scraper initialization with custom base URL"""
        custom_url = "https://example.com/api"
        scraper = ForeclosureScraper(base_url=custom_url)
        assert scraper.base_url == custom_url

    @patch('src.wholesaler.scrapers.foreclosure_scraper.requests.Session')
    def test_fetch_foreclosures_with_limit(self, mock_session):
        """Test fetching foreclosures with a limit"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "features": [
                {
                    "attributes": {
                        "BORROWERS_NAME": "John Doe",
                        "SITUS_ADDRESS": "123 Main St",
                        "SITUS_CITY": "Orlando",
                        "SITUS_STATE": "FL",
                        "SITUS_ZIP": "32801",
                        "PARCEL_NUMBER": "123456789",
                        "PROPERTY_TYPE": "Single Family Residence",
                        "YEAR": 2024
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

        scraper = ForeclosureScraper()
        scraper.session = mock_session_instance

        foreclosures = scraper.fetch_foreclosures(limit=1)

        assert len(foreclosures) == 1
        assert isinstance(foreclosures[0], ForeclosureProperty)
        assert foreclosures[0].borrowers_name == "John Doe"

    @patch('src.wholesaler.scrapers.foreclosure_scraper.requests.Session')
    def test_fetch_foreclosures_with_year_filter(self, mock_session):
        """Test fetching foreclosures with year filter"""
        mock_response = Mock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        scraper = ForeclosureScraper()
        scraper.session = mock_session_instance

        foreclosures = scraper.fetch_foreclosures(year=2024)

        call_args = mock_session_instance.get.call_args
        assert "YEAR=2024" in call_args[1]["params"]["where"]

    def test_parse_response_valid_data(self):
        """Test parsing valid response data"""
        scraper = ForeclosureScraper()

        json_data = {
            "features": [
                {
                    "attributes": {
                        "BORROWERS_NAME": "Jane Smith",
                        "SITUS_ADDRESS": "456 Oak Ave",
                        "SITUS_CITY": "Winter Park",
                        "SITUS_STATE": "FL",
                        "SITUS_ZIP": "32789",
                        "PARCEL_NUMBER": "987654321",
                        "PROPERTY_TYPE": "Condominium",
                        "DEFAULT_AMOUNT": 150000.0,
                        "OPENING_BID": 120000.0,
                        "YEAR": 2024
                    },
                    "geometry": {
                        "x": -81.6,
                        "y": 28.6
                    }
                }
            ]
        }

        foreclosures = scraper._parse_response(json_data)

        assert len(foreclosures) == 1
        assert foreclosures[0].borrowers_name == "Jane Smith"
        assert foreclosures[0].situs_address == "456 OAK AVE"
        assert foreclosures[0].default_amount == 150000.0
        assert foreclosures[0].longitude == -81.6
        assert foreclosures[0].latitude == 28.6

    def test_parse_response_missing_geometry(self):
        """Test parsing response with missing geometry"""
        scraper = ForeclosureScraper()

        json_data = {
            "features": [
                {
                    "attributes": {
                        "BORROWERS_NAME": "Test Person",
                        "PARCEL_NUMBER": "111222333",
                        "YEAR": 2024
                    },
                    "geometry": {}
                }
            ]
        }

        foreclosures = scraper._parse_response(json_data)

        assert len(foreclosures) == 1
        assert foreclosures[0].longitude is None
        assert foreclosures[0].latitude is None
        assert not foreclosures[0].has_coordinates()

    def test_parse_timestamp(self):
        """Test timestamp parsing"""
        timestamp_ms = 1609459200000
        result = ForeclosureScraper._parse_timestamp(timestamp_ms)

        assert result in ["2020-12-31", "2021-01-01"]

    def test_parse_timestamp_none(self):
        """Test timestamp parsing with None"""
        result = ForeclosureScraper._parse_timestamp(None)
        assert result is None

    def test_fetch_foreclosures_api_error(self):
        """Test handling of API errors"""
        import requests

        scraper = ForeclosureScraper()
        scraper.session = MagicMock()
        scraper.session.get.side_effect = requests.RequestException("API Error")

        foreclosures = scraper.fetch_foreclosures(limit=10)

        assert foreclosures == []

    def test_foreclosure_has_coordinates(self):
        """Test has_coordinates method"""
        prop_with_coords = ForeclosureProperty(
            borrowers_name="Test",
            parcel_number="123",
            latitude=28.5,
            longitude=-81.5
        )
        assert prop_with_coords.has_coordinates() is True

        prop_without_coords = ForeclosureProperty(
            borrowers_name="Test",
            parcel_number="456"
        )
        assert prop_without_coords.has_coordinates() is False

    def test_foreclosure_has_auction_date(self):
        """Test has_auction_date method"""
        prop_with_auction = ForeclosureProperty(
            borrowers_name="Test",
            auction_date="2024-06-01"
        )
        assert prop_with_auction.has_auction_date() is True

        prop_without_auction = ForeclosureProperty(
            borrowers_name="Test"
        )
        assert prop_without_auction.has_auction_date() is False

    def test_foreclosure_to_dict(self):
        """Test to_dict method for backward compatibility"""
        prop = ForeclosureProperty(
            borrowers_name="John Doe",
            situs_address="123 Main St",
            parcel_number="123456789",
            latitude=28.5,
            longitude=-81.5
        )

        prop_dict = prop.to_dict()

        assert isinstance(prop_dict, dict)
        assert prop_dict["borrowers_name"] == "John Doe"
        assert prop_dict["parcel_number"] == "123456789"


@pytest.mark.integration
class TestForeclosureScraperIntegration:
    """Integration tests that hit the real API"""

    def test_fetch_real_foreclosures(self):
        """Test fetching from real API (requires internet)"""
        scraper = ForeclosureScraper()
        foreclosures = scraper.fetch_foreclosures(limit=5)

        assert len(foreclosures) > 0
        assert len(foreclosures) <= 5

        prop = foreclosures[0]
        assert isinstance(prop, ForeclosureProperty)
        assert prop.parcel_number is not None
