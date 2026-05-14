"""Backfill participants.demographics.customer_name from the per-county

`<County>CountyDemographic` collections, using `linkage.parcel_id` + `linkage.county_key`
as the join key.

Background
----------
The `participants` collection is a denormalized snapshot built from the county
source-of-truth demographics. When the original participant import ran, only a
fraction of the records had `demographics.customer_name` filled in — for
example, in Text81 (Franklin County), only ~8% of participants carried a name
on their participant doc, even though 99.8% of those parcels DO have a
`customer_name` in `FranklinCountyDemographic`.

This tool walks every participant with `demographics.customer_name` empty/null,
looks up the matching parcel in the appropriate county demographic collection
(resolved via `CountyKeys`, the authoritative county-collection registry), and
writes the name back to `participants.demographics.customer_name`.

It is idempotent: re-running after a successful run is a no-op because every
participant that already has a name is skipped.

Usage
-----
    # Dry run (default) — reports counts, makes no writes:
    python scripts/backfill_participant_customer_name_tool.py

    # Limit to one county for a small smoke test:
    python scripts/backfill_participant_customer_name_tool.py --county Franklin

    # Actually write:
    python scripts/backfill_participant_customer_name_tool.py --apply
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Optional

# Allow `from src...` when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient, UpdateOne

from src.utils.envvars import EnvVars


def get_db():
    env = EnvVars()
    mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')
    db_name = env.get_env('MONGODB_OCTOPUS') or 'empower_development'
    return MongoClient(mongo_uri)[db_name]


def normalize_county_key(raw: Optional[str]) -> Optional[str]:
    """`linkage.county_key` is sometimes 'Franklin', sometimes 'FranklinCounty'.

    `CountyKeys.county` is always the bare name. Strip the suffix.
    """
    if not raw:
        return None
    return raw[:-len('County')] if raw.endswith('County') else raw


def build_county_demographic_map(db) -> Dict[str, str]:
    """county bare name → demographic collection name, via CountyKeys."""
    mapping = {}
    for c in db.CountyKeys.find({}, {'county': 1, 'demographic_data': 1}):
        if c.get('demographic_data'):
            mapping[c['county']] = c['demographic_data']
    return mapping


def backfill(db, apply: bool = False, county_filter: Optional[str] = None) -> Dict[str, int]:
    county_map = build_county_demographic_map(db)

    # Candidates: participants missing customer_name but linked to a parcel.
    query = {
        '$or': [
            {'demographics.customer_name': None},
            {'demographics.customer_name': ''},
            {'demographics.customer_name': {'$exists': False}},
        ],
        'linkage.parcel_id': {'$nin': [None, '']},
    }
    if county_filter:
        # Match both 'Franklin' and 'FranklinCounty' shapes.
        query['linkage.county_key'] = {'$in': [county_filter, county_filter + 'County']}

    total_candidates = db.participants.count_documents(query)
    print(f'Candidates (participants missing customer_name with a parcel_id): {total_candidates:,}')

    # Group candidates by their target demographic collection, then bulk-lookup.
    by_county: Dict[str, list] = {}
    for p in db.participants.find(query, {'_id': 1, 'linkage.parcel_id': 1, 'linkage.county_key': 1}):
        county = normalize_county_key((p.get('linkage') or {}).get('county_key'))
        if not county or county not in county_map:
            continue
        by_county.setdefault(county, []).append(p)

    stats = {'scanned': total_candidates, 'matched': 0, 'updated': 0, 'no_county_map': 0}

    for county, participants in sorted(by_county.items()):
        coll = county_map[county]
        parcel_ids = [p['linkage']['parcel_id'] for p in participants]

        # Bulk-fetch all source rows for this county in one round-trip.
        source_names: Dict[str, str] = {}
        for doc in db[coll].find(
            {'parcel_id': {'$in': parcel_ids}, 'customer_name': {'$nin': [None, '']}},
            {'parcel_id': 1, 'customer_name': 1},
        ):
            source_names[doc['parcel_id']] = doc['customer_name']

        county_matched = sum(1 for p in participants if p['linkage']['parcel_id'] in source_names)
        print(f'  {county:14s} → {coll}: {county_matched:,}/{len(participants):,} parcels have a name')
        stats['matched'] += county_matched

        if apply and source_names:
            ops = []
            for p in participants:
                name = source_names.get(p['linkage']['parcel_id'])
                if not name:
                    continue
                ops.append(UpdateOne(
                    {'_id': p['_id']},
                    {'$set': {'demographics.customer_name': name}},
                ))
            if ops:
                result = db.participants.bulk_write(ops, ordered=False)
                stats['updated'] += result.modified_count

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='Actually write changes. Default is dry-run.')
    parser.add_argument('--county', help='Restrict to one county (bare name, e.g. "Franklin").')
    args = parser.parse_args()

    db = get_db()
    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'Mode: {mode}')
    if args.county:
        print(f'County filter: {args.county}')
    print()

    stats = backfill(db, apply=args.apply, county_filter=args.county)
    print()
    print('Summary:')
    print(f'  Scanned candidates:   {stats["scanned"]:,}')
    print(f'  Matched in county DB: {stats["matched"]:,}')
    print(f'  Updated:              {stats["updated"]:,}')
    if not args.apply and stats['matched']:
        print(f'\nRe-run with --apply to write {stats["matched"]:,} customer_name values.')


if __name__ == '__main__':
    sys.exit(main())
