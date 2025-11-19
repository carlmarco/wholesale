"""
Export Data for Demo Dashboard

Exports a subset of real data to JSON for use in the static demo.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.db.models import LeadScore, Property
from sqlalchemy import select
from sqlalchemy.orm import joinedload

def export_demo_data():
    """Export 50 leads to demo_data.json"""
    print("Exporting demo data...")
    
    with get_db_session() as session:
        # Query top 50 leads with property data
        query = (
            select(LeadScore)
            .options(joinedload(LeadScore.property))
            .order_by(LeadScore.total_score.desc())
            .limit(50)
        )
        
        leads = session.execute(query).scalars().all()
        print(f"Found {len(leads)} leads")
        
        export_data = []
        for lead in leads:
            # Serialize lead data
            lead_dict = {
                "parcel_id_normalized": lead.parcel_id_normalized,
                "total_score": float(lead.total_score) if lead.total_score else 0.0,
                "tier": lead.tier,
                "distress_score": float(lead.distress_score) if lead.distress_score else 0.0,
                "value_score": float(lead.value_score) if lead.value_score else 0.0,
                "location_score": float(lead.location_score) if lead.location_score else 0.0,
                "urgency_score": float(lead.urgency_score) if lead.urgency_score else 0.0,
                "profitability_score": float(lead.profitability_score) if lead.profitability_score else 0.0,
                "scored_at": lead.scored_at.isoformat() if lead.scored_at else datetime.now().isoformat(),
                "reasons": lead.reasons,
                "profitability_details": lead.profitability_details,
                
                # Flatten property details for list view
                "situs_address": lead.property.situs_address if lead.property else "Unknown",
                "city": lead.property.city if lead.property else "Unknown",
                "zip_code": lead.property.zip_code if lead.property else "Unknown",
                
                # Full property object for detail view
                "property": {
                    "situs_address": lead.property.situs_address if lead.property else "Unknown",
                    "city": lead.property.city if lead.property else "Unknown",
                    "zip_code": lead.property.zip_code if lead.property else "Unknown",
                    "owner_name": "Unknown",
                    "total_market_value": float(lead.property.property_record.total_mkt) if lead.property and lead.property.property_record and lead.property.property_record.total_mkt else 0.0,
                    "year_built": lead.property.property_record.year_built if lead.property and lead.property.property_record else None,
                    "living_area": lead.property.property_record.living_area if lead.property and lead.property.property_record else None,
                    "lot_size": lead.property.property_record.lot_size if lead.property and lead.property.property_record else None,
                }
            }
            export_data.append(lead_dict)
            
        # Calculate stats
        stats = {
            "total_leads": len(leads),
            "tier_a_count": sum(1 for l in leads if l.tier == 'A'),
            "tier_b_count": sum(1 for l in leads if l.tier == 'B'),
            "tier_c_count": sum(1 for l in leads if l.tier == 'C'),
            "tier_d_count": sum(1 for l in leads if l.tier == 'D'),
            "recent_tier_a_count": sum(1 for l in leads if l.tier == 'A'), # Simplified
            "avg_score_tier_a": sum(float(l.total_score) for l in leads if l.tier == 'A') / max(1, sum(1 for l in leads if l.tier == 'A')),
            "total_properties": len(leads),
            "properties_with_tax_sales": 0, # Simplified
            "properties_with_foreclosures": 0 # Simplified
        }
        
        final_output = {
            "stats": stats,
            "leads": export_data,
            "generated_at": datetime.now().isoformat()
        }
        
        # Save to JSON file in frontend directory
        output_path = Path("src/wholesaler/frontend/data/demo_leads.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(final_output, f, indent=2)
            
        print(f"Successfully exported {len(leads)} leads to {output_path}")

if __name__ == "__main__":
    export_demo_data()
