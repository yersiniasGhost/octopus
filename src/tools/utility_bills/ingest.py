"""
Engine: stream utility pre-enrollment files -> county buckets -> merge into
{County}ElectricalDB. Dry-run by default via the CLI wrapper.

Merge policy: union new (date, kWh) readings into time_series_elec, never
overwriting an existing date key; monthly_averages/minimums/maximums are
recomputed from the merged series; matched docs also gain a missing `utility`.
Existing docs are found by parcel_key or parcel_id (ParcelIndex); an address shared by
several parcels resolves only when exactly one has a doc (resolve.py). A parcel with no
doc first takes the unlinked doc already stored under the record's surrogate key. Re-runs are
idempotent (parcel upserts for matched rows, deterministic surrogate _id upserts
for unmatched rows).
"""
import re
import shutil
import tempfile
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import zipcodes
from pymongo import UpdateOne

from src.tools.address_normalization import normalize_address
from src.tools.parcel_id import ParcelIndex, identity
from .parsers import PARSERS
from .resolve import address_index, merge_target, resolve_address, series_conflict
from .sources import BILLS_DIR, SOURCES

ZIP5_RE = re.compile(r'^\d{5}$')
_zip_county_cache = {}


def county_for_zip(zip5):
    """Zip5 -> Ohio county name (spaces stripped for collection naming), else None."""
    if zip5 in _zip_county_cache:
        return _zip_county_cache[zip5]
    county = None
    for m in zipcodes.matching(zip5) if ZIP5_RE.match(zip5) else []:
        if m.get('state') == 'OH' and m.get('county'):
            county = m['county'].replace(' County', '').replace(' ', '').replace('.', '')
            break
    _zip_county_cache[zip5] = county
    return county


def stream_records(src, limit=None):
    """Extract inner zip member to a temp file, stream-parse it, clean up."""
    parser = PARSERS[src['parser']]
    encoding = 'utf-8-sig' if src['parser'] == 'duke' else 'latin-1'
    tmpdir = Path(tempfile.mkdtemp(prefix='utilbills_'))
    try:
        with zipfile.ZipFile(BILLS_DIR / src['outer']) as outer:
            inner_path = tmpdir / 'inner.zip'
            with outer.open(src['inner_zip']) as fsrc, open(inner_path, 'wb') as fdst:
                shutil.copyfileobj(fsrc, fdst, 1024 * 1024)
        with zipfile.ZipFile(inner_path) as inner:
            member = src['member'] or max(inner.infolist(), key=lambda i: i.file_size).filename
            with inner.open(member) as raw:
                import io
                lines = io.TextIOWrapper(raw, encoding=encoding, errors='replace')
                for n, rec in enumerate(parser(lines, src['opco'])):
                    if limit and n >= limit:
                        break
                    yield rec
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def selected_sources(delivery, utilities=None, exclude=()):
    """A delivery's sources, limited to `utilities` (lowercase) when given and minus any in `exclude`."""
    return [s for s in SOURCES[delivery]
            if (not utilities or s['utility'].lower() in utilities) and s['utility'].lower() not in exclude]


def parse_all(delivery, utilities=None, limit=None, log=print, exclude=()):
    """Parse every selected source in a delivery, bucketing OH records by county."""
    by_county = defaultdict(list)
    parse_stats = {}
    for src in selected_sources(delivery, utilities, exclude):
        label = f"{delivery}/{src['utility']}-{src['opco'] or 'ALL'}"
        t0, n = time.time(), 0
        c = defaultdict(int)
        for rec in stream_records(src, limit):
            n += 1
            if not rec.readings:
                c['no_readings'] += 1
                continue
            if rec.state and rec.state.upper() not in ('OH', ''):
                c['out_of_state'] += 1
                continue
            if not rec.service_address:
                c['no_service_address'] += 1
                continue
            county = county_for_zip(rec.zip5)
            if not county:
                c['unknown_county'] += 1
                continue
            by_county[county].append(rec)
        parse_stats[label] = {'rows': n, **c, 'secs': round(time.time() - t0, 1)}
        log(f"  parsed {label}: {n:,} rows in {parse_stats[label]['secs']}s "
            f"(dropped: {sum(c.values()):,})")
    return by_county, parse_stats


def monthly_stats(ts):
    by_m = defaultdict(list)
    for k, v in ts.items():
        by_m[str(int(k[5:7]))].append(v)
    return {
        'monthly_averages': {m: round(sum(v) / len(v), 1) for m, v in by_m.items()},
        'monthly_minimums': {m: min(v) for m, v in by_m.items()},
        'monthly_maximums': {m: max(v) for m, v in by_m.items()},
    }


def _merge_readings(slot_dates, readings):
    conflicts = 0
    for d, kwh in readings:
        key = f"{d} 00:00:00"
        if key in slot_dates and slot_dates[key] != kwh:
            conflicts += 1
            slot_dates[key] = max(slot_dates[key], kwh)
        else:
            slot_dates[key] = kwh
    return conflicts


def _merge_set(target, dates, rec, tag, st):
    """The $set that folds new readings (and a missing utility) into a doc, or None when nothing changes."""
    ts = target.get('time_series_elec') or {}
    new = {k: v for k, v in dates.items() if k not in ts}
    out = {}
    if new:
        merged = {**ts, **new}
        out.update({'time_series_elec': merged, **monthly_stats(merged), 'last_utility_ingest': tag})
        st['docs_updated'] += 1
        st['readings_added_existing'] += len(new)
    if not target.get('utility'):
        out['utility'] = rec.utility
        st['utility_set'] += 1
    return out or None


def group_by_identity(docs):
    """Docs split into linked groups keyed by identity and surrogates (no identity) keyed by _id."""
    linked, surrogates = defaultdict(list), {}
    for doc in docs:
        ident = identity(doc)
        if ident is None:
            surrogates[doc['_id']] = doc
        else:
            linked[ident].append(doc)
    return linked, surrogates


def index_groups(linked):
    """A ParcelIndex answering every spelling of a parcel with its group of docs."""
    index = ParcelIndex()
    for group in linked.values():
        index.add(group[0], group)
    return index


def _load_existing(db, coll_name):
    """ElectricalDB docs as a ParcelIndex of linked docs (lists per parcel) and every doc by _id."""
    docs = list(db[coll_name].find({}, {'parcel_id': 1, 'parcel_key': 1, 'time_series_elec': 1,
                                        'utility': 1, 'source_delivery': 1, 'service_address': 1}))
    return index_groups(group_by_identity(docs)[0]), {d['_id']: d for d in docs}


def _same_meter(doc, slot):
    """True when a doc found by surrogate _id is this slot's meter: unlinked and at one of the slot's addresses."""
    return identity(doc) is None and normalize_address(doc.get('service_address') or '') in slot['naddrs']


def _target_for(docs, tag, dates):
    """The doc a parcel's readings merge into: its merge_target, else the single doc already holding every date,
    else the single doc this delivery made. None means create (no docs) or skip (docs exist, none identifiable)."""
    if target := merge_target(docs):
        return target
    for pick in (lambda d: set(dates) <= set(d.get('time_series_elec') or {}), lambda d: d.get('source_delivery') == tag):
        found = [d for d in docs if pick(d)]
        if len(found) == 1:
            return found[0]
    return None


def process_county(db, county, records, tag, dry_run, existing_colls, log=print):
    """Match records to parcels, diff against ElectricalDB, apply/count writes."""
    coll_name = f"{county}ElectricalDB"
    res_name = f"{county}CountyResidential"
    st = defaultdict(int)
    st_meta = {'county': county, 'records': len(records),
               'has_residential': res_name in existing_colls,
               'new_collection': coll_name not in existing_colls}

    # 1. collapse records by normalized service address (multi-account merge)
    by_addr = {}
    for rec in records:
        naddr = normalize_address(rec.service_address)
        slot = by_addr.setdefault(naddr, {'dates': {}, 'rec': rec, 'naddr': naddr, 'keys': set(),
                                       'naddrs': {naddr}})
        slot['keys'].add(rec.surrogate_key())
        st['reading_conflicts'] += _merge_readings(slot['dates'], rec.readings)
    st_meta['unique_addresses'] = len(by_addr)

    # 2. address -> residential parcels from the county Residential collection
    addr_parcels = {}
    if st_meta['has_residential']:
        addr_parcels = address_index(db[res_name].find({}, {'parcel_id': 1, 'parcel_key': 1, 'address': 1,
                                                             'parcel_zip': 1}))

    # 3. existing docs: linked ones by parcel spelling, surrogates by _id
    existing, by_id = ParcelIndex(), {}
    if not st_meta['new_collection']:
        existing, by_id = _load_existing(db, coll_name)

    # 4. key every address: residential parcel when resolved, else surrogate _id
    keyed = {}

    def put(key, slot):
        prev = keyed.setdefault(key, slot)
        if prev is not slot and key[0] == 's' and prev['naddr'] != slot['naddr']:
            st['surrogate_collision'] += 1  # one surrogate key, two service addresses: not the same meter
        elif prev is not slot:
            prev['dates'].update({k: v for k, v in slot['dates'].items() if k not in prev['dates']})
            prev['keys'], prev['naddrs'] = prev['keys'] | slot['keys'], prev['naddrs'] | slot['naddrs']

    for naddr, slot in by_addr.items():
        parcels = addr_parcels.get(naddr, [])
        parcel, how = resolve_address(parcels, slot['rec'].zip5, existing) if parcels else (None, 'none')
        if how == 'resolved':
            st['ambiguous_resolved'] += 1
            target = merge_target(existing.resolve(parcel)[0] or [])
            if series_conflict(slot['dates'], target.get('time_series_elec') or {}):
                st['ambiguous_conflict'] += 1
                parcel = None
        elif parcels and parcel is None:
            st['ambiguous_address'] += 1
        if parcel is not None:
            st['matched_parcels'] += 1
            put(('p', identity(parcel)), {**slot, 'parcel': parcel})
        else:
            put(('s', slot['rec'].surrogate_key()), slot)

    ops, first_date, last_date, merges = [], None, None, {}
    for key, slot in keyed.items():
        dates, rec, kind = slot['dates'], slot['rec'], key[0]
        lo, hi = min(dates), max(dates)
        first_date = min(first_date, lo) if first_date else lo
        last_date = max(last_date, hi) if last_date else hi
        parcel = slot.get('parcel')
        docs = (existing.resolve(parcel)[0] or []) if kind == 'p' else []
        target = _target_for(docs, tag, dates) if kind == 'p' else by_id.get(key[1])
        if kind == 's' and target and not _same_meter(target, slot):
            st['surrogate_collision'] += 1  # the _id already holds another meter: leave these readings out
            continue
        if kind == 'p' and not target and docs:
            st['skipped_multi_preingest'] += 1  # readings stay in whichever doc already has them
            continue
        if kind == 'p' and not docs:  # a parcel with no doc: an unlinked doc the repair left under these keys (§15.7)
            held = {k for k in slot['keys'] if k in by_id and _same_meter(by_id[k], slot)}
            if len(held) > 1:
                st['skipped_promote_multi'] += 1
                continue
            target = by_id[held.pop()] if held else None
        if target:
            prev = merges.setdefault(target['_id'], {'target': target, 'dates': {}, 'rec': rec})
            prev['dates'].update({k: v for k, v in dates.items() if k not in prev['dates']})
            continue
        doc = {'parcel_id': parcel['parcel_id'] if kind == 'p' else None,
               'time_series_elec': dates, **monthly_stats(dates),
               'county': county, 'utility': rec.utility,
               'source_delivery': tag, 'last_utility_ingest': tag}
        if kind == 'p':
            st['docs_created_parcel'] += 1
            if parcel.get('parcel_key') is not None:
                doc['parcel_key'] = parcel['parcel_key']
            flt = {'parcel_id': doc['parcel_id'], 'source_delivery': tag}
        else:
            st['docs_created_unmatched'] += 1
            doc.update({'_id': key[1], 'account_id': rec.account_id or None,
                        'service_address': rec.service_address,
                        'service_city': rec.city, 'service_zip5': rec.zip5})
            flt = {'_id': key[1]}
        st['readings_added_new'] += len(dates)
        if not dry_run:
            ops.append(UpdateOne(flt, {'$set': doc}, upsert=True))

    for m in merges.values():  # one write per target doc, however many addresses or spellings fed it
        changes = _merge_set(m['target'], m['dates'], m['rec'], tag, st)
        if not changes:
            st['unchanged'] += 1
        elif not dry_run:
            ops.append(UpdateOne({'_id': m['target']['_id']}, {'$set': changes}))

    if ops:
        for i in range(0, len(ops), 1000):
            db[coll_name].bulk_write(ops[i:i + 1000], ordered=False)
    st_meta.update(st)
    st_meta['date_range'] = f"{(first_date or '')[:10]} .. {(last_date or '')[:10]}"
    return st_meta
