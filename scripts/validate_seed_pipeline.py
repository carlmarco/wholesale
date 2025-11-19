"""
Seed Pipeline Validation Script

Validates the entire hybrid seed ingestion pipeline before migration.
Runs safety checks on legacy and new components to ensure no regression.

Usage:
    python scripts/validate_seed_pipeline.py --check all
    python scripts/validate_seed_pipeline.py --check legacy
    python scripts/validate_seed_pipeline.py --check seeds
    python scripts/validate_seed_pipeline.py --check database
"""
import sys
from pathlib import Path
import json
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wholesaler.db import get_db_session
from src.wholesaler.db.repository import (
    PropertyRepository,
    TaxSaleRepository,
    ForeclosureRepository,
    EnrichedSeedRepository,
    LeadScoreRepository,
)
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class PipelineValidator:
    """Validates the seed-based ingestion pipeline."""

    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'warnings': [],
            'errors': [],
        }
        self.data_dir = Path(__file__).parent.parent / "data"

    def run_all_checks(self):
        """Run all validation checks."""
        print("\n" + "=" * 80)
        print("SEED PIPELINE VALIDATION")
        print("=" * 80 + "\n")

        self.check_legacy_database()
        self.check_seed_files()
        self.check_enrichment_output()
        self.check_database_schema()
        self.check_scoring_integration()

        self.print_summary()

    def check_legacy_database(self):
        """Validate legacy database has data."""
        print("🔍 Checking legacy database state...")

        try:
            with get_db_session() as session:
                prop_repo = PropertyRepository()
                tax_sale_repo = TaxSaleRepository()
                foreclosure_repo = ForeclosureRepository()
                score_repo = LeadScoreRepository()

                # Count existing records
                properties = session.query(prop_repo.model).count()
                tax_sales = session.query(tax_sale_repo.model).count()
                foreclosures = session.query(foreclosure_repo.model).count()
                lead_scores = session.query(score_repo.model).count()

                self.results['checks']['legacy_database'] = {
                    'status': 'PASS',
                    'properties': properties,
                    'tax_sales': tax_sales,
                    'foreclosures': foreclosures,
                    'lead_scores': lead_scores,
                }

                print(f"  ✓ Properties: {properties:,}")
                print(f"  ✓ Tax Sales: {tax_sales:,}")
                print(f"  ✓ Foreclosures: {foreclosures:,}")
                print(f"  ✓ Lead Scores: {lead_scores:,}")

                if properties == 0:
                    self.results['warnings'].append("No properties in database - run legacy ingestion first")

        except Exception as e:
            self.results['checks']['legacy_database'] = {'status': 'FAIL', 'error': str(e)}
            self.results['errors'].append(f"Legacy database check failed: {e}")
            print(f"  ✗ Error: {e}")

    def check_seed_files(self):
        """Validate seed collection output."""
        print("\n🔍 Checking seed collection output...")

        seeds_file = self.data_dir / "processed" / "seeds.json"

        if not seeds_file.exists():
            self.results['checks']['seed_files'] = {
                'status': 'SKIP',
                'message': 'seeds.json not found - run: make ingest-seeds'
            }
            self.results['warnings'].append("No seeds.json - need to run seed collection")
            print(f"  ⚠ seeds.json not found at {seeds_file}")
            return

        try:
            with open(seeds_file, 'r') as f:
                seeds_data = json.load(f)

            # Count by seed type
            seed_counts = {}
            for seed in seeds_data:
                seed_type = seed.get('seed_type', 'unknown')
                seed_counts[seed_type] = seed_counts.get(seed_type, 0) + 1

            self.results['checks']['seed_files'] = {
                'status': 'PASS',
                'total_seeds': len(seeds_data),
                'by_type': seed_counts,
                'file_path': str(seeds_file),
            }

            print(f"  ✓ Total seeds: {len(seeds_data):,}")
            for seed_type, count in seed_counts.items():
                print(f"    - {seed_type}: {count:,}")

            if len(seeds_data) == 0:
                self.results['warnings'].append("Seeds file is empty")

        except Exception as e:
            self.results['checks']['seed_files'] = {'status': 'FAIL', 'error': str(e)}
            self.results['errors'].append(f"Seed file validation failed: {e}")
            print(f"  ✗ Error: {e}")

    def check_enrichment_output(self):
        """Validate enrichment pipeline output."""
        print("\n🔍 Checking enrichment output...")

        enriched_file = self.data_dir / "processed" / "enriched_seeds.parquet"

        if not enriched_file.exists():
            self.results['checks']['enrichment_output'] = {
                'status': 'SKIP',
                'message': 'enriched_seeds.parquet not found - run: make enrich-seeds'
            }
            self.results['warnings'].append("No enriched_seeds.parquet - need to run enrichment")
            print(f"  ⚠ enriched_seeds.parquet not found at {enriched_file}")
            return

        try:
            df = pd.read_parquet(enriched_file)

            # Analyze enrichment
            total_rows = len(df)
            seed_type_counts = df['seed_type'].value_counts().to_dict() if 'seed_type' in df.columns else {}

            # Check for required columns
            required_cols = ['parcel_id', 'seed_type']
            missing_cols = [col for col in required_cols if col not in df.columns]

            # Sample data quality
            has_coordinates = (df['latitude'].notna() & df['longitude'].notna()).sum() if 'latitude' in df.columns else 0
            has_violations = df['violation_count'].notna().sum() if 'violation_count' in df.columns else 0

            self.results['checks']['enrichment_output'] = {
                'status': 'PASS' if not missing_cols else 'FAIL',
                'total_rows': total_rows,
                'by_type': seed_type_counts,
                'missing_columns': missing_cols,
                'has_coordinates': has_coordinates,
                'has_violations': has_violations,
                'file_path': str(enriched_file),
            }

            print(f"  ✓ Total enriched seeds: {total_rows:,}")
            for seed_type, count in seed_type_counts.items():
                print(f"    - {seed_type}: {count:,}")
            print(f"  ✓ With coordinates: {has_coordinates:,} ({has_coordinates/total_rows*100:.1f}%)")
            print(f"  ✓ With violations: {has_violations:,} ({has_violations/total_rows*100:.1f}%)")

            if missing_cols:
                self.results['errors'].append(f"Missing required columns: {missing_cols}")
                print(f"  ✗ Missing columns: {missing_cols}")

        except Exception as e:
            self.results['checks']['enrichment_output'] = {'status': 'FAIL', 'error': str(e)}
            self.results['errors'].append(f"Enrichment output validation failed: {e}")
            print(f"  ✗ Error: {e}")

    def check_database_schema(self):
        """Validate database schema supports seed ingestion."""
        print("\n🔍 Checking database schema...")

        try:
            with get_db_session() as session:
                # Check if enriched_seeds table exists
                from sqlalchemy import inspect
                inspector = inspect(session.bind)
                tables = inspector.get_table_names()

                has_enriched_seeds = 'enriched_seeds' in tables

                # Check if properties has seed_type column
                if 'properties' in tables:
                    columns = [col['name'] for col in inspector.get_columns('properties')]
                    has_seed_type = 'seed_type' in columns
                else:
                    has_seed_type = False

                # Count enriched seeds in database
                if has_enriched_seeds:
                    seed_repo = EnrichedSeedRepository()
                    enriched_count = session.query(seed_repo.model).count()
                    processed_count = session.query(seed_repo.model).filter_by(processed=True).count()
                else:
                    enriched_count = 0
                    processed_count = 0

                schema_ready = has_enriched_seeds and has_seed_type

                self.results['checks']['database_schema'] = {
                    'status': 'PASS' if schema_ready else 'FAIL',
                    'enriched_seeds_table': has_enriched_seeds,
                    'seed_type_column': has_seed_type,
                    'enriched_seeds_count': enriched_count,
                    'processed_seeds_count': processed_count,
                }

                print(f"  {'✓' if has_enriched_seeds else '✗'} enriched_seeds table exists: {has_enriched_seeds}")
                print(f"  {'✓' if has_seed_type else '✗'} properties.seed_type column exists: {has_seed_type}")
                if has_enriched_seeds:
                    print(f"  ✓ Enriched seeds in DB: {enriched_count:,}")
                    print(f"  ✓ Processed seeds: {processed_count:,}")

                if not schema_ready:
                    self.results['warnings'].append("Database schema not ready - run: alembic upgrade head")

        except Exception as e:
            self.results['checks']['database_schema'] = {'status': 'FAIL', 'error': str(e)}
            self.results['errors'].append(f"Database schema check failed: {e}")
            print(f"  ✗ Error: {e}")

    def check_scoring_integration(self):
        """Validate lead scoring can handle seed-based properties."""
        print("\n🔍 Checking lead scoring integration...")

        try:
            with get_db_session() as session:
                # Check if any properties have seed_type
                prop_repo = PropertyRepository()

                try:
                    from sqlalchemy import func
                    seed_based_props = session.query(prop_repo.model).filter(
                        prop_repo.model.seed_type.isnot(None)
                    ).count()
                except:
                    seed_based_props = 0

                # Check lead scores exist
                score_repo = LeadScoreRepository()
                total_scores = session.query(score_repo.model).count()

                # Get tier distribution
                tier_counts = score_repo.get_tier_counts(session)

                self.results['checks']['scoring_integration'] = {
                    'status': 'PASS',
                    'seed_based_properties': seed_based_props,
                    'total_lead_scores': total_scores,
                    'tier_distribution': tier_counts,
                }

                print(f"  ✓ Seed-based properties: {seed_based_props:,}")
                print(f"  ✓ Total lead scores: {total_scores:,}")
                print(f"  ✓ Tier distribution:")
                for tier, count in sorted(tier_counts.items()):
                    print(f"    - Tier {tier}: {count:,}")

                if seed_based_props == 0:
                    self.results['warnings'].append("No seed-based properties yet - pipeline not fully integrated")

        except Exception as e:
            self.results['checks']['scoring_integration'] = {'status': 'FAIL', 'error': str(e)}
            self.results['errors'].append(f"Scoring integration check failed: {e}")
            print(f"  ✗ Error: {e}")

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)

        # Count statuses
        passed = sum(1 for c in self.results['checks'].values() if c.get('status') == 'PASS')
        failed = sum(1 for c in self.results['checks'].values() if c.get('status') == 'FAIL')
        skipped = sum(1 for c in self.results['checks'].values() if c.get('status') == 'SKIP')

        print(f"\n✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"⚠ Skipped: {skipped}")

        if self.results['warnings']:
            print(f"\n⚠ Warnings ({len(self.results['warnings'])}):")
            for warning in self.results['warnings']:
                print(f"  - {warning}")

        if self.results['errors']:
            print(f"\n✗ Errors ({len(self.results['errors'])}):")
            for error in self.results['errors']:
                print(f"  - {error}")

        # Overall status
        if failed > 0:
            print("\n🔴 VALIDATION FAILED - Fix errors before migration")
        elif len(self.results['warnings']) > 0:
            print("\n🟡 VALIDATION PASSED WITH WARNINGS - Review before migration")
        else:
            print("\n🟢 VALIDATION PASSED - Ready for migration")

        # Save results
        results_file = self.data_dir / "validation_results.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\nResults saved to: {results_file}")


def main():
    """Run validation."""
    import argparse

    parser = argparse.ArgumentParser(description='Validate seed pipeline before migration')
    parser.add_argument(
        '--check',
        choices=['all', 'legacy', 'seeds', 'enrichment', 'database', 'scoring'],
        default='all',
        help='Which check to run'
    )

    args = parser.parse_args()

    validator = PipelineValidator()

    if args.check == 'all':
        validator.run_all_checks()
    elif args.check == 'legacy':
        validator.check_legacy_database()
        validator.print_summary()
    elif args.check == 'seeds':
        validator.check_seed_files()
        validator.print_summary()
    elif args.check == 'enrichment':
        validator.check_enrichment_output()
        validator.print_summary()
    elif args.check == 'database':
        validator.check_database_schema()
        validator.print_summary()
    elif args.check == 'scoring':
        validator.check_scoring_integration()
        validator.print_summary()


if __name__ == "__main__":
    main()
