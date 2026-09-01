"""
Tests for shared date coercion.

The previous implementation sliced input by ``len(fmt)`` before parsing, so
"2024-03-15" was truncated to "2024-03-" and every plain date silently became
None. These cases pin the formats the ingestion sources actually publish.
"""
from datetime import date, datetime

import pytest

from src.wholesaler.utils.dates import coerce_date


@pytest.mark.parametrize(
    "value",
    [
        "2024-03-15",
        "03/15/2024",
        "2024-03-15T10:30:00",
        "2024-03-15T10:30:00.123456",
        "2024-03-15 10:30:00",
        "  2024-03-15  ",
        date(2024, 3, 15),
        datetime(2024, 3, 15, 10, 30),
    ],
)
def test_parses_supported_formats(value):
    assert coerce_date(value) == date(2024, 3, 15)


@pytest.mark.parametrize("value", [None, "", "   ", "null", "garbage", "13/45/2024", 42, []])
def test_returns_none_for_unparseable(value):
    assert coerce_date(value) is None


def test_distinguishes_day_and_month():
    """US-format input must not be read as ISO, or 03/15 becomes 15 March."""
    assert coerce_date("01/02/2024") == date(2024, 1, 2)
    assert coerce_date("2024-01-02") == date(2024, 1, 2)
