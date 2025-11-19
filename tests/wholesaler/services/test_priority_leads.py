import sys
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wholesaler.db.base import Base
from src.wholesaler.db.models import EnrichedSeed
from src.wholesaler.services.priority_leads import PriorityLeadService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def test_priority_lead_service_filters_high_priority(session):
    high_priority_payload = {
        "seed_type": "code_violation",
        "violation_count": 15,
        "open_violations": 5,
        "most_recent_violation": "2025-01-15",
        "property_record": {"equity_percent": 180, "total_mkt": 200000},
    }
    low_priority_payload = {
        "seed_type": "code_violation",
        "violation_count": 1,
        "property_record": {"equity_percent": 100, "total_mkt": 100000},
    }

    session.add_all(
        [
            EnrichedSeed(
                parcel_id_normalized="123",
                seed_type="code_violation",
                violation_count=15,
                enriched_data=json.dumps(high_priority_payload),
            ),
            EnrichedSeed(
                parcel_id_normalized="999",
                seed_type="code_violation",
                violation_count=1,
                enriched_data=json.dumps(low_priority_payload),
            ),
        ]
    )
    session.commit()

    service = PriorityLeadService(session)
    results = service.get_priority_leads(limit=10)

    assert len(results) == 1
    assert results[0]["parcel_id_normalized"] == "123"
    assert results[0]["priority_score"] > 0
