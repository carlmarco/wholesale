"""
Observed sale outcomes, and joining them to a cohort without leaking.

A feasibility test asks: for parcels that showed distress at time T, what
actually happened next? The answer comes from public deed and sale records,
which are available retroactively - so the question can be answered before
operating, using years of history.

The one thing that must not go wrong is the direction of time. If a parcel's
features are read from today's records while its label comes from a sale that
happened in between, the outcome leaks backwards into the features and every
later measurement is worthless - flattering offline, useless in production.
This module treats that as an error rather than trusting callers to remember.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from src.wholesaler.utils.dates import coerce_date
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# Deed records include non-market transfers - quitclaims between relatives,
# transfers into trusts, corrective deeds - which sell for a nominal sum and
# would poison both the label and any price model.
MIN_ARMS_LENGTH_PRICE = 1000.0


class PointInTimeError(ValueError):
    """Raised when a join would let an outcome leak into its own features."""


@dataclass(frozen=True)
class SaleOutcome:
    """
    One recorded transfer of a parcel.

    Attributes:
        parcel_id_normalized: Digits-only parcel identifier, the join key.
        sale_date: Date the transfer was recorded.
        sale_price: Consideration recorded on the deed, when present.
        instrument: Deed type, when the source provides it. Used only for
            reporting; arm's-length filtering is by price.
    """
    parcel_id_normalized: str
    sale_date: date
    sale_price: Optional[float] = None
    instrument: Optional[str] = None

    @property
    def is_arms_length(self) -> bool:
        """Whether the price looks like a real sale rather than a transfer."""
        return self.sale_price is not None and self.sale_price >= MIN_ARMS_LENGTH_PRICE


@dataclass(frozen=True)
class CohortMember:
    """
    One parcel observed at a point in time, before its outcome is known.

    Attributes:
        parcel_id_normalized: Join key.
        as_of: When this parcel entered the cohort - the distress event date.
            Every feature must be computed from data available on this date.
        score: The scorer's output for this parcel, computed from as_of data.
        tier: The tier assigned alongside the score.
    """
    parcel_id_normalized: str
    as_of: date
    score: float
    tier: Optional[str] = None


@dataclass(frozen=True)
class LabelledMember:
    """A cohort member with its observed outcome attached."""
    member: CohortMember
    sold: bool
    sale_date: Optional[date] = None
    sale_price: Optional[float] = None

    @property
    def days_to_sale(self) -> Optional[int]:
        if self.sale_date is None:
            return None
        return (self.sale_date - self.member.as_of).days


def load_sale_outcomes(path: Path) -> List[SaleOutcome]:
    """
    Read recorded sales from a CSV extract.

    Expected columns, case-insensitive: ``parcel_id`` (or
    ``parcel_id_normalized``), ``sale_date``, and optionally ``sale_price`` and
    ``instrument``. Rows missing a parcel or an unparseable date are skipped and
    counted, since county extracts routinely carry both.

    Args:
        path: CSV file of recorded transfers.

    Returns:
        Parsed outcomes.

    Raises:
        FileNotFoundError: If the extract does not exist.
        ValueError: If no recognisable parcel or date column is present, which
            usually means the wrong export was downloaded.
    """
    if not path.exists():
        raise FileNotFoundError(f"No sale extract at {path}")

    outcomes: List[SaleOutcome] = []
    skipped = 0

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")

        columns = {name.lower().strip(): name for name in reader.fieldnames}
        parcel_column = columns.get("parcel_id_normalized") or columns.get("parcel_id")
        date_column = columns.get("sale_date")
        price_column = columns.get("sale_price")
        instrument_column = columns.get("instrument")

        if not parcel_column or not date_column:
            raise ValueError(
                f"{path} needs parcel_id and sale_date columns; found {reader.fieldnames}"
            )

        for row in reader:
            parcel = (row.get(parcel_column) or "").strip()
            sale_date = coerce_date(row.get(date_column))
            if not parcel or sale_date is None:
                skipped += 1
                continue

            price = None
            if price_column:
                raw_price = (row.get(price_column) or "").replace("$", "").replace(",", "").strip()
                try:
                    price = float(raw_price) if raw_price else None
                except ValueError:
                    price = None

            outcomes.append(
                SaleOutcome(
                    parcel_id_normalized=parcel,
                    sale_date=sale_date,
                    sale_price=price,
                    instrument=(row.get(instrument_column) or None) if instrument_column else None,
                )
            )

    logger.info("sale_outcomes_loaded", path=str(path), loaded=len(outcomes), skipped=skipped)
    return outcomes


def index_by_parcel(outcomes: Iterable[SaleOutcome]) -> Dict[str, List[SaleOutcome]]:
    """Group outcomes by parcel, each list sorted by date."""
    index: Dict[str, List[SaleOutcome]] = {}
    for outcome in outcomes:
        index.setdefault(outcome.parcel_id_normalized, []).append(outcome)
    for sales in index.values():
        sales.sort(key=lambda sale: sale.sale_date)
    return index


def label_cohort(
    cohort: Sequence[CohortMember],
    outcomes: Iterable[SaleOutcome],
    horizon_days: int = 180,
    arms_length_only: bool = True,
) -> List[LabelledMember]:
    """
    Attach outcomes to a cohort, counting only sales inside the horizon.

    A member is positive when the parcel transferred in ``(as_of, as_of +
    horizon_days]``. Sales on or before ``as_of`` are ignored: they are history
    the scorer could legitimately have seen, not outcomes. Sales after the
    horizon are ignored too, so every member is evaluated over the same window.

    Args:
        cohort: Members scored as of their own ``as_of`` date.
        outcomes: Recorded sales for any parcels.
        horizon_days: Length of the observation window.
        arms_length_only: Ignore nominal transfers, which are not real sales.

    Returns:
        One labelled member per cohort member, in the order given.

    Raises:
        ValueError: If ``horizon_days`` is not positive, which would make every
            label vacuously false.
    """
    if horizon_days <= 0:
        raise ValueError(f"horizon_days must be positive, got {horizon_days}")

    index = index_by_parcel(outcomes)
    labelled: List[LabelledMember] = []

    for member in cohort:
        window_end = member.as_of + timedelta(days=horizon_days)
        match: Optional[SaleOutcome] = None

        for sale in index.get(member.parcel_id_normalized, ()):
            if sale.sale_date <= member.as_of or sale.sale_date > window_end:
                continue
            if arms_length_only and not sale.is_arms_length:
                continue
            match = sale  # sorted by date, so this ends on the earliest match
            break

        labelled.append(
            LabelledMember(
                member=member,
                sold=match is not None,
                sale_date=match.sale_date if match else None,
                sale_price=match.sale_price if match else None,
            )
        )

    positives = sum(1 for entry in labelled if entry.sold)
    logger.info(
        "cohort_labelled",
        members=len(labelled),
        positives=positives,
        horizon_days=horizon_days,
    )
    return labelled


def assert_features_precede_outcomes(
    labelled: Sequence[LabelledMember],
    feature_dates: Dict[str, date],
) -> None:
    """
    Verify no member's features were computed after its outcome.

    This is the check that catches the failure that would otherwise go unnoticed:
    building features from today's records while labelling with a sale that has
    already happened. Such a model looks excellent offline and is worthless live.

    Checking against ``as_of`` is sufficient. Labelling only counts sales after
    ``as_of``, so features that precede ``as_of`` necessarily precede the sale
    that labelled the member.

    Args:
        labelled: The labelled cohort.
        feature_dates: When each parcel's features were computed, by parcel id.

    Raises:
        PointInTimeError: If any parcel's features postdate its ``as_of`` date.
    """
    violations = []

    for entry in labelled:
        parcel = entry.member.parcel_id_normalized
        computed_at = feature_dates.get(parcel)
        if computed_at is None:
            continue

        if computed_at > entry.member.as_of:
            sold = f", which its sale on {entry.sale_date} precedes" if (
                entry.sale_date and computed_at >= entry.sale_date
            ) else ""
            violations.append(
                f"{parcel}: features computed {computed_at}, after as_of "
                f"{entry.member.as_of}{sold}"
            )

    if violations:
        raise PointInTimeError(
            "Features postdate the outcomes they are used to predict, so any "
            "measured signal is leakage:\n  " + "\n  ".join(violations[:20])
            + (f"\n  ... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )
