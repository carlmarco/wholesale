"""
Dental office asset profile.

Ranks dentist-owned commercial buildings by how soon they are likely to become
available, and how much value is at stake when they do.

The thesis, and why it is not distressed-property scoring
--------------------------------------------------------
A dental building transacts when the *practice* transacts, and practices
transact when the dentist retires. Code violations, tax deeds and foreclosures -
the whole residential distress vocabulary - are close to irrelevant here.

What makes the asset interesting is a structural gap. DSOs and private equity
buyers of dental practices generally will not buy the real estate; their
financing structures and investment mandates favour leasing. So when a dentist
sells to a DSO, the building is orphaned: the retired dentist becomes a landlord
they never wanted to be, to a tenant who would rather not have them.

That building, once it carries a long triple-net lease to a corporate operator,
is exactly what institutional buyers want. The value creation is therefore in
order of magnitude:

1. Lease structure. An unstructured dentist-owned building is worth materially
   less than the same building on a long NNN lease with escalations. This is
   decided at the moment of the practice sale, which is why timing beats
   everything else - reach the owner before that, or the value is set without
   you.
2. Aggregation. Portfolios of these assets clear at tighter cap rates than the
   same buildings sold one at a time to individual buyers.
3. Seller motivation. A retired dentist selling one building is not a
   professional counterparty.

So the scorer's job is to rank on: how close is this owner to exiting, and how
much real estate value is at stake when they do.

Calibration status
------------------
The cap rates and rent assumptions below are market-level starting points, not
measurements of any particular submarket. They set the scale of the gate's
output and should be replaced with observed figures - the first ten deals looked
at will beat any published average. Every one is named here so that recalibration
is an edit to this file.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from src.leadscore import Bonus, Bucket, GateResult, Record, ScoringEngine, TierBands
from src.wholesaler.utils.dates import coerce_date

# --- Owner exit: the dominant signal ----------------------------------------
# Licence issue date is the best public proxy for a dentist's age: dental school
# graduation clusters tightly around the mid-twenties, so years-since-licensure
# plus roughly 26 approximates age. Average retirement age was 68.7 in 2024, and
# in some states over 40% of active dentists are 55 or older.
YEARS_LICENSED_AT_TYPICAL_RETIREMENT = 43  # ~age 69
# The band where a sale is actively being contemplated. Practitioners in the
# 55-64 age range are the cohort brokers describe as having a three-to-five year
# transition window.
YEARS_LICENSED_EXIT_WINDOW = (29, 43)  # ~ages 55-69
EXIT_WINDOW_POINTS = 55
PAST_TYPICAL_RETIREMENT_POINTS = 70  # already overdue: most urgent of all
APPROACHING_WINDOW_POINTS = 20  # ~ages 50-55, worth warming up early

# Long ownership means an unlevered or lightly levered owner with a large
# embedded gain, and no recent refinance to reset their horizon.
OWNERSHIP_TENURE_BANDS = ((20, 30), (12, 20), (7, 10))  # (years held, points)

# --- Debt pressure: a dated, computable forcing function --------------------
# SBA 504 is the standard instrument for dental practice real estate. Its terms
# are long and fixed, so a recorded origination date implies a maturity date
# years in advance. A balloon forces a refinance or a sale.
MONTHS_TO_MATURITY_BANDS = ((12, 100), (24, 70), (36, 40))  # (months out, points)
DEFAULT_LOAN_TERM_YEARS = 25

# --- Asset fit: is this actually a dental office worth owning ---------------
# Florida DOR use code 0019 is "Professional Services Buildings", the roll code
# that carries medical and dental offices. It is how the universe is found at
# all, so a parcel that does not carry it is suspect.
DENTAL_USE_CODES = {"0019", "19"}
USE_CODE_MATCH_POINTS = 30
# A single-doctor practice runs three to five operatories in roughly this range.
# Much smaller is a suite inside a plaza, not a standalone asset; much larger is
# a medical building with several tenants and a different underwriting problem.
DENTAL_SQFT_RANGE = (1_500, 6_000)
IN_SQFT_RANGE_POINTS = 40
NEAR_SQFT_RANGE_POINTS = 15
# Asymmetric on purpose. Undersized is usually a suite inside a plaza rather
# than a standalone parcel, which is not an acquirable asset at all, so the
# tolerance below the range is tight. Oversized is a multi-tenant medical
# building - a different underwriting problem but still real estate - so the
# tolerance above it is generous.
SQFT_TOLERANCE_BELOW = 300
SQFT_TOLERANCE_ABOVE = 4_000
# Buildings older than this usually need the operatory plumbing reworked, which
# a buyer prices in and an institutional purchaser dislikes.
MODERN_BUILD_YEAR = 1985
MODERN_BUILD_POINTS = 30

# --- Deal value: scaled from the gate's projected spread --------------------
VIABLE_BASE_POINTS = 50
SPREAD_SCALE_CEILING = 400_000  # spread above the minimum earning full marks

WEIGHTS = {
    "owner_exit": 0.40,
    "debt_pressure": 0.20,
    "asset_fit": 0.15,
    "deal_value": 0.25,
}

# Applied after the weighted sum, for signals that matter beyond their bucket.
# A practice already sold to a DSO means the lease is written and the owner is a
# reluctant landlord - the cleanest possible acquisition, but the lease terms
# are now fixed rather than negotiable.
DSO_TENANT_BONUS = 12
# Conversely, a building the owner has already listed is a competitive process.
ALREADY_LISTED_PENALTY = -20

TIER_BANDS = TierBands(bands=(("A", 62), ("B", 48), ("C", 34)), fallback="D")
# A building that cannot be exited profitably is not a lead however close the
# dentist is to retiring.
NON_VIABLE_TIER_BANDS = TierBands(bands=(("C", 45),), fallback="D")


class InstitutionalExitGate:
    """
    Can this building be bought individually and exited institutionally?

    The commercial analogue of the residential profitability guardrail, and
    arithmetically a different thing: value here is net operating income divided
    by a capitalisation rate, not comparable sales less repairs.

    The spread comes from two sources. A single dentist-owned building trades at
    a wider cap rate than the same asset inside a portfolio sold to a REIT or
    private equity buyer, and an unstructured occupancy is worth less than a long
    triple-net lease. Both are captured as a cap rate differential.
    """

    # Individual, non-credit, short-or-no-lease dental assets sold to a dentist
    # or local investor. Dental NNN has been quoted around 7.00-8.50%, with the
    # tighter end reserved for newer build-to-suit with 12+ years remaining.
    ACQUISITION_CAP_RATE = 0.0800
    # The same income inside a portfolio of similar assets, with a structured
    # lease, sold to institutional capital.
    EXIT_CAP_RATE = 0.0665
    # Market NNN rent for suburban Florida dental space. The single assumption
    # most worth replacing with a real number: value scales linearly with it.
    MARKET_RENT_PER_SQFT = 32.0
    # NNN means the tenant carries taxes, insurance and maintenance, but not
    # structural reserves or the vacancy risk of a single-tenant asset.
    NOI_MARGIN = 0.94
    # Cost of getting a deal done: diligence, legal, lease negotiation, closing.
    TRANSACTION_COST_RATE = 0.055
    # Below this the deal does not justify the origination effort.
    MIN_SPREAD = 120_000.0

    def evaluate(self, record: Record) -> GateResult:
        """Estimate the spread between individual purchase and portfolio exit."""
        square_feet = _square_feet(record)
        if not square_feet:
            return GateResult(
                viable=False,
                detail={"reason": "no building area, so income cannot be estimated"},
            )

        rent = _rent_per_sqft(record) or self.MARKET_RENT_PER_SQFT
        gross_rent = square_feet * rent
        noi = gross_rent * self.NOI_MARGIN

        acquisition_value = noi / self.ACQUISITION_CAP_RATE
        exit_value = noi / self.EXIT_CAP_RATE
        transaction_costs = acquisition_value * self.TRANSACTION_COST_RATE
        spread = exit_value - acquisition_value - transaction_costs

        return GateResult(
            viable=spread >= self.MIN_SPREAD,
            detail={
                "square_feet": square_feet,
                "rent_per_sqft": round(rent, 2),
                "noi": round(noi, 2),
                "acquisition_value": round(acquisition_value, 2),
                "exit_value": round(exit_value, 2),
                "transaction_costs": round(transaction_costs, 2),
                "projected_spread": round(spread, 2),
                "is_viable": spread >= self.MIN_SPREAD,
                "min_spread": self.MIN_SPREAD,
            },
        )


def _nested(record: Record, section: str) -> Mapping[str, Any]:
    """Read a sub-mapping, tolerating its absence."""
    value = record.get(section)
    return value if isinstance(value, Mapping) else {}


def _square_feet(record: Record) -> Optional[float]:
    """Building area, from whichever section carries it."""
    for section in ("property", "property_record"):
        area = _nested(record, section).get("building_sqft") or _nested(record, section).get(
            "living_area"
        )
        if area:
            return float(area)
    area = record.get("building_sqft")
    return float(area) if area else None


def _rent_per_sqft(record: Record) -> Optional[float]:
    """Observed rent, when a lease is known. Beats any market assumption."""
    rent = _nested(record, "lease").get("rent_per_sqft")
    return float(rent) if rent else None


def _years_since(value: Any, as_of: Optional[date] = None) -> Optional[float]:
    """Years between a date and ``as_of``, defaulting to today."""
    parsed = coerce_date(value)
    if parsed is None:
        return None
    reference = as_of or date.today()
    return (reference - parsed).days / 365.25


def owner_exit_score(record: Record, gate: GateResult) -> float:
    """
    Score how close the owning dentist is to leaving practice.

    Licence date carries most of the weight; ownership tenure adds to it, since
    a long hold means an owner with a large embedded gain and no recent
    refinance resetting their horizon.
    """
    as_of = coerce_date(record.get("as_of"))
    score = 0.0

    years_licensed = _years_since(_nested(record, "dentist").get("license_date"), as_of)
    if years_licensed is not None:
        window_start, window_end = YEARS_LICENSED_EXIT_WINDOW
        if years_licensed >= YEARS_LICENSED_AT_TYPICAL_RETIREMENT:
            score += PAST_TYPICAL_RETIREMENT_POINTS
        elif years_licensed >= window_start:
            score += EXIT_WINDOW_POINTS
        elif years_licensed >= window_start - 5:
            score += APPROACHING_WINDOW_POINTS

    years_held = _years_since(_nested(record, "ownership").get("last_sale_date"), as_of)
    if years_held is not None:
        for threshold, points in OWNERSHIP_TENURE_BANDS:
            if years_held >= threshold:
                score += points
                break

    return score


def debt_pressure_score(record: Record, gate: GateResult) -> float:
    """
    Score how soon the mortgage forces a decision.

    A recorded origination date plus the instrument's term implies a maturity,
    and a balloon leaves an owner refinancing or selling on a known date.
    """
    debt = _nested(record, "debt")
    as_of = coerce_date(record.get("as_of")) or date.today()

    maturity = coerce_date(debt.get("maturity_date"))
    if maturity is None:
        originated = coerce_date(debt.get("origination_date"))
        if originated is None:
            return 0.0
        term_years = debt.get("term_years") or DEFAULT_LOAN_TERM_YEARS
        maturity = date(
            originated.year + int(term_years), originated.month, min(originated.day, 28)
        )

    months_out = (maturity - as_of).days / 30.44
    if months_out < 0:
        return 0.0  # already matured; whatever happened, happened

    for threshold, points in MONTHS_TO_MATURITY_BANDS:
        if months_out <= threshold:
            return points
    return 0.0


def asset_fit_score(record: Record, gate: GateResult) -> float:
    """Score whether this is a standalone dental building worth owning."""
    prop = _nested(record, "property")
    score = 0.0

    use_code = str(prop.get("dor_use_code") or "").strip().lstrip("0") or "0"
    if use_code in {code.lstrip("0") or "0" for code in DENTAL_USE_CODES}:
        score += USE_CODE_MATCH_POINTS

    square_feet = _square_feet(record)
    if square_feet:
        low, high = DENTAL_SQFT_RANGE
        if low <= square_feet <= high:
            score += IN_SQFT_RANGE_POINTS
        elif low - SQFT_TOLERANCE_BELOW <= square_feet <= high + SQFT_TOLERANCE_ABOVE:
            score += NEAR_SQFT_RANGE_POINTS

    year_built = prop.get("year_built")
    if year_built and int(year_built) >= MODERN_BUILD_YEAR:
        score += MODERN_BUILD_POINTS

    return score


def deal_value_score(record: Record, gate: GateResult) -> float:
    """Scale the gate's projected spread into a sub-score."""
    if not gate.viable:
        return 0.0

    minimum = gate.detail.get("min_spread", 0)
    surplus = max(0.0, gate.detail.get("projected_spread", 0.0) - minimum)
    return VIABLE_BASE_POINTS + (surplus / SPREAD_SCALE_CEILING * VIABLE_BASE_POINTS)


def build_engine(weights: Mapping[str, float] | None = None) -> ScoringEngine:
    """
    Build the scoring engine for dentist-owned commercial buildings.

    Args:
        weights: Optional override of the bucket weights, which must still sum
            to 1. Useful for retuning without editing this module.

    Returns:
        A configured engine.
    """
    resolved = dict(WEIGHTS)
    if weights:
        resolved.update(weights)

    return ScoringEngine(
        buckets=[
            Bucket("owner_exit", resolved["owner_exit"], owner_exit_score),
            Bucket("debt_pressure", resolved["debt_pressure"], debt_pressure_score),
            Bucket("asset_fit", resolved["asset_fit"], asset_fit_score),
            Bucket("deal_value", resolved["deal_value"], deal_value_score),
        ],
        tiers=TIER_BANDS,
        gate=InstitutionalExitGate(),
        bonuses=[
            Bonus(
                "dso_tenant",
                DSO_TENANT_BONUS,
                lambda r: bool(_nested(r, "practice").get("dso_affiliated")),
            ),
            Bonus(
                "already_listed",
                ALREADY_LISTED_PENALTY,
                lambda r: bool(_nested(r, "ownership").get("listed_for_sale")),
            ),
        ],
        non_viable_tiers=NON_VIABLE_TIER_BANDS,
    )
