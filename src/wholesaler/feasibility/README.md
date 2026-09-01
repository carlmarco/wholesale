# Feasibility test

Answers one question before any ML gets built:

> For parcels that showed distress at a point in time, did the scorer's ranking
> predict which ones actually transacted?

Public deed records make this answerable **retroactively**, so it can be settled
with history instead of by operating for a year. The answer decides whether a
labelling pipeline and real models are worth building, or whether the edge is in
data coverage and speed-to-lead instead.

## Running it

Pre-launch, with no scoring history, build the cohort from past events first:

```bash
python scripts/build_cohort.py \
    --events data/tax_sales_2019_2023.csv --event-type tax_sale \
    --events data/foreclosures_2019_2023.csv --event-type foreclosure \
    --violations data/code_violations_history.csv \
    --valuations data/nal_rolls_2018_2023.csv \
    --out data/cohort.csv

python scripts/run_feasibility.py --cohort data/cohort.csv --sales data/sales.csv
```

With live scoring history already in `lead_scores`, the cohort comes from the
database instead:

```bash
python scripts/run_feasibility.py --sales data/sales_extract.csv
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

## What the reconstruction can and cannot rebuild

`build_cohort.py` scores each past event as of its own date. Not every signal
survives that:

| signal | recoverable | how |
|---|---|---|
| violation count, recency | yes | violations carry filing dates |
| open violations | only with close dates | a case closed in 2023 was open in 2022; current status cannot tell you a past one |
| prior distress events | yes | event dates |
| living area, year built | effectively | these rarely change |
| **market / assessed value** | **no, from the live layer** | the parcel layer holds only the currently certified value — and that value *reacts to the sale being predicted*, so reusing it leaks the outcome directly |
| equity percent | no | derived from current value and debt |

Historical values must come from annual certified tax rolls (in Florida, the
Department of Revenue's NAL files, one per county per year), passed as
`--valuations`. Without them the profitability gate cannot run, every member
fails it, and the test covers distress and disposition only. The coverage report
says so explicitly rather than letting it pass unnoticed.

By default only each parcel's earliest event becomes a cohort member. Repeat
events on one parcel share an outcome, which breaks the independence the
bootstrap intervals assume; `--all-events` overrides this deliberately.

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

Four outcomes, not two. Two things must agree before anything is called signal:

1. **AUC interval excludes 0.5.** The omnibus test — uses every parcel, one
   comparison, so it cannot be reached by a lucky budget.
2. **At least one action budget has a lift interval excluding 1.0**, at a
   Bonferroni-adjusted level. This is the effect size the business feels.

Requiring only the second is how noise gets called a result: testing four
budgets at 90% and accepting any of them yields a false positive roughly a
third of the time. That exact failure is pinned by
`test_a_lucky_budget_alone_does_not_make_a_verdict`.

When AUC clears 0.5 but no budget does, the result is **weak signal** rather
than "no signal": the ranking genuinely beats chance, the advantage is just too
small to act on. Reporting that as "no better than random" would contradict the
AUC it was measured against.

Cohorts below 200 parcels or 20 transactions return **insufficient data** rather
than a verdict, because at that size neither answer would mean anything.

## Reading the result

- **signal** → build the labelling pipeline, then fit `P(transacts)` and
  `E[sale price]` on real outcomes.
- **weak signal** → the ranking beats chance overall but not at any action
  budget: real, and not yet usable. Worth building labels, since they are what
  let you improve features against a real target, but do not plan a campaign
  around the current scorer.
- **no signal** → do not build the ML platform. A model trained on these
  features inherits the same absence of signal. Test whether coverage and
  speed-to-lead are the real edge.
- **insufficient data** → widen the cohort: more event types, more years, or a
  longer horizon.

A "no signal" result is a successful run. It is far cheaper to learn this now
than after building a platform on top of it.

