"""
Unit tests for deduplication and lead scoring modules
"""
import pytest

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.wholesaler.pipelines.deduplication import PropertyDeduplicator
from src.wholesaler.scoring import LeadScorer, LeadScore
from src.wholesaler.models.property import TaxSaleProperty
from src.wholesaler.models.foreclosure import ForeclosureProperty
from src.wholesaler.models.property_record import PropertyRecord


class TestPropertyDeduplicator:
    """Tests for PropertyDeduplicator class"""

    def test_deduplicator_initialization(self):
        """Test that deduplicator initializes correctly"""
        deduplicator = PropertyDeduplicator()
        assert deduplicator is not None
        assert deduplicator.standardizer is not None

    def test_merge_sources_empty(self):
        """Test merging with no data"""
        deduplicator = PropertyDeduplicator()

        result = deduplicator.merge_sources()

        assert result == []

    def test_merge_tax_sales_only(self):
        """Test merging tax sales only"""
        deduplicator = PropertyDeduplicator()

        tax_sales = [
            TaxSaleProperty(
                tda_number="2023-1234",
                parcel_id="12-34-56-7890-12-345",
                sale_date="12/18/2025",
                latitude=28.5,
                longitude=-81.5
            )
        ]

        result = deduplicator.merge_sources(tax_sales=tax_sales)

        assert len(result) == 1
        assert 'tax_sale' in result[0]
        assert result[0]['tax_sale']['tda_number'] == "2023-1234"

    def test_merge_multiple_sources_same_parcel(self):
        """Test merging multiple sources for same parcel"""
        deduplicator = PropertyDeduplicator()

        tax_sales = [
            TaxSaleProperty(
                tda_number="2023-1234",
                parcel_id="12-34-56-7890-12-345",
                sale_date="12/18/2025"
            )
        ]

        foreclosures = [
            ForeclosureProperty(
                borrowers_name="John Doe",
                parcel_number="123456789012345",
                default_amount=150000
            )
        ]

        property_records = [
            PropertyRecord(
                parcel_number="12-34-56-7890-12-345",
                total_mkt=250000,
                owner_name="John Doe"
            )
        ]

        result = deduplicator.merge_sources(
            tax_sales=tax_sales,
            foreclosures=foreclosures,
            property_records=property_records
        )

        assert len(result) == 1
        assert 'tax_sale' in result[0]
        assert 'foreclosure' in result[0]
        assert 'property_record' in result[0]

    def test_merge_different_parcels(self):
        """Test merging properties with different parcel IDs"""
        deduplicator = PropertyDeduplicator()

        tax_sales = [
            TaxSaleProperty(
                tda_number="2023-1111",
                parcel_id="111111111"
            ),
            TaxSaleProperty(
                tda_number="2023-2222",
                parcel_id="222222222"
            )
        ]

        result = deduplicator.merge_sources(tax_sales=tax_sales)

        assert len(result) == 2

    def test_resolve_coordinates_priority(self):
        """Test coordinate resolution with priority"""
        deduplicator = PropertyDeduplicator()

        merged_prop = {
            'tax_sale': {'latitude': 28.1, 'longitude': -81.1},
            'property_record': {'latitude': 28.5, 'longitude': -81.5}
        }

        lat, lon = deduplicator.resolve_coordinates(merged_prop)

        assert lat == 28.5
        assert lon == -81.5

    def test_resolve_coordinates_no_data(self):
        """Test coordinate resolution with no coordinates"""
        deduplicator = PropertyDeduplicator()

        merged_prop = {}

        lat, lon = deduplicator.resolve_coordinates(merged_prop)

        assert lat is None
        assert lon is None


class TestLeadScorer:
    """Tests for LeadScorer class"""

    def test_scorer_initialization(self):
        """Test that scorer initializes correctly"""
        scorer = LeadScorer()
        assert scorer is not None

    def test_score_lead_minimal_data(self):
        """Test scoring with minimal data"""
        scorer = LeadScorer()

        merged_prop = {
            'parcel_id_normalized': '123456789',
            'property_record': {
                'total_mkt': 200000,
                'equity_percent': 100
            }
        }

        result = scorer.score_lead(merged_prop)

        assert isinstance(result, LeadScore)
        assert 0 <= result.total_score <= 100
        assert result.tier in ['A', 'B', 'C', 'D']

    def test_score_lead_tax_sale_boost(self):
        """Test that tax sale status boosts distress score"""
        scorer = LeadScorer()

        prop_with_tax_sale = {
            'parcel_id_normalized': '123456789',
            'tax_sale': {
                'tda_number': '2023-1234',
                'sale_date': '12/18/2025'
            }
        }

        result = scorer.score_lead(prop_with_tax_sale)

        assert result.distress_score >= 40
        assert any('tax sale' in reason.lower() for reason in result.reasons)

    def test_score_lead_foreclosure_boost(self):
        """Test that foreclosure status boosts distress score"""
        scorer = LeadScorer()

        prop_with_foreclosure = {
            'parcel_id_normalized': '123456789',
            'foreclosure': {
                'borrowers_name': 'John Doe',
                'default_amount': 150000,
                'auction_date': '2024-06-01'
            }
        }

        result = scorer.score_lead(prop_with_foreclosure)

        assert result.distress_score >= 40
        assert any('foreclosure' in reason.lower() or 'auction' in reason.lower() for reason in result.reasons)

    def test_score_lead_high_equity(self):
        """Test that high equity boosts value score"""
        scorer = LeadScorer()

        prop_high_equity = {
            'parcel_id_normalized': '123456789',
            'property_record': {
                'total_mkt': 300000,
                'equity_percent': 250
            }
        }

        result = scorer.score_lead(prop_high_equity)

        assert result.value_score > 30
        assert any('equity' in reason.lower() for reason in result.reasons)

    def test_score_lead_violations(self):
        """Test that violations affect distress and location scores"""
        scorer = LeadScorer()

        prop_with_violations = {
            'parcel_id_normalized': '123456789',
            'enrichment': {
                'nearby_violations': 25,
                'nearby_open_violations': 5,
                'nearest_violation_distance': 0.1
            }
        }

        result = scorer.score_lead(prop_with_violations)

        assert result.distress_score > 0
        assert any('violation' in reason.lower() for reason in result.reasons)

    def test_tier_determination(self):
        """Test lead tier assignment"""
        scorer = LeadScorer()

        assert scorer._determine_tier(80) == "A"
        assert scorer._determine_tier(65) == "B"
        assert scorer._determine_tier(45) == "C"
        assert scorer._determine_tier(30) == "D"

    def test_rank_leads(self):
        """Test lead ranking by score"""
        scorer = LeadScorer()

        prop1 = {'parcel_id_normalized': '111'}
        score1 = LeadScore(
            total_score=85.0, distress_score=40, value_score=30,
            location_score=50, urgency_score=40, tier="A", reasons=[]
        )

        prop2 = {'parcel_id_normalized': '222'}
        score2 = LeadScore(
            total_score=45.0, distress_score=20, value_score=20,
            location_score=50, urgency_score=10, tier="C", reasons=[]
        )

        prop3 = {'parcel_id_normalized': '333'}
        score3 = LeadScore(
            total_score=65.0, distress_score=30, value_score=25,
            location_score=50, urgency_score=20, tier="B", reasons=[]
        )

        leads = [(prop1, score1), (prop2, score2), (prop3, score3)]

        ranked = scorer.rank_leads(leads)

        assert ranked[0][1].total_score == 85.0
        assert ranked[1][1].total_score == 65.0
        assert ranked[2][1].total_score == 45.0

    def test_score_lead_comprehensive(self):
        """Test scoring with comprehensive data"""
        scorer = LeadScorer()

        comprehensive_prop = {
            'parcel_id_normalized': '123456789',
            'tax_sale': {
                'tda_number': '2023-1234',
                'sale_date': '12/18/2025'
            },
            'foreclosure': {
                'borrowers_name': 'Jane Doe',
                'default_amount': 200000,
                'auction_date': '2024-06-15'
            },
            'property_record': {
                'total_mkt': 300000,
                'total_assd': 150000,
                'equity_percent': 200,
                'taxes': 4000,
                'living_area': 1800
            },
            'enrichment': {
                'nearby_violations': 15,
                'nearby_open_violations': 3,
                'nearest_violation_distance': 0.15
            }
        }

        result = scorer.score_lead(comprehensive_prop)

        assert result.total_score > 60
        assert result.distress_score > 40
        assert result.value_score > 20
        assert result.tier in ['A', 'B']
        assert len(result.reasons) > 3

    def test_urgency_score_auction(self):
        """Test urgency score with auction date"""
        scorer = LeadScorer()

        prop_with_auction = {
            'parcel_id_normalized': '123456789',
            'foreclosure': {
                'auction_date': '2024-06-01'
            }
        }

        result = scorer.score_lead(prop_with_auction)

        assert result.urgency_score >= 50
