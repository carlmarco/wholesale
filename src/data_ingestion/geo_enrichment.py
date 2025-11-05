"""
Geographic Property Enrichment Module

Uses geospatial proximity matching to enrich tax sale properties
with nearby code enforcement violations when parcel IDs don't match.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from math import radians, cos, sin, asin, sqrt
from pyproj import Transformer


class GeoPropertyEnricher:
    """
    Enriches tax sale properties using geographic proximity to code violations.

    When parcel ID systems are incompatible between datasets, this class
    uses the Haversine formula to find code enforcement violations within
    a specified radius of each tax sale property.
    """

    def __init__(self, code_enforcement_csv_path: str, radius_miles: float = 0.1):
        """
        Initialize enricher with code enforcement data.

        Args:
            code_enforcement_csv_path: Path to code enforcement CSV file
            radius_miles: Search radius in miles (default 0.1 = ~528 feet)
        """
        print(f"Loading code enforcement data from {code_enforcement_csv_path}...")
        self.violations_df = pd.read_csv(
            code_enforcement_csv_path,
            low_memory=False
        )

        # Filter to records with non-zero coordinates
        # Fixed bug: was filtering gpsx > 0, which excluded negative longitudes
        self.violations_df = self.violations_df[
            (self.violations_df['gpsx'] != 0) &
            (self.violations_df['gpsy'] != 0) &
            (self.violations_df['gpsx'].notna()) &
            (self.violations_df['gpsy'].notna())
        ].copy()

        print(f"Loaded {len(self.violations_df):,} violation records with coordinates")

        # Determine coordinate system and convert if needed
        # State Plane coordinates are large (500,000+)
        # Lat/lon coordinates are small (28-29 lat, -81 to -82 lon)
        if len(self.violations_df) > 0:
            avg_y = abs(self.violations_df['gpsy'].mean())
            if avg_y > 100:
                print(f"Detected State Plane coordinates (avg_y={avg_y:.0f})")
                print("Converting Florida State Plane (East Zone, EPSG:2881) to WGS84...")
                self._convert_coordinates()
            else:
                print(f"Detected lat/lon coordinates (avg_y={avg_y:.2f})")
                # Already in lat/lon format (gpsy=lat, gpsx=lon)
                self.violations_df['latitude'] = self.violations_df['gpsy']
                self.violations_df['longitude'] = self.violations_df['gpsx']

        self.radius_miles = radius_miles
        print(f"Using search radius: {radius_miles} miles (~{int(radius_miles*5280)} feet)")

    def _convert_coordinates(self):
        """
        Convert Florida State Plane coordinates to WGS84 lat/lon.

        Uses pyproj to transform from EPSG:2881 (Florida East State Plane, US Survey Feet)
        to EPSG:4326 (WGS84 latitude/longitude).
        """
        # Create transformer from Florida State Plane East to WGS84
        # EPSG:2881 = NAD83 / Florida East (ftUS)
        # EPSG:4326 = WGS 84 (latitude, longitude)
        transformer = Transformer.from_crs(
            "EPSG:2881",  # Florida State Plane East Zone (US Survey Feet)
            "EPSG:4326",  # WGS84 lat/lon
            always_xy=True  # Ensure (x, y) order, not (lat, lon)
        )

        # Transform coordinates
        # Note: gpsx = easting (x), gpsy = northing (y) in State Plane
        lon, lat = transformer.transform(
            self.violations_df['gpsx'].values,
            self.violations_df['gpsy'].values
        )

        self.violations_df['longitude'] = lon
        self.violations_df['latitude'] = lat

        # Filter out any invalid conversions
        valid_mask = (
            (self.violations_df['latitude'].between(28, 29)) &
            (self.violations_df['longitude'].between(-82, -81))
        )

        invalid_count = (~valid_mask).sum()
        if invalid_count > 0:
            print(f"Warning: {invalid_count} coordinates outside Orlando area (likely conversion errors)")
            self.violations_df = self.violations_df[valid_mask].copy()

        print(f"Successfully converted {len(self.violations_df):,} coordinates to WGS84")

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points on Earth using Haversine formula.

        Args:
            lat1, lon1: Coordinates of first point (decimal degrees)
            lat2, lon2: Coordinates of second point (decimal degrees)

        Returns:
            Distance in miles
        """
        # Convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))

        # Radius of Earth in miles
        r = 3956

        return c * r

    def enrich_properties(self, properties: List[Dict]) -> List[Dict]:
        """
        Enrich tax sale properties with nearby violation data.

        Args:
            properties: List of tax sale property dictionaries

        Returns:
            List of enriched property dictionaries with nearby violation metrics
        """
        enriched = []

        for prop in properties:
            prop_lat = prop.get('latitude')
            prop_lon = prop.get('longitude')

            if not prop_lat or not prop_lon:
                # No coordinates, can't enrich
                enriched_prop = {
                    **prop,
                    'nearby_violations': 0,
                    'nearby_open_violations': 0,
                    'nearest_violation_distance': None,
                    'violation_types_nearby': []
                }
                enriched.append(enriched_prop)
                continue

            # Find violations within radius
            nearby_violations = []
            for _, violation in self.violations_df.iterrows():
                v_lat = violation.get('latitude')
                v_lon = violation.get('longitude')

                if pd.isna(v_lat) or pd.isna(v_lon):
                    continue

                distance = self.haversine_distance(prop_lat, prop_lon, v_lat, v_lon)

                if distance <= self.radius_miles:
                    nearby_violations.append({
                        'distance': distance,
                        'status': violation.get('caseinfostatus'),
                        'type': violation.get('case_type'),
                        'date': violation.get('casedt')
                    })

            # Calculate metrics
            enrichment_data = self._calculate_proximity_metrics(nearby_violations)

            # Merge with original property data
            enriched_prop = {
                **prop,
                **enrichment_data
            }

            enriched.append(enriched_prop)

        return enriched

    def _calculate_proximity_metrics(self, nearby_violations: List[Dict]) -> Dict:
        """
        Calculate metrics for nearby violations.

        Args:
            nearby_violations: List of violation dictionaries with distance

        Returns:
            Dictionary of proximity-based metrics
        """
        if not nearby_violations:
            return {
                'nearby_violations': 0,
                'nearby_open_violations': 0,
                'nearest_violation_distance': None,
                'violation_types_nearby': [],
                'avg_violation_distance': None
            }

        open_count = sum(1 for v in nearby_violations if v['status'] == 'Open')
        violation_types = list(set(v['type'] for v in nearby_violations if v['type']))

        distances = [v['distance'] for v in nearby_violations]
        nearest_distance = min(distances)
        avg_distance = sum(distances) / len(distances)

        return {
            'nearby_violations': len(nearby_violations),
            'nearby_open_violations': open_count,
            'nearest_violation_distance': round(nearest_distance, 3),
            'violation_types_nearby': violation_types[:5],  # Limit to 5 types
            'avg_violation_distance': round(avg_distance, 3)
        }

    def display_enriched_property(self, prop: Dict, index: int = 1):
        """
        Display a single enriched property with proximity violation details.

        Args:
            prop: Enriched property dictionary
            index: Property index number for display
        """
        # Header
        opportunity_flag = " [DISTRESSED AREA]" if prop['nearby_violations'] >= 5 else ""
        print(f"\n[Property {index}]{opportunity_flag}")

        # Basic property info
        print(f"  TDA Number:         {prop['tda_number']}")
        print(f"  Sale Date:          {prop['sale_date']}")
        print(f"  Deed Status:        {prop['deed_status']}")
        print(f"  Parcel ID:          {prop['parcel_id']}")
        print(f"  Coordinates:        ({prop['latitude']:.6f}, {prop['longitude']:.6f})")

        # Proximity violation metrics
        print(f"\n  NEARBY VIOLATIONS (within {self.radius_miles} miles):")
        print(f"    Total Nearby:        {prop['nearby_violations']}")
        print(f"    Open Nearby:         {prop['nearby_open_violations']}")

        nearest = prop['nearest_violation_distance']
        if nearest:
            print(f"    Nearest Violation:   {nearest} miles ({int(nearest*5280)} feet)")
            print(f"    Avg Distance:        {prop['avg_violation_distance']} miles")

        types_display = ', '.join(prop['violation_types_nearby']) if prop['violation_types_nearby'] else 'N/A'
        print(f"    Violation Types:     {types_display}")

        # Investment insights
        if prop['nearby_violations'] > 0:
            print(f"\n  AREA ANALYSIS:")
            if prop['nearby_violations'] >= 10:
                print(f"    - High violation density ({prop['nearby_violations']} within radius)")
                print(f"    - May indicate neighborhood decline")
            elif prop['nearby_violations'] >= 5:
                print(f"    - Moderate violation density")
                print(f"    - Mixed neighborhood condition")
            if prop['nearby_open_violations'] > 0:
                print(f"    - {prop['nearby_open_violations']} unresolved violations nearby")
                print(f"    - Consider neighborhood risk in valuation")

    def display_summary_stats(self, enriched_properties: List[Dict]):
        """
        Display summary statistics for enriched dataset.

        Args:
            enriched_properties: List of enriched property dictionaries
        """
        total = len(enriched_properties)
        with_nearby = sum(1 for p in enriched_properties if p['nearby_violations'] > 0)
        total_violations = sum(p['nearby_violations'] for p in enriched_properties)
        total_open = sum(p['nearby_open_violations'] for p in enriched_properties)

        print(f"\n{'='*80}")
        print(f"GEOGRAPHIC ENRICHMENT SUMMARY")
        print(f"{'='*80}")
        print(f"  Total Properties:              {total}")
        print(f"  Properties with Nearby Issues: {with_nearby} ({with_nearby/total*100:.1f}%)")
        print(f"  Total Nearby Violations:       {total_violations}")
        print(f"  Total Open Nearby:             {total_open}")
        if total > 0:
            print(f"  Avg Nearby per Property:       {total_violations/total:.1f}")
        print(f"  Search Radius:                 {self.radius_miles} miles")
        print(f"{'='*80}\n")
