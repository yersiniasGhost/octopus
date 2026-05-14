"""ZIP → county lookup for Ohio addresses.

Authoritative source for `applications.address.county`, replacing the prior
free-text input from form submissions (which produced records like
"San Diego" / "Duval" / "Hamilton" attached to Columbus ZIPs).

Backed by `data/zipcode_to_county_cache.json`, built from existing
demographic collections in MongoDB by scripts/zipcode_to_county_mapper.py.
The cache stores values like 'FranklinCounty'; this module strips the
'County' suffix so callers get the same shape used elsewhere
(`applications.address.county = 'Franklin'`).
"""
import json
import re
from pathlib import Path
from typing import FrozenSet, Optional

_CACHE_PATH = Path(__file__).resolve().parents[2] / 'data' / 'zipcode_to_county_cache.json'
_COUNTY_SUFFIX_RE = re.compile(r'County$')
_zipcode_map: Optional[dict] = None
_multi_county: Optional[dict] = None


def _normalize_zip(zip_code: Optional[str]) -> Optional[str]:
    if not zip_code:
        return None
    zip_str = str(zip_code).strip()
    if '-' in zip_str:
        zip_str = zip_str.split('-', 1)[0]
    if not zip_str:
        return None
    if zip_str.isdigit():
        zip_str = zip_str.zfill(5)
    return zip_str


def _strip_suffix(name: str) -> str:
    return _COUNTY_SUFFIX_RE.sub('', name)


def _load() -> None:
    """Lazy-load both the primary map and the multi-county candidate map."""
    global _zipcode_map, _multi_county
    if _zipcode_map is not None:
        return
    with _CACHE_PATH.open() as f:
        data = json.load(f)
    raw_primary = data.get('zipcode_map', data)
    _zipcode_map = {z: _strip_suffix(name) for z, name in raw_primary.items()}
    raw_multi = data.get('multi_county', {})
    _multi_county = {
        z: frozenset(_strip_suffix(c) for c in counties)
        for z, counties in raw_multi.items()
    }


def lookup_county(zip_code: Optional[str]) -> Optional[str]:
    """Return the primary county for a US ZIP, or None if unmappable.

    For multi-county ZIPs this returns the first county encountered when
    the cache was built. Use `candidate_counties` when you have a
    pre-existing county value and want to validate it.
    """
    zip_str = _normalize_zip(zip_code)
    if zip_str is None:
        return None
    _load()
    return _zipcode_map.get(zip_str)


def candidate_counties(zip_code: Optional[str]) -> FrozenSet[str]:
    """Return the full set of counties a ZIP may belong to.

    For single-county ZIPs this is a one-element set; for multi-county
    ZIPs (about 290 in the Ohio cache) it includes every observed county.
    Returns an empty set for unmappable ZIPs.
    """
    zip_str = _normalize_zip(zip_code)
    if zip_str is None:
        return frozenset()
    _load()
    if zip_str in _multi_county:
        return _multi_county[zip_str]
    primary = _zipcode_map.get(zip_str)
    return frozenset({primary}) if primary else frozenset()


def is_plausible_county(zip_code: Optional[str], county: Optional[str]) -> bool:
    """True iff `county` is a known candidate for the given ZIP.

    Used to decide whether a pre-existing county value should be kept
    (plausible) or overwritten (impossible — e.g. 'San Diego' for ZIP 43302).
    Returns False if either input is empty or the ZIP isn't in the cache.
    """
    if not county:
        return False
    candidates = candidate_counties(zip_code)
    return county in candidates


def resolve_county(zip_code: Optional[str], existing_county: Optional[str]) -> Optional[str]:
    """Pick the best county for an address.

    Rules:
    - If `existing_county` is plausible for `zip_code` → keep it (respects
      user choice on multi-county ZIPs where the cache primary may be wrong).
    - Otherwise → use the cache's primary mapping for this ZIP.
    - If neither produces a value → return None.
    """
    if is_plausible_county(zip_code, existing_county):
        return existing_county
    return lookup_county(zip_code)


def reset_cache() -> None:
    """Drop the in-memory caches (test helper / for cache rebuilds)."""
    global _zipcode_map, _multi_county
    _zipcode_map = None
    _multi_county = None
