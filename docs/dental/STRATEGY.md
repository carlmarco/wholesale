# Dental office real estate: where the money is

Research behind `src/wholesaler/scoring/profiles/dental_office.py`. Written to be
argued with — every number here is a starting point to replace with observation.

## The structural gap

A dental building transacts when the *practice* transacts, and practices
transact when the dentist retires. This is the whole reason the residential
distress model does not carry over: code violations, tax deeds and foreclosures
are close to irrelevant for a professional building with a solvent owner.

What makes the asset interesting is a gap nobody is arbitraging at scale:

1. **DSOs buy practices but not buildings.** Their financing structures and
   investment mandates favour leasing; they prefer sale-leasebacks.
2. **So the building is orphaned.** The retiring dentist becomes a landlord they
   never wanted to be, to a tenant who would rather not have them. Industry
   commentary is blunt that this relationship is uncomfortable for both sides.
3. **But that same building, once it carries a long triple-net lease to a
   corporate operator, is what institutional buyers want.** Long term, clean
   structure, escalations, credit-ish tenant.

The seller is an individual with one asset and no interest in holding it. The
buyer pool at the other end is institutional. That is the spread.

## Where value is actually created, in order

**1. Lease structure — the biggest lever, and it has a deadline.**

An unstructured dentist-owned occupancy is worth materially less than the same
building on a long NNN lease with escalations. Institutional demand concentrates
on "strong tenants, durable operating formats, clean lease structures, and long
remaining terms". A buyer typically needs 5+ years of term to finance.

The lease gets written **at the moment of the practice sale**. Reach the owner
after that and the value is already set — badly, usually, because the dentist was
negotiating the practice price and treated the lease as paperwork. Dental
Economics titled an article on exactly this "the transition valuation nobody
talks about—until it's too late."

**This deadline is why the scorer optimises for timing, not for property
quality.** Being early is worth more than being right about the building.

**2. Aggregation.** Portfolio trades clear at tighter cap rates than equivalent
single-asset sales — for medical office roughly 60bps tighter, and the premium
held into 2026. On a $12M portfolio that differential is worth on the order of
$1M+ purely for having assembled it.

**3. Seller motivation.** A retired dentist selling one building is not a
professional counterparty and is not running a competitive process — provided you
reach them before a broker does.

## Which business model is most profitable

The honest answer: **the data product is identical for all of them**, so this is
the one decision that can safely be deferred.

| Model | Capital | Per-deal economics | Notes |
|---|---|---|---|
| Acquire + aggregate | High ($10M+ for a portfolio) | Cap-rate spread on exit, plus NOI held | Highest absolute profit; captures both levers 1 and 2 |
| Sale-leaseback origination | Low | Fee or assigned spread | Closest to the wholesaling model already in this repo |
| Brokerage | Minimal | ~4–6% commission | Competitive, needs licensure, captures none of the spread |
| DSO-adjacent (practice + property) | High | Largest, but | Needs practice-level data that is not public |

All four rank the same thing: *which dentist-owned building is most likely to
become available, and how much is at stake when it does.* Build the
identification engine, monetise later — you can broker into capital and then
acquire, and nothing about the data work changes.

The two levers above argue for ending up at **acquire + aggregate**, because
lever 2 is only available to a principal. Origination is the sensible way in.

## Timing: the window is real and it is closing

- Over 40% of active dentists are 55+ in some states; average retirement age
  reached 68.7 in 2024.
- 69% of DSOs expect to meaningfully increase acquisition activity in 2026, and
  78% anticipate a recapitalisation within 12–36 months.
- Private practice ownership fell from 85% (2005) to 73% (2023); solo practice
  from ~67% to ~50%.
- Brokers describe a 3–5 year window for the 55–64 cohort **before the retirement
  wave completes and supply normalises**, at which point seller leverage — and
  acquisition pricing — moves against sellers and towards buyers.

Read carefully, that last point cuts both ways. High supply is *bad* for a
brokerage or origination model that depends on seller leverage, and *good* for an
acquirer buying assets. Another argument for ending up as a principal.

## Why statewide Florida, not one county

Rough county-level arithmetic: ~1.4M people in Orange County, dentist-to-
population somewhere near 1:1,500–2,000, several dentists per office, and many
practices leasing space in plazas that are not separately parcelled. Plausibly
**150–350 acquirable dental buildings county-wide**, transacting at maybe 4–7% a
year — on the order of **10–20 transactions annually**.

That is too few to validate a scorer against outcomes: the feasibility harness
requires 200 cohort members and 20 transactions before it will return a verdict
at all.

Statewide changes the arithmetic. The Florida Dental Association alone represents
over 8,100 dentists, and the same three data sources cover all 67 counties with
no new plumbing per county. **Go wide before going deep** — the opposite of the
residential instinct.

## The data sources that make this buildable

| Source | What it gives | Notes |
|---|---|---|
| **FL DOH Medical Quality Assurance data download** | Every licensed dentist statewide: licence number, licence date, name, practice address | Free public records, pipe-delimited, **updated daily**, filterable by profession. Licence date is the age proxy the whole model rests on. |
| **FL DOR NAL tax rolls** | Per-parcel use code, owner name, values, building area, year built — annually, all 67 counties | Use code **0019 (Professional Services Buildings)** is how the universe is found. Annual roll years are also what make point-in-time valuation possible. |
| **County deed / mortgage records** | Sales (the outcome label) and mortgage originations | SBA 504 is standard for dental real estate; a recorded origination plus its term implies a **maturity date years in advance** — a dated, computable forcing function. |

Matching licensee practice addresses against use-code-0019 parcels is what
produces the target list. Nobody has that list assembled; assembling it *is* the
product.

## What to do first

**Measure the universe before building anything else.** Pull NAL use code 0019
for a handful of counties, match against Board of Dentistry addresses, and count:

- how many separately-parcelled dental buildings exist,
- how many transacted per year,
- what share are owner-occupied by the practising dentist.

That is roughly a day of work and it decides whether this is a side project or a
statewide business. It also produces the cohort the feasibility harness needs.

## Sources

- [Emerging Trends in Real Estate: medical office outlook — PwC/ULI](https://www.pwc.com/us/en/industries/financial-services/asset-wealth-management/real-estate/emerging-trends-in-real-estate-pwc-uli/property-type-outlook/medical-office.html)
- [Why Use Sale-Leasebacks to Maximize Medical Office Value — Matthews](https://www.matthews.com/market_insights/medical-office-sale-leaseback)
- [The Next Chapter for Healthcare Real Estate — Matthews](https://www.matthews.com/market_insights/next-chapter-for-healthcare-real-estate)
- [Maximize real estate when selling your dental practice to a DSO — Dental Economics](https://www.dentaleconomics.com/practice/practice-transitions/article/55279041/maximize-real-estate-when-selling-your-dental-practice-to-a-dso)
- [The transition valuation nobody talks about—until it's too late — Dental Economics](https://www.dentaleconomics.com/money/investments/news/55376120/the-transition-valuation-nobody-talks-aboutuntil-its-too-late)
- [Maximizing Dental Real Estate Value Through a Portfolio Sale — DOCS Education](https://www.docseducation.com/blog/maximizing-dental-real-estate-value-through-portfolio-sale)
- [TUSK Practice Sales Q2 2026 Dental Market Report](https://www.prnewswire.com/news-releases/tusk-practice-sales-releases-q2-2026-dental-market-report-what-dentists-should-know-about-transition-planning-302748901.html)
- [The State of US Dental Practice Ownership: A 4-Cohort Framework — Private Practice Research](https://privatepracticeresearch.org/reports/us-dental-practice-ownership-2026)
- [Dental practice values hold, but these shifts are changing who sells and for how much — DrBicuspid](https://www.drbicuspid.com/dental-business/practice-sales/article/15830584/dental-industry-shifts-that-are-changing-who-sells-and-for-how-much)
- [Pacific Dental Services Credit Rating & NNN Cap Rate (2026)](https://investmentgrade.com/pacific-dental-services-credit-rating-nnn-cap-rate/)
- [Net Lease Cap Rates Tick Upward in Q2 2026 — Connect CRE](https://www.connectcre.com/stories/net-lease-cap-rates-tick-upward-in-q2-2026/)
- [MQA Search Services and Data Download User Guide — FL DOH](https://mqa-internet.doh.state.fl.us/MQASearchServices/Content/HelpFile/MQA%20SearchServices%20and%20DataDownload%20UserGuide.pdf)
- [Data Portal — FL HealthSource](https://flhealthsource.gov/data-portal/)
