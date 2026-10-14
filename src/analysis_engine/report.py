"""Human-readable build summaries, and live per-county dimension and archetype counts."""

from typing import Dict

from src.analysis_engine.archetypes import compile_archetype, proxy_mask
from src.analysis_engine.registry import Registry
from src.analysis_engine.store import HOUSEHOLDS

LEVEL_NAMES = {-1: 'unknown', 0: 'none', 1: 'moderate', 2: 'high'}


def summarize_build(build: Dict) -> str:
    lines = [f"{build['county']}: {build['status']} - {build.get('doc_count', 0):,} households, "
             f"size p50/p99 {build.get('size_p50')}/{build.get('size_p99')} B"]
    if build.get('error'):
        lines.append(f"  error: {build['error']}")
    stats = build.get('stats', {})
    if stats:
        lines.append(f"  unlinked {stats['unlinked']:,} · multi-unit {stats['multi_unit']:,} · "
                     f"stale {stats['stale']:,} · duplicate parcels {stats['duplicates']}")
    for role, names in build.get('unmapped_fields', {}).items():
        lines.append(f"  unmapped {role} fields: {', '.join(names)}")
    for name, pairs in build.get('unmapped_values', {}).items():
        lines.append(f"  unmapped values {name}: " + ', '.join(f'{v} ({n})' for v, n in pairs))
    return '\n'.join(lines)


def county_report(db, county: str, reg: Registry) -> Dict:
    """Level counts per dimension (with proxy counts) and, per archetype, n, the known-enough denominator
    (non-residential excluded) and how many of n rest on a proxy for one of its dimensions."""
    households = db[HOUSEHOLDS]
    total = households.count_documents({'county': county})
    dims = {}
    for i, name in enumerate(reg.dims):
        rows = households.aggregate([{'$match': {'county': county}},
                                     {'$group': {'_id': {'$arrayElemAt': ['$dims', i]}, 'n': {'$sum': 1}}}])
        dims[name] = {'levels': {row['_id']: row['n'] for row in rows},
                      'proxy': households.count_documents({'county': county, 'proxy': {'$bitsAllSet': 1 << i}})}
    archetypes = {}
    for name in reg.rules['archetypes']:
        match, known = compile_archetype(name, reg.rules)
        mask = proxy_mask(name, reg.rules)
        count = lambda *clauses: households.count_documents({'$and': [{'county': county}, *clauses]})  # noqa: E731
        archetypes[name] = {'n': count(match), 'known': count(known),
                            'proxy': count(match, {'proxy': {'$bitsAnySet': mask}}) if mask else 0}
    return {'county': county, 'total': total, 'dims': dims, 'archetypes': archetypes}


def format_report(report: Dict, reg: Registry) -> str:
    lines = [f"{report['county']}: {report['total']:,} households"]
    for name, entry in report['dims'].items():
        levels = ' · '.join(f"{LEVEL_NAMES[lv]} {entry['levels'].get(lv, 0):,}" for lv in (2, 1, 0, -1))
        lines.append(f"  {name:<22} {levels} · proxy {entry['proxy']:,}")
    for name, entry in report['archetypes'].items():
        label = reg.rules['archetypes'][name]['label']
        if not entry['known']:
            lines.append(f"  {label:<42} no measured source")
            continue
        split = f" (measured {entry['n'] - entry['proxy']:,} · proxy {entry['proxy']:,})" if entry['proxy'] else ''
        lines.append(f"  {label:<42} {entry['n']:,} of {entry['known']:,} known-enough{split}")
    return '\n'.join(lines)
