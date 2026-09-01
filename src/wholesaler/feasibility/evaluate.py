"""
Does the scorer actually rank leads better than chance?

The business works a fixed number of leads a week, so this is a ranking problem
under an action budget, not a classification problem. The measure that matters
is precision@k: of the top k leads the scorer surfaces, what share actually
transacted. Lift@k compares that to the base rate - lift of 1.0 means the
ranking is worth nothing.

Every estimate here carries a bootstrap confidence interval. With a few hundred
parcels and a low base rate, precision@10 of 20% can be two events; reporting it
as "7x lift" without an interval is how a project convinces itself it has signal
it does not have.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from src.wholesaler.feasibility.outcomes import LabelledMember

# Below these, the cohort cannot separate a real effect from noise at any
# interval worth reporting. Chosen so the narrowest bootstrap CI on lift is
# still informative rather than spanning an order of magnitude.
MIN_COHORT_SIZE = 200
MIN_POSITIVES = 20

BOOTSTRAP_SAMPLES = 2000
CONFIDENCE = 0.90


def _adjusted_confidence(comparisons: int) -> float:
    """
    Bonferroni-adjust the confidence level for the number of budgets tested.

    Testing four action budgets at 90% and calling signal on any one of them
    gives roughly a one-in-three chance of a false positive under the null. The
    per-budget interval is widened so the family-wide error rate stays at
    1 - CONFIDENCE.
    """
    if comparisons <= 1:
        return CONFIDENCE
    return 1 - (1 - CONFIDENCE) / comparisons


@dataclass(frozen=True)
class Interval:
    """A point estimate with a bootstrap confidence interval."""
    point: float
    low: float
    high: float

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"


@dataclass(frozen=True)
class LiftAtK:
    """Ranking quality at one action budget."""
    k: int
    precision: Interval
    lift: Interval

    @property
    def beats_chance(self) -> bool:
        """Whether the interval excludes 'no better than random'."""
        return self.lift.low > 1.0


@dataclass(frozen=True)
class FeasibilityReport:
    """
    What the cohort says about whether the scorer has signal.

    Attributes:
        cohort_size: Members evaluated.
        positives: Members that transacted inside the horizon.
        base_rate: Share that transacted - the rate random selection achieves.
        horizon_days: Observation window used.
        lift_at_k: Ranking quality at each action budget tested.
        auc: Rank correlation between score and outcome, as a secondary check.
        verdict: One of "signal", "no signal", "insufficient data".
        reasoning: Why that verdict, in a sentence.
    """
    cohort_size: int
    positives: int
    base_rate: float
    horizon_days: int
    lift_at_k: Sequence[LiftAtK]
    auc: Optional[Interval]
    verdict: str
    reasoning: str

    @property
    def is_conclusive(self) -> bool:
        return self.verdict != "insufficient data"


def _precision_at_k(ranked_outcomes: Sequence[int], k: int) -> float:
    """Share of the top k that were positive."""
    if k <= 0:
        return 0.0
    top = ranked_outcomes[:k]
    return sum(top) / len(top)


def _auc(scores: Sequence[float], outcomes: Sequence[int]) -> Optional[float]:
    """
    Probability a random positive outscores a random negative.

    Computed by rank sum rather than a sweep so ties are handled correctly -
    heuristic scores tie often, and treating ties as wins inflates the result.
    """
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    if positives == 0 or negatives == 0:
        return None

    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and scores[order[stop + 1]] == scores[order[index]]:
            stop += 1
        average_rank = (index + stop) / 2 + 1
        for position in range(index, stop + 1):
            ranks[order[position]] = average_rank
        index = stop + 1

    positive_rank_sum = sum(ranks[i] for i, y in enumerate(outcomes) if y)
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _percentile_bounds(values: List[float], confidence: float = CONFIDENCE) -> Tuple[float, float]:
    """Percentile confidence bounds from bootstrap replicates."""
    if not values:
        return (float("nan"), float("nan"))

    values.sort()
    tail = (1 - confidence) / 2
    low = values[max(0, int(tail * len(values)) - 1)]
    high = values[min(len(values) - 1, int((1 - tail) * len(values)))]
    return (low, high)


def _bootstrap_replicates(
    scores: Sequence[float],
    outcomes: Sequence[int],
    budgets: Sequence[int],
    samples: int,
    rng: random.Random,
):
    """
    Resample the cohort once per replicate and derive every statistic from it.

    Each replicate is ranked once and reused across all action budgets and both
    statistics. Ranking per budget instead would sort the cohort an order of
    magnitude more often for identical results.

    Returns:
        (precision_by_k, lift_by_k, auc_values)
    """
    size = len(scores)
    precision_by_k = {k: [] for k in budgets}
    lift_by_k = {k: [] for k in budgets}
    auc_values: List[float] = []

    for _ in range(samples):
        picks = [rng.randrange(size) for _ in range(size)]
        resampled = [(scores[i], outcomes[i]) for i in picks]
        resampled.sort(key=lambda pair: pair[0], reverse=True)

        ranked = [outcome for _, outcome in resampled]
        positives = sum(ranked)
        rate = positives / size

        for k in budgets:
            precision = sum(ranked[:k]) / k
            precision_by_k[k].append(precision)
            if rate > 0:
                lift_by_k[k].append(precision / rate)

        if 0 < positives < size:
            auc = _auc([score for score, _ in resampled], ranked)
            if auc is not None:
                auc_values.append(auc)

    return precision_by_k, lift_by_k, auc_values


def _rank_outcomes(scores: Sequence[float], outcomes: Sequence[int]) -> List[int]:
    """Outcomes ordered by descending score."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [outcomes[i] for i in order]


def evaluate(
    labelled: Sequence[LabelledMember],
    horizon_days: int,
    budgets: Sequence[int] = (10, 25, 50, 100),
    seed: int = 20260901,
) -> FeasibilityReport:
    """
    Measure whether the scorer's ranking beats the base rate.

    Args:
        labelled: The labelled cohort.
        horizon_days: Window the labels were computed over, for reporting.
        budgets: Action budgets to evaluate, dropped when larger than the cohort.
        seed: Bootstrap seed, so a report is reproducible.

    Returns:
        The report, including a verdict that accounts for cohort size.
    """
    scores = [entry.member.score for entry in labelled]
    outcomes = [1 if entry.sold else 0 for entry in labelled]

    size = len(labelled)
    positives = sum(outcomes)
    base_rate = positives / size if size else 0.0

    applicable = [k for k in budgets if k <= size]
    rng = random.Random(seed)
    precision_by_k, lift_by_k, auc_values = _bootstrap_replicates(
        scores, outcomes, applicable, BOOTSTRAP_SAMPLES, rng
    )

    ranked = _rank_outcomes(scores, outcomes)
    results: List[LiftAtK] = []
    per_budget_confidence = _adjusted_confidence(len(applicable))

    for k in applicable:
        precision_point = _precision_at_k(ranked, k)
        precision_low, precision_high = _percentile_bounds(
            precision_by_k[k], per_budget_confidence
        )
        lift_low, lift_high = _percentile_bounds(lift_by_k[k], per_budget_confidence)

        results.append(
            LiftAtK(
                k=k,
                precision=Interval(precision_point, precision_low, precision_high),
                lift=Interval(
                    precision_point / base_rate if base_rate else float("nan"),
                    lift_low,
                    lift_high,
                ),
            )
        )

    auc_point = _auc(scores, outcomes)
    auc = None
    if auc_point is not None:
        auc_low, auc_high = _percentile_bounds(auc_values)
        auc = Interval(auc_point, auc_low, auc_high)

    verdict, reasoning = _judge(size, positives, base_rate, results, auc)

    return FeasibilityReport(
        cohort_size=size,
        positives=positives,
        base_rate=base_rate,
        horizon_days=horizon_days,
        lift_at_k=results,
        auc=auc,
        verdict=verdict,
        reasoning=reasoning,
    )


def _judge(
    size: int,
    positives: int,
    base_rate: float,
    results: Sequence[LiftAtK],
    auc: Optional[Interval],
) -> Tuple[str, str]:
    """
    Turn the measurements into a decision, refusing to call an underpowered one.

    Reporting "no signal" from 40 parcels would be as misleading as reporting
    signal from three lucky events, so cohort size is checked before lift.

    Signal requires two things to agree. AUC is the omnibus test: it uses every
    parcel and is a single comparison, so it cannot be reached by chance the way
    a lucky action budget can. Lift@k is then the effect size that matters to the
    business. Requiring only the second is how noise gets called a result -
    a scorer with AUC 0.51 can still show lift at one of four budgets.
    """
    if size < MIN_COHORT_SIZE:
        return (
            "insufficient data",
            f"{size} parcels is below the {MIN_COHORT_SIZE} needed to tell signal "
            "from noise. Widen the cohort - more event types, or more years.",
        )

    if positives < MIN_POSITIVES:
        return (
            "insufficient data",
            f"only {positives} parcels transacted (base rate {base_rate:.1%}); "
            f"{MIN_POSITIVES} is the minimum for a usable interval. Lengthen the "
            "horizon or widen the cohort.",
        )

    ranks_better_than_chance = auc is not None and auc.low > 0.5
    convincing = [result for result in results if result.beats_chance]

    if ranks_better_than_chance and convincing:
        best = max(convincing, key=lambda result: result.lift.point)
        return (
            "signal",
            f"AUC {auc.point:.3f} with the interval above 0.5 "
            f"({auc.low:.3f}-{auc.high:.3f}), and at k={best.k} the scorer reaches "
            f"{best.precision.point:.1%} against a {base_rate:.1%} base rate - lift "
            f"{best.lift.point:.2f}x ({best.lift.low:.2f}-{best.lift.high:.2f}). "
            "Worth building the labelling pipeline.",
        )

    if convincing and not ranks_better_than_chance:
        best = max(convincing, key=lambda result: result.lift.point)
        return (
            "no signal",
            f"k={best.k} shows lift {best.lift.point:.2f}x, but overall ranking is "
            f"indistinguishable from random (AUC {auc.point:.3f}, interval "
            f"{auc.low:.3f}-{auc.high:.3f} spans 0.5). One budget out of "
            f"{len(results)} clearing the bar is what noise looks like, not a result.",
        )

    return (
        "no signal",
        f"no action budget beats the {base_rate:.1%} base rate once uncertainty is "
        "accounted for. The ranking is not currently worth more than picking at "
        "random, so better features or better data coverage matter more than a "
        "better model.",
    )
