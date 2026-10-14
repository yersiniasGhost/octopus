"""Recount a county's sources independently of the build and compare with its analysis_coverage document (§15.4).

Read-only. `meters`, `linked` and `stale` come from count_documents / an aggregation on the source collection, never
from engine code. `nonres` is the one non-independent count: it reuses `summarize_usage` with the registry's span
params (the 50,000 kWh rule needs the engine's 12-reading annual sum), then applies `annual_kwh > nonres_kwh`.
"""

import random
from typing import Dict, List

from src.analysis_engine.build import month_of
from src.analysis_engine.registry import Registry
from src.analysis_engine.sources import all_counties, collection_name
from src.analysis_engine.store import COVERAGE
from src.analysis_engine.usage import summarize_usage

KEYS = ('meters', 'linked', 'stale', 'nonres')
P1_COUNTIES = ('Franklin', 'Cuyahoga', 'Adams')
_LINKED = {'$or': [{'parcel_key': {'$nin': [None, '']}}, {'parcel_id': {'$nin': [None, '']}}]}


def stale_cutoff(build_month: int, max_age_months: int) -> str:
    """'YYYY-MM' of the oldest read still fresh: is_fresh keeps reads up to max_age_months before build_month."""
    year, month = divmod(build_month // 100 * 12 + build_month % 100 - 1 - max_age_months, 12)
    return f'{year:04d}-{month + 1:02d}'


def source_counts(db, county: str, build_month: int, reg: Registry) -> Dict[str, int]:
    params, col = reg.rules['params']['usage'], db[collection_name('electrical', county)]
    pipeline = [{'$project': {'last': {'$max': {'$map': {'input': {'$objectToArray': {'$ifNull': ['$time_series_elec', {}]}},
                                                           'in': '$$this.k'}}}}},
                {'$match': {'last': {'$ne': None, '$lt': stale_cutoff(build_month, params['max_age_months'])}}},
                {'$count': 'n'}]
    stale = next(iter(col.aggregate(pipeline)), {}).get('n', 0)
    nonres = sum((u := summarize_usage(d.get('time_series_elec'), params['min_span_days'], params['max_span_days'])
                  ).annual_kwh is not None and u.annual_kwh > params['nonres_kwh']
                 for d in col.find({}, {'time_series_elec': 1}))
    return {'meters': col.count_documents({}), 'linked': col.count_documents(_LINKED), 'stale': stale,
            'nonres': nonres}


def reconcile(db, counties: List[str], reg: Registry, build_month: int) -> List[Dict]:
    """One row per county: per key a (source, coverage) pair, and ok when every pair agrees (no coverage = not ok).

    Each county is recounted at its coverage document's build month; build_month is the fallback without one."""
    rows = []
    for county in counties:
        cov = db[COVERAGE].find_one({'_id': county})
        month = month_of(cov['built_at']) if cov and cov.get('built_at') else build_month  # recount as of the build
        source = source_counts(db, county, month, reg)
        row = {'county': county, **{k: (source[k], (cov or {}).get(k)) for k in KEYS}}
        rows.append({**row, 'ok': cov is not None and all(a == b for a, b in (row[k] for k in KEYS))})
    return rows


def format_row(row: Dict) -> str:
    bad = [f'{k} {row[k][0]} != {row[k][1]}' for k in KEYS if row[k][0] != row[k][1]]
    return f"{row['county']}: " + ('ok' if row['ok'] else 'MISMATCH ' + (', '.join(bad) or 'no coverage document'))


def sample_counties(db, rng_seed: int) -> List[str]:
    """Franklin; largest linked and largest unlinked county outside the P1 three; Montgomery; one seeded random other."""
    names = set(db.list_collection_names())
    counties = all_counties(db)
    size = {c: db[collection_name('electrical', c)].count_documents({}) for c in counties}
    linked = [c for c in counties if collection_name('residential', c) in names]
    pick = lambda pool: max(sorted(pool), key=size.get)  # noqa: E731
    chosen = ['Franklin', pick(set(linked) - set(P1_COUNTIES) - {'Montgomery'})]
    chosen += [pick(set(counties) - set(linked) - set(chosen) - {'Montgomery'}), 'Montgomery']
    return chosen + [random.Random(rng_seed).choice(sorted(set(counties) - set(chosen)))]
