"""
Tier banding.

Tiers are just labelled score thresholds. Keeping them as data rather than a
chain of comparisons means a profile can retune them, and a gate can select a
different set of bands, without touching the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass(frozen=True)
class TierBands:
    """
    Ordered score thresholds mapping a score to a label.

    Attributes:
        bands: (label, minimum_score) pairs in descending threshold order. The
            first band whose minimum the score meets wins, so thresholds are
            inclusive. May be empty, meaning every score gets the fallback.
        fallback: Label for a score below every threshold.

    Raises:
        ValueError: If the bands are not in descending order or repeat a label,
            either of which would silently make a band unreachable.
    """
    bands: Tuple[Tuple[str, float], ...]
    fallback: str

    def __post_init__(self) -> None:
        thresholds = [threshold for _, threshold in self.bands]
        if thresholds != sorted(thresholds, reverse=True):
            raise ValueError(
                "TierBands must be ordered by descending threshold, or lower "
                f"bands become unreachable; got {thresholds}"
            )

        labels = [label for label, _ in self.bands] + [self.fallback]
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise ValueError(f"TierBands labels must be unique; repeated: {duplicates}")

    def band(self, score: float) -> str:
        """Return the label for a score."""
        for label, threshold in self.bands:
            if score >= threshold:
                return label
        return self.fallback

    @property
    def labels(self) -> Sequence[str]:
        """Every label this banding can produce, best first."""
        return [label for label, _ in self.bands] + [self.fallback]

    def capped_at(self, label: str) -> "TierBands":
        """
        The same banding with every tier above ``label`` removed.

        Expresses "a lead failing the viability gate cannot reach the top tiers"
        without restating the thresholds. Capping at the fallback label leaves
        no bands at all, so everything lands there.

        Raises:
            ValueError: If the label is not one this banding produces.
        """
        if label == self.fallback:
            return TierBands(bands=(), fallback=self.fallback)

        for index, (name, _) in enumerate(self.bands):
            if name == label:
                return TierBands(bands=self.bands[index:], fallback=self.fallback)

        raise ValueError(f"{label!r} is not one of {list(self.labels)}")
