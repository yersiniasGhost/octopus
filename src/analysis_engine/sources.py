"""Read one county's source collections into in-memory parcel indexes for household assembly.

Parcel-side documents are projected to the paths the registry maps before they are kept, so a county's
indexes stay small. Every key seen in every source document is tracked, so fields the registry neither maps
nor ignores surface in analysis_builds.unmapped_fields instead of disappearing (spec §10).
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from src.analysis_engine.household import PARCEL_ROLES, ParcelMatch
from src.analysis_engine.normalize import PRESENT, read_value
from src.analysis_engine.registry import FieldSpec, Registry
from src.tools.county_weather import normalize_county
from src.tools.parcel_id import ParcelIndex, identity, parcel_id_of, parcel_key_of

# 'multitenant' is reported as present but not read: P1 derives multi_unit from meters per parcel only.
COLLECTIONS = {'electrical': '{}ElectricalDB', 'residential': '{}CountyResidential',
               'demographic': '{}CountyDemographic', 'thermal': '{}ThermalLoads', 'multitenant': '{}MultiTenant'}
ID_KEYS = ('_id', 'parcel_id', 'parcel_key')


def collection_name(role: str, county: str) -> str:
    return COLLECTIONS[role].format(county)


def all_counties(db) -> List[str]:
    suffix = collection_name('electrical', '')
    return sorted(n[:-len(suffix)] for n in db.list_collection_names() if n.endswith(suffix))


def sources_present(collection_names: Iterable[str], county: str) -> Dict[str, str]:
    names = set(collection_names)
    return {role: collection_name(role, county) for role in COLLECTIONS if collection_name(role, county) in names}


def countykeys_collections(db, county: str) -> Dict[str, str]:
    """Collection names the county's CountyKeys document lists, by role; {} when it has none."""
    if 'CountyKeys' not in db.list_collection_names():
        return {}
    by_county = {normalize_county(d['county']): d for d in db['CountyKeys'].find({}, {'_id': 0})}
    keys = by_county.get(normalize_county(county), {})
    return {role: keys[field] for role, field in (('residential', 'residential_data'),
                                                  ('demographic', 'demographic_data')) if keys.get(field)}


class FieldTracker:
    """Source keys seen per role, minus those the registry maps, reads directly, or ignores."""

    def __init__(self, reg: Registry):
        self._known = reg.known_keys
        self._seen = defaultdict(set)

    def observe(self, role: str, doc: Dict) -> None:
        self._seen[role].update(doc.keys())

    def unmapped(self) -> Dict[str, List[str]]:
        found = {role: sorted(seen - self._known[role]) for role, seen in self._seen.items()}
        return {role: names for role, names in found.items() if names}


def choose_most_complete(docs: List[Dict], specs: List[FieldSpec], tokens) -> Dict:
    """The doc with the most usable mapped fields; ties go to the larger _id, so cursor order never decides."""
    def score(doc: Dict):
        return sum(read_value(doc, f.source, tokens)[0] == PRESENT for f in specs), str(doc.get('_id'))
    return max(docs, key=score)


def index_role(docs: Iterable[Dict], specs: List[FieldSpec], tokens) -> Tuple[ParcelIndex, int]:
    """Group by parcel_key and by parcel_id, keep the most complete doc per group; count parcels with duplicates."""
    by_key, by_id, per_parcel = defaultdict(list), defaultdict(list), Counter()
    for doc in docs:
        key, ident = parcel_key_of(doc), parcel_id_of(doc)
        if key is not None:
            by_key[key].append(doc)
        if ident is not None:
            by_id[ident].append(doc)
        if identity(doc) is not None:
            per_parcel[identity(doc)] += 1
    index = ParcelIndex()
    index.by_key = {k: choose_most_complete(group, specs, tokens) for k, group in by_key.items()}
    index.by_id = {k: choose_most_complete(group, specs, tokens) for k, group in by_id.items()}
    return index, sum(1 for n in per_parcel.values() if n > 1)


@dataclass
class CountySources:
    present: Dict[str, str]
    counts: Dict[str, int]
    indexes: Dict[str, ParcelIndex]
    meters: Counter
    duplicates: Dict[str, int]
    tracker: FieldTracker

    def match(self, elec: Dict) -> ParcelMatch:
        ident = identity(elec)
        if ident is None:
            return ParcelMatch()
        found = {role: index.resolve(elec)[0] for role, index in self.indexes.items()}
        return ParcelMatch(linked=True, meters_on_parcel=self.meters[ident], **found)


def iter_electrical(db, county: str) -> Iterator[Dict]:
    return iter(db[collection_name('electrical', county)].find({}))


def _project(doc: Dict, paths: List[str]) -> Dict:
    return {k: doc[k] for k in (*ID_KEYS, *paths) if k in doc}


def load_county_sources(db, county: str, reg: Registry) -> CountySources:
    """Index every parcel-side source the county has, count meters per parcel, and track source keys."""
    present = sources_present(db.list_collection_names(), county)
    tracker, counts, indexes, duplicates = FieldTracker(reg), {}, {}, {}
    for role in PARCEL_ROLES:
        if role not in present:
            continue
        specs = reg.fields_for(role)
        paths = [p for spec in specs for p in spec.source['paths']]
        docs = []
        for doc in db[present[role]].find({}):
            tracker.observe(role, doc)
            docs.append(_project(doc, paths))
        counts[role] = len(docs)
        indexes[role], duplicates[role] = index_role(docs, specs, reg.missing_tokens)
    meters = Counter()
    if 'electrical' in present:
        counts['electrical'] = 0
        for doc in db[present['electrical']].find({}, {'parcel_id': 1, 'parcel_key': 1}):
            counts['electrical'] += 1
            if identity(doc) is not None:
                meters[identity(doc)] += 1
    return CountySources(present, counts, indexes, meters, duplicates, tracker)
