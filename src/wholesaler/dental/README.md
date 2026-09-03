# Dental office universe

Assembles the list nobody has: every separately-parcelled dental building in
Florida, who owns it, and how close that dentist is to leaving practice.

```bash
python scripts/measure_dental_universe.py \
    --licensees data/mqa_dentists.txt \
    --parcels data/nal_orange_2025.csv \
    --parcels data/nal_seminole_2025.csv \
    --out data/dental_targets.csv
```

Exit code 0 when the universe is large enough to validate a scorer against
(200+ owner-occupied buildings), 2 when it is not, 1 on an input error.

## The two inputs

| | Source | Notes |
|---|---|---|
| **Licensees** | [FL DOH Medical Quality Assurance data download](https://flhealthsource.gov/data-portal/), filtered to Dentistry | Pipe-delimited, refreshed **daily**, free public record. Carries licence number, name, practice address, licence date, status. |
| **Parcels** | FL DOR annual NAL tax rolls, one file per county per year | Use code **0019 — Professional Services Buildings** is where medical and dental offices sit. |

Column names are resolved by trying the spellings each source is known to use
(`PHY_ADDR1`, `JV`, `TOT_LVG_AR`, `ACT_YR_BLT`, `SALE_YR1`…), because county
re-exports rename headers and neither file has a stable published order. The
delimiter is sniffed when not stated — pipe for MQA, comma for re-exports.

## What the matching does

Licence records write "1234 North Orange Avenue, Suite 200". Rolls write
"1234 N ORANGE AVE". Both sides reduce to `1234 N ORANGE AVE|32801` before
comparison.

**Stripping the suite is the point.** The dentist occupies a suite; the parcel is
the whole building. Dropping the unit is what lets a licensee find their building
at all — and when several dentists reduce to one key that is a finding, not a
collision: a multi-practitioner building.

ZIP is part of the key because street names repeat statewide; matching on street
alone would merge a Main St in Orlando with one in Miami.

**Owner-occupancy** is detected two ways, since either means the person to
approach is the dentist rather than a landlord:

- the dentist's surname appears in the owner of record (`NGUYEN ANH T`), or
- the owner names itself dentally (`LAKESIDE DENTAL LLC`, `SMITH DDS PA`).

Entity boilerplate (`LLC`, `PA`, `FAMILY TRUST`, `TTEE`) is stripped before
comparing, and surname matching is whole-word — `NGUY` must not match `NGUYEN`,
or a large share of any roll matches something.

## Reading the output

The report is deliberately blunt about its own funnel, because **a low match rate
looks exactly like a small market and means something completely different**:

- **Match rate below ~35%** → the bottleneck is address parsing or missing
  counties, not the size of the universe. Treat the totals as a floor.
- **Zero matches** → a plumbing failure. Usually the roll covers different
  counties than the licensees practise in, or the address column was not the one
  expected.
- **Under 200 owner-occupied buildings** → below what the feasibility harness
  needs to return a verdict at all. Add counties.
- **No sale dates** → turnover is unmeasured, and turnover is the number that
  decides whether a pipeline can be filled.

## The gap this leaves

The target list carries no **mortgage data**, and `debt_pressure` is 20% of the
dental scoring profile. Run the scorer on this list alone and that bucket is zero
for every building, which caps realistic scores around 62 and puts almost nothing
in Tier A.

That is not a scorer problem — it is a missing source. Mortgage originations are
recorded at the county level, and SBA 504's long fixed terms mean a recorded
origination implies a maturity date years ahead. Adding that source is what makes
the timing signal work, and it is the obvious next ingestion after this one.

## Where this fits

```
MQA licensees  ─┐
                ├─→ measure_dental_universe.py ─→ target list ─→ dental_office profile
NAL tax rolls  ─┘                                      │
                                                       └─→ + sale outcomes ─→ feasibility harness
```

The target list is already shaped to score. Attaching recorded sales to it turns
it into the cohort the feasibility harness needs to test whether the ranking
predicts anything.
