"""
The scoring engine.

One pass, fixed shape, no knowledge of any asset class:

    signals -> weighted bucket sub-scores -> bonuses -> viability gate -> tier

Everything specific to what is being scored - which fields carry signal, how
they map to a sub-score, what makes a lead worth acting on, where the tier
boundaries sit - is supplied by an asset profile as buckets, bonuses, a gate and
tier bands. Scoring a different kind of asset means writing a profile, not
editing this module.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from src.leadscore.tiers import TierBands
from src.leadscore.types import (
    Bonus,
    Bucket,
    GateResult,
    Record,
    ScoreResult,
    ViabilityGate,
    clamp,
)

# Bucket weights are a proportion of the final score, so they must sum to 1.
# Floating point makes exact equality unreliable, hence a tolerance.
WEIGHT_TOLERANCE = 1e-6


class ScoringEngine:
    """
    Scores records against one asset profile.

    Args:
        buckets: Weighted components. Weights must sum to 1.
        tiers: Bands applied to a viable record's score.
        gate: Viability check. When omitted every record is treated as viable.
        bonuses: Flat adjustments applied after the weighted sum.
        non_viable_tiers: Bands applied when the gate fails. Defaults to
            ``tiers``, meaning the gate records its verdict without capping the
            tier; a profile that wants a hard ceiling passes
            ``tiers.capped_at("C")`` or similar.

    Raises:
        ValueError: If no buckets are given, bucket names repeat, or the weights
            do not sum to 1 - each of which would make scores incomparable
            between profiles.
    """

    def __init__(
        self,
        buckets: Sequence[Bucket],
        tiers: TierBands,
        gate: Optional[ViabilityGate] = None,
        bonuses: Iterable[Bonus] = (),
        non_viable_tiers: Optional[TierBands] = None,
    ) -> None:
        if not buckets:
            raise ValueError("A scoring engine needs at least one bucket")

        names = [bucket.name for bucket in buckets]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"Bucket names must be unique; repeated: {duplicates}")

        total_weight = sum(bucket.weight for bucket in buckets)
        if abs(total_weight - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError(
                f"Bucket weights must sum to 1, got {total_weight} from "
                + ", ".join(f"{b.name}={b.weight}" for b in buckets)
            )

        self.buckets = tuple(buckets)
        self.tiers = tiers
        self.gate = gate
        self.bonuses = tuple(bonuses)
        self.non_viable_tiers = non_viable_tiers or tiers

    @property
    def bucket_names(self) -> Sequence[str]:
        """Names of this engine's buckets, in weighting order."""
        return [bucket.name for bucket in self.buckets]

    def score(self, record: Record) -> ScoreResult:
        """
        Score one record.

        The gate runs first and its result is handed to every extractor, so a
        bucket that scores off viability evidence reuses that work instead of
        recomputing it.

        Args:
            record: The record to score.

        Returns:
            The score, tier, per-bucket sub-scores and gate verdict.
        """
        gate_result = self.gate.evaluate(record) if self.gate else GateResult(viable=True)

        bucket_scores = {
            bucket.name: clamp(bucket.extract(record, gate_result))
            for bucket in self.buckets
        }

        total = sum(bucket_scores[bucket.name] * bucket.weight for bucket in self.buckets)

        applied = []
        for bonus in self.bonuses:
            if bonus.applies(record):
                total += bonus.points
                applied.append(bonus.name)

        total = clamp(total)
        bands = self.tiers if gate_result.viable else self.non_viable_tiers

        return ScoreResult(
            total_score=total,
            tier=bands.band(total),
            bucket_scores=bucket_scores,
            bonuses_applied=tuple(applied),
            gate=gate_result,
        )
