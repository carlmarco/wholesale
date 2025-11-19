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
from src.wholesaler.scoring import LeadScorer, HybridBucketScorer, LogisticOpportunityScorer
from src.wholesaler.ml.inference.hybrid_ml_scorer import HybridMLScorer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


def _score_seed_based_property(prop, seed_repo, scorer, hybrid_scorer, logistic_scorer, session):
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

    # Start with enriched_data from seeds
    enriched_data = dict(enriched_seed.enriched_data)

    # Join property_record data if available
    if prop.property_record:
        enriched_data['property_record'] = {
            'total_mkt': float(prop.property_record.total_mkt) if prop.property_record.total_mkt else None,
            'equity_percent': float(prop.property_record.equity_percent) if prop.property_record.equity_percent else None,
            'year_built': prop.property_record.year_built,
            'taxes': float(prop.property_record.taxes) if prop.property_record.taxes else None,
            'living_area': prop.property_record.living_area,
            'lot_size': prop.property_record.lot_size,
        }

    # Score using HybridBucketScorer as primary
    hybrid_result = hybrid_scorer.score(enriched_data)

    # Map hybrid buckets to LeadScore format for database compatibility
    from src.wholesaler.scoring import LeadScore
    primary_score = LeadScore(
        distress_score=hybrid_result["bucket_scores"].distress,
        value_score=hybrid_result["bucket_scores"].equity,
        location_score=hybrid_result["bucket_scores"].disposition,
        urgency_score=0.0,  # Not used by HybridBucketScorer
        total_score=hybrid_result["total_score"],
        tier=hybrid_result["tier"],
        reasons=[
            f"Distress: {hybrid_result['bucket_scores'].distress:.1f} (violations × enhanced multipliers)",
            f"Disposition: {hybrid_result['bucket_scores'].disposition:.1f} (seed type: {primary_seed_type})",
            f"Equity: {hybrid_result['bucket_scores'].equity:.1f} (property value/equity)",
        ]
    )

    # Compute alternate scores for comparison
    alt_scores = _compute_alternate_scores(enriched_data, hybrid_scorer, logistic_scorer, scorer)
    return primary_score, alt_scores


def _score_legacy_property(prop, scorer, hybrid_scorer, logistic_scorer):
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

    # Score using HybridBucketScorer as primary for legacy properties too
    hybrid_result = hybrid_scorer.score(prop_dict)

    # Map hybrid buckets to LeadScore format
    from src.wholesaler.scoring import LeadScore
    primary_score = LeadScore(
        distress_score=hybrid_result["bucket_scores"].distress,
        value_score=hybrid_result["bucket_scores"].equity,
        location_score=hybrid_result["bucket_scores"].disposition,
        urgency_score=0.0,
        total_score=hybrid_result["total_score"],
        tier=hybrid_result["tier"],
        reasons=[
            f"Distress: {hybrid_result['bucket_scores'].distress:.1f}",
            f"Disposition: {hybrid_result['bucket_scores'].disposition:.1f}",
            f"Equity: {hybrid_result['bucket_scores'].equity:.1f}",
        ]
    )

    alt_scores = _compute_alternate_scores(prop_dict, hybrid_scorer, logistic_scorer, scorer)
    return primary_score, alt_scores


def _compute_alternate_scores(feature_dict, hybrid_scorer, logistic_scorer, legacy_scorer):
    """
    Compute additional scoring views for reporting and comparison.
    """
    hybrid_result = hybrid_scorer.score(feature_dict)
    logistic_result = logistic_scorer.score(feature_dict)

    # Include legacy scorer for comparison (not primary anymore)
    try:
        legacy_result = legacy_scorer.score_lead(feature_dict)
        legacy_total = legacy_result.total_score if legacy_result else 0.0
    except:
        legacy_total = 0.0

    priority_score = 0.6 * hybrid_result["total_score"] + 0.4 * logistic_result["score"]
    priority_flag = (
        hybrid_result["tier"] in ("A", "B") or logistic_result["probability"] >= 0.65
    )
    return {
        "hybrid": hybrid_result,
        "logistic": logistic_result,
        "legacy": legacy_total,
        "priority": {
            "priority_flag": priority_flag,
            "priority_score": round(priority_score, 2),
        },
    }


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
        hybrid_scorer = HybridBucketScorer()
        logistic_scorer = LogisticOpportunityScorer()

        # Initialize ML scorer (will use heuristics if models not available)
        try:
            ml_scorer = HybridMLScorer()
            logger.info("ML scorer initialized")
        except Exception as e:
            logger.warning(f"ML scorer initialization failed: {e}, using heuristics only")
            ml_scorer = None

        seed_repo = EnrichedSeedRepository()
        scored_count = 0
        seed_based_count = 0
        legacy_count = 0
        ml_scored_count = 0

        for prop in properties:
            try:
                # Check if this is a seed-based property
                alt_scores = None
                if prop.seed_type:
                    # Seed-based scoring: get enriched_data from enriched_seeds table
                    legacy_score, alt_scores = _score_seed_based_property(
                        prop, seed_repo, scorer, hybrid_scorer, logistic_scorer, session
                    )
                    seed_based_count += 1
                else:
                    # Legacy scoring: build prop_dict from relationships
                    legacy_score, alt_scores = _score_legacy_property(
                        prop, scorer, hybrid_scorer, logistic_scorer
                    )
                    legacy_count += 1

                if legacy_score:
                    # Get ML prediction if available
                    ml_prediction = None
                    if ml_scorer and alt_scores:
                        try:
                            enriched_data = alt_scores.get("hybrid", {})
                            # Build enriched_data dict for ML scoring
                            ml_input = {
                                "violation_count": enriched_data.get("bucket_scores", {}).distress if hasattr(enriched_data.get("bucket_scores", {}), "distress") else 0,
                                "seed_type": prop.seed_type.split(',')[0] if prop.seed_type else "code_violation",
                                "property_record": {},
                            }
                            if prop.property_record:
                                ml_input["property_record"] = {
                                    "total_mkt": float(prop.property_record.total_mkt) if prop.property_record.total_mkt else None,
                                    "equity_percent": float(prop.property_record.equity_percent) if prop.property_record.equity_percent else None,
                                    "year_built": prop.property_record.year_built,
                                }
                            ml_prediction = ml_scorer.score(ml_input)
                            ml_scored_count += 1
                        except Exception as ml_err:
                            logger.warning(f"ML scoring failed for {prop.parcel_id_normalized}: {ml_err}")

                    if alt_scores:
                        logistic_view = alt_scores["logistic"]
                        priority_view = alt_scores["priority"]
                        legacy_view = alt_scores.get("legacy", 0.0)
                        hybrid_view = alt_scores.get("hybrid", {})
                        legacy_score.reasons.append(
                            f"Logistic probability {logistic_view['probability']:.2f}"
                        )
                        legacy_score.reasons.append(
                            f"Priority: {'YES' if priority_view['priority_flag'] else 'no'} (score {priority_view['priority_score']:.1f})"
                        )
                        legacy_score.reasons.append(
                            f"Legacy scorer comparison: {legacy_view:.1f}"
                        )

                    # Add ML reasons if available
                    if ml_prediction:
                        legacy_score.reasons.extend(ml_prediction.reasons)

                    # Extract profitability data from hybrid scorer result
                    profitability_score = None
                    profitability_details = None
                    if alt_scores and "hybrid" in alt_scores:
                        hybrid_view = alt_scores["hybrid"]
                        # Get profitability bucket score
                        if "bucket_scores" in hybrid_view and hasattr(hybrid_view["bucket_scores"], "profitability"):
                            profitability_score = float(hybrid_view["bucket_scores"].profitability)
                        # Get profitability details (profit, ROI, etc.)
                        if "profitability" in hybrid_view:
                            profitability_details = hybrid_view["profitability"]

                    # Save to database with ML and profitability columns
                    score_data = {
                        'parcel_id_normalized': prop.parcel_id_normalized,
                        'total_score': legacy_score.total_score,
                        'distress_score': legacy_score.distress_score,
                        'value_score': legacy_score.value_score,
                        'location_score': legacy_score.location_score,
                        'urgency_score': legacy_score.urgency_score,
                        'tier': legacy_score.tier,
                        'reasons': legacy_score.reasons,
                        'scored_at': datetime.utcnow(),
                        # ML-specific columns
                        'ml_probability': ml_prediction.probability if ml_prediction else None,
                        'expected_return': ml_prediction.expected_return if ml_prediction else None,
                        'ml_confidence': ml_prediction.confidence if ml_prediction else None,
                        'priority_flag': ml_prediction.priority_flag if ml_prediction else False,
                        # Phase 3.6 - Profitability columns
                        'profitability_score': profitability_score,
                        'profitability_details': profitability_details,
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
