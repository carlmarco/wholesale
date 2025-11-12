"""
Tests for Seed-Based Lead Scoring

Tests LeadScorer extensions for hybrid seed ingestion.
"""
import pytest

from src.wholesaler.pipelines.lead_scoring import LeadScorer


@pytest.fixture
def scorer():
    """Create LeadScorer instance."""
    return LeadScorer()


@pytest.fixture
def tax_sale_enriched_data():
    """Sample tax sale enriched data."""
    return {
        'parcel_id': '1234567890',
        'seed_type': 'tax_sale',
        'tda_number': '2024-001',
        'sale_date': '2024-03-15',
        'deed_status': 'Not Issued',
        'latitude': 28.5383,
        'longitude': -81.3792,
        'situs_address': '123 Main St',
        'city': 'Orlando',
        'zip_code': '32801',
        'total_mkt': 250000,
        'total_assd': 245000,
        'equity_percent': 180.0,  # High equity
        'violation_count': 5,
        'nearby_violations': 5,
        'nearby_open_violations': 2,
    }


@pytest.fixture
def code_violation_enriched_data():
    """Sample code violation enriched data."""
    return {
        'parcel_id': '9876543210',
        'seed_type': 'code_violation',
        'latitude': 28.5400,
        'longitude': -81.3800,
        'situs_address': '456 Oak Ave',
        'city': 'Orlando',
        'zip_code': '32803',
        'violation_count': 15,  # High violation count
        'nearby_violations': 15,
        'nearby_open_violations': 8,
        'most_recent_violation': '2024-02-01',
        'total_mkt': 180000,
        'equity_percent': 120.0,
    }


@pytest.fixture
def foreclosure_enriched_data():
    """Sample foreclosure enriched data."""
    return {
        'parcel_id': '5555555555',
        'seed_type': 'foreclosure',
        'default_amount': 150000,
        'opening_bid': 140000,
        'auction_date': '2024-04-15',
        'lender_name': 'Big Bank Corp',
        'latitude': 28.5420,
        'longitude': -81.3820,
        'situs_address': '789 Elm St',
        'city': 'Orlando',
        'zip_code': '32804',
        'total_mkt': 200000,
        'equity_percent': 140.0,
    }


class TestSeedBasedScoring:
    """Tests for seed-based lead scoring."""

    def test_score_tax_sale_seed(self, scorer, tax_sale_enriched_data):
        """Test scoring a tax sale seed."""
        result = scorer.score_seed_based_lead(
            enriched_data=tax_sale_enriched_data,
            seed_type='tax_sale'
        )

        # Tax sales get 1.2x multiplier
        assert result.total_score > 0
        assert result.tier in ['A', 'B', 'C', 'D']
        assert len(result.reasons) > 0

        # Should mention tax sale seed type
        seed_type_mentioned = any('tax_sale' in r.lower() for r in result.reasons)
        assert seed_type_mentioned

    def test_score_code_violation_seed(self, scorer, code_violation_enriched_data):
        """Test scoring a code violation seed."""
        result = scorer.score_seed_based_lead(
            enriched_data=code_violation_enriched_data,
            seed_type='code_violation'
        )

        # Code violations get 1.0x multiplier (standard)
        assert result.total_score > 0
        assert result.tier in ['A', 'B', 'C', 'D']

        # High violation count should contribute to score
        assert result.distress_score > 0

    def test_score_foreclosure_seed(self, scorer, foreclosure_enriched_data):
        """Test scoring a foreclosure seed."""
        result = scorer.score_seed_based_lead(
            enriched_data=foreclosure_enriched_data,
            seed_type='foreclosure'
        )

        # Foreclosures get 1.15x multiplier
        assert result.total_score > 0
        assert result.tier in ['A', 'B', 'C', 'D']

        # Should detect foreclosure status
        foreclosure_mentioned = any('foreclosure' in r.lower() or 'default' in r.lower() for r in result.reasons)
        assert foreclosure_mentioned or result.distress_score > 0

    def test_seed_type_weights_applied(self, scorer, tax_sale_enriched_data, code_violation_enriched_data):
        """Test that seed type weights are correctly applied."""
        # Use similar data but different seed types
        base_data = {
            'parcel_id': '1111111111',
            'latitude': 28.5383,
            'longitude': -81.3792,
            'total_mkt': 200000,
            'equity_percent': 150.0,
            'violation_count': 5,
        }

        # Score as tax_sale (1.2x weight)
        tax_sale_score = scorer.score_seed_based_lead(
            enriched_data=base_data,
            seed_type='tax_sale'
        )

        # Score as code_violation (1.0x weight)
        violation_score = scorer.score_seed_based_lead(
            enriched_data=base_data,
            seed_type='code_violation'
        )

        # Tax sale should score higher due to weight
        assert tax_sale_score.total_score > violation_score.total_score

    def test_convert_seed_to_legacy_format(self, scorer, tax_sale_enriched_data):
        """Test conversion from seed format to legacy format."""
        legacy = scorer._convert_seed_to_legacy_format(
            enriched_data=tax_sale_enriched_data,
            seed_type='tax_sale'
        )

        # Check structure
        assert 'parcel_id_normalized' in legacy
        assert 'tax_sale' in legacy
        assert 'property_record' in legacy
        assert 'enrichment' in legacy

        # Check tax sale data mapped correctly
        assert legacy['tax_sale']['tda_number'] == '2024-001'
        assert legacy['tax_sale']['sale_date'] == '2024-03-15'

        # Check property record mapped correctly
        assert legacy['property_record']['total_mkt'] == 250000
        assert legacy['property_record']['equity_percent'] == 180.0

        # Check enrichment data mapped correctly
        assert legacy['enrichment']['nearby_violations'] == 5

    def test_high_equity_tax_sale_tiers_high(self, scorer):
        """Test that high equity tax sales score in high tiers."""
        data = {
            'parcel_id': '1111111111',
            'seed_type': 'tax_sale',
            'total_mkt': 300000,
            'equity_percent': 220.0,  # Excellent equity
            'violation_count': 10,     # High violations
            'nearby_violations': 10,
            'latitude': 28.5383,
            'longitude': -81.3792,
        }

        result = scorer.score_seed_based_lead(data, 'tax_sale')

        # With high equity, high violations, and tax sale weight, should score well
        assert result.total_score >= scorer.TIER_B_THRESHOLD
        assert result.tier in ['A', 'B']

    def test_low_value_property_tiers_low(self, scorer):
        """Test that low value properties tier appropriately."""
        data = {
            'parcel_id': '2222222222',
            'seed_type': 'code_violation',
            'total_mkt': 50000,       # Low market value
            'equity_percent': 80.0,   # Low equity
            'violation_count': 1,     # Few violations
            'latitude': 28.5383,
            'longitude': -81.3792,
        }

        result = scorer.score_seed_based_lead(data, 'code_violation')

        # Low value with low distress indicators should tier lower
        assert result.tier in ['C', 'D']

    def test_missing_optional_fields(self, scorer):
        """Test scoring with minimal data (missing optional fields)."""
        minimal_data = {
            'parcel_id': '3333333333',
            'latitude': 28.5383,
            'longitude': -81.3792,
        }

        result = scorer.score_seed_based_lead(minimal_data, 'code_violation')

        # Should not crash, but score will be low
        assert result.total_score >= 0
        assert result.tier in ['C', 'D']

    def test_scoring_components_calculated(self, scorer, tax_sale_enriched_data):
        """Test that all scoring components are calculated."""
        result = scorer.score_seed_based_lead(
            tax_sale_enriched_data,
            'tax_sale'
        )

        # All components should be calculated
        assert result.distress_score >= 0
        assert result.value_score >= 0
        assert result.location_score >= 0
        assert result.urgency_score >= 0

        # Total should be weighted sum
        assert result.total_score > 0

    def test_tier_thresholds_respected(self, scorer):
        """Test that tier thresholds are respected."""
        # Create data that should score in each tier
        tiers_tested = set()

        test_cases = [
            # High score (Tier A or B)
            {
                'parcel_id': '1111111111',
                'seed_type': 'tax_sale',
                'total_mkt': 400000,
                'equity_percent': 250.0,
                'violation_count': 20,
                'nearby_violations': 20,
                'expected_tier': 'A_or_B'  # High score, should be A or B
            },
            # Low score (Tier D)
            {
                'parcel_id': '4444444444',
                'seed_type': 'code_violation',
                'total_mkt': 30000,
                'equity_percent': 60.0,
                'violation_count': 0,
                'expected_tier': 'D'
            },
        ]

        for case in test_cases:
            expected_tier = case.pop('expected_tier')
            seed_type = case.pop('seed_type')

            result = scorer.score_seed_based_lead(case, seed_type)

            if expected_tier == 'A_or_B':
                # High equity + tax sale + violations should score well
                assert result.total_score >= scorer.TIER_B_THRESHOLD
                assert result.tier in ['A', 'B']
            elif expected_tier == 'D':
                assert result.total_score < scorer.TIER_C_THRESHOLD

            tiers_tested.add(result.tier)

        # Should have tested multiple tiers
        assert len(tiers_tested) >= 2


class TestSeedTypeWeights:
    """Tests specifically for seed type weighting."""

    def test_weight_constants_defined(self, scorer):
        """Test that seed type weights are defined."""
        assert hasattr(scorer, 'SEED_TYPE_WEIGHTS')
        assert 'tax_sale' in scorer.SEED_TYPE_WEIGHTS
        assert 'code_violation' in scorer.SEED_TYPE_WEIGHTS
        assert 'foreclosure' in scorer.SEED_TYPE_WEIGHTS

    def test_tax_sale_highest_weight(self, scorer):
        """Test that tax sales have highest priority weight."""
        weights = scorer.SEED_TYPE_WEIGHTS
        assert weights['tax_sale'] >= weights['foreclosure']
        assert weights['tax_sale'] >= weights['code_violation']

    def test_weight_multiplier_effect(self, scorer):
        """Test that weight multiplier has measurable effect."""
        data = {
            'parcel_id': '5555555555',
            'total_mkt': 200000,
            'equity_percent': 150.0,
            'violation_count': 5,
            'latitude': 28.5383,
            'longitude': -81.3792,
        }

        # Score with different seed types
        tax_sale_result = scorer.score_seed_based_lead(data, 'tax_sale')
        violation_result = scorer.score_seed_based_lead(data, 'code_violation')

        # Calculate expected multiplier effect
        tax_sale_weight = scorer.SEED_TYPE_WEIGHTS['tax_sale']
        violation_weight = scorer.SEED_TYPE_WEIGHTS['code_violation']

        # Tax sale should score proportionally higher
        if tax_sale_weight > violation_weight:
            assert tax_sale_result.total_score > violation_result.total_score
