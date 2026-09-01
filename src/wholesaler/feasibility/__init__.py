"""
Feasibility testing for lead scoring.

Answers one question before any ML is built: for parcels that showed distress at
a point in time, did the scorer's ranking predict which ones actually
transacted? Public deed records make that answerable retroactively, so it can be
settled with history rather than by operating for a year.

The answer decides whether a labelling pipeline and real models are worth
building, or whether the edge lies in data coverage and speed instead.
"""
from src.wholesaler.feasibility.evaluate import FeasibilityReport, evaluate
from src.wholesaler.feasibility.outcomes import (
    CohortMember,
    LabelledMember,
    PointInTimeError,
    SaleOutcome,
    assert_features_precede_outcomes,
    label_cohort,
    load_sale_outcomes,
)
from src.wholesaler.feasibility.reconstruct import (
    CoverageReport,
    DistressEvent,
    Valuation,
    ViolationRecord,
    reconstruct_cohort,
)
from src.wholesaler.feasibility.report import render
from src.wholesaler.feasibility.sources import (
    load_events,
    load_valuations,
    load_violations,
    write_cohort,
)

__all__ = [
    "CohortMember",
    "CoverageReport",
    "DistressEvent",
    "FeasibilityReport",
    "LabelledMember",
    "PointInTimeError",
    "SaleOutcome",
    "assert_features_precede_outcomes",
    "Valuation",
    "ViolationRecord",
    "evaluate",
    "label_cohort",
    "load_events",
    "load_sale_outcomes",
    "load_valuations",
    "load_violations",
    "reconstruct_cohort",
    "render",
    "write_cohort",
]
