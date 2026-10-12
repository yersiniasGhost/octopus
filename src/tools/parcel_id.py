"""Parcel identifier normalization, shared by every tool that joins on parcel_id.

`_norm` was originally private to `scripts/audit_thermal_load_coverage_tool.py`.
It lives here because `scripts/normalize_thermal_parcel_id_types_tool.py` (T-02)
writes the strings the audit then verifies: if the two definitions ever drift,
the audit stops verifying the thing that was written.

This is *not* the normalization in `scripts/enrich_demographics_from_bolt.py`,
which strips dashes and spaces for fuzzy CSV matching. Doing that here would
turn "24-01889-000" into "2401889000" and break the join it is meant to repair.
Normalization here is exactly one thing: render the value as its string form.
"""

from typing import Any, Dict, Optional, Tuple


def normalize_parcel_id(value: Any) -> Optional[str]:
    """Render a parcel identifier as the string form used for joins.

    int and bson.Int64 become their decimal string. Strings keep their leading
    zeros and punctuation, losing only surrounding whitespace. Absence -- None,
    empty, whitespace-only -- stays absent rather than becoming a joinable "".
    """
    return None if value is None else str(value).strip() or None


def parcel_key_of(doc: Dict) -> Optional[str]:
    """The normalized parcel_key of a document, or None when it carries none."""
    return normalize_parcel_id(doc.get('parcel_key'))


def parcel_id_of(doc: Dict) -> Optional[str]:
    """The normalized parcel_id of a document, or None when it carries none."""
    return normalize_parcel_id(doc.get('parcel_id'))


class ParcelIndex:
    """Every spelling a parcel answers to -> one stored value.

    Two tables rather than one chosen key (T-04): parcel_key resolves counties whose sides differ by
    zero-padding, while four counties carry no parcel_key at all. Lookups try parcel_key first, then the
    normalized parcel_id. The first value added under a spelling wins, so callers that must choose among
    duplicates do so before adding.
    """

    def __init__(self):
        self.by_key: Dict[str, Any] = {}
        self.by_id: Dict[str, Any] = {}

    def add(self, doc: Dict, value: Any) -> None:
        key, ident = parcel_key_of(doc), parcel_id_of(doc)
        if key is not None:
            self.by_key.setdefault(key, value)
        if ident is not None:
            self.by_id.setdefault(ident, value)

    def resolve(self, doc: Dict) -> Tuple[Optional[Any], str]:
        key = parcel_key_of(doc)
        if key is not None and key in self.by_key:
            return self.by_key[key], 'parcel_key'
        ident = parcel_id_of(doc)
        if ident is not None and ident in self.by_id:
            return self.by_id[ident], 'parcel_id'
        return None, 'unmatched'
