"""
Coordinate Transformation Utilities

Utilities for converting between coordinate systems, primarily
Florida State Plane to WGS84 lat/lon.
"""
from typing import Tuple
import pandas as pd
from pyproj import Transformer

from config.settings import settings
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class CoordinateTransformer:
    """
    Transforms coordinates between different coordinate reference systems.

    Primarily used for converting Florida State Plane (EPSG:2881)
    to WGS84 lat/lon (EPSG:4326).
    """

    def __init__(
        self,
        source_epsg: int = None,
        target_epsg: int = None
    ):
        """
        Initialize coordinate transformer.

        Args:
            source_epsg: Source EPSG code (default: settings.florida_state_plane_epsg)
            target_epsg: Target EPSG code (default: settings.wgs84_epsg)
        """
        self.source_epsg = source_epsg or settings.florida_state_plane_epsg
        self.target_epsg = target_epsg or settings.wgs84_epsg

        self.transformer = Transformer.from_crs(
            f"EPSG:{self.source_epsg}",
            f"EPSG:{self.target_epsg}",
            always_xy=True
        )

        logger.info(
            "coordinate_transformer_initialized",
            source_epsg=self.source_epsg,
            target_epsg=self.target_epsg
        )

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        """
        Transform a single coordinate point.

        Args:
            x: X coordinate (easting for State Plane, longitude for WGS84)
            y: Y coordinate (northing for State Plane, latitude for WGS84)

        Returns:
            Tuple of (longitude, latitude) in WGS84
        """
        lon, lat = self.transformer.transform(x, y)
        return lon, lat

    def transform_dataframe(
        self,
        df: pd.DataFrame,
        x_col: str = 'gpsx',
        y_col: str = 'gpsy'
    ) -> pd.DataFrame:
        """
        Transform coordinates in a pandas DataFrame.

        Args:
            df: DataFrame with coordinate columns
            x_col: Name of X coordinate column
            y_col: Name of Y coordinate column

        Returns:
            DataFrame with added 'longitude' and 'latitude' columns
        """
        logger.info(
            "transforming_dataframe_coordinates",
            rows=len(df),
            x_col=x_col,
            y_col=y_col
        )

        lon, lat = self.transformer.transform(
            df[x_col].values,
            df[y_col].values
        )

        df_copy = df.copy()
        df_copy['longitude'] = lon
        df_copy['latitude'] = lat

        logger.info(
            "coordinate_transformation_complete",
            rows_transformed=len(df_copy)
        )

        return df_copy

    @staticmethod
    def detect_coordinate_system(df: pd.DataFrame, y_col: str = 'gpsy') -> str:
        """
        Detect if coordinates are in State Plane or lat/lon format.

        State Plane coordinates are large (typically > 100).
        Lat/lon coordinates are small (typically 28-29 for Orlando).

        Args:
            df: DataFrame with coordinates
            y_col: Name of Y coordinate column

        Returns:
            'state_plane' or 'latlon'
        """
        if len(df) == 0:
            logger.warning("empty_dataframe_for_detection")
            return 'latlon'

        avg_y = abs(df[y_col].mean())

        if avg_y > 100:
            logger.info(
                "detected_state_plane_coordinates",
                avg_y=round(avg_y, 2)
            )
            return 'state_plane'
        else:
            logger.info(
                "detected_latlon_coordinates",
                avg_y=round(avg_y, 2)
            )
            return 'latlon'

    @staticmethod
    def validate_orlando_coordinates(
        df: pd.DataFrame,
        lat_col: str = 'latitude',
        lon_col: str = 'longitude'
    ) -> pd.DataFrame:
        """
        Filter DataFrame to valid Orlando area coordinates.

        Args:
            df: DataFrame with lat/lon columns
            lat_col: Name of latitude column
            lon_col: Name of longitude column

        Returns:
            Filtered DataFrame with only valid coordinates
        """
        original_count = len(df)

        valid_mask = (
            (df[lat_col].between(28, 29)) &
            (df[lon_col].between(-82, -81))
        )

        df_filtered = df[valid_mask].copy()
        invalid_count = original_count - len(df_filtered)

        if invalid_count > 0:
            logger.warning(
                "invalid_coordinates_filtered",
                invalid_count=invalid_count,
                valid_count=len(df_filtered),
                percentage_valid=round(len(df_filtered) / original_count * 100, 2)
            )

        return df_filtered
