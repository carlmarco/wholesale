"""
Parity between HybridBucketScorer and the scoring engine it now delegates to.

The scorer was refactored into an asset-agnostic engine plus a real estate
profile. Its scores decide which leads the pipeline surfaces, so the refactor
had to be exactly behaviour-preserving. scoring_golden.json holds outputs
captured from the original implementation across a grid of records covering
every tier; this pins them.

Regenerating the fixture is only correct when the model is deliberately being
retuned. A diff here otherwise means the refactor changed the model.
"""
import json
from pathlib import Path

import pytest

from src.wholesaler.scoring import HybridBucketScorer, LogisticOpportunityScorer

GOLDEN = json.loads((Path(__file__).parent / "scoring_golden.json").read_text())


@pytest.fixture(scope="module")
def hybrid():
    return HybridBucketScorer()


@pytest.fixture(scope="module")
def logistic():
    return LogisticOpportunityScorer()


def test_golden_corpus_covers_every_tier():
    """A corpus that misses a tier would not exercise the guardrail."""
    tiers = {case["hybrid"]["tier"] for case in GOLDEN}
    assert tiers == {"A", "B", "C", "D"}


@pytest.mark.parametrize("case", GOLDEN, ids=range(len(GOLDEN)))
def test_hybrid_scores_match_the_original(hybrid, case):
    result = hybrid.score(case["record"])
    expected = case["hybrid"]

    assert result["total_score"] == pytest.approx(expected["total_score"])
    assert result["tier"] == expected["tier"]
    assert result["profitability"] == expected["profitability"]

    for name, value in expected["buckets"].items():
        assert getattr(result["bucket_scores"], name) == pytest.approx(value), name


@pytest.mark.parametrize("case", GOLDEN, ids=range(len(GOLDEN)))
def test_logistic_scores_match_the_original(logistic, case):
    result = logistic.score(case["record"])
    expected = case["logistic"]

    assert result["probability"] == pytest.approx(expected["probability"])
    assert result["score"] == pytest.approx(expected["score"])
    assert result["tier"] == expected["tier"]


def test_scorer_still_returns_attribute_style_bucket_scores(hybrid):
    """The API router and scoring script read bucket_scores by attribute."""
    result = hybrid.score(GOLDEN[0]["record"])
    buckets = result["bucket_scores"]

    for name in ("distress", "disposition", "equity", "profitability"):
        # int or float, matching what the original scorer produced
        assert isinstance(getattr(buckets, name), (int, float)), name
