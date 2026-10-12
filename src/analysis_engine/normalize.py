"""Source value → canonical value, with every encoding of "missing" reading as blank.

Measured encodings (spec §3): absent field, None, -1, '', float NaN, the strings 'nan' / 'Unknown', and
field-specific sentinels. Per-field sentinels come from fields.json; the string tokens are global.
"""

import math
import re
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

PRESENT, BLANK, ABSENT, UNMAPPED = 'present', 'blank', 'absent', 'unmapped'

_MONEY_STRIP = re.compile(r'[$,\s]')
_LEADING_INT = re.compile(r'^(\d+)')


def is_blank(value: Any, sentinels: Iterable = (), tokens: Iterable[str] = ()) -> bool:
    """True when a raw source value means "no data"."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == '' or stripped in tokens
    return isinstance(value, (int, float)) and value in tuple(sentinels)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _positive(value: Any) -> Optional[float]:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _count(value: Any) -> Optional[int]:
    number = _number(value)
    count = int(round(number)) if number is not None else 0
    return count if count >= 1 else None


def _year(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None and 1700 <= number <= 2100 else None


def _money(value: Any) -> Optional[float]:
    return _positive(_MONEY_STRIP.sub('', value) if isinstance(value, str) else value)


def _years_range(value: Any) -> Optional[int]:
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith('less than'):
            return 0
        match = _LEADING_INT.match(text)
        return int(match.group(1)) if match else None
    number = _number(value)
    return int(number) if number is not None and number >= 0 else None


TRANSFORMS: Dict[str, Callable[[Any], Any]] = {
    'number': _number, 'positive': _positive, 'count': _count,
    'year': _year, 'money': _money, 'years_range': _years_range,
}


def read_value(doc: Dict, source: Dict, tokens: Iterable[str]) -> Tuple[str, Any]:
    """Resolve one canonical field from one source document.

    Paths are tried in priority order and the first usable value wins. A path that exists but holds a blank
    or out-of-range value makes the field BLANK unless a later path supplies a value; no path present at all is
    ABSENT. A value_map miss is UNMAPPED (a drift signal the build reports); a value mapped to None is a known
    value that carries no information, so it reads as ABSENT.
    """
    sentinels, value_map = tuple(source.get('sentinels', ())), source.get('value_map')
    state, unmapped = ABSENT, None
    for path in source['paths']:
        if path not in doc:
            continue
        raw = doc[path]
        if is_blank(raw, sentinels, tokens):
            state = BLANK
            continue
        if value_map is not None:
            key = raw.strip() if isinstance(raw, str) else raw
            if key not in value_map:
                unmapped = raw
                continue
            return (ABSENT, None) if value_map[key] is None else (PRESENT, value_map[key])
        value = TRANSFORMS[source['transform']](raw)
        if value is None:
            state = BLANK
            continue
        return PRESENT, value
    return (UNMAPPED, unmapped) if unmapped is not None else (state, None)
