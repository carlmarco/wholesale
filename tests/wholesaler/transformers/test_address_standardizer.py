"""
Unit tests for address_standardizer module
"""
import pytest

import sys
sys.path.insert(0, '/Users/carlmarco/wholesaler')

from src.wholesaler.transformers.address_standardizer import AddressStandardizer, StandardizedAddress


class TestAddressStandardizer:
    """Tests for AddressStandardizer class"""

    def test_standardizer_initialization(self):
        """Test that standardizer initializes correctly"""
        standardizer = AddressStandardizer()
        assert standardizer is not None

    def test_standardize_simple_address(self):
        """Test standardizing a simple address"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize(
            "123 Main Street",
            city="Orlando",
            state="FL",
            zip_code="32801"
        )

        assert result.street_number == "123"
        assert result.street_name == "MAIN"
        assert result.street_type == "ST"
        assert result.city == "ORLANDO"
        assert result.state == "FL"
        assert result.zip_code == "32801"

    def test_standardize_with_direction(self):
        """Test standardizing address with directional"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize("456 North Oak Avenue")

        assert result.street_number == "456"
        assert "N" in result.street_name or "NORTH" in result.street_name
        assert "OAK" in result.street_name
        assert result.street_type == "AVE"

    def test_standardize_with_unit(self):
        """Test standardizing address with unit number"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize("789 Elm Street APT 4B")

        assert result.street_number == "789"
        assert result.street_name == "ELM"
        assert result.street_type == "ST"
        assert result.unit_type == "APT"
        assert result.unit_number == "4B"

    def test_standardize_with_hash_unit(self):
        """Test standardizing address with # unit notation"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize("100 Park Place # 205")

        assert result.street_number == "100"
        assert result.street_name == "PARK"
        assert result.street_type == "PL"
        assert result.unit_type == "UNIT"
        assert result.unit_number == "205"

    def test_standardize_boulevard(self):
        """Test standardizing boulevard abbreviation"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize("555 Sunset Boulevard")

        assert result.street_name == "SUNSET"
        assert result.street_type == "BLVD"

    def test_standardize_empty_address(self):
        """Test standardizing empty address"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize("")

        assert result.street_number is None
        assert result.street_name is None
        assert result.full_address is None

    def test_normalize_zip_code(self):
        """Test ZIP code normalization"""
        standardizer = AddressStandardizer()

        result1 = standardizer._normalize_zip("32801-1234")
        assert result1 == "32801"

        result2 = standardizer._normalize_zip("328011234")
        assert result2 == "32801"

        result3 = standardizer._normalize_zip("32801")
        assert result3 == "32801"

    def test_normalize_parcel_id(self):
        """Test parcel ID normalization"""
        standardizer = AddressStandardizer()

        result1 = standardizer.normalize_parcel_id("12-34-56-7890-12-345")
        assert result1 == "123456789012345"

        result2 = standardizer.normalize_parcel_id("123456789")
        assert result2 == "123456789"

        result3 = standardizer.normalize_parcel_id("29-22-28-8850-02-050")
        assert result3 == "292228885002050"

    def test_normalize_parcel_id_none(self):
        """Test parcel ID normalization with None"""
        standardizer = AddressStandardizer()

        result = standardizer.normalize_parcel_id(None)
        assert result is None

    def test_full_address_formatting(self):
        """Test full address string generation"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize(
            "1234 WEST COLONIAL DRIVE",
            city="Orlando",
            state="FL",
            zip_code="32804"
        )

        assert result.full_address is not None
        assert "1234" in result.full_address
        assert "W" in result.full_address or "WEST" in result.full_address
        assert "COLONIAL" in result.full_address
        assert "ORLANDO" in result.full_address
        assert "FL" in result.full_address
        assert "32804" in result.full_address

    def test_street_type_normalization(self):
        """Test various street type normalizations"""
        standardizer = AddressStandardizer()

        test_cases = [
            ("123 Oak Lane", "LN"),
            ("456 Pine Court", "CT"),
            ("789 Maple Drive", "DR"),
            ("100 Elm Circle", "CIR"),
            ("200 Cedar Terrace", "TER"),
        ]

        for address, expected_type in test_cases:
            result = standardizer.standardize(address)
            assert result.street_type == expected_type

    def test_complex_address_with_all_components(self):
        """Test complex address with all components"""
        standardizer = AddressStandardizer()

        result = standardizer.standardize(
            "9876 SOUTH ORANGE BLOSSOM TRAIL UNIT 305",
            city="Orlando",
            state="Florida",
            zip_code="32837-5678"
        )

        assert result.street_number == "9876"
        assert "S" in result.street_name or "SOUTH" in result.street_name
        assert "ORANGE" in result.street_name
        assert "BLOSSOM" in result.street_name
        assert result.street_type == "TRL"
        assert result.unit_type == "UNIT"
        assert result.unit_number == "305"
        assert result.city == "ORLANDO"
        assert result.state == "FLORIDA"
        assert result.zip_code == "32837"

    def test_case_insensitivity(self):
        """Test that standardization is case-insensitive"""
        standardizer = AddressStandardizer()

        result1 = standardizer.standardize("123 main street")
        result2 = standardizer.standardize("123 MAIN STREET")
        result3 = standardizer.standardize("123 Main Street")

        assert result1.street_name == result2.street_name == result3.street_name
        assert result1.street_type == result2.street_type == result3.street_type
