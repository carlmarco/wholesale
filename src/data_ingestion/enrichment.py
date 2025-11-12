"""
Property Enrichment Module
Cross-references tax sale properties with code enforcement violations
to identify high-value wholesale opportunities
"""
import pandas as pd
from typing import List, Dict, Optional, Union
from datetime import datetime

from src.wholesaler.transformers.address_standardizer import AddressStandardizer

class PropertyEnricher:
    """Enriches tax sale properties with code enforcement violation data"""

    def __init__(self, violations: Union[pd.DataFrame, List[Dict]]):
        """
        Initialize enricher with violation records.

        Args:
            violations: DataFrame or list of dicts representing violations
        """
        if violations is None:
            raise ValueError("Violation records are required")

        self.standardizer = AddressStandardizer()
        self.violations_df = self._prepare_violations_dataframe(violations)
        print(f"Loaded {len(self.violations_df):,} violation records")
        print(f"Records with parcel IDs: {self.violations_df['parcel_id'].notna().sum():,}")

    @classmethod
    def from_csv(cls, csv_path: str) -> "PropertyEnricher":
        """Convenience constructor for CSV inputs (tests/backfills)."""
        df = pd.read_csv(csv_path, low_memory=False, dtype={'parcel_id': str})
        return cls(df)

    def _prepare_violations_dataframe(
        self,
        violations: Union[pd.DataFrame, List[Dict]]
    ) -> pd.DataFrame:
        """Normalize incoming violation records into DataFrame form."""
        if isinstance(violations, pd.DataFrame):
            df = violations.copy()
        else:
            df = pd.DataFrame.from_records(violations or [])

        if 'parcel_id' not in df.columns:
            df['parcel_id'] = None

        df['parcel_id_normalized'] = (
            df['parcel_id']
            .apply(self.standardizer.normalize_parcel_id)
            .fillna('')
        )

        return df

    def enrich_properties(self, properties: List[Dict]) -> List[Dict]:
        """
        Enrich tax sale properties with violation data

        Args:
            properties: List of tax sale property dictionaries

        Returns:
            List of enriched property dictionaries with violation metrics
        """
        enriched = []

        for prop in properties:
            # Normalize tax sale parcel ID
            parcel_id = prop.get('parcel_id')
            parcel_normalized = self.standardizer.normalize_parcel_id(parcel_id) or ''

            # Find matching violations
            violations = self.violations_df[
                self.violations_df['parcel_id_normalized'] == parcel_normalized
            ]

            # Calculate metrics
            enrichment_data = self._calculate_violation_metrics(violations)

            # Merge with original property data
            enriched_prop = {
                **prop,
                **enrichment_data,
                'has_violations': len(violations) > 0,
                'parcel_id_normalized': parcel_normalized
            }

            enriched.append(enriched_prop)

        return enriched

    def _calculate_violation_metrics(self, violations: pd.DataFrame) -> Dict:
        """
        Calculate violation metrics for a property

        Args:
            violations: DataFrame of violations for a specific parcel

        Returns:
            Dictionary of violation metrics
        """
        if len(violations) == 0:
            return {
                'violation_count': 0,
                'open_violations': 0,
                'closed_violations': 0,
                'violation_types': [],
                'most_recent_violation': None,
                'avg_days_to_resolve': None
            }

        # Count by status
        status_counts = violations['caseinfostatus'].value_counts().to_dict()

        # Violation types
        case_types = violations['case_type'].dropna().unique().tolist()

        # Most recent violation
        violations['casedt'] = pd.to_datetime(violations['casedt'], errors='coerce')
        most_recent = violations['casedt'].max()
        most_recent_str = most_recent.strftime('%Y-%m-%d') if pd.notna(most_recent) else None

        # Average resolution time
        avg_days = violations['days_to_resolve'].mean()
        avg_days_clean = round(float(avg_days), 1) if pd.notna(avg_days) else None

        return {
            'violation_count': len(violations),
            'open_violations': status_counts.get('Open', 0),
            'closed_violations': status_counts.get('Closed', 0),
            'violation_types': case_types,
            'most_recent_violation': most_recent_str,
            'avg_days_to_resolve': avg_days_clean
        }

    def get_top_opportunities(
        self,
        enriched_properties: List[Dict],
        min_violations: int = 1
    ) -> List[Dict]:
        """
        Filter and rank properties by wholesale opportunity score

        Args:
            enriched_properties: List of enriched property dictionaries
            min_violations: Minimum violation count threshold

        Returns:
            Sorted list of high-opportunity properties
        """
        # Filter properties with violations
        opportunities = [
            prop for prop in enriched_properties
            if prop['violation_count'] >= min_violations
        ]

        # Sort by violation count (descending) - more violations = more distressed
        opportunities.sort(key=lambda x: x['violation_count'], reverse=True)

        return opportunities

    def display_enriched_property(self, prop: Dict, index: int = 1):
        """
        Display a single enriched property with violation details

        Args:
            prop: Enriched property dictionary
            index: Property index number for display
        """
        print(f"\n[Property {index}] {'HIGH OPPORTUNITY' if prop['violation_count'] > 0 else ''}")
        print(f"  TDA Number:         {prop['tda_number']}")
        print(f"  Sale Date:          {prop['sale_date']}")
        print(f"  Deed Status:        {prop['deed_status']}")
        print(f"  Parcel ID:          {prop['parcel_id']}")
        print(f"  Coordinates:        ({prop['latitude']:.6f}, {prop['longitude']:.6f})")
        print(f"\n  VIOLATION METRICS:")
        print(f"    Total Violations:    {prop['violation_count']}")
        print(f"    Open Violations:     {prop['open_violations']}")
        print(f"    Closed Violations:   {prop['closed_violations']}")
        print(f"    Violation Types:     {', '.join(prop['violation_types'][:5]) if prop['violation_types'] else 'N/A'}")
        print(f"    Most Recent:         {prop['most_recent_violation'] or 'N/A'}")
        print(f"    Avg Days to Resolve: {prop['avg_days_to_resolve'] or 'N/A'}")

        if prop['violation_count'] > 0:
            print(f"\n  WHOLESALE INSIGHT:")
            if prop['open_violations'] > 0:
                print(f"    {prop['open_violations']} open violations - owner may be motivated to sell")
            if prop['violation_count'] >= 3:
                print(f"    {prop['violation_count']} total violations - high distress indicator")

    def display_summary_stats(self, enriched_properties: List[Dict]):
        """
        Display summary statistics for enriched dataset

        Args:
            enriched_properties: List of enriched property dictionaries
        """
        total = len(enriched_properties)
        with_violations = sum(1 for p in enriched_properties if p['violation_count'] > 0)
        total_violations = sum(p['violation_count'] for p in enriched_properties)
        total_open = sum(p['open_violations'] for p in enriched_properties)

        print(f"\n{'='*80}")
        print(f"ENRICHMENT SUMMARY")
        print(f"{'='*80}")
        print(f"  Total Properties:           {total}")
        print(f"  Properties with Violations: {with_violations} ({with_violations/total*100:.1f}%)")
        print(f"  Total Violations:           {total_violations}")
        print(f"  Open Violations:            {total_open}")
        print(f"  Avg Violations per Property: {total_violations/total:.1f}")
        print(f"{'='*80}\n")
