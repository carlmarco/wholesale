"""
Model Registry Utility

Manages ML model versions, tracks metadata, and handles model promotion.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select, and_, update
from sqlalchemy.orm import Session

from src.wholesaler.db.models import ModelRegistry
from src.wholesaler.db.session import get_db_session
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class ModelRegistryManager:
    """
    Manages model artifacts and metadata in the database.

    Provides functionality for:
    - Registering new model versions
    - Promoting models to production
    - Retrieving active models
    - Cleaning up old versions
    """

    def __init__(self, session: Optional[Session] = None):
        """Initialize with optional session."""
        self._session = session
        self._owned_session = False

    def __enter__(self):
        if self._session is None:
            self._session_ctx = get_db_session()
            self._session = self._session_ctx.__enter__()
            self._owned_session = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owned_session:
            self._session_ctx.__exit__(exc_type, exc_val, exc_tb)

    def register_model(
        self,
        model_name: str,
        version: str,
        artifact_path: str,
        training_date: datetime,
        training_samples: Optional[int] = None,
        feature_names: Optional[list] = None,
        hyperparameters: Optional[dict] = None,
        metrics: Optional[dict] = None,
        validation_metrics: Optional[dict] = None,
        description: Optional[str] = None,
    ) -> ModelRegistry:
        """
        Register a new model version in the registry.

        Args:
            model_name: Name of the model (e.g., distress_classifier).
            version: Version string (e.g., 20241114_120000).
            artifact_path: Path to model artifact file.
            training_date: When model was trained.
            training_samples: Number of training samples.
            feature_names: List of feature names used.
            hyperparameters: Model hyperparameters.
            metrics: Training metrics.
            validation_metrics: Validation metrics.
            description: Model description.

        Returns:
            Created ModelRegistry instance.
        """
        model_record = ModelRegistry(
            model_name=model_name,
            version=version,
            artifact_path=artifact_path,
            training_date=training_date,
            training_samples=training_samples,
            feature_names=feature_names,
            hyperparameters=hyperparameters,
            metrics=metrics,
            validation_metrics=validation_metrics,
            description=description,
            is_active=False,
        )

        self._session.add(model_record)
        self._session.commit()

        logger.info(
            "model_registered",
            model_name=model_name,
            version=version,
            artifact_path=artifact_path,
        )

        return model_record

    def promote_model(self, model_name: str, version: str) -> bool:
        """
        Promote a model version to active/production status.

        Deactivates all other versions of the same model.

        Args:
            model_name: Name of the model.
            version: Version to promote.

        Returns:
            True if successful, False otherwise.
        """
        # Deactivate all current active versions
        deactivate_stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.model_name == model_name,
                    ModelRegistry.is_active == True,
                )
            )
            .values(is_active=False, deprecated_at=datetime.utcnow())
        )
        self._session.execute(deactivate_stmt)

        # Activate the specified version
        activate_stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.model_name == model_name,
                    ModelRegistry.version == version,
                )
            )
            .values(is_active=True, promoted_at=datetime.utcnow())
        )
        result = self._session.execute(activate_stmt)

        self._session.commit()

        if result.rowcount > 0:
            logger.info("model_promoted", model_name=model_name, version=version)
            return True
        else:
            logger.warning(
                "model_promotion_failed",
                model_name=model_name,
                version=version,
                reason="not_found",
            )
            return False

    def get_active_model(self, model_name: str) -> Optional[ModelRegistry]:
        """
        Get the currently active model for a given name.

        Args:
            model_name: Name of the model.

        Returns:
            Active ModelRegistry instance or None.
        """
        query = select(ModelRegistry).where(
            and_(
                ModelRegistry.model_name == model_name,
                ModelRegistry.is_active == True,
            )
        )
        result = self._session.execute(query).scalar_one_or_none()

        if result:
            logger.info(
                "active_model_retrieved",
                model_name=model_name,
                version=result.version,
            )
        else:
            logger.warning("no_active_model_found", model_name=model_name)

        return result

    def get_model_by_version(
        self, model_name: str, version: str
    ) -> Optional[ModelRegistry]:
        """
        Get a specific model version.

        Args:
            model_name: Name of the model.
            version: Version string.

        Returns:
            ModelRegistry instance or None.
        """
        query = select(ModelRegistry).where(
            and_(
                ModelRegistry.model_name == model_name,
                ModelRegistry.version == version,
            )
        )
        return self._session.execute(query).scalar_one_or_none()

    def list_models(self, model_name: Optional[str] = None) -> list[ModelRegistry]:
        """
        List all registered models, optionally filtered by name.

        Args:
            model_name: Optional filter by model name.

        Returns:
            List of ModelRegistry instances.
        """
        if model_name:
            query = (
                select(ModelRegistry)
                .where(ModelRegistry.model_name == model_name)
                .order_by(ModelRegistry.training_date.desc())
            )
        else:
            query = select(ModelRegistry).order_by(
                ModelRegistry.model_name, ModelRegistry.training_date.desc()
            )

        result = self._session.execute(query)
        return list(result.scalars().all())

    def cleanup_old_versions(self, model_name: str, keep_count: int = 5) -> int:
        """
        Remove old model versions, keeping the most recent N.

        Args:
            model_name: Name of the model.
            keep_count: Number of recent versions to keep.

        Returns:
            Number of versions removed.
        """
        # Get all versions ordered by training date
        query = (
            select(ModelRegistry)
            .where(ModelRegistry.model_name == model_name)
            .order_by(ModelRegistry.training_date.desc())
        )
        all_versions = list(self._session.execute(query).scalars().all())

        if len(all_versions) <= keep_count:
            logger.info(
                "no_cleanup_needed",
                model_name=model_name,
                current_count=len(all_versions),
                keep_count=keep_count,
            )
            return 0

        # Delete old versions (keep the newest N)
        versions_to_delete = all_versions[keep_count:]
        deleted_count = 0

        for version_record in versions_to_delete:
            # Don't delete active models
            if version_record.is_active:
                logger.warning(
                    "skipping_active_model_deletion",
                    model_name=model_name,
                    version=version_record.version,
                )
                continue

            # Delete artifact file if exists
            artifact_path = Path(version_record.artifact_path)
            if artifact_path.exists():
                try:
                    artifact_path.unlink()
                    logger.info(
                        "artifact_deleted", path=str(artifact_path)
                    )
                except Exception as e:
                    logger.warning(
                        "artifact_deletion_failed",
                        path=str(artifact_path),
                        error=str(e),
                    )

            # Delete database record
            self._session.delete(version_record)
            deleted_count += 1

        self._session.commit()

        logger.info(
            "old_versions_cleaned",
            model_name=model_name,
            deleted_count=deleted_count,
        )

        return deleted_count

    def update_metrics(
        self,
        model_name: str,
        version: str,
        metrics: Optional[dict] = None,
        validation_metrics: Optional[dict] = None,
    ) -> bool:
        """
        Update metrics for a model version.

        Args:
            model_name: Name of the model.
            version: Version string.
            metrics: New training metrics.
            validation_metrics: New validation metrics.

        Returns:
            True if successful, False otherwise.
        """
        update_values = {}
        if metrics is not None:
            update_values["metrics"] = metrics
        if validation_metrics is not None:
            update_values["validation_metrics"] = validation_metrics

        if not update_values:
            return False

        stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.model_name == model_name,
                    ModelRegistry.version == version,
                )
            )
            .values(**update_values)
        )
        result = self._session.execute(stmt)
        self._session.commit()

        return result.rowcount > 0
