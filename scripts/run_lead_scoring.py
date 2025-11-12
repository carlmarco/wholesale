"""
Run Lead Scoring on All Properties

Scores all properties in the database and saves results to lead_scores table.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import get_db_session
from src.wholesaler.db.repository import PropertyRepository, LeadScoreRepository, EnrichedSeedRepository
from src.wholesaler.pipelines.lead_scoring import LeadScorer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def _score_seed_based_property(prop, seed_repo, scorer, session):
    """
    Score a seed-based property using enriched_data from enriched_seeds table.

    Args:
        prop: Property model instance with seed_type
        seed_repo: EnrichedSeedRepository
        scorer: LeadScorer instance
        session: Database session

    Returns:
        LeadScore or None if enriched_data not found
    """
    # Get primary seed type (handle comma-separated multi-source)
    primary_seed_type = prop.seed_type.split(',')[0]

    # Get enriched seed data from staging table
    from sqlalchemy import select, and_
    from src.wholesaler.db.models import EnrichedSeed

    query = select(EnrichedSeed).where(
        and_(
            EnrichedSeed.parcel_id_normalized == prop.parcel_id_normalized,
            EnrichedSeed.seed_type == primary_seed_type
        )
    )
    enriched_seed = session.execute(query).scalar_one_or_none()

    if not enriched_seed or not enriched_seed.enriched_data:
        logger.warning(
            "enriched_data_not_found",
            parcel_id=prop.parcel_id_normalized,
            seed_type=primary_seed_type
        )
        return None

    # Score using seed-based method
    return scorer.score_seed_based_lead(
        enriched_data=enriched_seed.enriched_data,
        seed_type=primary_seed_type
    )


def _score_legacy_property(prop, scorer):
    """
    Score a legacy property using relationships.

    Args:
        prop: Property model instance
        scorer: LeadScorer instance

    Returns:
        LeadScore
    """
    # Build property dict for scorer
    prop_dict = {
        'parcel_id_normalized': prop.parcel_id_normalized,
        'city': prop.city,
        'zip_code': prop.zip_code,
    }

    # Add tax sale info if exists
    if prop.tax_sale:
        prop_dict['tax_sale'] = {
            'sale_date': prop.tax_sale.sale_date,
            'deed_status': prop.tax_sale.deed_status,
        }

    # Add foreclosure info if exists
    if prop.foreclosure:
        prop_dict['foreclosure'] = {
            'auction_date': prop.foreclosure.auction_date,
            'default_amount': float(prop.foreclosure.default_amount) if prop.foreclosure.default_amount else None,
            'opening_bid': float(prop.foreclosure.opening_bid) if prop.foreclosure.opening_bid else None,
        }

    # Add property record info if exists
    if prop.property_record:
        prop_dict['property_record'] = {
            'total_mkt': float(prop.property_record.total_mkt) if prop.property_record.total_mkt else None,
            'equity_percent': float(prop.property_record.equity_percent) if prop.property_record.equity_percent else None,
            'year_built': prop.property_record.year_built,
        }

    # Score the property
    return scorer.score_lead(prop_dict)


def main():
    """Score all properties and save to database."""
    logger.info("Starting lead scoring pipeline...")

    with get_db_session() as session:
        # Get all properties
        prop_repo = PropertyRepository()
        properties = prop_repo.get_all(session)
        logger.info(f"Found {len(properties)} properties to score")

        if len(properties) == 0:
            logger.warning("No properties found in database")
            return

        # Initialize scorer and score repository
        scorer = LeadScorer()
        score_repo = LeadScoreRepository()

        seed_repo = EnrichedSeedRepository()
        scored_count = 0
        seed_based_count = 0
        legacy_count = 0

        for prop in properties:
            try:
                # Check if this is a seed-based property
                if prop.seed_type:
                    # Seed-based scoring: get enriched_data from enriched_seeds table
                    lead_score = _score_seed_based_property(prop, seed_repo, scorer, session)
                    seed_based_count += 1
                else:
                    # Legacy scoring: build prop_dict from relationships
                    lead_score = _score_legacy_property(prop, scorer)
                    legacy_count += 1

                if lead_score:
                    # Save to database
                    score_data = {
                        'parcel_id_normalized': prop.parcel_id_normalized,
                        'total_score': lead_score.total_score,
                        'distress_score': lead_score.distress_score,
                        'value_score': lead_score.value_score,
                        'location_score': lead_score.location_score,
                        'urgency_score': lead_score.urgency_score,
                        'tier': lead_score.tier,
                        'reasons': lead_score.reasons,
                        'scored_at': datetime.utcnow()
                    }
                    score_repo.upsert_by_parcel(session, score_data)
                    scored_count += 1

            except Exception as e:
                logger.error(
                    "property_scoring_failed",
                    parcel_id=prop.parcel_id_normalized,
                    error=str(e)
                )

        logger.info(f"Successfully scored {scored_count} properties")

        # Print summary
        print("\n" + "=" * 60)
        print("LEAD SCORING COMPLETE")
        print("=" * 60)
        print(f"\nTotal properties scored: {scored_count}")
        print(f"  - Seed-based scoring: {seed_based_count}")
        print(f"  - Legacy scoring: {legacy_count}")

        # Get tier breakdown
        tier_counts = score_repo.get_tier_counts(session)
        print("\nTier Distribution:")
        for tier, count in sorted(tier_counts.items()):
            print(f"  Tier {tier}: {count} properties")

        print("\nNext steps:")
        print("1. API is ready at http://localhost:8000")
        print("2. Start Streamlit: streamlit run src/wholesaler/frontend/app.py")
        print("3. View dashboard at http://localhost:8501")


if __name__ == "__main__":
    main()
