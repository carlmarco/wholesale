"""
Validate seed-aware lead scoring integration.

Captures baseline, runs seed-aware scoring, and compares results.
"""
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db.session import SessionLocal
from src.wholesaler.db.models import Property, LeadScore
from src.wholesaler.scoring.lead_scorer import LeadScorer
from src.wholesaler.utils.logger import get_logger
from sqlalchemy import func, case

logger = get_logger(__name__)


def get_lead_tier_distribution(session) -> Dict[str, int]:
    """Get current tier distribution."""
    results = session.query(
        LeadScore.tier,
        func.count(LeadScore.property_id)
    ).group_by(LeadScore.tier).all()

    return {tier: count for tier, count in results}


def get_seed_type_distribution(session) -> Dict[str, int]:
    """Get property distribution by seed_type."""
    results = session.query(
        Property.seed_type,
        func.count(Property.parcel_id_normalized)
    ).filter(
        Property.seed_type.isnot(None)
    ).group_by(Property.seed_type).all()

    return {seed_type: count for seed_type, count in results}


def get_average_scores_by_seed_type(session) -> Dict[str, float]:
    """Get average scores by seed type."""
    results = session.query(
        Property.seed_type,
        func.avg(LeadScore.total_score)
    ).join(
        LeadScore,
        Property.parcel_id_normalized == LeadScore.property_id
    ).filter(
        Property.seed_type.isnot(None)
    ).group_by(Property.seed_type).all()

    return {seed_type: float(score) for seed_type, score in results}


def main():
    """Run lead scoring validation."""

    with SessionLocal() as session:
        print(f"\n{'='*70}")
        print("PHASE 6: LEAD SCORING VALIDATION")
        print(f"{'='*70}\n")

        # Step 1: Capture baseline
        print("Step 1: Capturing baseline metrics...")
        baseline_tiers = get_lead_tier_distribution(session)
        baseline_total = sum(baseline_tiers.values())
        seed_distribution = get_seed_type_distribution(session)

        print(f"\nBaseline Lead Tier Distribution:")
        print(f"{'Tier':<10} {'Count':>10} {'Percentage':>12}")
        print("-" * 35)
        for tier in ['A', 'B', 'C', 'D']:
            count = baseline_tiers.get(tier, 0)
            pct = (count / baseline_total * 100) if baseline_total > 0 else 0
            print(f"{tier:<10} {count:>10,} {pct:>11.1f}%")
        print(f"{'Total':<10} {baseline_total:>10,}")

        print(f"\n\nSeed Type Distribution:")
        print(f"{'Seed Type':<30} {'Count':>10}")
        print("-" * 42)
        for seed_type, count in sorted(seed_distribution.items()):
            print(f"{seed_type:<30} {count:>10,}")
        print(f"{'Total':<30} {sum(seed_distribution.values()):>10,}")

        # Step 2: Run seed-aware scoring
        print(f"\n\nStep 2: Running seed-aware lead scoring...")
        scorer = LeadScorer()

        # Get properties with seed types
        properties_with_seeds = session.query(Property).filter(
            Property.seed_type.isnot(None)
        ).all()

        print(f"Found {len(properties_with_seeds):,} properties with seed types")

        scored_count = 0
        error_count = 0

        for prop in properties_with_seeds:
            try:
                # The scorer will automatically apply seed-type weighting
                scorer.score_property(session, prop)
                scored_count += 1

                if scored_count % 1000 == 0:
                    print(f"  Scored {scored_count:,} properties...")

            except Exception as e:
                error_count += 1
                if error_count <= 5:  # Only log first 5 errors
                    logger.error(
                        "scoring_failed",
                        parcel_id=prop.parcel_id_normalized,
                        seed_type=prop.seed_type,
                        error=str(e)
                    )

        session.commit()

        print(f"\nScoring complete:")
        print(f"  Scored: {scored_count:,}")
        print(f"  Errors: {error_count:,}")

        # Step 3: Compare results
        print(f"\n\nStep 3: Comparing results...")
        new_tiers = get_lead_tier_distribution(session)
        new_total = sum(new_tiers.values())

        print(f"\nNew Lead Tier Distribution:")
        print(f"{'Tier':<10} {'Count':>10} {'Percentage':>12} {'Change':>15}")
        print("-" * 50)
        for tier in ['A', 'B', 'C', 'D']:
            old_count = baseline_tiers.get(tier, 0)
            new_count = new_tiers.get(tier, 0)
            new_pct = (new_count / new_total * 100) if new_total > 0 else 0
            change = new_count - old_count
            change_str = f"+{change:,}" if change >= 0 else f"{change:,}"
            print(f"{tier:<10} {new_count:>10,} {new_pct:>11.1f}% {change_str:>14}")
        print(f"{'Total':<10} {new_total:>10,}")

        # Step 4: Analyze seed type scoring
        print(f"\n\nStep 4: Analyzing seed-type scoring...")
        avg_scores = get_average_scores_by_seed_type(session)

        print(f"\nAverage Scores by Seed Type:")
        print(f"{'Seed Type':<30} {'Avg Score':>12}")
        print("-" * 44)
        for seed_type in sorted(avg_scores.keys()):
            score = avg_scores[seed_type]
            print(f"{seed_type:<30} {score:>12.2f}")

        # Step 5: Validation checks
        print(f"\n\n{'='*70}")
        print("VALIDATION RESULTS")
        print(f"{'='*70}\n")

        checks = []

        # Check 1: No crashes
        checks.append(("No crashes during scoring", error_count == 0))

        # Check 2: All seed properties scored
        checks.append((
            "All seed properties scored",
            scored_count == len(properties_with_seeds)
        ))

        # Check 3: Reasonable tier distribution
        tier_a_pct = (new_tiers.get('A', 0) / new_total * 100) if new_total > 0 else 0
        checks.append((
            "Tier A not over-represented (< 30%)",
            tier_a_pct < 30
        ))

        # Check 4: Multi-source properties score higher
        multi_source_avg = avg_scores.get('code_violation,foreclosure', 0)
        single_source_avg = avg_scores.get('code_violation', 0)
        if multi_source_avg > 0 and single_source_avg > 0:
            checks.append((
                "Multi-source properties score higher",
                multi_source_avg > single_source_avg
            ))

        # Print validation results
        for check_name, passed in checks:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {check_name}")

        all_passed = all(passed for _, passed in checks)

        print(f"\n{'='*70}")
        if all_passed:
            print("✅ PHASE 6 VALIDATION: PASSED")
        else:
            print("❌ PHASE 6 VALIDATION: FAILED")
        print(f"{'='*70}\n")

        return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
