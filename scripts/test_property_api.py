"""
Test Property Appraiser API to diagnose 403 errors.

Tries different approaches to fetch a single property record.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from src.wholesaler.db import get_db_session
from src.wholesaler.db.models import Property

def test_api_access():
    """Test different API request methods."""

    # Get a sample parcel ID
    with get_db_session() as session:
        sample_property = (
            session.query(Property.parcel_id_normalized, Property.situs_address)
            .filter(Property.is_active == True)
            .filter(Property.parcel_id_normalized != None)
            .first()
        )

        if not sample_property:
            print("No properties found in database!")
            return

        parcel_id, address = sample_property
        print(f"\nTesting with parcel: {parcel_id}")
        print(f"Address: {address}\n")

    base_url = "https://ocgis4.ocfl.net/arcgis/rest/services/Public_Dynamic/MapServer/216/query"

    # Test 1: Simple query with 1=1
    print("=" * 60)
    print("TEST 1: Simple query (1=1, limit 5)")
    print("=" * 60)

    params1 = {
        "where": "1=1",
        "outFields": "PARCEL,SITUS,TOTAL_MKT",
        "outSR": 4326,
        "f": "json",
        "resultRecordCount": 5
    }

    try:
        response1 = requests.get(base_url, params=params1, timeout=30)
        print(f"Status: {response1.status_code}")
        if response1.status_code == 200:
            data = response1.json()
            print(f"Features returned: {len(data.get('features', []))}")
            if data.get('features'):
                print(f"Sample: {data['features'][0]['attributes']}")
        else:
            print(f"Error: {response1.text[:200]}")
    except Exception as e:
        print(f"Exception: {e}")

    print()

    # Test 2: Query by single parcel
    print("=" * 60)
    print(f"TEST 2: Query by single parcel ({parcel_id})")
    print("=" * 60)

    params2 = {
        "where": f"PARCEL = '{parcel_id}'",
        "outFields": "PARCEL,SITUS,TOTAL_MKT,NAME1",
        "outSR": 4326,
        "f": "json",
        "returnGeometry": "true"
    }

    try:
        response2 = requests.get(base_url, params=params2, timeout=30)
        print(f"Status: {response2.status_code}")
        if response2.status_code == 200:
            data = response2.json()
            print(f"Features returned: {len(data.get('features', []))}")
            if data.get('features'):
                print(f"Found: {data['features'][0]['attributes']}")
            else:
                print("No results found for this parcel")
        else:
            print(f"Error: {response2.text[:200]}")
    except Exception as e:
        print(f"Exception: {e}")

    print()

    # Test 3: Query with IN clause (small list)
    print("=" * 60)
    print("TEST 3: Query with IN clause (3 parcels)")
    print("=" * 60)

    # Get 3 sample parcels
    with get_db_session() as session:
        sample_parcels = (
            session.query(Property.parcel_id_normalized)
            .filter(Property.is_active == True)
            .filter(Property.parcel_id_normalized != None)
            .limit(3)
            .all()
        )
        parcel_list = [p.parcel_id_normalized for p in sample_parcels]

    parcel_in_clause = "','".join(parcel_list)
    params3 = {
        "where": f"PARCEL IN ('{parcel_in_clause}')",
        "outFields": "PARCEL,SITUS,TOTAL_MKT",
        "outSR": 4326,
        "f": "json",
        "returnGeometry": "true"
    }

    try:
        response3 = requests.get(base_url, params=params3, timeout=30)
        print(f"Status: {response3.status_code}")
        print(f"URL length: {len(response3.url)} characters")
        if response3.status_code == 200:
            data = response3.json()
            print(f"Features returned: {len(data.get('features', []))}")
        else:
            print(f"Error: {response3.text[:200]}")
    except Exception as e:
        print(f"Exception: {e}")

    print()

    # Test 4: Check if endpoint requires token
    print("=" * 60)
    print("TEST 4: Check endpoint capabilities")
    print("=" * 60)

    info_url = "https://ocgis4.ocfl.net/arcgis/rest/services/Public_Dynamic/MapServer/216?f=json"

    try:
        response4 = requests.get(info_url, timeout=10)
        print(f"Status: {response4.status_code}")
        if response4.status_code == 200:
            data = response4.json()
            print(f"Layer Name: {data.get('name')}")
            print(f"Type: {data.get('type')}")
            if 'capabilities' in data:
                print(f"Capabilities: {data['capabilities']}")
            if 'supportedQueryFormats' in data:
                print(f"Query Formats: {data['supportedQueryFormats']}")
    except Exception as e:
        print(f"Exception: {e}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_api_access()
