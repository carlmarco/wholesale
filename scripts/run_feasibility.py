#!/usr/bin/env python3
"""
Test whether the lead scorer's ranking predicts real transactions.

Builds a cohort of parcels that showed distress at a point in time, scores each
one, joins recorded sales to see which actually transacted inside a horizon, and
reports whether the ranking beat the base rate.

Run this before building a labelling pipeline or training any model. If the
scorer shows no lift over picking at random, a model trained on the same
features will inherit that, and the effort belongs in data coverage instead.

Usage:
    python scripts/run_feasibility.py --sales data/sales_extract.csv
    python scripts/run_feasibility.py --sales data/sales.csv --horizon-days 365
    python scripts/run_feasibility.py --sales data/sales.csv --cohort data/cohort.csv

The sales extract is a CSV of recorded transfers with parcel_id, sale_date and
optionally sale_price. For Orange County FL these come from the Comptroller's
Official Records and the Property Appraiser's sales history; any county that
publishes deed transfers works the same way.

Without --cohort, the cohort is read from the database: every scored lead, using
its scored_at date as the point in time.
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.feasibility import (  # noqa: E402
    CohortMember,
    evaluate,
    label_cohort,
    load_sale_outcomes,
    render,
)
from src.wholesaler.utils.dates import coerce_date  # noqa: E402


def load_cohort_from_csv(path: Path) -> list:
    """
    Read a cohort from CSV.

    Columns: parcel_id, as_of, score, and optionally tier. Use this to test a
    historically reconstructed cohort without loading it into the database.
    """
    members = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")

        columns = {name.lower().strip(): name for name in reader.fieldnames}
        parcel_column = columns.get("parcel_id_normalized") or columns.get("parcel_id")
        as_of_column = columns.get("as_of") or columns.get("scored_at")
        score_column = columns.get("score") or columns.get("total_score")

        missing = [
            label
            for label, column in (
                ("parcel_id", parcel_column),
                ("as_of", as_of_column),
                ("score", score_column),
            )
            if column is None
        ]
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

        for row in reader:
            parcel = (row.get(parcel_column) or "").strip()
            as_of = coerce_date(row.get(as_of_column))
            raw_score = (row.get(score_column) or "").strip()
            if not parcel or as_of is None or not raw_score:
                continue
            members.append(
                CohortMember(
                    parcel_id_normalized=parcel,
                    as_of=as_of,
                    score=float(raw_score),
                    tier=(row.get(columns["tier"]) if "tier" in columns else None),
                )
            )
    return members


def load_cohort_from_database() -> list:
    """
    Read every scored lead from the database as a cohort.

    Each lead's ``scored_at`` is its point in time. This is only sound if the
    score was computed from data available on that date - which holds for scores
    written by the live pipeline, and does not hold if the table was backfilled
    by rescoring old parcels against today's data.
    """
    from src.wholesaler.db.repository import LeadScoreRepository
    from src.wholesaler.db.session import get_db_session

    repository = LeadScoreRepository()
    members = []

    with get_db_session() as session:
        for lead in repository.get_all(session):
            scored_at = getattr(lead, "scored_at", None)
            if scored_at is None:
                continue
            members.append(
                CohortMember(
                    parcel_id_normalized=lead.parcel_id_normalized,
                    as_of=scored_at.date() if hasattr(scored_at, "date") else scored_at,
                    score=float(lead.total_score),
                    tier=lead.tier,
                )
            )
    return members


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--sales", type=Path, required=True,
        help="CSV of recorded sales (parcel_id, sale_date, sale_price)",
    )
    parser.add_argument(
        "--cohort", type=Path,
        help="CSV of scored parcels (parcel_id, as_of, score). Defaults to the database.",
    )
    parser.add_argument(
        "--horizon-days", type=int, default=180,
        help="Days after scoring in which a sale counts as an outcome (default: 180)",
    )
    parser.add_argument(
        "--budgets", type=int, nargs="+", default=[10, 25, 50, 100],
        help="Action budgets to evaluate (default: 10 25 50 100)",
    )
    parser.add_argument(
        "--include-nominal-transfers", action="store_true",
        help="Count quitclaims and other non-market transfers as sales",
    )
    args = parser.parse_args()

    try:
        outcomes = load_sale_outcomes(args.sales)
    except (FileNotFoundError, ValueError) as error:
        print(f"Could not read the sales extract: {error}", file=sys.stderr)
        return 1

    try:
        cohort = load_cohort_from_csv(args.cohort) if args.cohort else load_cohort_from_database()
    except Exception as error:
        print(f"Could not build the cohort: {error}", file=sys.stderr)
        return 1

    if not cohort:
        print(
            "The cohort is empty. Score some parcels first, or pass --cohort with a "
            "historically reconstructed one.",
            file=sys.stderr,
        )
        return 1

    labelled = label_cohort(
        cohort,
        outcomes,
        horizon_days=args.horizon_days,
        arms_length_only=not args.include_nominal_transfers,
    )
    report = evaluate(labelled, horizon_days=args.horizon_days, budgets=tuple(args.budgets))

    print(render(report))

    earliest = min(member.as_of for member in cohort)
    latest = max(member.as_of for member in cohort)
    print(f"\n  Cohort spans {earliest} to {latest}.")
    if latest > date.today().replace(year=date.today().year - 1):
        print(
            "  Note: recent members may not have had a full horizon to transact in, "
            "which biases the base rate downward."
        )

    return 0 if report.is_conclusive else 2


if __name__ == "__main__":
    raise SystemExit(main())
