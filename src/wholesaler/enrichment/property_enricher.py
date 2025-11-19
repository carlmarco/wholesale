"""
Property Enrichment Utilities

Enriches seed properties with violation metrics by parcel ID.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional, Union

import pandas as pd

from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class PropertyEnricher:
    """Enriches properties with code enforcement violation data."""

    def __init__(self, violations: Union[pd.DataFrame, List[Dict]]):
        if violations is None:
            raise ValueError("Violation records are required")

        self.standardizer = AddressStandardizer()
        self.violations_df = self._prepare_violations_dataframe(violations)
        logger.info(
            "violation_records_loaded",
            total=len(self.violations_df),
            with_parcel_ids=int(self.violations_df['parcel_id'].notna().sum())
        )

    @classmethod
    def from_csv(cls, csv_path: str) -> "PropertyEnricher":
        df = pd.read_csv(csv_path, low_memory=False, dtype={'parcel_id': str})
        return cls(df)

    def _prepare_violations_dataframe(
        self,
        violations: Union[pd.DataFrame, List[Dict]]
    ) -> pd.DataFrame:
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
        enriched = []

        for prop in properties:
            parcel_id = prop.get('parcel_id')
            parcel_normalized = self.standardizer.normalize_parcel_id(parcel_id) or ''

            violations = self.violations_df[
                self.violations_df['parcel_id_normalized'] == parcel_normalized
            ]

            enrichment_data = self._calculate_violation_metrics(violations)

            enriched_prop = {
                **prop,
                **enrichment_data,
                'has_violations': len(violations) > 0,
                'parcel_id_normalized': parcel_normalized,
            }

            enriched.append(enriched_prop)

        return enriched

    def _calculate_violation_metrics(self, violations: pd.DataFrame) -> Dict:
        if len(violations) == 0:
            return {
                'violation_count': 0,
                'open_violations': 0,
                'closed_violations': 0,
                'violation_types': [],
                'most_recent_violation': None,
                'avg_days_to_resolve': None
            }

        status_counts = violations['caseinfostatus'].value_counts().to_dict()
        case_types = violations['case_type'].dropna().unique().tolist()

        violations = violations.copy()
        violations['casedt'] = pd.to_datetime(violations['casedt'], errors='coerce')
        most_recent = violations['casedt'].max()
        most_recent_str = most_recent.strftime('%Y-%m-%d') if pd.notna(most_recent) else None

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
        opportunities = [
            prop for prop in enriched_properties
            if prop['violation_count'] >= min_violations
        ]
        opportunities.sort(key=lambda x: x['violation_count'], reverse=True)
        return opportunities

    def display_summary_stats(self, enriched_properties: List[Dict]):
        total = len(enriched_properties)
        with_violations = sum(1 for p in enriched_properties if p['violation_count'] > 0)
        total_violations = sum(p['violation_count'] for p in enriched_properties)
        total_open = sum(p['open_violations'] for p in enriched_properties)

        logger.info(
            "enrichment_summary",
            total_properties=total,
            properties_with_violations=with_violations,
            total_violations=total_violations,
            total_open_violations=total_open
        )
