"""
Unit Tests for SeedMerger Logic

Tests the business logic of SeedMerger without requiring database.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.wholesaler.etl.seed_merger import SeedMerger


class TestSeedMergerLogic:
    """Unit tests for SeedMerger business logic."""

    def test_build_property_data_from_seed(self):
        """Test building property data dict from enriched seed."""
        merger = SeedMerger()

        # Create mock seed
        mock_seed = Mock()
        mock_seed.parcel_id_normalized = '1234567890'
        mock_seed.seed_type = 'tax_sale'

        enriched_data = {
            'parcel_id': '1234567890',
            'situs_address': '123 Main St',
            'city': 'Orlando',
            'state': 'FL',
            'zip_code': '32801',
            'latitude': 28.5383,
            'longitude': -81.3792,
        }

        result = merger._build_property_data_from_seed(mock_seed, enriched_data)

        assert result['parcel_id_normalized'] == '1234567890'
        assert result['seed_type'] == 'tax_sale'
        assert result['situs_address'] == '123 Main St'
        assert result['city'] == 'Orlando'
        assert result['latitude'] == 28.5383
        assert result['is_active'] is True

    def test_build_property_data_minimal(self):
        """Test building property data with minimal enriched_data."""
        merger = SeedMerger()

        mock_seed = Mock()
        mock_seed.parcel_id_normalized = '1234567890'
        mock_seed.seed_type = 'code_violation'

        enriched_data = {'parcel_id': '1234567890'}

        result = merger._build_property_data_from_seed(mock_seed, enriched_data)

        assert result['parcel_id_normalized'] == '1234567890'
        assert result['seed_type'] == 'code_violation'
        assert result['is_active'] is True

    def test_update_property_from_seed_new_seed_type(self):
        """Test updating property adds new seed_type."""
        merger = SeedMerger()

        # Create mock property with existing seed_type
        mock_prop = Mock()
        mock_prop.seed_type = 'tax_sale'
        mock_prop.latitude = 28.5383
        mock_prop.longitude = -81.3792
        mock_prop.situs_address = '123 Main St'
        mock_prop.city = 'Orlando'
        mock_prop.zip_code = '32801'

        # Create mock seed with different type
        mock_seed = Mock()
        mock_seed.seed_type = 'code_violation'
        mock_seed.parcel_id_normalized = '1234567890'

        enriched_data = {
            'parcel_id': '1234567890',
            'latitude': 28.5383,
            'longitude': -81.3792,
        }

        merger._update_property_from_seed(mock_prop, mock_seed, enriched_data)

        # Should merge seed types
        assert 'code_violation' in mock_prop.seed_type
        assert 'tax_sale' in mock_prop.seed_type

    def test_update_property_from_seed_duplicate_type(self):
        """Test updating property doesn't duplicate existing seed_type."""
        merger = SeedMerger()

        mock_prop = Mock()
        mock_prop.seed_type = 'tax_sale'
        mock_prop.latitude = None
        mock_prop.longitude = None

        mock_seed = Mock()
        mock_seed.seed_type = 'tax_sale'  # Same type
        mock_seed.parcel_id_normalized = '1234567890'

        enriched_data = {}

        merger._update_property_from_seed(mock_prop, mock_seed, enriched_data)

        # Should not duplicate
        assert mock_prop.seed_type == 'tax_sale'

    def test_update_property_fills_missing_coordinates(self):
        """Test that missing coordinates are filled from seed."""
        merger = SeedMerger()

        mock_prop = Mock()
        mock_prop.seed_type = None
        mock_prop.latitude = None  # Missing
        mock_prop.longitude = None  # Missing
        mock_prop.situs_address = None
        mock_prop.city = None
        mock_prop.zip_code = None

        mock_seed = Mock()
        mock_seed.seed_type = 'tax_sale'

        enriched_data = {
            'latitude': 28.5383,
            'longitude': -81.3792,
            'situs_address': '123 Main St',
        }

        merger._update_property_from_seed(mock_prop, mock_seed, enriched_data)

        # Should fill missing values
        assert mock_prop.latitude == 28.5383
        assert mock_prop.longitude == -81.3792
        assert mock_prop.situs_address == '123 Main St'

    def test_update_property_preserves_existing_coordinates(self):
        """Test that existing coordinates are not overwritten."""
        merger = SeedMerger()

        mock_prop = Mock()
        mock_prop.seed_type = None
        mock_prop.latitude = 28.0000  # Existing value
        mock_prop.longitude = -81.0000  # Existing value
        mock_prop.situs_address = 'Old Address'  # Existing
        mock_prop.city = None
        mock_prop.zip_code = None

        mock_seed = Mock()
        mock_seed.seed_type = 'tax_sale'

        enriched_data = {
            'latitude': 28.5383,  # Different value
            'longitude': -81.3792,  # Different value
            'situs_address': 'New Address',  # Different value
        }

        merger._update_property_from_seed(mock_prop, mock_seed, enriched_data)

        # Should NOT overwrite existing values
        assert mock_prop.latitude == 28.0000
        assert mock_prop.longitude == -81.0000
        assert mock_prop.situs_address == 'Old Address'


@pytest.mark.unit
class TestSeedMergerInit:
    """Test SeedMerger initialization."""

    def test_init(self):
        """Test SeedMerger initializes correctly."""
        merger = SeedMerger()

        assert merger.seed_repo is not None
        assert merger.property_repo is not None
        assert merger.standardizer is not None
