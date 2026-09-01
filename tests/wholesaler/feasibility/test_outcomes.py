"""
Tests for outcome loading and the point-in-time join.

The join is the correctness-critical piece: a label drawn from a sale that
predates the scoring date, or features computed after the sale, makes every
downstream measurement meaningless while looking fine.
"""
from datetime import date

import pytest

from src.wholesaler.feasibility.outcomes import (
    CohortMember,
    PointInTimeError,
    SaleOutcome,
    assert_features_precede_outcomes,
    label_cohort,
    load_sale_outcomes,
)


def member(parcel="1", as_of=date(2024, 1, 1), score=50.0):
    return CohortMember(parcel_id_normalized=parcel, as_of=as_of, score=score)


def sale(parcel="1", when=date(2024, 3, 1), price=250_000.0):
    return SaleOutcome(parcel_id_normalized=parcel, sale_date=when, sale_price=price)


class TestLabelling:
    def test_sale_inside_the_horizon_is_a_positive(self):
        [result] = label_cohort([member()], [sale(when=date(2024, 3, 1))], horizon_days=180)
        assert result.sold is True
        assert result.days_to_sale == 60

    def test_sale_after_the_horizon_is_not(self):
        [result] = label_cohort([member()], [sale(when=date(2024, 9, 1))], horizon_days=180)
        assert result.sold is False
        assert result.sale_date is None

    def test_sale_before_the_scoring_date_is_history_not_an_outcome(self):
        """A prior sale is something the scorer could have seen, not a result."""
        [result] = label_cohort([member()], [sale(when=date(2023, 6, 1))], horizon_days=180)
        assert result.sold is False

    def test_sale_on_the_scoring_date_is_excluded(self):
        [result] = label_cohort([member()], [sale(when=date(2024, 1, 1))], horizon_days=180)
        assert result.sold is False

    def test_sale_on_the_final_day_is_included(self):
        [result] = label_cohort([member()], [sale(when=date(2024, 6, 29))], horizon_days=180)
        assert result.sold is True

    def test_earliest_qualifying_sale_wins(self):
        sales = [sale(when=date(2024, 5, 1)), sale(when=date(2024, 2, 1))]
        [result] = label_cohort([member()], sales, horizon_days=180)
        assert result.sale_date == date(2024, 2, 1)

    def test_nominal_transfers_are_excluded_by_default(self):
        """A $10 quitclaim is not a sale and would poison the label."""
        [result] = label_cohort([member()], [sale(price=10.0)], horizon_days=180)
        assert result.sold is False

    def test_nominal_transfers_can_be_kept_deliberately(self):
        [result] = label_cohort(
            [member()], [sale(price=10.0)], horizon_days=180, arms_length_only=False
        )
        assert result.sold is True

    def test_each_member_uses_its_own_as_of_date(self):
        cohort = [
            member(parcel="1", as_of=date(2024, 1, 1)),
            member(parcel="2", as_of=date(2024, 6, 1)),
        ]
        sales = [sale(parcel="1", when=date(2024, 2, 1)), sale(parcel="2", when=date(2024, 2, 1))]

        results = label_cohort(cohort, sales, horizon_days=180)

        assert results[0].sold is True
        assert results[1].sold is False, "sale predates this member's own scoring date"

    def test_unmatched_parcels_are_negatives_not_dropped(self):
        results = label_cohort([member(parcel="absent")], [], horizon_days=180)
        assert len(results) == 1
        assert results[0].sold is False

    def test_rejects_a_non_positive_horizon(self):
        with pytest.raises(ValueError, match="horizon_days"):
            label_cohort([member()], [sale()], horizon_days=0)


class TestPointInTimeGuard:
    def test_accepts_features_computed_before_scoring(self):
        labelled = label_cohort([member()], [sale()], horizon_days=180)
        assert_features_precede_outcomes(labelled, {"1": date(2023, 12, 1)})

    def test_rejects_features_computed_after_the_scoring_date(self):
        labelled = label_cohort([member()], [sale()], horizon_days=180)
        with pytest.raises(PointInTimeError, match="after as_of"):
            assert_features_precede_outcomes(labelled, {"1": date(2024, 2, 1)})

    def test_names_the_sale_when_features_postdate_it(self):
        """The failure that flatters offline and fails live."""
        labelled = label_cohort(
            [member(as_of=date(2024, 1, 1))], [sale(when=date(2024, 2, 1))], horizon_days=180
        )
        with pytest.raises(PointInTimeError, match="which its sale on 2024-02-01 precedes"):
            assert_features_precede_outcomes(labelled, {"1": date(2024, 3, 1)})

    def test_parcels_without_a_recorded_feature_date_are_skipped(self):
        labelled = label_cohort([member()], [sale()], horizon_days=180)
        assert_features_precede_outcomes(labelled, {})


class TestLoading:
    def _write(self, tmp_path, text):
        path = tmp_path / "sales.csv"
        path.write_text(text)
        return path

    def test_reads_the_expected_columns(self, tmp_path):
        path = self._write(
            tmp_path,
            "parcel_id,sale_date,sale_price\n123456789001001,03/15/2024,\"$250,000\"\n",
        )
        [outcome] = load_sale_outcomes(path)

        assert outcome.parcel_id_normalized == "123456789001001"
        assert outcome.sale_date == date(2024, 3, 15)
        assert outcome.sale_price == 250_000.0

    def test_accepts_iso_dates_and_plain_prices(self, tmp_path):
        path = self._write(tmp_path, "parcel_id,sale_date,sale_price\n1,2024-03-15,250000\n")
        [outcome] = load_sale_outcomes(path)
        assert outcome.sale_date == date(2024, 3, 15)
        assert outcome.sale_price == 250_000.0

    def test_skips_rows_without_a_usable_parcel_or_date(self, tmp_path):
        path = self._write(
            tmp_path,
            "parcel_id,sale_date,sale_price\n1,2024-03-15,100\n,2024-03-15,100\n2,,100\n2,garbage,100\n",
        )
        assert len(load_sale_outcomes(path)) == 1

    def test_missing_price_is_allowed(self, tmp_path):
        path = self._write(tmp_path, "parcel_id,sale_date\n1,2024-03-15\n")
        [outcome] = load_sale_outcomes(path)
        assert outcome.sale_price is None
        assert outcome.is_arms_length is False

    def test_rejects_an_extract_without_the_needed_columns(self, tmp_path):
        path = self._write(tmp_path, "folio,date_of_sale\n1,2024-03-15\n")
        with pytest.raises(ValueError, match="parcel_id and sale_date"):
            load_sale_outcomes(path)

    def test_missing_file_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_sale_outcomes(tmp_path / "nope.csv")
