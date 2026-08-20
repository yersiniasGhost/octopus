"""
Engine: stream utility pre-enrollment files -> county buckets -> merge into
{County}ElectricalDB. Dry-run by default via the CLI wrapper.

Merge policy: union new (date, kWh) readings into time_series_elec, never
overwriting an existing date key; monthly_averages/minimums/maximums are
recomputed from the merged series. Re-runs are idempotent (parcel_id upserts
for matched rows, deterministic surrogate _id upserts for unmatched rows).
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
from .parsers import PARSERS
from .sources import BILLS_DIR, SOURCES

AMBIGUOUS = object()
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


def parse_all(delivery, utilities=None, limit=None, log=print):
    """Parse every source in a delivery, bucketing OH records by county."""
    by_county = defaultdict(list)
    parse_stats = {}
    for src in SOURCES[delivery]:
        if utilities and src['utility'].lower() not in utilities:
            continue
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
        slot = by_addr.setdefault(naddr, {'dates': {}, 'rec': rec})
        st['reading_conflicts'] += _merge_readings(slot['dates'], rec.readings)
    st_meta['unique_addresses'] = len(by_addr)

    # 2. address -> parcel index from the county Residential collection
    addr_to_parcel = {}
    if st_meta['has_residential']:
        for doc in db[res_name].find({}, {'parcel_id': 1, 'address': 1}):
            na = normalize_address(doc.get('address') or '')
            if not na:
                continue
            if na in addr_to_parcel and addr_to_parcel[na] != doc['parcel_id']:
                addr_to_parcel[na] = AMBIGUOUS
            else:
                addr_to_parcel[na] = doc['parcel_id']

    # 3. key every address: parcel_id when uniquely matched, else surrogate _id
    keyed = {}
    for naddr, slot in by_addr.items():
        pid = addr_to_parcel.get(naddr)
        if pid is AMBIGUOUS:
            st['ambiguous_address'] += 1
            pid = None
        if pid is not None:
            st['matched_parcels'] += 1
            prev = keyed.get(('p', pid))
            if prev:
                prev['dates'].update({k: v for k, v in slot['dates'].items() if k not in prev['dates']})
            else:
                keyed[('p', pid)] = slot
        else:
            keyed[('s', slot['rec'].surrogate_key())] = slot

    # 4. diff against existing docs (keyed by parcel_id, else by _id for surrogates)
    existing = {}
    if not st_meta['new_collection']:
        for doc in db[coll_name].find({}, {'parcel_id': 1, 'time_series_elec': 1}):
            pid = doc.get('parcel_id')
            key = ('p', pid) if pid else ('s', doc['_id'])
            existing[key] = (doc['_id'], doc.get('time_series_elec') or {})

    ops, first_date, last_date = [], None, None
    for key, slot in keyed.items():
        dates = slot['dates']
        lo, hi = min(dates), max(dates)
        first_date = min(first_date, lo) if first_date else lo
        last_date = max(last_date, hi) if last_date else hi
        if key in existing:
            _id, ts = existing[key]
            new = {k: v for k, v in dates.items() if k not in ts}
            if not new:
                st['unchanged'] += 1
                continue
            merged = {**ts, **new}
            st['docs_updated'] += 1
            st['readings_added_existing'] += len(new)
            if not dry_run:
                ops.append(UpdateOne({'_id': _id}, {'$set': {
                    'time_series_elec': merged, **monthly_stats(merged),
                    'last_utility_ingest': tag}}))
        else:
            kind, ident = key
            rec = slot['rec']
            doc = {'parcel_id': ident if kind == 'p' else None,
                   'time_series_elec': dates, **monthly_stats(dates),
                   'county': county, 'utility': rec.utility,
                   'source_delivery': tag, 'last_utility_ingest': tag}
            if kind == 'p':
                st['docs_created_parcel'] += 1
                flt = {'parcel_id': ident}
            else:
                st['docs_created_unmatched'] += 1
                doc.update({'_id': ident, 'account_id': rec.account_id or None,
                            'service_address': rec.service_address,
                            'service_city': rec.city, 'service_zip5': rec.zip5})
                flt = {'_id': ident}
            st['readings_added_new'] += len(dates)
            if not dry_run:
                ops.append(UpdateOne(flt, {'$set': doc}, upsert=True))

    if ops:
        for i in range(0, len(ops), 1000):
            db[coll_name].bulk_write(ops[i:i + 1000], ordered=False)
    st_meta.update(st)
    st_meta['date_range'] = f"{(first_date or '')[:10]} .. {(last_date or '')[:10]}"
    return st_meta
