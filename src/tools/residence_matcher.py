"""
Reusable Residence/Demographic Matching Tool

Provides 8-strategy matching logic for matching contacts to residence/demographic data:
1. Email matching (Demographic) - Fastest, most reliable
2. Name matching (Demographic) - Fuzzy name logic
3. Phone matching (Demographic) - Normalized phone comparison
4. Exact address (Residential) - Direct string match
5. Normalized address (Residential) - Street/directional abbreviations
6. State route variations (Residential) - OH-314, US-40 patterns
7. Hyphenated road variations (Residential) - "Cadiz-New Athens Rd"
8. Fuzzy address (Residential) - Score-based similarity

Usage:
    from src.tools.residence_matcher import ResidenceMatcher

    matcher = ResidenceMatcher(db, county='FranklinCounty')
    residence_ref, demographic_ref, match_method = matcher.match(
        phone='6145551234',
        email='john@example.com',
        first_name='John',
        last_name='Doe',
        address='123 Main St',
        zipcode='43210'
    )
"""
import re
from typing import Dict, List, Optional, Tuple
from enum import Enum

from src.models.common import ResidenceReference, DemographicReference


class MatchQuality(Enum):
    """Match quality levels"""
    EXACT = "exact"
    GOOD = "good"
    FUZZY = "fuzzy"
    DEMOGRAPHIC = "demographic"
    NO_MATCH = "no_match"


class AddressNormalizer:
    """Enhanced address normalization"""

    STREET_ABBREV = {
        'street': 'st', 'avenue': 'ave', 'road': 'rd', 'drive': 'dr',
        'lane': 'ln', 'court': 'ct', 'circle': 'cir', 'boulevard': 'blvd',
        'parkway': 'pkwy', 'place': 'pl', 'terrace': 'ter', 'way': 'way',
        'highway': 'hwy', 'route': 'rte',
    }

    DIRECTIONAL_ABBREV = {
        'north': 'n', 'south': 's', 'east': 'e', 'west': 'w',
        'northeast': 'ne', 'northwest': 'nw', 'southeast': 'se', 'southwest': 'sw',
    }

    @classmethod
    def normalize_state_route(cls, address: str) -> List[str]:
        """
        Normalize state route addresses to multiple variations

        Returns list of possible variations:
        - "OH-314" → ["OH 314", "SR 314", "STATE ROUTE 314", "OH-314"]
        - "US-40" → ["US 40", "US HIGHWAY 40", "US-40"]
        """
        variations = [address]

        # OH-### pattern
        match = re.search(r'(OH|US|SR|STATE ROUTE)\s*[-\s]\s*(\d+)', address, re.IGNORECASE)
        if match:
            route_type = match.group(1).upper()
            route_num = match.group(2)

            if 'OH' in route_type:
                variations.extend([
                    f"OH {route_num}",
                    f"SR {route_num}",
                    f"STATE ROUTE {route_num}",
                    f"OH-{route_num}",
                ])
            elif 'US' in route_type:
                variations.extend([
                    f"US {route_num}",
                    f"US HIGHWAY {route_num}",
                    f"US-{route_num}",
                ])
            elif 'SR' in route_type:
                variations.extend([
                    f"SR {route_num}",
                    f"STATE ROUTE {route_num}",
                    f"OH {route_num}",
                ])

        return list(set(variations))

    @classmethod
    def normalize_hyphenated(cls, address: str) -> List[str]:
        """
        Generate variations for hyphenated road names

        - "Cadiz-New Athens Rd" → ["CADIZ NEW ATHENS RD", "NEW ATHENS RD", "CADIZ RD"]
        """
        variations = [address]

        # Find hyphenated components
        if '-' in address and not re.match(r'^\d+-\d+', address):  # Not a house number range
            # Replace hyphen with space
            variations.append(address.replace('-', ' '))

            # Try individual components
            parts = address.split('-')
            if len(parts) == 2:
                # Try second part only (often the main road name)
                variations.append(parts[1].strip())
                # Try first part only
                variations.append(parts[0].strip())

        return list(set(variations))

    @classmethod
    def normalize(cls, address: str) -> str:
        """Normalize address for matching"""
        if not address:
            return ""

        addr = address.lower().strip()
        addr = re.sub(r'[,.]', '', addr)

        # Normalize street types
        for full, abbrev in cls.STREET_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        # Normalize directionals
        for full, abbrev in cls.DIRECTIONAL_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        addr = re.sub(r'\s+', ' ', addr)
        return addr.strip()

    @classmethod
    def exact_match(cls, addr1: str, addr2: str) -> bool:
        """Check if addresses match exactly after normalization"""
        return cls.normalize(addr1) == cls.normalize(addr2)

    @classmethod
    def fuzzy_match(cls, addr1: str, addr2: str) -> Tuple[bool, float]:
        """Fuzzy address matching with confidence score"""
        norm1 = cls.normalize(addr1)
        norm2 = cls.normalize(addr2)

        if not norm1 or not norm2:
            return False, 0.0

        if norm1 == norm2:
            return True, 1.0

        # Extract street number
        match1 = re.match(r'^(\d+)', norm1)
        match2 = re.match(r'^(\d+)', norm2)

        if not match1 or not match2:
            return False, 0.0

        # Street numbers must match
        if match1.group(1) != match2.group(1):
            return False, 0.0

        # Calculate similarity
        rest1 = norm1[len(match1.group(1)):].strip()
        rest2 = norm2[len(match2.group(1)):].strip()

        if rest1 in rest2 or rest2 in rest1:
            score = min(len(rest1), len(rest2)) / max(len(rest1), len(rest2))
            return score > 0.7, score

        return False, 0.0


class NameMatcher:
    """Match names"""

    @classmethod
    def normalize_name(cls, name: str) -> str:
        """Normalize name for comparison"""
        if not name:
            return ""
        # Lowercase, remove extra spaces
        name = re.sub(r'\s+', ' ', name.lower().strip())
        # Remove suffixes
        name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)
        return name.strip()

    @classmethod
    def match(cls, first: str, last: str, full_name: str) -> Tuple[bool, str]:
        """
        Match first/last name against full name

        Returns: (is_match, match_type)
        """
        if not first and not last:
            return False, ""
        if not full_name:
            return False, ""

        norm_first = cls.normalize_name(first)
        norm_last = cls.normalize_name(last)
        norm_full = cls.normalize_name(full_name)

        # Exact match
        if norm_first and norm_last:
            constructed = f"{norm_first} {norm_last}"
            if constructed in norm_full or norm_full == constructed:
                return True, "exact"

        # Last name match
        if norm_last and norm_last in norm_full:
            if norm_first and (norm_first in norm_full or norm_full.startswith(norm_first[0])):
                return True, "fuzzy"

        return False, ""


class PhoneNormalizer:
    """Normalize phone numbers"""

    @classmethod
    def normalize(cls, phone) -> str:
        """Normalize to digits only"""
        if not phone:
            return ""

        phone_str = str(phone)
        digits = re.sub(r'\D', '', phone_str)

        # Remove leading 1 if 11 digits
        if len(digits) == 11 and digits[0] == '1':
            digits = digits[1:]

        return digits

    @classmethod
    def match(cls, phone1: str, phone2: str) -> bool:
        """Check if phone numbers match"""
        norm1 = cls.normalize(phone1)
        norm2 = cls.normalize(phone2)

        if not norm1 or not norm2:
            return False

        return norm1 == norm2


class ResidenceMatcher:
    """
    Reusable residence/demographic matcher with 8-strategy logic

    Example:
        matcher = ResidenceMatcher(db, county='FranklinCounty')
        residence_ref, demographic_ref, method = matcher.match(
            phone='6145551234',
            email='john@example.com',
            address='123 Main St',
            zipcode='43210'
        )
    """

    def __init__(self, db, county: str):
        """
        Initialize matcher

        Args:
            db: MongoDB database instance
            county: County name (e.g., 'FranklinCounty', 'CuyahogaCounty')
        """
        self.db = db
        self.county = county
        self.residence_coll_name = f"{county}Residential"
        self.demographic_coll_name = f"{county}Demographic"

    def match(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        address: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> Tuple[Optional[ResidenceReference], Optional[DemographicReference], str]:
        """
        Match contact to residence/demographic using 8 strategies

        Returns:
            (residence_ref, demographic_ref, match_method)
        """

        # Strategy 1: Email matching (fastest, most reliable)
        if email and self.demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_email(email)
            if result:
                return result

        # Strategy 2: Name matching
        if first_name and last_name and self.demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_name(first_name, last_name, zipcode)
            if result:
                return result

        # Strategy 3: Phone matching
        if phone and self.demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_phone(phone)
            if result:
                return result

        # Strategies 4-8: Address matching
        if self.residence_coll_name not in self.db.list_collection_names():
            return None, None, "collection_not_found"

        residence_coll = self.db[self.residence_coll_name]

        # Strategy 4: Exact address
        if address:
            result = self._match_by_address(residence_coll, address, zipcode, exact=True)
            if result:
                return result

        # Strategy 5: Normalized address
        if address:
            result = self._match_by_address(residence_coll, address, zipcode, exact=False)
            if result:
                return result

        # Strategy 6: State route variations
        if address and re.search(r'(OH|US|SR)[-\s]\d+', address, re.IGNORECASE):
            result = self._match_state_route(residence_coll, address)
            if result:
                return result

        # Strategy 7: Hyphenated road variations
        if address and '-' in address:
            result = self._match_hyphenated(residence_coll, address)
            if result:
                return result

        # Strategy 8: Fuzzy address
        if address:
            result = self._match_fuzzy_address(residence_coll, address, zipcode)
            if result:
                return result

        return None, None, "no_match"

    def _match_by_email(self, email: str) -> Optional[Tuple[Optional[ResidenceReference], DemographicReference, str]]:
        """Strategy 1: Email matching in demographic collection"""
        collection = self.db[self.demographic_coll_name]

        doc = collection.find_one({'email': email.lower()})
        if doc:
            # Try to get residence record too
            residence_doc = None
            if self.residence_coll_name in self.db.list_collection_names():
                residence_coll = self.db[self.residence_coll_name]
                residence_doc = residence_coll.find_one({'parcel_id': doc.get('parcel_id')})

            residence_ref = ResidenceReference.from_record(self.county, residence_doc) if residence_doc else None
            demographic_ref = DemographicReference.from_record(self.county, doc)

            return residence_ref, demographic_ref, "email"

        return None

    def _match_by_name(self, first_name: str, last_name: str, zipcode: Optional[str]) -> Optional[Tuple[Optional[ResidenceReference], DemographicReference, str]]:
        """Strategy 2: Name matching in demographic collection"""
        collection = self.db[self.demographic_coll_name]

        # Filter by ZIP if available
        query = {}
        if zipcode:
            try:
                query['parcel_zip'] = int(zipcode)
            except ValueError:
                pass

        for doc in collection.find(query):
            customer_name = doc.get('customer_name', '')
            is_match, match_type = NameMatcher.match(first_name, last_name, customer_name)

            if is_match:
                # Get residence record
                residence_doc = None
                if self.residence_coll_name in self.db.list_collection_names():
                    residence_coll = self.db[self.residence_coll_name]
                    residence_doc = residence_coll.find_one({'parcel_id': doc.get('parcel_id')})

                residence_ref = ResidenceReference.from_record(self.county, residence_doc) if residence_doc else None
                demographic_ref = DemographicReference.from_record(self.county, doc)

                return residence_ref, demographic_ref, f"name_{match_type}"

        return None

    def _match_by_phone(self, phone: str) -> Optional[Tuple[Optional[ResidenceReference], DemographicReference, str]]:
        """Strategy 3: Phone matching in demographic collection"""
        collection = self.db[self.demographic_coll_name]

        norm_phone = PhoneNormalizer.normalize(phone)
        if not norm_phone:
            return None

        for doc in collection.find():
            db_phone = str(doc.get('mobile', ''))
            if PhoneNormalizer.match(phone, db_phone):
                # Get residence record
                residence_doc = None
                if self.residence_coll_name in self.db.list_collection_names():
                    residence_coll = self.db[self.residence_coll_name]
                    residence_doc = residence_coll.find_one({'parcel_id': doc.get('parcel_id')})

                residence_ref = ResidenceReference.from_record(self.county, residence_doc) if residence_doc else None
                demographic_ref = DemographicReference.from_record(self.county, doc)

                return residence_ref, demographic_ref, "phone"

        return None

    def _match_by_address(self, collection, address: str, zipcode: Optional[str], exact: bool) -> Optional[Tuple[ResidenceReference, None, str]]:
        """Strategy 4-5: Address matching (exact or normalized)"""
        query = {}
        if zipcode:
            try:
                query['parcel_zip'] = int(zipcode)
            except ValueError:
                pass

        for record in collection.find(query):
            db_address = record.get('address', '')

            if exact:
                if address == db_address:
                    residence_ref = ResidenceReference.from_record(self.county, record)
                    return residence_ref, None, "address_exact"
            else:
                if AddressNormalizer.exact_match(address, db_address):
                    residence_ref = ResidenceReference.from_record(self.county, record)
                    return residence_ref, None, "address_normalized"

        return None

    def _match_state_route(self, collection, address: str) -> Optional[Tuple[ResidenceReference, None, str]]:
        """Strategy 6: State route variations"""
        variations = AddressNormalizer.normalize_state_route(address)

        for var in variations:
            norm_var = AddressNormalizer.normalize(var)
            for record in collection.find():
                db_addr = AddressNormalizer.normalize(record.get('address', ''))
                if norm_var in db_addr or db_addr in norm_var:
                    residence_ref = ResidenceReference.from_record(self.county, record)
                    return residence_ref, None, "state_route"

        return None

    def _match_hyphenated(self, collection, address: str) -> Optional[Tuple[ResidenceReference, None, str]]:
        """Strategy 7: Hyphenated road variations"""
        variations = AddressNormalizer.normalize_hyphenated(address)

        for var in variations:
            norm_var = AddressNormalizer.normalize(var)
            for record in collection.find():
                db_addr = AddressNormalizer.normalize(record.get('address', ''))
                if norm_var == db_addr or (len(norm_var) > 5 and norm_var in db_addr):
                    residence_ref = ResidenceReference.from_record(self.county, record)
                    return residence_ref, None, "hyphenated"

        return None

    def _match_fuzzy_address(self, collection, address: str, zipcode: Optional[str]) -> Optional[Tuple[ResidenceReference, None, str]]:
        """Strategy 8: Fuzzy address matching"""
        query = {}
        if zipcode:
            try:
                query['parcel_zip'] = int(zipcode)
            except ValueError:
                pass

        best_match = None
        best_score = 0.0

        for record in collection.find(query):
            db_address = record.get('address', '')
            is_match, score = AddressNormalizer.fuzzy_match(address, db_address)

            if is_match and score > best_score:
                best_score = score
                best_match = record

        if best_match:
            residence_ref = ResidenceReference.from_record(self.county, best_match)
            return residence_ref, None, f"fuzzy_{best_score:.2f}"

        return None
