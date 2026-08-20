"""
Shared address normalization for matching utility-file addresses to county
Residential collections. Canonical form is the Residential format (AV, BL, CR).

Extracted from scripts/enrich_residential_from_utility_tool.py (DRY).
"""
import re


def normalize_address(address: str) -> str:
    """
    Normalize address for matching between utility and residential data.

    Converts to residential format (AV, BL, CR) which is the canonical form.
    Strips apartment/unit suffixes that appear in utility data but not residential.
    """
    if not address:
        return ''

    # Uppercase, strip whitespace, remove extra spaces
    addr = ' '.join(address.upper().strip().split())

    # Remove apartment, unit, suite suffixes (utility data has these, residential doesn't)
    # Must be done BEFORE suffix standardization to avoid partial matches
    addr = re.sub(r'\s+(APT|UNIT|SUITE|STE|#)\s*\S*$', '', addr, flags=re.IGNORECASE)

    # Suffix standardization - convert TO residential format (shorter forms)
    # Order matters: longer forms first to avoid partial replacements
    replacements = [
        # Full words to residential abbreviations
        (' STREET', ' ST'), (' AVENUE', ' AV'), (' DRIVE', ' DR'),
        (' ROAD', ' RD'), (' LANE', ' LN'), (' COURT', ' CT'),
        (' CIRCLE', ' CR'), (' BOULEVARD', ' BL'), (' PLACE', ' PL'),
        (' TERRACE', ' TE'), (' PARKWAY', ' PK'), (' HIGHWAY', ' HW'),
        (' ALLEY', ' AL'), (' LOOP', ' LP'),
        # Utility abbreviations to residential abbreviations
        (' AVE', ' AV'), (' BLVD', ' BL'), (' CIR', ' CR'),
        (' TER', ' TE'), (' PKWY', ' PK'), (' HWY', ' HW'),
        # Direction standardization
        (' NORTH', ' N'), (' SOUTH', ' S'), (' EAST', ' E'), (' WEST', ' W'),
    ]
    for old, new in replacements:
        addr = addr.replace(old, new)

    return addr


def normalize_address_keep_unit(address: str) -> str:
    """Normalize address but KEEP apartment/unit suffix for multi-unit detection."""
    if not address:
        return ''
    addr = ' '.join(address.upper().strip().split())
    replacements = [
        (' STREET', ' ST'), (' AVENUE', ' AV'), (' DRIVE', ' DR'),
        (' ROAD', ' RD'), (' LANE', ' LN'), (' COURT', ' CT'),
        (' CIRCLE', ' CR'), (' BOULEVARD', ' BL'), (' PLACE', ' PL'),
        (' TERRACE', ' TE'), (' PARKWAY', ' PK'), (' HIGHWAY', ' HW'),
        (' ALLEY', ' AL'), (' LOOP', ' LP'),
        (' AVE', ' AV'), (' BLVD', ' BL'), (' CIR', ' CR'),
        (' TER', ' TE'), (' PKWY', ' PK'), (' HWY', ' HW'),
        (' NORTH', ' N'), (' SOUTH', ' S'), (' EAST', ' E'), (' WEST', ' W'),
    ]
    for old, new in replacements:
        addr = addr.replace(old, new)
    return addr


def is_valid_person_name(name: str) -> bool:
    """Check if name looks like a person (not LLC, Corp, etc)."""
    if not name:
        return False
    name_upper = name.upper()
    business_indicators = [
        'LLC', 'INC', 'CORP', 'LTD', 'COMPANY', 'PROPERTIES', 'HOLDINGS',
        'TRUST', 'BANK', 'MORTGAGE', 'RENTAL', 'REALTY', 'INVESTMENT',
        'MANAGEMENT', 'DEVELOPMENT', 'ENTERPRISE', 'FOUNDATION', 'CHURCH',
        'ASSOCIATION', 'UNIVERSITY', 'SCHOOL', 'HOSPITAL', 'CENTER',
        'APARTMENTS', 'APTS', 'PARTNERS', 'GROUP', 'FUND', 'CAPITAL'
    ]
    for indicator in business_indicators:
        if indicator in name_upper:
            return False
    if name.startswith('.') or name.startswith('#') or name.startswith('`'):
        return False
    return True
