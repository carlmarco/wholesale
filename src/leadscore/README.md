# leadscore

An asset-agnostic lead scoring engine.

```
signals -> weighted bucket sub-scores -> bonuses -> viability gate -> tier
```

The engine knows nothing about what it is scoring. Everything asset-specific —
which fields carry signal, how each maps to a sub-score, what makes a lead worth
acting on, where the tier boundaries sit — lives in an **asset profile**.

Scoring a new kind of asset means writing a profile, not editing this package.
`tests/leadscore/test_independence.py` enforces that: the package may not import
the application, pull in third-party dependencies, or name an asset concept.

## The pieces

| Piece | Role |
|---|---|
| `Bucket` | A weighted component. `extract(record, gate) -> 0..100`. Weights across a profile must sum to 1. |
| `Bonus` | A flat adjustment after the weighted sum, for a signal that matters beyond its bucket. Points may be negative. |
| `ViabilityGate` | Decides whether a lead is worth acting on at all, separately from how it scores. Returns `GateResult(viable, detail)`. |
| `TierBands` | Labelled score thresholds. A profile can supply different bands for leads that fail the gate. |
| `ScoringEngine` | Composes the above. One pass, no asset knowledge. |

## Why the gate is separate

A lead can score well on its signals and still be one nobody should act on — a
property that cannot be resold at a profit, an invoice past recovery. Folding
that into a bucket weight distorts the signal; the gate expresses it as a
verdict, and the profile decides what tier a non-viable lead may reach.

The gate runs first and its result is passed to every extractor, so a bucket
that scores off viability evidence reuses that work rather than recomputing it.

## Adding an asset class

Write a profile module that returns a configured engine. The real estate profile
in `src/wholesaler/scoring/profiles/real_estate.py` is the worked example.

```python
from src.leadscore import Bonus, Bucket, GateResult, ScoringEngine, TierBands

# 1. Name the constants. Anything you would otherwise inline as a magic number.
DAYS_TO_POINTS = 1 / 1.8
AMOUNT_TO_POINTS = 1 / 1000

# 2. Write an extractor per bucket. Return anything; the engine clamps to 0-100.
def age_score(record, gate):
    return record["days_overdue"] * DAYS_TO_POINTS

def size_score(record, gate):
    return record["amount"] * AMOUNT_TO_POINTS

# 3. Decide what makes a lead not worth acting on.
class Recoverable:
    def evaluate(self, record):
        insolvent = record.get("debtor_insolvent", False)
        return GateResult(viable=not insolvent, detail={"insolvent": insolvent})

# 4. Compose. Weights must sum to 1.
def build_engine():
    return ScoringEngine(
        buckets=[
            Bucket("age", 0.6, age_score),
            Bucket("size", 0.4, size_score),
        ],
        tiers=TierBands(bands=(("chase_now", 60), ("monitor", 30)), fallback="write_off"),
        gate=Recoverable(),
        bonuses=[Bonus("disputed", -20, lambda r: r.get("disputed", False))],
        non_viable_tiers=TierBands(bands=(), fallback="write_off"),
    )
```

Then `build_engine().score(record)` returns a `ScoreResult` with `total_score`,
`tier`, `bucket_scores`, `bonuses_applied` and `gate`.

## What is not in scope

The engine scores a record that someone else assembled. Ingestion, enrichment,
storage and identity are the application's concern — in this repository they are
still property-shaped (`parcel_id_normalized` is the key everything joins on).
Reusing the engine for another asset class does not require changing that;
storing that asset class would.
