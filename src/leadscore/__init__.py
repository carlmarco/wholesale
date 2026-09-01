"""
Asset-agnostic lead scoring.

A scoring engine plus the pieces an asset profile supplies to configure it:

    signals -> weighted bucket sub-scores -> bonuses -> viability gate -> tier

This package knows nothing about property, vehicles, invoices or anything else.
An asset profile provides the buckets, bonuses, viability gate and tier bands;
the engine composes them. Scoring a new kind of asset means writing a profile,
not changing this package.

The real estate profile that reproduces the wholesaler's original scoring lives
in ``src.wholesaler.scoring.profiles.real_estate`` and is a worked example of
what a profile contains.
"""
from src.leadscore.engine import ScoringEngine
from src.leadscore.tiers import TierBands
from src.leadscore.types import (
    Bonus,
    Bucket,
    Extractor,
    GateResult,
    Record,
    ScoreResult,
    ViabilityGate,
    clamp,
)

__all__ = [
    "Bonus",
    "Bucket",
    "Extractor",
    "GateResult",
    "Record",
    "ScoreResult",
    "ScoringEngine",
    "TierBands",
    "ViabilityGate",
    "clamp",
]
