import sys
import os
from datetime import datetime
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.wholesaler.enrichment.pipeline import UnifiedEnrichmentPipeline
from src.wholesaler.ingestion.seed_models import SeedRecord
from src.wholesaler.utils.logger import setup_logging

def test_enrichment():
    setup_logging()
    
    # Create a dummy tax sale seed
    # Using a known parcel ID from the probe_arcgis.py output or a common one
    # The probe output showed: USER_PARCEL: 29-22-28-8850-02-050
    parcel_id = "29-22-28-8850-02-050"
    
    seed = SeedRecord(
        parcel_id=parcel_id,
        seed_type="tax_sale",
        ingested_at=datetime.now(),
        source_payload={
            "USER_TDA_NUM": "2023-4348",
            "USER_Sale_Date": "12/18/2025",
            "USER_Deed_Status": "Active Sale",
            "USER_PARCEL": parcel_id
        }
    )
    
    print(f"Running enrichment for parcel: {parcel_id}")
    
    # Initialize pipeline (disable geo for speed/simplicity if not needed for this test, 
    # but we want to test property scraper integration)
    pipeline = UnifiedEnrichmentPipeline(enable_geo=False)
    
    # Run enrichment
    results = pipeline.run([seed])
    
    if not results:
        print("No results returned!")
        return
        
    record = results[0]
    print("\nEnriched Record:")
    print(f"Parcel ID: {record.get('parcel_id')}")
    print(f"Address: {record.get('situs_address')}")
    print(f"City: {record.get('city')}")
    print(f"Zip: {record.get('zip_code')}")
    
    prop_record = record.get('property_record', {})
    print("\nProperty Record Details:")
    print(f"Market Value: {prop_record.get('total_mkt')}")
    print(f"Assessed Value: {prop_record.get('total_assd')}")
    print(f"Year Built: {prop_record.get('year_built')}")
    
    # Assertions
    if record.get('situs_address'):
        print("\nSUCCESS: Address fetched!")
    else:
        print("\nFAILURE: Address missing.")
        
    if prop_record.get('total_mkt'):
        print("SUCCESS: Market value fetched!")
    else:
        print("FAILURE: Market value missing.")

if __name__ == "__main__":
    test_enrichment()
