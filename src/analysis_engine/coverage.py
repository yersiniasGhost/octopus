"""One coverage document per county: counts and collection names only, no household data."""

from typing import Dict, Optional, Set

from src.analysis_engine.sources import collection_name

_LEVELS = ('-1', '0', '1', '2')  # BSON keys must be strings


def _share(n: int, total: int) -> float:
    return round(n / total, 4) if total else 0.0


def coverage_doc(build: Dict, report: Optional[Dict], countykeys: Dict[str, str], present: Dict[str, str],
                 rules: Dict, collections: Set[str]) -> Dict:
    county, total, stats = build['county'], build['doc_count'], build['stats']
    levels = {dim: dict(zip(_LEVELS, row)) for dim, row in zip(rules['dims'], stats['levels'])}
    hud = rules['tables']['hud_low_income_fy2026']['counties'].get(county, {})
    doc = {'_id': county, 'county': county, 'build_id': build.get('_id', build['built_at']),
           'built_at': build['built_at'], 'meters': total, 'linked': total - stats['unlinked'],
           'stale': stats['stale'], 'nonres': stats['nonres'],
           **{f'{k}_share': _share(stats[k], total) for k in ('priced', 'income_known', 'usable_fit')},
           'boundary': stats['boundary'], 'levels': levels, 'sources_present': sorted(present),
           'countykeys': {'missing': sorted(n for n in countykeys.values() if n not in collections),
                          'disagree': sorted(r for r, n in countykeys.items() if n != collection_name(r, county))},
           'heat_fuel_source': 'measured' if any(levels['electrification'][k] for k in _LEVELS[1:]) else 'none',
           'fallbacks': stats['fallbacks'], 'hud_estimated': hud.get('estimated') is True}
    if report:
        doc['archetypes'] = report['archetypes']
    return doc
