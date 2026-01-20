#!/usr/bin/env python3
"""
Enrich participants with thermal load data from county-specific collections.

This script joins participant data with thermal load analysis results:
- Reads participants from campaign_data.participants (with linkage.parcel_id)
- Matches to {County}ThermalLoads collections in empower_development
- Updates participants with heating/cooling load regression coefficients

The thermal load fields added:
- thermal.kwh_hl_slope: Heating load slope (kWh/HDD)
- thermal.kwh_hl_intercept: Heating load intercept
- thermal.kwh_hl_r2: Heating load R² fit quality
- thermal.kwh_cl_slope: Cooling load slope (kWh/CDD)
- thermal.kwh_cl_intercept: Cooling load intercept
- thermal.kwh_cl_r2: Cooling load R² fit quality
- thermal.enriched_at: Timestamp of enrichment
- thermal.source_collection: Source thermal collection name

Usage:
    python scripts/enrich_thermal_loads.py
    python scripts/enrich_thermal_loads.py --dry-run
    python scripts/enrich_thermal_loads.py --county "Hennepin"
    python scripts/enrich_thermal_loads.py --force  # Re-enrich already enriched

Options:
    --dry-run       Preview changes without writing to database
    --county NAME   Only process participants from a specific county
    --force         Re-enrich participants that already have thermal data
    --verbose       Show detailed progress for each participant
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
from datetime import datetime
from collections import defaultdict

from src.tools.mongo import get_campaign_db, get_empower_db
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


def get_thermal_collections(empower_db) -> dict:
    """
    Discover all thermal load collections and build a lookup map.

    Returns:
        Dict mapping county names to collection objects
    """
    collections = empower_db.list_collection_names()
    thermal_collections = {}

    for name in collections:
        if name.endswith('ThermalLoads'):
            county = name.replace('ThermalLoads', '')
            thermal_collections[county] = empower_db[name]

    return thermal_collections


def build_thermal_lookup(thermal_collections: dict, verbose: bool = False) -> dict:
    """
    Build a parcel_id -> thermal_data lookup from all thermal collections.

    Args:
        thermal_collections: Dict of county -> collection objects
        verbose: Print progress

    Returns:
        Dict mapping parcel_id to (county, thermal_data)
    """
    lookup = {}
    stats = defaultdict(int)

    for county, collection in thermal_collections.items():
        count = 0
        for doc in collection.find({}, {
            'parcel_id': 1,
            'kwh_hl_slope': 1,
            'kwh_hl_intercept': 1,
            'kwh_hl_r2': 1,
            'kwh_cl_slope': 1,
            'kwh_cl_intercept': 1,
            'kwh_cl_r2': 1
        }):
            parcel_id = doc.get('parcel_id')
            if parcel_id:
                lookup[parcel_id] = {
                    'county': county,
                    'collection': f"{county}ThermalLoads",
                    'kwh_hl_slope': doc.get('kwh_hl_slope'),
                    'kwh_hl_intercept': doc.get('kwh_hl_intercept'),
                    'kwh_hl_r2': doc.get('kwh_hl_r2'),
                    'kwh_cl_slope': doc.get('kwh_cl_slope'),
                    'kwh_cl_intercept': doc.get('kwh_cl_intercept'),
                    'kwh_cl_r2': doc.get('kwh_cl_r2')
                }
                count += 1

        stats[county] = count
        if verbose:
            print(f"  {county}: {count:,} parcels")

    return lookup, stats


def normalize_county(county_key: str) -> str:
    """
    Normalize county name by removing 'County' suffix.

    Args:
        county_key: Raw county key like 'Franklin' or 'FranklinCounty'

    Returns:
        Normalized county name (e.g., 'Franklin')
    """
    if not county_key:
        return 'Unknown'
    # Remove 'County' suffix if present
    if county_key.endswith('County'):
        return county_key[:-6]  # Remove last 6 chars
    return county_key


def enrich_participants(campaign_db, thermal_lookup: dict, args) -> dict:
    """
    Enrich participants with thermal load data.

    Args:
        campaign_db: Campaign database
        thermal_lookup: parcel_id -> thermal_data mapping
        args: Command line arguments

    Returns:
        Statistics dictionary
    """
    stats = {
        'total': 0,
        'with_parcel_id': 0,
        'matched': 0,
        'already_enriched': 0,
        'updated': 0,
        'no_parcel_id': 0,
        'no_thermal_data': 0,
        'by_county': defaultdict(lambda: {'matched': 0, 'no_data': 0})
    }

    # Build query - use county_key field
    query = {}
    if args.county:
        # Match both normalized and with-County-suffix variants
        query['$or'] = [
            {'linkage.county_key': args.county},
            {'linkage.county_key': f'{args.county}County'}
        ]

    # Skip already enriched unless --force
    if not args.force:
        query['thermal.enriched_at'] = {'$exists': False}

    participants = campaign_db.participants.find(query)

    for participant in participants:
        stats['total'] += 1

        parcel_id = participant.get('linkage', {}).get('parcel_id')
        county_key = participant.get('linkage', {}).get('county_key')
        county = normalize_county(county_key)

        if not parcel_id:
            stats['no_parcel_id'] += 1
            continue

        stats['with_parcel_id'] += 1

        # Check if already enriched
        if participant.get('thermal', {}).get('enriched_at') and not args.force:
            stats['already_enriched'] += 1
            continue

        # Look up thermal data
        thermal_data = thermal_lookup.get(parcel_id)

        if not thermal_data:
            stats['no_thermal_data'] += 1
            stats['by_county'][county]['no_data'] += 1
            if args.verbose:
                print(f"  No thermal data: {parcel_id} ({county})")
            continue

        stats['matched'] += 1
        stats['by_county'][county]['matched'] += 1

        # Prepare update
        update_doc = {
            '$set': {
                'thermal.kwh_hl_slope': thermal_data['kwh_hl_slope'],
                'thermal.kwh_hl_intercept': thermal_data['kwh_hl_intercept'],
                'thermal.kwh_hl_r2': thermal_data['kwh_hl_r2'],
                'thermal.kwh_cl_slope': thermal_data['kwh_cl_slope'],
                'thermal.kwh_cl_intercept': thermal_data['kwh_cl_intercept'],
                'thermal.kwh_cl_r2': thermal_data['kwh_cl_r2'],
                'thermal.enriched_at': datetime.now(),
                'thermal.source_collection': thermal_data['collection'],
                'thermal.county': county  # Normalized county name
            }
        }

        if args.verbose:
            print(f"  Match: {parcel_id} -> {thermal_data['collection']}")
            print(f"    HL slope: {thermal_data['kwh_hl_slope']:.4f}, CL slope: {thermal_data['kwh_cl_slope']:.4f}")

        if not args.dry_run:
            campaign_db.participants.update_one(
                {'_id': participant['_id']},
                update_doc
            )
            stats['updated'] += 1

    return stats


def print_stats(stats: dict, dry_run: bool = False):
    """Print enrichment statistics."""
    print("\n" + "=" * 60)
    print("  THERMAL LOAD ENRICHMENT RESULTS")
    print("=" * 60)

    if dry_run:
        print("\n  [DRY RUN - No changes made]\n")

    print(f"\n  Total participants processed: {stats['total']:,}")
    print(f"  With parcel_id:              {stats['with_parcel_id']:,}")
    print(f"  Without parcel_id:           {stats['no_parcel_id']:,}")
    print(f"  Already enriched (skipped):  {stats['already_enriched']:,}")
    print(f"  Matched to thermal data:     {stats['matched']:,}")
    print(f"  No thermal data found:       {stats['no_thermal_data']:,}")

    if not dry_run:
        print(f"  Records updated:             {stats['updated']:,}")

    # Coverage calculation
    if stats['with_parcel_id'] > 0:
        coverage = stats['matched'] / stats['with_parcel_id'] * 100
        print(f"\n  Coverage rate: {coverage:.1f}%")

    # By county breakdown
    if stats['by_county']:
        print("\n  BY COUNTY:")
        print("-" * 40)
        for county in sorted(stats['by_county'].keys()):
            data = stats['by_county'][county]
            total = data['matched'] + data['no_data']
            if total > 0:
                rate = data['matched'] / total * 100
                print(f"  {county:<20} {data['matched']:>5} / {total:<5} ({rate:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description='Enrich participants with thermal load data'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without writing')
    parser.add_argument('--county', type=str,
                       help='Only process specific county')
    parser.add_argument('--force', action='store_true',
                       help='Re-enrich already enriched participants')
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed progress')
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  THERMAL LOAD ENRICHMENT")
    print("=" * 60)

    if args.dry_run:
        print("\n  [DRY RUN MODE]")

    # Connect to databases
    print("\n  Connecting to databases...")
    campaign_db = get_campaign_db()
    empower_db = get_empower_db()

    # Discover thermal collections
    print("\n  Discovering thermal load collections...")
    thermal_collections = get_thermal_collections(empower_db)
    print(f"  Found {len(thermal_collections)} county thermal collections")

    # Build lookup table
    print("\n  Building thermal data lookup table...")
    thermal_lookup, collection_stats = build_thermal_lookup(
        thermal_collections,
        verbose=args.verbose
    )
    print(f"  Total parcels with thermal data: {len(thermal_lookup):,}")

    # Show collection stats
    if args.verbose:
        print("\n  THERMAL COLLECTIONS:")
        for county, count in sorted(collection_stats.items()):
            print(f"    {county}: {count:,} parcels")

    # Enrich participants
    print("\n  Enriching participants...")
    stats = enrich_participants(campaign_db, thermal_lookup, args)

    # Print results
    print_stats(stats, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("  COMPLETE")
    print("=" * 60 + "\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
