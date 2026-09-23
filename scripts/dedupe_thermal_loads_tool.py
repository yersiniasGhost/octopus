#!/usr/bin/env python3
"""
T-03 -- remove duplicate parcel_id documents from *ThermalLoads, then make the
uniqueness a constraint.

CuyahogaThermalLoads holds 875 parcels twice. T-02 found each pair storing
parcel_id as int in one document and as the same digits in str in the other, and
skipped the int rather than create a genuine duplicate key -- so the duplicates
and the remaining type mismatches are the same 875 documents.

Grouping is on `src.tools.parcel_id.normalize_parcel_id`, the function the audit
verifies with. Grouping on the raw value finds nothing: 123 != "123" in Python
and in MongoDB alike. For the same reason a unique index built *before* this runs
would succeed while every duplicate remained, and report the collection healthy.
Order is therefore: dedupe, re-run T-02 on the survivors, then --create-unique-index.

Keep rule, electric-first by direction (2026-09-21): newest calculated_at, then
highest kwh_hl_r2, then the longer kwh_hl_cl_loads, then the str parcel_id, then
the lowest _id. A gas model on the losing document does not save it; gas is
re-derived from billing data later. The plan reports the gas slopes it drops and
every loser is exported whole before deletion, so the drop stays reversible at
the record level. This deviates from the runbook's "never drop a doc carrying
real gas slopes" rule, deliberately.

Read-only by default. `--execute` is required to write.

Usage:
    python scripts/dedupe_thermal_loads_tool.py --county Cuyahoga --dry-run
    python scripts/dedupe_thermal_loads_tool.py --county Cuyahoga --execute
    python scripts/dedupe_thermal_loads_tool.py --create-unique-index --execute
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import DeleteOne, MongoClient

from src.tools.parcel_id import normalize_parcel_id

DEFAULT_URI = 'mongodb://localhost:27017'
DEFAULT_DB = 'empower_development'
DEFAULT_EXPORT_DIR = Path(__file__).parent.parent / 'exports'
BATCH_SIZE = 1000
GAS_SENTINELS = (-1, 0, None)
INDEX_KEYS = [('parcel_id', 1)]


class DuplicatesRemain(Exception):
    """A unique index was requested while normalized duplicates are still present."""


class CollisionSetMismatch(Exception):
    """The duplicates found here differ from the set T-02 enumerated."""


class Group(NamedTuple):
    key: str
    survivor: Dict[str, Any]
    losers: List[Dict[str, Any]]


class DedupePlan(NamedTuple):
    groups: List[Group]
    examined: int
    null_parcel_id: int

    @property
    def removed(self) -> int:
        return sum(len(g.losers) for g in self.groups)

    @property
    def gas_slopes_dropped(self) -> int:
        return sum(1 for g in self.groups for d in g.losers if has_real_gas_slope(d))

    @property
    def keys(self) -> Set[str]:
        return {g.key for g in self.groups}


def has_real_gas_slope(doc: Dict[str, Any]) -> bool:
    """A fitted gas model, as opposed to the -1/0/absent sentinels."""
    return doc.get('gas_hl_slope') not in GAS_SENTINELS


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def rank(doc: Dict[str, Any]) -> tuple:
    """Sort key for the keep rule; the largest rank survives.

    Presence flags precede their values so a missing field never has to compare
    against a present one -- tuple comparison short-circuits on the flag.
    """
    calculated_at = doc.get('calculated_at')
    r2 = doc.get('kwh_hl_r2')
    return (calculated_at is not None, calculated_at if calculated_at is not None else 0,
            _numeric(r2), r2 if _numeric(r2) else 0.0,
            len(doc.get('kwh_hl_cl_loads') or []),
            isinstance(doc.get('parcel_id'), str))


def choose_survivor(docs: List[Dict[str, Any]]):
    """Return (survivor, losers). Deterministic regardless of cursor order.

    Documents are ordered by _id before max(), which returns the first maximal
    element: a total tie therefore keeps the lowest _id rather than whichever
    copy Mongo happened to yield first.
    """
    ordered = sorted(docs, key=lambda d: str(d['_id']))
    survivor = max(ordered, key=rank)
    return survivor, [d for d in ordered if d['_id'] != survivor['_id']]


def plan_dedupe(docs: Iterable[Dict[str, Any]]) -> DedupePlan:
    by_key = defaultdict(list)
    examined = null_parcel_id = 0
    for doc in docs:
        examined += 1
        key = normalize_parcel_id(doc.get('parcel_id'))
        if key is None:
            null_parcel_id += 1
        else:
            by_key[key].append(doc)

    groups = []
    for key in sorted(by_key):
        copies = by_key[key]
        if len(copies) > 1:
            survivor, losers = choose_survivor(copies)
            groups.append(Group(key, survivor, losers))
    return DedupePlan(groups, examined, null_parcel_id)


def apply_dedupe(collection, plan: DedupePlan, execute: bool = False,
                 batch_size: int = BATCH_SIZE) -> int:
    """Delete the losers. Returns documents deleted; 0 on a dry run."""
    ids = [d['_id'] for g in plan.groups for d in g.losers]
    if not execute or not ids:
        return 0
    deleted = 0
    for start in range(0, len(ids), batch_size):
        result = collection.bulk_write(
            [DeleteOne({'_id': _id}) for _id in ids[start:start + batch_size]], ordered=False)
        deleted += result.deleted_count
    return deleted


def cross_check_against_t02(plan: DedupePlan, expected: Set[str]) -> None:
    """Fail unless the duplicate keys found here are exactly the ones T-02 saw."""
    found = plan.keys
    unexpected, missing = sorted(found - expected), sorted(expected - found)
    if unexpected or missing:
        raise CollisionSetMismatch(
            f"duplicate keys diverge from the T-02 collision export: "
            f"{len(unexpected)} not seen by T-02 ({unexpected[:5]}), "
            f"{len(missing)} seen by T-02 but no longer duplicated ({missing[:5]})")


def load_t02_collision_keys(path: Path, county: str) -> Set[str]:
    payload = json.loads(path.read_text())
    return {c['key'] for entry in payload if entry['county'] == county
            for c in entry['collisions']}


def create_unique_parcel_id_index(collection, execute: bool = False) -> str:
    """Make uniqueness a constraint, refusing while duplicates remain.

    The refusal is the substance of this function. A unique index compares BSON
    values including type, so it would build happily over int 123 alongside
    "123" and then report a collection that is still duplicated as clean.
    """
    plan = plan_dedupe(collection.find({}, {'parcel_id': 1}))
    if plan.groups:
        raise DuplicatesRemain(
            f"{plan.removed} duplicate document(s) across {len(plan.groups)} parcel(s) "
            f"remain; dedupe before indexing")
    if not execute:
        return 'dry-run'

    for name, spec in collection.index_information().items():
        if [tuple(k) for k in spec['key']] == INDEX_KEYS:
            if spec.get('unique'):
                return 'already unique'
            collection.drop_index(name)   # uniqueness cannot be added in place
            break
    return collection.create_index(INDEX_KEYS, unique=True, name='parcel_id_1')


def counties_with_thermal(db, only: str = None) -> List[str]:
    names = sorted(n[: -len('ThermalLoads')] for n in db.list_collection_names()
                   if n.endswith('ThermalLoads'))
    return [c for c in names if c == only] if only else names


def write_loser_export(rows: List[Dict[str, Any]], export_dir: Path) -> Path:
    """Export every dropped document whole, before it is deleted.

    Whole, not just _id: 549 of Cuyahoga's losers carry a fitted gas model that
    nothing else holds. Re-adding gas later should be a data problem, not a
    restore-and-replay of the checkpoint.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"t03_dedupe_losers_{datetime.now():%Y%m%d_%H%M%S}.json"
    payload = [{'county': r['county'],
                'losers': [{'key': g.key, 'survivor_id': g.survivor['_id'], 'document': d}
                           for g in r['plan'].groups for d in g.losers]}
               for r in rows if r['plan'].groups]
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def find_duplicate_ids(collection):
    """First pass: parcel_id alone, returning the _ids of duplicated parcels.

    Returns (ids, examined, null_parcel_id). CuyahogaThermalLoads is 446 MB
    across 260,939 documents; reading all of it to find 875 duplicates would
    cost gigabytes of Python dicts. parcel_id carries no index until this task
    finishes, so the second pass keys on _id, which is always indexed.
    """
    by_key = defaultdict(list)
    examined = null_parcel_id = 0
    for doc in collection.find({}, {'parcel_id': 1}):
        examined += 1
        key = normalize_parcel_id(doc.get('parcel_id'))
        if key is None:
            null_parcel_id += 1
        else:
            by_key[key].append(doc['_id'])
    ids = [_id for ids in by_key.values() if len(ids) > 1 for _id in ids]
    return ids, examined, null_parcel_id


def dedupe_county(db, county: str, execute: bool = False) -> Dict[str, Any]:
    collection = db[f'{county}ThermalLoads']
    ids, examined, null_parcel_id = find_duplicate_ids(collection)
    docs = collection.find({'_id': {'$in': ids}}) if ids else []
    plan = plan_dedupe(docs)._replace(examined=examined, null_parcel_id=null_parcel_id)
    deleted = apply_dedupe(collection, plan, execute=execute)
    return {'county': county, 'plan': plan, 'deleted': deleted}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--county', help='single county, e.g. Cuyahoga')
    p.add_argument('--uri', default=DEFAULT_URI)
    p.add_argument('--db', default=DEFAULT_DB)
    p.add_argument('--export-dir', type=Path, default=DEFAULT_EXPORT_DIR)
    p.add_argument('--t02-collisions', type=Path,
                   help='T-02 collision export to cross-check the duplicate set against')
    p.add_argument('--create-unique-index', action='store_true',
                   help='build the unique parcel_id index instead of deduping')
    p.add_argument('--dry-run', action='store_true', default=True)
    p.add_argument('--execute', action='store_true', help='actually write')
    args = p.parse_args()
    execute = args.execute

    db = MongoClient(args.uri)[args.db]
    counties = counties_with_thermal(db, args.county)
    if not counties:
        print(f"no ThermalLoads collection for county {args.county!r}", file=sys.stderr)
        return 1

    if args.create_unique_index:
        return run_index(db, counties, execute)
    return run_dedupe(db, counties, execute, args)


def run_dedupe(db, counties: List[str], execute: bool, args) -> int:
    print(f"=== T-03 thermal dedupe === {'EXECUTE' if execute else 'DRY RUN (no writes)'}")
    print(f"  {'county':<12}{'examined':>10}{'dup_parcels':>13}{'to_remove':>11}"
          f"{'deleted':>9}{'gas_dropped':>13}{'null_pid':>10}")
    rows, totals = [], Counter()
    for county in counties:
        row = dedupe_county(db, county, execute=execute)
        plan = row['plan']
        if plan.examined == 0:
            continue
        rows.append(row)
        totals['examined'] += plan.examined
        totals['groups'] += len(plan.groups)
        totals['removed'] += plan.removed
        totals['deleted'] += row['deleted']
        totals['gas'] += plan.gas_slopes_dropped
        totals['null'] += plan.null_parcel_id
        if plan.groups:
            print(f"  {county:<12}{plan.examined:>10,}{len(plan.groups):>13,}{plan.removed:>11,}"
                  f"{row['deleted']:>9,}{plan.gas_slopes_dropped:>13,}{plan.null_parcel_id:>10,}")
    print(f"  {'TOTAL':<12}{totals['examined']:>10,}{totals['groups']:>13,}{totals['removed']:>11,}"
          f"{totals['deleted']:>9,}{totals['gas']:>13,}{totals['null']:>10,}")

    if args.t02_collisions:
        for row in rows:
            expected = load_t02_collision_keys(args.t02_collisions, row['county'])
            if expected or row['plan'].groups:
                cross_check_against_t02(row['plan'], expected)
        print(f"\n  cross-check: duplicate keys match the T-02 collision export exactly.")

    if totals['removed']:
        path = write_loser_export(rows, args.export_dir)
        print(f"\n  {totals['gas']:,} of the {totals['removed']:,} dropped document(s) carry a "
              f"fitted gas model.")
        print(f"  Every dropped document is exported whole first: {path}")
    if not execute:
        print("\n  dry run -- nothing written. Re-run with --execute.")
    return 0


def run_index(db, counties: List[str], execute: bool) -> int:
    print(f"=== T-03 unique parcel_id index === "
          f"{'EXECUTE' if execute else 'DRY RUN (no writes)'}")
    failures = 0
    for county in counties:
        try:
            outcome = create_unique_parcel_id_index(db[f'{county}ThermalLoads'], execute=execute)
        except DuplicatesRemain as exc:
            outcome, failures = f"REFUSED -- {exc}", failures + 1
        print(f"  {county:<14}{outcome}")
    if failures:
        print(f"\n  {failures} collection(s) still duplicated. Dedupe them first.")
    elif not execute:
        print("\n  dry run -- no index created. Re-run with --execute.")
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
