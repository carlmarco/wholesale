"""
Core types for the scoring engine.

Nothing here knows what an asset is. A record is any mapping; what to read out
of it lives in the extractors an asset profile supplies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

# A record is whatever the caller's pipeline produces. The engine never reads a
# field itself - only the profile's extractors do.
Record = Mapping[str, Any]

SCORE_MIN = 0.0
SCORE_MAX = 100.0


def clamp(value: float, low: float = SCORE_MIN, high: float = SCORE_MAX) -> float:
    """Constrain a value to the scoring range."""
    return max(low, min(high, value))


@dataclass(frozen=True)
class GateResult:
    """
    The outcome of a viability check.

    A lead can score well on its signals and still be one nobody should act on -
    a property that cannot be resold at a profit, an invoice past recovery. The
    gate expresses that judgement separately from the score, so a profile can cap
    the tier of a non-viable lead without distorting the signal weights.

    Attributes:
        viable: Whether the lead passes the profile's viability rule.
        detail: Profile-specific evidence, surfaced to callers unchanged.
    """
    viable: bool
    detail: Mapping[str, Any] = field(default_factory=dict)


class ViabilityGate(Protocol):
    """Decides whether a record is worth acting on at all."""

    def evaluate(self, record: Record) -> GateResult:
        ...


# Extractors receive the gate result so a bucket can score off viability
# evidence without recomputing it.
Extractor = Callable[[Record, GateResult], float]


@dataclass(frozen=True)
class Bucket:
    """
    One weighted component of a score.

    Attributes:
        name: Identifier used in results and weight configuration.
        weight: Share of the total score, as a fraction. Weights across a
            profile's buckets must sum to 1.
        extract: Reads the record and returns a 0-100 sub-score. Values outside
            that range are clamped, so extractors may compute freely.
    """
    name: str
    weight: float
    extract: Extractor


@dataclass(frozen=True)
class Bonus:
    """
    A flat adjustment applied after the weighted sum.

    Bonuses express "this signal matters beyond its bucket" without distorting
    bucket weights. Points may be negative.
    """
    name: str
    points: float
    applies: Callable[[Record], bool]


@dataclass(frozen=True)
class ScoreResult:
    """
    What the engine returns.

    Attributes:
        total_score: Final 0-100 score after weighting, bonuses and clamping.
        tier: Band label for total_score, from the bands the gate selected.
        bucket_scores: Each bucket's sub-score by name.
        bonuses_applied: Names of the bonuses that fired.
        gate: The viability result, including the profile's evidence.
    """
    total_score: float
    tier: str
    bucket_scores: Mapping[str, float]
    bonuses_applied: Sequence[str]
    gate: GateResult
