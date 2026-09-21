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

from typing import Any, Optional


def normalize_parcel_id(value: Any) -> Optional[str]:
    """Render a parcel identifier as the string form used for joins.

    int and bson.Int64 become their decimal string. Strings keep their leading
    zeros and punctuation, losing only surrounding whitespace. Absence -- None,
    empty, whitespace-only -- stays absent rather than becoming a joinable "".
    """
    return None if value is None else str(value).strip() or None
