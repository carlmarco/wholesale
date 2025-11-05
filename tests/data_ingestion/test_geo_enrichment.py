"""
Unit tests for geo_enrichment module
"""
import pytest
import pandas as pd
import tempfile
import os
import math

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.data_ingestion.geo_enrichment import GeoPropertyEnricher


@pytest.fixture
def sample_csv_with_state_plane():
    """Create a temporary CSV file with State Plane coordinates"""
    # Florida State Plane East coordinates (large values)
    # These should trigger coordinate conversion
    data = """apno,caseinfostatus,gpsx,gpsy,case_type,casedt
2025-001,Open,511279,1524452,Lot,2025-01-15
2025-002,Closed,534679,1542276,Housing,2025-01-10
2025-003,Open,501552,1520974,Sign,2025-02-01
2025-004,Closed,0,0,Lot,2025-01-01
"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(data)
        temp_path = f.name

    yield temp_path

    os.unlink(temp_path)


@pytest.fixture
def sample_csv_with_coords():
    """Create a temporary CSV file with coordinate data (lat/lon format)"""
    # Using negative longitudes (Orlando is at -81.x)
    # Small values (<100) will be detected as lat/lon, not State Plane
    data = """apno,caseinfostatus,gpsx,gpsy,case_type,casedt
2025-001,Open,-81.5,28.5,Lot,2025-01-15
2025-002,Closed,-81.50001,28.50001,Housing,2025-01-10
2025-003,Open,-81.6,28.6,Sign,2025-02-01
2025-004,Closed,0,0,Lot,2025-01-01
"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(data)
        temp_path = f.name

    yield temp_path

    os.unlink(temp_path)


class TestGeoPropertyEnricher:
    """Tests for GeoPropertyEnricher class"""

    def test_enricher_initialization(self, sample_csv_with_coords):
        """Test that enricher initializes correctly"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.5)

        assert enricher.violations_df is not None
        assert enricher.radius_miles == 0.5
        # Should filter out (0, 0) coordinates
        assert len(enricher.violations_df) == 3

    def test_haversine_distance_calculation(self, sample_csv_with_coords):
        """Test Haversine distance calculation"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        # Orlando coordinates
        lat1, lon1 = 28.5, -81.5
        lat2, lon2 = 28.5, -81.5

        # Same point
        distance = enricher.haversine_distance(lat1, lon1, lat2, lon2)
        assert distance == 0.0

        # Different points (roughly 0.0001 degrees apart ~ 0.007 miles)
        lat2, lon2 = 28.50001, -81.50001
        distance = enricher.haversine_distance(lat1, lon1, lat2, lon2)
        assert distance > 0
        assert distance < 0.01  # Should be very small

    def test_haversine_distance_known_values(self, sample_csv_with_coords):
        """Test Haversine with known distance"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        # Orlando to approximately 1 mile north
        lat1, lon1 = 28.5, -81.5
        lat2, lon2 = 28.514, -81.5  # Approximately 1 mile north

        distance = enricher.haversine_distance(lat1, lon1, lat2, lon2)

        # Should be close to 1 mile (allow some tolerance)
        assert 0.9 < distance < 1.1

    def test_enrich_properties_with_nearby_violations(self, sample_csv_with_coords):
        """Test enriching when violations are nearby"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        properties = [
            {
                'tda_number': '2023-1234',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'parcel_id': '29-22-28-8850-02-050',
                'latitude': 28.5,
                'longitude': -81.5  # Negative longitude (Orlando)
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        prop = enriched[0]

        # Should find 2 nearby violations (both at ~-81.5, 28.5)
        assert prop['nearby_violations'] >= 1
        assert 'nearest_violation_distance' in prop
        assert 'violation_types_nearby' in prop

    def test_enrich_properties_no_nearby_violations(self, sample_csv_with_coords):
        """Test enriching when no violations are nearby"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.01)

        properties = [
            {
                'tda_number': '2023-9999',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'parcel_id': '99-99-99-9999-99-999',
                'latitude': 30.0,  # Far from Orlando
                'longitude': -80.0,
                'tda_number': '2023-9999'
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        prop = enriched[0]

        assert prop['nearby_violations'] == 0
        assert prop['nearby_open_violations'] == 0
        assert prop['nearest_violation_distance'] is None
        assert prop['violation_types_nearby'] == []

    def test_enrich_properties_missing_coordinates(self, sample_csv_with_coords):
        """Test enriching property with missing coordinates"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        properties = [
            {
                'tda_number': '2023-1234',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'parcel_id': '29-22-28-8850-02-050',
                'latitude': None,
                'longitude': None
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        prop = enriched[0]

        # Should have zero violations due to missing coords
        assert prop['nearby_violations'] == 0
        assert prop['nearest_violation_distance'] is None

    def test_calculate_proximity_metrics_no_violations(self, sample_csv_with_coords):
        """Test metrics calculation with no nearby violations"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        metrics = enricher._calculate_proximity_metrics([])

        assert metrics['nearby_violations'] == 0
        assert metrics['nearby_open_violations'] == 0
        assert metrics['nearest_violation_distance'] is None
        assert metrics['violation_types_nearby'] == []
        assert metrics['avg_violation_distance'] is None

    def test_calculate_proximity_metrics_with_violations(self, sample_csv_with_coords):
        """Test metrics calculation with nearby violations"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        nearby = [
            {'distance': 0.05, 'status': 'Open', 'type': 'Lot', 'date': '2025-01-15'},
            {'distance': 0.08, 'status': 'Closed', 'type': 'Housing', 'date': '2025-01-10'}
        ]

        metrics = enricher._calculate_proximity_metrics(nearby)

        assert metrics['nearby_violations'] == 2
        assert metrics['nearby_open_violations'] == 1
        assert metrics['nearest_violation_distance'] == 0.05
        assert metrics['avg_violation_distance'] == 0.065
        assert 'Lot' in metrics['violation_types_nearby'] or 'Housing' in metrics['violation_types_nearby']

    def test_enrich_multiple_properties_varying_distances(self, sample_csv_with_coords):
        """Test enriching multiple properties at different distances"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.5)

        properties = [
            {
                'tda_number': '2023-1111',
                'parcel_id': 'A',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'latitude': 28.5,
                'longitude': -81.5
            },
            {
                'tda_number': '2023-2222',
                'parcel_id': 'B',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'latitude': 28.6,
                'longitude': -81.6
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 2

        # All should have enrichment fields
        for prop in enriched:
            assert 'nearby_violations' in prop
            assert 'nearby_open_violations' in prop

    def test_different_radius_sizes(self, sample_csv_with_coords):
        """Test that different radius sizes affect results"""
        property_data = [{
            'tda_number': '2023-1234',
            'parcel_id': 'A',
            'sale_date': '12/18/2025',
            'deed_status': 'Active Sale',
            'latitude': 28.5,
            'longitude': -81.5
        }]

        # Small radius
        enricher_small = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.0001)
        enriched_small = enricher_small.enrich_properties(property_data)

        # Large radius
        enricher_large = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=10.0)
        enriched_large = enricher_large.enrich_properties(property_data)

        # Larger radius should find more or equal violations
        assert enriched_large[0]['nearby_violations'] >= enriched_small[0]['nearby_violations']

    def test_coordinate_system_detection_state_plane(self, sample_csv_with_state_plane):
        """Test that State Plane coordinates are detected and converted"""
        enricher = GeoPropertyEnricher(sample_csv_with_state_plane, radius_miles=0.1)

        # Should have converted coordinates
        assert 'latitude' in enricher.violations_df.columns
        assert 'longitude' in enricher.violations_df.columns

        # Should have 3 valid records (0,0 filtered out)
        assert len(enricher.violations_df) == 3

        # Check that coordinates are in valid Orlando range
        lats = enricher.violations_df['latitude']
        lons = enricher.violations_df['longitude']

        assert all(28 <= lat <= 29 for lat in lats)
        assert all(-82 <= lon <= -81 for lon in lons)

    def test_coordinate_system_detection_latlon(self, sample_csv_with_coords):
        """Test that lat/lon coordinates are detected (no conversion)"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        # Should have latitude/longitude columns
        assert 'latitude' in enricher.violations_df.columns
        assert 'longitude' in enricher.violations_df.columns

        # Should have 3 valid records (0,0 filtered out)
        assert len(enricher.violations_df) == 3

        # Coordinates should match input (no conversion)
        assert enricher.violations_df['latitude'].iloc[0] == 28.5
        assert enricher.violations_df['longitude'].iloc[0] == -81.5

    def test_negative_longitude_filter_fixed(self, sample_csv_with_coords):
        """Test that negative longitudes are no longer filtered out"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        # Should have records with negative longitudes
        assert len(enricher.violations_df) > 0

        # All non-zero longitudes should be negative (Orlando)
        negative_lons = enricher.violations_df[enricher.violations_df['longitude'] != 0]['longitude']
        assert all(lon < 0 for lon in negative_lons)

    def test_coordinate_conversion_accuracy(self, sample_csv_with_state_plane):
        """Test that State Plane conversion produces accurate results"""
        enricher = GeoPropertyEnricher(sample_csv_with_state_plane, radius_miles=0.1)

        # First coordinate: (511279, 1524452) should convert to approximately (28.527, -81.451)
        first_lat = enricher.violations_df['latitude'].iloc[0]
        first_lon = enricher.violations_df['longitude'].iloc[0]

        # Check within reasonable tolerance (0.01 degrees ~ 0.7 miles)
        assert 28.52 < first_lat < 28.54
        assert -81.46 < first_lon < -81.44

    def test_invalid_coordinates_filtered(self, sample_csv_with_coords):
        """Test that (0, 0) coordinates are filtered out"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        # Should have filtered out the (0, 0) record
        # Original has 4 records, one with (0,0)
        assert len(enricher.violations_df) == 3

        # No coordinates should be exactly (0, 0)
        for _, row in enricher.violations_df.iterrows():
            assert not (row['latitude'] == 0 and row['longitude'] == 0)
