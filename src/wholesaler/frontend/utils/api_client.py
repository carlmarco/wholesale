"""
API Client for Streamlit Frontend

Handles all HTTP requests to the FastAPI backend.
"""
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime


class APIClient:
    """Client for interacting with Wholesaler API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize API client.

        Args:
            base_url: Base URL for API endpoints (default: http://localhost:8000)
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make GET request to API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def health_check(self) -> Dict[str, Any]:
        """
        Check API health.

        Returns:
            Health check response
        """
        return self._get("/health")

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """
        Get dashboard statistics.

        Returns:
            Dashboard stats including tier counts and averages
        """
        return self._get("/api/v1/stats/dashboard")

    def list_leads(
        self,
        tier: Optional[str] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        city: Optional[str] = None,
        zip_code: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "total_score",
        sort_order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        List leads with filtering and pagination.

        Args:
            tier: Filter by tier (A, B, C, D)
            min_score: Minimum total score
            max_score: Maximum total score
            city: Filter by city
            zip_code: Filter by ZIP code
            limit: Number of results (max 1000)
            offset: Pagination offset
            sort_by: Sort field (total_score, scored_at, situs_address)
            sort_order: Sort order (asc, desc)

        Returns:
            List of lead scores
        """
        params = {
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }

        if tier:
            params["tier"] = tier
        if min_score is not None:
            params["min_score"] = min_score
        if max_score is not None:
            params["max_score"] = max_score
        if city:
            params["city"] = city
        if zip_code:
            params["zip_code"] = zip_code

        return self._get("/api/v1/leads/", params=params)

    def get_lead_detail(self, parcel_id: str) -> Dict[str, Any]:
        """
        Get detailed lead information.

        Args:
            parcel_id: Normalized parcel ID

        Returns:
            Detailed lead score with property info
        """
        return self._get(f"/api/v1/leads/{parcel_id}")

    def get_lead_history(self, parcel_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Get historical score snapshots for a lead.

        Args:
            parcel_id: Normalized parcel ID
            limit: Number of historical records (max 100)

        Returns:
            List of historical snapshots
        """
        params = {"limit": limit}
        return self._get(f"/api/v1/leads/{parcel_id}/history", params=params)

    def get_property_detail(self, parcel_id: str) -> Dict[str, Any]:
        """
        Get detailed property information.

        Args:
            parcel_id: Normalized parcel ID

        Returns:
            Detailed property info
        """
        return self._get(f"/api/v1/properties/{parcel_id}")
