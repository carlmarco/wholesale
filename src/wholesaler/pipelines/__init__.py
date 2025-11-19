"""
Pipelines Package

Data transformation pipelines.

Note: Most pipelines have been migrated to dedicated modules:
- Enrichment → src.wholesaler.enrichment
- Scoring → src.wholesaler.scoring

This module contains remaining transformation pipelines:
- Deduplication: Property record merging
"""
from src.wholesaler.pipelines.deduplication import PropertyDeduplicator

__all__ = ["PropertyDeduplicator"]
