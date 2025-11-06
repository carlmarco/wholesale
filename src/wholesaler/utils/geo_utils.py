"""
Geographic Utility Functions

Helper functions for geographic calculations including distance measurements.
"""
from math import radians, cos, sin, asin, sqrt


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate great-circle distance between two points using Haversine formula.

    Args:
        lat1: Latitude of first point (decimal degrees)
        lon1: Longitude of first point (decimal degrees)
        lat2: Latitude of second point (decimal degrees)
        lon2: Longitude of second point (decimal degrees)

    Returns:
        Distance in miles

    Formula:
        a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlon/2)
        c = 2 × atan2(√a, √(1−a))
        distance = R × c  (R = Earth radius = 3,956 miles)
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    r = 3956

    return c * r


def miles_to_feet(miles: float) -> int:
    """Convert miles to feet."""
    return int(miles * 5280)


def feet_to_miles(feet: float) -> float:
    """Convert feet to miles."""
    return feet / 5280
