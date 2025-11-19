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
    return {
        "seed_type": "tax_sale",
        "tax_sale": {"tda_number": "2024-001"},
        "foreclosure": {"default_amount": 180000},
        "violation_count": 2,
        "property_record": {"equity_percent": 220, "total_mkt": 180000},
    }


def test_hybrid_bucket_scorer_rankings(violation_only_record, tax_sale_record):
    scorer = HybridBucketScorer()
    violation_score = scorer.score(violation_only_record)
    tax_score = scorer.score(tax_sale_record)

    assert violation_score["tier"] in {"A", "B", "C"}
    assert tax_score["tier"] == "A"
    assert tax_score["total_score"] > violation_score["total_score"]


def test_logistic_scorer_probabilities(violation_only_record, tax_sale_record):
    scorer = LogisticOpportunityScorer()
    violation_score = scorer.score(violation_only_record)
    tax_score = scorer.score(tax_sale_record)

    assert 0 <= violation_score["probability"] <= 1
    assert tax_score["probability"] > violation_score["probability"]
    assert violation_score["tier"] in {"B", "C", "D"}
