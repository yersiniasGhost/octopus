#!/usr/bin/env python3
"""
Populate Applicants MongoDB Collection (Enhanced Version)

This script uses the SAME matching logic as match_csv_to_residence_enhanced.py
to achieve 97%+ match rates.

Based on enhanced matching documented in:
.claude_docs/20251104_1535_Enhanced_Matching_Results.md

Usage:
    source venv/bin/activate
    python scripts/populate_applicants_db_v2.py
"""
import os
import sys
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

from src.models.applicant import Applicant

load_dotenv()

CSV_FILE = Path(__file__).parent.parent / 'data' / 'APPLICANTS_sign-up-today-2025-09-03.csv'
ZIPCODE_COUNTY_MAP = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'


class AddressNormalizer:
    """Enhanced address normalization (from match_csv_to_residence_enhanced.py)"""

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
        """Normalize state route addresses to multiple variations"""
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
        """Generate variations for hyphenated road names"""
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
        """Match first/last name against full name"""
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


class EnhancedMatcher:
    """Enhanced matching logic with all 8 strategies"""

    def __init__(self, mongo_client: MongoClient, database_name: str):
        self.client = mongo_client
        self.db = mongo_client[database_name]
        self.zipcode_map = self._load_zipcode_map()

    def _load_zipcode_map(self) -> Dict[str, str]:
        """Load ZIP code to county mapping"""
        if ZIPCODE_COUNTY_MAP.exists():
            with open(ZIPCODE_COUNTY_MAP, 'r') as f:
                data = json.load(f)
                # Handle nested structure if present
                if 'zipcode_map' in data:
                    return data['zipcode_map']
                return data
        return {}

    def _get_county_from_zip(self, zip_code: str) -> Optional[str]:
        """Get county name from ZIP code"""
        zip5 = zip_code[:5] if len(zip_code) >= 5 else zip_code
        county = self.zipcode_map.get(zip5)
        if county:
            # Remove 'County' suffix if present (both spaced and concatenated forms)
            county = county.replace(' County', '').replace(' county', '').replace('County', '')
        return county

    def match_applicant(self, csv_row: Dict) -> Dict:
        """
        Match applicant using all 8 strategies in priority order

        Strategy Priority (from match_csv_to_residence_enhanced.py):
        1. Email (demographic)
        2. Name (demographic)
        3. Phone (demographic)
        4. Exact address (residential)
        5. Normalized address (residential)
        6. State route variations (residential)
        7. Hyphenated road variations (residential)
        8. Fuzzy address (residential)
        """
        # Extract data
        email = csv_row.get('Email', '')
        first_name = csv_row.get('Name (First)', '')
        last_name = csv_row.get('Name (Last)', '')
        phone = csv_row.get('Phone', '')
        address = (csv_row.get('Address (Street Address)', '') or
                  csv_row.get('City (Street Address)', '') or
                  csv_row.get('State (Street Address)', '') or
                  csv_row.get('Zip (Street Address)', ''))
        zip_code = (csv_row.get('Address (ZIP / Postal Code)', '') or
                   csv_row.get('City (ZIP / Postal Code)', '') or
                   csv_row.get('State (ZIP / Postal Code)', '') or
                   csv_row.get('Zip (ZIP / Postal Code)', ''))

        # Get county - prioritize CSV County field, fallback to ZIP mapping
        county = csv_row.get('County', '')
        if county:
            county = county.strip()
        else:
            county = self._get_county_from_zip(zip_code)

        if not county:
            return {
                'match_quality': 'no_match',
                'match_method': None,
                'match_details': 'Could not determine county from ZIP code',
                'county': None,
                'residence_record': None,
                'demographic_record': None
            }

        demographic_coll_name = f"{county}CountyDemographic"
        residence_coll_name = f"{county}CountyResidential"

        # Strategy 1: Email match
        if email and demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_email(demographic_coll_name, residence_coll_name, email)
            if result:
                result['county'] = county
                return result

        # Strategy 2: Name match
        if first_name and last_name and demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_name(demographic_coll_name, residence_coll_name,
                                        first_name, last_name, zip_code)
            if result:
                result['county'] = county
                return result

        # Strategy 3: Phone match
        if phone and demographic_coll_name in self.db.list_collection_names():
            result = self._match_by_phone(demographic_coll_name, residence_coll_name, phone)
            if result:
                result['county'] = county
                return result

        # Strategies 4-8: Address matching (if residence collection exists)
        if residence_coll_name not in self.db.list_collection_names():
            return {
                'match_quality': 'no_match',
                'match_method': None,
                'match_details': f'Collection {residence_coll_name} not found',
                'county': county,
                'residence_record': None,
                'demographic_record': None
            }

        if address:
            # Strategy 4: Exact address
            result = self._match_by_address_exact(residence_coll_name, demographic_coll_name,
                                                   address, zip_code)
            if result:
                result['county'] = county
                return result

            # Strategy 5: Normalized address
            result = self._match_by_address_normalized(residence_coll_name, demographic_coll_name,
                                                        address, zip_code)
            if result:
                result['county'] = county
                return result

            # Strategy 6: State route variations
            if re.search(r'(OH|US|SR)[-\s]\d+', address, re.IGNORECASE):
                result = self._match_state_route(residence_coll_name, demographic_coll_name, address)
                if result:
                    result['county'] = county
                    return result

            # Strategy 7: Hyphenated road variations
            if '-' in address:
                result = self._match_hyphenated(residence_coll_name, demographic_coll_name, address)
                if result:
                    result['county'] = county
                    return result

            # Strategy 8: Fuzzy address
            result = self._match_fuzzy_address(residence_coll_name, demographic_coll_name,
                                                address, zip_code)
            if result:
                result['county'] = county
                return result

        # No match found
        collection_exists = demographic_coll_name in self.db.list_collection_names()
        return {
            'match_quality': 'no_match',
            'match_method': None,
            'match_details': f'No match found. Collection exists: {collection_exists}',
            'county': county,
            'residence_record': None,
            'demographic_record': None
        }

    def _match_by_email(self, demo_coll: str, res_coll: str, email: str) -> Optional[Dict]:
        """Strategy 1: Email match"""
        collection = self.db[demo_coll]
        doc = collection.find_one({'email': email.lower()})

        if doc:
            # Get residence record
            residence_doc = None
            if res_coll in self.db.list_collection_names():
                residence_doc = self.db[res_coll].find_one({'parcel_id': doc.get('parcel_id')})

            return {
                'match_quality': 'demographic',
                'match_method': 'email',
                'match_details': f'Email match: {email}',
                'demographic_record': doc,
                'residence_record': residence_doc
            }

        return None

    def _match_by_name(self, demo_coll: str, res_coll: str,
                       first: str, last: str, zip_code: str) -> Optional[Dict]:
        """Strategy 2: Name match"""
        collection = self.db[demo_coll]

        # Get candidates from same ZIP if available
        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
            except ValueError:
                pass

        for doc in collection.find(query):
            customer_name = doc.get('customer_name', '')
            is_match, match_type = NameMatcher.match(first, last, customer_name)

            if is_match:
                # Get residence record
                residence_doc = None
                if res_coll in self.db.list_collection_names():
                    residence_doc = self.db[res_coll].find_one({'parcel_id': doc.get('parcel_id')})

                return {
                    'match_quality': 'demographic',
                    'match_method': f'name_{match_type}',
                    'match_details': f'Name match ({match_type}): {first} {last} → {customer_name}',
                    'demographic_record': doc,
                    'residence_record': residence_doc
                }

        return None

    def _match_by_phone(self, demo_coll: str, res_coll: str, phone: str) -> Optional[Dict]:
        """Strategy 3: Phone match"""
        collection = self.db[demo_coll]
        norm_phone = PhoneNormalizer.normalize(phone)

        if not norm_phone:
            return None

        for doc in collection.find():
            db_phone = str(doc.get('mobile', ''))
            if PhoneNormalizer.match(phone, db_phone):
                # Get residence record
                residence_doc = None
                if res_coll in self.db.list_collection_names():
                    residence_doc = self.db[res_coll].find_one({'parcel_id': doc.get('parcel_id')})

                return {
                    'match_quality': 'demographic',
                    'match_method': 'phone',
                    'match_details': f'Phone match: {phone}',
                    'demographic_record': doc,
                    'residence_record': residence_doc
                }

        return None

    def _match_by_address_exact(self, res_coll: str, demo_coll: str,
                                 address: str, zip_code: str) -> Optional[Dict]:
        """Strategy 4: Exact address match"""
        collection = self.db[res_coll]

        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            db_address = record.get('address', '')
            if address == db_address:
                # Get demographic record
                demo_doc = None
                if demo_coll in self.db.list_collection_names():
                    demo_doc = self.db[demo_coll].find_one({'parcel_id': record.get('parcel_id')})

                return {
                    'match_quality': 'exact',
                    'match_method': 'address_exact',
                    'match_details': f'Exact: {address}',
                    'residence_record': record,
                    'demographic_record': demo_doc
                }

        return None

    def _match_by_address_normalized(self, res_coll: str, demo_coll: str,
                                      address: str, zip_code: str) -> Optional[Dict]:
        """Strategy 5: Normalized address match"""
        collection = self.db[res_coll]

        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            db_address = record.get('address', '')
            if AddressNormalizer.exact_match(address, db_address):
                # Get demographic record
                demo_doc = None
                if demo_coll in self.db.list_collection_names():
                    demo_doc = self.db[demo_coll].find_one({'parcel_id': record.get('parcel_id')})

                return {
                    'match_quality': 'good',
                    'match_method': 'address_normalized',
                    'match_details': f'Normalized: \'{address}\' → \'{db_address}\'',
                    'residence_record': record,
                    'demographic_record': demo_doc
                }

        return None

    def _match_state_route(self, res_coll: str, demo_coll: str, address: str) -> Optional[Dict]:
        """Strategy 6: State route variations"""
        collection = self.db[res_coll]
        variations = AddressNormalizer.normalize_state_route(address)

        for var in variations:
            norm_var = AddressNormalizer.normalize(var)
            for record in collection.find():
                db_addr = AddressNormalizer.normalize(record.get('address', ''))
                if norm_var in db_addr or db_addr in norm_var:
                    # Get demographic record
                    demo_doc = None
                    if demo_coll in self.db.list_collection_names():
                        demo_doc = self.db[demo_coll].find_one({'parcel_id': record.get('parcel_id')})

                    return {
                        'match_quality': 'good',
                        'match_method': 'state_route',
                        'match_details': f'State route: \'{address}\' → \'{record.get("address")}\' (variation: {var})',
                        'residence_record': record,
                        'demographic_record': demo_doc
                    }

        return None

    def _match_hyphenated(self, res_coll: str, demo_coll: str, address: str) -> Optional[Dict]:
        """Strategy 7: Hyphenated road variations"""
        collection = self.db[res_coll]
        variations = AddressNormalizer.normalize_hyphenated(address)

        for var in variations:
            norm_var = AddressNormalizer.normalize(var)
            for record in collection.find():
                db_addr = AddressNormalizer.normalize(record.get('address', ''))
                if norm_var == db_addr or (len(norm_var) > 5 and norm_var in db_addr):
                    # Get demographic record
                    demo_doc = None
                    if demo_coll in self.db.list_collection_names():
                        demo_doc = self.db[demo_coll].find_one({'parcel_id': record.get('parcel_id')})

                    return {
                        'match_quality': 'good',
                        'match_method': 'hyphenated',
                        'match_details': f'Hyphenated: \'{address}\' → \'{record.get("address")}\' (variation: {var})',
                        'residence_record': record,
                        'demographic_record': demo_doc
                    }

        return None

    def _match_fuzzy_address(self, res_coll: str, demo_coll: str,
                             address: str, zip_code: str) -> Optional[Dict]:
        """Strategy 8: Fuzzy address match"""
        collection = self.db[res_coll]

        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
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
            # Get demographic record
            demo_doc = None
            if demo_coll in self.db.list_collection_names():
                demo_doc = self.db[demo_coll].find_one({'parcel_id': best_match.get('parcel_id')})

            return {
                'match_quality': 'fuzzy',
                'match_method': 'fuzzy_address',
                'match_details': f'Fuzzy match (score: {best_score:.2f}): \'{address}\' ~= \'{best_match.get("address")}\'',
                'residence_record': best_match,
                'demographic_record': demo_doc
            }

        return None


def main():
    """Main execution function"""
    # Connect to MongoDB (use remote instance for residence matching data)
    mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
    mongo_port = os.getenv('MONGODB_PORT_RM', '27017')
    mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

    mongo_uri = f'mongodb://{mongo_host}:{mongo_port}/'
    client = MongoClient(mongo_uri)
    db = client[mongo_db]

    # Initialize matcher
    matcher = EnhancedMatcher(client, mongo_db)

    # Read CSV
    if not CSV_FILE.exists():
        print(f"❌ CSV file not found: {CSV_FILE}")
        return

    print(f"📄 Reading CSV: {CSV_FILE}")
    print(f"🔗 MongoDB URI: {mongo_uri}")
    print()

    # Process applicants
    applicants_collection = db['applicants']
    processed = 0
    inserted = 0
    updated = 0
    errors = 0

    match_stats = {
        'email': 0,
        'name_exact': 0,
        'name_fuzzy': 0,
        'phone': 0,
        'address_exact': 0,
        'address_normalized': 0,
        'state_route': 0,
        'hyphenated': 0,
        'fuzzy_address': 0,
        'no_match': 0
    }

    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            processed += 1
            entry_id = row.get('Entry Id', '')

            try:
                # Match applicant
                match_result = matcher.match_applicant(row)

                # Create applicant model
                applicant = Applicant.from_csv_and_match(row, match_result)

                # Update statistics
                method = match_result.get('match_method', 'no_match')
                if method is None:
                    method = 'no_match'
                match_stats[method] = match_stats.get(method, 0) + 1

                # Insert or update in database
                result = applicants_collection.update_one(
                    {'entry_id': entry_id},
                    {'$set': applicant.to_mongo_dict()},
                    upsert=True
                )

                if result.upserted_id:
                    inserted += 1
                elif result.modified_count > 0:
                    updated += 1

                # Progress indicator
                if processed % 10 == 0:
                    print(f"✓ Processed {processed} applicants...", end='\r')

            except Exception as e:
                errors += 1
                print(f"\n❌ Error processing entry {entry_id}: {e}")

    # Calculate totals
    total_demographic = (match_stats.get('email', 0) +
                        match_stats.get('name_exact', 0) +
                        match_stats.get('name_fuzzy', 0) +
                        match_stats.get('phone', 0))

    total_address = (match_stats.get('address_exact', 0) +
                    match_stats.get('address_normalized', 0) +
                    match_stats.get('state_route', 0) +
                    match_stats.get('hyphenated', 0) +
                    match_stats.get('fuzzy_address', 0))

    total_matched = total_demographic + total_address

    print(f"\n\n{'='*60}")
    print(f"✅ Processing Complete!")
    print(f"{'='*60}")
    print(f"Total processed: {processed}")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Errors: {errors}")
    print()
    print(f"Match Statistics:")
    print(f"  DEMOGRAPHIC MATCHES:")
    print(f"    Email: {match_stats.get('email', 0)} ({match_stats.get('email', 0)/processed*100:.1f}%)")
    print(f"    Name (exact): {match_stats.get('name_exact', 0)} ({match_stats.get('name_exact', 0)/processed*100:.1f}%)")
    print(f"    Name (fuzzy): {match_stats.get('name_fuzzy', 0)} ({match_stats.get('name_fuzzy', 0)/processed*100:.1f}%)")
    print(f"    Phone: {match_stats.get('phone', 0)} ({match_stats.get('phone', 0)/processed*100:.1f}%)")
    print(f"  DEMOGRAPHIC TOTAL: {total_demographic} ({total_demographic/processed*100:.1f}%)")
    print()
    print(f"  ADDRESS MATCHES:")
    print(f"    Exact: {match_stats.get('address_exact', 0)} ({match_stats.get('address_exact', 0)/processed*100:.1f}%)")
    print(f"    Normalized: {match_stats.get('address_normalized', 0)} ({match_stats.get('address_normalized', 0)/processed*100:.1f}%)")
    print(f"    State route: {match_stats.get('state_route', 0)} ({match_stats.get('state_route', 0)/processed*100:.1f}%)")
    print(f"    Hyphenated: {match_stats.get('hyphenated', 0)} ({match_stats.get('hyphenated', 0)/processed*100:.1f}%)")
    print(f"    Fuzzy: {match_stats.get('fuzzy_address', 0)} ({match_stats.get('fuzzy_address', 0)/processed*100:.1f}%)")
    print(f"  ADDRESS TOTAL: {total_address} ({total_address/processed*100:.1f}%)")
    print()
    print(f"  No match: {match_stats.get('no_match', 0)} ({match_stats.get('no_match', 0)/processed*100:.1f}%)")
    print()

    match_rate = (total_matched / processed * 100) if processed > 0 else 0
    print(f"📊 Overall match rate: {match_rate:.1f}% ({total_matched}/{processed})")
    print()


if __name__ == '__main__':
    main()
