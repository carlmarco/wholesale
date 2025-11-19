# DEPRECATED MODULE

**Status**: This module is deprecated as of 2025-11-12.

## Migration Path

All functionality from `src/data_ingestion/` has been migrated to the new modular architecture:

- **Enrichment** → `src/wholesaler/enrichment/`
- **Scoring** → `src/wholesaler/scoring/`
- **Ingestion** → `src/wholesaler/ingestion/`
- **Scrapers** → `src/wholesaler/scrapers/`

## Files in this Directory

- `enrichment.py` - **DEPRECATED** → Use `src/wholesaler/enrichment/pipeline.py` (PropertyEnricher class is still used temporarily)
- `geo_enrichment.py` - **DEPRECATED** → Use `src/wholesaler/enrichers/geo_enricher.py`
- `tax_sale_scraper.py` - **DEPRECATED** → Use `src/wholesaler/scrapers/tax_sale_scraper.py`
- `pipeline.py` - **DEPRECATED** → Use new seed-based ingestion pipeline
- `geo_pipeline.py` - **DEPRECATED** → Replaced by modular enrichment

## Removal Timeline

This directory will be removed in a future release after all dependencies are migrated.

## Current Status

- **PropertyEnricher** class from `enrichment.py` is still temporarily used by `UnifiedEnrichmentPipeline`
- All other functionality has been fully migrated
- No new code should be added to this module
