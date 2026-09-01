"""
Tests for historical cohort reconstruction.

The reconstruction exists to answer a question about the past without letting
the present leak into it. Most of these tests are about that boundary: a
violation filed after the event, a tax roll certified after the event, a second
distress event that had not happened yet - none of them may reach the record
that gets scored.
"""
from datetime import date

import pytest

from src.wholesaler.feasibility.reconstruct import (
    CODE_VIOLATION,
    FORECLOSURE,
    TAX_SALE,
    DistressEvent,
    Valuation,
    ViolationRecord,
    build_record,
    reconstruct_cohort,
    valuation_as_of,
)


class RecordingScorer:
    """Captures the records it is asked to score."""

    def __init__(self, score=50.0, tier="C"):
        self.records = []
        self._score = score
        self._tier = tier

    def score(self, record):
        self.records.append(record)
        return {"total_score": self._score, "tier": self._tier}


def event(parcel="1", when=date(2022, 6, 1), kind=TAX_SALE, **kwargs):
    return DistressEvent(
        parcel_id_normalized=parcel, event_date=when, event_type=kind, **kwargs
    )


def violation(parcel="1", filed=date(2022, 1, 1), closed=None):
    return ViolationRecord(parcel_id_normalized=parcel, filed_on=filed, closed_on=closed)


def valuation(parcel="1", year=2022, market=300_000.0):
    return Valuation(
        parcel_id_normalized=parcel,
        roll_year=year,
        total_mkt=market,
        living_area=1500,
        year_built=1995,
    )


class TestEventValidation:
    def test_rejects_an_unknown_event_type(self):
        with pytest.raises(ValueError, match="unknown event_type"):
            DistressEvent(
                parcel_id_normalized="1", event_date=date(2022, 1, 1), event_type="auction"
            )

    def test_accepts_the_known_types(self):
        for kind in (TAX_SALE, FORECLOSURE, CODE_VIOLATION):
            assert event(kind=kind).event_type == kind


class TestViolationHistoryIsPointInTime:
    def test_counts_only_violations_filed_by_the_event_date(self):
        record = build_record(
            "1",
            date(2022, 6, 1),
            event(),
            [event()],
            [
                violation(filed=date(2021, 1, 1)),
                violation(filed=date(2022, 5, 1)),
                violation(filed=date(2022, 7, 1)),  # after the event
            ],
            None,
            have_close_dates=False,
        )
        assert record["violation_count"] == 2

    def test_most_recent_violation_is_the_latest_prior_one(self):
        record = build_record(
            "1",
            date(2022, 6, 1),
            event(),
            [event()],
            [violation(filed=date(2021, 1, 1)), violation(filed=date(2022, 5, 1))],
            None,
            have_close_dates=False,
        )
        assert record["most_recent_violation"] == "2022-05-01"

    def test_a_violation_filed_on_the_event_date_counts(self):
        record = build_record(
            "1", date(2022, 6, 1), event(), [event()],
            [violation(filed=date(2022, 6, 1))], None, have_close_dates=False,
        )
        assert record["violation_count"] == 1

    def test_open_counts_use_the_status_on_the_event_date(self):
        """A case closed after the event was open at the time."""
        record = build_record(
            "1",
            date(2022, 6, 1),
            event(),
            [event()],
            [
                violation(filed=date(2021, 1, 1), closed=date(2021, 6, 1)),   # closed before
                violation(filed=date(2021, 2, 1), closed=date(2023, 1, 1)),   # closed after
                violation(filed=date(2021, 3, 1), closed=None),               # still open
            ],
            None,
            have_close_dates=True,
        )
        assert record["violation_count"] == 3
        assert record["open_violations"] == 2

    def test_without_close_dates_open_counts_stay_zero(self):
        """Current status cannot tell you a past status, so it is not guessed."""
        record = build_record(
            "1", date(2022, 6, 1), event(), [event()],
            [violation(filed=date(2021, 1, 1))], None, have_close_dates=False,
        )
        assert record["violation_count"] == 1
        assert record["open_violations"] == 0

    def test_no_violations_yields_no_recency_signal(self):
        record = build_record(
            "1", date(2022, 6, 1), event(), [event()], [], None, have_close_dates=False
        )
        assert record["violation_count"] == 0
        assert record["most_recent_violation"] is None


class TestValuationIsPointInTime:
    def test_uses_the_latest_roll_certified_by_the_event_year(self):
        rolls = [valuation(year=2020, market=200_000), valuation(year=2021, market=250_000)]
        chosen = valuation_as_of(rolls, date(2022, 6, 1))
        assert chosen.roll_year == 2021

    def test_never_uses_a_later_roll(self):
        """The roll after a sale reflects that sale - using it leaks the label."""
        rolls = [valuation(year=2023, market=400_000)]
        assert valuation_as_of(rolls, date(2022, 6, 1)) is None

    def test_the_event_year_roll_is_eligible(self):
        rolls = [valuation(year=2022, market=300_000)]
        assert valuation_as_of(rolls, date(2022, 6, 1)).roll_year == 2022

    def test_valuation_fields_reach_the_record(self):
        record = build_record(
            "1", date(2022, 6, 1), event(), [event()], [],
            valuation(year=2021, market=275_000), have_close_dates=False,
        )
        assert record["property_record"]["total_mkt"] == 275_000
        assert record["property_record"]["living_area"] == 1500

    def test_missing_valuation_leaves_the_record_empty_not_guessed(self):
        record = build_record(
            "1", date(2022, 6, 1), event(), [event()], [], None, have_close_dates=False
        )
        assert record["property_record"] == {}


class TestPriorEventsArePointInTime:
    def test_a_later_event_is_not_visible(self):
        events = [
            event(kind=TAX_SALE, when=date(2022, 6, 1)),
            event(kind=FORECLOSURE, when=date(2023, 1, 1)),
        ]
        record = build_record(
            "1", date(2022, 6, 1), events[0], events, [], None, have_close_dates=False
        )
        assert record["tax_sale"]
        assert record["foreclosure"] == {}

    def test_an_earlier_event_is_visible(self):
        events = [
            event(kind=FORECLOSURE, when=date(2021, 1, 1), default_amount=180_000),
            event(kind=TAX_SALE, when=date(2022, 6, 1)),
        ]
        record = build_record(
            "1", date(2022, 6, 1), events[1], events, [], None, have_close_dates=False
        )
        assert record["foreclosure"]["default_amount"] == 180_000
        assert record["tax_sale"]

    def test_event_attributes_are_carried_through(self):
        events = [event(kind=TAX_SALE, when=date(2022, 6, 1), opening_bid=40_000)]
        record = build_record(
            "1", date(2022, 6, 1), events[0], events, [], None, have_close_dates=False
        )
        assert record["tax_sale"]["opening_bid"] == 40_000

    def test_seed_type_is_the_event_that_created_the_member(self):
        record = build_record(
            "1", date(2022, 6, 1), event(kind=CODE_VIOLATION), [event(kind=CODE_VIOLATION)],
            [], None, have_close_dates=False,
        )
        assert record["seed_type"] == CODE_VIOLATION


class TestReconstruction:
    def test_scores_each_event_as_of_its_own_date(self):
        scorer = RecordingScorer()
        events = [
            event(parcel="1", when=date(2021, 3, 1)),
            event(parcel="2", when=date(2022, 9, 1)),
        ]
        members, _ = reconstruct_cohort(events, scorer)

        assert [member.as_of for member in members] == [date(2021, 3, 1), date(2022, 9, 1)]
        assert [member.score for member in members] == [50.0, 50.0]

    def test_keeps_the_earliest_event_per_parcel_by_default(self):
        scorer = RecordingScorer()
        events = [
            event(parcel="1", when=date(2022, 6, 1)),
            event(parcel="1", when=date(2021, 1, 1)),
            event(parcel="1", when=date(2023, 1, 1)),
        ]
        members, coverage = reconstruct_cohort(events, scorer)

        assert len(members) == 1
        assert members[0].as_of == date(2021, 1, 1)
        assert coverage.parcels_deduplicated == 2

    def test_all_events_can_be_kept_deliberately(self):
        scorer = RecordingScorer()
        events = [
            event(parcel="1", when=date(2022, 6, 1)),
            event(parcel="1", when=date(2021, 1, 1)),
        ]
        members, coverage = reconstruct_cohort(events, scorer, one_event_per_parcel=False)

        assert len(members) == 2
        assert coverage.parcels_deduplicated == 0

    def test_violation_history_from_other_parcels_does_not_bleed_across(self):
        scorer = RecordingScorer()
        members, _ = reconstruct_cohort(
            [event(parcel="1", when=date(2022, 6, 1))],
            scorer,
            violations=[violation(parcel="2", filed=date(2021, 1, 1))],
        )
        assert len(members) == 1
        assert scorer.records[0]["violation_count"] == 0

    def test_close_dates_are_detected_when_present(self):
        scorer = RecordingScorer()
        reconstruct_cohort(
            [event(parcel="1", when=date(2022, 6, 1))],
            scorer,
            violations=[violation(filed=date(2021, 1, 1), closed=date(2023, 1, 1))],
        )
        assert scorer.records[0]["open_violations"] == 1

    def test_prior_distress_counts_only_strictly_earlier_events(self):
        """A member's own event is not a prior event, however many fields it has."""
        single, coverage = reconstruct_cohort(
            [event(parcel="1", when=date(2022, 6, 1), opening_bid=40_000)],
            RecordingScorer(),
        )
        assert len(single) == 1
        assert coverage.with_prior_events == 0

        _, repeat_coverage = reconstruct_cohort(
            [
                event(parcel="2", when=date(2021, 1, 1), kind=FORECLOSURE),
                event(parcel="2", when=date(2022, 6, 1), kind=TAX_SALE),
            ],
            RecordingScorer(),
            one_event_per_parcel=False,
        )
        assert repeat_coverage.with_prior_events == 1, "only the later event has a prior"

    def test_tier_from_the_scorer_is_recorded(self):
        members, _ = reconstruct_cohort(
            [event()], RecordingScorer(score=72.0, tier="A")
        )
        assert members[0].tier == "A"
        assert members[0].score == 72.0


class TestCoverageReporting:
    def test_warns_when_no_valuations_were_supplied(self):
        _, coverage = reconstruct_cohort([event()], RecordingScorer())
        warnings = " ".join(coverage.warnings())

        assert "distress and disposition signals only" in warnings
        assert coverage.profitability_is_measurable is False

    def test_warns_when_valuations_cover_a_minority(self):
        events = [event(parcel=str(i), when=date(2022, 6, 1)) for i in range(10)]
        _, coverage = reconstruct_cohort(
            events, RecordingScorer(), valuations=[valuation(parcel="0", year=2021)]
        )
        warnings = " ".join(coverage.warnings())

        assert "minority of the cohort" in warnings
        assert coverage.profitability_is_measurable is False

    def test_no_valuation_warning_when_coverage_is_good(self):
        events = [event(parcel=str(i), when=date(2022, 6, 1)) for i in range(4)]
        valuations = [valuation(parcel=str(i), year=2021) for i in range(4)]
        _, coverage = reconstruct_cohort(events, RecordingScorer(), valuations=valuations)

        assert coverage.profitability_is_measurable is True
        assert not any("profitability" in warning for warning in coverage.warnings())

    def test_warns_when_close_dates_are_absent(self):
        _, coverage = reconstruct_cohort(
            [event()], RecordingScorer(), violations=[violation(filed=date(2021, 1, 1))]
        )
        assert any("close dates" in warning for warning in coverage.warnings())

    def test_warns_about_deduplication(self):
        events = [
            event(parcel="1", when=date(2021, 1, 1)),
            event(parcel="1", when=date(2022, 1, 1)),
        ]
        _, coverage = reconstruct_cohort(events, RecordingScorer())
        assert any("repeat events" in warning for warning in coverage.warnings())

    def test_reports_when_valuations_predate_no_event(self):
        """A roll that only exists after the event cannot be used."""
        _, coverage = reconstruct_cohort(
            [event(parcel="1", when=date(2020, 6, 1))],
            RecordingScorer(),
            valuations=[valuation(parcel="1", year=2023)],
        )
        assert coverage.valuation_years_missing == [2020]
        assert any("preceded these event years" in w for w in coverage.warnings())

    def test_empty_cohort_is_reported(self):
        _, coverage = reconstruct_cohort([], RecordingScorer())
        assert coverage.warnings() == ["The reconstruction produced no cohort members."]


class TestEndToEndWithTheRealScorer:
    def test_produces_scores_from_the_live_scoring_profile(self):
        """The cohort must carry the scorer's real output, not a stand-in."""
        from src.wholesaler.scoring import HybridBucketScorer

        events = [
            event(parcel="123456789001001", when=date(2022, 6, 1), opening_bid=40_000),
        ]
        violations = [
            violation(parcel="123456789001001", filed=date(2022, 1, 1), closed=date(2023, 1, 1)),
        ]
        valuations = [
            Valuation(
                parcel_id_normalized="123456789001001",
                roll_year=2021,
                total_mkt=300_000.0,
                living_area=1500,
                year_built=1995,
            )
        ]

        members, coverage = reconstruct_cohort(
            events, HybridBucketScorer(), violations=violations, valuations=valuations
        )

        assert len(members) == 1
        assert 0 <= members[0].score <= 100
        assert members[0].tier in {"A", "B", "C", "D"}
        assert coverage.with_valuation == 1
