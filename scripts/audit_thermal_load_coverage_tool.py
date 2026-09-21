#!/usr/bin/env python3
"""
Audit *ThermalLoads coverage and integrity against *ElectricalDB.

Reports the populations the thermal-slope remediation works through:
  coverage   parcels eligible for slopes vs parcels that have them
  types      parcel_id BSON type mismatches between Electrical and Thermal
  duplicates duplicate parcel_id within each collection
  joinkey    parcel_id vs parcel_key as the join field
  staleness  electrical deliveries newer than the thermal calculation
  slopes     null / zero / absent kwh_hl_slope records

Read-only. Never writes. Safe to run at any point in the remediation.

Usage:
    python scripts/audit_thermal_load_coverage_tool.py --check all
    python scripts/audit_thermal_load_coverage_tool.py --check coverage --county Montgomery
    python scripts/audit_thermal_load_coverage_tool.py --check types --json out.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient

from src.tools.parcel_id import normalize_parcel_id as _norm

MIN_PERIODS = 3  # regression minimum enforced by calculate_missing_thermal_loads_tool.py


def _counties(db, only: str) -> list:
    names = set(db.list_collection_names())
    out = sorted(n[: -len('ThermalLoads')] for n in names if n.endswith('ThermalLoads'))
    return [c for c in out if c == only] if only else out


def _load_electrical(db, county: str) -> dict:
    """Return per-parcel electrical facts for eligible docs."""
    eligible, no_pid, short, dup = {}, 0, 0, Counter()
    for d in db[f'{county}ElectricalDB'].find(
        {}, {'parcel_id': 1, 'parcel_key': 1, 'time_series_elec': 1, 'last_utility_ingest': 1}
    ):
        if len(d.get('time_series_elec') or {}) < MIN_PERIODS:
            short += 1
            continue
        pid = _norm(d.get('parcel_id'))
        if pid is None:
            no_pid += 1
            continue
        dup[pid] += 1
        eligible[pid] = {'parcel_key': _norm(d.get('parcel_key')),
                         'ingest': d.get('last_utility_ingest')}
    return {'eligible': eligible, 'no_pid': no_pid, 'short': short,
            'dup_excess': sum(v - 1 for v in dup.values() if v > 1)}


def _load_thermal(db, county: str) -> dict:
    """Return per-parcel thermal facts."""
    by_pid, keys, dup = {}, set(), Counter()
    types = Counter()
    for d in db[f'{county}ThermalLoads'].find(
        {}, {'parcel_id': 1, 'parcel_key': 1, 'calculated_at': 1, 'kwh_hl_slope': 1, 'gas_hl_slope': 1}
    ):
        types[type(d.get('parcel_id')).__name__] += 1
        pid = _norm(d.get('parcel_id'))
        if pid is not None:
            dup[pid] += 1
            by_pid[pid] = d
        key = _norm(d.get('parcel_key'))
        if key:
            keys.add(key)
    return {'by_pid': by_pid, 'keys': keys, 'types': types,
            'dup_excess': sum(v - 1 for v in dup.values() if v > 1)}


def check_coverage(db, counties: list) -> list:
    rows = []
    for c in counties:
        e, t = _load_electrical(db, c), _load_thermal(db, c)
        e_keys = {v['parcel_key'] for v in e['eligible'].values() if v['parcel_key']}
        keyed = bool(e_keys and t['keys'])
        miss_pid = len(set(e['eligible']) - set(t['by_pid']))
        miss_key = len(e_keys - t['keys']) if keyed else None
        rows.append({'county': c, 'eligible': len(e['eligible']), 'thermal': len(t['by_pid']),
                     'missing_by_parcel_id': miss_pid, 'missing_by_parcel_key': miss_key,
                     'best': miss_key if keyed else miss_pid,
                     'no_parcel_id': e['no_pid'], 'below_min_periods': e['short']})
    return rows


def check_types(db, counties: list) -> list:
    rows = []
    for c in counties:
        t = _load_thermal(db, c)
        e = Counter(type(d['parcel_id']).__name__
                    for d in db[f'{c}ElectricalDB'].find({'parcel_id': {'$ne': None}}, {'parcel_id': 1}))
        nonstr = sum(v for k, v in t['types'].items() if k not in ('str', 'NoneType'))
        rows.append({'county': c, 'thermal_types': dict(t['types']), 'electrical_types': dict(e),
                     'thermal_non_string': nonstr, 'mismatch': nonstr > 0})
    return rows


def check_duplicates(db, counties: list) -> list:
    rows = []
    for c in counties:
        e, t = _load_electrical(db, c), _load_thermal(db, c)
        rows.append({'county': c, 'electrical_excess': e['dup_excess'], 'thermal_excess': t['dup_excess']})
    return rows


def check_joinkey(db, counties: list) -> list:
    rows = []
    for c in counties:
        e, t = _load_electrical(db, c), _load_thermal(db, c)
        e_keys = {v['parcel_key'] for v in e['eligible'].values() if v['parcel_key']}
        has_key = bool(e_keys and t['keys'])
        miss_pid = len(set(e['eligible']) - set(t['by_pid']))
        miss_key = len(e_keys - t['keys']) if has_key else None
        rows.append({'county': c, 'has_parcel_key': has_key,
                     'missing_by_parcel_id': miss_pid, 'missing_by_parcel_key': miss_key,
                     'phantom': (miss_pid - miss_key) if has_key else 0})
    return rows


def check_staleness(db, counties: list) -> list:
    rows = []
    for c in counties:
        deliveries = Counter()
        for d in db[f'{c}ElectricalDB'].find({'parcel_id': {'$ne': None}}, {'last_utility_ingest': 1}):
            deliveries[d.get('last_utility_ingest')] += 1
        t = _load_thermal(db, c)
        stamped = sum(1 for d in t['by_pid'].values() if d.get('calculated_at'))
        rows.append({'county': c, 'deliveries': {str(k): v for k, v in deliveries.items()},
                     'thermal_docs': len(t['by_pid']), 'with_calculated_at': stamped,
                     'without_provenance': len(t['by_pid']) - stamped})
    return rows


def check_slopes(db, counties: list) -> list:
    rows = []
    for c in counties:
        col = db[f'{c}ThermalLoads']
        rows.append({
            'county': c,
            'null_or_absent': col.count_documents(
                {'$or': [{'kwh_hl_slope': None}, {'kwh_hl_slope': {'$exists': False}}]}),
            'exactly_zero': col.count_documents({'kwh_hl_slope': 0}),
            'real_gas_slopes': col.count_documents({'gas_hl_slope': {'$nin': [-1, None, 0]}}),
        })
    return rows


CHECKS = {'coverage': check_coverage, 'types': check_types, 'duplicates': check_duplicates,
          'joinkey': check_joinkey, 'staleness': check_staleness, 'slopes': check_slopes}


def _print(name: str, rows: list) -> None:
    print(f"\n=== {name} ===")
    if not rows:
        print("  (no counties matched)")
        return
    cols = [k for k in rows[0] if k != 'county']
    width = max(len(r['county']) for r in rows) + 2
    print(f"  {'county':<{width}}" + "".join(f"{c:>26}" for c in cols))
    for r in rows:
        cells = "".join(f"{(format(r[c], ',') if isinstance(r[c], int) else str(r[c]))[:25]:>26}" for c in cols)
        print(f"  {r['county']:<{width}}{cells}")
    totals = {c: sum(r[c] for r in rows) for c in cols if all(isinstance(r[c], int) for r in rows)}
    if totals:
        print(f"  {'TOTAL':<{width}}" + "".join(
            f"{format(totals[c], ',') if c in totals else '':>26}" for c in cols))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--check', default='coverage', choices=list(CHECKS) + ['all'])
    p.add_argument('--county', default=None, help='restrict to one county')
    p.add_argument('--uri', default='mongodb://localhost:27017')
    p.add_argument('--database', default='empower_development')
    p.add_argument('--json', default=None, help='also write results to this JSON path')
    args = p.parse_args()

    db = MongoClient(args.uri)[args.database]
    counties = _counties(db, args.county)
    if not counties:
        print(f"no ThermalLoads collections matched county={args.county!r}")
        return 1

    names = [args.check] if args.check != 'all' else list(CHECKS)
    out = {}
    for name in names:
        rows = CHECKS[name](db, counties)
        out[name] = rows
        _print(name, rows)
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1, default=str))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
