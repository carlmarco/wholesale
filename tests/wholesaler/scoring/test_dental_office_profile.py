"""
Tests for the dental office profile.

The profile ranks dentist-owned commercial buildings by how close the owner is
to exiting and how much value is at stake. These pin the behaviour that the
business logic depends on, and in particular that every date-based signal is
computed against the record's ``as_of`` rather than today - without which a
historical cohort would age every dentist to the present and the scores would be
meaningless.
"""

import pytest

from src.wholesaler.scoring.profiles import dental_office
from src.wholesaler.scoring.profiles.dental_office import (
    InstitutionalExitGate,
    asset_fit_score,
    build_engine,
    debt_pressure_score,
    owner_exit_score,
)

AS_OF = "2026-09-01"


def record(**sections):
    """A dental record with sensible defaults, overridable per section."""
    base = {
        "as_of": AS_OF,
        "dentist": {"license_date": "1990-06-01"},
        "ownership": {"last_sale_date": "2010-01-01"},
        "property": {"dor_use_code": "0019", "building_sqft": 3200, "year_built": 1998},
        "debt": {},
        "practice": {},
    }
    for name, value in sections.items():
        base[name] = {**base.get(name, {}), **value} if isinstance(value, dict) else value
    return base


@pytest.fixture(scope="module")
def engine():
    return build_engine()


class TestConfiguration:
    def test_weights_sum_to_one(self, engine):
        assert sum(bucket.weight for bucket in engine.buckets) == pytest.approx(1.0)

    def test_owner_exit_carries_the_most_weight(self):
        """The thesis is that the building transacts when the dentist retires."""
        assert dental_office.WEIGHTS["owner_exit"] == max(dental_office.WEIGHTS.values())

    def test_buckets_are_named_for_the_commercial_thesis(self, engine):
        assert engine.bucket_names == [
            "owner_exit",
            "debt_pressure",
            "asset_fit",
            "deal_value",
        ]

    def test_shares_no_vocabulary_with_the_residential_profile(self):
        """The two profiles are independent models, not variants of one."""
        from src.wholesaler.scoring.profiles import real_estate

        assert set(dental_office.WEIGHTS) & set(real_estate.WEIGHTS) == set()


class TestOwnerExit:
    def gate(self):
        return InstitutionalExitGate().evaluate(record())

    @pytest.mark.parametrize(
        "license_year,expected",
        [
            (1980, dental_office.PAST_TYPICAL_RETIREMENT_POINTS),  # ~46 years, overdue
            (1990, dental_office.EXIT_WINDOW_POINTS),              # ~36 years, in window
            (2000, dental_office.APPROACHING_WINDOW_POINTS),       # ~26 years, warming up
            (2016, 0.0),                                           # ~10 years, no signal
        ],
    )
    def test_licence_age_bands(self, license_year, expected):
        score = owner_exit_score(
            record(
                dentist={"license_date": f"{license_year}-06-01"},
                ownership={"last_sale_date": "2024-01-01"},  # short hold, no tenure points
            ),
            self.gate(),
        )
        assert score == pytest.approx(expected)

    def test_long_ownership_adds_to_the_licence_signal(self):
        short_hold = owner_exit_score(
            record(ownership={"last_sale_date": "2024-01-01"}), self.gate()
        )
        long_hold = owner_exit_score(
            record(ownership={"last_sale_date": "2001-01-01"}), self.gate()
        )
        assert long_hold > short_hold

    def test_only_the_highest_tenure_band_applies(self):
        """Bands are alternatives, not cumulative."""
        score = owner_exit_score(
            record(
                dentist={"license_date": "2016-06-01"},  # no licence points
                ownership={"last_sale_date": "1990-01-01"},  # 36 years held
            ),
            self.gate(),
        )
        assert score == pytest.approx(30)

    def test_missing_dates_score_zero_rather_than_guessing(self):
        assert owner_exit_score(
            {"as_of": AS_OF, "dentist": {}, "ownership": {}}, self.gate()
        ) == 0.0

    def test_uses_as_of_not_today(self):
        """A 1990 licensee was mid-career in 2005 and retiring in 2026."""
        early = owner_exit_score(
            record(as_of="2005-01-01", ownership={"last_sale_date": "2004-01-01"}),
            self.gate(),
        )
        late = owner_exit_score(
            record(as_of="2026-09-01", ownership={"last_sale_date": "2004-01-01"}),
            self.gate(),
        )
        assert early < late, "the same dentist must not look retirement-aged in 2005"


class TestDebtPressure:
    def gate(self):
        return InstitutionalExitGate().evaluate(record())

    def test_maturity_is_derived_from_origination_and_term(self):
        """SBA 504 terms are long and fixed, so maturity is computable."""
        score = debt_pressure_score(
            record(debt={"origination_date": "2002-01-01", "term_years": 25}), self.gate()
        )
        assert score == dental_office.MONTHS_TO_MATURITY_BANDS[0][1]

    def test_an_explicit_maturity_date_wins(self):
        score = debt_pressure_score(
            record(debt={"maturity_date": "2027-03-01"}), self.gate()
        )
        assert score == dental_office.MONTHS_TO_MATURITY_BANDS[0][1]

    def test_distant_maturity_scores_nothing(self):
        assert debt_pressure_score(
            record(debt={"maturity_date": "2040-01-01"}), self.gate()
        ) == 0.0

    def test_already_matured_scores_nothing(self):
        """Whatever the balloon was going to force, it already forced."""
        assert debt_pressure_score(
            record(debt={"maturity_date": "2020-01-01"}), self.gate()
        ) == 0.0

    def test_no_debt_information_scores_zero(self):
        assert debt_pressure_score(record(debt={}), self.gate()) == 0.0

    def test_pressure_increases_as_maturity_approaches(self):
        far = debt_pressure_score(record(debt={"maturity_date": "2029-06-01"}), self.gate())
        near = debt_pressure_score(record(debt={"maturity_date": "2027-03-01"}), self.gate())
        assert near > far


class TestAssetFit:
    def gate(self):
        return InstitutionalExitGate().evaluate(record())

    def test_the_dental_use_code_is_recognised(self):
        with_code = asset_fit_score(record(property={"dor_use_code": "0019"}), self.gate())
        without = asset_fit_score(record(property={"dor_use_code": "0001"}), self.gate())
        assert with_code - without == dental_office.USE_CODE_MATCH_POINTS

    def test_use_code_matches_with_or_without_leading_zeros(self):
        padded = asset_fit_score(record(property={"dor_use_code": "0019"}), self.gate())
        bare = asset_fit_score(record(property={"dor_use_code": "19"}), self.gate())
        assert padded == bare

    def test_a_building_in_the_dental_range_scores_full_marks(self):
        score = asset_fit_score(record(property={"building_sqft": 3200}), self.gate())
        assert score == pytest.approx(
            dental_office.USE_CODE_MATCH_POINTS
            + dental_office.IN_SQFT_RANGE_POINTS
            + dental_office.MODERN_BUILD_POINTS
        )

    def test_an_undersized_suite_is_penalised_hard(self):
        """Below the range is usually a plaza suite, not an acquirable parcel."""
        suite = asset_fit_score(record(property={"building_sqft": 700}), self.gate())
        building = asset_fit_score(record(property={"building_sqft": 3200}), self.gate())
        assert suite < building - dental_office.NEAR_SQFT_RANGE_POINTS

    def test_an_oversized_building_is_treated_more_generously(self):
        """Above the range is a multi-tenant medical building - still real estate."""
        oversized = asset_fit_score(record(property={"building_sqft": 9_000}), self.gate())
        undersized = asset_fit_score(record(property={"building_sqft": 900}), self.gate())
        assert oversized > undersized

    def test_older_buildings_lose_the_construction_points(self):
        modern = asset_fit_score(record(property={"year_built": 1998}), self.gate())
        dated = asset_fit_score(record(property={"year_built": 1965}), self.gate())
        assert modern - dated == dental_office.MODERN_BUILD_POINTS


class TestInstitutionalExitGate:
    def test_spread_comes_from_the_cap_rate_differential(self):
        result = InstitutionalExitGate().evaluate(record())
        detail = result.detail

        assert detail["exit_value"] > detail["acquisition_value"], (
            "exiting at a tighter cap rate than the purchase is the whole thesis"
        )
        expected = (
            detail["exit_value"] - detail["acquisition_value"] - detail["transaction_costs"]
        )
        assert detail["projected_spread"] == pytest.approx(expected, abs=0.01)

    def test_a_small_building_cannot_clear_the_minimum_spread(self):
        result = InstitutionalExitGate().evaluate(record(property={"building_sqft": 800}))
        assert result.viable is False

    def test_a_large_building_clears_it(self):
        result = InstitutionalExitGate().evaluate(record(property={"building_sqft": 4_000}))
        assert result.viable is True

    def test_an_observed_lease_rent_beats_the_market_assumption(self):
        market = InstitutionalExitGate().evaluate(record())
        leased = InstitutionalExitGate().evaluate(
            record(lease={"rent_per_sqft": 48.0})
        )
        assert leased.detail["rent_per_sqft"] == 48.0
        assert leased.detail["projected_spread"] > market.detail["projected_spread"]

    def test_without_building_area_the_gate_refuses_rather_than_guesses(self):
        result = InstitutionalExitGate().evaluate(
            {"as_of": AS_OF, "property": {"dor_use_code": "0019"}}
        )
        assert result.viable is False
        assert "no building area" in result.detail["reason"]


class TestScoringEndToEnd:
    def test_a_retiring_owner_with_a_maturing_loan_reaches_tier_a(self, engine):
        result = engine.score(
            record(
                dentist={"license_date": "1986-06-01"},
                ownership={"last_sale_date": "2004-03-01"},
                debt={"origination_date": "2002-07-01", "term_years": 25},
            )
        )
        assert result.tier == "A"

    def test_a_young_owner_who_just_bought_is_not_a_lead(self, engine):
        result = engine.score(
            record(
                dentist={"license_date": "2016-06-01"},
                ownership={"last_sale_date": "2022-03-01"},
                debt={"origination_date": "2022-03-01", "term_years": 25},
            )
        )
        assert result.tier == "D"

    def test_an_unviable_deal_cannot_reach_the_top_tiers(self, engine):
        """However close to retirement, a building with no spread is not a lead."""
        result = engine.score(
            record(
                dentist={"license_date": "1980-06-01"},
                ownership={"last_sale_date": "1995-01-01"},
                property={"building_sqft": 800},
            )
        )
        assert result.gate.viable is False
        assert result.tier not in {"A", "B"}

    def test_a_dso_tenant_is_a_bonus(self, engine):
        """The lease is written and the owner is a reluctant landlord."""
        without = engine.score(record(practice={"dso_affiliated": False}))
        with_dso = engine.score(record(practice={"dso_affiliated": True}))

        assert "dso_tenant" in with_dso.bonuses_applied
        assert with_dso.total_score > without.total_score

    def test_an_already_listed_building_is_penalised(self, engine):
        """A listed building is a competitive process, and the lease is set."""
        quiet = engine.score(record(ownership={"listed_for_sale": False}))
        listed = engine.score(record(ownership={"listed_for_sale": True}))

        assert "already_listed" in listed.bonuses_applied
        assert listed.total_score < quiet.total_score

    def test_scores_stay_in_range(self, engine):
        for sqft in (500, 3_000, 20_000):
            for year in (1975, 1990, 2015):
                result = engine.score(
                    record(
                        dentist={"license_date": f"{year}-06-01"},
                        property={"building_sqft": sqft},
                    )
                )
                assert 0 <= result.total_score <= 100
                assert result.tier in {"A", "B", "C", "D"}


class TestPointInTimeSafety:
    def test_the_same_record_scores_differently_at_different_dates(self, engine):
        """Required for historical reconstruction to mean anything."""
        past = engine.score(record(as_of="2008-01-01"))
        present = engine.score(record(as_of="2026-09-01"))
        assert past.total_score != present.total_score

    def test_a_missing_as_of_falls_back_to_today_without_raising(self, engine):
        result = engine.score(
            {
                "dentist": {"license_date": "1990-06-01"},
                "ownership": {"last_sale_date": "2005-01-01"},
                "property": {"dor_use_code": "0019", "building_sqft": 3200, "year_built": 1998},
            }
        )
        assert 0 <= result.total_score <= 100
