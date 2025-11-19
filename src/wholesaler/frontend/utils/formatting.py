"""
Formatting Utilities for Streamlit Frontend

Helper functions for formatting data display.
"""
from typing import Optional
from datetime import datetime, date


def format_currency(amount: Optional[float]) -> str:
    """
    Format number as US currency.

    Args:
        amount: Dollar amount

    Returns:
        Formatted currency string (e.g., "$1,234.56")
    """
    if amount is None:
        return "N/A"
    return f"${amount:,.2f}"


def format_score(score: float) -> str:
    """
    Format score with 1 decimal place.

    Args:
        score: Score value

    Returns:
        Formatted score (e.g., "85.5")
    """
    return f"{score:.1f}"


def format_date(date_value: Optional[date]) -> str:
    """
    Format date as MM/DD/YYYY.

    Args:
        date_value: Date object

    Returns:
        Formatted date string
    """
    if date_value is None:
        return "N/A"
    if isinstance(date_value, str):
        try:
            date_value = datetime.fromisoformat(date_value.replace("Z", "+00:00")).date()
        except:
            return date_value
    return date_value.strftime("%m/%d/%Y")


def format_datetime(datetime_value: Optional[datetime]) -> str:
    """
    Format datetime as MM/DD/YYYY HH:MM AM/PM.

    Args:
        datetime_value: Datetime object

    Returns:
        Formatted datetime string
    """
    if datetime_value is None:
        return "N/A"
    if isinstance(datetime_value, str):
        try:
            datetime_value = datetime.fromisoformat(datetime_value.replace("Z", "+00:00"))
        except:
            return datetime_value
    return datetime_value.strftime("%m/%d/%Y %I:%M %p")


def format_address(address: Optional[str], city: Optional[str], state: Optional[str], zip_code: Optional[str]) -> str:
    """
    Format full address.

    Args:
        address: Street address
        city: City name
        state: State abbreviation
        zip_code: ZIP code

    Returns:
        Formatted address string
    """
    parts = []
    if address:
        parts.append(address)
    if city and state:
        parts.append(f"{city}, {state}")
    elif city:
        parts.append(city)
    elif state:
        parts.append(state)
    if zip_code:
        parts.append(zip_code)

    return " ".join(parts) if parts else "N/A"


def get_tier_color(tier: str) -> str:
    """
    Get color code for tier badge.

    Args:
        tier: Tier letter (A, B, C, D)

    Returns:
        Hex color code
    """
    colors = {
        "A": "#28a745",  # Green
        "B": "#17a2b8",  # Blue
        "C": "#ffc107",  # Yellow
        "D": "#6c757d",  # Gray
    }
    return colors.get(tier, "#6c757d")


def get_tier_label(tier: str) -> str:
    """
    Get display label for tier.

    Args:
        tier: Tier letter

    Returns:
        Formatted tier label
    """
    labels = {
        "A": "Tier A - Highest Priority",
        "B": "Tier B - High Priority",
        "C": "Tier C - Medium Priority",
        "D": "Tier D - Low Priority",
    }
    return labels.get(tier, f"Tier {tier}")


def format_percentage(value: Optional[float], total: Optional[float]) -> str:
    """
    Calculate and format percentage.

    Args:
        value: Numerator
        total: Denominator

    Returns:
        Formatted percentage (e.g., "25.0%")
    """
    if value is None or total is None or total == 0:
        return "0.0%"
    percentage = (value / total) * 100
    return f"{percentage:.1f}%"
