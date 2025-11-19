"""
Check how many properties are missing property records.

Quick diagnostic script to see if backfill is needed.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.wholesaler.db import get_db_session
from src.wholesaler.db.models import Property, PropertyRecord

def check_missing_records():
    """Check how many properties need property records."""
    with get_db_session() as session:
        # Count total properties
        total_properties = session.query(Property).filter(Property.is_active == True).count()

        # Count properties WITH property records
        properties_with_records = (
            session.query(Property)
            .join(PropertyRecord, Property.parcel_id_normalized == PropertyRecord.parcel_id_normalized)
            .filter(Property.is_active == True)
            .count()
        )

        # Count properties WITHOUT property records
        properties_without_records = total_properties - properties_with_records

        print("\n" + "="*60)
        print("PROPERTY RECORDS COVERAGE CHECK")
        print("="*60)
        print(f"Total active properties:          {total_properties:,}")
        print(f"Properties WITH records:          {properties_with_records:,}")
        print(f"Properties WITHOUT records:       {properties_without_records:,}")
        print(f"Coverage:                         {(properties_with_records/total_properties*100 if total_properties > 0 else 0):.1f}%")
        print("="*60 + "\n")

        if properties_without_records > 0:
            # Show sample of parcels missing records
            print("Sample parcels missing records (first 10):")
            missing = (
                session.query(Property.parcel_id_normalized, Property.situs_address)
                .outerjoin(PropertyRecord, Property.parcel_id_normalized == PropertyRecord.parcel_id_normalized)
                .filter(PropertyRecord.parcel_id_normalized == None)
                .filter(Property.parcel_id_normalized != None)
                .filter(Property.is_active == True)
                .limit(10)
                .all()
            )

            for parcel_id, address in missing:
                print(f"  - {parcel_id}: {address}")
            print()

if __name__ == "__main__":
    check_missing_records()
