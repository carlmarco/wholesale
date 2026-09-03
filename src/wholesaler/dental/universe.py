"""
How big is the opportunity, really.

Everything downstream - the scorer, a labelling pipeline, any model - depends on
a number nobody has measured: how many separately-parcelled dental buildings
exist, how many are owned by the dentist practising in them, and how many change
hands in a year.

Those three numbers decide whether this is a statewide business or a side
project, and they are cheap to establish. This module produces them, and is
deliberately blunt about the funnel: at each stage it reports how many records
were lost, because a low match rate is a data problem to fix rather than a small
universe to accept.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

from src.wholesaler.dental.matching import AddressMatch, address_match_key
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

# Below this share of licensees resolving to a parcel, the bottleneck is address
# parsing rather than the size of the market, and the totals mean little.
HEALTHY_MATCH_RATE = 0.35

# A dentist this far past licensure is in or beyond the retirement window the
# dental profile scores on.
EXIT_WINDOW_YEARS = 29


@dataclass
class UniverseReport:
    """
    The funnel from licensees to acquirable buildings.

    Attributes:
        licensees: Licences read.
        licensees_with_address: Those carrying a usable practice address.
        distinct_practice_addresses: Buildings implied by those addresses.
        parcels: Office-coded parcels read.
        parcels_with_address: Those carrying a usable situs address.
        matched_buildings: Parcels at least one licensee resolved to.
        owner_occupied: Matched buildings whose owner looks like the dentist.
        multi_practitioner: Matched buildings with more than one licensee.
        in_exit_window: Owner-occupied buildings whose dentist is near retirement.
        transactions_by_year: Recorded sales of matched buildings, by year.
        counties: Matched building counts by county.
    """
    licensees: int = 0
    licensees_with_address: int = 0
    distinct_practice_addresses: int = 0
    parcels: int = 0
    parcels_with_address: int = 0
    matched_buildings: int = 0
    owner_occupied: int = 0
    multi_practitioner: int = 0
    in_exit_window: int = 0
    transactions_by_year: Dict[int, int] = field(default_factory=dict)
    counties: Dict[str, int] = field(default_factory=dict)

    @property
    def match_rate(self) -> float:
        """Share of licensee addresses that found a parcel."""
        if not self.distinct_practice_addresses:
            return 0.0
        return self.matched_buildings / self.distinct_practice_addresses

    @property
    def owner_occupied_rate(self) -> float:
        """Share of matched buildings the practising dentist appears to own."""
        if not self.matched_buildings:
            return 0.0
        return self.owner_occupied / self.matched_buildings

    @property
    def annual_transactions(self) -> float:
        """Mean recorded sales per year across the years observed."""
        if not self.transactions_by_year:
            return 0.0
        return sum(self.transactions_by_year.values()) / len(self.transactions_by_year)

    @property
    def annual_turnover_rate(self) -> float:
        """Share of the owner-occupied universe transacting in a typical year."""
        if not self.owner_occupied:
            return 0.0
        return self.annual_transactions / self.owner_occupied

    def warnings(self) -> List[str]:
        """What would make these numbers misleading."""
        notes: List[str] = []

        if not self.licensees:
            return ["No licensees were read; nothing can be concluded."]

        if not self.matched_buildings:
            notes.append(
                "No licensee address resolved to a parcel. Either the roll covers "
                "different counties than the licensees practise in, or the address "
                "columns were not the ones expected. This is a plumbing failure, "
                "not a finding about the market."
            )
        elif self.match_rate < HEALTHY_MATCH_RATE:
            notes.append(
                f"Only {self.match_rate:.0%} of practice addresses found a parcel. "
                "Below roughly a third, the bottleneck is usually address parsing "
                "or missing counties rather than a genuinely small universe, so "
                "treat the totals as a floor."
            )

        if self.owner_occupied and self.owner_occupied < 200:
            notes.append(
                f"{self.owner_occupied} owner-occupied buildings is below the 200 "
                "the feasibility harness needs to return a verdict. Add counties "
                "before trying to validate a scorer against outcomes."
            )

        if not self.transactions_by_year:
            notes.append(
                "The roll carried no sale dates, so turnover could not be measured. "
                "Supply a sales extract to establish the annual transaction rate - "
                "the number that decides whether a pipeline can be filled."
            )

        return notes


def measure_universe(
    licensees: Sequence[object],
    parcels: Sequence[object],
    matches: Sequence[AddressMatch],
    as_of: Optional[date] = None,
) -> UniverseReport:
    """
    Count the funnel from licensees to acquirable buildings.

    Args:
        licensees: Every licence read.
        parcels: Every office-coded parcel read.
        matches: Output of ``match_licensees_to_parcels``.
        as_of: Date the exit window is measured against; defaults to today.

    Returns:
        The report, including the caveats that would make it misleading.
    """
    reference = as_of or date.today()
    report = UniverseReport()

    report.licensees = len(licensees)
    licensee_keys = set()
    for licensee in licensees:
        key = address_match_key(
            getattr(licensee, "practice_street", ""), getattr(licensee, "practice_zip", "")
        )
        if key:
            report.licensees_with_address += 1
            licensee_keys.add(key)
    report.distinct_practice_addresses = len(licensee_keys)

    report.parcels = len(parcels)
    report.parcels_with_address = sum(
        1
        for parcel in parcels
        if address_match_key(getattr(parcel, "site_street", ""), getattr(parcel, "site_zip", ""))
    )

    report.matched_buildings = len(matches)

    counties: Counter = Counter()
    transactions: Counter = Counter()

    for match in matches:
        parcel = match.parcel

        if match.owner_occupied:
            report.owner_occupied += 1

            near_exit = any(
                (getattr(licensee, "years_licensed", lambda _as_of=None: None)(reference) or 0)
                >= EXIT_WINDOW_YEARS
                for licensee in match.licensees
            )
            if near_exit:
                report.in_exit_window += 1

        if match.practitioner_count > 1:
            report.multi_practitioner += 1

        county = getattr(parcel, "county", "") or "unknown"
        counties[county] += 1

        sale_date = getattr(parcel, "last_sale_date", None)
        if sale_date is not None:
            transactions[sale_date.year] += 1

    report.counties = dict(counties.most_common())
    report.transactions_by_year = dict(sorted(transactions.items()))

    logger.info(
        "universe_measured",
        licensees=report.licensees,
        matched=report.matched_buildings,
        owner_occupied=report.owner_occupied,
        match_rate=round(report.match_rate, 3),
    )
    return report


def render(report: UniverseReport) -> str:
    """Format the report for a terminal."""
    lines = [
        "=" * 72,
        "DENTAL OFFICE UNIVERSE",
        "=" * 72,
        "",
        "  Funnel",
        f"    Licensees read                 {report.licensees:>8,}",
        f"    With a usable address          {report.licensees_with_address:>8,}",
        f"    Distinct practice addresses    {report.distinct_practice_addresses:>8,}",
        f"    Office-coded parcels read      {report.parcels:>8,}",
        f"    Matched to a building          {report.matched_buildings:>8,}"
        f"   ({report.match_rate:.0%} of addresses)",
        "",
        "  The acquirable universe",
        f"    Owner-occupied buildings       {report.owner_occupied:>8,}"
        f"   ({report.owner_occupied_rate:.0%} of matched)",
        f"    Dentist near retirement        {report.in_exit_window:>8,}",
        f"    Multi-practitioner buildings   {report.multi_practitioner:>8,}",
    ]

    if report.transactions_by_year:
        lines += [
            "",
            "  Turnover",
            f"    Recorded sales per year        {report.annual_transactions:>8,.1f}",
            f"    Annual turnover rate           {report.annual_turnover_rate:>8.1%}",
            "    By year: "
            + ", ".join(f"{year}={count}" for year, count in report.transactions_by_year.items()),
        ]

    if report.counties:
        top = list(report.counties.items())[:8]
        lines += [
            "",
            "  Counties (top)",
            "    " + ", ".join(f"{name}={count}" for name, count in top),
        ]

    warnings = report.warnings()
    if warnings:
        lines += ["", "  Read this before believing the numbers:"]
        for warning in warnings:
            lines.append(f"    - {warning}")

    lines.append("=" * 72)
    return "\n".join(lines)
