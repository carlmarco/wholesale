"""
Seed record definitions for ingestion pipeline.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


@dataclass
class SeedRecord:
    """Normalized representation of a candidate property prior to enrichment."""

    parcel_id: Optional[str]
    seed_type: str  # e.g., "tax_sale", "code_violation", "foreclosure"
    source_payload: Dict
    ingested_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Dict representation used by downstream enrichment."""
        return {
            "parcel_id": self.parcel_id,
            "seed_type": self.seed_type,
            "ingested_at": self.ingested_at.isoformat(),
            "source_payload": self.source_payload,
        }
