"""
Tests for the feasibility evaluation.

The property that makes this harness worth trusting is that it says "no signal"
when there is none. A harness that finds signal in noise would repeat exactly
the mistake it exists to catch, so those cases are tested first.
"""
import random
from datetime import date

import pytest

from src.wholesaler.feasibility.evaluate import (
    MIN_COHORT_SIZE,
    MIN_POSITIVES,
    evaluate,
)
from src.wholesaler.feasibility.outcomes import CohortMember, LabelledMember


def cohort(pairs):
    """Build a labelled cohort from (score, sold) pairs."""
    return [
        LabelledMember(
            member=CohortMember(
                parcel_id_normalized=str(index), as_of=date(2024, 1, 1), score=score
            ),
            sold=sold,
            sale_date=date(2024, 3, 1) if sold else None,
        )
        for index, (score, sold) in enumerate(pairs)
    ]


def random_cohort(size, base_rate, seed):
    """Scores unrelated to outcomes - the null case."""
    rng = random.Random(seed)
    return cohort(
        [(rng.uniform(0, 100), rng.random() < base_rate) for _ in range(size)]
    )


def ranked_cohort(size, base_rate, seed, strength=1.0):
    """Scores that genuinely carry signal, for the positive control."""
    rng = random.Random(seed)
    pairs = []
    for _ in range(size):
        score = rng.uniform(0, 100)
        probability = base_rate * (1 - strength) + strength * (score / 100) * base_rate * 4
        pairs.append((score, rng.random() < min(1.0, probability)))
    return cohort(pairs)


class TestUnderpoweredCohorts:
    def test_small_cohort_is_refused_not_judged(self):
        report = evaluate(random_cohort(50, 0.3, seed=1), horizon_days=180)
        assert report.verdict == "insufficient data"
        assert str(MIN_COHORT_SIZE) in report.reasoning
        assert report.is_conclusive is False

    def test_too_few_positives_is_refused(self):
        """A large cohort with almost no events still cannot answer anything."""
        pairs = [(float(i), i < 5) for i in range(400)]
        report = evaluate(cohort(pairs), horizon_days=180)
        assert report.verdict == "insufficient data"
        assert str(MIN_POSITIVES) in report.reasoning

    def test_no_positives_at_all(self):
        report = evaluate(cohort([(float(i), False) for i in range(300)]), horizon_days=180)
        assert report.verdict == "insufficient data"
        assert report.base_rate == 0.0
        assert report.auc is None


class TestNullCase:
    def test_random_scores_do_not_produce_a_signal_verdict(self):
        """The property that makes the harness trustworthy."""
        report = evaluate(random_cohort(600, 0.25, seed=7), horizon_days=180)
        assert report.verdict == "no signal"
        assert not any(result.beats_chance for result in report.lift_at_k)

    @pytest.mark.slow
    def test_random_scores_stay_null_across_seeds(self):
        """One lucky seed should not be able to manufacture a positive."""
        verdicts = [
            evaluate(random_cohort(600, 0.25, seed=seed), horizon_days=180).verdict
            for seed in range(12)
        ]
        assert verdicts.count("signal") == 0, verdicts

    def test_null_case_auc_interval_contains_one_half(self):
        report = evaluate(random_cohort(800, 0.25, seed=3), horizon_days=180)
        assert report.auc.low <= 0.5 <= report.auc.high

    def test_a_lucky_budget_alone_does_not_make_a_verdict(self):
        """Regression: this cohort was once reported as signal.

        Its AUC is 0.512 with an interval spanning 0.5 - pure noise - but one of
        four action budgets had a lift interval just clearing 1.0. Testing four
        budgets at 90% and accepting any of them gives a false positive about a
        third of the time, so the budgets are Bonferroni-adjusted and AUC has to
        agree before anything is called signal.
        """
        rng = random.Random(4)
        pairs = []
        for _ in range(600):
            rng.randrange(400)  # the date draw, kept so the stream matches
            score = rng.uniform(0, 100)
            pairs.append((score, rng.random() < 0.22))

        report = evaluate(cohort(pairs), horizon_days=180)

        assert report.auc.low <= 0.5 <= report.auc.high, "cohort must be genuine noise"
        assert report.verdict == "no signal"

    def test_lift_without_auc_agreement_is_reported_as_noise(self):
        """The reasoning should name why a lifted budget was not enough."""
        rng = random.Random(4)
        pairs = []
        for _ in range(600):
            rng.randrange(400)
            score = rng.uniform(0, 100)
            pairs.append((score, rng.random() < 0.22))

        report = evaluate(cohort(pairs), horizon_days=180, budgets=(25,))

        if any(result.beats_chance for result in report.lift_at_k):
            assert report.verdict == "no signal"
            assert "what noise looks like" in report.reasoning


class TestSignalCase:
    def test_a_genuinely_predictive_score_is_detected(self):
        report = evaluate(ranked_cohort(800, 0.2, seed=11), horizon_days=180)
        assert report.verdict == "signal"
        assert report.auc.point > 0.5

    def test_perfect_ranking_beats_chance_at_every_budget(self):
        pairs = [(float(i), i >= 700) for i in range(800)]
        report = evaluate(cohort(pairs), horizon_days=180)

        assert report.verdict == "signal"
        assert all(result.beats_chance for result in report.lift_at_k)
        assert report.lift_at_k[0].precision.point == 1.0


class TestReportedNumbers:
    def test_base_rate_and_counts(self):
        pairs = [(float(i), i % 4 == 0) for i in range(400)]
        report = evaluate(cohort(pairs), horizon_days=90)

        assert report.cohort_size == 400
        assert report.positives == 100
        assert report.base_rate == 0.25
        assert report.horizon_days == 90

    def test_budgets_larger_than_the_cohort_are_dropped(self):
        report = evaluate(random_cohort(300, 0.3, seed=2), horizon_days=180)
        assert [result.k for result in report.lift_at_k] == [10, 25, 50, 100]

        smaller = evaluate(random_cohort(220, 0.3, seed=2), horizon_days=180, budgets=(10, 500))
        assert [result.k for result in smaller.lift_at_k] == [10]

    def test_intervals_bracket_their_point_estimate(self):
        report = evaluate(ranked_cohort(600, 0.2, seed=5), horizon_days=180)
        for result in report.lift_at_k:
            assert result.precision.low <= result.precision.point <= result.precision.high

    def test_is_reproducible(self):
        data = ranked_cohort(500, 0.2, seed=9)
        first = evaluate(data, horizon_days=180)
        second = evaluate(data, horizon_days=180)

        assert first.verdict == second.verdict
        assert [r.lift.low for r in first.lift_at_k] == [r.lift.low for r in second.lift_at_k]


class TestTieHandling:
    def test_tied_scores_do_not_inflate_auc(self):
        """Heuristic scores tie constantly; counting ties as wins fakes signal."""
        pairs = [(50.0, index % 2 == 0) for index in range(400)]
        report = evaluate(cohort(pairs), horizon_days=180)

        assert report.auc.point == 0.5
        assert report.verdict == "no signal"
