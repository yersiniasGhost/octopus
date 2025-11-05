#!/usr/bin/env python3
"""
Match CSV applicants to MongoDB Residence records

This script:
1. Loads CSV file: data/APPLICANTS_sign-up-today-2025-09-03.csv
2. Maps zipcodes to counties using: data/zipcode_to_county_cache.json
3. Searches {County}CountyResidential MongoDB collections for matching records
4. Provides detailed results with match statistics

Usage:
    source venv/bin/activate
    python scripts/match_csv_to_residence.py
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

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# File paths
CSV_FILE = Path(__file__).parent.parent / 'data' / 'APPLICANTS_sign-up-today-2025-09-03.csv'
ZIPCODE_COUNTY_MAP = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'


class MatchQuality(Enum):
    """Match quality levels"""
    EXACT = "exact"           # Exact match on address
    GOOD = "good"             # Good match with normalized address
    FUZZY = "fuzzy"           # Fuzzy match (partial address)
    NO_MATCH = "no_match"     # No match found


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
    """Result of matching an applicant to residence"""
    applicant: ApplicantRecord
    match_quality: MatchQuality
    residence_record: Optional[Dict] = None
    match_method: Optional[str] = None
    match_details: str = ""


class AddressNormalizer:
    """Normalize addresses for matching"""

    STREET_ABBREV = {
        'street': 'st', 'avenue': 'ave', 'road': 'rd', 'drive': 'dr',
        'lane': 'ln', 'court': 'ct', 'circle': 'cir', 'boulevard': 'blvd',
        'parkway': 'pkwy', 'place': 'pl', 'terrace': 'ter', 'way': 'way',
    }

    DIRECTIONAL_ABBREV = {
        'north': 'n', 'south': 's', 'east': 'e', 'west': 'w',
        'northeast': 'ne', 'northwest': 'nw', 'southeast': 'se', 'southwest': 'sw',
    }

    @classmethod
    def normalize(cls, address: str) -> str:
        """Normalize address for matching"""
        if not address:
            return ""

        addr = address.lower().strip()
        addr = re.sub(r'[,.]', '', addr)  # Remove punctuation

        # Normalize street types
        for full, abbrev in cls.STREET_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        # Normalize directionals
        for full, abbrev in cls.DIRECTIONAL_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        addr = re.sub(r'\s+', ' ', addr)  # Collapse spaces
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


class ResidenceMatcher:
    """Match CSV applicants to MongoDB Residence records"""

    def __init__(self):
        """Initialize MongoDB connection and load zipcode mapping"""
        # MongoDB connection to residence data
        self.mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        print(f"Connecting to MongoDB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db}")
        self.client = MongoClient(self.mongo_host, self.mongo_port)
        self.db = self.client[self.mongo_db]

        # Load zipcode to county mapping
        print(f"Loading zipcode mapping from: {ZIPCODE_COUNTY_MAP}")
        with open(ZIPCODE_COUNTY_MAP, 'r') as f:
            data = json.load(f)
            self.zipcode_map = data.get('zipcode_map', {})

        # Statistics
        self.stats = {
            'total_applicants': 0,
            'exact_matches': 0,
            'good_matches': 0,
            'fuzzy_matches': 0,
            'no_matches': 0,
            'county_not_found': 0,
            'collection_not_found': 0,
        }

    def load_applicants(self) -> List[ApplicantRecord]:
        """Load applicants from CSV file"""
        print(f"\nLoading applicants from: {CSV_FILE}")
        applicants = []

        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                applicant = ApplicantRecord.from_csv_row(row)
                applicants.append(applicant)

        self.stats['total_applicants'] = len(applicants)
        print(f"Loaded {len(applicants)} applicants from CSV")
        return applicants

    def get_county_from_zipcode(self, zipcode: str) -> Optional[str]:
        """Map zipcode to county name"""
        if not zipcode:
            return None

        # Clean zipcode (remove spaces, take first 5 digits)
        clean_zip = re.sub(r'\D', '', zipcode)[:5]

        county = self.zipcode_map.get(clean_zip)
        return county

    def get_residence_collection_name(self, county: str) -> str:
        """Get MongoDB collection name for county residence data"""
        # Format: {County}CountyResidential (e.g., FranklinCountyResidential)
        # Note: county already contains "County" suffix from zipcode_to_county_cache.json
        # So we just need to append "Residential"
        return f"{county}Residential"

    def match_applicant(self, applicant: ApplicantRecord) -> MatchResult:
        """Match a single applicant to residence record"""

        # Determine county from CSV or zipcode mapping
        county = applicant.county
        if county:
            # CSV county is just "Harrison", need to add "County" suffix
            county = f"{county}County"
        elif applicant.zip_code:
            # Zipcode mapping already includes "County" suffix
            county = self.get_county_from_zipcode(applicant.zip_code)

        if not county:
            self.stats['county_not_found'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.NO_MATCH,
                match_details="County not found (no zipcode or county in CSV)"
            )

        # Get collection name
        collection_name = self.get_residence_collection_name(county)

        # Check if collection exists
        if collection_name not in self.db.list_collection_names():
            self.stats['collection_not_found'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.NO_MATCH,
                match_details=f"Collection '{collection_name}' not found in database"
            )

        collection = self.db[collection_name]

        # Strategy 1: Exact address match
        if applicant.address:
            result = self._match_by_address(collection, applicant, exact=True)
            if result:
                self.stats['exact_matches'] += 1
                return result

        # Strategy 2: Normalized address match
        if applicant.address:
            result = self._match_by_address(collection, applicant, exact=False)
            if result:
                self.stats['good_matches'] += 1
                return result

        # Strategy 3: Fuzzy address match
        if applicant.address:
            result = self._fuzzy_match_by_address(collection, applicant)
            if result:
                self.stats['fuzzy_matches'] += 1
                return result

        # No match found
        self.stats['no_matches'] += 1
        return MatchResult(
            applicant=applicant,
            match_quality=MatchQuality.NO_MATCH,
            match_details=f"No matching residence found in {collection_name}"
        )

    def _match_by_address(self, collection, applicant: ApplicantRecord, exact: bool = True) -> Optional[MatchResult]:
        """Match by address (exact or normalized)"""

        # Query all records (we'll filter in Python for flexibility)
        query = {}
        if applicant.zip_code:
            try:
                # Try to filter by zipcode if available
                query['parcel_zip'] = int(applicant.zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            db_address = record.get('address', '')

            if exact:
                # Exact string match
                if applicant.address == db_address:
                    return MatchResult(
                        applicant=applicant,
                        match_quality=MatchQuality.EXACT,
                        residence_record=record,
                        match_method='exact_address',
                        match_details=f"Exact address match: {applicant.address}"
                    )
            else:
                # Normalized match
                if AddressNormalizer.exact_match(applicant.address, db_address):
                    return MatchResult(
                        applicant=applicant,
                        match_quality=MatchQuality.GOOD,
                        residence_record=record,
                        match_method='normalized_address',
                        match_details=f"Normalized match: '{applicant.address}' -> '{db_address}'"
                    )

        return None

    def _fuzzy_match_by_address(self, collection, applicant: ApplicantRecord) -> Optional[MatchResult]:
        """Fuzzy match by address"""

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
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.FUZZY,
                residence_record=best_match,
                match_method='fuzzy_address',
                match_details=f"Fuzzy match (score: {best_score:.2f}): '{applicant.address}' ~= '{best_match.get('address', '')}'"
            )

        return None

    def run_matching(self) -> List[MatchResult]:
        """Run matching process for all applicants"""
        print("\n" + "="*80)
        print("STARTING RESIDENCE MATCHING PROCESS")
        print("="*80)

        applicants = self.load_applicants()
        results = []

        for i, applicant in enumerate(applicants, 1):
            if i % 10 == 0:
                print(f"Processing applicant {i}/{len(applicants)}...")

            result = self.match_applicant(applicant)
            results.append(result)

        return results

    def print_detailed_results(self, results: List[MatchResult]):
        """Print detailed results"""
        print("\n" + "="*80)
        print("DETAILED MATCH RESULTS")
        print("="*80)

        # Group by match quality
        exact = [r for r in results if r.match_quality == MatchQuality.EXACT]
        good = [r for r in results if r.match_quality == MatchQuality.GOOD]
        fuzzy = [r for r in results if r.match_quality == MatchQuality.FUZZY]
        no_match = [r for r in results if r.match_quality == MatchQuality.NO_MATCH]

        # Print exact matches
        if exact:
            print(f"\n{'='*80}")
            print(f"EXACT MATCHES ({len(exact)})")
            print(f"{'='*80}")
            for r in exact[:10]:  # Show first 10
                print(f"\nEntry ID: {r.applicant.entry_id}")
                print(f"  Applicant: {r.applicant.first_name} {r.applicant.last_name}")
                print(f"  Address: {r.applicant.address}, {r.applicant.city}, {r.applicant.zip_code}")
                print(f"  County: {r.applicant.county}")
                print(f"  Match: {r.match_details}")
                if r.residence_record:
                    print(f"  Residence ID: {r.residence_record.get('_id')}")
                    print(f"  Residence Fields: {list(r.residence_record.keys())[:10]}...")

        # Print good matches
        if good:
            print(f"\n{'='*80}")
            print(f"GOOD MATCHES (Normalized) ({len(good)})")
            print(f"{'='*80}")
            for r in good[:10]:  # Show first 10
                print(f"\nEntry ID: {r.applicant.entry_id}")
                print(f"  Applicant: {r.applicant.first_name} {r.applicant.last_name}")
                print(f"  Address: {r.applicant.address}, {r.applicant.city}, {r.applicant.zip_code}")
                print(f"  Match: {r.match_details}")

        # Print fuzzy matches
        if fuzzy:
            print(f"\n{'='*80}")
            print(f"FUZZY MATCHES ({len(fuzzy)})")
            print(f"{'='*80}")
            for r in fuzzy[:10]:  # Show first 10
                print(f"\nEntry ID: {r.applicant.entry_id}")
                print(f"  Applicant: {r.applicant.first_name} {r.applicant.last_name}")
                print(f"  Address: {r.applicant.address}, {r.applicant.city}, {r.applicant.zip_code}")
                print(f"  Match: {r.match_details}")

        # Print no matches sample
        if no_match:
            print(f"\n{'='*80}")
            print(f"NO MATCHES ({len(no_match)})")
            print(f"{'='*80}")
            for r in no_match[:5]:  # Show first 5
                print(f"\nEntry ID: {r.applicant.entry_id}")
                print(f"  Applicant: {r.applicant.first_name} {r.applicant.last_name}")
                print(f"  Address: {r.applicant.address}, {r.applicant.city}, {r.applicant.zip_code}")
                print(f"  Reason: {r.match_details}")

    def print_statistics(self):
        """Print matching statistics"""
        print("\n" + "="*80)
        print("MATCHING STATISTICS")
        print("="*80)
        total = self.stats['total_applicants']

        print(f"\nTotal Applicants:       {total}")
        print(f"Exact Matches:          {self.stats['exact_matches']:4d} ({self._pct('exact_matches')}%)")
        print(f"Good Matches:           {self.stats['good_matches']:4d} ({self._pct('good_matches')}%)")
        print(f"Fuzzy Matches:          {self.stats['fuzzy_matches']:4d} ({self._pct('fuzzy_matches')}%)")
        print(f"No Matches:             {self.stats['no_matches']:4d} ({self._pct('no_matches')}%)")
        print(f"\nIssues:")
        print(f"County Not Found:       {self.stats['county_not_found']:4d} ({self._pct('county_not_found')}%)")
        print(f"Collection Not Found:   {self.stats['collection_not_found']:4d} ({self._pct('collection_not_found')}%)")

        total_matched = self.stats['exact_matches'] + self.stats['good_matches'] + self.stats['fuzzy_matches']
        print(f"\nTotal Matched:          {total_matched:4d} ({total_matched/total*100:.1f}%)")
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

    matcher = ResidenceMatcher()

    try:
        # Run matching
        results = matcher.run_matching()

        # Print detailed results
        matcher.print_detailed_results(results)

        # Print statistics
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
