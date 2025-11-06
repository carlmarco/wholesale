"""
Geographic Property Enrichment

Uses geospatial proximity matching to enrich tax sale properties
with nearby code enforcement violations.

Migrated version with structured logging, configuration management,
and Pydantic models.
"""
import pandas as pd
from typing import List, Optional

from config.settings import settings
from src.wholesaler.utils.logger import get_logger
from src.wholesaler.models.property import TaxSaleProperty, EnrichedProperty, ProximityMetrics
from src.wholesaler.transformers.coordinate_transformer import CoordinateTransformer
from src.wholesaler.utils.geo_utils import haversine_distance, miles_to_feet

logger = get_logger(__name__)


class GeoPropertyEnricher:
    """
    Enriches tax sale properties using geographic proximity to code violations.

    When parcel ID systems are incompatible between datasets, this class
    uses the Haversine formula to find code enforcement violations within
    a specified radius of each tax sale property.
    """

    def __init__(
        self,
        code_enforcement_csv_path: Optional[str] = None,
        radius_miles: Optional[float] = None
    ):
        """
        Initialize enricher with code enforcement data.

        Args:
            code_enforcement_csv_path: Path to code enforcement CSV
            radius_miles: Search radius in miles (default from settings)
        """
        csv_path = code_enforcement_csv_path or settings.code_enforcement_csv
        self.radius_miles = radius_miles or settings.search_radius_miles

        logger.info(
            "loading_code_enforcement_data",
            csv_path=csv_path,
            radius_miles=self.radius_miles
        )

        self.violations_df = pd.read_csv(csv_path, low_memory=False)

        self.violations_df = self._filter_valid_coordinates()

        self.violations_df = self._transform_coordinates()

        logger.info(
            "geo_enricher_initialized",
            violations_loaded=len(self.violations_df),
            radius_miles=self.radius_miles,
            radius_feet=miles_to_feet(self.radius_miles)
        )

    def _filter_valid_coordinates(self) -> pd.DataFrame:
        """
        Filter dataframe to records with non-zero coordinates.

        Returns:
            Filtered DataFrame
        """
        original_count = len(self.violations_df)

        filtered_df = self.violations_df[
            (self.violations_df['gpsx'] != 0) &
            (self.violations_df['gpsy'] != 0) &
            (self.violations_df['gpsx'].notna()) &
            (self.violations_df['gpsy'].notna())
        ].copy()

        filtered_count = original_count - len(filtered_df)

        logger.info(
            "coordinates_filtered",
            original_count=original_count,
            filtered_out=filtered_count,
            remaining=len(filtered_df)
        )

        return filtered_df

    def _transform_coordinates(self) -> pd.DataFrame:
        """
        Detect coordinate system and transform if needed.

        Returns:
            DataFrame with 'latitude' and 'longitude' columns
        """
        if len(self.violations_df) == 0:
            logger.warning("empty_dataframe_no_transformation")
            return self.violations_df

        coord_system = CoordinateTransformer.detect_coordinate_system(
            self.violations_df,
            y_col='gpsy'
        )

        if coord_system == 'state_plane':
            transformer = CoordinateTransformer()
            self.violations_df = transformer.transform_dataframe(
                self.violations_df,
                x_col='gpsx',
                y_col='gpsy'
            )

            self.violations_df = CoordinateTransformer.validate_orlando_coordinates(
                self.violations_df
            )
        else:
            logger.info("coordinates_already_latlon_no_transformation_needed")
            self.violations_df['latitude'] = self.violations_df['gpsy']
            self.violations_df['longitude'] = self.violations_df['gpsx']

        return self.violations_df

    def enrich_properties(
        self,
        properties: List[TaxSaleProperty]
    ) -> List[EnrichedProperty]:
        """
        Enrich tax sale properties with nearby violation data.

        Args:
            properties: List of TaxSaleProperty instances

        Returns:
            List of EnrichedProperty instances with proximity metrics
        """
        logger.info(
            "starting_property_enrichment",
            property_count=len(properties),
            radius_miles=self.radius_miles
        )

        enriched = []

        for idx, prop in enumerate(properties):
            if not prop.has_coordinates():
                logger.debug(
                    "property_missing_coordinates",
                    tda_number=prop.tda_number,
                    index=idx
                )

                enriched_prop = EnrichedProperty(
                    **prop.to_dict(),
                    nearby_violations=0,
                    nearby_open_violations=0,
                    nearest_violation_distance=None,
                    avg_violation_distance=None,
                    violation_types_nearby=[]
                )
                enriched.append(enriched_prop)
                continue

            nearby_violations = self._find_nearby_violations(
                prop.latitude,
                prop.longitude
            )

            metrics = self._calculate_proximity_metrics(nearby_violations)

            enriched_prop = EnrichedProperty(
                **prop.to_dict(),
                **metrics.model_dump()
            )

            enriched.append(enriched_prop)

            if idx > 0 and idx % 10 == 0:
                logger.debug(
                    "enrichment_progress",
                    processed=idx + 1,
                    total=len(properties)
                )

        logger.info(
            "enrichment_complete",
            total_properties=len(enriched),
            with_violations=sum(1 for p in enriched if p.nearby_violations > 0)
        )

        return enriched

    def _find_nearby_violations(
        self,
        prop_lat: float,
        prop_lon: float
    ) -> List[dict]:
        """
        Find violations within radius of a property.

        Args:
            prop_lat: Property latitude
            prop_lon: Property longitude

        Returns:
            List of nearby violation dictionaries with distance info
        """
        nearby = []

        for _, violation in self.violations_df.iterrows():
            v_lat = violation.get('latitude')
            v_lon = violation.get('longitude')

            if pd.isna(v_lat) or pd.isna(v_lon):
                continue

            distance = haversine_distance(prop_lat, prop_lon, v_lat, v_lon)

            if distance <= self.radius_miles:
                nearby.append({
                    'distance': distance,
                    'status': violation.get('caseinfostatus'),
                    'type': violation.get('case_type'),
                    'date': violation.get('casedt')
                })

        return nearby

    def _calculate_proximity_metrics(
        self,
        nearby_violations: List[dict]
    ) -> ProximityMetrics:
        """
        Calculate metrics for nearby violations.

        Args:
            nearby_violations: List of violation dictionaries with distance

        Returns:
            ProximityMetrics instance
        """
        if not nearby_violations:
            return ProximityMetrics()

        open_count = sum(1 for v in nearby_violations if v['status'] == 'Open')
        violation_types = list(set(
            v['type'] for v in nearby_violations if v['type']
        ))[:5]

        distances = [v['distance'] for v in nearby_violations]
        nearest_distance = round(min(distances), 3)
        avg_distance = round(sum(distances) / len(distances), 3)

        return ProximityMetrics(
            nearby_violations=len(nearby_violations),
            nearby_open_violations=open_count,
            nearest_violation_distance=nearest_distance,
            avg_violation_distance=avg_distance,
            violation_types_nearby=violation_types
        )

    def display_enriched_property(
        self,
        prop: EnrichedProperty,
        index: int = 1
    ):
        """
        Display a single enriched property with violation details.

        Args:
            prop: EnrichedProperty instance
            index: Property index for display
        """
        opportunity_flag = " [DISTRESSED AREA]" if prop.nearby_violations >= 5 else ""
        print(f"\n[Property {index}]{opportunity_flag}")

        print(f"  TDA Number:         {prop.tda_number}")
        print(f"  Sale Date:          {prop.sale_date}")
        print(f"  Deed Status:        {prop.deed_status}")
        print(f"  Parcel ID:          {prop.parcel_id}")

        if prop.has_coordinates():
            print(f"  Coordinates:        ({prop.latitude:.6f}, {prop.longitude:.6f})")

        print(f"\n  NEARBY VIOLATIONS (within {self.radius_miles} miles):")
        print(f"    Total Nearby:        {prop.nearby_violations}")
        print(f"    Open Nearby:         {prop.nearby_open_violations}")

        if prop.nearest_violation_distance:
            print(f"    Nearest Violation:   {prop.nearest_violation_distance} miles ({miles_to_feet(prop.nearest_violation_distance)} feet)")
            print(f"    Avg Distance:        {prop.avg_violation_distance} miles")

        types_display = ', '.join(prop.violation_types_nearby) if prop.violation_types_nearby else 'N/A'
        print(f"    Violation Types:     {types_display}")

        if prop.nearby_violations > 0:
            print(f"\n  AREA ANALYSIS:")
            if prop.nearby_violations >= 10:
                print(f"    - High violation density ({prop.nearby_violations} within radius)")
                print(f"    - May indicate neighborhood decline")
            elif prop.nearby_violations >= 5:
                print(f"    - Moderate violation density")
                print(f"    - Mixed neighborhood condition")
            if prop.nearby_open_violations > 0:
                print(f"    - {prop.nearby_open_violations} unresolved violations nearby")
                print(f"    - Consider neighborhood risk in valuation")

    def display_summary_stats(self, enriched_properties: List[EnrichedProperty]):
        """
        Display summary statistics for enriched dataset.

        Args:
            enriched_properties: List of EnrichedProperty instances
        """
        total = len(enriched_properties)
        with_nearby = sum(1 for p in enriched_properties if p.nearby_violations > 0)
        total_violations = sum(p.nearby_violations for p in enriched_properties)
        total_open = sum(p.nearby_open_violations for p in enriched_properties)

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
