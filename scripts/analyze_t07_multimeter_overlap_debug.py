#!/usr/bin/env python3
"""
Read-only: how much of T-07's write population is exposed to the unfixed T-06
multi-meter defect.

T-07 creates thermal records for parcels that have none. `get_electrical_data()`
assigns `data[parcel_id] = time_series` inside the cursor loop, so when a parcel
owns more than one eligible electrical document the last one the cursor happens
to yield wins and the rest are discarded without a warning (T-06). For a
*recompute* that produces a wrong slope on an existing record; for T-07 it
manufactures a brand-new record whose slopes were fitted on partial household
load, with nothing on the document to say so.

The audit's `duplicates electrical_excess` counts collisions across the whole
collection. That is not the number that matters here -- what matters is the
intersection with the parcels T-07 would actually write. This measures that
intersection using the production selection path (`get_target_parcels`) and the
production eligibility gate (`len(time_series) >= 2`), so it cannot drift from
what the tool would really do.

Usage:
    python scripts/analyze_t07_multimeter_overlap_debug.py [--county NAME]
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from calculate_missing_thermal_loads_tool import get_target_parcels  # noqa: E402
from src.tools.mongo import get_empower_db  # noqa: E402

# T-07's six counties, ascending by population (the runbook's execute order).
T07_COUNTIES = ['Athens', 'Hancock', 'Ottawa', 'Cuyahoga', 'Franklin', 'Montgomery']

ELIGIBLE_MIN_PERIODS = 2  # the gate get_electrical_data() actually applies


def measure(db, county: str) -> dict:
    targets = set(get_target_parcels(db, county, recompute_all=False))
    if not targets:
        return {'county': county, 'targets': 0, 'collided': 0, 'excess': 0, 'worst': 0}

    # Count eligible electrical documents per target parcel, in one pass.
    per_parcel = Counter()
    ineligible = defaultdict(int)
    for doc in db[f'{county}ElectricalDB'].find(
        {'parcel_id': {'$in': list(targets)}}, {'parcel_id': 1, 'time_series_elec': 1}
    ):
        pid = doc['parcel_id']
        if len(doc.get('time_series_elec') or {}) >= ELIGIBLE_MIN_PERIODS:
            per_parcel[pid] += 1
        else:
            ineligible[pid] += 1

    collided = {p: n for p, n in per_parcel.items() if n > 1}
    return {
        'county': county,
        'targets': len(targets),
        'with_data': len(per_parcel),
        'collided': len(collided),
        'excess': sum(n - 1 for n in collided.values()),
        'worst': max(collided.values()) if collided else 0,
        'sample': sorted(collided.items(), key=lambda kv: -kv[1])[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--county', type=str, default=None, help='restrict to one county')
    args = parser.parse_args()

    counties = [args.county] if args.county else T07_COUNTIES
    db = get_empower_db()

    print(f"\n{'county':<14}{'targets':>10}{'with_data':>11}{'collided':>10}"
          f"{'excess':>9}{'worst':>7}{'pct':>8}")
    print('-' * 69)
    totals = Counter()
    for county in counties:
        r = measure(db, county)
        pct = (100.0 * r['collided'] / r['targets']) if r['targets'] else 0.0
        print(f"{r['county']:<14}{r['targets']:>10,}{r.get('with_data', 0):>11,}"
              f"{r['collided']:>10,}{r['excess']:>9,}{r['worst']:>7}{pct:>7.2f}%")
        for pid, n in r.get('sample', []):
            print(f"{'':<14}  {pid} -> {n} eligible documents")
        for k in ('targets', 'with_data', 'collided', 'excess'):
            totals[k] += r.get(k, 0)
    print('-' * 69)
    pct = (100.0 * totals['collided'] / totals['targets']) if totals['targets'] else 0.0
    print(f"{'TOTAL':<14}{totals['targets']:>10,}{totals['with_data']:>11,}"
          f"{totals['collided']:>10,}{totals['excess']:>9,}{'':>7}{pct:>7.2f}%\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
