"""
Tests for Database Utilities

Tests PostGIS utilities, data transformations, and database operations.
"""
import pytest
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.wholesaler.db.base import Base
from src.wholesaler.db import db_utils
from src.wholesaler.db.models import Property, LeadScore


@pytest.fixture(scope="function")
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


class TestDistanceConversions:
    """Tests for distance conversion utilities."""

    def test_meters_to_miles(self):
        """Test converting meters to miles."""
        # 1609.34 meters = 1 mile
        miles = db_utils.meters_to_miles(1609.34)
        assert abs(miles - 1.0) < 0.01

        # 5 km = 3.107 miles
        miles = db_utils.meters_to_miles(5000)
        assert abs(miles - 3.107) < 0.01

    def test_miles_to_meters(self):
        """Test converting miles to meters."""
        # 1 mile = 1609.34 meters
        meters = db_utils.miles_to_meters(1.0)
        assert abs(meters - 1609.34) < 0.1

        # 5 miles = 8046.7 meters
        meters = db_utils.miles_to_meters(5.0)
        assert abs(meters - 8046.7) < 1.0

    def test_round_trip_conversion(self):
        """Test that converting back and forth preserves the original value."""
        original_miles = 10.0
        meters = db_utils.miles_to_meters(original_miles)
        back_to_miles = db_utils.meters_to_miles(meters)

        assert abs(back_to_miles - original_miles) < 0.001


class TestDateParsing:
    """Tests for date parsing utilities."""

    def test_parse_iso_date(self):
        """Test parsing ISO format date (YYYY-MM-DD)."""
        parsed = db_utils.parse_date_string("2024-03-15")

        assert parsed is not None
        assert parsed == date(2024, 3, 15)

    def test_parse_us_date(self):
        """Test parsing US format date (MM/DD/YYYY)."""
        parsed = db_utils.parse_date_string("03/15/2024")

        assert parsed is not None
        assert parsed == date(2024, 3, 15)

    def test_parse_invalid_date(self):
        """Test that invalid date returns None."""
        parsed = db_utils.parse_date_string("not-a-date")

        assert parsed is None

    def test_parse_none(self):
        """Test that None input returns None."""
        parsed = db_utils.parse_date_string(None)

        assert parsed is None


class TestJSONBSanitization:
    """Tests for JSONB sanitization utilities."""

    def test_sanitize_dict_with_dates(self):
        """Test sanitizing dict with datetime objects."""
        data = {
            "name": "Test Property",
            "created_at": datetime(2024, 3, 15, 10, 30, 0),
            "sale_date": date(2024, 3, 15),
            "score": 85.5,
        }

        sanitized = db_utils.sanitize_dict_for_jsonb(data)

        assert sanitized["name"] == "Test Property"
        assert sanitized["created_at"] == "2024-03-15T10:30:00"
        assert sanitized["sale_date"] == "2024-03-15"
        assert sanitized["score"] == 85.5

    def test_sanitize_dict_removes_none(self):
        """Test that None values are removed."""
        data = {
            "name": "Test",
            "optional_field": None,
            "score": 100,
        }

        sanitized = db_utils.sanitize_dict_for_jsonb(data)

        assert "optional_field" not in sanitized
        assert sanitized["name"] == "Test"
        assert sanitized["score"] == 100

    def test_sanitize_nested_dict(self):
        """Test sanitizing nested dictionaries."""
        data = {
            "property": {
                "address": "123 Main St",
                "sale_date": date(2024, 3, 15),
            },
            "metadata": {
                "created_at": datetime(2024, 3, 15, 10, 30, 0),
                "optional": None,
            },
        }

        sanitized = db_utils.sanitize_dict_for_jsonb(data)

        assert sanitized["property"]["address"] == "123 Main St"
        assert sanitized["property"]["sale_date"] == "2024-03-15"
        assert sanitized["metadata"]["created_at"] == "2024-03-15T10:30:00"
        assert "optional" not in sanitized["metadata"]

    def test_sanitize_list_of_dicts(self):
        """Test sanitizing lists containing dictionaries."""
        data = {
            "violations": [
                {"type": "Code", "date": date(2024, 1, 1)},
                {"type": "Zoning", "date": date(2024, 2, 1)},
            ]
        }

        sanitized = db_utils.sanitize_dict_for_jsonb(data)

        assert len(sanitized["violations"]) == 2
        assert sanitized["violations"][0]["date"] == "2024-01-01"
        assert sanitized["violations"][1]["date"] == "2024-02-01"


class TestBoundingBox:
    """Tests for bounding box calculation."""

    def test_calculate_bounding_box(self):
        """Test calculating bounding box for spatial queries."""
        # Orlando, FL coordinates
        center_lat = 28.5383
        center_lon = -81.3792
        radius_miles = 1.0

        bbox = db_utils.calculate_bounding_box(center_lat, center_lon, radius_miles)

        assert "min_lat" in bbox
        assert "max_lat" in bbox
        assert "min_lon" in bbox
        assert "max_lon" in bbox

        # Verify box is centered
        lat_center = (bbox["min_lat"] + bbox["max_lat"]) / 2
        lon_center = (bbox["min_lon"] + bbox["max_lon"]) / 2

        assert abs(lat_center - center_lat) < 0.01
        assert abs(lon_center - center_lon) < 0.01

    def test_bounding_box_larger_radius(self):
        """Test that larger radius creates larger bounding box."""
        center_lat = 28.5383
        center_lon = -81.3792

        bbox_1_mile = db_utils.calculate_bounding_box(center_lat, center_lon, 1.0)
        bbox_5_miles = db_utils.calculate_bounding_box(center_lat, center_lon, 5.0)

        # 5 mile box should be larger
        assert (bbox_5_miles["max_lat"] - bbox_5_miles["min_lat"]) > \
               (bbox_1_mile["max_lat"] - bbox_1_mile["min_lat"])
        assert (bbox_5_miles["max_lon"] - bbox_5_miles["min_lon"]) > \
               (bbox_1_mile["max_lon"] - bbox_1_mile["min_lon"])


class TestDatabaseStatistics:
    """Tests for database statistics utilities."""

    def test_get_table_row_count(self, test_db):
        """Test getting row count for a table."""
        # Create some properties
        for i in range(5):
            property_obj = Property(
                parcel_id_normalized=f"12-34-56-7890-01-00{i}",
                parcel_id_original=f"12 34 56 7890 01 00{i}",
                situs_address=f"{i*100} Main St",
            )
            test_db.add(property_obj)
        test_db.commit()

        # Get row count
        count = db_utils.get_table_row_count(test_db, "properties")

        assert count == 5

    def test_get_database_stats(self, test_db):
        """Test getting statistics for all tables."""
        # Create sample data
        for i in range(3):
            property_obj = Property(
                parcel_id_normalized=f"12-34-56-7890-01-00{i}",
                parcel_id_original=f"12 34 56 7890 01 00{i}",
                situs_address=f"{i*100} Main St",
            )
            test_db.add(property_obj)

        for i in range(2):
            lead_score = LeadScore(
                parcel_id_normalized=f"12-34-56-7890-01-00{i}",
                total_score=75.0,
                tier="B",
            )
            test_db.add(lead_score)

        test_db.commit()

        # Get stats
        stats = db_utils.get_database_stats(test_db)

        assert "properties" in stats
        assert "lead_scores" in stats
        assert stats["properties"] == 3
        assert stats["lead_scores"] == 2


class TestUpsertHelpers:
    """Tests for upsert helper functions."""

    def test_build_upsert_values(self):
        """Test building values dict for upsert."""
        data = {
            "id": 1,
            "parcel_id": "123",
            "address": "123 Main St",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        # Build upsert values (exclude id and created_at)
        upsert_values = db_utils.build_upsert_values(data)

        assert "id" not in upsert_values
        assert "created_at" not in upsert_values
        assert "parcel_id" in upsert_values
        assert "address" in upsert_values
        assert "updated_at" in upsert_values

    def test_build_upsert_values_custom_exclude(self):
        """Test building upsert values with custom exclude keys."""
        data = {
            "id": 1,
            "parcel_id": "123",
            "address": "123 Main St",
            "temp_field": "temporary",
        }

        # Exclude custom keys
        upsert_values = db_utils.build_upsert_values(
            data,
            exclude_keys=["id", "temp_field"]
        )

        assert "id" not in upsert_values
        assert "temp_field" not in upsert_values
        assert "parcel_id" in upsert_values
        assert "address" in upsert_values
