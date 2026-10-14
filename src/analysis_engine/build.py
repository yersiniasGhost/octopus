"""Two-pass county build: pass 1 learns the county's distributions, pass 2 assigns levels and stages documents.

Assembly is deterministic, so pass 2 re-assembles from the in-memory parcel indexes instead of holding a
county's households in memory between passes (Franklin: 475k meters).
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import bson

from src.analysis_engine.coverage import coverage_doc
from src.analysis_engine.household import assemble
from src.analysis_engine.ids import analysis_id, is_surrogate
from src.analysis_engine.registry import Registry
from src.analysis_engine.rules import Distributions, cutpoints, finalize, quantile, usable_fit, usage_ok
from src.analysis_engine.report import county_report
from src.analysis_engine.sources import CountySources, countykeys_collections, identity, iter_electrical, load_county_sources
from src.analysis_engine.store import MongoStore
from src.analysis_engine.usage import is_fresh
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)
MAX_P99_BYTES = 1024
_BATCH = 1000
_MAX_NAMES = 20


class BuildError(RuntimeError):
    """A county build was refused before its swap; the previous version stays live."""


def doc_size(doc: Dict) -> int:
    return len(bson.encode(doc))


def check_gates(doc_count: int, source_count: int, sizes_sorted: List[int], surrogate_ids: int = 0,
                nonres: Tuple[int, int] = (0, 0), wrong_county: int = 0, unmapped: Optional[Dict] = None) -> List[str]:
    """Pre-swap gates (spec §12): one document per meter, p99 size under 1 KB, nonres counts agree between passes,
    no document from another county, and no source field or value the registry cannot place."""
    failures = []
    if source_count == 0:
        failures.append('no source meters; refusing to replace the county')
    if doc_count != source_count:
        failures.append(f'doc count {doc_count} != source meter count {source_count}')
    p99 = quantile(sizes_sorted, 99)
    if p99 is not None and p99 >= MAX_P99_BYTES:
        failures.append(f'p99 document size {p99} B is not under {MAX_P99_BYTES} B')
    if surrogate_ids:
        failures.append(f'{surrogate_ids} document _id(s) still carry a readable source id')
    if nonres[0] != nonres[1]:
        failures.append(f'nonres pass-1 {nonres[0]} != staged {nonres[1]}')
    if wrong_county:
        failures.append(f'{wrong_county} document(s) carry another county')
    if unmapped and (unmapped.get('fields') or unmapped.get('values')):
        names = [f'{role}.{field}' for role, fields in unmapped.get('fields', {}).items() for field in fields]
        names += [f'{name}={value}' for name, pairs in unmapped.get('values', {}).items() for value, _ in pairs]
        failures.append(f"unmapped fields/values: {', '.join(names[:_MAX_NAMES])}")
    return failures


def _distributions(db, county: str, src: CountySources, reg: Registry, build_month: int) -> Tuple[Distributions, int]:
    """Pass 1: the county's distributions and how many meters assemble as nonres (independent of usage_ok)."""
    params, kwh, hl, nonres = reg.rules['params'], [], [], 0
    for meter in iter_electrical(db, county):
        src.tracker.observe('electrical', meter)
        hh = assemble(meter, src.match(meter), county, build_month, reg).doc
        nonres += hh.get('nonres') is True
        if usage_ok(hh, params, build_month):
            kwh.append(hh['annual_kwh'])
        if usable_fit(hh, params):
            hl.append(hh['hl_per_sqft'])
    return Distributions.from_values(kwh, hl), nonres


def _boundaries(params: Dict) -> List[Tuple[str, float]]:
    """(stored field, value) pairs where a rounded percent sits exactly on a registry threshold."""
    income, burden = params['income_need'], params['energy_burden']
    return [('fpl_pct', income['fpl_high']), ('fpl_pct', income['fpl_moderate']), ('ami_pct', income['ami_moderate']),
            ('energy_burden', burden['moderate']), ('energy_burden', burden['high'])]


def _stage_households(db, store, county: str, src: CountySources, dist: Distributions, reg: Registry,
                      build_month: int, build: Dict, id_key: bytes) -> Tuple[List[int], int]:
    params = reg.rules['params']
    max_age = params['usage']['max_age_months']
    bounds = _boundaries(params)
    sizes, batch, stats, unmapped = [], [], Counter(), defaultdict(Counter)
    fallbacks, boundary, levels = Counter(), Counter(), [[0] * 4 for _ in reg.dims]
    store.reset_staging(county)
    for meter in iter_electrical(db, county):
        assembled = assemble(meter, src.match(meter), county, build_month, reg)
        hh = finalize(assembled.doc, dist, reg.rules, build_month)
        hh['_id'] = analysis_id(hh['_id'], id_key)
        stats['surrogate_ids'] += is_surrogate(hh['_id'])
        for name, raw in assembled.unmapped_values:
            unmapped[name][str(raw)] += 1
        stats['unlinked'] += identity(meter) is None
        stats['nonres'] += hh.get('nonres') is True
        stats['wrong_county'] += hh['county'] != county
        stats['priced'] += 'annual_cost' in hh
        stats['income_known'] += 'fpl_pct' in hh
        stats['usable_fit'] += bool(usable_fit(hh, params))
        fallbacks.update(assembled.fallbacks)
        boundary.update(f'{field}={value}' for field, value in bounds if hh.get(field) == value)
        for row, level in zip(levels, hh['dims']):
            row[level + 1] += 1
        stats['multi_unit'] += hh.get('multi_unit') is True
        stats['stale'] += hh.get('last_read') is not None and not is_fresh(hh['last_read'], build_month, max_age)
        sizes.append(doc_size(hh))
        batch.append(hh)
        if len(batch) >= _BATCH:
            store.stage(county, batch)
            batch = []
    if batch:
        store.stage(county, batch)
    surrogates = stats.pop('surrogate_ids')
    keys = ('unlinked', 'multi_unit', 'stale', 'nonres', 'priced', 'income_known', 'usable_fit')
    build['stats'] = {**{k: stats[k] for k in keys}, 'duplicates': src.duplicates, 'fallbacks': dict(fallbacks),
                      'boundary': {f'{field}={value}': boundary[f'{field}={value}'] for field, value in bounds},
                      'levels': levels}
    build['wrong_county'] = stats['wrong_county']
    build['unmapped_values'] = {name: [[value, n] for value, n in counts.most_common()]
                                for name, counts in unmapped.items()}
    return sorted(sizes), surrogates


def month_of(moment: datetime) -> int:
    """YYYYMM of a build time."""
    return moment.year * 100 + moment.month


def build_county(db, store, county: str, reg: Registry, now: datetime, id_key: bytes) -> Dict:
    """Build one county and record the attempt. Never raises: failures are recorded with status 'failed'."""
    build_month = month_of(now)
    build = {'county': county, 'built_at': now, 'registry_version': reg.fields_version,
             'rules_version': reg.rules_version, 'status': 'staging'}
    try:
        src = load_county_sources(db, county, reg)
        if 'electrical' not in src.present:
            raise BuildError(f'{county}: no ElectricalDB collection')
        dist, nonres = _distributions(db, county, src, reg, build_month)
        sizes, surrogates = _stage_households(db, store, county, src, dist, reg, build_month, build, id_key)
        build.update(sources_present=sorted(src.present), source_counts=src.counts, doc_count=len(sizes),
                     size_p50=quantile(sizes, 50), size_p99=quantile(sizes, 99),
                     cutpoints=cutpoints(dist, reg.rules['params']), unmapped_fields=src.tracker.unmapped())
        failures = check_gates(len(sizes), src.counts['electrical'], sizes, surrogates, (nonres, build['stats']['nonres']),
                            build.pop('wrong_county'), {'fields': build['unmapped_fields'],
                                                        'values': build['unmapped_values']})
        if failures:
            raise BuildError('; '.join(failures))
        try:
            store.swap(county)
        except Exception as exc:
            raise BuildError(f'swap failed (live county may be partially replaced; re-run the build): {exc}') from exc
        build['status'] = 'ok'
    except Exception as exc:  # recorded, not swallowed: the build doc carries the error and status 'failed'
        logger.exception(f'{county}: build failed')
        build['status'], build['error'] = 'failed', str(exc)[:1000]
        store.discard_staging(county)
    inserted = store.record_build(build)
    if inserted is not None:
        build['_id'] = inserted
    if build['status'] == 'ok':
        try:
            report = county_report(db, county, reg) if isinstance(store, MongoStore) else None
            store.write_coverage(coverage_doc(build, report, countykeys_collections(db, county), src.present,
                                              reg.rules, set(db.list_collection_names())))
        except Exception as exc:  # the build is already live and recorded; surface the gap without aborting a batch
            logger.exception(f'{county}: coverage failed')
            build['coverage_error'] = str(exc)[:1000]
    return build
