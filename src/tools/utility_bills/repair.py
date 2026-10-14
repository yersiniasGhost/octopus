"""Database-only repair: fold the ingest's duplicate ElectricalDB docs and link its orphan surrogates.

Type (b): a parcel with several docs (same parcel_key/parcel_id spelling) folds its ingest-created docs into the
single pre-ingest doc. Type (c): an unlinked doc with a service address folds into the one residential parcel
resolve_address picks. Type (d): two unlinked docs from different deliveries at one (utility, address, zip) fold the
older delivery's doc into the newer one. Type (e): an unlinked doc that alone resolves to a residential parcel with
no doc is linked in place. Series that disagree on a shared date are left alone (spec 20261008_1713 §15.3, §15.7).
Skip counters count only documents that end up neither deleted nor promoted (a (d) survivor that stays unlinked
still counts), each once, under the reason from the last pass that skipped it; (b)'s skipped_multi_preingest counts
parcels. A fold survivor records every id it absorbed (and theirs) in `merged_ids`, so a re-ingest finds it by them.
"""
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from pymongo import UpdateOne

from .ingest import group_by_identity, index_groups, monthly_stats
from src.tools.address_normalization import normalize_address
from src.tools.parcel_id import ParcelIndex, identity
from .resolve import address_index, merge_target, resolve_address, series_conflict

COUNTERS = ['parcel_folds', 'address_folds', 'delivery_folds', 'promoted', 'utility_from_fold', 'deleted',
            'skipped_multi_preingest', 'skipped_conflict', 'skipped_multi_candidate', 'skipped_none',
            'skipped_cross_delivery', 'skipped_promote_multi']
FIELDS = {'parcel_id': 1, 'parcel_key': 1, 'time_series_elec': 1, 'utility': 1, 'source_delivery': 1,
          'last_utility_ingest': 1, 'service_address': 1, 'service_zip5': 1, 'merged_ids': 1}


class _Folds:
    """Writes planned in memory: per target doc, the accumulated series and fields, the docs absorbed (deleted) and
    the ids it will answer to (its own merged_ids plus each absorbed doc's _id and merged_ids)."""

    def __init__(self, st):
        self.plans, self.st, self.skips, self.promoted = {}, st, {}, set()

    def skip(self, doc: Dict, reason: str):
        """Note why doc was left alone; the last reason wins, counted only if doc is neither deleted nor promoted."""
        self.skips[doc['_id']] = reason

    def _plan(self, target: Dict) -> Dict:
        return self.plans.setdefault(target['_id'], {'ts': dict(target.get('time_series_elec') or {}), 'set': {},
                                                     'target': target, 'ids': [],
                                                     'merged': set(target.get('merged_ids') or [])})

    def add(self, target: Dict, doc: Dict, counter: str):
        plan = self._plan(target)
        ts = doc.get('time_series_elec') or {}
        if series_conflict(ts, plan['ts']):
            self.skip(doc, 'skipped_conflict')
            return
        plan['ts'].update({k: v for k, v in ts.items() if k not in plan['ts']})
        for field in ('utility', 'last_utility_ingest'):
            if doc.get(field) and not (target.get(field) or plan['set'].get(field)):
                plan['set'][field] = doc[field]
                self.st['utility_from_fold'] += field == 'utility'
        plan['ids'].append(doc['_id'])
        plan['merged'] |= {doc['_id'], *(doc.get('merged_ids') or [])}
        self.st[counter] += 1

    def promote(self, doc: Dict, parcel: Dict):
        """Link doc in place to parcel: one write with any fold into it, never a delete."""
        self._plan(doc)['set'].update({f: parcel[f] for f in ('parcel_id', 'parcel_key') if parcel.get(f) is not None})
        self.promoted.add(doc['_id'])
        self.st['promoted'] += 1

    def ops(self) -> List[UpdateOne]:
        return [UpdateOne({'_id': tid}, {'$set': {**({'time_series_elec': p['ts'], **monthly_stats(p['ts']),
                                                      'merged_ids': sorted(p['merged'] - {tid}, key=str)}
                                                     if p['ids'] else {}), **p['set']}})
                for tid, p in self.plans.items() if p['ids'] or p['set']]

    def doc_ids(self) -> List:
        return [i for p in self.plans.values() for i in p['ids']]

    def count_skips(self):
        touched = set(self.doc_ids()) | self.promoted
        for doc_id, reason in self.skips.items():
            self.st[reason] += doc_id not in touched


def delivery_date(tag: str) -> Optional[datetime]:
    """The month a delivery tag names ('jan2026' -> 2026-01-01), or None when the tag is not month+year."""
    try:
        return datetime.strptime(tag, '%b%Y')
    except (TypeError, ValueError):
        return None


def _fold_deliveries(docs: List[Dict], folds: _Folds):
    """Type (d): a (utility, address, zip) group of exactly two docs from two deliveries folds older into newer."""
    groups = defaultdict(list)
    for doc in docs:
        naddr = normalize_address(doc.get('service_address') or '')
        if naddr:
            groups[(doc.get('utility'), naddr, str(doc.get('service_zip5') or ''))].append(doc)
    for group in (g for g in groups.values() if len(g) > 1):
        when = [delivery_date(d['source_delivery']) for d in group]
        if len(group) != 2 or None in when or when[0] == when[1]:
            for doc in group:
                folds.skip(doc, 'skipped_cross_delivery')
            continue
        older, newer = group if when[0] < when[1] else group[::-1]
        folds.add(newer, older, 'delivery_folds')


class _Promoted:
    """Existing docs plus the planned promotions, as resolve_address sees them on a rerun."""

    def __init__(self, existing: ParcelIndex, picks: List):
        self.existing, self.planned = existing, ParcelIndex()
        for doc, parcel in picks:
            self.planned.add(parcel, [doc])

    def resolve(self, parcel: Dict):
        hit = self.planned.resolve(parcel)
        return hit if hit[0] else self.existing.resolve(parcel)


def _promote(orphans: List, nones: List, existing: ParcelIndex, folds: _Folds):
    """Type (e): link a no-doc parcel's only orphan, unless a 'none' address would then resolve to that parcel."""
    index, groups = ParcelIndex(), []  # one group per parcel, whichever spelling each orphan's address row used
    for doc, parcel in orphans:
        i = index.resolve(parcel)[0]
        if i is None:
            i = len(groups)
            groups.append([])
        index.add(parcel, i)
        groups[i].append((doc, parcel))
    group_of = {doc['_id']: i for i, group in enumerate(groups) for doc, _ in group}
    blocked = {i for i, group in enumerate(groups) if len(group) > 1}
    while True:  # blocking one parcel can turn a 'multi' rerun outcome into 'resolved' for another
        view = _Promoted(existing, [g[0] for i, g in enumerate(groups) if i not in blocked])
        rerun = (resolve_address(parcels, zip5, view) for parcels, zip5 in nones)
        hits = {group_of[d['_id']] for parcel, how in rerun if how == 'resolved'
                for d in view.planned.resolve(parcel)[0] or []}
        if hits <= blocked:
            break
        blocked |= hits
    for i, group in enumerate(groups):
        if i in blocked:
            for doc, _ in group:
                folds.skip(doc, 'skipped_promote_multi')
        else:
            folds.promote(*group[0])


def repair_county(db, county: str, dry_run: bool) -> Dict[str, int]:
    """Plan every fold and promotion for one county, then (unless dry_run) apply the updates and delete folded docs."""
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

    ingested = [d for d in surrogates.values() if d.get('source_delivery')]
    orphans, nones = [], []  # (doc, parcel) unique to a no-doc parcel; (candidates, zip5) of 'none' addresses
    if res_name in db.list_collection_names():
        addr_parcels = address_index(db[res_name].find({}, {'parcel_id': 1, 'parcel_key': 1, 'address': 1,
                                                             'parcel_zip': 1}))
        for doc in ingested:
            parcels, zip5 = addr_parcels.get(normalize_address(doc.get('service_address') or '')), \
                str(doc.get('service_zip5') or '')
            if not parcels:
                continue
            parcel, how = resolve_address(parcels, zip5, existing)
            group = (existing.resolve(parcel)[0] or []) if parcel else []
            target = merge_target(group)
            if target is not None:
                folds.add(target, doc, 'address_folds')
            elif group:
                folds.skip(doc, 'skipped_multi_preingest')
            elif how == 'multi':
                folds.skip(doc, 'skipped_multi_candidate')
            elif how == 'none':
                folds.skip(doc, 'skipped_none')
                nones.append((parcels, zip5))
            elif identity(parcel) is not None:
                orphans.append((doc, parcel))

    gone = set(folds.doc_ids())
    _fold_deliveries([d for d in ingested if d['_id'] not in gone], folds)
    gone = set(folds.doc_ids())
    _promote([o for o in orphans if o[0]['_id'] not in gone], nones, existing, folds)

    folds.count_skips()
    ops, ids = folds.ops(), folds.doc_ids()
    st['deleted'] = len(ids)
    if not dry_run:
        matched = sum(db[coll_name].bulk_write(ops[i:i + 1000], ordered=False).matched_count
                      for i in range(0, len(ops), 1000))
        if matched < len(ops):  # a target vanished since planning: its folded docs are the only copy of the readings
            raise RuntimeError(f"{county}: {len(ops) - matched} of {len(ops)} updates not matched; nothing deleted")
        for i in range(0, len(ids), 10000):
            db[coll_name].delete_many({'_id': {'$in': ids[i:i + 10000]}})
    return dict(st)
