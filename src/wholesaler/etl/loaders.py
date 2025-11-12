"""
ETL Loaders

Convert Pydantic models (Phase 1) to SQLAlchemy models (Phase 2) and load into database.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from src.wholesaler.models.property import TaxSaleProperty, EnrichedProperty
from src.wholesaler.models.foreclosure import ForeclosureProperty
from src.wholesaler.models.property_record import PropertyRecord as PydanticPropertyRecord
from src.wholesaler.pipelines.lead_scoring import LeadScore as PydanticLeadScore

from src.wholesaler.db.repository import (
    PropertyRepository,
    TaxSaleRepository,
    ForeclosureRepository,
    PropertyRecordRepository,
    EnrichedSeedRepository,
    LeadScoreRepository,
    DataIngestionRunRepository,
)
from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class PropertyLoader:
    """
    Load properties into database from Pydantic models.

    Handles conversion from Phase 1 Pydantic models to Phase 2 SQLAlchemy models.
    """

    def __init__(self):
        self.repository = PropertyRepository()
        self.standardizer = AddressStandardizer()
        logger.info("property_loader_initialized")

    def load_from_tax_sale(
        self,
        session: Session,
        tax_sale_property: TaxSaleProperty
    ) -> Dict[str, Any]:
        """
        Load property from tax sale Pydantic model.

        Args:
            session: Database session
            tax_sale_property: Tax sale property from Phase 1

        Returns:
            Property data dict for upsert
        """
        # Normalize parcel ID
        parcel_id_normalized = self.standardizer.normalize_parcel_id(
            tax_sale_property.parcel_id
        )

        if not parcel_id_normalized:
            raise ValueError(f"Cannot normalize parcel ID: {tax_sale_property.parcel_id}")

        # Standardize address if available
        situs_address = None
        city = None
        state = None
        zip_code = None

        if hasattr(tax_sale_property, 'address') and tax_sale_property.address:
            standardized = self.standardizer.standardize(tax_sale_property.address)
            situs_address = standardized.full_address
            city = standardized.city
            state = standardized.state
            zip_code = standardized.zip_code

        property_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'parcel_id_original': tax_sale_property.parcel_id,
            'situs_address': situs_address,
            'city': city,
            'state': state,
            'zip_code': zip_code,
            'latitude': tax_sale_property.latitude,
            'longitude': tax_sale_property.longitude,
        }

        return property_data

    def load_from_enriched(
        self,
        session: Session,
        enriched_property: EnrichedProperty
    ) -> Dict[str, Any]:
        """
        Load property from enriched Pydantic model.

        Args:
            session: Database session
            enriched_property: Enriched property from Phase 1

        Returns:
            Property data dict for upsert
        """
        parcel_id_normalized = self.standardizer.normalize_parcel_id(
            enriched_property.parcel_id
        )

        if not parcel_id_normalized:
            raise ValueError(f"Cannot normalize parcel ID: {enriched_property.parcel_id}")

        property_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'parcel_id_original': enriched_property.parcel_id,
            'latitude': enriched_property.latitude,
            'longitude': enriched_property.longitude,
        }

        return property_data

    def bulk_load(
        self,
        session: Session,
        tax_sale_properties: List[TaxSaleProperty],
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Bulk load properties from tax sale list.

        Args:
            session: Database session
            tax_sale_properties: List of tax sale properties
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            run = run_repo.create_run(session, 'properties_from_tax_sales')
            run_id = run.id

        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
        }

        properties_data = []
        for tax_sale in tax_sale_properties:
            try:
                property_data = self.load_from_tax_sale(session, tax_sale)
                properties_data.append(property_data)
                stats['processed'] += 1
            except Exception as e:
                logger.error(
                    "property_load_failed",
                    parcel_id=getattr(tax_sale, 'parcel_id', None),
                    error=str(e)
                )
                stats['failed'] += 1

        if properties_data:
            count = self.repository.bulk_upsert(session, properties_data)
            stats['inserted'] = count  # Note: Can't distinguish insert vs update in bulk

        if track_run and run_id:
            run_repo.complete_run(
                session,
                run_id,
                status='success' if stats['failed'] == 0 else 'partial',
                records_processed=stats['processed'],
                records_inserted=stats['inserted'],
                records_failed=stats['failed']
            )

        logger.info("properties_bulk_loaded", stats=stats)
        return stats


class TaxSaleLoader:
    """Load tax sales into database from Pydantic models."""

    def __init__(self):
        self.repository = TaxSaleRepository()
        self.property_loader = PropertyLoader()
        self.standardizer = AddressStandardizer()
        logger.info("tax_sale_loader_initialized")

    def load(
        self,
        session: Session,
        tax_sale_property: TaxSaleProperty
    ) -> Dict[str, Any]:
        """
        Load tax sale from Pydantic model.

        Args:
            session: Database session
            tax_sale_property: Tax sale property from Phase 1

        Returns:
            Tax sale data dict for upsert
        """
        # Ensure property exists first
        property_data = self.property_loader.load_from_tax_sale(session, tax_sale_property)
        self.property_loader.repository.upsert(session, property_data)

        parcel_id_normalized = self.standardizer.normalize_parcel_id(
            tax_sale_property.parcel_id
        )

        tax_sale_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'tda_number': tax_sale_property.tda_number,
            'sale_date': tax_sale_property.sale_date,
            'deed_status': tax_sale_property.deed_status,
            'latitude': tax_sale_property.latitude,
            'longitude': tax_sale_property.longitude,
            'raw_data': tax_sale_property.to_dict(),
            'data_source_timestamp': datetime.now(),
        }

        return tax_sale_data

    def bulk_load(
        self,
        session: Session,
        tax_sale_properties: List[TaxSaleProperty],
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Bulk load tax sales.

        Args:
            session: Database session
            tax_sale_properties: List of tax sale properties
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            run = run_repo.create_run(session, 'tax_sales')
            run_id = run.id

        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
        }

        for tax_sale in tax_sale_properties:
            try:
                tax_sale_data = self.load(session, tax_sale)
                self.repository.upsert_by_parcel(session, tax_sale_data)
                stats['processed'] += 1
                stats['inserted'] += 1  # Simplified - can't easily distinguish
            except Exception as e:
                logger.error(
                    "tax_sale_load_failed",
                    parcel_id=getattr(tax_sale, 'parcel_id', None),
                    error=str(e)
                )
                stats['failed'] += 1

        if track_run and run_id:
            run_repo.complete_run(
                session,
                run_id,
                status='success' if stats['failed'] == 0 else 'partial',
                records_processed=stats['processed'],
                records_inserted=stats['inserted'],
                records_failed=stats['failed']
            )

        logger.info("tax_sales_bulk_loaded", stats=stats)
        return stats


class ForeclosureLoader:
    """Load foreclosures into database from Pydantic models."""

    def __init__(self):
        self.repository = ForeclosureRepository()
        self.property_loader = PropertyLoader()
        self.standardizer = AddressStandardizer()
        logger.info("foreclosure_loader_initialized")

    def load(
        self,
        session: Session,
        foreclosure_property: ForeclosureProperty
    ) -> Dict[str, Any]:
        """
        Load foreclosure from Pydantic model.

        Args:
            session: Database session
            foreclosure_property: Foreclosure property from Phase 1

        Returns:
            Foreclosure data dict for upsert
        """
        parcel_id_normalized = self.standardizer.normalize_parcel_id(
            foreclosure_property.parcel_number
        )

        if not parcel_id_normalized:
            raise ValueError(f"Cannot normalize parcel ID: {foreclosure_property.parcel_number}")

        # Ensure property exists
        property_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'parcel_id_original': foreclosure_property.parcel_number,
            'situs_address': foreclosure_property.situs_address,
            'latitude': foreclosure_property.latitude,
            'longitude': foreclosure_property.longitude,
        }
        self.property_loader.repository.upsert(session, property_data)

        foreclosure_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'borrowers_name': foreclosure_property.borrowers_name,
            'situs_address': foreclosure_property.situs_address,
            'default_amount': foreclosure_property.default_amount,
            'opening_bid': foreclosure_property.opening_bid,
            'auction_date': foreclosure_property.auction_date,
            'lender_name': foreclosure_property.lender_name,
            'property_type': foreclosure_property.property_type,
            'latitude': foreclosure_property.latitude,
            'longitude': foreclosure_property.longitude,
            'raw_data': foreclosure_property.to_dict(),
            'data_source_timestamp': datetime.now(),
        }

        return foreclosure_data

    def bulk_load(
        self,
        session: Session,
        foreclosure_properties: List[ForeclosureProperty],
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Bulk load foreclosures.

        Args:
            session: Database session
            foreclosure_properties: List of foreclosure properties
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            run = run_repo.create_run(session, 'foreclosures')
            run_id = run.id

        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
        }

        for foreclosure in foreclosure_properties:
            try:
                foreclosure_data = self.load(session, foreclosure)
                self.repository.upsert_by_parcel(session, foreclosure_data)
                stats['processed'] += 1
                stats['inserted'] += 1
            except Exception as e:
                logger.error(
                    "foreclosure_load_failed",
                    parcel_id=getattr(foreclosure, 'parcel_number', None),
                    error=str(e)
                )
                stats['failed'] += 1

        if track_run and run_id:
            run_repo.complete_run(
                session,
                run_id,
                status='success' if stats['failed'] == 0 else 'partial',
                records_processed=stats['processed'],
                records_inserted=stats['inserted'],
                records_failed=stats['failed']
            )

        logger.info("foreclosures_bulk_loaded", stats=stats)
        return stats


class PropertyRecordLoader:
    """Load property records into database from Pydantic models."""

    def __init__(self):
        self.repository = PropertyRecordRepository()
        self.property_loader = PropertyLoader()
        self.standardizer = AddressStandardizer()
        logger.info("property_record_loader_initialized")

    def load(
        self,
        session: Session,
        property_record: PydanticPropertyRecord
    ) -> Dict[str, Any]:
        """
        Load property record from Pydantic model.

        Args:
            session: Database session
            property_record: Property record from Phase 1

        Returns:
            Property record data dict for upsert
        """
        parcel_id_normalized = self.standardizer.normalize_parcel_id(
            property_record.parcel_number
        )

        if not parcel_id_normalized:
            raise ValueError(f"Cannot normalize parcel ID: {property_record.parcel_number}")

        # Ensure property exists
        property_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'parcel_id_original': property_record.parcel_number,
            'situs_address': property_record.situs_address,
            'latitude': property_record.latitude,
            'longitude': property_record.longitude,
        }
        self.property_loader.repository.upsert(session, property_data)

        property_record_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'owner_name': property_record.owner_name,
            'total_mkt': property_record.total_mkt,
            'total_assd': property_record.total_assd,
            'taxable': property_record.taxable,
            'taxes': property_record.taxes,
            'year_built': property_record.year_built,
            'living_area': property_record.living_area,
            'lot_size': property_record.lot_size,
            'equity_percent': property_record.calculate_equity_percent(),
            'tax_rate': property_record.calculate_tax_rate(),
            'latitude': property_record.latitude,
            'longitude': property_record.longitude,
            'raw_data': property_record.to_dict(),
            'data_source_timestamp': datetime.now(),
        }

        return property_record_data

    def bulk_load(
        self,
        session: Session,
        property_records: List[PydanticPropertyRecord],
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Bulk load property records.

        Args:
            session: Database session
            property_records: List of property records
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            run = run_repo.create_run(session, 'property_records')
            run_id = run.id

        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
        }

        for property_record in property_records:
            try:
                property_record_data = self.load(session, property_record)
                self.repository.upsert_by_parcel(session, property_record_data)
                stats['processed'] += 1
                stats['inserted'] += 1
            except Exception as e:
                logger.error(
                    "property_record_load_failed",
                    parcel_id=getattr(property_record, 'parcel_number', None),
                    error=str(e)
                )
                stats['failed'] += 1

        if track_run and run_id:
            run_repo.complete_run(
                session,
                run_id,
                status='success' if stats['failed'] == 0 else 'partial',
                records_processed=stats['processed'],
                records_inserted=stats['inserted'],
                records_failed=stats['failed']
            )

        logger.info("property_records_bulk_loaded", stats=stats)
        return stats


class LeadScoreLoader:
    """Load lead scores into database from Phase 1 scoring results."""

    def __init__(self):
        self.repository = LeadScoreRepository()
        self.standardizer = AddressStandardizer()
        logger.info("lead_score_loader_initialized")

    def load(
        self,
        session: Session,
        parcel_id: str,
        lead_score: PydanticLeadScore,
        create_history: bool = True
    ) -> Dict[str, Any]:
        """
        Load lead score from Pydantic dataclass.

        Args:
            session: Database session
            parcel_id: Parcel ID
            lead_score: Lead score from Phase 1
            create_history: Whether to create history snapshot

        Returns:
            Lead score data dict for upsert
        """
        parcel_id_normalized = self.standardizer.normalize_parcel_id(parcel_id)

        if not parcel_id_normalized:
            raise ValueError(f"Cannot normalize parcel ID: {parcel_id}")

        lead_score_data = {
            'parcel_id_normalized': parcel_id_normalized,
            'total_score': lead_score.total_score,
            'distress_score': lead_score.distress_score,
            'value_score': lead_score.value_score,
            'location_score': lead_score.location_score,
            'urgency_score': lead_score.urgency_score,
            'tier': lead_score.tier,
            'reasons': lead_score.reasons,
            'scored_at': datetime.now(),
        }

        # Upsert lead score
        db_lead_score = self.repository.upsert_by_parcel(session, lead_score_data)

        # Create history snapshot if requested
        if create_history:
            self.repository.create_history_snapshot(session, db_lead_score.id)

        return lead_score_data

    def bulk_load(
        self,
        session: Session,
        scored_leads: List[tuple],
        create_history: bool = True,
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Bulk load lead scores.

        Args:
            session: Database session
            scored_leads: List of (merged_property, lead_score) tuples
            create_history: Whether to create history snapshots
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            run = run_repo.create_run(session, 'lead_scores')
            run_id = run.id

        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
        }

        for merged_property, lead_score in scored_leads:
            try:
                parcel_id = merged_property.get('parcel_id_normalized') or merged_property.get('parcel_id_original')
                if not parcel_id:
                    raise ValueError("No parcel ID found in merged property")

                self.load(session, parcel_id, lead_score, create_history=create_history)
                stats['processed'] += 1
                stats['inserted'] += 1
            except Exception as e:
                logger.error(
                    "lead_score_load_failed",
                    parcel_id=merged_property.get('parcel_id_normalized'),
                    error=str(e)
                )
                stats['failed'] += 1

        if track_run and run_id:
            run_repo.complete_run(
                session,
                run_id,
                status='success' if stats['failed'] == 0 else 'partial',
                records_processed=stats['processed'],
                records_inserted=stats['inserted'],
                records_failed=stats['failed']
            )

        logger.info("lead_scores_bulk_loaded", stats=stats)
        return stats


class EnrichedSeedLoader:
    """Load enriched seeds into database from parquet files."""

    def __init__(self):
        self.repository = EnrichedSeedRepository()
        self.standardizer = AddressStandardizer()
        logger.info("enriched_seed_loader_initialized")

    def load_from_parquet(
        self,
        session: Session,
        parquet_path: str,
        track_run: bool = True
    ) -> Dict[str, int]:
        """
        Load enriched seeds from parquet file.

        Args:
            session: Database session
            parquet_path: Path to enriched_seeds.parquet file
            track_run: Whether to track ingestion run

        Returns:
            Stats dict with counts
        """
        import pandas as pd
        from pathlib import Path

        if not Path(parquet_path).exists():
            logger.error("parquet_file_not_found", path=parquet_path)
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

        run_id = None
        if track_run:
            run_repo = DataIngestionRunRepository()
            run = run_repo.create_run(session, 'enriched_seeds')
            run_id = run.id

        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
        }

        try:
            # Read parquet file
            df = pd.read_parquet(parquet_path)
            logger.info("parquet_file_loaded", path=parquet_path, rows=len(df))

            # Process each record
            for idx, row in df.iterrows():
                try:
                    # Extract required fields
                    parcel_id = row.get('parcel_id')
                    seed_type = row.get('seed_type')

                    if not parcel_id or not seed_type:
                        logger.warning(
                            "missing_required_fields",
                            row_index=idx,
                            parcel_id=parcel_id,
                            seed_type=seed_type
                        )
                        stats['failed'] += 1
                        continue

                    # Normalize parcel ID
                    parcel_id_normalized = self.standardizer.normalize_parcel_id(parcel_id)
                    if not parcel_id_normalized:
                        logger.warning(
                            "cannot_normalize_parcel_id",
                            row_index=idx,
                            parcel_id=parcel_id
                        )
                        stats['failed'] += 1
                        continue

                    # Convert row to dict (handling NaN values)
                    enriched_data = row.to_dict()
                    # Replace NaN with None for JSON serialization
                    enriched_data = {
                        k: (None if pd.isna(v) else v)
                        for k, v in enriched_data.items()
                    }

                    # Upsert to database
                    self.repository.upsert(
                        session,
                        parcel_id_normalized=parcel_id_normalized,
                        seed_type=seed_type,
                        enriched_data=enriched_data
                    )

                    stats['processed'] += 1
                    stats['inserted'] += 1  # Simplified - can't easily distinguish

                except Exception as e:
                    logger.error(
                        "enriched_seed_load_failed",
                        row_index=idx,
                        parcel_id=row.get('parcel_id'),
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
                    records_inserted=stats['inserted'],
                    records_failed=stats['failed']
                )

            logger.info("enriched_seeds_loaded", stats=stats)
            return stats

        except Exception as e:
            logger.error("parquet_load_failed", path=parquet_path, error=str(e))
            session.rollback()

            if track_run and run_id:
                run_repo.complete_run(
                    session,
                    run_id,
                    status='failure',
                    error_message=str(e)
                )

            raise
