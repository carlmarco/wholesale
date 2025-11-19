"""
ML Feature Builder

Responsible for extracting training datasets from the operational database.

.. deprecated:: 2025-11
    The direct table access methods (build_arv_dataset, build_lead_dataset) are deprecated.
    Use FeatureStoreBuilder from src.wholesaler.ml.features.feature_store instead, which
    provides a centralized feature store with proper normalization and temporal features.

Migration path:
    - build_arv_dataset() -> FeatureStoreBuilder.build_feature_dataframe()
    - build_lead_dataset() -> FeatureStoreBuilder.build_feature_dataframe()
    - Direct to ML models -> Use HybridMLScorer for inference
"""
import warnings
from typing import Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from src.wholesaler.db.repository import (
    PropertyRepository,
    PropertyRecordRepository,
    TaxSaleRepository,
    ForeclosureRepository,
    LeadScoreRepository,
)
from src.wholesaler.db.session import get_db_session
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class FeatureBuilder:
    """
    Builds ML-ready feature matrices from database tables.
    """

    def __init__(self):
        self.property_repo = PropertyRepository()
        self.property_record_repo = PropertyRecordRepository()
        self.tax_sale_repo = TaxSaleRepository()
        self.foreclosure_repo = ForeclosureRepository()
        self.lead_repo = LeadScoreRepository()

    def build_from_feature_store(
        self,
        session: Optional[Session] = None,
    ) -> pd.DataFrame:
        """
        Build training dataset using the new centralized FeatureStoreBuilder.

        This is the recommended method for ML training datasets.

        Returns:
            pandas DataFrame with ML-ready features from enriched seeds.
        """
        from src.wholesaler.ml.features.feature_store import FeatureStoreBuilder

        owned_session = False
        if session is None:
            session_ctx = get_db_session()
            session = session_ctx.__enter__()
            owned_session = True

        try:
            builder = FeatureStoreBuilder(session)
            df = builder.build_feature_dataframe()
            logger.info("feature_store_dataset_built", rows=len(df))
            return df
        finally:
            if owned_session:
                session_ctx.__exit__(None, None, None)

    def build_arv_dataset(
        self,
        session: Optional[Session] = None,
        min_market_value: float = 50000,
        max_market_value: float = 800000,
    ) -> pd.DataFrame:
        """
        Build features for ARV regression using property records and related data.

        .. deprecated:: 2025-11
            Use build_from_feature_store() instead.
        """
        warnings.warn(
            "build_arv_dataset is deprecated. Use build_from_feature_store() for centralized features.",
            DeprecationWarning,
            stacklevel=2,
        )
        owned_session = False
        if session is None:
            session_ctx = get_db_session()
            session = session_ctx.__enter__()
            owned_session = True

        try:
            properties = self.property_repo.get_all(session)
            property_records = self.property_record_repo.get_all(session)
            tax_sales = self.tax_sale_repo.get_all(session)
            foreclosures = self.foreclosure_repo.get_all(session)

            df_properties = self._to_dataframe(properties)
            df_records = self._to_dataframe(property_records)
            df_tax_sales = self._to_dataframe(tax_sales)
            df_foreclosures = self._to_dataframe(foreclosures)

            # Ensure all dataframes have parcel_id_normalized column
            dfs = [df_properties, df_records, df_tax_sales, df_foreclosures]
            for df in dfs:
                if "parcel_id_normalized" not in df.columns:
                    df["parcel_id_normalized"] = pd.NA

            dataset = (
                df_properties.merge(
                    df_records,
                    on="parcel_id_normalized",
                    how="inner",
                    suffixes=("", "_record"),
                )
                .merge(df_tax_sales, on="parcel_id_normalized", how="left", suffixes=("", "_tax"))
                .merge(
                    df_foreclosures,
                    on="parcel_id_normalized",
                    how="left",
                    suffixes=("", "_foreclosure"),
                )
            )

            dataset = dataset[
                (dataset["total_mkt"].notna())
                & (dataset["total_mkt"] >= min_market_value)
                & (dataset["total_mkt"] <= max_market_value)
            ]

            logger.info(
                "arv_feature_dataset_built",
                rows=len(dataset),
                min_market_value=min_market_value,
                max_market_value=max_market_value,
            )

            return dataset
        finally:
            if owned_session:
                session_ctx.__exit__(None, None, None)

    def build_lead_dataset(
        self,
        session: Optional[Session] = None,
        recent_days: int = 90,
    ) -> pd.DataFrame:
        """
        Build lead qualification dataset using current scores and property attributes.

        .. deprecated:: 2025-11
            Use build_from_feature_store() instead.

        Args:
            session: Optional SQLAlchemy session
            recent_days: Filter to leads scored within N days

        Returns:
            pandas DataFrame with features and binary target (tier A vs others)
        """
        warnings.warn(
            "build_lead_dataset is deprecated. Use build_from_feature_store() for centralized features.",
            DeprecationWarning,
            stacklevel=2,
        )
        owned_session = False
        if session is None:
            session_ctx = get_db_session()
            session = session_ctx.__enter__()
            owned_session = True

        try:
            leads = self.lead_repo.get_all(session)
            properties = self.property_repo.get_all(session)
            property_records = self.property_record_repo.get_all(session)
            tax_sales = self.tax_sale_repo.get_all(session)
            foreclosures = self.foreclosure_repo.get_all(session)

            df_leads = self._to_dataframe(leads)
            df_properties = self._to_dataframe(properties)
            df_records = self._to_dataframe(property_records)
            df_tax_sales = self._to_dataframe(tax_sales)
            df_foreclosures = self._to_dataframe(foreclosures)

            for df in [df_leads, df_properties, df_records, df_tax_sales, df_foreclosures]:
                if "parcel_id_normalized" not in df.columns:
                    df["parcel_id_normalized"] = pd.NA

            dataset = (
                df_leads.merge(
                    df_properties,
                    on="parcel_id_normalized",
                    how="left",
                    suffixes=("", "_property"),
                )
                .merge(
                    df_records,
                    on="parcel_id_normalized",
                    how="left",
                    suffixes=("", "_record"),
                )
                .merge(
                    df_tax_sales,
                    on="parcel_id_normalized",
                    how="left",
                    suffixes=("", "_tax"),
                )
                .merge(
                    df_foreclosures,
                    on="parcel_id_normalized",
                    how="left",
                    suffixes=("", "_foreclosure"),
                )
            )

            if "scored_at" in dataset.columns:
                scored = pd.to_datetime(dataset["scored_at"], errors="coerce", utc=True)
                cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=recent_days)
                dataset = dataset[scored >= cutoff]

            dataset["label_tier_a"] = (dataset["tier"] == "A").astype(int)

            logger.info(
                "lead_feature_dataset_built",
                rows=len(dataset),
                recent_days=recent_days,
            )

            return dataset
        finally:
            if owned_session:
                session_ctx.__exit__(None, None, None)

    def _to_dataframe(self, records) -> pd.DataFrame:
        """Convert list of SQLAlchemy models to DataFrame."""
        if not records:
            return pd.DataFrame()
        rows = [self._object_to_dict(rec) for rec in records]
        return pd.DataFrame.from_records(rows)

    @staticmethod
    def _object_to_dict(obj) -> dict:
        """Convert SQLAlchemy model to dictionary by reading __dict__."""
        data = {}
        for key, value in vars(obj).items():
            if key.startswith("_"):
                continue
            data[key] = value
        return data
