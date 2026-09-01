import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.scoring import HybridBucketScorer, LogisticOpportunityScorer


@pytest.fixture
def violation_only_record():
    return {
        "seed_type": "code_violation",
        "violation_count": 12,
        "open_violations": 5,
        "most_recent_violation": "2025-01-10",
        "property_record": {"equity_percent": 160, "total_mkt": 210000},
    }


@pytest.fixture
def tax_sale_record():
    """A tax sale worth buying: a $40k opening bid against a $300k ARV."""
    return {
        "seed_type": "tax_sale",
        "tax_sale": {"tda_number": "2024-001", "opening_bid": 40000},
        "violation_count": 2,
        "property_record": {
            "equity_percent": 220,
            "total_mkt": 300000,
            "living_area": 1500,
            "year_built": 1995,
        },
    }


@pytest.fixture
def underwater_tax_sale_record():
    """The same seed type, but the debt matches the market value."""
    return {
        "seed_type": "tax_sale",
        "tax_sale": {"tda_number": "2024-002"},
        "foreclosure": {"default_amount": 180000},
        "violation_count": 2,
        "property_record": {"equity_percent": 220, "total_mkt": 180000},
    }


def test_hybrid_bucket_scorer_promotes_profitable_tax_sale(tax_sale_record):
    scorer = HybridBucketScorer()
    result = scorer.score(tax_sale_record)

    assert result["profitability"]["is_profitable"] is True
    assert result["tier"] == "A"


def test_hybrid_bucket_scorer_guardrail_blocks_unprofitable_leads(
    violation_only_record, underwater_tax_sale_record
):
    """Distress alone must not earn Tier A - the profitability guardrail wins.

    The violation record scores maximum distress (12 violations, 5 open) and the
    tax sale carries a judgment equal to its market value. Neither can be
    resold at a profit, so neither may reach the tiers the pipeline acts on.
    """
    scorer = HybridBucketScorer()

    for record in (violation_only_record, underwater_tax_sale_record):
        result = scorer.score(record)
        assert result["profitability"]["is_profitable"] is False
        assert result["tier"] not in {"A", "B"}


def test_logistic_scorer_probabilities(violation_only_record, tax_sale_record):
    scorer = LogisticOpportunityScorer()
    violation_score = scorer.score(violation_only_record)
    tax_score = scorer.score(tax_sale_record)

    assert 0 <= violation_score["probability"] <= 1
    assert tax_score["probability"] > violation_score["probability"]
    assert violation_score["tier"] in {"B", "C", "D"}
