"""
Tests for Seed-Based Ingestion Components

Tests EnrichedSeedRepository, EnrichedSeedLoader, and SeedMerger.
"""
import sys
from pathlib import Path
import pytest
from datetime import datetime, date
import tempfile
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.db.base import Base
from src.wholesaler.db.models import EnrichedSeed, Property
from src.wholesaler.db.repository import EnrichedSeedRepository, PropertyRepository
from src.wholesaler.etl.loaders import EnrichedSeedLoader
from src.wholesaler.etl.seed_merger import SeedMerger


@pytest.fixture(scope="function")
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_enriched_data():
    """Create sample enriched data dict."""
    return {
        'parcel_id': '1234567890',
        'seed_type': 'tax_sale',
        'tda_number': '2024-001',
        'sale_date': '2024-03-15',
        'deed_status': 'Not Issued',
        'latitude': 28.5383,
        'longitude': -81.3792,
        'situs_address': '123 Main St',
        'city': 'Orlando',
        'zip_code': '32801',
        'total_mkt': 250000,
        'total_assd': 245000,
        'equity_percent': 150.0,
        'violation_count': 3,
        'most_recent_violation': '2024-01-15',
        'nearby_violations': 3,
    }


class TestEnrichedSeedRepository:
    """Tests for EnrichedSeedRepository."""

    def test_upsert_new_seed(self, test_db, sample_enriched_data):
        """Test upserting a new enriched seed."""
        repo = EnrichedSeedRepository()

        seed = repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
            enriched_data=sample_enriched_data
        )

        test_db.commit()

        assert seed.parcel_id_normalized == '1234567890'
        assert seed.seed_type == 'tax_sale'
        assert seed.violation_count == 3
        assert seed.enriched_data is not None
        assert not seed.processed

    def test_upsert_duplicate_seed(self, test_db, sample_enriched_data):
        """Test upserting duplicate seed updates existing record."""
        repo = EnrichedSeedRepository()

        # Insert first seed
        seed1 = repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
            enriched_data=sample_enriched_data
        )
        test_db.commit()

        # Update with new data
        updated_data = sample_enriched_data.copy()
        updated_data['violation_count'] = 5

        seed2 = repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
            enriched_data=updated_data
        )
        test_db.commit()

        # Should update, not create new
        assert seed2.violation_count == 5
        total_seeds = test_db.query(EnrichedSeed).count()
        assert total_seeds == 1

    def test_get_unprocessed(self, test_db, sample_enriched_data):
        """Test getting unprocessed seeds."""
        repo = EnrichedSeedRepository()

        # Create processed and unprocessed seeds
        seed1 = repo.upsert(
            test_db,
            parcel_id_normalized='1111111111',
            seed_type='tax_sale',
            enriched_data=sample_enriched_data
        )
        seed1.processed = True

        seed2 = repo.upsert(
            test_db,
            parcel_id_normalized='2222222222',
            seed_type='code_violation',
            enriched_data=sample_enriched_data
        )

        test_db.commit()

        # Get unprocessed
        unprocessed = repo.get_unprocessed(test_db)
        assert len(unprocessed) == 1
        assert unprocessed[0].parcel_id_normalized == '2222222222'

    def test_mark_processed(self, test_db, sample_enriched_data):
        """Test marking seed as processed."""
        repo = EnrichedSeedRepository()

        seed = repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
            enriched_data=sample_enriched_data
        )
        test_db.commit()

        # Mark as processed
        updated_seed = repo.mark_processed(test_db, seed.id)
        test_db.commit()

        assert updated_seed.processed is True
        assert updated_seed.processed_at is not None

    def test_get_by_seed_type(self, test_db, sample_enriched_data):
        """Test filtering seeds by type."""
        repo = EnrichedSeedRepository()

        # Create seeds of different types
        repo.upsert(test_db, '1111111111', 'tax_sale', sample_enriched_data)
        repo.upsert(test_db, '2222222222', 'code_violation', sample_enriched_data)
        repo.upsert(test_db, '3333333333', 'tax_sale', sample_enriched_data)
        test_db.commit()

        # Get tax_sale seeds
        tax_sales = repo.get_by_seed_type(test_db, 'tax_sale')
        assert len(tax_sales) == 2

    def test_get_stats(self, test_db, sample_enriched_data):
        """Test getting repository statistics."""
        repo = EnrichedSeedRepository()

        # Create seeds
        seed1 = repo.upsert(test_db, '1111111111', 'tax_sale', sample_enriched_data)
        repo.upsert(test_db, '2222222222', 'code_violation', sample_enriched_data)
        seed1.processed = True
        test_db.commit()

        stats = repo.get_stats(test_db)

        assert stats['total'] == 2
        assert stats['processed'] == 1
        assert stats['unprocessed'] == 1
        assert stats['by_type']['tax_sale'] == 1
        assert stats['by_type']['code_violation'] == 1


class TestEnrichedSeedLoader:
    """Tests for EnrichedSeedLoader."""

    def test_load_from_parquet(self, test_db, sample_enriched_data):
        """Test loading seeds from parquet file."""
        # Create temporary parquet file
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            df = pd.DataFrame([
                {
                    'parcel_id': '1234567890',
                    'seed_type': 'tax_sale',
                    'tda_number': '2024-001',
                    'latitude': 28.5383,
                    'longitude': -81.3792,
                    'violation_count': 3,
                },
                {
                    'parcel_id': '9876543210',
                    'seed_type': 'code_violation',
                    'latitude': 28.5400,
                    'longitude': -81.3800,
                    'violation_count': 5,
                }
            ])
            df.to_parquet(tmp.name)
            parquet_path = tmp.name

        try:
            loader = EnrichedSeedLoader()
            stats = loader.load_from_parquet(test_db, parquet_path, track_run=False)

            assert stats['processed'] == 2
            assert stats['failed'] == 0

            # Verify seeds in database
            repo = EnrichedSeedRepository()
            seeds = repo.get_by_seed_type(test_db, 'tax_sale')
            assert len(seeds) == 1

        finally:
            Path(parquet_path).unlink()

    def test_load_missing_file(self, test_db):
        """Test loading from non-existent file raises error."""
        loader = EnrichedSeedLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_from_parquet(test_db, '/nonexistent/file.parquet', track_run=False)

    def test_load_invalid_data(self, test_db):
        """Test loading with missing required fields."""
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            df = pd.DataFrame([
                {
                    'parcel_id': '1234567890',
                    # Missing seed_type
                    'latitude': 28.5383,
                }
            ])
            df.to_parquet(tmp.name)
            parquet_path = tmp.name

        try:
            loader = EnrichedSeedLoader()
            stats = loader.load_from_parquet(test_db, parquet_path, track_run=False)

            # Should fail gracefully
            assert stats['failed'] == 1
            assert stats['processed'] == 0

        finally:
            Path(parquet_path).unlink()


class TestSeedMerger:
    """Tests for SeedMerger."""

    def test_merge_new_property(self, test_db, sample_enriched_data):
        """Test merging seed creates new property."""
        # Create enriched seed
        seed_repo = EnrichedSeedRepository()
        seed = seed_repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
            enriched_data=sample_enriched_data
        )
        test_db.commit()

        # Merge seeds
        merger = SeedMerger()
        stats = merger.merge_seeds(test_db, track_run=False)

        assert stats['processed'] == 1
        assert stats['created'] == 1
        assert stats['updated'] == 0

        # Verify property created
        prop_repo = PropertyRepository()
        prop = prop_repo.get_by_parcel_id(test_db, '1234567890')
        assert prop is not None
        assert prop.seed_type == 'tax_sale'
        assert prop.situs_address == '123 Main St'

        # Verify seed marked as processed
        test_db.refresh(seed)
        assert seed.processed is True

    def test_merge_existing_property(self, test_db, sample_enriched_data):
        """Test merging seed updates existing property."""
        # Create existing property
        prop_repo = PropertyRepository()
        existing_prop = prop_repo.create(
            test_db,
            parcel_id_normalized='1234567890',
            situs_address='Old Address',
        )
        test_db.commit()

        # Create enriched seed
        seed_repo = EnrichedSeedRepository()
        seed = seed_repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
            enriched_data=sample_enriched_data
        )
        test_db.commit()

        # Merge seeds
        merger = SeedMerger()
        stats = merger.merge_seeds(test_db, track_run=False)

        assert stats['processed'] == 1
        assert stats['created'] == 0
        assert stats['updated'] == 1

        # Verify property updated
        test_db.refresh(existing_prop)
        assert existing_prop.seed_type == 'tax_sale'
        assert existing_prop.situs_address == 'Old Address'  # Doesn't overwrite existing

    def test_merge_multi_source_seed(self, test_db, sample_enriched_data):
        """Test merging multiple seed types for same parcel."""
        # Create property with tax_sale seed
        prop_repo = PropertyRepository()
        prop = prop_repo.create(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='tax_sale',
        )
        test_db.commit()

        # Create code_violation seed for same parcel
        seed_repo = EnrichedSeedRepository()
        violation_data = sample_enriched_data.copy()
        violation_data['seed_type'] = 'code_violation'
        seed = seed_repo.upsert(
            test_db,
            parcel_id_normalized='1234567890',
            seed_type='code_violation',
            enriched_data=violation_data
        )
        test_db.commit()

        # Merge seeds
        merger = SeedMerger()
        stats = merger.merge_seeds(test_db, track_run=False)

        # Verify seed types merged
        test_db.refresh(prop)
        assert 'code_violation' in prop.seed_type
        assert 'tax_sale' in prop.seed_type

    def test_get_merge_stats(self, test_db, sample_enriched_data):
        """Test getting merge statistics."""
        # Create some seeds
        seed_repo = EnrichedSeedRepository()
        seed_repo.upsert(test_db, '1111111111', 'tax_sale', sample_enriched_data)
        seed_repo.upsert(test_db, '2222222222', 'code_violation', sample_enriched_data)
        test_db.commit()

        merger = SeedMerger()
        stats = merger.get_merge_stats(test_db)

        assert stats['seeds']['total'] == 2
        assert stats['seeds']['unprocessed'] == 2
