# Feasibility test

Answers one question before any ML gets built:

> For parcels that showed distress at a point in time, did the scorer's ranking
> predict which ones actually transacted?

Public deed records make this answerable **retroactively**, so it can be settled
with history instead of by operating for a year. The answer decides whether a
labelling pipeline and real models are worth building, or whether the edge is in
data coverage and speed-to-lead instead.

## Running it

```bash
python scripts/run_feasibility.py --sales data/sales_extract.csv
python scripts/run_feasibility.py --sales data/sales.csv --cohort data/cohort.csv --horizon-days 365
```

Exit code is 0 for a conclusive verdict, 2 for insufficient data, 1 for a
usage or input error.

## The two inputs

**Sales extract** — recorded transfers, one row per sale:

| column | required | notes |
|---|---|---|
| `parcel_id` | yes | digits only, matching `parcel_id_normalized` |
| `sale_date` | yes | ISO or `MM/DD/YYYY` |
| `sale_price` | no | needed to filter nominal transfers, and for any price model |
| `instrument` | no | deed type, reporting only |

**Cohort** — parcels scored at a point in time. Defaults to the `lead_scores`
table; pass `--cohort` to test a historically reconstructed one:

| column | required | notes |
|---|---|---|
| `parcel_id` | yes | join key |
| `as_of` | yes | the distress event date — features must predate this |
| `score` | yes | the scorer's output, computed from `as_of` data |
| `tier` | no | reporting only |

## Where the data comes from

For Orange County, FL:

- **Sales / deed transfers** — Comptroller's Official Records (deed transfers,
  grantor/grantee, consideration) and the Property Appraiser's per-parcel sales
  history.
- **Cohort events** — the sources this repo already ingests: tax sale
  (`arcgis_base_url`), foreclosure (`arcgis_foreclosure_url`), code violations
  (Socrata `k6e8-nw6w`). Pull the event lists for 2019–2023 rather than today.

Any county publishing deed transfers works the same way; only the extract step
changes.

## The trap this guards against

Features must be computed from data available on `as_of`, not from today's
records. Label a parcel with a sale that happened between those two dates and
the outcome leaks backwards — the model looks excellent offline and fails live.

`assert_features_precede_outcomes` makes that an error rather than a matter of
discipline. Pass it the `computed_at` per parcel from `ml_features`:

```python
assert_features_precede_outcomes(labelled, feature_dates)  # raises PointInTimeError
```

Note that reading the cohort from `lead_scores` is only sound if those scores
were written by the live pipeline as events arrived. If the table was backfilled
by rescoring old parcels against current data, the scores are contaminated and
the result is meaningless.

## How the verdict is decided

Two things must agree before anything is called signal:

1. **AUC interval excludes 0.5.** The omnibus test — uses every parcel, one
   comparison, so it cannot be reached by a lucky budget.
2. **At least one action budget has a lift interval excluding 1.0**, at a
   Bonferroni-adjusted level. This is the effect size the business feels.

Requiring only the second is how noise gets called a result: testing four
budgets at 90% and accepting any of them yields a false positive roughly a
third of the time. That exact failure is pinned by
`test_a_lucky_budget_alone_does_not_make_a_verdict`.

Cohorts below 200 parcels or 20 transactions return **insufficient data** rather
than a verdict, because at that size neither answer would mean anything.

## Reading the result

- **signal** → build the labelling pipeline, then fit `P(transacts)` and
  `E[sale price]` on real outcomes.
- **no signal** → do not build the ML platform. A model trained on these
  features inherits the same absence of signal. Test whether coverage and
  speed-to-lead are the real edge.
- **insufficient data** → widen the cohort: more event types, more years, or a
  longer horizon.

A "no signal" result is a successful run. It is far cheaper to learn this now
than after building a platform on top of it.
