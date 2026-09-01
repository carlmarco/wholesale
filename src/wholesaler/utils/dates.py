"""
Date Parsing Utilities

Shared date coercion for ingestion. Sources publish dates in several formats -
the tax sale feed uses MM/DD/YYYY, seed exports use ISO dates, and some records
carry full ISO timestamps - so values are parsed here rather than handed to a
DATE column, where interpretation would depend on the server's DateStyle.
"""
from datetime import date, datetime
from typing import Any, Optional

# Ordered most specific first: a full timestamp must be tried before the plain
# date formats, which would otherwise match its leading characters.
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
)


def coerce_date(value: Any) -> Optional[date]:
    """
    Parse a source date value into a :class:`datetime.date`.

    Args:
        value: A date, datetime, or string from a source record.

    Returns:
        The parsed date, or None when the value is missing or unparseable.
    """
    if value is None or value == "" or value == "null":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # Covers ISO spellings strptime does not, such as trailing timezone offsets.
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None
