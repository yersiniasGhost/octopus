"""
Parsing and normalization utilities for application data.

Handles the messy real-world data formats from application forms:
- Income: "40,000", "$100,000", "1850mo", "28.000", "100,00.00"
- Phone: "(614)499-2431", "+ 4197072553", "419. 544 1539"
- UTM: Parse from URL query strings
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs


def normalize_phone(phone_raw: Optional[str]) -> Optional[str]:
    """Normalize phone number to digits only.

    Args:
        phone_raw: Raw phone string in various formats

    Returns:
        10-digit phone string or None if invalid

    Examples:
        "(614)499-2431" -> "6144992431"
        "+ 4197072553" -> "4197072553"
        "419. 544 1539" -> "4195441539"
        "3302067363" -> "3302067363"
    """
    if not phone_raw:
        return None

    # Extract only digits
    digits = re.sub(r'\D', '', str(phone_raw))

    # Handle country code prefix (1 for US)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]

    # Validate 10-digit US phone
    if len(digits) == 10:
        return digits

    return None  # Invalid phone


_RANGE_DELIMITER_RE = re.compile(r'\s*[-–—]\s*|\s+to\s+', re.IGNORECASE)
_NUMERIC_TOKEN_RE = re.compile(r'\d[\d.,]*[kK]?')
# Match monthly markers: "1850mo" / "1850/mo" / "$1850 mo" / "month" / "monthly".
# Note: `\b` doesn't fire between a digit and a letter (both word chars), so the
# digit-prefixed form needs its own alternative. `month` covers "month"/"monthly"
# and avoids the `\b` problem inside "month" itself (n follows mo → no boundary).
_MONTHLY_RE = re.compile(r'(?<=\d)\s*/?mo\b|\bmo\b|month', re.IGNORECASE)
_K_SUFFIX_RE = re.compile(r'\d\s*[kK]\b')


def _parse_single_amount(token: str) -> Optional[float]:
    """Parse one numeric token (with optional thousands/decimal separators) to a float.

    Recognizes a trailing 'k'/'K' as a thousands multiplier (e.g. '50k' → 50000).
    """
    has_k_suffix = bool(_K_SUFFIX_RE.search(token))

    cleaned = re.sub(r'[^\d.,]', '', token)
    if not cleaned:
        return None

    # European format (28.000 = 28,000): one period followed by exactly 3 digits at end
    if re.match(r'^\d{1,3}\.\d{3}$', cleaned):
        cleaned = cleaned.replace('.', '')

    cleaned = cleaned.replace(',', '')

    # Multiple decimal points — keep first as decimal, drop rest
    if cleaned.count('.') > 1:
        parts = cleaned.split('.')
        cleaned = parts[0] + '.' + ''.join(parts[1:])

    try:
        amount = float(cleaned)
    except ValueError:
        return None

    if has_k_suffix:
        amount *= 1000.0
    return amount


def normalize_income(income_raw: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """Normalize income to annual amount.

    Handles various formats from application forms:
    - Plain numbers: "35000", "35,000"
    - With dollar sign: "$100,000"
    - Monthly: "1850mo", "1850/mo"
    - European format: "28.000" (comma as thousands sep)
    - Malformed thousands sep: "100,00.00", "36, 000"
    - Ranges: "21,000-22,000", "$40k to $50k" → midpoint
    - Ambiguous free-text with multiple disjoint numbers → None
      (e.g. "1200 and$1245 $45" — refuses to silently concatenate)

    Args:
        income_raw: Raw income string

    Returns:
        Tuple of (normalized_annual_income, raw_value)
    """
    if not income_raw:
        return None, None

    raw = str(income_raw).strip()
    if not raw:
        return None, None
    if raw == '0':
        return 0.0, raw

    is_monthly = bool(_MONTHLY_RE.search(raw))

    # Strip currency markers and monthly suffix to expose pure structure
    working = re.sub(r'[$£€¥]', '', raw)
    working = _MONTHLY_RE.sub('', working).strip()

    # Collapse "comma + whitespace" → comma (typo for thousands sep, e.g. "36, 000")
    working = re.sub(r',\s+', ',', working)

    # Range pattern: "21,000-22,000", "21000 to 22000", "$55-75k"
    range_parts = _RANGE_DELIMITER_RE.split(working)
    if len(range_parts) == 2:
        left, right = range_parts
        # Convention: "$55-75k" means "$55k-$75k" — propagate k suffix across
        # the range when only one side carries it.
        left_has_k = bool(_K_SUFFIX_RE.search(left))
        right_has_k = bool(_K_SUFFIX_RE.search(right))
        if right_has_k and not left_has_k:
            left = left + 'k'
        elif left_has_k and not right_has_k:
            right = right + 'k'
        low = _parse_single_amount(left)
        high = _parse_single_amount(right)
        if low is not None and high is not None and low <= high:
            amount = (low + high) / 2.0
            if is_monthly:
                amount *= 12
            return amount, raw

    # Refuse to guess when raw contains multiple disjoint numeric tokens
    # separated by non-numeric content that isn't a range delimiter.
    tokens = _NUMERIC_TOKEN_RE.findall(working)
    if not tokens:
        return None, raw
    if len(tokens) > 1:
        return None, raw

    amount = _parse_single_amount(tokens[0])
    if amount is None:
        return None, raw
    if is_monthly:
        amount *= 12
    return amount, raw


def parse_utm_from_url(url: Optional[str]) -> dict:
    """Parse UTM parameters from a URL.

    Args:
        url: Full URL potentially containing UTM parameters

    Returns:
        Dict with utm_source, utm_medium, utm_campaign, utm_id, utm_content

    Example:
        "https://example.com/?utm_source=Majority&utm_medium=Letter"
        -> {"utm_source": "Majority", "utm_medium": "Letter", ...}
    """
    result = {
        'utm_source': None,
        'utm_medium': None,
        'utm_campaign': None,
        'utm_id': None,
        'utm_content': None,
        'source_url': url
    }

    if not url:
        return result

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Extract UTM params (parse_qs returns lists, take first value)
        for key in ['utm_source', 'utm_medium', 'utm_campaign', 'utm_id', 'utm_content']:
            if key in params:
                value = params[key][0]
                # Decode URL encoding (+ becomes space)
                result[key] = value.replace('+', ' ')

    except Exception:
        pass  # Return defaults on parse error

    return result


def normalize_age(age_raw: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Normalize age to integer.

    Args:
        age_raw: Raw age string

    Returns:
        Tuple of (normalized_age, raw_value)
    """
    if not age_raw:
        return None, None

    raw = str(age_raw).strip()

    try:
        age = int(float(raw))
        if 0 < age < 120:  # Sanity check
            return age, raw
        return None, raw
    except ValueError:
        return None, raw


def normalize_household_members(members_raw: Optional[str]) -> Optional[int]:
    """Normalize household members to integer.

    Handles edge cases like "E" (typo for a number).
    """
    if not members_raw:
        return None

    raw = str(members_raw).strip()

    try:
        members = int(float(raw))
        if 0 <= members <= 20:  # Sanity check
            return members
        return None
    except ValueError:
        return None


def parse_housing_status(rent_val: Optional[str], own_val: Optional[str]) -> Optional[str]:
    """Parse housing status from Rent/Own checkbox fields.

    The CSV has separate Rent and Own columns.
    """
    if rent_val and str(rent_val).strip():
        return "rent"
    if own_val and str(own_val).strip():
        return "own"
    return None


def parse_boolean_field(value: Optional[str]) -> Optional[bool]:
    """Parse boolean from various checkbox/text representations."""
    if not value:
        return None

    val = str(value).strip().lower()

    if val in ('y', 'yes', 'true', '1', 'x', 'checked'):
        return True
    if val in ('n', 'no', 'false', '0', '', 'unchecked'):
        return False

    # Non-empty value usually means checked
    if val:
        return True

    return None
