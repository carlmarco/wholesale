"""
Mock API Client for Streamlit Demo Mode

Allows the frontend to run without a live backend by returning static mock data.
"""
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import json
from pathlib import Path

class MockAPIClient:
    """Mock client that serves exported real data."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = "mock://localhost"
        self._load_data()

    def _load_data(self):
        """Load exported demo data."""
        try:
            # Resolve path relative to this file (src/wholesaler/frontend/utils/mock_api_client.py)
            # Data is in src/wholesaler/frontend/data/demo_leads.json
            current_dir = Path(__file__).parent.resolve()
            data_path = current_dir.parent / "data" / "demo_leads.json"
            
            if not data_path.exists():
                print(f"Warning: Demo data file not found at {data_path}")
                self.data = {"leads": [], "stats": {}}
                return

            with open(data_path, "r") as f:
                self.data = json.load(f)
        except Exception as e:
            print(f"Error loading demo data: {e}")
            self.data = {"leads": [], "stats": {}}

    def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "version": "0.3.0-demo-static"}

    def get_dashboard_stats(self) -> Dict[str, Any]:
        return self.data.get("stats", {
            "total_leads": 0,
            "tier_a_count": 0,
            "tier_b_count": 0,
            "tier_c_count": 0,
            "tier_d_count": 0,
            "recent_tier_a_count": 0,
            "avg_score_tier_a": 0.0,
            "total_properties": 0,
            "properties_with_tax_sales": 0,
            "properties_with_foreclosures": 0
        })

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
        view: str = "hybrid",
    ) -> List[Dict[str, Any]]:
        leads = self.data.get("leads", [])
        
        # Filter by tier
        if tier:
            leads = [l for l in leads if l["tier"] == tier]
            
        # Filter by score
        if min_score is not None:
            leads = [l for l in leads if l["total_score"] >= min_score]
        if max_score is not None:
            leads = [l for l in leads if l["total_score"] <= max_score]
            
        # Filter by city
        if city:
            leads = [l for l in leads if l["city"].lower() == city.lower()]
            
        # Filter by zip
        if zip_code:
            leads = [l for l in leads if str(l["zip_code"]) == str(zip_code)]
            
        # Sort
        reverse = sort_order == "desc"
        try:
            leads.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
        except:
            pass
            
        # Paginate
        return leads[offset : offset + limit]

    def get_lead_detail(self, parcel_id: str) -> Dict[str, Any]:
        leads = self.data.get("leads", [])
        for lead in leads:
            if lead["parcel_id_normalized"] == parcel_id:
                return lead
        return {}

    def get_lead_history(self, parcel_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        # Return mock history since we don't export full history
        return []

    def get_property_detail(self, parcel_id: str) -> Dict[str, Any]:
        leads = self.data.get("leads", [])
        for lead in leads:
            if lead["parcel_id_normalized"] == parcel_id:
                return lead.get("property", {})
        return {}
