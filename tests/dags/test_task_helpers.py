"""
Helper tests for DAG task utilities.
"""
from types import SimpleNamespace

from dags.daily_lead_scoring import build_property_payload


def test_build_property_payload_counts_violations():
    """build_property_payload should include violation counts and relationships."""
    tax_sale = SimpleNamespace(
        tda_number="2024-001",
        sale_date="2024-03-15",
        deed_status="Active Sale",
        latitude=28.5,
        longitude=-81.3,
    )
    foreclosure = SimpleNamespace(
        borrowers_name="Jane Doe",
        default_amount=150000,
        opening_bid=140000,
        auction_date="2024-04-01",
        lender_name="Bank",
    )
    property_record = SimpleNamespace(
        total_mkt=250000,
        equity_percent=180.0,
        taxes=3200,
        year_built=1990,
        living_area=1800,
        lot_size=7500,
    )
    violations = [
        SimpleNamespace(status="OPEN"),
        SimpleNamespace(status="Closed"),
    ]
    property_obj = SimpleNamespace(
        parcel_id_normalized="1234567890",
        parcel_id_original="12-34-56-7890-00-000",
        situs_address="123 Main St",
        city="Orlando",
        state="FL",
        zip_code="32801",
        seed_type="tax_sale",
        tax_sale=tax_sale,
        foreclosure=foreclosure,
        property_record=property_record,
        code_violations=violations,
    )

    payload = build_property_payload(property_obj)

    assert payload["parcel_id_normalized"] == "1234567890"
    assert payload["tax_sale"]["tda_number"] == "2024-001"
    assert payload["foreclosure"]["default_amount"] == 150000.0
    assert payload["property_record"]["total_mkt"] == 250000.0
    assert payload["violation_count"] == 2
    assert payload["nearby_open_violations"] == 1
