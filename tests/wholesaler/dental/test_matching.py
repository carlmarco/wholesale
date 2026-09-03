"""
Tests for licensee-to-parcel matching.

This join is the whole product: a dentist's practice address written one way,
a parcel's situs address written another. If the normalisation is too strict the
universe looks tiny and the conclusion is wrong; too loose and unrelated
buildings merge. These pin both edges.
"""
from datetime import date

import pytest

from src.wholesaler.dental.matching import (
    address_match_key,
    index_by_address,
    looks_like_dental_entity,
    match_licensees_to_parcels,
    normalize_entity_name,
    normalize_street,
    normalize_zip,
    owner_matches_dentist,
)
from src.wholesaler.dental.sources import DentalParcel, DentistLicense


def licensee(street="1234 N ORANGE AVE", zip_code="32801", last="NGUYEN", licensed="1990-06-01"):
    return DentistLicense(
        license_number="DN1234",
        last_name=last,
        full_name=f"ANH {last}",
        license_date=date.fromisoformat(licensed) if licensed else None,
        status="ACTIVE",
        practice_street=street,
        practice_city="ORLANDO",
        practice_zip=zip_code,
    )


def parcel(street="1234 N ORANGE AVE", zip_code="32801", owner="NGUYEN ANH", pid="123456789"):
    return DentalParcel(
        parcel_id_normalized=pid,
        parcel_id_original=pid,
        dor_use_code="0019",
        owner_name=owner,
        site_street=street,
        site_city="ORLANDO",
        site_zip=zip_code,
    )


class TestStreetNormalisation:
    @pytest.mark.parametrize(
        "written",
        [
            "1234 North Orange Avenue",
            "1234 N. Orange Ave.",
            "1234 N ORANGE AVE",
            "1234  n   orange   avenue ",
        ],
    )
    def test_spellings_of_one_address_agree(self, written):
        assert normalize_street(written) == "1234 N ORANGE AVE"

    @pytest.mark.parametrize(
        "written",
        [
            "1234 N Orange Ave Suite 200",
            "1234 N Orange Ave STE 200",
            "1234 N Orange Ave #200",
            "1234 N Orange Ave Unit B",
            "1234 N Orange Ave Bldg 3",
            "1234 N Orange Ave, Floor 2",
        ],
    )
    def test_the_unit_is_stripped(self, written):
        """The dentist occupies a suite; the parcel is the whole building."""
        assert normalize_street(written) == "1234 N ORANGE AVE"

    def test_different_buildings_stay_different(self):
        assert normalize_street("1234 N Orange Ave") != normalize_street("1236 N Orange Ave")
        assert normalize_street("1234 N Orange Ave") != normalize_street("1234 S Orange Ave")

    def test_street_type_matters(self):
        assert normalize_street("100 Park Ave") != normalize_street("100 Park St")

    def test_empty_input_yields_nothing(self):
        assert normalize_street("") == ""
        assert normalize_street("   ") == ""


class TestZipNormalisation:
    def test_zip_plus_four_reduces_to_five(self):
        assert normalize_zip("32801-1234") == "32801"

    def test_five_digits_pass_through(self):
        assert normalize_zip("32801") == "32801"

    def test_short_or_missing_zips_are_unusable(self):
        assert normalize_zip("328") == ""
        assert normalize_zip(None) == ""


class TestMatchKey:
    def test_key_combines_street_and_zip(self):
        assert address_match_key("1234 N Orange Ave Ste 5", "32801-9999") == "1234 N ORANGE AVE|32801"

    def test_same_street_in_different_cities_does_not_collide(self):
        """Statewide, matching on street alone would merge unrelated buildings."""
        assert address_match_key("100 Main St", "32801") != address_match_key("100 Main St", "33101")

    def test_a_half_key_is_refused(self):
        assert address_match_key("1234 N Orange Ave", "") is None
        assert address_match_key("", "32801") is None


class TestOwnerIdentification:
    @pytest.mark.parametrize(
        "owner",
        [
            "ORLANDO FAMILY DENTAL LLC",
            "SMITH DDS PA",
            "BAYSIDE ORTHODONTICS INC",
            "CENTRAL FL ORAL SURGERY",
            "PEDIATRIC DENTISTRY OF WINTER PARK",
        ],
    )
    def test_dental_entities_are_recognised(self, owner):
        assert looks_like_dental_entity(owner) is True

    @pytest.mark.parametrize(
        "owner",
        ["ORANGE AVE HOLDINGS LLC", "SUNBELT PROPERTIES INC", "CITY OF ORLANDO"],
    )
    def test_landlords_are_not(self, owner):
        assert looks_like_dental_entity(owner) is False

    def test_a_surname_in_the_owner_name_counts_as_owner_occupied(self):
        assert owner_matches_dentist("NGUYEN ANH T", "NGUYEN") is True

    def test_a_practice_entity_counts_even_without_the_surname(self):
        assert owner_matches_dentist("LAKESIDE DENTAL LLC", "NGUYEN") is True

    def test_an_unrelated_landlord_does_not(self):
        assert owner_matches_dentist("ORANGE AVE HOLDINGS LLC", "NGUYEN") is False

    def test_entity_boilerplate_is_ignored_when_comparing(self):
        assert normalize_entity_name("NGUYEN FAMILY TRUST LLC") == "NGUYEN"

    def test_a_partial_surname_does_not_match(self):
        """'NGUY' inside 'NGUYEN' must not count, or half the roll matches."""
        assert owner_matches_dentist("NGUYEN ANH", "NGUY") is False

    def test_missing_inputs_are_safe(self):
        assert owner_matches_dentist("", "NGUYEN") is False
        assert owner_matches_dentist("NGUYEN ANH", "") is False


class TestIndexing:
    def test_records_without_a_usable_key_are_dropped(self):
        index = index_by_address(
            [licensee(zip_code="32801"), licensee(zip_code="")],
            "practice_street",
            "practice_zip",
        )
        assert sum(len(v) for v in index.values()) == 1

    def test_records_sharing_an_address_group_together(self):
        index = index_by_address(
            [licensee(street="1 Main St"), licensee(street="1 Main Street Suite 3")],
            "practice_street",
            "practice_zip",
        )
        assert len(index) == 1
        assert len(next(iter(index.values()))) == 2


class TestMatching:
    def test_a_dentist_finds_their_building_through_a_suite_address(self):
        matches = match_licensees_to_parcels(
            [licensee(street="1234 N Orange Ave Suite 200")],
            [parcel(street="1234 N ORANGE AVE")],
        )
        assert len(matches) == 1
        assert matches[0].practitioner_count == 1

    def test_owner_occupancy_is_detected(self):
        matches = match_licensees_to_parcels(
            [licensee(last="NGUYEN")], [parcel(owner="NGUYEN ANH T")]
        )
        assert matches[0].owner_occupied is True

    def test_a_third_party_landlord_is_flagged_as_not_owner_occupied(self):
        matches = match_licensees_to_parcels(
            [licensee(last="NGUYEN")], [parcel(owner="ORANGE AVE HOLDINGS LLC")]
        )
        assert matches[0].owner_occupied is False

    def test_several_dentists_at_one_address_are_one_building(self):
        """Not a collision - a multi-practitioner building is a real thing."""
        matches = match_licensees_to_parcels(
            [
                licensee(last="NGUYEN", street="1234 N Orange Ave Ste 100"),
                licensee(last="PATEL", street="1234 N Orange Ave Ste 200"),
                licensee(last="OKAFOR", street="1234 N ORANGE AVENUE"),
            ],
            [parcel()],
        )
        assert len(matches) == 1
        assert matches[0].practitioner_count == 3

    def test_owner_occupancy_holds_if_any_practitioner_owns(self):
        matches = match_licensees_to_parcels(
            [licensee(last="PATEL"), licensee(last="NGUYEN")],
            [parcel(owner="NGUYEN ANH")],
        )
        assert matches[0].owner_occupied is True

    def test_parcels_without_a_dentist_are_excluded(self):
        matches = match_licensees_to_parcels(
            [licensee(street="1 Main St")], [parcel(street="999 Elsewhere Blvd")]
        )
        assert matches == []

    def test_busiest_buildings_come_first(self):
        matches = match_licensees_to_parcels(
            [
                licensee(street="1 Main St", zip_code="32801"),
                licensee(street="2 Oak Ave", zip_code="32801"),
                licensee(street="2 Oak Ave Ste 5", zip_code="32801"),
            ],
            [
                parcel(street="1 Main St", zip_code="32801", pid="1"),
                parcel(street="2 Oak Ave", zip_code="32801", pid="2"),
            ],
        )
        assert [match.practitioner_count for match in matches] == [2, 1]

    def test_no_input_yields_no_matches(self):
        assert match_licensees_to_parcels([], [parcel()]) == []
        assert match_licensees_to_parcels([licensee()], []) == []
