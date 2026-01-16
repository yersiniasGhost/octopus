#!/usr/bin/env python3
"""
Calculate Energy Percentiles Tool

Calculates energy consumption percentile rank for residential properties
relative to comparable homes (similar sqft, age, stories, location).

Uses scipy.stats.percentileofscore for robust percentile calculation.
Higher percentile = higher consumption relative to peers.

Usage:
    # Test on a single parcel
    python scripts/calculate_energy_percentiles_tool.py --parcel 010-000002-00

    # Process all properties in a county (dry run - no DB updates)
    python scripts/calculate_energy_percentiles_tool.py --county Franklin --limit 100

    # Process and save to database
    python scripts/calculate_energy_percentiles_tool.py --county Franklin --update-db

    # Process from a list of parcel IDs
    python scripts/calculate_energy_percentiles_tool.py --parcel-file parcels.txt --update-db
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient
from dotenv import load_dotenv
import os

from src.tools.comparables import EnergyPercentileCalculator, TieredFilterConfig
from src.utils.log_manager import LogManager

load_dotenv()
logger = LogManager().get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Calculate energy consumption percentiles for residential properties',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Target selection (mutually exclusive)
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument('--parcel', type=str, help='Single parcel ID to process')
    target_group.add_argument('--county', type=str, help='Process all properties in county')
    target_group.add_argument('--parcel-file', type=str, help='File with parcel IDs (one per line)')

    # Processing options
    parser.add_argument('--limit', type=int, default=0, help='Limit number of properties (0=all)')
    parser.add_argument('--update-db', action='store_true', help='Save results to database')
    parser.add_argument('--min-months', type=int, default=6, help='Min months of electrical data (default: 6)')
    parser.add_argument('--min-comparables', type=int, default=30, help='Min comparables before relaxing filters (default: 30)')

    # Output options
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--output', '-o', type=str, help='Output CSV file for results')

    return parser.parse_args()


def get_parcels_for_county(db, county: str, limit: int = 0) -> list:
    """Get parcel IDs with electrical data for a county"""
    county_normalized = county.replace('County', '').strip()
    electrical_coll = f"{county_normalized}ElectricalDB"

    query = {'time_series_elec': {'$exists': True}}
    projection = {'parcel_id': 1}

    cursor = db[electrical_coll].find(query, projection)
    if limit > 0:
        cursor = cursor.limit(limit)

    return [doc['parcel_id'] for doc in cursor]


def main():
    args = parse_args()

    # Connect to MongoDB
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client['empower_development']

    # Configure the calculator
    config = TieredFilterConfig(min_comparables=args.min_comparables)

    # Determine county from parcel or explicit arg
    if args.parcel:
        # For single parcel, we need to figure out the county
        # Try Franklin first (most common), then search
        county = 'Franklin'
        parcel_ids = [args.parcel]
        logger.info(f"Processing single parcel: {args.parcel}")

    elif args.county:
        county = args.county
        parcel_ids = get_parcels_for_county(db, county, args.limit)
        logger.info(f"Found {len(parcel_ids)} parcels with electrical data in {county} County")

    elif args.parcel_file:
        # Read parcel IDs from file
        with open(args.parcel_file, 'r') as f:
            parcel_ids = [line.strip() for line in f if line.strip()]
        county = 'Franklin'  # Default, may need to be smarter about this
        logger.info(f"Loaded {len(parcel_ids)} parcel IDs from {args.parcel_file}")

    # Initialize calculator
    calculator = EnergyPercentileCalculator(db, county, config)

    # Process parcels
    results = []
    success_count = 0
    error_count = 0

    for i, parcel_id in enumerate(parcel_ids):
        if args.verbose or (i + 1) % 100 == 0:
            logger.info(f"Processing {i + 1}/{len(parcel_ids)}: {parcel_id}")

        if args.update_db:
            result = calculator.update_property_percentile(parcel_id)
        else:
            result = calculator.calculate_percentile(parcel_id)

        results.append(result)

        if result.is_valid:
            success_count += 1
            if args.verbose or args.parcel:
                print(f"  {parcel_id}: {result.annual_kwh:,.0f} kWh/year, "
                      f"{result.percentile_rank:.1f}th percentile "
                      f"(compared to {result.comparable_count} homes)")
        else:
            error_count += 1
            if args.verbose:
                print(f"  {parcel_id}: ERROR - {result.error}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {success_count}/{len(parcel_ids)} successful ({error_count} errors)")

    if success_count > 0:
        valid_results = [r for r in results if r.is_valid]
        percentiles = [r.percentile_rank for r in valid_results]
        avg_percentile = sum(percentiles) / len(percentiles)
        print(f"Average percentile: {avg_percentile:.1f}")

        # Distribution breakdown
        buckets = [0, 0, 0, 0, 0]  # 0-20, 20-40, 40-60, 60-80, 80-100
        for p in percentiles:
            idx = min(int(p // 20), 4)
            buckets[idx] += 1

        print("\nPercentile Distribution:")
        for i, count in enumerate(buckets):
            low, high = i * 20, (i + 1) * 20
            pct = 100 * count / len(percentiles)
            bar = '█' * int(pct / 2)
            print(f"  {low:3d}-{high:3d}: {count:5d} ({pct:5.1f}%) {bar}")

    # Write CSV output if requested
    if args.output:
        import csv
        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['parcel_id', 'annual_kwh', 'percentile_rank', 'comparable_count', 'error'])
            for r in results:
                writer.writerow([r.parcel_id, r.annual_kwh, r.percentile_rank, r.comparable_count, r.error])
        print(f"\nResults written to: {args.output}")

    if args.update_db:
        print(f"\nDatabase updated: {success_count} records in {county}CountyResidential")


if __name__ == '__main__':
    main()
