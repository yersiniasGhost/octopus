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


def normalize_income(income_raw: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """Normalize income to annual amount.

    Handles various formats from application forms:
    - Plain numbers: "35000", "35,000"
    - With dollar sign: "$100,000"
    - Monthly: "1850mo", "1850/mo"
    - European format: "28.000" (comma as thousands sep)
    - Malformed: "100,00.00", "36, 000"

    Args:
        income_raw: Raw income string

    Returns:
        Tuple of (normalized_annual_income, raw_value)
    """
    if not income_raw:
        return None, None

    raw = str(income_raw).strip()
    if not raw or raw == '0':
        return 0.0, raw

    # Detect monthly income patterns
    is_monthly = bool(re.search(r'mo|/mo|per\s*month|monthly', raw, re.IGNORECASE))

    # Remove non-numeric characters except . and ,
    cleaned = re.sub(r'[^\d.,]', '', raw)

    if not cleaned:
        return None, raw

    # Handle European format (28.000 = 28,000)
    # If there's exactly one period and it's followed by 3 digits at end, it's thousands sep
    if re.match(r'^\d{1,3}\.\d{3}$', cleaned):
        cleaned = cleaned.replace('.', '')

    # Handle malformed comma placement (100,00.00 or 36, 000)
    # Remove commas that aren't proper thousands separators
    cleaned = cleaned.replace(' ', '')

    # Standard cleanup: remove commas (thousands separators)
    cleaned = cleaned.replace(',', '')

    # Handle multiple decimal points - take first valid number
    if cleaned.count('.') > 1:
        parts = cleaned.split('.')
        cleaned = parts[0] + '.' + ''.join(parts[1:])

    try:
        amount = float(cleaned)

        # Convert monthly to annual
        if is_monthly:
            amount = amount * 12

        return amount, raw
    except ValueError:
        return None, raw


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
