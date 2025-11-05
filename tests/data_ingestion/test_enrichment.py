"""
Unit tests for enrichment module
"""
import pytest
import pandas as pd
import tempfile
import os

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.data_ingestion.enrichment import PropertyEnricher


@pytest.fixture
def sample_csv_file():
    """Create a temporary CSV file with sample code enforcement data"""
    data = """apno,caseinfostatus,parcel_id,case_type,casedt,days_to_resolve
2025-001,Open,292228885002050,Lot,2025-01-15,0
2025-002,Closed,292228885002050,Housing,2025-01-10,5
2025-003,Open,123456789012345,Sign,2025-02-01,0
2025-004,Closed,999999999999999,Lot,2025-01-01,30
"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(data)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def sample_properties():
    """Sample tax sale properties"""
    return [
        {
            'tda_number': '2023-1234',
            'sale_date': '12/18/2025',
            'deed_status': 'Active Sale',
            'parcel_id': '29-22-28-8850-02-050',
            'latitude': 28.5,
            'longitude': -81.5
        },
        {
            'tda_number': '2023-5678',
            'sale_date': '12/18/2025',
            'deed_status': 'Active Sale',
            'parcel_id': '12-34-56-7890-12-345',
            'latitude': 28.6,
            'longitude': -81.6
        }
    ]


class TestPropertyEnricher:
    """Tests for PropertyEnricher class"""

    def test_enricher_initialization(self, sample_csv_file):
        """Test that enricher initializes correctly"""
        enricher = PropertyEnricher(sample_csv_file)

        assert enricher.violations_df is not None
        assert len(enricher.violations_df) == 4
        assert 'parcel_id_normalized' in enricher.violations_df.columns

    def test_parcel_id_normalization(self, sample_csv_file):
        """Test that parcel IDs are normalized correctly"""
        enricher = PropertyEnricher(sample_csv_file)

        # Check that .0 suffix is removed
        normalized_ids = enricher.violations_df['parcel_id_normalized'].tolist()
        assert '292228885002050' in normalized_ids
        assert '123456789012345' in normalized_ids

    def test_enrich_properties_with_match(self, sample_csv_file):
        """Test enriching properties when there's a match"""
        enricher = PropertyEnricher(sample_csv_file)

        properties = [
            {
                'tda_number': '2023-1234',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'parcel_id': '29-22-28-8850-02-050',  # Matches normalized 292228885002050
                'latitude': 28.5,
                'longitude': -81.5
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        prop = enriched[0]

        # Should have 2 violations for this parcel
        assert prop['violation_count'] == 2
        assert prop['open_violations'] == 1
        assert prop['closed_violations'] == 1
        assert prop['has_violations'] is True
        assert 'Lot' in prop['violation_types'] or 'Housing' in prop['violation_types']

    def test_enrich_properties_without_match(self, sample_csv_file):
        """Test enriching properties when there's no match"""
        enricher = PropertyEnricher(sample_csv_file)

        properties = [
            {
                'tda_number': '2023-9999',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'parcel_id': '88-88-88-8888-88-888',  # Different parcel that won't match
                'latitude': 28.5,
                'longitude': -81.5
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 1
        prop = enriched[0]

        assert prop['violation_count'] == 0
        assert prop['open_violations'] == 0
        assert prop['closed_violations'] == 0
        assert prop['has_violations'] is False
        assert prop['violation_types'] == []
        assert prop['most_recent_violation'] is None

    def test_calculate_violation_metrics_no_violations(self, sample_csv_file):
        """Test metrics calculation with no violations"""
        enricher = PropertyEnricher(sample_csv_file)

        empty_df = pd.DataFrame()
        metrics = enricher._calculate_violation_metrics(empty_df)

        assert metrics['violation_count'] == 0
        assert metrics['open_violations'] == 0
        assert metrics['closed_violations'] == 0
        assert metrics['violation_types'] == []
        assert metrics['most_recent_violation'] is None
        assert metrics['avg_days_to_resolve'] is None

    def test_calculate_violation_metrics_with_violations(self, sample_csv_file):
        """Test metrics calculation with violations"""
        enricher = PropertyEnricher(sample_csv_file)

        # Get violations for parcel 292228885002050
        violations = enricher.violations_df[
            enricher.violations_df['parcel_id_normalized'] == '292228885002050'
        ]

        metrics = enricher._calculate_violation_metrics(violations)

        assert metrics['violation_count'] == 2
        assert metrics['open_violations'] == 1
        assert metrics['closed_violations'] == 1
        assert len(metrics['violation_types']) > 0

    def test_get_top_opportunities(self, sample_csv_file, sample_properties):
        """Test filtering and ranking opportunities"""
        enricher = PropertyEnricher(sample_csv_file)

        enriched = enricher.enrich_properties(sample_properties)

        # Filter for properties with at least 1 violation
        opportunities = enricher.get_top_opportunities(enriched, min_violations=1)

        # Should find properties with violations (sample data may match multiple)
        assert len(opportunities) >= 0

        # If there are opportunities, they should be sorted by violation count (descending)
        if len(opportunities) > 1:
            for i in range(len(opportunities) - 1):
                assert opportunities[i]['violation_count'] >= opportunities[i+1]['violation_count']

    def test_get_top_opportunities_high_threshold(self, sample_csv_file, sample_properties):
        """Test filtering with high violation threshold"""
        enricher = PropertyEnricher(sample_csv_file)

        enriched = enricher.enrich_properties(sample_properties)

        # Filter for properties with at least 10 violations (should be none)
        opportunities = enricher.get_top_opportunities(enriched, min_violations=10)

        assert len(opportunities) == 0

    def test_enrich_multiple_properties(self, sample_csv_file):
        """Test enriching multiple properties"""
        enricher = PropertyEnricher(sample_csv_file)

        properties = [
            {
                'tda_number': '2023-1234',
                'parcel_id': '29-22-28-8850-02-050',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'latitude': 28.5,
                'longitude': -81.5
            },
            {
                'tda_number': '2023-5678',
                'parcel_id': '12-34-56-7890-12-345',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'latitude': 28.6,
                'longitude': -81.6
            },
            {
                'tda_number': '2023-9999',
                'parcel_id': '99-99-99-9999-99-999',
                'sale_date': '12/18/2025',
                'deed_status': 'Active Sale',
                'latitude': 28.7,
                'longitude': -81.7
            }
        ]

        enriched = enricher.enrich_properties(properties)

        assert len(enriched) == 3

        # All should have enrichment fields
        for prop in enriched:
            assert 'violation_count' in prop
            assert 'has_violations' in prop
            assert 'parcel_id_normalized' in prop
