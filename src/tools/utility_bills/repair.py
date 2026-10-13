"""Database-only repair: fold the 2026-08-19 ingest's duplicate ElectricalDB docs into their pre-ingest doc.

Type (b): a parcel with several docs (same parcel_key/parcel_id spelling) folds its ingest-created docs into the
single pre-ingest doc. Type (c): an unlinked doc with a service address folds into the one residential parcel
resolve_address picks. Series that disagree on a shared date are left alone (spec 20261008_1713 §15.3).
"""
from collections import defaultdict
from typing import Dict, List

from pymongo import UpdateOne

from .ingest import group_by_identity, index_groups, monthly_stats
from src.tools.address_normalization import normalize_address
from .resolve import address_index, merge_target, resolve_address, series_conflict

COUNTERS = ['parcel_folds', 'address_folds', 'utility_from_fold', 'deleted', 'skipped_multi_preingest',
            'skipped_conflict', 'skipped_multi_candidate']
FIELDS = {'parcel_id': 1, 'parcel_key': 1, 'time_series_elec': 1, 'utility': 1, 'source_delivery': 1,
          'last_utility_ingest': 1, 'service_address': 1, 'service_zip5': 1}


class _Folds:
    """Folds planned in memory: per target doc, the accumulated series and fields, and the docs absorbed."""

    def __init__(self, st):
        self.plans, self.st = {}, st

    def add(self, target: Dict, doc: Dict, counter: str):
        plan = self.plans.setdefault(target['_id'], {'ts': dict(target.get('time_series_elec') or {}), 'set': {},
                                                     'target': target, 'ids': []})
        ts = doc.get('time_series_elec') or {}
        if series_conflict(ts, plan['ts']):
            self.st['skipped_conflict'] += 1
            return
        plan['ts'].update({k: v for k, v in ts.items() if k not in plan['ts']})
        for field in ('utility', 'last_utility_ingest'):
            if doc.get(field) and not (target.get(field) or plan['set'].get(field)):
                plan['set'][field] = doc[field]
                self.st['utility_from_fold'] += field == 'utility'
        plan['ids'].append(doc['_id'])
        self.st[counter] += 1

    def ops(self) -> List[UpdateOne]:
        return [UpdateOne({'_id': tid}, {'$set': {'time_series_elec': p['ts'], **monthly_stats(p['ts']), **p['set']}})
                for tid, p in self.plans.items() if p['ids']]

    def doc_ids(self) -> List:
        return [i for p in self.plans.values() for i in p['ids']]


def repair_county(db, county: str, dry_run: bool) -> Dict[str, int]:
    """Plan every fold for one county, then (unless dry_run) apply the updates and delete the folded docs."""
    coll_name, res_name = f"{county}ElectricalDB", f"{county}CountyResidential"
    st = defaultdict(int, {k: 0 for k in COUNTERS})
    linked, surrogates = group_by_identity(db[coll_name].find({}, FIELDS))
    existing, folds = index_groups(linked), _Folds(st)

    for group in linked.values():
        ingested = [d for d in group if d.get('source_delivery')]
        if not ingested or len(ingested) == len(group):
            continue
        target = merge_target(group)
        if target is None:
            st['skipped_multi_preingest'] += 1
            continue
        for doc in ingested:
            folds.add(target, doc, 'parcel_folds')

    if res_name in db.list_collection_names():
        addr_parcels = address_index(db[res_name].find({}, {'parcel_id': 1, 'parcel_key': 1, 'address': 1,
                                                             'parcel_zip': 1}))
        for doc in surrogates.values():
            parcels = addr_parcels.get(normalize_address(doc.get('service_address') or ''))
            if not parcels:
                continue
            parcel, how = resolve_address(parcels, str(doc.get('service_zip5') or ''), existing)
            target = merge_target(existing.resolve(parcel)[0] or []) if parcel else None
            if target is not None:
                folds.add(target, doc, 'address_folds')
            elif how == 'multi':
                st['skipped_multi_candidate'] += 1

    ops, ids = folds.ops(), folds.doc_ids()
    st['deleted'] = len(ids)
    if not dry_run:
        for i in range(0, len(ops), 1000):
            db[coll_name].bulk_write(ops[i:i + 1000], ordered=False)
        for i in range(0, len(ids), 10000):
            db[coll_name].delete_many({'_id': {'$in': ids[i:i + 10000]}})
    return dict(st)
