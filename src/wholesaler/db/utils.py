"""
Database Utilities

Helper functions for database operations, queries, and data transformations.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, date

from geoalchemy2.functions import ST_MakePoint, ST_DWithin, ST_Distance
from geoalchemy2.elements import WKTElement
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def create_geography_point(longitude: float, latitude: float) -> WKTElement:
    """
    Create PostGIS GEOGRAPHY point from lat/lon.

    Args:
        longitude: Longitude in WGS84
        latitude: Latitude in WGS84

    Returns:
        WKTElement for database insertion
    """
    return WKTElement(f'POINT({longitude} {latitude})', srid=4326)


def meters_to_miles(meters: float) -> float:
    """
    Convert meters to miles.

    Args:
        meters: Distance in meters

    Returns:
        Distance in miles
    """
    return meters / 1609.34


def miles_to_meters(miles: float) -> float:
    """
    Convert miles to meters.

    Args:
        miles: Distance in miles

    Returns:
        Distance in meters
    """
    return miles * 1609.34


def parse_date_string(date_str: Optional[str]) -> Optional[date]:
    """
    Parse date string in various formats.

    Args:
        date_str: Date string (YYYY-MM-DD, MM/DD/YYYY, etc.)

    Returns:
        date object or None
    """
    if not date_str:
        return None

    # Try common date formats
    formats = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%Y/%m/%d',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    logger.warning("date_parse_failed", date_str=date_str)
    return None


def sanitize_dict_for_jsonb(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize dictionary for JSONB storage.

    Converts datetime objects to strings, removes None values, etc.

    Args:
        data: Dictionary to sanitize

    Returns:
        Sanitized dictionary
    """
    sanitized = {}

    for key, value in data.items():
        if value is None:
            continue

        if isinstance(value, (datetime, date)):
            sanitized[key] = value.isoformat()
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict_for_jsonb(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict_for_jsonb(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def build_upsert_values(
    data: Dict[str, Any],
    exclude_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Build values dict for upsert on_conflict_do_update.

    Args:
        data: Source data dictionary
        exclude_keys: Keys to exclude from update

    Returns:
        Values dict for SQLAlchemy upsert
    """
    if exclude_keys is None:
        exclude_keys = ['id', 'created_at']

    return {
        k: v for k, v in data.items()
        if k not in exclude_keys
    }


def calculate_bounding_box(
    center_lat: float,
    center_lon: float,
    radius_miles: float
) -> Dict[str, float]:
    """
    Calculate bounding box for spatial queries.

    Args:
        center_lat: Center latitude
        center_lon: Center longitude
        radius_miles: Radius in miles

    Returns:
        Dict with min_lat, max_lat, min_lon, max_lon
    """
    # Approximate degrees per mile at this latitude
    lat_degree_miles = 69.0
    lon_degree_miles = 69.0 * abs(center_lat / 90.0)

    lat_offset = radius_miles / lat_degree_miles
    lon_offset = radius_miles / lon_degree_miles

    return {
        'min_lat': center_lat - lat_offset,
        'max_lat': center_lat + lat_offset,
        'min_lon': center_lon - lon_offset,
        'max_lon': center_lon + lon_offset,
    }


def execute_raw_sql(
    session: Session,
    sql: str,
    params: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Execute raw SQL query safely.

    Args:
        session: Database session
        sql: SQL query string
        params: Query parameters

    Returns:
        Query result
    """
    logger.debug("executing_raw_sql", sql=sql[:100])

    try:
        result = session.execute(text(sql), params or {})
        return result
    except Exception as e:
        logger.error("raw_sql_failed", sql=sql[:100], error=str(e))
        raise


def get_table_row_count(session: Session, table_name: str) -> int:
    """
    Get row count for a table.

    Args:
        session: Database session
        table_name: Table name

    Returns:
        Row count
    """
    sql = f"SELECT COUNT(*) FROM {table_name}"
    result = execute_raw_sql(session, sql)
    count = result.scalar()
    logger.debug("table_row_count", table=table_name, count=count)
    return count


def truncate_table(session: Session, table_name: str, cascade: bool = False):
    """
    Truncate table (delete all rows).

    WARNING: This is destructive!

    Args:
        session: Database session
        table_name: Table name
        cascade: Whether to cascade to dependent tables
    """
    cascade_clause = " CASCADE" if cascade else ""
    sql = f"TRUNCATE TABLE {table_name}{cascade_clause}"

    logger.warning("truncating_table", table=table_name, cascade=cascade)
    execute_raw_sql(session, sql)
    logger.warning("table_truncated", table=table_name)


def vacuum_analyze_table(session: Session, table_name: str):
    """
    Run VACUUM ANALYZE on table to optimize performance.

    Args:
        session: Database session
        table_name: Table name
    """
    sql = f"VACUUM ANALYZE {table_name}"
    logger.info("vacuum_analyze_starting", table=table_name)

    # Note: VACUUM cannot run inside a transaction block
    # This should be run outside of a transaction
    execute_raw_sql(session, sql)
    logger.info("vacuum_analyze_completed", table=table_name)


def get_database_stats(session: Session) -> Dict[str, Any]:
    """
    Get database statistics.

    Args:
        session: Database session

    Returns:
        Dict with database stats
    """
    tables = [
        'properties',
        'tax_sales',
        'foreclosures',
        'property_records',
        'code_violations',
        'lead_scores',
        'lead_score_history',
        'data_ingestion_runs',
    ]

    stats = {}
    for table in tables:
        try:
            stats[table] = get_table_row_count(session, table)
        except Exception as e:
            logger.error("table_stats_failed", table=table, error=str(e))
            stats[table] = -1

    logger.info("database_stats_retrieved", stats=stats)
    return stats


def check_postgis_installed(session: Session) -> bool:
    """
    Check if PostGIS extension is installed.

    Args:
        session: Database session

    Returns:
        True if PostGIS is installed
    """
    sql = "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')"
    result = execute_raw_sql(session, sql)
    installed = result.scalar()
    logger.info("postgis_check", installed=installed)
    return installed


def get_postgis_version(session: Session) -> Optional[str]:
    """
    Get PostGIS version.

    Args:
        session: Database session

    Returns:
        PostGIS version string or None
    """
    try:
        sql = "SELECT PostGIS_Version()"
        result = execute_raw_sql(session, sql)
        version = result.scalar()
        logger.info("postgis_version", version=version)
        return version
    except Exception as e:
        logger.error("postgis_version_failed", error=str(e))
        return None
