"""Render a feasibility report as text."""
from __future__ import annotations

from src.wholesaler.feasibility.evaluate import FeasibilityReport

VERDICT_GUIDANCE = {
    "signal": (
        "Build the labelling pipeline (step 2): ingest deed and sale records "
        "keyed on parcel_id_normalized into actual_sale_price and label_date, "
        "then fit P(transacts) and E[sale price] on real outcomes."
    ),
    "no signal": (
        "Do not build the ML platform yet. A model trained on these features "
        "would inherit the same absence of signal. Test whether coverage and "
        "speed-to-lead are the real edge before investing further."
    ),
    "insufficient data": (
        "Widen the cohort before drawing any conclusion. More event types, more "
        "years of history, or a longer horizon - whichever is cheapest."
    ),
}


def render(report: FeasibilityReport) -> str:
    """Format a report for a terminal."""
    lines = [
        "=" * 72,
        "LEAD SCORING FEASIBILITY",
        "=" * 72,
        "",
        f"  Cohort           {report.cohort_size:,} parcels",
        f"  Transacted       {report.positives:,} within {report.horizon_days} days",
        f"  Base rate        {report.base_rate:.2%}  (what random selection achieves)",
    ]

    if report.auc:
        lines.append(f"  AUC              {report.auc}")

    lines += ["", "  Ranking quality (90% bootstrap intervals)", ""]

    if report.lift_at_k:
        lines.append(f"  {'k':>6}  {'precision@k':>26}  {'lift@k':>26}  beats chance")
        for result in report.lift_at_k:
            lines.append(
                f"  {result.k:>6}  {str(result.precision):>26}  "
                f"{str(result.lift):>26}  {'yes' if result.beats_chance else 'no'}"
            )
    else:
        lines.append("  (cohort smaller than every action budget tested)")

    lines += [
        "",
        "-" * 72,
        f"  VERDICT: {report.verdict.upper()}",
        "",
        f"  {report.reasoning}",
        "",
        f"  {VERDICT_GUIDANCE[report.verdict]}",
        "=" * 72,
    ]
    return "\n".join(lines)
