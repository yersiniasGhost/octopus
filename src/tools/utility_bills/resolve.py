"""Which parcel an ingested address belongs to, and which ElectricalDB document absorbs its readings.

Shared by ingest.py (new deliveries) and repair.py (folding the 2026-08-19 duplicates) so both apply one rule
(spec 20261008_1713 §15.3).
"""
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from src.tools.address_normalization import normalize_address
from src.tools.parcel_id import ParcelIndex


def merge_target(docs: List[Dict]) -> Optional[Dict]:
    """The one document to merge into: the only doc, else the only pre-ingest doc (no source_delivery)."""
    if len(docs) == 1:
        return docs[0]
    pre = [d for d in docs if not d.get('source_delivery')]
    return pre[0] if len(pre) == 1 else None


def series_conflict(a: Dict, b: Dict) -> bool:
    """True when two readings series disagree on any date they share."""
    return any(a[k] != b[k] for k in a.keys() & b.keys())


def address_index(res_docs: Iterable[Dict]) -> Dict[str, List[Dict]]:
    """Residential docs grouped by normalized address; docs without an address are skipped."""
    index = defaultdict(list)
    for doc in res_docs:
        naddr = normalize_address(doc.get('address') or '')
        if naddr:
            index[naddr].append(doc)
    return index


def resolve_address(parcels: List[Dict], zip5: str, existing: ParcelIndex) -> Tuple[Optional[Dict], str]:
    """The residential parcel an address belongs to, with how it was decided (unique/resolved/none/multi)."""
    narrowed = [p for p in parcels if not p.get('parcel_zip') or str(p['parcel_zip'])[:5] == zip5] or parcels
    if len(narrowed) == 1:
        return narrowed[0], 'unique'
    with_doc = [p for p in narrowed if merge_target(existing.resolve(p)[0] or [])]
    if len(with_doc) == 1:
        return with_doc[0], 'resolved'
    return None, 'none' if not with_doc else 'multi'
