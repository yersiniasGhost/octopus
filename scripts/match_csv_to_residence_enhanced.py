#!/usr/bin/env python3
"""
Enhanced CSV-to-Residence Matching with Multiple Strategies

Improvements over basic matcher:
1. State route normalization (OH-314 → SR 314, US-40 → US 40)
2. Hyphenated road name handling
3. Name matching via Demographic collections
4. Email matching via Demographic collections
5. Phone matching via Demographic collections
6. Enhanced abbreviation normalization

Usage:
    source venv/bin/activate
    python scripts/match_csv_to_residence_enhanced.py
"""
import os
import sys
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = Path(__file__).parent.parent / 'data' / 'APPLICANTS_sign-up-today-2025-09-03.csv'
ZIPCODE_COUNTY_MAP = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'


class MatchQuality(Enum):
    """Match quality levels"""
    EXACT = "exact"
    GOOD = "good"
    FUZZY = "fuzzy"
    DEMOGRAPHIC = "demographic"  # Matched via name/email/phone
    NO_MATCH = "no_match"


@dataclass
class ApplicantRecord:
    """CSV applicant record"""
    entry_id: str
    first_name: str
    last_name: str
    email: str
    address: str
    city: str
    zip_code: str
    phone: str
    county: str

    @classmethod
    def from_csv_row(cls, row: Dict) -> 'ApplicantRecord':
        """Create from CSV row"""
        return cls(
            entry_id=row.get('Entry Id', ''),
            first_name=row.get('Name (First)', ''),
            last_name=row.get('Name (Last)', ''),
            email=row.get('Email', ''),
            address=row.get('Address (Street Address)', '') or row.get('City (Street Address)', '') or row.get('State (Street Address)', '') or row.get('Zip (Street Address)', ''),
            city=row.get('Address (City)', '') or row.get('City (City)', '') or row.get('State (City)', '') or row.get('Zip (City)', ''),
            zip_code=row.get('Address (ZIP / Postal Code)', '') or row.get('City (ZIP / Postal Code)', '') or row.get('State (ZIP / Postal Code)', '') or row.get('Zip (ZIP / Postal Code)', ''),
            phone=row.get('Phone', ''),
            county=row.get('County', '')
        )


@dataclass
class MatchResult:
    """Result of matching an applicant to residence/demographic"""
    applicant: ApplicantRecord
    match_quality: MatchQuality
    residence_record: Optional[Dict] = None
    demographic_record: Optional[Dict] = None
    match_method: Optional[str] = None
    match_details: str = ""


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
    def normalize(cls, phone: str) -> str:
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


class EnhancedResidenceMatcher:
    """Enhanced matching with multiple strategies"""

    def __init__(self):
        self.mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        print(f"Connecting to MongoDB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db}")
        self.client = MongoClient(self.mongo_host, self.mongo_port)
        self.db = self.client[self.mongo_db]

        # Load zipcode mapping
        with open(ZIPCODE_COUNTY_MAP, 'r') as f:
            data = json.load(f)
            self.zipcode_map = data.get('zipcode_map', {})

        # Statistics
        self.stats = {
            'total_applicants': 0,
            'exact_matches': 0,
            'good_matches': 0,
            'fuzzy_matches': 0,
            'demographic_matches': 0,
            'no_matches': 0,
            'county_not_found': 0,
            'collection_not_found': 0,
            'match_methods': {
                'address_exact': 0,
                'address_normalized': 0,
                'address_fuzzy': 0,
                'address_state_route': 0,
                'address_hyphenated': 0,
                'email': 0,
                'name': 0,
                'phone': 0,
            }
        }

    def load_applicants(self) -> List[ApplicantRecord]:
        """Load applicants from CSV"""
        print(f"\nLoading applicants from: {CSV_FILE}")
        applicants = []

        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                applicant = ApplicantRecord.from_csv_row(row)
                applicants.append(applicant)

        self.stats['total_applicants'] = len(applicants)
        print(f"Loaded {len(applicants)} applicants")
        return applicants

    def get_county_from_zipcode(self, zipcode: str) -> Optional[str]:
        """Map zipcode to county"""
        if not zipcode:
            return None
        clean_zip = re.sub(r'\D', '', zipcode)[:5]
        return self.zipcode_map.get(clean_zip)

    def match_applicant(self, applicant: ApplicantRecord) -> MatchResult:
        """Match applicant using multiple strategies"""

        # Determine county
        county = applicant.county
        if county:
            county = f"{county}County"
        elif applicant.zip_code:
            county = self.get_county_from_zipcode(applicant.zip_code)

        if not county:
            self.stats['county_not_found'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.NO_MATCH,
                match_details="County not found"
            )

        # Get collections
        residence_coll_name = f"{county}Residential"
        demographic_coll_name = f"{county}Demographic"

        # Strategy 1: Try email matching first (fastest, most reliable)
        if applicant.email and demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_email(demographic_coll_name, applicant)
            if result:
                return result

        # Strategy 2: Try name matching in demographic
        if applicant.first_name and applicant.last_name and demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_name(demographic_coll_name, applicant)
            if result:
                return result

        # Strategy 3: Try phone matching
        if applicant.phone and demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_phone(demographic_coll_name, applicant)
            if result:
                return result

        # Strategy 4-8: Address matching (if residence collection exists)
        if residence_coll_name not in self.db.list_collection_names():
            self.stats['collection_not_found'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.NO_MATCH,
                match_details=f"Collection '{residence_coll_name}' not found"
            )

        residence_coll = self.db[residence_coll_name]

        # Strategy 4: Exact address
        if applicant.address:
            result = self._match_by_address(residence_coll, applicant, exact=True)
            if result:
                return result

        # Strategy 5: Normalized address
        if applicant.address:
            result = self._match_by_address(residence_coll, applicant, exact=False)
            if result:
                return result

        # Strategy 6: State route variations
        if applicant.address and re.search(r'(OH|US|SR)[-\s]\d+', applicant.address, re.IGNORECASE):
            result = self._match_state_route(residence_coll, applicant)
            if result:
                return result

        # Strategy 7: Hyphenated road variations
        if applicant.address and '-' in applicant.address:
            result = self._match_hyphenated(residence_coll, applicant)
            if result:
                return result

        # Strategy 8: Fuzzy address
        if applicant.address:
            result = self._match_fuzzy_address(residence_coll, applicant)
            if result:
                return result

        # No match
        self.stats['no_matches'] += 1
        return MatchResult(
            applicant=applicant,
            match_quality=MatchQuality.NO_MATCH,
            match_details=f"No match found in {residence_coll_name} or {demographic_coll_name}"
        )

    def _match_by_email(self, demographic_coll_name: str, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Match by email in demographic collection"""
        collection = self.db[demographic_coll_name]

        doc = collection.find_one({'email': applicant.email.lower()})
        if doc:
            self.stats['demographic_matches'] += 1
            self.stats['match_methods']['email'] += 1

            # Try to get residence record too
            residence_coll_name = demographic_coll_name.replace('Demographic', 'Residential')
            residence_doc = None
            if residence_coll_name in self.db.list_collection_names():
                residence_coll = self.db[residence_coll_name]
                residence_doc = residence_coll.find_one({'parcel_id': doc.get('parcel_id')})

            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.DEMOGRAPHIC,
                demographic_record=doc,
                residence_record=residence_doc,
                match_method='email',
                match_details=f"Email match: {applicant.email}"
            )

        return None

    def _match_by_name(self, demographic_coll_name: str, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Match by name in demographic collection"""
        collection = self.db[demographic_coll_name]

        # Get candidates from same ZIP if available
        query = {}
        if applicant.zip_code:
            try:
                query['parcel_zip'] = int(applicant.zip_code)
            except ValueError:
                pass

        for doc in collection.find(query):
            customer_name = doc.get('customer_name', '')
            is_match, match_type = NameMatcher.match(
                applicant.first_name,
                applicant.last_name,
                customer_name
            )

            if is_match:
                self.stats['demographic_matches'] += 1
                self.stats['match_methods']['name'] += 1

                # Get residence record
                residence_coll_name = demographic_coll_name.replace('Demographic', 'Residential')
                residence_doc = None
                if residence_coll_name in self.db.list_collection_names():
                    residence_coll = self.db[residence_coll_name]
                    residence_doc = residence_coll.find_one({'parcel_id': doc.get('parcel_id')})

                return MatchResult(
                    applicant=applicant,
                    match_quality=MatchQuality.DEMOGRAPHIC,
                    demographic_record=doc,
                    residence_record=residence_doc,
                    match_method=f'name_{match_type}',
                    match_details=f"Name match ({match_type}): {applicant.first_name} {applicant.last_name} → {customer_name}"
                )

        return None

    def _match_by_phone(self, demographic_coll_name: str, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Match by phone in demographic collection"""
        collection = self.db[demographic_coll_name]

        norm_phone = PhoneNormalizer.normalize(applicant.phone)
        if not norm_phone:
            return None

        for doc in collection.find():
            db_phone = str(doc.get('mobile', ''))
            if PhoneNormalizer.match(applicant.phone, db_phone):
                self.stats['demographic_matches'] += 1
                self.stats['match_methods']['phone'] += 1

                # Get residence record
                residence_coll_name = demographic_coll_name.replace('Demographic', 'Residential')
                residence_doc = None
                if residence_coll_name in self.db.list_collection_names():
                    residence_coll = self.db[residence_coll_name]
                    residence_doc = residence_coll.find_one({'parcel_id': doc.get('parcel_id')})

                return MatchResult(
                    applicant=applicant,
                    match_quality=MatchQuality.DEMOGRAPHIC,
                    demographic_record=doc,
                    residence_record=residence_doc,
                    match_method='phone',
                    match_details=f"Phone match: {applicant.phone}"
                )

        return None

    def _match_by_address(self, collection, applicant: ApplicantRecord, exact: bool = True) -> Optional[MatchResult]:
        """Match by address (exact or normalized)"""
        query = {}
        if applicant.zip_code:
            try:
                query['parcel_zip'] = int(applicant.zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            db_address = record.get('address', '')

            if exact:
                if applicant.address == db_address:
                    self.stats['exact_matches'] += 1
                    self.stats['match_methods']['address_exact'] += 1
                    return MatchResult(
                        applicant=applicant,
                        match_quality=MatchQuality.EXACT,
                        residence_record=record,
                        match_method='address_exact',
                        match_details=f"Exact: {applicant.address}"
                    )
            else:
                if AddressNormalizer.exact_match(applicant.address, db_address):
                    self.stats['good_matches'] += 1
                    self.stats['match_methods']['address_normalized'] += 1
                    return MatchResult(
                        applicant=applicant,
                        match_quality=MatchQuality.GOOD,
                        residence_record=record,
                        match_method='address_normalized',
                        match_details=f"Normalized: '{applicant.address}' → '{db_address}'"
                    )

        return None

    def _match_state_route(self, collection, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Match with state route variations"""
        variations = AddressNormalizer.normalize_state_route(applicant.address)

        for var in variations:
            # Search using regex for flexibility
            norm_var = AddressNormalizer.normalize(var)
            for record in collection.find():
                db_addr = AddressNormalizer.normalize(record.get('address', ''))
                if norm_var in db_addr or db_addr in norm_var:
                    self.stats['good_matches'] += 1
                    self.stats['match_methods']['address_state_route'] += 1
                    return MatchResult(
                        applicant=applicant,
                        match_quality=MatchQuality.GOOD,
                        residence_record=record,
                        match_method='state_route',
                        match_details=f"State route: '{applicant.address}' → '{record.get('address')}' (variation: {var})"
                    )

        return None

    def _match_hyphenated(self, collection, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Match with hyphenated road variations"""
        variations = AddressNormalizer.normalize_hyphenated(applicant.address)

        for var in variations:
            norm_var = AddressNormalizer.normalize(var)
            for record in collection.find():
                db_addr = AddressNormalizer.normalize(record.get('address', ''))
                if norm_var == db_addr or (len(norm_var) > 5 and norm_var in db_addr):
                    self.stats['good_matches'] += 1
                    self.stats['match_methods']['address_hyphenated'] += 1
                    return MatchResult(
                        applicant=applicant,
                        match_quality=MatchQuality.GOOD,
                        residence_record=record,
                        match_method='hyphenated',
                        match_details=f"Hyphenated: '{applicant.address}' → '{record.get('address')}' (variation: {var})"
                    )

        return None

    def _match_fuzzy_address(self, collection, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Fuzzy address matching"""
        query = {}
        if applicant.zip_code:
            try:
                query['parcel_zip'] = int(applicant.zip_code)
            except ValueError:
                pass

        best_match = None
        best_score = 0.0

        for record in collection.find(query):
            db_address = record.get('address', '')
            is_match, score = AddressNormalizer.fuzzy_match(applicant.address, db_address)

            if is_match and score > best_score:
                best_score = score
                best_match = record

        if best_match:
            self.stats['fuzzy_matches'] += 1
            self.stats['match_methods']['address_fuzzy'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.FUZZY,
                residence_record=best_match,
                match_method='fuzzy_address',
                match_details=f"Fuzzy (score: {best_score:.2f}): '{applicant.address}' ~= '{best_match.get('address')}'"
            )

        return None

    def run_matching(self) -> List[MatchResult]:
        """Run enhanced matching process"""
        print("\n" + "="*80)
        print("ENHANCED RESIDENCE MATCHING - Multiple Strategies")
        print("="*80)
        print("Strategies:")
        print("  1. Email matching (Demographic)")
        print("  2. Name matching (Demographic)")
        print("  3. Phone matching (Demographic)")
        print("  4. Exact address (Residential)")
        print("  5. Normalized address (Residential)")
        print("  6. State route variations (Residential)")
        print("  7. Hyphenated road variations (Residential)")
        print("  8. Fuzzy address (Residential)")
        print("="*80)

        applicants = self.load_applicants()
        results = []

        for i, applicant in enumerate(applicants, 1):
            if i % 10 == 0:
                print(f"Processing applicant {i}/{len(applicants)}...")

            result = self.match_applicant(applicant)
            results.append(result)

        return results

    def print_statistics(self):
        """Print detailed statistics"""
        print("\n" + "="*80)
        print("ENHANCED MATCHING STATISTICS")
        print("="*80)
        total = self.stats['total_applicants']

        print(f"\nTotal Applicants:         {total}")
        print(f"Exact Matches:            {self.stats['exact_matches']:4d} ({self._pct('exact_matches')}%)")
        print(f"Good Matches:             {self.stats['good_matches']:4d} ({self._pct('good_matches')}%)")
        print(f"Fuzzy Matches:            {self.stats['fuzzy_matches']:4d} ({self._pct('fuzzy_matches')}%)")
        print(f"Demographic Matches:      {self.stats['demographic_matches']:4d} ({self._pct('demographic_matches')}%)")
        print(f"No Matches:               {self.stats['no_matches']:4d} ({self._pct('no_matches')}%)")

        print(f"\nIssues:")
        print(f"County Not Found:         {self.stats['county_not_found']:4d} ({self._pct('county_not_found')}%)")
        print(f"Collection Not Found:     {self.stats['collection_not_found']:4d} ({self._pct('collection_not_found')}%)")

        total_matched = total - self.stats['no_matches']
        print(f"\nTotal Matched:            {total_matched:4d} ({total_matched/total*100:.1f}%)")

        print(f"\nMatch Methods:")
        for method, count in sorted(self.stats['match_methods'].items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                print(f"  {method:25s}: {count:4d}")

        print("="*80)

    def _pct(self, key: str) -> str:
        """Calculate percentage"""
        total = self.stats['total_applicants']
        if total == 0:
            return "0.0"
        return f"{(self.stats[key] / total * 100):.1f}"

    def close(self):
        """Close MongoDB connection"""
        self.client.close()


def main():
    """Main execution"""
    print(f"Script started at: {datetime.now()}")

    matcher = EnhancedResidenceMatcher()

    try:
        results = matcher.run_matching()
        matcher.print_statistics()

        print(f"\nScript completed at: {datetime.now()}")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        matcher.close()


if __name__ == '__main__':
    sys.exit(main())
