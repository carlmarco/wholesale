"""
Unit tests for migrated geo_enricher module
"""
import pytest
import tempfile
import os

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.wholesaler.enrichers.geo_enricher import GeoPropertyEnricher
from src.wholesaler.models.property import TaxSaleProperty, EnrichedProperty
from src.wholesaler.utils.geo_utils import haversine_distance


@pytest.fixture
def sample_csv_with_state_plane():
    """Create a temporary CSV file with State Plane coordinates"""
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
    """Create a temporary CSV file with lat/lon coordinates"""
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
    """Tests for migrated GeoPropertyEnricher class"""

    def test_enricher_initialization(self, sample_csv_with_coords):
        """Test that enricher initializes correctly with config"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.5)

        assert enricher.violations_df is not None
        assert enricher.radius_miles == 0.5
        assert len(enricher.violations_df) == 3

    def test_haversine_distance_calculation(self):
        """Test Haversine distance calculation"""
        lat1, lon1 = 28.5, -81.5
        lat2, lon2 = 28.5, -81.5

        distance = haversine_distance(lat1, lon1, lat2, lon2)
        assert distance == 0.0

        lat2, lon2 = 28.50001, -81.50001
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        assert distance > 0
        assert distance < 0.01

    def test_haversine_distance_known_values(self):
        """Test Haversine with known distance"""
        lat1, lon1 = 28.5, -81.5
        lat2, lon2 = 28.514, -81.5

        distance = haversine_distance(lat1, lon1, lat2, lon2)

        assert 0.9 < distance < 1.1

    def test_enrich_properties_with_nearby_violations(self, sample_csv_with_coords):
        """Test enriching when violations are nearby"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        properties = [
            TaxSaleProperty(
                tda_number='2023-1234',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                parcel_id='29-22-28-8850-02-050',
                latitude=28.5,
                longitude=-81.5
            )
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        assert isinstance(enriched[0], EnrichedProperty)
        assert enriched[0].nearby_violations >= 1
        assert enriched[0].nearest_violation_distance is not None
        assert isinstance(enriched[0].violation_types_nearby, list)

    def test_enrich_properties_no_nearby_violations(self, sample_csv_with_coords):
        """Test enriching when no violations are nearby"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.01)

        properties = [
            TaxSaleProperty(
                tda_number='2023-9999',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                parcel_id='99-99-99-9999-99-999',
                latitude=30.0,
                longitude=-80.0
            )
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        assert enriched[0].nearby_violations == 0
        assert enriched[0].nearby_open_violations == 0
        assert enriched[0].nearest_violation_distance is None
        assert enriched[0].violation_types_nearby == []

    def test_enrich_properties_missing_coordinates(self, sample_csv_with_coords):
        """Test enriching property with missing coordinates"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        properties = [
            TaxSaleProperty(
                tda_number='2023-1234',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                parcel_id='29-22-28-8850-02-050',
                latitude=None,
                longitude=None
            )
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        assert enriched[0].nearby_violations == 0
        assert enriched[0].nearest_violation_distance is None

    def test_enrich_multiple_properties_varying_distances(self, sample_csv_with_coords):
        """Test enriching multiple properties at different distances"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.5)

        properties = [
            TaxSaleProperty(
                tda_number='2023-1111',
                parcel_id='A',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                latitude=28.5,
                longitude=-81.5
            ),
            TaxSaleProperty(
                tda_number='2023-2222',
                parcel_id='B',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                latitude=28.6,
                longitude=-81.6
            )
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 2
        for prop in enriched:
            assert isinstance(prop, EnrichedProperty)
            assert hasattr(prop, 'nearby_violations')
            assert hasattr(prop, 'nearby_open_violations')

    def test_different_radius_sizes(self, sample_csv_with_coords):
        """Test that different radius sizes affect results"""
        property_data = [
            TaxSaleProperty(
                tda_number='2023-1234',
                parcel_id='A',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                latitude=28.5,
                longitude=-81.5
            )
        ]

        enricher_small = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.0001)
        enriched_small = enricher_small.enrich_properties(property_data)

        enricher_large = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=10.0)
        enriched_large = enricher_large.enrich_properties(property_data)

        assert enriched_large[0].nearby_violations >= enriched_small[0].nearby_violations

    def test_coordinate_system_detection_state_plane(self, sample_csv_with_state_plane):
        """Test that State Plane coordinates are detected and converted"""
        enricher = GeoPropertyEnricher(sample_csv_with_state_plane, radius_miles=0.1)

        assert 'latitude' in enricher.violations_df.columns
        assert 'longitude' in enricher.violations_df.columns

        assert len(enricher.violations_df) == 3

        lats = enricher.violations_df['latitude']
        lons = enricher.violations_df['longitude']

        assert all(28 <= lat <= 29 for lat in lats)
        assert all(-82 <= lon <= -81 for lon in lons)

    def test_coordinate_system_detection_latlon(self, sample_csv_with_coords):
        """Test that lat/lon coordinates are detected"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        assert 'latitude' in enricher.violations_df.columns
        assert 'longitude' in enricher.violations_df.columns

        assert len(enricher.violations_df) == 3

        assert enricher.violations_df['latitude'].iloc[0] == 28.5
        assert enricher.violations_df['longitude'].iloc[0] == -81.5

    def test_negative_longitude_filter_fixed(self, sample_csv_with_coords):
        """Test that negative longitudes are no longer filtered out"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        assert len(enricher.violations_df) > 0

        negative_lons = enricher.violations_df[enricher.violations_df['longitude'] != 0]['longitude']
        assert all(lon < 0 for lon in negative_lons)

    def test_coordinate_conversion_accuracy(self, sample_csv_with_state_plane):
        """Test that State Plane conversion produces accurate results"""
        enricher = GeoPropertyEnricher(sample_csv_with_state_plane, radius_miles=0.1)

        first_lat = enricher.violations_df['latitude'].iloc[0]
        first_lon = enricher.violations_df['longitude'].iloc[0]

        assert 28.52 < first_lat < 28.54
        assert -81.46 < first_lon < -81.44

    def test_invalid_coordinates_filtered(self, sample_csv_with_coords):
        """Test that (0, 0) coordinates are filtered out"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        assert len(enricher.violations_df) == 3

        for _, row in enricher.violations_df.iterrows():
            assert not (row['latitude'] == 0 and row['longitude'] == 0)

    def test_enriched_property_to_dict(self, sample_csv_with_coords):
        """Test EnrichedProperty to_dict for backward compatibility"""
        enricher = GeoPropertyEnricher(sample_csv_with_coords, radius_miles=0.1)

        properties = [
            TaxSaleProperty(
                tda_number='2023-1234',
                sale_date='12/18/2025',
                deed_status='Active Sale',
                parcel_id='29-22-28-8850-02-050',
                latitude=28.5,
                longitude=-81.5
            )
        ]

        enriched = enricher.enrich_properties(properties)
        prop_dict = enriched[0].to_dict()

        assert isinstance(prop_dict, dict)
        assert 'tda_number' in prop_dict
        assert 'nearby_violations' in prop_dict
        assert 'nearest_violation_distance' in prop_dict
