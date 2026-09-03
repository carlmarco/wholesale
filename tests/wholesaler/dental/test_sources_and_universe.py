"""
Tests for reading the two public files, and for the universe measurement.

The loaders have to survive real files: pipe-delimited licensure downloads,
county rolls re-exported with renamed headers, use codes written with and
without leading zeros. The measurement has to be honest about its own funnel,
because a low match rate looks exactly like a small market and means something
completely different.
"""
from datetime import date

import pytest

from src.wholesaler.dental.matching import match_licensees_to_parcels
from src.wholesaler.dental.sources import (
    WIDER_OFFICE_USE_CODES,
    DentalParcel,
    DentistLicense,
    load_licensees,
    load_parcels,
)
from src.wholesaler.dental.universe import measure_universe, render

AS_OF = date(2026, 9, 1)


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


class TestLoadingLicensees:
    def test_reads_a_pipe_delimited_download(self, tmp_path):
        path = write(
            tmp_path,
            "mqa.txt",
            "LICENSE_NUMBER|LAST_NAME|FIRST_NAME|LICENSE_DATE|LICENSE_STATUS|"
            "PRACTICE_ADDRESS|PRACTICE_CITY|PRACTICE_ZIP\n"
            "DN12345|NGUYEN|ANH|06/01/1990|ACTIVE|1234 N ORANGE AVE STE 200|ORLANDO|32801\n",
        )
        [licence] = load_licensees(path)

        assert licence.license_number == "DN12345"
        assert licence.last_name == "NGUYEN"
        assert licence.license_date == date(1990, 6, 1)
        assert licence.practice_zip == "32801"

    def test_sniffs_a_comma_delimited_re_export(self, tmp_path):
        path = write(
            tmp_path,
            "mqa.csv",
            "license_number,last_name,license_date,license_status,practice_address,practice_zip\n"
            "DN1,PATEL,1995-03-01,ACTIVE,500 Main St,32803\n",
        )
        [licence] = load_licensees(path)
        assert licence.last_name == "PATEL"

    def test_inactive_licences_are_excluded_by_default(self, tmp_path):
        path = write(
            tmp_path,
            "mqa.txt",
            "LICENSE_NUMBER|LAST_NAME|LICENSE_STATUS|PRACTICE_ADDRESS|PRACTICE_ZIP\n"
            "DN1|A|ACTIVE|1 Main St|32801\n"
            "DN2|B|NULL AND VOID|2 Main St|32801\n"
            "DN3|C|RETIRED|3 Main St|32801\n",
        )
        assert len(load_licensees(path)) == 1
        assert len(load_licensees(path, active_only=False)) == 3

    def test_years_licensed_is_measured_against_a_given_date(self, tmp_path):
        path = write(
            tmp_path,
            "mqa.txt",
            "LICENSE_NUMBER|LAST_NAME|LICENSE_DATE|LICENSE_STATUS|PRACTICE_ADDRESS|PRACTICE_ZIP\n"
            "DN1|A|1990-06-01|ACTIVE|1 Main St|32801\n",
        )
        [licence] = load_licensees(path)
        assert licence.years_licensed(AS_OF) == pytest.approx(36.3, abs=0.2)

    def test_a_missing_licence_date_is_not_invented(self, tmp_path):
        path = write(
            tmp_path,
            "mqa.txt",
            "LICENSE_NUMBER|LAST_NAME|LICENSE_DATE|LICENSE_STATUS|PRACTICE_ADDRESS|PRACTICE_ZIP\n"
            "DN1|A||ACTIVE|1 Main St|32801\n",
        )
        [licence] = load_licensees(path)
        assert licence.license_date is None
        assert licence.years_licensed(AS_OF) is None

    def test_the_wrong_profession_export_is_rejected_clearly(self, tmp_path):
        path = write(tmp_path, "mqa.txt", "NAME|ADDRESS\nSOMEONE|1 Main St\n")
        with pytest.raises(ValueError, match="no licence number column"):
            load_licensees(path)


class TestLoadingParcels:
    NAL_HEADER = (
        "PARCEL_ID,DOR_UC,OWN_NAME,PHY_ADDR1,PHY_CITY,PHY_ZIPCD,JV,TOT_LVG_AR,"
        "ACT_YR_BLT,SALE_YR1,SALE_MO1,SALE_PRC1\n"
    )

    def test_reads_nal_column_names(self, tmp_path):
        path = write(
            tmp_path,
            "nal.csv",
            self.NAL_HEADER
            + "12-34-56-7890,0019,NGUYEN ANH,1234 N ORANGE AVE,ORLANDO,32801,"
            "950000,3200,1998,2004,3,610000\n",
        )
        [parcel] = load_parcels(path)

        assert parcel.parcel_id_normalized == "1234567890"
        assert parcel.owner_name == "NGUYEN ANH"
        assert parcel.just_value == 950_000
        assert parcel.building_sqft == 3200
        assert parcel.year_built == 1998
        assert parcel.last_sale_date == date(2004, 3, 1)

    def test_only_the_requested_use_codes_are_kept(self, tmp_path):
        path = write(
            tmp_path,
            "nal.csv",
            self.NAL_HEADER
            + "1,0019,A,1 Main St,ORLANDO,32801,1,1,2000,,,\n"
            + "2,0001,B,2 Main St,ORLANDO,32801,1,1,2000,,,\n"
            + "3,0018,C,3 Main St,ORLANDO,32801,1,1,2000,,,\n",
        )
        assert len(load_parcels(path)) == 1
        assert len(load_parcels(path, use_codes=WIDER_OFFICE_USE_CODES)) == 2

    def test_use_codes_match_with_or_without_leading_zeros(self, tmp_path):
        path = write(
            tmp_path,
            "nal.csv",
            self.NAL_HEADER + "1,19,A,1 Main St,ORLANDO,32801,1,1,2000,,,\n",
        )
        assert len(load_parcels(path)) == 1

    def test_the_county_label_falls_back_to_the_argument(self, tmp_path):
        path = write(
            tmp_path,
            "nal.csv",
            self.NAL_HEADER + "1,0019,A,1 Main St,ORLANDO,32801,1,1,2000,,,\n",
        )
        [parcel] = load_parcels(path, county="orange")
        assert parcel.county == "orange"

    def test_a_roll_without_a_parcel_column_is_rejected(self, tmp_path):
        path = write(tmp_path, "nal.csv", "DOR_UC,OWN_NAME\n0019,A\n")
        with pytest.raises(ValueError, match="no parcel identifier column"):
            load_parcels(path)

    def test_a_missing_file_says_so(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_parcels(tmp_path / "absent.csv")


def licensee(street, zip_code="32801", last="NGUYEN", licensed="1990-06-01"):
    return DentistLicense(
        license_number=f"DN{street}",
        last_name=last,
        full_name=f"A {last}",
        license_date=date.fromisoformat(licensed) if licensed else None,
        status="ACTIVE",
        practice_street=street,
        practice_city="ORLANDO",
        practice_zip=zip_code,
    )


def parcel(street, zip_code="32801", owner="NGUYEN ANH", county="orange", sold=None):
    return DentalParcel(
        parcel_id_normalized=street.replace(" ", ""),
        parcel_id_original=street,
        dor_use_code="0019",
        owner_name=owner,
        site_street=street,
        site_city="ORLANDO",
        site_zip=zip_code,
        county=county,
        last_sale_date=date.fromisoformat(sold) if sold else None,
    )


class TestUniverseMeasurement:
    def test_counts_the_funnel(self):
        licensees = [licensee("1 Main St"), licensee("2 Oak Ave"), licensee("3 Absent Rd")]
        parcels = [parcel("1 Main St"), parcel("2 Oak Ave"), parcel("9 Empty Way")]
        matches = match_licensees_to_parcels(licensees, parcels)

        report = measure_universe(licensees, parcels, matches, as_of=AS_OF)

        assert report.licensees == 3
        assert report.distinct_practice_addresses == 3
        assert report.parcels == 3
        assert report.matched_buildings == 2
        assert report.match_rate == pytest.approx(2 / 3)

    def test_owner_occupancy_is_counted_separately(self):
        licensees = [licensee("1 Main St", last="NGUYEN"), licensee("2 Oak Ave", last="PATEL")]
        parcels = [
            parcel("1 Main St", owner="NGUYEN ANH"),
            parcel("2 Oak Ave", owner="BIGCO HOLDINGS LLC"),
        ]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )

        assert report.owner_occupied == 1
        assert report.owner_occupied_rate == pytest.approx(0.5)

    def test_the_exit_window_counts_only_owner_occupied_buildings(self):
        """A building the dentist does not own is not an acquisition target."""
        licensees = [
            licensee("1 Main St", last="NGUYEN", licensed="1985-01-01"),   # long-licensed, owns
            licensee("2 Oak Ave", last="PATEL", licensed="1985-01-01"),    # long-licensed, rents
        ]
        parcels = [
            parcel("1 Main St", owner="NGUYEN ANH"),
            parcel("2 Oak Ave", owner="BIGCO HOLDINGS LLC"),
        ]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )
        assert report.in_exit_window == 1

    def test_a_recently_licensed_owner_is_not_in_the_exit_window(self):
        licensees = [licensee("1 Main St", licensed="2018-01-01")]
        parcels = [parcel("1 Main St")]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )
        assert report.owner_occupied == 1
        assert report.in_exit_window == 0

    def test_turnover_is_measured_from_recorded_sales(self):
        licensees = [licensee(f"{i} Main St") for i in range(1, 5)]
        parcels = [
            parcel("1 Main St", sold="2022-04-01"),
            parcel("2 Main St", sold="2023-06-01"),
            parcel("3 Main St", sold="2023-09-01"),
            parcel("4 Main St"),
        ]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )

        assert report.transactions_by_year == {2022: 1, 2023: 2}
        assert report.annual_transactions == pytest.approx(1.5)

    def test_counties_are_broken_out(self):
        licensees = [licensee("1 Main St"), licensee("2 Oak Ave", zip_code="32701")]
        parcels = [
            parcel("1 Main St", county="orange"),
            parcel("2 Oak Ave", zip_code="32701", county="seminole"),
        ]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )
        assert report.counties == {"orange": 1, "seminole": 1}


class TestUniverseWarnings:
    def test_zero_matches_is_reported_as_a_plumbing_failure(self):
        licensees = [licensee("1 Main St")]
        parcels = [parcel("999 Elsewhere Blvd")]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )

        warnings = " ".join(report.warnings())
        assert "plumbing failure, not a finding about the market" in warnings

    def test_a_low_match_rate_is_flagged_as_a_floor(self):
        licensees = [licensee(f"{i} Main St") for i in range(1, 11)]
        parcels = [parcel("1 Main St")]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )

        assert report.match_rate < 0.35
        assert any("treat the totals as a floor" in w for w in report.warnings())

    def test_a_small_universe_points_at_the_feasibility_threshold(self):
        licensees = [licensee("1 Main St")]
        parcels = [parcel("1 Main St")]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )
        assert any("below the 200" in w for w in report.warnings())

    def test_absent_sale_dates_are_called_out(self):
        licensees = [licensee("1 Main St")]
        parcels = [parcel("1 Main St")]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )
        assert any("turnover could not be measured" in w for w in report.warnings())

    def test_no_licensees_at_all(self):
        report = measure_universe([], [], [], as_of=AS_OF)
        assert report.warnings() == ["No licensees were read; nothing can be concluded."]


class TestRendering:
    def test_the_report_renders_its_numbers_and_caveats(self):
        licensees = [licensee("1 Main St")]
        parcels = [parcel("1 Main St", sold="2023-01-01")]
        report = measure_universe(
            licensees, parcels, match_licensees_to_parcels(licensees, parcels), as_of=AS_OF
        )
        text = render(report)

        assert "DENTAL OFFICE UNIVERSE" in text
        assert "Owner-occupied buildings" in text
        assert "Read this before believing the numbers" in text
