"""
Helpers for computing basic data-quality metrics.
"""
from __future__ import annotations

from typing import List, Dict
import pandas as pd

from src.wholesaler.ingestion.seed_models import SeedRecord


def compute_seed_metrics(seeds: List[SeedRecord]) -> Dict[str, Dict[str, int]]:
    """Return count of seeds per type and with parcel IDs."""
    df = pd.DataFrame([seed.to_dict() for seed in seeds])
    if df.empty:
        return {"counts": {}, "with_parcel_id": {}}

    counts = df["seed_type"].value_counts().to_dict()
    with_parcel = (
        df[df["parcel_id"].notna()]
        .groupby("seed_type")["parcel_id"]
        .count()
        .to_dict()
    )
    return {"counts": counts, "with_parcel_id": with_parcel}
