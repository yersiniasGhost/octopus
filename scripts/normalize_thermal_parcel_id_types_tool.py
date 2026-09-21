#!/usr/bin/env python3
"""
T-02 -- convert non-string parcel_id in *ThermalLoads to its string form.

Nine counties store parcel_id as int/Int64 in ThermalLoads while ElectricalDB
stores str: Belmont, Coshocton, Cuyahoga, Guernsey, Harrison, Holmes, Lawrence,
Morgan, Muskingum -- 67,307 documents. `get_missing_parcels()` subtracts two raw
Python sets, and 123 != "123", so eight of those counties report 100% missing and
a calculation run inserts a complete duplicate set.

Normalization is `src.tools.parcel_id.normalize_parcel_id`, the same function the
audit uses to verify the result. Measured 2026-09-21: all 67,307 values land on
an existing electrical string under that function, with nothing unmatched, so the
conversion is lossless for every value actually present.

Collisions are reported and skipped, never merged. Cuyahoga holds 875 int
documents whose string form is already taken by another document -- those are the
875 duplicates T-03 dedupes. Merging them is T-03's job.

Read-only by default. `--execute` is required to write.

Usage:
    python scripts/normalize_thermal_parcel_id_types_tool.py --dry-run
    python scripts/normalize_thermal_parcel_id_types_tool.py --county Morgan --dry-run
    python scripts/normalize_thermal_parcel_id_types_tool.py --county Morgan --execute
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient, UpdateOne

from src.tools.parcel_id import normalize_parcel_id

DEFAULT_URI = 'mongodb://localhost:27017'
DEFAULT_DB = 'empower_development'
DEFAULT_EXPORT_DIR = Path(__file__).parent.parent / 'exports'
BATCH_SIZE = 1000


class Plan(NamedTuple):
    conversions: List[Tuple[Any, str]]   # (_id, new string value)
    collisions: List[Dict[str, Any]]     # {'key': str, 'ids': [...], 'reason': str}
    already_string: int
    null_parcel_id: int

    @property
    def collided_docs(self) -> int:
        return sum(len(c['ids']) for c in self.collisions)


def plan_conversions(docs: Iterable[Dict[str, Any]]) -> Plan:
    """Decide, per document, whether its parcel_id can be safely stringified.

    Contested keys convert nothing. Collisions are found by counting normalized
    values across the whole batch rather than claiming keys as they arrive:
    Mongo guarantees no cursor order, and a first-come-wins guard would convert
    a different member of a colliding pair on every run.
    """
    claimed_by_string = set()          # keys already held by a str document
    pending = defaultdict(list)        # normalized key -> [_id] of non-str documents
    already_string = null_parcel_id = 0

    for doc in docs:
        value = doc.get('parcel_id')
        key = normalize_parcel_id(value)
        if key is None:
            null_parcel_id += 1
        elif isinstance(value, str):
            already_string += 1
            claimed_by_string.add(key)
        else:
            pending[key].append(doc['_id'])

    conversions, collisions = [], []
    for key, ids in pending.items():
        if key in claimed_by_string:
            collisions.append({'key': key, 'ids': ids, 'reason': 'string document already holds this key'})
        elif len(ids) > 1:
            collisions.append({'key': key, 'ids': ids, 'reason': 'several non-string documents normalize alike'})
        else:
            conversions.append((ids[0], key))

    conversions.sort(key=lambda pair: pair[1])
    collisions.sort(key=lambda c: c['key'])
    return Plan(conversions, collisions, already_string, null_parcel_id)


def apply_conversions(collection, conversions: List[Tuple[Any, str]],
                      execute: bool = False, batch_size: int = BATCH_SIZE) -> int:
    """Write the planned conversions. Returns documents modified; 0 on a dry run.

    Updates are keyed on _id, never on parcel_id: parcel_id carries no index
    until T-05, so filtering on it would make every update a collection scan.
    """
    if not execute or not conversions:
        return 0
    modified = 0
    for start in range(0, len(conversions), batch_size):
        batch = conversions[start:start + batch_size]
        result = collection.bulk_write(
            [UpdateOne({'_id': _id}, {'$set': {'parcel_id': value}}) for _id, value in batch],
            ordered=False)
        modified += result.modified_count
    return modified


def counties_with_thermal(db, only: str = None) -> List[str]:
    names = sorted(n[: -len('ThermalLoads')] for n in db.list_collection_names()
                   if n.endswith('ThermalLoads'))
    return [c for c in names if c == only] if only else names


def normalize_county(db, county: str, execute: bool = False) -> Dict[str, Any]:
    collection = db[f'{county}ThermalLoads']
    docs = list(collection.find({}, {'parcel_id': 1}))
    plan = plan_conversions(docs)
    modified = apply_conversions(collection, plan.conversions, execute=execute)
    return {'county': county, 'examined': len(docs), 'planned': len(plan.conversions),
            'modified': modified, 'already_string': plan.already_string,
            'collisions': len(plan.collisions), 'collided_docs': plan.collided_docs,
            'null_parcel_id': plan.null_parcel_id, 'collision_detail': plan.collisions}


def write_collision_report(rows: List[Dict[str, Any]], export_dir: Path) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"t02_parcel_id_collisions_{datetime.now():%Y%m%d_%H%M%S}.json"
    payload = [{'county': r['county'], 'collisions': r['collision_detail']}
               for r in rows if r['collision_detail']]
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--county', help='single county, e.g. Morgan')
    p.add_argument('--uri', default=DEFAULT_URI)
    p.add_argument('--db', default=DEFAULT_DB)
    p.add_argument('--export-dir', type=Path, default=DEFAULT_EXPORT_DIR)
    p.add_argument('--dry-run', action='store_true', default=True)
    p.add_argument('--execute', action='store_true', help='actually write the conversions')
    args = p.parse_args()
    execute = args.execute

    db = MongoClient(args.uri)[args.db]
    counties = counties_with_thermal(db, args.county)
    if not counties:
        print(f"no ThermalLoads collection for county {args.county!r}", file=sys.stderr)
        return 1

    print(f"=== T-02 parcel_id normalization === {'EXECUTE' if execute else 'DRY RUN (no writes)'}")
    print(f"  {'county':<12}{'examined':>10}{'planned':>10}{'modified':>10}"
          f"{'already_str':>13}{'collisions':>12}{'null_pid':>10}")
    rows, totals = [], Counter()
    for county in counties:
        row = normalize_county(db, county, execute=execute)
        if row['examined'] == 0:
            continue
        rows.append(row)
        for field in ('examined', 'planned', 'modified', 'already_string',
                      'collided_docs', 'null_parcel_id'):
            totals[field] += row[field]
        if row['planned'] or row['collisions']:
            print(f"  {county:<12}{row['examined']:>10,}{row['planned']:>10,}{row['modified']:>10,}"
                  f"{row['already_string']:>13,}{row['collided_docs']:>12,}{row['null_parcel_id']:>10,}")
    print(f"  {'TOTAL':<12}{totals['examined']:>10,}{totals['planned']:>10,}{totals['modified']:>10,}"
          f"{totals['already_string']:>13,}{totals['collided_docs']:>12,}{totals['null_parcel_id']:>10,}")

    if any(r['collision_detail'] for r in rows):
        path = write_collision_report(rows, args.export_dir)
        print(f"\n  {totals['collided_docs']:,} document(s) skipped on collision -- these are "
              f"T-03's duplicates, not this task's to merge.")
        print(f"  detail: {path}")
    if not execute:
        print("\n  dry run -- nothing written. Re-run with --execute.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
