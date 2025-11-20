"""
Tests for Repository Pattern

Tests CRUD operations, upsert logic, bulk operations, and domain-specific queries.
"""
import pytest
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.wholesaler.db.base import Base
from src.wholesaler.db.models import Property, TaxSale, LeadScore, DataIngestionRun
from src.wholesaler.db.repository import (
    PropertyRepository,
    TaxSaleRepository,
    LeadScoreRepository,
    DataIngestionRunRepository,
)


@pytest.fixture(scope="function")
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


class TestPropertyRepository:
    """Tests for PropertyRepository."""

    def test_create_property(self, test_db):
        """Test creating a property via repository."""
        repo = PropertyRepository()

        property_obj = repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
            city="Orlando",
            state="FL",
        )

        test_db.commit()

        assert property_obj.parcel_id_normalized == "12-34-56-7890-01-001"
        assert property_obj.situs_address == "123 Main St"

    def test_get_by_parcel(self, test_db):
        """Test retrieving property by parcel ID."""
        repo = PropertyRepository()

        # Create property
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
        )
        test_db.commit()

        # Retrieve property
        found = repo.get_by_parcel(test_db, "12-34-56-7890-01-001")

        assert found is not None
        assert found.situs_address == "123 Main St"

    def test_upsert_insert(self, test_db):
        """Test upsert operation (insert)."""
        repo = PropertyRepository()

        property_data = {
            "parcel_id_normalized": "12-34-56-7890-01-001",
            "situs_address": "123 Main St",
            "city": "Orlando",
        }

        property_obj = repo.upsert(test_db, property_data)

        assert property_obj is not None
        assert property_obj.situs_address == "123 Main St"
        assert property_obj.city == "Orlando"

    def test_upsert_update(self, test_db):
        """Test upsert operation (update existing)."""
        repo = PropertyRepository()

        # Insert
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
            city="Orlando",
        )
        test_db.commit()

        # Upsert with updated data
        property_data = {
            "parcel_id_normalized": "12-34-56-7890-01-001",
            "situs_address": "123 Main St",
            "city": "Winter Park",  # Updated city
            "zip_code": "32789",
        }

        property_obj = repo.upsert(test_db, property_data)

        assert property_obj.city == "Winter Park"
        assert property_obj.zip_code == "32789"

    def test_get_active_properties(self, test_db):
        """Test retrieving only active properties."""
        repo = PropertyRepository()

        # Create active property
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
            is_active=True,
        )

        # Create inactive property
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-002",
            parcel_id_original="12 34 56 7890 01 002",
            situs_address="456 Oak Ave",
            is_active=False,
        )

        test_db.commit()

        active = repo.get_active_properties(test_db)

        assert len(active) == 1
        assert active[0].parcel_id_normalized == "12-34-56-7890-01-001"

    def test_get_with_coordinates(self, test_db):
        """Test retrieving properties with coordinates."""
        repo = PropertyRepository()

        # Create property with coordinates
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
            latitude=28.5383,
            longitude=-81.3792,
        )

        # Create property without coordinates
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-002",
            parcel_id_original="12 34 56 7890 01 002",
            situs_address="456 Oak Ave",
        )

        test_db.commit()

        with_coords = repo.get_with_coordinates(test_db)

        assert len(with_coords) == 1
        assert with_coords[0].latitude == 28.5383

    def test_soft_delete(self, test_db):
        """Test soft delete operation."""
        repo = PropertyRepository()

        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
        )
        test_db.commit()

        # Soft delete
        repo.soft_delete(test_db, "12-34-56-7890-01-001")
        test_db.commit()

        # Property still exists but is_active = False
        property_obj = repo.get_by_parcel(test_db, "12-34-56-7890-01-001")
        assert property_obj is not None
        assert property_obj.is_active is False


class TestTaxSaleRepository:
    """Tests for TaxSaleRepository."""

    def test_upsert_by_parcel(self, test_db):
        """Test upserting tax sale by parcel ID."""
        # Create parent property first
        property_repo = PropertyRepository()
        property_repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
        )
        test_db.commit()

        # Upsert tax sale
        repo = TaxSaleRepository()
        tax_sale_data = {
            "parcel_id_normalized": "12-34-56-7890-01-001",
            "tda_number": "2024-001",
            "sale_date": date(2024, 3, 15),
        }

        tax_sale = repo.upsert_by_parcel(test_db, tax_sale_data)

        assert tax_sale.tda_number == "2024-001"
        assert tax_sale.sale_date == date(2024, 3, 15)

    def test_get_by_sale_date_range(self, test_db):
        """Test retrieving tax sales within date range."""
        # Create parent property
        property_repo = PropertyRepository()
        property_repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
        )
        test_db.commit()

        # Create tax sales
        repo = TaxSaleRepository()
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            tda_number="2024-001",
            sale_date=date(2024, 3, 15),
        )
        test_db.commit()

        # Query by date range
        sales = repo.get_by_sale_date_range(
            test_db,
            start_date=date(2024, 3, 1),
            end_date=date(2024, 3, 31),
        )

        assert len(sales) == 1
        assert sales[0].tda_number == "2024-001"


class TestLeadScoreRepository:
    """Tests for LeadScoreRepository."""

    def test_get_by_tier(self, test_db):
        """Test retrieving leads by tier."""
        # Create parent properties
        property_repo = PropertyRepository()
        property_repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
        )
        property_repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-002",
            parcel_id_original="12 34 56 7890 01 002",
            situs_address="456 Oak Ave",
        )
        test_db.commit()

        # Create lead scores
        repo = LeadScoreRepository()
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            total_score=85.0,
            tier="A",
        )
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-002",
            total_score=65.0,
            tier="B",
        )
        test_db.commit()

        # Get Tier A leads
        tier_a = repo.get_by_tier(test_db, "A")

        assert len(tier_a) == 1
        assert tier_a[0].tier == "A"
        assert tier_a[0].total_score == 85.0

    def test_get_tier_a_leads(self, test_db):
        """Test get_tier_a_leads convenience method."""
        # Create parent property
        property_repo = PropertyRepository()
        property_repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            parcel_id_original="12 34 56 7890 01 001",
            situs_address="123 Main St",
        )
        test_db.commit()

        # Create Tier A lead
        repo = LeadScoreRepository()
        repo.create(
            test_db,
            parcel_id_normalized="12-34-56-7890-01-001",
            total_score=90.0,
            tier="A",
        )
        test_db.commit()

        # Get Tier A leads
        tier_a = repo.get_tier_a_leads(test_db)

        assert len(tier_a) == 1
        assert tier_a[0].total_score == 90.0

    def test_get_tier_counts(self, test_db):
        """Test counting leads by tier."""
        # Create parent properties
        property_repo = PropertyRepository()
        for i in range(1, 6):
            property_repo.create(
                test_db,
                parcel_id_normalized=f"12-34-56-7890-01-00{i}",
                parcel_id_original=f"12 34 56 7890 01 00{i}",
                situs_address=f"{i*100} Main St",
            )
        test_db.commit()

        # Create lead scores with different tiers
        repo = LeadScoreRepository()
        repo.create(test_db, parcel_id_normalized="12-34-56-7890-01-001", total_score=90.0, tier="A")
        repo.create(test_db, parcel_id_normalized="12-34-56-7890-01-002", total_score=85.0, tier="A")
        repo.create(test_db, parcel_id_normalized="12-34-56-7890-01-003", total_score=70.0, tier="B")
        repo.create(test_db, parcel_id_normalized="12-34-56-7890-01-004", total_score=55.0, tier="C")
        repo.create(test_db, parcel_id_normalized="12-34-56-7890-01-005", total_score=40.0, tier="D")
        test_db.commit()

        # Get tier counts
        counts = repo.get_tier_counts(test_db)

        assert counts["A"] == 2
        assert counts["B"] == 1
        assert counts["C"] == 1
        assert counts["D"] == 1

    def test_get_top_n_leads(self, test_db):
        """Test retrieving top N leads by score."""
        # Create parent properties
        property_repo = PropertyRepository()
        for i in range(1, 6):
            property_repo.create(
                test_db,
                parcel_id_normalized=f"12-34-56-7890-01-00{i}",
                parcel_id_original=f"12 34 56 7890 01 00{i}",
                situs_address=f"{i*100} Main St",
            )
        test_db.commit()

        # Create lead scores
        repo = LeadScoreRepository()
        scores = [90.0, 85.0, 75.0, 60.0, 45.0]
        for i, score in enumerate(scores, 1):
            repo.create(
                test_db,
                parcel_id_normalized=f"12-34-56-7890-01-00{i}",
                total_score=score,
                tier="A" if score >= 80 else "B",
            )
        test_db.commit()

        # Get top 3 leads
        top_3 = repo.get_top_n_leads(test_db, n=3)

        assert len(top_3) == 3
        assert top_3[0].total_score == 90.0
        assert top_3[1].total_score == 85.0
        assert top_3[2].total_score == 75.0


class TestDataIngestionRunRepository:
    """Tests for DataIngestionRunRepository."""

    def test_create_run(self, test_db):
        """Test creating a new ETL run."""
        repo = DataIngestionRunRepository()

        run = repo.create_run(test_db, source_type="tax_sales")
        test_db.commit()

        assert run.source_type == "tax_sales"
        assert run.status == "running"
        assert run.started_at is not None

    def test_complete_run(self, test_db):
        """Test completing an ETL run with stats."""
        repo = DataIngestionRunRepository()

        # Create run
        run = repo.create_run(test_db, source_type="tax_sales")
        test_db.commit()

        run_id = run.id

        # Complete run
        completed = repo.complete_run(
            test_db,
            run_id=run_id,
            status="success",
            records_processed=100,
            records_inserted=85,
            records_updated=15,
            records_failed=0,
        )

        assert completed.status == "success"
        assert completed.records_processed == 100
        assert completed.completed_at is not None

    def test_get_recent_runs(self, test_db):
        """Test retrieving recent ETL runs."""
        repo = DataIngestionRunRepository()

        # Create multiple runs
        for i in range(5):
            run = repo.create_run(test_db, source_type="tax_sales")
            repo.complete_run(
                test_db,
                run_id=run.id,
                status="success",
                records_processed=100,
            )
        test_db.commit()

        # Get recent runs
        recent = repo.get_recent_runs(test_db, source_type="tax_sales", limit=3)

        assert len(recent) == 3
        assert recent[0].source_type == "tax_sales"

    def test_get_failed_runs(self, test_db):
        """Test retrieving failed ETL runs."""
        repo = DataIngestionRunRepository()

        # Create successful run
        success_run = repo.create_run(test_db, source_type="tax_sales")
        repo.complete_run(
            test_db,
            run_id=success_run.id,
            status="success",
            records_processed=100,
        )

        # Create failed run
        failed_run = repo.create_run(test_db, source_type="foreclosures")
        repo.complete_run(
            test_db,
            run_id=failed_run.id,
            status="failure",
            records_processed=50,
            records_failed=50,
            error_message="API timeout",
        )
        test_db.commit()

        # Get failed runs
        failed = repo.get_failed_runs(test_db)

        assert len(failed) == 1
        assert failed[0].status == "failure"
        assert failed[0].error_message == "API timeout"
