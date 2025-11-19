#!/usr/bin/env python3
"""
Verify profitability data was saved to database.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import get_db_session
from sqlalchemy import text

with get_db_session() as session:
    result = session.execute(text('''
        SELECT 
            parcel_id_normalized, 
            total_score, 
            tier, 
            profitability_score,
            profitability_details
        FROM lead_scores 
        WHERE profitability_score IS NOT NULL 
        LIMIT 5
    '''))
    
    print('Profitability Data Verification')
    print('=' * 80)
    
    rows = result.fetchall()
    if not rows:
        print('❌ No profitability data found')
    else:
        print(f'✅ Found {len(rows)} leads with profitability data\n')
        for row in rows:
            print(f'Parcel: {row[0]}')
            print(f'  Score: {row[1]:.1f} | Tier: {row[2]}')
            print(f'  Profitability Score: {row[3]:.1f}')
            if row[4]:
                details = row[4]
                print(f'  Projected Profit: ${details.get("projected_profit", 0):,.2f}')
                print(f'  Is Profitable: {details.get("is_profitable", False)}')
                print(f'  ROI: {details.get("roi_percent", 0):.1f}%')
            print()
    
    # Count total
    count_result = session.execute(text('SELECT COUNT(*) FROM lead_scores WHERE profitability_score IS NOT NULL'))
    total = count_result.scalar()
    print(f'\nTotal leads with profitability data: {total}')
