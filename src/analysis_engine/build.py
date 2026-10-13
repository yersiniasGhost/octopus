"""Two-pass county build: pass 1 learns the county's distributions, pass 2 assigns levels and stages documents.

Assembly is deterministic, so pass 2 re-assembles from the in-memory parcel indexes instead of holding a
county's households in memory between passes (Franklin: 475k meters).
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List

import bson

from src.analysis_engine.household import assemble
from src.analysis_engine.registry import Registry
from src.analysis_engine.rules import Distributions, cutpoints, finalize, quantile, usable_fit, usage_ok
from src.analysis_engine.sources import CountySources, identity, iter_electrical, load_county_sources
from src.analysis_engine.usage import is_fresh
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)
MAX_P99_BYTES = 1024
_BATCH = 1000


class BuildError(RuntimeError):
    """A county build was refused before its swap; the previous version stays live."""


def doc_size(doc: Dict) -> int:
    return len(bson.encode(doc))


def check_gates(doc_count: int, source_count: int, sizes_sorted: List[int]) -> List[str]:
    """Pre-swap gates (spec §12, P1): one document per meter, p99 size under 1 KB."""
    failures = []
    if doc_count != source_count:
        failures.append(f'doc count {doc_count} != source meter count {source_count}')
    p99 = quantile(sizes_sorted, 99)
    if p99 is not None and p99 >= MAX_P99_BYTES:
        failures.append(f'p99 document size {p99} B is not under {MAX_P99_BYTES} B')
    return failures


def _distributions(db, county: str, src: CountySources, reg: Registry, build_month: int) -> Distributions:
    params, kwh, hl = reg.rules['params'], [], []
    for meter in iter_electrical(db, county):
        src.tracker.observe('electrical', meter)
        hh = assemble(meter, src.match(meter), county, build_month, reg).doc
        if usage_ok(hh, params, build_month):
            kwh.append(hh['annual_kwh'])
        if usable_fit(hh, params):
            hl.append(hh['hl_per_sqft'])
    return Distributions.from_values(kwh, hl)


def _stage_households(db, store, county: str, src: CountySources, dist: Distributions, reg: Registry,
                      build_month: int, build: Dict) -> List[int]:
    max_age = reg.params('usage')['max_age_months']
    sizes, batch, stats, unmapped = [], [], Counter(), defaultdict(Counter)
    store.reset_staging(county)
    for meter in iter_electrical(db, county):
        assembled = assemble(meter, src.match(meter), county, build_month, reg)
        hh = finalize(assembled.doc, dist, reg.rules, build_month)
        for name, raw in assembled.unmapped_values:
            unmapped[name][str(raw)] += 1
        stats['unlinked'] += identity(meter) is None
        stats['multi_unit'] += hh.get('multi_unit') is True
        stats['stale'] += hh.get('last_read') is not None and not is_fresh(hh['last_read'], build_month, max_age)
        sizes.append(doc_size(hh))
        batch.append(hh)
        if len(batch) >= _BATCH:
            store.stage(county, batch)
            batch = []
    if batch:
        store.stage(county, batch)
    build['stats'] = {**{k: stats[k] for k in ('unlinked', 'multi_unit', 'stale')}, 'duplicates': src.duplicates}
    build['unmapped_values'] = {name: [[value, n] for value, n in counts.most_common()]
                                for name, counts in unmapped.items()}
    return sorted(sizes)


def build_county(db, store, county: str, reg: Registry, now: datetime) -> Dict:
    """Build one county and record the attempt. Never raises: failures are recorded with status 'failed'."""
    build_month = now.year * 100 + now.month
    build = {'county': county, 'built_at': now, 'registry_version': reg.fields_version,
             'rules_version': reg.rules_version, 'status': 'staging'}
    try:
        src = load_county_sources(db, county, reg)
        if 'electrical' not in src.present:
            raise BuildError(f'{county}: no ElectricalDB collection')
        dist = _distributions(db, county, src, reg, build_month)
        sizes = _stage_households(db, store, county, src, dist, reg, build_month, build)
        build.update(sources_present=sorted(src.present), source_counts=src.counts, doc_count=len(sizes),
                     size_p50=quantile(sizes, 50), size_p99=quantile(sizes, 99),
                     cutpoints=cutpoints(dist, reg.rules['params']), unmapped_fields=src.tracker.unmapped())
        failures = check_gates(len(sizes), src.counts['electrical'], sizes)
        if failures:
            raise BuildError('; '.join(failures))
        try:
            store.swap(county)
        except Exception as exc:
            raise BuildError(f'swap failed (live county may be partially replaced; re-run the build): {exc}') from exc
        build['status'] = 'ok'
    except Exception as exc:  # recorded, not swallowed: the build doc carries the error and status 'failed'
        logger.exception(f'{county}: build failed')
        build['status'], build['error'] = 'failed', str(exc)
        store.discard_staging(county)
    store.record_build(build)
    return build
