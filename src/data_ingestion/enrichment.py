"""
Property Enrichment Module

Cross-references tax sale properties with code enforcement violations
to identify high-value wholesale opportunities.
"""
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime


class PropertyEnricher:
    """
    Enriches tax sale properties with code enforcement violation data.

    This class loads code enforcement violation data and matches it with
    tax sale properties based on normalized parcel IDs, providing violation
    metrics that indicate property distress levels.
    """

    def __init__(self, code_enforcement_csv_path: str):
        """
        Initialize enricher with code enforcement data.

        Args:
            code_enforcement_csv_path: Path to code enforcement CSV file
        """
        print(f"Loading code enforcement data from {code_enforcement_csv_path}...")
        self.violations_df = pd.read_csv(
            code_enforcement_csv_path,
            low_memory=False,
            dtype={'parcel_id': str}
        )
        print(f"Loaded {len(self.violations_df):,} violation records")
        print(f"Records with parcel IDs: {self.violations_df['parcel_id'].notna().sum():,}")

        # Normalize parcel IDs by removing formatting characters
        # Tax sale format: 29-22-28-8850-02-050
        # Code enforcement format: 292231182405260.0
        # Normalized format: 292228885002050 (remove dashes and decimal points)
        self.violations_df['parcel_id_normalized'] = (
            self.violations_df['parcel_id']
            .fillna('')
            .astype(str)
            .str.replace('-', '', regex=False)
            .str.replace('.0', '', regex=False)
            .str.strip()
            .str.upper()
        )

        # Display sample for debugging
        sample_normalized = self.violations_df[
            self.violations_df['parcel_id_normalized'] != ''
        ]['parcel_id_normalized'].head(5).tolist()
        print(f"Sample normalized IDs: {sample_normalized[:3]}")

    def enrich_properties(self, properties: List[Dict]) -> List[Dict]:
        """
        Enrich tax sale properties with violation data.

        Args:
            properties: List of tax sale property dictionaries

        Returns:
            List of enriched property dictionaries with violation metrics
        """
        enriched = []

        for prop in properties:
            # Normalize tax sale parcel ID using same logic
            parcel_id = prop.get('parcel_id', '')
            parcel_normalized = (
                parcel_id
                .replace('-', '')
                .replace('.0', '')
                .strip()
                .upper()
            )

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
        Calculate violation metrics for a property.

        Metrics include:
        - Total violation count
        - Open vs closed violations
        - Types of violations
        - Most recent violation date
        - Average resolution time

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
        Filter and rank properties by wholesale opportunity score.

        Properties with more violations are ranked higher, as they indicate
        greater distress and potentially more motivated sellers.

        Args:
            enriched_properties: List of enriched property dictionaries
            min_violations: Minimum violation count threshold

        Returns:
            Sorted list of high-opportunity properties (descending by violation count)
        """
        # Filter properties meeting minimum violation threshold
        opportunities = [
            prop for prop in enriched_properties
            if prop['violation_count'] >= min_violations
        ]

        # Sort by violation count (descending) - more violations = more distressed
        opportunities.sort(key=lambda x: x['violation_count'], reverse=True)

        return opportunities

    def display_enriched_property(self, prop: Dict, index: int = 1):
        """
        Display a single enriched property with violation details.

        Args:
            prop: Enriched property dictionary
            index: Property index number for display
        """
        # Header with opportunity flag
        opportunity_flag = " [HIGH OPPORTUNITY]" if prop['violation_count'] > 0 else ""
        print(f"\n[Property {index}]{opportunity_flag}")

        # Basic property info
        print(f"  TDA Number:         {prop['tda_number']}")
        print(f"  Sale Date:          {prop['sale_date']}")
        print(f"  Deed Status:        {prop['deed_status']}")
        print(f"  Parcel ID:          {prop['parcel_id']}")
        print(f"  Coordinates:        ({prop['latitude']:.6f}, {prop['longitude']:.6f})")

        # Violation metrics
        print(f"\n  VIOLATION METRICS:")
        print(f"    Total Violations:    {prop['violation_count']}")
        print(f"    Open Violations:     {prop['open_violations']}")
        print(f"    Closed Violations:   {prop['closed_violations']}")

        # Violation types (limit to 5 for readability)
        types_display = ', '.join(prop['violation_types'][:5]) if prop['violation_types'] else 'N/A'
        print(f"    Violation Types:     {types_display}")
        print(f"    Most Recent:         {prop['most_recent_violation'] or 'N/A'}")
        print(f"    Avg Days to Resolve: {prop['avg_days_to_resolve'] or 'N/A'}")

        # Wholesale insights for properties with violations
        if prop['violation_count'] > 0:
            print(f"\n  WHOLESALE INSIGHT:")
            if prop['open_violations'] > 0:
                print(f"    - {prop['open_violations']} open violations indicate motivated seller")
            if prop['violation_count'] >= 3:
                print(f"    - {prop['violation_count']} total violations suggest high distress")
            print(f"    - Use violation data to estimate repair costs and negotiate")

    def display_summary_stats(self, enriched_properties: List[Dict]):
        """
        Display summary statistics for enriched dataset.

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
        if total > 0:
            print(f"  Avg Violations per Property: {total_violations/total:.1f}")
        print(f"{'='*80}\n")
