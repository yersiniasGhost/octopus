#!/usr/bin/env python3
"""
Backfill missing parcel_id values in FranklinCountyDemographic collection.

Matches demographic records (missing parcel_id) to FranklinCountyResidential
by normalized address to populate the parcel_id field.

Usage:
    python scripts/backfill_demographic_parcel_ids_tool.py --dry-run
    python scripts/backfill_demographic_parcel_ids_tool.py --limit 100
    python scripts/backfill_demographic_parcel_ids_tool.py
"""

import argparse
from pymongo import MongoClient
from datetime import datetime
import os
import re
from dotenv import load_dotenv

load_dotenv()

DATABASE = 'empower_development'
DEMOGRAPHIC_COLLECTION = 'FranklinCountyDemographic'
RESIDENTIAL_COLLECTION = 'FranklinCountyResidential'


def normalize_address(addr):
    """Normalize address for matching - handles suffix variations."""
    if not addr:
        return None
    addr = str(addr).upper().strip()
    addr = re.sub(r'\s+', ' ', addr)
    addr = re.sub(r'\.$', '', addr)
    # Standardize common suffixes
    addr = re.sub(r'\bAVE?\b', 'AVE', addr)
    addr = re.sub(r'\bSTR?\b', 'ST', addr)
    addr = re.sub(r'\bDRV?\b', 'DR', addr)
    addr = re.sub(r'\bBLVD?\b', 'BLVD', addr)
    addr = re.sub(r'\bCRT?\b', 'CT', addr)
    addr = re.sub(r'\bPLACE\b', 'PL', addr)
    addr = re.sub(r'\bLANE\b', 'LN', addr)
    addr = re.sub(r'\bCIRCLE\b', 'CIR', addr)
    addr = re.sub(r'\bROAD\b', 'RD', addr)
    addr = re.sub(r'\bPKWY\b', 'PKWY', addr)
    return addr


def main():
    parser = argparse.ArgumentParser(description='Backfill missing parcel_ids in demographic data')
    parser.add_argument('--dry-run', action='store_true', help='Preview without updating')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("=" * 70)
    print("BACKFILL DEMOGRAPHIC PARCEL_IDS FROM RESIDENTIAL")
    print("=" * 70)
    print(f"Database: {DATABASE}")
    print(f"Demographic: {DEMOGRAPHIC_COLLECTION}")
    print(f"Residential: {RESIDENTIAL_COLLECTION}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Limit: {args.limit or 'None'}")
    print()

    # Connect to MongoDB
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    client = MongoClient(mongo_uri)
    db = client[DATABASE]
    demo_coll = db[DEMOGRAPHIC_COLLECTION]
    res_coll = db[RESIDENTIAL_COLLECTION]

    # Count records needing backfill
    missing_query = {'$or': [
        {'parcel_id': ''},
        {'parcel_id': None},
        {'parcel_id': {'$exists': False}}
    ]}

    total_missing = demo_coll.count_documents(missing_query)
    total_demo = demo_coll.count_documents({})
    print(f"Total demographic records: {total_demo:,}")
    print(f"Records missing parcel_id: {total_missing:,}")
    print()

    # Build residential address -> parcel_id lookup
    print("Building residential address index...")
    res_lookup = {}
    res_count = 0
    for r in res_coll.find({}, {'address': 1, 'parcel_id': 1, 'parcel_zip': 1}):
        addr = normalize_address(r.get('address'))
        if addr and r.get('parcel_id'):
            # Key by address and optionally zip for better matching
            res_lookup[addr] = {
                'parcel_id': r['parcel_id'],
                'parcel_zip': r.get('parcel_zip')
            }
            res_count += 1
    print(f"Indexed {res_count:,} residential addresses")
    print()

    # Find and update records
    print("Processing demographic records...")

    cursor = demo_coll.find(missing_query, {'_id': 1, 'address': 1, 'parcel_zip': 1})
    if args.limit:
        cursor = cursor.limit(args.limit)

    stats = {
        'processed': 0,
        'matched': 0,
        'updated': 0,
        'no_match': 0,
        'no_address': 0,
    }

    updates = []

    for doc in cursor:
        stats['processed'] += 1

        addr = normalize_address(doc.get('address'))
        if not addr:
            stats['no_address'] += 1
            continue

        # Look up in residential
        res_data = res_lookup.get(addr)

        if res_data:
            stats['matched'] += 1
            updates.append({
                '_id': doc['_id'],
                'parcel_id': res_data['parcel_id']
            })

            if args.verbose and len(updates) <= 5:
                print(f"  Match: {addr} -> {res_data['parcel_id']}")
        else:
            stats['no_match'] += 1
            if args.verbose and stats['no_match'] <= 3:
                print(f"  No match: {addr}")

        if stats['processed'] % 5000 == 0:
            print(f"  Processed {stats['processed']:,}... (matched: {stats['matched']:,})")

    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total processed: {stats['processed']:,}")
    print(f"Matched to residential: {stats['matched']:,}")
    print(f"No match found: {stats['no_match']:,}")
    print(f"No address: {stats['no_address']:,}")
    print(f"Ready to update: {len(updates):,}")
    print()

    # Apply updates
    if args.dry_run:
        print("DRY RUN - No documents updated")
        print(f"Would update {len(updates):,} documents with parcel_id")
    else:
        if updates:
            print(f"Updating {len(updates):,} documents...")
            for i, update in enumerate(updates):
                demo_coll.update_one(
                    {'_id': update['_id']},
                    {'$set': {
                        'parcel_id': update['parcel_id'],
                        'parcel_id_source': 'backfill_from_residential',
                        'parcel_id_backfilled_at': datetime.utcnow()
                    }}
                )
                stats['updated'] += 1

                if (i + 1) % 2000 == 0:
                    print(f"  Updated {i + 1:,} / {len(updates):,}...")

            print(f"Updated {stats['updated']:,} documents")

            # Verify
            still_missing = demo_coll.count_documents(missing_query)
            print(f"\nRecords still missing parcel_id: {still_missing:,}")
        else:
            print("No documents to update")

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)

    return stats


if __name__ == '__main__':
    main()
