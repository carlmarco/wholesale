"""
Integrated Data Pipeline

Fetches tax sale properties and enriches with code enforcement violations
to identify high-value wholesale opportunities.
"""
from tax_sale_scraper import TaxSaleScraper
from enrichment import PropertyEnricher


def main():
    """
    Run the complete data enrichment pipeline.

    Steps:
    1. Fetch tax sale properties from ArcGIS API
    2. Load code enforcement violation data
    3. Cross-reference and enrich properties
    4. Identify and display top wholesale opportunities
    """

    print("="*80)
    print("REAL ESTATE WHOLESALE OPPORTUNITY PIPELINE")
    print("="*80)
    print("\nPhase 1: Fetching Tax Sale Properties...")
    print("-" * 80)

    # Step 1: Fetch tax sale properties
    scraper = TaxSaleScraper()
    properties = scraper.fetch_properties(limit=10)

    if not properties:
        print("[ERROR] No properties fetched. Exiting.")
        return

    print(f"[SUCCESS] Fetched {len(properties)} tax sale properties\n")

    # Step 2: Load and enrich with code enforcement data
    print("Phase 2: Enriching with Code Enforcement Data...")
    print("-" * 80)

    enricher = PropertyEnricher('data/code_enforcement_data.csv')
    enriched_properties = enricher.enrich_properties(properties)

    print(f"[SUCCESS] Enrichment complete\n")

    # Step 3: Display summary statistics
    enricher.display_summary_stats(enriched_properties)

    # Step 4: Get and display top opportunities
    print("Phase 3: Identifying Top Wholesale Opportunities...")
    print("-" * 80)

    opportunities = enricher.get_top_opportunities(
        enriched_properties,
        min_violations=1
    )

    if opportunities:
        print(f"\n[ANALYSIS] Found {len(opportunities)} properties with code violations")
        print("="*80)

        for idx, prop in enumerate(opportunities, 1):
            enricher.display_enriched_property(prop, idx)

        print(f"\n{'='*80}")
        print("PIPELINE COMPLETE")
        print(f"{'='*80}\n")

        # Investment strategy insights
        print("INVESTMENT STRATEGY:")
        print("   1. Properties with violations indicate motivated sellers")
        print("   2. Tax sale + violations = maximum distress")
        print("   3. Focus on properties with open violations for negotiation leverage")
        print("   4. Use violation data to estimate repair costs")
        print()

    else:
        print("\n[INFO] No properties found with code violations in this sample.")
        print("       Recommendation: Fetch more properties or expand search criteria\n")

        # Still display all properties
        print("All Tax Sale Properties:")
        print("="*80)
        for idx, prop in enumerate(enriched_properties, 1):
            enricher.display_enriched_property(prop, idx)

        print(f"\n{'='*80}")
        print("DEBUGGING INFO")
        print(f"{'='*80}")
        print("No matches found between tax sale and code enforcement parcels.")
        print("This could indicate:")
        print("  - Different parcel ID systems being used")
        print("  - Tax sale properties are in different jurisdiction")
        print("  - Need to fetch more properties to find matches")
        print("\nTax sale sample parcel: ", enriched_properties[0]['parcel_id'])
        print("Normalized:", enriched_properties[0]['parcel_id_normalized'])
        print()


if __name__ == "__main__":
    main()
