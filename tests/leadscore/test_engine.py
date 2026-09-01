"""
Tests for the asset-agnostic scoring engine.

These use deliberately non-property assets. The engine's value is that it does
not know what it is scoring, so exercising it only through the real estate
profile would not demonstrate that.
"""
import pytest

from src.leadscore import Bonus, Bucket, GateResult, ScoringEngine, TierBands


def const(value):
    """A bucket extractor returning a fixed sub-score."""
    return lambda record, gate: value


BANDS = TierBands(bands=(("A", 70), ("B", 40)), fallback="C")


class TestConfiguration:
    def test_rejects_weights_that_do_not_sum_to_one(self):
        with pytest.raises(ValueError, match="must sum to 1"):
            ScoringEngine(
                buckets=[Bucket("a", 0.5, const(0)), Bucket("b", 0.2, const(0))],
                tiers=BANDS,
            )

    def test_rejects_duplicate_bucket_names(self):
        with pytest.raises(ValueError, match="unique"):
            ScoringEngine(
                buckets=[Bucket("a", 0.5, const(0)), Bucket("a", 0.5, const(0))],
                tiers=BANDS,
            )

    def test_rejects_no_buckets(self):
        with pytest.raises(ValueError, match="at least one bucket"):
            ScoringEngine(buckets=[], tiers=BANDS)

    def test_accepts_weights_with_floating_point_error(self):
        """Thirds do not sum to exactly 1 in binary floating point."""
        third = 1 / 3
        engine = ScoringEngine(
            buckets=[
                Bucket("a", third, const(60)),
                Bucket("b", third, const(60)),
                Bucket("c", third, const(60)),
            ],
            tiers=BANDS,
        )
        assert engine.score({}).total_score == pytest.approx(60)


class TestScoring:
    def test_weighted_sum(self):
        engine = ScoringEngine(
            buckets=[Bucket("a", 0.75, const(100)), Bucket("b", 0.25, const(0))],
            tiers=BANDS,
        )
        assert engine.score({}).total_score == pytest.approx(75)

    def test_sub_scores_are_clamped_to_the_scoring_range(self):
        engine = ScoringEngine(
            buckets=[Bucket("over", 0.5, const(500)), Bucket("under", 0.5, const(-500))],
            tiers=BANDS,
        )
        result = engine.score({})
        assert result.bucket_scores == {"over": 100.0, "under": 0.0}
        assert result.total_score == pytest.approx(50)

    def test_extractors_receive_the_record(self):
        engine = ScoringEngine(
            buckets=[Bucket("mileage", 1.0, lambda r, g: r["miles"] / 1000)],
            tiers=BANDS,
        )
        assert engine.score({"miles": 42_000}).total_score == pytest.approx(42)

    def test_total_is_clamped_after_bonuses(self):
        engine = ScoringEngine(
            buckets=[Bucket("a", 1.0, const(95))],
            tiers=BANDS,
            bonuses=[Bonus("urgent", 20, lambda r: True)],
        )
        assert engine.score({}).total_score == 100.0

    def test_bonuses_only_fire_when_they_apply(self):
        engine = ScoringEngine(
            buckets=[Bucket("a", 1.0, const(50))],
            tiers=BANDS,
            bonuses=[
                Bonus("recalled", 10, lambda r: r.get("recalled", False)),
                Bonus("one_owner", 5, lambda r: r.get("owners") == 1),
            ],
        )

        plain = engine.score({"owners": 3})
        assert plain.total_score == pytest.approx(50)
        assert plain.bonuses_applied == ()

        both = engine.score({"recalled": True, "owners": 1})
        assert both.total_score == pytest.approx(65)
        assert both.bonuses_applied == ("recalled", "one_owner")

    def test_negative_bonus_is_a_penalty(self):
        engine = ScoringEngine(
            buckets=[Bucket("a", 1.0, const(50))],
            tiers=BANDS,
            bonuses=[Bonus("salvage_title", -30, lambda r: True)],
        )
        assert engine.score({}).total_score == pytest.approx(20)


class TestViabilityGate:
    class RejectingGate:
        def evaluate(self, record):
            return GateResult(viable=False, detail={"reason": "below reserve"})

    class AcceptingGate:
        def evaluate(self, record):
            return GateResult(viable=True, detail={"margin": 4200})

    def test_without_a_gate_everything_is_viable(self):
        engine = ScoringEngine(buckets=[Bucket("a", 1.0, const(90))], tiers=BANDS)
        result = engine.score({})
        assert result.gate.viable is True
        assert result.tier == "A"

    def test_failing_the_gate_selects_the_restricted_bands(self):
        engine = ScoringEngine(
            buckets=[Bucket("a", 1.0, const(90))],
            tiers=BANDS,
            gate=self.RejectingGate(),
            non_viable_tiers=TierBands(bands=(("B", 80),), fallback="C"),
        )
        result = engine.score({})

        assert result.total_score == pytest.approx(90)
        assert result.tier == "B", "a non-viable lead must not reach the top tier"
        assert result.gate.detail["reason"] == "below reserve"

    def test_gate_detail_reaches_the_extractors(self):
        """A bucket can score off the gate's work instead of redoing it."""
        engine = ScoringEngine(
            buckets=[Bucket("margin", 1.0, lambda r, g: g.detail["margin"] / 100)],
            tiers=BANDS,
            gate=self.AcceptingGate(),
        )
        assert engine.score({}).total_score == pytest.approx(42)

    def test_gate_verdict_is_reported_without_capping_by_default(self):
        engine = ScoringEngine(
            buckets=[Bucket("a", 1.0, const(90))],
            tiers=BANDS,
            gate=self.RejectingGate(),
        )
        result = engine.score({})
        assert result.gate.viable is False
        assert result.tier == "A"


def test_scores_an_asset_class_the_engine_has_never_heard_of():
    """A worked example: overdue invoices, nothing to do with property."""
    engine = ScoringEngine(
        buckets=[
            Bucket("age", 0.6, lambda r, g: r["days_overdue"] / 1.8),
            Bucket("size", 0.4, lambda r, g: r["amount"] / 1000),
        ],
        tiers=TierBands(bands=(("chase_now", 60), ("monitor", 30)), fallback="write_off"),
        gate=type("Recoverable", (), {
            "evaluate": lambda self, r: GateResult(
                viable=not r.get("debtor_insolvent", False), detail={}
            )
        })(),
        non_viable_tiers=TierBands(bands=(), fallback="write_off"),
    )

    urgent = engine.score({"days_overdue": 180, "amount": 50_000})
    assert urgent.tier == "chase_now"

    insolvent = engine.score(
        {"days_overdue": 180, "amount": 50_000, "debtor_insolvent": True}
    )
    assert insolvent.tier == "write_off", "an unrecoverable debt is never worth chasing"
