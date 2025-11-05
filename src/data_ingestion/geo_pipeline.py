"""
Geographic Enrichment Pipeline

Fetches tax sale properties and enriches with code enforcement violations
using geographic proximity matching.
"""
from tax_sale_scraper import TaxSaleScraper
from geo_enrichment import GeoPropertyEnricher


def main():
    """
    Run the complete geographic enrichment pipeline.

    Steps:
    1. Fetch tax sale properties from ArcGIS API
    2. Load and convert code enforcement coordinates
    3. Find violations within radius of each property
    4. Display results and investment opportunities
    """

    print("="*80)
    print("REAL ESTATE WHOLESALE - GEOGRAPHIC ENRICHMENT PIPELINE")
    print("="*80)

    # Step 1: Fetch tax sale properties
    print("\nPhase 1: Fetching Tax Sale Properties...")
    print("-" * 80)

    scraper = TaxSaleScraper()
    properties = scraper.fetch_properties(limit=None)  # Get all properties

    if not properties:
        print("[ERROR] No properties fetched. Exiting.")
        return

    print(f"[SUCCESS] Fetched {len(properties)} tax sale properties\n")

    # Step 2: Geographic enrichment
    print("Phase 2: Geographic Enrichment with Code Violations...")
    print("-" * 80)

    # Use 0.25 mile radius (about 4-5 city blocks)
    enricher = GeoPropertyEnricher('data/code_enforcement_data.csv', radius_miles=0.25)
    enriched_properties = enricher.enrich_properties(properties)

    print(f"[SUCCESS] Enrichment complete\n")

    # Step 3: Summary statistics
    print("="*80)
    print("ENRICHMENT SUMMARY")
    print("="*80)

    total = len(enriched_properties)
    with_violations = sum(1 for p in enriched_properties if p['nearby_violations'] > 0)
    total_violations = sum(p['nearby_violations'] for p in enriched_properties)
    total_open = sum(p['nearby_open_violations'] for p in enriched_properties)

    print(f"  Total Properties:              {total}")
    print(f"  Properties with Nearby Issues: {with_violations} ({with_violations/total*100:.1f}%)")
    print(f"  Total Nearby Violations:       {total_violations}")
    print(f"  Total Open Nearby:             {total_open}")
    print(f"  Avg Nearby per Property:       {total_violations/total:.1f}")
    print(f"  Search Radius:                 0.25 miles (~4-5 city blocks)")
    print("="*80 + "\n")

    # Step 4: Identify top opportunities
    print("Phase 3: Identifying High-Distress Areas...")
    print("-" * 80)

    # Sort by violation count (high violations = distressed area)
    opportunities = [p for p in enriched_properties if p['nearby_violations'] > 0]
    opportunities.sort(key=lambda x: x['nearby_violations'], reverse=True)

    if opportunities:
        print(f"\n[ANALYSIS] Found {len(opportunities)} properties in areas with violations")
        print("\nTop 10 Properties in Most Distressed Areas:")
        print("="*80)

        for idx, prop in enumerate(opportunities[:10], 1):
            enricher.display_enriched_property(prop, idx)

        # Investment insights
        print(f"\n{'='*80}")
        print("INVESTMENT STRATEGY - GEOGRAPHIC ANALYSIS")
        print(f"{'='*80}")
        print("\nKey Findings:")
        print(f"  - {with_violations/total*100:.1f}% of tax sale properties are in areas with code violations")
        print(f"  - Average {total_violations/total:.1f} violations within 0.25 miles of each property")

        print("\nInvestment Considerations:")
        print("  1. HIGH VIOLATION DENSITY (100+ nearby):")
        print("     - May indicate neighborhood decline")
        print("     - Lower property values, but higher risk")
        print("     - Good for fix-and-hold or land banking")

        print("\n  2. MODERATE VIOLATIONS (20-100 nearby):")
        print("     - Mixed neighborhood conditions")
        print("     - Opportunity for value-add renovations")
        print("     - Best for wholesale flips")

        print("\n  3. LOW VIOLATIONS (1-20 nearby):")
        print("     - Stable neighborhoods with isolated issues")
        print("     - Lower wholesale margins but faster turnover")
        print("     - Good for beginner investors")

        print("\n  4. NO NEARBY VIOLATIONS:")
        print("     - Better neighborhoods (less distress)")
        print("     - Tax sale may be due to other factors (death, divorce, etc.)")
        print("     - Requires different analysis approach")

        print("\nNext Steps:")
        print("  - Visit top 5 properties for physical inspection")
        print("  - Cross-reference with property assessor data")
        print("  - Analyze recent sales comps in area")
        print("  - Calculate repair estimates based on violation types")
        print()

    else:
        print("\n[INFO] No properties found with nearby violations.")
        print("       All tax sale properties are in low-violation areas.\n")

        # Still show sample
        print("Sample Properties (No Nearby Violations):")
        print("="*80)
        for idx, prop in enumerate(enriched_properties[:5], 1):
            enricher.display_enriched_property(prop, idx)

    print(f"\n{'='*80}")
    print("PIPELINE COMPLETE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
