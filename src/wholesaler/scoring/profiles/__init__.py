"""
Asset profiles: the asset-specific half of scoring.

A profile supplies the buckets, bonuses, viability gate and tier bands that
configure a :class:`src.leadscore.ScoringEngine`. Adding an asset class means
adding a profile here, not changing the engine.

    real_estate    distressed residential - scores property distress
    dental_office  dentist-owned commercial - scores owner exit

The two share no constants and no vocabulary; only the engine.
"""
from src.wholesaler.scoring.profiles import dental_office, real_estate
from src.wholesaler.scoring.profiles.real_estate import build_engine

__all__ = ["build_engine", "dental_office", "real_estate"]
