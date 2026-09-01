"""
Rebuild a scored cohort from history.

For each distress event in the past, this reconstructs what the scorer would
have seen on the day of that event and scores it. The result feeds the
feasibility test: parcels ranked as of a date, against sales that happened after
it.

The whole exercise is worthless if a feature is read from today's records. Some
of what the scorer consumes is recoverable historically and some is not, and the
difference is not obvious:

    recoverable      violation counts and recency (violations carry filing
                     dates), prior distress events, the event's own attributes,
                     and physical attributes such as living area and year built,
                     which rarely change

    NOT recoverable  market and assessed values, and any equity figure derived
                     from them. The parcel layer carries only the currently
                     certified value. Worse, that value reacts to the sale being
                     predicted - a property that sold gets reassessed - so
                     reusing it leaks the outcome directly into the features.

Historical values therefore have to come from annual certified tax rolls, passed
in as a valuation roll. Without one the profitability gate cannot run, every
member fails it, and the feasibility test measures distress and disposition
only. That is a legitimate test, but a narrower one, so the coverage report says
so rather than letting it pass unnoticed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.wholesaler.feasibility.outcomes import CohortMember
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

TAX_SALE = "tax_sale"
FORECLOSURE = "foreclosure"
CODE_VIOLATION = "code_violation"
EVENT_TYPES = (TAX_SALE, FORECLOSURE, CODE_VIOLATION)


@dataclass(frozen=True)
class DistressEvent:
    """
    A dated event that would have put a parcel in front of the scorer.

    Attributes:
        parcel_id_normalized: Join key.
        event_date: When the event became visible. This is the cohort member's
            ``as_of``, and every feature must predate it.
        event_type: One of EVENT_TYPES.
        default_amount: Judgment amount, for foreclosures.
        opening_bid: Opening bid, for tax sales.
    """
    parcel_id_normalized: str
    event_date: date
    event_type: str
    default_amount: Optional[float] = None
    opening_bid: Optional[float] = None

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(
                f"unknown event_type {self.event_type!r}; expected one of {EVENT_TYPES}"
            )


@dataclass(frozen=True)
class ViolationRecord:
    """
    One code enforcement case.

    Attributes:
        parcel_id_normalized: Join key.
        filed_on: When the case was opened.
        closed_on: When it was resolved, when the source publishes it. Without
            it, whether the case was open on a past date is unknowable, and the
            open-violation signal is reported as uncovered rather than guessed.
    """
    parcel_id_normalized: str
    filed_on: date
    closed_on: Optional[date] = None


@dataclass(frozen=True)
class Valuation:
    """
    A parcel's certified values for one roll year.

    Attributes:
        parcel_id_normalized: Join key.
        roll_year: Year these values were certified for.
        total_mkt: Certified market value.
        assessed_val: Assessed value.
        living_area: Heated square footage.
        year_built: Year of construction.
        equity_percent: Value against debt, when the roll carries it.
    """
    parcel_id_normalized: str
    roll_year: int
    total_mkt: Optional[float] = None
    assessed_val: Optional[float] = None
    living_area: Optional[float] = None
    year_built: Optional[int] = None
    equity_percent: Optional[float] = None


@dataclass
class CoverageReport:
    """
    Which signals the reconstruction could actually supply.

    A feasibility test that silently measured two buckets out of four would
    invite the wrong conclusion, so what was missing is reported alongside the
    verdict.
    """
    members: int = 0
    with_violation_history: int = 0
    with_open_violation_status: int = 0
    with_valuation: int = 0
    with_prior_events: int = 0
    events_dropped_no_date: int = 0
    parcels_deduplicated: int = 0
    valuation_years_missing: List[int] = field(default_factory=list)

    def _share(self, count: int) -> float:
        return count / self.members if self.members else 0.0

    @property
    def profitability_is_measurable(self) -> bool:
        """Whether enough parcels carry values for the gate to mean anything."""
        return self._share(self.with_valuation) >= 0.5

    def warnings(self) -> List[str]:
        """Human-readable caveats about what this cohort can and cannot show."""
        notes = []

        if not self.members:
            return ["The reconstruction produced no cohort members."]

        if self.with_valuation == 0:
            notes.append(
                "No historical valuations were supplied, so the profitability gate "
                "could not run and every member fails it. This cohort tests the "
                "distress and disposition signals only. Supply annual certified "
                "tax rolls to test the full model."
            )
        elif not self.profitability_is_measurable:
            notes.append(
                f"Only {self._share(self.with_valuation):.0%} of members had a "
                "historical valuation, so profitability is measured on a minority "
                "of the cohort and the tier mix is not representative."
            )

        if self.with_open_violation_status == 0 and self.with_violation_history:
            notes.append(
                "No violation close dates were supplied, so open-violation counts "
                "are zero throughout. Whether a case was open on a past date "
                "cannot be inferred from its current status."
            )

        if self.events_dropped_no_date:
            notes.append(
                f"{self.events_dropped_no_date} events had no usable date and were "
                "dropped; an event without a date has no point in time to score at."
            )

        if self.parcels_deduplicated:
            notes.append(
                f"{self.parcels_deduplicated} repeat events were dropped to keep one "
                "member per parcel. Repeated parcels share an outcome, which would "
                "break the independence the bootstrap intervals assume."
            )

        if self.valuation_years_missing:
            years = ", ".join(str(year) for year in sorted(set(self.valuation_years_missing))[:5])
            notes.append(
                f"No valuation roll covered or preceded these event years: {years}. "
                "Those members were scored without values."
            )

        return notes


def _index_violations(
    violations: Iterable[ViolationRecord],
) -> Dict[str, List[ViolationRecord]]:
    index: Dict[str, List[ViolationRecord]] = defaultdict(list)
    for violation in violations:
        index[violation.parcel_id_normalized].append(violation)
    for records in index.values():
        records.sort(key=lambda record: record.filed_on)
    return dict(index)


def _index_valuations(
    valuations: Iterable[Valuation],
) -> Dict[str, List[Valuation]]:
    index: Dict[str, List[Valuation]] = defaultdict(list)
    for valuation in valuations:
        index[valuation.parcel_id_normalized].append(valuation)
    for records in index.values():
        records.sort(key=lambda record: record.roll_year)
    return dict(index)


def _index_events(events: Iterable[DistressEvent]) -> Dict[str, List[DistressEvent]]:
    index: Dict[str, List[DistressEvent]] = defaultdict(list)
    for event in events:
        index[event.parcel_id_normalized].append(event)
    for records in index.values():
        records.sort(key=lambda record: record.event_date)
    return dict(index)


def valuation_as_of(valuations: Sequence[Valuation], as_of: date) -> Optional[Valuation]:
    """
    The most recent roll certified on or before ``as_of``.

    A later roll must never be used: it reflects the outcome being predicted,
    since a parcel that sells is reassessed on the following roll.
    """
    eligible = [record for record in valuations if record.roll_year <= as_of.year]
    return eligible[-1] if eligible else None


def build_record(
    parcel_id: str,
    as_of: date,
    event: DistressEvent,
    parcel_events: Sequence[DistressEvent],
    violations: Sequence[ViolationRecord],
    valuation: Optional[Valuation],
    have_close_dates: bool,
) -> Mapping[str, object]:
    """
    Assemble the record the scorer would have seen on ``as_of``.

    Args:
        parcel_id: The parcel being scored.
        as_of: The event date. Nothing dated after this may be included.
        event: The event that put this parcel in the cohort.
        parcel_events: Every event known for the parcel, filtered here.
        violations: Every violation known for the parcel, filtered here.
        valuation: Values certified on or before ``as_of``, if available.
        have_close_dates: Whether the violation source published close dates.
            When it did not, open counts stay at zero rather than being guessed
            from current status.

    Returns:
        A record shaped for the real estate scoring profile.
    """
    prior_violations = [record for record in violations if record.filed_on <= as_of]

    open_violations = 0
    if have_close_dates:
        open_violations = sum(
            1
            for record in prior_violations
            if record.closed_on is None or record.closed_on > as_of
        )

    prior_events = [entry for entry in parcel_events if entry.event_date <= as_of]

    tax_sale: Dict[str, object] = {}
    foreclosure: Dict[str, object] = {}
    for entry in prior_events:
        if entry.event_type == TAX_SALE:
            tax_sale = {"event_date": entry.event_date.isoformat()}
            if entry.opening_bid is not None:
                tax_sale["opening_bid"] = entry.opening_bid
        elif entry.event_type == FORECLOSURE:
            foreclosure = {"event_date": entry.event_date.isoformat()}
            if entry.default_amount is not None:
                foreclosure["default_amount"] = entry.default_amount

    property_record: Dict[str, object] = {}
    if valuation:
        for name in ("total_mkt", "assessed_val", "living_area", "year_built", "equity_percent"):
            value = getattr(valuation, name)
            if value is not None:
                property_record[name] = value

    return {
        "seed_type": event.event_type,
        "violation_count": len(prior_violations),
        "open_violations": open_violations,
        "most_recent_violation": (
            prior_violations[-1].filed_on.isoformat() if prior_violations else None
        ),
        "tax_sale": tax_sale,
        "foreclosure": foreclosure,
        "property_record": property_record,
    }


def reconstruct_cohort(
    events: Iterable[DistressEvent],
    scorer,
    violations: Iterable[ViolationRecord] = (),
    valuations: Iterable[Valuation] = (),
    one_event_per_parcel: bool = True,
    have_close_dates: Optional[bool] = None,
) -> Tuple[List[CohortMember], CoverageReport]:
    """
    Score historical events as of their own dates.

    Args:
        events: Distress events to reconstruct.
        scorer: Anything with ``.score(record) -> {"total_score", "tier"}``;
            in practice ``HybridBucketScorer``.
        violations: Code enforcement history, for the distress signal.
        valuations: Annual certified values, for the profitability gate.
        one_event_per_parcel: Keep only each parcel's earliest event. Repeat
            events on one parcel share an outcome, which breaks the
            independence the feasibility intervals assume.
        have_close_dates: Whether violation close dates are trustworthy.
            Inferred from the data when not stated.

    Returns:
        The cohort and a coverage report describing what could be reconstructed.
    """
    event_list = list(events)
    violation_list = list(violations)
    valuation_list = list(valuations)

    coverage = CoverageReport()

    dated = [entry for entry in event_list if entry.event_date is not None]
    coverage.events_dropped_no_date = len(event_list) - len(dated)

    if have_close_dates is None:
        have_close_dates = any(record.closed_on is not None for record in violation_list)

    violations_by_parcel = _index_violations(violation_list)
    valuations_by_parcel = _index_valuations(valuation_list)
    events_by_parcel = _index_events(dated)

    selected: List[DistressEvent] = []
    if one_event_per_parcel:
        for parcel_events in events_by_parcel.values():
            selected.append(parcel_events[0])
            coverage.parcels_deduplicated += len(parcel_events) - 1
    else:
        selected = sorted(dated, key=lambda entry: (entry.parcel_id_normalized, entry.event_date))

    members: List[CohortMember] = []

    for event in selected:
        parcel = event.parcel_id_normalized
        as_of = event.event_date

        parcel_violations = violations_by_parcel.get(parcel, [])
        valuation = valuation_as_of(valuations_by_parcel.get(parcel, []), as_of)

        record = build_record(
            parcel_id=parcel,
            as_of=as_of,
            event=event,
            parcel_events=events_by_parcel.get(parcel, []),
            violations=parcel_violations,
            valuation=valuation,
            have_close_dates=have_close_dates,
        )

        result = scorer.score(record)
        members.append(
            CohortMember(
                parcel_id_normalized=parcel,
                as_of=as_of,
                score=float(result["total_score"]),
                tier=result.get("tier"),
            )
        )

        coverage.members += 1
        if record["violation_count"]:
            coverage.with_violation_history += 1
        if record["open_violations"]:
            coverage.with_open_violation_status += 1
        if record["property_record"].get("total_mkt") is not None:
            coverage.with_valuation += 1
        elif valuations_by_parcel.get(parcel):
            coverage.valuation_years_missing.append(as_of.year)

        # A parcel already in distress before this event is a stronger lead, so
        # count members carrying one - strictly earlier, not the event itself.
        if any(
            entry.event_date < as_of for entry in events_by_parcel.get(parcel, [])
        ):
            coverage.with_prior_events += 1

    logger.info(
        "cohort_reconstructed",
        members=coverage.members,
        with_valuation=coverage.with_valuation,
        deduplicated=coverage.parcels_deduplicated,
    )
    return members, coverage
