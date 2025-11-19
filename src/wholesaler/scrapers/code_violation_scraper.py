"""
Code Enforcement Violation Scraper

Pulls violation records from the City of Orlando Socrata API.
"""
from typing import List, Optional, Dict

import pandas as pd
from sodapy import Socrata

from config.settings import settings
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class CodeViolationScraper:
    """
    Scraper for Orlando code enforcement violations (Socrata dataset).
    """

    def __init__(
        self,
        dataset_id: Optional[str] = None,
        domain: Optional[str] = None,
        page_size: int = 50000,
    ):
        """
        Initialize the Socrata client.

        Args:
            dataset_id: Override default dataset identifier
            domain: Override Socrata domain
            page_size: Records to pull per request
        """
        self.dataset_id = dataset_id or settings.socrata_code_violations_dataset
        self.domain = domain or settings.socrata_domain
        self.page_size = page_size

        if not self.dataset_id:
            raise ValueError("Socrata dataset id is required")

        logger.info(
            "code_violation_scraper_initialized",
            domain=self.domain,
            dataset=self.dataset_id,
            page_size=self.page_size,
        )

        self.client = Socrata(
            self.domain,
            app_token=settings.socrata_app_token,
            username=settings.socrata_api_key,
            password=settings.socrata_api_secret,
            timeout=30,
        )

    def fetch_violations(
        self,
        limit: Optional[int] = None,
        where: Optional[str] = None,
        order: Optional[str] = "casedt DESC",
    ) -> pd.DataFrame:
        """
        Fetch violation records from Socrata.

        Args:
            limit: Max records to fetch (None = all available)
            where: Optional Socrata where clause
            order: Order clause (default newest first)

        Returns:
            pandas.DataFrame with violation records
        """
        records: List[Dict] = []
        offset = 0

        logger.info(
            "fetching_code_violations",
            limit=limit if limit else "all",
            where=where or "all",
            order=order,
        )

        while True:
            batch_limit = self._next_batch_size(limit, offset)
            if batch_limit == 0:
                break

            batch = self.client.get(
                self.dataset_id,
                limit=batch_limit,
                offset=offset,
                where=where,
                order=order,
            )

            if not batch:
                break

            records.extend(batch)
            offset += len(batch)

            if len(batch) < batch_limit:
                break

        if not records:
            logger.warning("no_code_violation_records_fetched")
            return pd.DataFrame()

        df = pd.DataFrame.from_records(records)
        logger.info("code_violations_fetched", total=len(df))

        return df

    def _next_batch_size(self, limit: Optional[int], offset: int) -> int:
        """Determine next batch size respecting caller limit."""
        if limit is None:
            return self.page_size
        remaining = max(limit - offset, 0)
        return min(self.page_size, remaining)

