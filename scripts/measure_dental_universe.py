#!/usr/bin/env python3
"""
Measure the dental office universe, and write the target list.

Matches licensed dentists to the parcels they practise on, counts how many
buildings the practising dentist appears to own, and reports how many change
hands in a year. Those numbers decide whether this is a statewide business or a
side project, and nothing downstream is worth building until they exist.

Usage:
    python scripts/measure_dental_universe.py \\
        --licensees data/mqa_dentists.txt \\
        --parcels data/nal_orange_2025.csv \\
        --parcels data/nal_seminole_2025.csv \\
        --out data/dental_targets.csv

    # Cast a wider net if the professional-services code alone matches little
    python scripts/measure_dental_universe.py ... --wider-use-codes

Getting the inputs:

  Licensees  Florida DOH Medical Quality Assurance data download, filtered to
             Dentistry. Pipe-delimited, refreshed daily, free public record.
             https://flhealthsource.gov/data-portal/

  Parcels    Florida DOR annual NAL tax rolls, one file per county per year.
             Use code 0019 is "Professional Services Buildings".

The target list this writes carries one row per matched building, ready to score
with the dental_office profile.
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.dental.matching import match_licensees_to_parcels  # noqa: E402
from src.wholesaler.dental.sources import (  # noqa: E402
    DEFAULT_USE_CODES,
    WIDER_OFFICE_USE_CODES,
    load_licensees,
    load_parcels,
)
from src.wholesaler.dental.universe import measure_universe, render  # noqa: E402

TARGET_COLUMNS = [
    "parcel_id",
    "site_street",
    "site_city",
    "site_zip",
    "county",
    "owner_name",
    "owner_occupied",
    "practitioner_count",
    "primary_dentist",
    "license_date",
    "years_licensed",
    "dor_use_code",
    "building_sqft",
    "year_built",
    "just_value",
    "last_sale_date",
]


def write_targets(path: Path, matches) -> None:
    """Write one row per matched building, ordered by the matcher."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(TARGET_COLUMNS)

        for match in matches:
            parcel = match.parcel
            # The longest-licensed practitioner is the one whose exit drives the
            # building, so they lead the row.
            # Undated licences sort last so a real date always wins.
            dentists = sorted(
                match.licensees, key=lambda licensee: licensee.license_date or date.max
            )
            primary = dentists[0] if dentists else None

            writer.writerow(
                [
                    parcel.parcel_id_normalized,
                    parcel.site_street,
                    parcel.site_city,
                    parcel.site_zip,
                    parcel.county,
                    parcel.owner_name,
                    "yes" if match.owner_occupied else "no",
                    match.practitioner_count,
                    primary.full_name if primary else "",
                    primary.license_date.isoformat() if primary and primary.license_date else "",
                    f"{primary.years_licensed():.1f}" if primary and primary.license_date else "",
                    parcel.dor_use_code,
                    parcel.building_sqft or "",
                    parcel.year_built or "",
                    parcel.just_value or "",
                    parcel.last_sale_date.isoformat() if parcel.last_sale_date else "",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--licensees", type=Path, required=True,
        help="MQA dental licensee download",
    )
    parser.add_argument(
        "--parcels", type=Path, action="append", required=True, metavar="CSV",
        help="NAL tax roll. Repeatable, once per county.",
    )
    parser.add_argument("--out", type=Path, help="Target list CSV to write")
    parser.add_argument(
        "--wider-use-codes", action="store_true",
        help="Include general office codes (0017, 0018) alongside professional "
             "services (0019). Some counties code dental buildings there.",
    )
    parser.add_argument(
        "--include-inactive", action="store_true",
        help="Keep licences that are not currently active.",
    )
    args = parser.parse_args()

    use_codes = WIDER_OFFICE_USE_CODES if args.wider_use_codes else DEFAULT_USE_CODES

    try:
        licensees = load_licensees(args.licensees, active_only=not args.include_inactive)
        print(f"  {args.licensees.name}: {len(licensees):,} licensees")

        parcels = []
        for path in args.parcels:
            loaded = load_parcels(path, use_codes=use_codes, county=path.stem)
            print(f"  {path.name}: {len(loaded):,} office parcels")
            parcels.extend(loaded)
    except (FileNotFoundError, ValueError) as error:
        print(f"Could not read an extract: {error}", file=sys.stderr)
        return 1

    if not licensees:
        print("No licensees were loaded.", file=sys.stderr)
        return 1
    if not parcels:
        print(
            f"No parcels carried use code {', '.join(use_codes)}. Try "
            "--wider-use-codes, or check the roll's use code column.",
            file=sys.stderr,
        )
        return 1

    matches = match_licensees_to_parcels(licensees, parcels)
    report = measure_universe(licensees, parcels, matches)

    print()
    print(render(report))

    if args.out:
        write_targets(args.out, matches)
        print(f"\n  Target list written to {args.out} ({len(matches):,} buildings)")

    # A universe too small to validate against is a real answer, not a failure,
    # but it should not read as success either.
    return 0 if report.owner_occupied >= 200 else 2


if __name__ == "__main__":
    raise SystemExit(main())
