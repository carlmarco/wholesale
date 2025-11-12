"""
Seed Merger

Merges enriched seeds from staging table into main properties table.
Handles multi-source deduplication and seed_type tracking.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from src.wholesaler.db.repository import (
    EnrichedSeedRepository,
    PropertyRepository,
    DataIngestionRunRepository,
)
from src.wholesaler.db.models import EnrichedSeed
from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class SeedMerger:
    """
    Merge enriched seeds into properties table.

    Handles:
    - Creating new properties from seeds
    - Merging seed_type for multi-source properties
    - Tracking processed seeds
    """

    def __init__(self):
        self.seed_repo = EnrichedSeedRepository()
        self.property_repo = PropertyRepository()
        self.standardizer = AddressStandardizer()
        logger.info("seed_merger_initialized")

    def merge_seeds(
        self,
        session: Session,
        seed_type: Optional[str] = None,
        limit: Optional[int] = None,
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Merge unprocessed seeds into properties table.

        Args:
            session: Database session
            seed_type: Optional filter by seed type
            limit: Optional limit on number to process
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            source_label = f'seed_merge_{seed_type}' if seed_type else 'seed_merge_all'
            run = run_repo.create_run(session, source_label)
            run_id = run.id

        stats = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'failed': 0,
        }

        try:
            # Get unprocessed seeds
            seeds = self.seed_repo.get_unprocessed(session, seed_type=seed_type, limit=limit)
            logger.info("seeds_fetched_for_merge", count=len(seeds), seed_type=seed_type or "all")

            for seed in seeds:
                try:
                    # Merge seed into properties table
                    self._merge_single_seed(session, seed, stats)

                    # Mark as processed
                    self.seed_repo.mark_processed(session, seed.id)
                    stats['processed'] += 1

                except Exception as e:
                    logger.error(
                        "seed_merge_failed",
                        seed_id=seed.id,
                        parcel_id=seed.parcel_id_normalized,
                        seed_type=seed.seed_type,
                        error=str(e)
                    )
                    stats['failed'] += 1

            # Commit transaction
            session.commit()

            if track_run and run_id:
                run_repo.complete_run(
                    session,
                    run_id,
                    status='success' if stats['failed'] == 0 else 'partial',
                    records_processed=stats['processed'],
                    records_inserted=stats['created'],
                    records_updated=stats['updated'],
                    records_failed=stats['failed']
                )

            logger.info("seeds_merged", stats=stats)
            return stats

        except Exception as e:
            logger.error("seed_merge_batch_failed", error=str(e))
            session.rollback()

            if track_run and run_id:
                run_repo.complete_run(
                    session,
                    run_id,
                    status='failure',
                    error_message=str(e)
                )

            raise

    def _merge_single_seed(
        self,
        session: Session,
        seed: EnrichedSeed,
        stats: Dict[str, int]
    ) -> None:
        """
        Merge a single seed into properties table.

        Args:
            session: Database session
            seed: EnrichedSeed instance
            stats: Stats dict to update

        Updates stats dict in-place.
        """
        # Check if property already exists
        existing_property = self.property_repo.get_by_parcel(
            session,
            seed.parcel_id_normalized
        )

        # Extract relevant data from enriched_data
        enriched_data = seed.enriched_data or {}

        if existing_property:
            # Update existing property
            self._update_property_from_seed(existing_property, seed, enriched_data)
            session.flush()
            stats['updated'] += 1
            logger.debug(
                "property_updated_from_seed",
                parcel_id=seed.parcel_id_normalized,
                seed_type=seed.seed_type
            )
        else:
            # Create new property from seed
            property_data = self._build_property_data_from_seed(seed, enriched_data)
            self.property_repo.upsert(session, property_data)
            stats['created'] += 1
            logger.debug(
                "property_created_from_seed",
                parcel_id=seed.parcel_id_normalized,
                seed_type=seed.seed_type
            )

    def _update_property_from_seed(
        self,
        property_obj,
        seed: EnrichedSeed,
        enriched_data: Dict[str, Any]
    ) -> None:
        """
        Update existing property with seed data.

        Args:
            property_obj: Property model instance
            seed: EnrichedSeed instance
            enriched_data: Enriched data dict

        Modifies property_obj in-place.
        """
        # Merge seed_type (handle multi-source properties)
        if property_obj.seed_type:
            # Check if this seed_type is already present
            existing_types = set(property_obj.seed_type.split(','))
            if seed.seed_type not in existing_types:
                existing_types.add(seed.seed_type)
                property_obj.seed_type = ','.join(sorted(existing_types))
                logger.debug(
                    "seed_type_merged",
                    parcel_id=seed.parcel_id_normalized,
                    seed_types=property_obj.seed_type
                )
        else:
            property_obj.seed_type = seed.seed_type

        # Update coordinates if missing and available in seed
        if not property_obj.latitude and enriched_data.get('latitude'):
            property_obj.latitude = enriched_data.get('latitude')
        if not property_obj.longitude and enriched_data.get('longitude'):
            property_obj.longitude = enriched_data.get('longitude')

        # Update address fields if missing
        if not property_obj.situs_address and enriched_data.get('situs_address'):
            property_obj.situs_address = enriched_data.get('situs_address')
        if not property_obj.city and enriched_data.get('city'):
            property_obj.city = enriched_data.get('city')
        if not property_obj.zip_code and enriched_data.get('zip_code'):
            property_obj.zip_code = enriched_data.get('zip_code')

        property_obj.updated_at = datetime.now()

    def _build_property_data_from_seed(
        self,
        seed: EnrichedSeed,
        enriched_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build property data dict from seed for new property creation.

        Args:
            seed: EnrichedSeed instance
            enriched_data: Enriched data dict

        Returns:
            Property data dict for upsert
        """
        # Standardize address if available
        situs_address = enriched_data.get('situs_address')
        city = enriched_data.get('city')
        state = enriched_data.get('state', 'FL')
        zip_code = enriched_data.get('zip_code')

        if situs_address and not city:
            # Attempt to standardize address to extract city/zip
            standardized = self.standardizer.standardize(situs_address)
            if standardized:
                situs_address = standardized.full_address
                city = city or standardized.city
                state = state or standardized.state
                zip_code = zip_code or standardized.zip_code

        property_data = {
            'parcel_id_normalized': seed.parcel_id_normalized,
            'parcel_id_original': enriched_data.get('parcel_id', seed.parcel_id_normalized),
            'seed_type': seed.seed_type,
            'situs_address': situs_address,
            'city': city,
            'state': state,
            'zip_code': zip_code,
            'latitude': enriched_data.get('latitude'),
            'longitude': enriched_data.get('longitude'),
            'is_active': True,
        }

        return property_data

    def get_merge_stats(self, session: Session) -> Dict[str, Any]:
        """
        Get statistics about seed merge status.

        Args:
            session: Database session

        Returns:
            Dict with merge statistics
        """
        seed_stats = self.seed_repo.get_stats(session)

        # Get property counts by seed_type
        from src.wholesaler.db.models import Property
        from sqlalchemy import func

        properties_by_seed = session.query(
            Property.seed_type,
            func.count(Property.parcel_id_normalized)
        ).filter(
            Property.seed_type.isnot(None)
        ).group_by(Property.seed_type).all()

        return {
            'seeds': seed_stats,
            'properties_by_seed_type': {
                seed_type: count for seed_type, count in properties_by_seed
            }
        }
