#!/usr/bin/env python3
"""
Rebuild a scored cohort from historical distress events.

Scores each past event as of the day it happened, using only data available on
that date, and writes the cohort that scripts/run_feasibility.py consumes.

Usage:
    python scripts/build_cohort.py \\
        --events data/tax_sales_2019_2023.csv --event-type tax_sale \\
        --events data/foreclosures_2019_2023.csv --event-type foreclosure \\
        --violations data/code_violations_history.csv \\
        --valuations data/nal_rolls_2018_2023.csv \\
        --out data/cohort.csv

    python scripts/run_feasibility.py --cohort data/cohort.csv --sales data/sales.csv

Each --events file needs a matching --event-type unless it carries an
event_type column. Extracts are historical exports, not live API pulls: the
point is to reconstruct what was knowable then.

Valuations are optional but change what the test can measure. Without them the
profitability gate cannot run, every member fails it, and the feasibility test
covers distress and disposition only. The coverage report says so.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.feasibility.reconstruct import reconstruct_cohort  # noqa: E402
from src.wholesaler.feasibility.sources import (  # noqa: E402
    load_events,
    load_valuations,
    load_violations,
    write_cohort,
)
from src.wholesaler.scoring import HybridBucketScorer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--events", type=Path, action="append", required=True, metavar="CSV",
        help="Historical distress events. Repeatable, once per source.",
    )
    parser.add_argument(
        "--event-type", action="append", default=[],
        choices=["tax_sale", "foreclosure", "code_violation"],
        help="Type for the corresponding --events file, in the same order.",
    )
    parser.add_argument("--violations", type=Path, help="Code enforcement history")
    parser.add_argument("--valuations", type=Path, help="Annual certified tax rolls")
    parser.add_argument("--out", type=Path, required=True, help="Cohort CSV to write")
    parser.add_argument(
        "--all-events", action="store_true",
        help="Keep every event rather than one per parcel. Repeat parcels share "
             "an outcome, which breaks the independence the intervals assume.",
    )
    args = parser.parse_args()

    if args.event_type and len(args.event_type) != len(args.events):
        print(
            f"Got {len(args.events)} --events files but {len(args.event_type)} "
            "--event-type values. Pass one type per file, in the same order, or "
            "none if every file carries an event_type column.",
            file=sys.stderr,
        )
        return 1

    events = []
    try:
        for index, path in enumerate(args.events):
            event_type = args.event_type[index] if args.event_type else None
            loaded = load_events(path, event_type=event_type)
            print(f"  {path.name}: {len(loaded):,} events")
            events.extend(loaded)

        violations = load_violations(args.violations) if args.violations else []
        if args.violations:
            print(f"  {args.violations.name}: {len(violations):,} violations")

        valuations = load_valuations(args.valuations) if args.valuations else []
        if args.valuations:
            print(f"  {args.valuations.name}: {len(valuations):,} valuations")
    except (FileNotFoundError, ValueError) as error:
        print(f"Could not read an extract: {error}", file=sys.stderr)
        return 1

    if not events:
        print("No usable events were loaded.", file=sys.stderr)
        return 1

    members, coverage = reconstruct_cohort(
        events,
        scorer=HybridBucketScorer(),
        violations=violations,
        valuations=valuations,
        one_event_per_parcel=not args.all_events,
    )

    if not members:
        print("The reconstruction produced no cohort members.", file=sys.stderr)
        return 1

    write_cohort(args.out, members)

    span_start = min(member.as_of for member in members)
    span_end = max(member.as_of for member in members)
    tiers = {}
    for member in members:
        tiers[member.tier] = tiers.get(member.tier, 0) + 1

    print()
    print("=" * 72)
    print("COHORT RECONSTRUCTED")
    print("=" * 72)
    print(f"  Members            {coverage.members:,}")
    print(f"  Span               {span_start} to {span_end}")
    print(f"  Violation history  {coverage.with_violation_history:,}")
    print(f"  Historical values  {coverage.with_valuation:,}")
    print(f"  Prior distress     {coverage.with_prior_events:,}")
    print(f"  Tiers              {', '.join(f'{k}={v}' for k, v in sorted(tiers.items()))}")
    print(f"  Written to         {args.out}")

    warnings = coverage.warnings()
    if warnings:
        print()
        print("  What this cohort cannot show:")
        for warning in warnings:
            print(f"    - {warning}")

    print("=" * 72)
    print(f"\nNext: python scripts/run_feasibility.py --cohort {args.out} --sales <sales.csv>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
