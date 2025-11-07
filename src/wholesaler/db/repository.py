"""
Repository Pattern for Data Access

Provides CRUD operations and domain-specific queries for all models.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Type, TypeVar

from sqlalchemy import select, update, delete, func, and_, or_, desc
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.wholesaler.db.models import (
    Property,
    TaxSale,
    Foreclosure,
    PropertyRecord,
    CodeViolation,
    LeadScore,
    LeadScoreHistory,
    DataIngestionRun,
)
from src.wholesaler.db.session import get_db_session, with_retry
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class BaseRepository:
    """
    Base repository with common CRUD operations.

    Generic repository that can be extended for specific models.
    """

    def __init__(self, model: Type[T]):
        """
        Initialize repository with model class.

        Args:
            model: SQLAlchemy model class
        """
        self.model = model
        logger.debug("repository_initialized", model=model.__name__)

    def get_by_id(self, session: Session, id_value: Any) -> Optional[T]:
        """
        Get single record by primary key.

        Args:
            session: Database session
            id_value: Primary key value

        Returns:
            Model instance or None
        """
        result = session.get(self.model, id_value)
        logger.debug(
            "repository_get_by_id",
            model=self.model.__name__,
            id=id_value,
            found=result is not None
        )
        return result

    def get_all(self, session: Session, limit: Optional[int] = None, offset: int = 0) -> List[T]:
        """
        Get all records with optional pagination.

        Args:
            session: Database session
            limit: Maximum number of records
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        query = select(self.model).offset(offset)
        if limit:
            query = query.limit(limit)

        result = session.execute(query).scalars().all()
        logger.debug(
            "repository_get_all",
            model=self.model.__name__,
            count=len(result),
            limit=limit,
            offset=offset
        )
        return result

    def create(self, session: Session, **kwargs) -> T:
        """
        Create new record.

        Args:
            session: Database session
            **kwargs: Model field values

        Returns:
            Created model instance
        """
        instance = self.model(**kwargs)
        session.add(instance)
        session.flush()
        logger.info("repository_created", model=self.model.__name__, id=getattr(instance, 'id', None))
        return instance

    def update(self, session: Session, id_value: Any, **kwargs) -> Optional[T]:
        """
        Update existing record.

        Args:
            session: Database session
            id_value: Primary key value
            **kwargs: Fields to update

        Returns:
            Updated model instance or None
        """
        instance = self.get_by_id(session, id_value)
        if not instance:
            logger.warning("repository_update_not_found", model=self.model.__name__, id=id_value)
            return None

        for key, value in kwargs.items():
            setattr(instance, key, value)

        session.flush()
        logger.info("repository_updated", model=self.model.__name__, id=id_value)
        return instance

    def delete(self, session: Session, id_value: Any) -> bool:
        """
        Delete record (hard delete).

        Args:
            session: Database session
            id_value: Primary key value

        Returns:
            True if deleted, False if not found
        """
        instance = self.get_by_id(session, id_value)
        if not instance:
            logger.warning("repository_delete_not_found", model=self.model.__name__, id=id_value)
            return False

        session.delete(instance)
        session.flush()
        logger.info("repository_deleted", model=self.model.__name__, id=id_value)
        return True

    def soft_delete(self, session: Session, id_value: Any) -> bool:
        """
        Soft delete record (set is_active=False).

        Only works for models with SoftDeleteMixin.

        Args:
            session: Database session
            id_value: Primary key value

        Returns:
            True if soft deleted, False if not found
        """
        if not hasattr(self.model, 'is_active'):
            raise AttributeError(f"{self.model.__name__} does not support soft delete")

        instance = self.get_by_id(session, id_value)
        if not instance:
            logger.warning("repository_soft_delete_not_found", model=self.model.__name__, id=id_value)
            return False

        instance.is_active = False
        session.flush()
        logger.info("repository_soft_deleted", model=self.model.__name__, id=id_value)
        return True

    def count(self, session: Session) -> int:
        """
        Count total records.

        Args:
            session: Database session

        Returns:
            Total count
        """
        count = session.scalar(select(func.count()).select_from(self.model))
        logger.debug("repository_count", model=self.model.__name__, count=count)
        return count


class PropertyRepository(BaseRepository):
    """Repository for Property model with specialized queries."""

    def __init__(self):
        super().__init__(Property)

    def get_by_parcel(self, session: Session, parcel_id: str) -> Optional[Property]:
        """
        Get property by normalized parcel ID.

        Args:
            session: Database session
            parcel_id: Normalized parcel ID

        Returns:
            Property instance or None
        """
        return self.get_by_id(session, parcel_id)

    def upsert(self, session: Session, property_data: Dict[str, Any]) -> Property:
        """
        Insert or update property by parcel ID.

        Args:
            session: Database session
            property_data: Property field values (must include parcel_id_normalized)

        Returns:
            Property instance
        """
        parcel_id = property_data.get('parcel_id_normalized')
        if not parcel_id:
            raise ValueError("parcel_id_normalized is required for upsert")

        stmt = insert(Property).values(**property_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['parcel_id_normalized'],
            set_={k: v for k, v in property_data.items() if k != 'parcel_id_normalized'}
        )

        session.execute(stmt)
        session.flush()

        logger.info("property_upserted", parcel_id=parcel_id)
        return self.get_by_parcel(session, parcel_id)

    def bulk_upsert(self, session: Session, properties: List[Dict[str, Any]]) -> int:
        """
        Bulk insert or update properties.

        Args:
            session: Database session
            properties: List of property dictionaries

        Returns:
            Number of properties processed
        """
        if not properties:
            return 0

        stmt = insert(Property).values(properties)
        stmt = stmt.on_conflict_do_update(
            index_elements=['parcel_id_normalized'],
            set_={
                'parcel_id_original': stmt.excluded.parcel_id_original,
                'situs_address': stmt.excluded.situs_address,
                'city': stmt.excluded.city,
                'state': stmt.excluded.state,
                'zip_code': stmt.excluded.zip_code,
                'coordinates': stmt.excluded.coordinates,
                'latitude': stmt.excluded.latitude,
                'longitude': stmt.excluded.longitude,
                'updated_at': func.now(),
            }
        )

        session.execute(stmt)
        session.flush()

        logger.info("properties_bulk_upserted", count=len(properties))
        return len(properties)

    def get_active_properties(self, session: Session, limit: Optional[int] = None) -> List[Property]:
        """
        Get all active properties.

        Args:
            session: Database session
            limit: Maximum number of records

        Returns:
            List of active properties
        """
        query = select(Property).where(Property.is_active == True)
        if limit:
            query = query.limit(limit)

        return session.execute(query).scalars().all()

    def get_by_city(self, session: Session, city: str) -> List[Property]:
        """
        Get properties by city.

        Args:
            session: Database session
            city: City name

        Returns:
            List of properties
        """
        query = select(Property).where(Property.city == city.upper())
        return session.execute(query).scalars().all()

    def get_with_coordinates(self, session: Session) -> List[Property]:
        """
        Get properties that have coordinates.

        Args:
            session: Database session

        Returns:
            List of properties with coordinates
        """
        query = select(Property).where(
            and_(
                Property.latitude.isnot(None),
                Property.longitude.isnot(None)
            )
        )
        return session.execute(query).scalars().all()


class TaxSaleRepository(BaseRepository):
    """Repository for TaxSale model."""

    def __init__(self):
        super().__init__(TaxSale)

    def upsert_by_parcel(self, session: Session, tax_sale_data: Dict[str, Any]) -> TaxSale:
        """
        Insert or update tax sale by parcel ID.

        Args:
            session: Database session
            tax_sale_data: Tax sale field values

        Returns:
            TaxSale instance
        """
        parcel_id = tax_sale_data.get('parcel_id_normalized')
        if not parcel_id:
            raise ValueError("parcel_id_normalized is required")

        stmt = insert(TaxSale).values(**tax_sale_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['parcel_id_normalized'],
            set_={k: v for k, v in tax_sale_data.items() if k not in ['id', 'parcel_id_normalized']}
        )

        session.execute(stmt)
        session.flush()

        query = select(TaxSale).where(TaxSale.parcel_id_normalized == parcel_id)
        return session.execute(query).scalar_one()

    def get_by_sale_date_range(self, session: Session, start_date: date, end_date: date) -> List[TaxSale]:
        """
        Get tax sales within date range.

        Args:
            session: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of tax sales
        """
        query = select(TaxSale).where(
            and_(
                TaxSale.sale_date >= start_date,
                TaxSale.sale_date <= end_date
            )
        ).order_by(TaxSale.sale_date)

        return session.execute(query).scalars().all()

    def get_upcoming_sales(self, session: Session, days: int = 30) -> List[TaxSale]:
        """
        Get upcoming tax sales.

        Args:
            session: Database session
            days: Number of days to look ahead

        Returns:
            List of tax sales
        """
        from datetime import timedelta
        today = date.today()
        future_date = today + timedelta(days=days)

        return self.get_by_sale_date_range(session, today, future_date)


class ForeclosureRepository(BaseRepository):
    """Repository for Foreclosure model."""

    def __init__(self):
        super().__init__(Foreclosure)

    def upsert_by_parcel(self, session: Session, foreclosure_data: Dict[str, Any]) -> Foreclosure:
        """
        Insert or update foreclosure by parcel ID.

        Args:
            session: Database session
            foreclosure_data: Foreclosure field values

        Returns:
            Foreclosure instance
        """
        parcel_id = foreclosure_data.get('parcel_id_normalized')
        if not parcel_id:
            raise ValueError("parcel_id_normalized is required")

        stmt = insert(Foreclosure).values(**foreclosure_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['parcel_id_normalized'],
            set_={k: v for k, v in foreclosure_data.items() if k not in ['id', 'parcel_id_normalized']}
        )

        session.execute(stmt)
        session.flush()

        query = select(Foreclosure).where(Foreclosure.parcel_id_normalized == parcel_id)
        return session.execute(query).scalar_one()

    def get_by_default_amount_range(
        self,
        session: Session,
        min_amount: float,
        max_amount: float
    ) -> List[Foreclosure]:
        """
        Get foreclosures by default amount range.

        Args:
            session: Database session
            min_amount: Minimum default amount
            max_amount: Maximum default amount

        Returns:
            List of foreclosures
        """
        query = select(Foreclosure).where(
            and_(
                Foreclosure.default_amount >= min_amount,
                Foreclosure.default_amount <= max_amount
            )
        ).order_by(desc(Foreclosure.default_amount))

        return session.execute(query).scalars().all()

    def get_with_auction_date(self, session: Session) -> List[Foreclosure]:
        """
        Get foreclosures with scheduled auction dates.

        Args:
            session: Database session

        Returns:
            List of foreclosures
        """
        query = select(Foreclosure).where(
            Foreclosure.auction_date.isnot(None)
        ).order_by(Foreclosure.auction_date)

        return session.execute(query).scalars().all()


class PropertyRecordRepository(BaseRepository):
    """Repository for PropertyRecord model."""

    def __init__(self):
        super().__init__(PropertyRecord)

    def upsert_by_parcel(self, session: Session, property_record_data: Dict[str, Any]) -> PropertyRecord:
        """
        Insert or update property record by parcel ID.

        Args:
            session: Database session
            property_record_data: Property record field values

        Returns:
            PropertyRecord instance
        """
        parcel_id = property_record_data.get('parcel_id_normalized')
        if not parcel_id:
            raise ValueError("parcel_id_normalized is required")

        stmt = insert(PropertyRecord).values(**property_record_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['parcel_id_normalized'],
            set_={k: v for k, v in property_record_data.items() if k not in ['id', 'parcel_id_normalized']}
        )

        session.execute(stmt)
        session.flush()

        query = select(PropertyRecord).where(PropertyRecord.parcel_id_normalized == parcel_id)
        return session.execute(query).scalar_one()

    def get_by_market_value_range(
        self,
        session: Session,
        min_value: float,
        max_value: float
    ) -> List[PropertyRecord]:
        """
        Get property records by market value range.

        Args:
            session: Database session
            min_value: Minimum market value
            max_value: Maximum market value

        Returns:
            List of property records
        """
        query = select(PropertyRecord).where(
            and_(
                PropertyRecord.total_mkt >= min_value,
                PropertyRecord.total_mkt <= max_value
            )
        ).order_by(PropertyRecord.total_mkt)

        return session.execute(query).scalars().all()

    def get_high_equity_properties(
        self,
        session: Session,
        min_equity_percent: float = 150.0
    ) -> List[PropertyRecord]:
        """
        Get properties with high equity percentage.

        Args:
            session: Database session
            min_equity_percent: Minimum equity percentage

        Returns:
            List of property records
        """
        query = select(PropertyRecord).where(
            PropertyRecord.equity_percent >= min_equity_percent
        ).order_by(desc(PropertyRecord.equity_percent))

        return session.execute(query).scalars().all()


class LeadScoreRepository(BaseRepository):
    """Repository for LeadScore model with tier-based queries."""

    def __init__(self):
        super().__init__(LeadScore)

    def upsert_by_parcel(self, session: Session, lead_score_data: Dict[str, Any]) -> LeadScore:
        """
        Insert or update lead score by parcel ID.

        Args:
            session: Database session
            lead_score_data: Lead score field values

        Returns:
            LeadScore instance
        """
        parcel_id = lead_score_data.get('parcel_id_normalized')
        if not parcel_id:
            raise ValueError("parcel_id_normalized is required")

        stmt = insert(LeadScore).values(**lead_score_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['parcel_id_normalized'],
            set_={k: v for k, v in lead_score_data.items() if k not in ['id', 'parcel_id_normalized']}
        )

        session.execute(stmt)
        session.flush()

        query = select(LeadScore).where(LeadScore.parcel_id_normalized == parcel_id)
        return session.execute(query).scalar_one()

    def get_by_tier(self, session: Session, tier: str) -> List[LeadScore]:
        """
        Get lead scores by tier.

        Args:
            session: Database session
            tier: Lead tier (A, B, C, D)

        Returns:
            List of lead scores ordered by total_score DESC
        """
        query = select(LeadScore).where(
            LeadScore.tier == tier.upper()
        ).order_by(desc(LeadScore.total_score))

        return session.execute(query).scalars().all()

    def get_tier_a_leads(self, session: Session) -> List[LeadScore]:
        """
        Get Tier A leads (hot leads).

        Args:
            session: Database session

        Returns:
            List of Tier A lead scores
        """
        return self.get_by_tier(session, 'A')

    def get_by_score_range(
        self,
        session: Session,
        min_score: float,
        max_score: float
    ) -> List[LeadScore]:
        """
        Get lead scores within score range.

        Args:
            session: Database session
            min_score: Minimum total score
            max_score: Maximum total score

        Returns:
            List of lead scores
        """
        query = select(LeadScore).where(
            and_(
                LeadScore.total_score >= min_score,
                LeadScore.total_score <= max_score
            )
        ).order_by(desc(LeadScore.total_score))

        return session.execute(query).scalars().all()

    def get_top_n_leads(self, session: Session, n: int = 10) -> List[LeadScore]:
        """
        Get top N leads by score.

        Args:
            session: Database session
            n: Number of leads to return

        Returns:
            List of top N lead scores
        """
        query = select(LeadScore).order_by(
            desc(LeadScore.total_score)
        ).limit(n)

        return session.execute(query).scalars().all()

    def get_tier_counts(self, session: Session) -> Dict[str, int]:
        """
        Get count of leads by tier.

        Args:
            session: Database session

        Returns:
            Dictionary with tier counts
        """
        from sqlalchemy import case

        query = select(
            LeadScore.tier,
            func.count(LeadScore.id).label('count')
        ).group_by(LeadScore.tier)

        results = session.execute(query).all()

        counts = {tier: count for tier, count in results}
        logger.info("lead_tier_counts", counts=counts)
        return counts

    def create_history_snapshot(
        self,
        session: Session,
        lead_score_id: int,
        snapshot_date: Optional[date] = None
    ) -> LeadScoreHistory:
        """
        Create historical snapshot of lead score.

        Args:
            session: Database session
            lead_score_id: LeadScore ID
            snapshot_date: Date of snapshot (defaults to today)

        Returns:
            LeadScoreHistory instance
        """
        lead_score = self.get_by_id(session, lead_score_id)
        if not lead_score:
            raise ValueError(f"LeadScore {lead_score_id} not found")

        if snapshot_date is None:
            snapshot_date = date.today()

        history = LeadScoreHistory(
            lead_score_id=lead_score_id,
            parcel_id_normalized=lead_score.parcel_id_normalized,
            total_score=lead_score.total_score,
            tier=lead_score.tier,
            snapshot_date=snapshot_date
        )

        session.add(history)
        session.flush()

        logger.info(
            "lead_score_history_created",
            lead_score_id=lead_score_id,
            parcel_id=lead_score.parcel_id_normalized,
            snapshot_date=snapshot_date
        )

        return history


class DataIngestionRunRepository(BaseRepository):
    """Repository for DataIngestionRun model (ETL tracking)."""

    def __init__(self):
        super().__init__(DataIngestionRun)

    def create_run(
        self,
        session: Session,
        source_type: str,
        started_at: Optional[datetime] = None
    ) -> DataIngestionRun:
        """
        Create new ingestion run.

        Args:
            session: Database session
            source_type: Source type (tax_sales, foreclosures, etc.)
            started_at: Start timestamp (defaults to now)

        Returns:
            DataIngestionRun instance
        """
        if started_at is None:
            started_at = datetime.now()

        run = DataIngestionRun(
            source_type=source_type,
            status='running',
            started_at=started_at
        )

        session.add(run)
        session.flush()

        logger.info("ingestion_run_created", run_id=run.id, source_type=source_type)
        return run

    def complete_run(
        self,
        session: Session,
        run_id: int,
        status: str,
        records_processed: int = 0,
        records_inserted: int = 0,
        records_updated: int = 0,
        records_failed: int = 0,
        error_message: Optional[str] = None,
        error_details: Optional[Dict] = None
    ) -> DataIngestionRun:
        """
        Mark ingestion run as complete.

        Args:
            session: Database session
            run_id: Run ID
            status: Final status (success, failure, partial)
            records_processed: Total records processed
            records_inserted: Records inserted
            records_updated: Records updated
            records_failed: Records failed
            error_message: Error message if failed
            error_details: Structured error data

        Returns:
            Updated DataIngestionRun instance
        """
        run = self.get_by_id(session, run_id)
        if not run:
            raise ValueError(f"DataIngestionRun {run_id} not found")

        run.status = status
        run.records_processed = records_processed
        run.records_inserted = records_inserted
        run.records_updated = records_updated
        run.records_failed = records_failed
        run.error_message = error_message
        run.error_details = error_details
        run.completed_at = datetime.now()

        session.flush()

        logger.info(
            "ingestion_run_completed",
            run_id=run_id,
            status=status,
            processed=records_processed,
            inserted=records_inserted,
            updated=records_updated,
            failed=records_failed
        )

        return run

    def get_recent_runs(
        self,
        session: Session,
        source_type: Optional[str] = None,
        limit: int = 10
    ) -> List[DataIngestionRun]:
        """
        Get recent ingestion runs.

        Args:
            session: Database session
            source_type: Filter by source type (optional)
            limit: Maximum number of runs

        Returns:
            List of ingestion runs
        """
        query = select(DataIngestionRun).order_by(desc(DataIngestionRun.started_at))

        if source_type:
            query = query.where(DataIngestionRun.source_type == source_type)

        query = query.limit(limit)

        return session.execute(query).scalars().all()

    def get_failed_runs(self, session: Session, limit: int = 20) -> List[DataIngestionRun]:
        """
        Get failed ingestion runs.

        Args:
            session: Database session
            limit: Maximum number of runs

        Returns:
            List of failed runs
        """
        query = select(DataIngestionRun).where(
            DataIngestionRun.status == 'failure'
        ).order_by(desc(DataIngestionRun.started_at)).limit(limit)

        return session.execute(query).scalars().all()
