"""
Feature Store Builder

Materializes features from enriched_seeds and related tables into ML-ready format.
Exports to parquet files and/or database table for training and inference.
"""
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, joinedload

from src.wholesaler.db.models import (
    EnrichedSeed,
    Property,
    MLFeatureStore,
)
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class FeatureStoreBuilder:
    """
    Builds and materializes ML feature vectors from enriched seeds and property data.

    Features include:
    - Distress signals (violation counts, recency, severity)
    - Financial metrics (market value, equity, tax rates)
    - Temporal features (days to auction, days since violation)
    - Categorical encodings (seed type, city, zip code)
    - Geo features (nearby violations)
    """

    def __init__(self, session: Session):
        """Initialize with database session."""
        self.session = session
        self._city_encoder: dict[str, int] = {}
        self._zip_encoder: dict[str, int] = {}

    def build_feature_dataframe(self) -> pd.DataFrame:
        """
        Build a pandas DataFrame with all features from enriched seeds.

        Returns:
            DataFrame with one row per parcel containing all ML features.
        """
        logger.info("building_feature_dataframe")

        # Get all enriched seeds with their JSONB data
        enriched_seeds = self._fetch_enriched_seeds()
        if not enriched_seeds:
            logger.warning("no_enriched_seeds_found")
            return pd.DataFrame()

        parcel_ids = [seed.parcel_id_normalized for seed in enriched_seeds]
        property_map = self._fetch_property_map(parcel_ids)
        today = date.today()

        # Build feature rows
        feature_rows = []
        for seed in enriched_seeds:
            try:
                features = self._extract_features_from_seed(seed, property_map, today)
                if features:
                    feature_rows.append(features)
            except Exception as e:
                logger.error(
                    "feature_extraction_failed",
                    parcel_id=seed.parcel_id_normalized,
                    error=str(e),
                )

        df = pd.DataFrame(feature_rows)
        logger.info("feature_dataframe_built", rows=len(df), columns=len(df.columns))

        # Apply encoding for categorical features
        df = self._encode_categorical_features(df)

        return df

    def _fetch_enriched_seeds(self) -> list[EnrichedSeed]:
        """Fetch all enriched seed records."""
        query = select(EnrichedSeed).where(EnrichedSeed.processed == True)
        result = self.session.execute(query)
        return list(result.scalars().all())

    def _extract_features_from_seed(
        self,
        seed: EnrichedSeed,
        property_map: dict[str, Property],
        today: date,
    ) -> Optional[dict]:
        """
        Extract ML features from a single enriched seed record.

        Combines enriched_data JSONB with joined property/tax/foreclosure data.
        """
        if not seed.enriched_data:
            return None

        enriched = seed.enriched_data
        if isinstance(enriched, str):
            try:
                import json

                enriched = json.loads(enriched)
            except (json.JSONDecodeError, TypeError):
                return None

        parcel_id = seed.parcel_id_normalized

        # Base features from enriched_data JSONB
        features = {
            "parcel_id_normalized": parcel_id,
            "computed_at": datetime.utcnow(),
            # Distress features
            "violation_count": enriched.get("violation_count", 0) or 0,
            "open_violation_count": self._count_open_violations(enriched),
            "days_since_last_violation": self._compute_days_since_violation(enriched, today),
            "max_violation_severity": self._compute_violation_severity(enriched, today),
            # Categorical (seed type)
            "seed_type_tax_sale": seed.seed_type == "tax_sale",
            "seed_type_foreclosure": seed.seed_type == "foreclosure",
            "seed_type_code_violation": seed.seed_type == "code_violation",
            # Geo features
            "nearby_violations_count": enriched.get("geo_nearby_violations", 0) or 0,
            "nearest_violation_distance": enriched.get("geo_nearest_violation_distance"),
        }

        # Join property data
        property_obj = property_map.get(parcel_id)
        if property_obj:
            prop = property_obj
            prop_record = property_obj.property_record
            tax_sale = property_obj.tax_sale
            foreclosure = property_obj.foreclosure

            # Location features (raw, will be encoded later)
            features["city"] = prop.city
            features["zip_code"] = prop.zip_code

            # Financial features from property record
            if prop_record:
                features["total_market_value"] = float(prop_record.total_mkt) if prop_record.total_mkt else None
                features["equity_percent"] = float(prop_record.equity_percent) if prop_record.equity_percent else None
                features["tax_rate"] = float(prop_record.tax_rate) if prop_record.tax_rate else None
                # Temporal: property age
                if prop_record.year_built:
                    features["property_age_years"] = today.year - prop_record.year_built

            # Foreclosure features
            if foreclosure:
                features["default_amount"] = float(foreclosure.default_amount) if foreclosure.default_amount else None
                features["opening_bid"] = float(foreclosure.opening_bid) if foreclosure.opening_bid else None
                # Temporal: days to auction
                if foreclosure.auction_date:
                    delta = foreclosure.auction_date - today
                    features["days_to_auction"] = max(0, delta.days)

            # Tax sale features
            if tax_sale:
                # Temporal: days to tax sale
                if tax_sale.sale_date:
                    delta = tax_sale.sale_date - today
                    features["days_to_tax_sale"] = max(0, delta.days)

        # Set defaults for missing values
        features.setdefault("city", None)
        features.setdefault("zip_code", None)
        features.setdefault("total_market_value", None)
        features.setdefault("equity_percent", None)
        features.setdefault("tax_rate", None)
        features.setdefault("default_amount", None)
        features.setdefault("opening_bid", None)
        features.setdefault("days_to_auction", None)
        features.setdefault("days_to_tax_sale", None)
        features.setdefault("property_age_years", None)

        return features

    def _fetch_property_map(self, parcel_ids: list[str]) -> dict[str, Property]:
        """Fetch properties and related records in a single query."""
        if not parcel_ids:
            return {}

        query = (
            select(Property)
            .options(
                joinedload(Property.property_record),
                joinedload(Property.tax_sale),
                joinedload(Property.foreclosure),
            )
            .where(Property.parcel_id_normalized.in_(parcel_ids))
            .where(Property.is_active == True)
        )
        properties = self.session.execute(query).scalars().all()
        return {prop.parcel_id_normalized: prop for prop in properties}

    def _count_open_violations(self, enriched: dict) -> int:
        """Count open/active violations from enriched data."""
        nearby_open = enriched.get("nearby_open_violations")
        if nearby_open is not None:
            try:
                return int(nearby_open)
            except (TypeError, ValueError):
                pass

        # Check if violation_types includes open indicators
        violation_types = enriched.get("violation_types", [])
        if isinstance(violation_types, list):
            return len([v for v in violation_types if "OPEN" in str(v).upper()])
        return 0

    def _compute_days_since_violation(self, enriched: dict, today: date) -> Optional[int]:
        """Compute days since most recent violation."""
        most_recent = enriched.get("most_recent_violation")
        if not most_recent:
            return None

        if isinstance(most_recent, str):
            try:
                most_recent = date.fromisoformat(most_recent[:10])
            except (ValueError, TypeError):
                return None

        delta = today - most_recent
        return max(0, delta.days)

    def _compute_violation_severity(self, enriched: dict, today: date) -> float:
        """
        Compute maximum violation severity score.

        Higher scores indicate more severe distress:
        - More violations = higher severity
        - Recent violations = higher severity
        - Open violations = higher severity
        """
        base_score = min(100.0, enriched.get("violation_count", 0) * 10.0)

        # Recency boost
        days_since = self._compute_days_since_violation(enriched, today)
        if days_since is not None and days_since < 90:
            base_score += 20.0
        elif days_since is not None and days_since < 180:
            base_score += 10.0

        # Open violations boost
        open_count = self._count_open_violations(enriched)
        base_score += open_count * 15.0

        return min(100.0, base_score)

    def _encode_categorical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Encode categorical features (city, zip_code) as integers.

        Uses label encoding for ML model compatibility.
        """
        if "city" in df.columns:
            # Build encoder if not exists
            if not self._city_encoder:
                unique_cities = df["city"].dropna().unique()
                self._city_encoder = {city: i for i, city in enumerate(sorted(unique_cities))}

            df["city_encoded"] = df["city"].map(self._city_encoder).fillna(-1).astype(int)

        if "zip_code" in df.columns:
            if not self._zip_encoder:
                unique_zips = df["zip_code"].dropna().unique()
                self._zip_encoder = {zip_code: i for i, zip_code in enumerate(sorted(unique_zips))}

            df["zip_code_encoded"] = df["zip_code"].map(self._zip_encoder).fillna(-1).astype(int)

        # Drop raw categorical columns
        df = df.drop(columns=["city", "zip_code"], errors="ignore")

        return df

    def export_to_parquet(self, output_path: str = "features/lead_training.parquet") -> str:
        """
        Export feature DataFrame to parquet file.

        Args:
            output_path: Path to output parquet file.

        Returns:
            Absolute path to created file.
        """
        df = self.build_feature_dataframe()

        if df.empty:
            logger.warning("empty_dataframe_not_exported")
            return ""

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Add timestamp to filename if it's the standard path
        if output_path == "features/lead_training.parquet":
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_file.parent / f"lead_training_{timestamp}.parquet"

        df.to_parquet(output_file, index=False)
        logger.info("features_exported_to_parquet", path=str(output_file), rows=len(df))

        return str(output_file.absolute())

    def materialize_to_database(self) -> dict:
        """
        Materialize features to ml_feature_store table in database.

        Returns:
            Statistics dict with processed, inserted, failed counts.
        """
        df = self.build_feature_dataframe()

        if df.empty:
            logger.warning("empty_dataframe_not_materialized")
            return {"processed": 0, "inserted": 0, "failed": 0}

        stats = {"processed": len(df), "inserted": 0, "failed": 0}

        for _, row in df.iterrows():
            try:
                feature_record = MLFeatureStore(
                    parcel_id_normalized=row["parcel_id_normalized"],
                    computed_at=row["computed_at"],
                    violation_count=row.get("violation_count"),
                    open_violation_count=row.get("open_violation_count"),
                    days_since_last_violation=row.get("days_since_last_violation"),
                    max_violation_severity=row.get("max_violation_severity"),
                    total_market_value=row.get("total_market_value"),
                    equity_percent=row.get("equity_percent"),
                    tax_rate=row.get("tax_rate"),
                    default_amount=row.get("default_amount"),
                    opening_bid=row.get("opening_bid"),
                    days_to_auction=row.get("days_to_auction"),
                    days_to_tax_sale=row.get("days_to_tax_sale"),
                    property_age_years=row.get("property_age_years"),
                    seed_type_tax_sale=row.get("seed_type_tax_sale", False),
                    seed_type_foreclosure=row.get("seed_type_foreclosure", False),
                    seed_type_code_violation=row.get("seed_type_code_violation", False),
                    city_encoded=row.get("city_encoded"),
                    zip_code_encoded=row.get("zip_code_encoded"),
                    nearby_violations_count=row.get("nearby_violations_count"),
                    nearest_violation_distance=row.get("nearest_violation_distance"),
                )
                self.session.add(feature_record)
                stats["inserted"] += 1

            except Exception as e:
                logger.error(
                    "feature_materialization_failed",
                    parcel_id=row.get("parcel_id_normalized"),
                    error=str(e),
                )
                stats["failed"] += 1

        self.session.commit()
        logger.info("features_materialized_to_database", stats=stats)

        return stats

    def get_feature_vector(self, enriched_data: dict, seed_type: str = "code_violation") -> dict:
        """
        Get a single feature vector for real-time inference.

        Args:
            enriched_data: Enriched seed data dictionary.
            seed_type: Type of seed (tax_sale, foreclosure, code_violation).

        Returns:
            Dictionary of features ready for ML model inference.
        """
        today = date.today()

        features = {
            "violation_count": enriched_data.get("violation_count", 0) or 0,
            "open_violation_count": self._count_open_violations(enriched_data),
            "days_since_last_violation": self._compute_days_since_violation(enriched_data, today),
            "max_violation_severity": self._compute_violation_severity(enriched_data, today),
            "seed_type_tax_sale": seed_type == "tax_sale",
            "seed_type_foreclosure": seed_type == "foreclosure",
            "seed_type_code_violation": seed_type == "code_violation",
            "nearby_violations_count": enriched_data.get("geo_nearby_violations", 0) or 0,
            "nearest_violation_distance": enriched_data.get("geo_nearest_violation_distance"),
        }

        # Add property record features if available
        prop_record = enriched_data.get("property_record", {})
        if prop_record:
            features["total_market_value"] = prop_record.get("total_mkt")
            features["equity_percent"] = prop_record.get("equity_percent")
            features["tax_rate"] = prop_record.get("tax_rate")
            if prop_record.get("year_built"):
                features["property_age_years"] = today.year - prop_record["year_built"]

        # Default missing values
        features.setdefault("total_market_value", None)
        features.setdefault("equity_percent", None)
        features.setdefault("tax_rate", None)
        features.setdefault("property_age_years", None)
        features.setdefault("default_amount", None)
        features.setdefault("opening_bid", None)
        features.setdefault("days_to_auction", None)
        features.setdefault("days_to_tax_sale", None)

        return features
