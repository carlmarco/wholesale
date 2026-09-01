"""
Read historical source extracts.

The reconstruction needs events, violations and valuations as they were
published, not as the live API serves them today. Those come from exports the
operator pulls once per source, so everything here reads CSV rather than calling
an API - it keeps the historical inputs auditable and lets the whole pipeline
run without network access.

Column names are matched case-insensitively against a few common spellings,
because county exports rarely agree on them.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, TypeVar

from src.wholesaler.feasibility.reconstruct import (
    EVENT_TYPES,
    DistressEvent,
    Valuation,
    ViolationRecord,
)
from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.utils.dates import coerce_date
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

_standardizer = AddressStandardizer()


def _resolve(columns: Dict[str, str], *candidates: str) -> Optional[str]:
    """First candidate present in the header, case-insensitively."""
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None


def _number(raw: Optional[str]) -> Optional[float]:
    """Parse a currency-ish string, tolerating $ and thousands separators."""
    if raw is None:
        return None
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _read(path: Path, parse_row: Callable[[Dict[str, str], Dict[str, str]], Optional[T]]) -> List[T]:
    """
    Read a CSV, applying ``parse_row`` and counting what it rejected.

    Args:
        path: The extract.
        parse_row: Receives (row, lowercase-column-index) and returns a parsed
            record or None to skip.

    Raises:
        FileNotFoundError: If the extract is absent.
        ValueError: If the file has no header.
    """
    if not path.exists():
        raise FileNotFoundError(f"No extract at {path}")

    parsed: List[T] = []
    skipped = 0

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")

        columns = {name.lower().strip(): name for name in reader.fieldnames}
        for row in reader:
            record = parse_row(row, columns)
            if record is None:
                skipped += 1
            else:
                parsed.append(record)

    logger.info("extract_read", path=str(path), parsed=len(parsed), skipped=skipped)
    return parsed


def _parcel(row: Dict[str, str], columns: Dict[str, str], *candidates: str) -> Optional[str]:
    """
    Read and normalise a parcel identifier.

    Sources punctuate parcel numbers differently, so everything is reduced to
    digits the same way the ETL does - otherwise the same parcel appears under
    several keys and nothing joins.
    """
    column = _resolve(columns, *candidates)
    if column is None:
        return None
    return _standardizer.normalize_parcel_id(row.get(column) or "")


def load_events(path: Path, event_type: Optional[str] = None) -> List[DistressEvent]:
    """
    Read distress events.

    Columns: ``parcel_id``, a date (``event_date``, ``sale_date``,
    ``auction_date``, ``case_date`` or ``filed_date``), and optionally
    ``event_type``, ``default_amount``, ``opening_bid``.

    Args:
        path: The extract.
        event_type: Applied to every row when the file has no event_type column,
            which is the normal case for a single-source export.

    Raises:
        ValueError: If no event type can be determined for a row, or the given
            type is not recognised.
    """
    if event_type is not None and event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}; expected one of {EVENT_TYPES}")

    def parse(row, columns):
        parcel = _parcel(row, columns, "parcel_id_normalized", "parcel_id", "parcel", "folio")
        if not parcel:
            return None

        date_column = _resolve(
            columns, "event_date", "sale_date", "auction_date", "case_date", "filed_date"
        )
        event_date = coerce_date(row.get(date_column)) if date_column else None
        if event_date is None:
            return None

        type_column = _resolve(columns, "event_type", "seed_type")
        resolved = (row.get(type_column) or "").strip().lower() if type_column else None
        resolved = resolved or event_type
        if resolved not in EVENT_TYPES:
            raise ValueError(
                f"{path}: row for parcel {parcel} has event type {resolved!r}; pass "
                f"--event-type or add an event_type column. Expected one of {EVENT_TYPES}"
            )

        default_column = _resolve(columns, "default_amount", "judgment_amount")
        bid_column = _resolve(columns, "opening_bid", "minimum_bid")

        return DistressEvent(
            parcel_id_normalized=parcel,
            event_date=event_date,
            event_type=resolved,
            default_amount=_number(row.get(default_column)) if default_column else None,
            opening_bid=_number(row.get(bid_column)) if bid_column else None,
        )

    return _read(path, parse)


def load_violations(path: Path) -> List[ViolationRecord]:
    """
    Read code enforcement history.

    Columns: ``parcel_id``, a filing date (``case_date``, ``filed_date`` or
    ``violation_date``), and optionally a close date (``closed_date``,
    ``close_date`` or ``resolved_date``).

    The close date is what makes open-violation counts reconstructable. Without
    it the reconstruction reports that signal as uncovered rather than inferring
    a past status from a current one.
    """
    def parse(row, columns):
        parcel = _parcel(row, columns, "parcel_id_normalized", "parcel_id", "parcel", "folio")
        if not parcel:
            return None

        filed_column = _resolve(columns, "case_date", "filed_date", "violation_date", "filed_on")
        filed_on = coerce_date(row.get(filed_column)) if filed_column else None
        if filed_on is None:
            return None

        closed_column = _resolve(columns, "closed_date", "close_date", "resolved_date", "closed_on")
        closed_on = coerce_date(row.get(closed_column)) if closed_column else None

        return ViolationRecord(
            parcel_id_normalized=parcel, filed_on=filed_on, closed_on=closed_on
        )

    return _read(path, parse)


def load_valuations(path: Path) -> List[Valuation]:
    """
    Read annual certified values.

    Columns: ``parcel_id``, ``roll_year``, and any of ``total_mkt``,
    ``assessed_val``, ``living_area``, ``year_built``, ``equity_percent``.

    In Florida these come from the Department of Revenue's annual NAL tax roll
    files, one per county per year. A roll year must never be later than the
    event being scored: the roll following a sale reflects that sale.
    """
    def parse(row, columns):
        parcel = _parcel(row, columns, "parcel_id_normalized", "parcel_id", "parcel", "folio")
        if not parcel:
            return None

        year_column = _resolve(columns, "roll_year", "tax_year", "year")
        raw_year = _number(row.get(year_column)) if year_column else None
        if raw_year is None:
            return None

        def value(*names):
            column = _resolve(columns, *names)
            return _number(row.get(column)) if column else None

        year_built = value("year_built", "act_yr_blt", "eff_yr_blt")

        return Valuation(
            parcel_id_normalized=parcel,
            roll_year=int(raw_year),
            total_mkt=value("total_mkt", "jv", "just_value", "market_value"),
            assessed_val=value("assessed_val", "av_nsd", "assessed_value"),
            living_area=value("living_area", "tot_lvg_ar", "heated_area"),
            year_built=int(year_built) if year_built else None,
            equity_percent=value("equity_percent"),
        )

    return _read(path, parse)


def write_cohort(path: Path, members: Sequence) -> None:
    """
    Write a cohort in the shape ``run_feasibility.py --cohort`` expects.

    Args:
        path: Destination CSV.
        members: CohortMember records.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parcel_id", "as_of", "score", "tier"])
        for member in members:
            writer.writerow(
                [
                    member.parcel_id_normalized,
                    member.as_of.isoformat(),
                    f"{member.score:.4f}",
                    member.tier or "",
                ]
            )
    logger.info("cohort_written", path=str(path), members=len(members))
