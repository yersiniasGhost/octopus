#!/usr/bin/env python3
"""
Match CSV applicants to MongoDB Residence records using comprehensive 8-strategy matcher

This script:
1. Loads CSV file: data/APPLICANTS_sign-up-today-2025-09-03.csv
2. Maps zipcodes to counties using: data/zipcode_to_county_cache.json
3. Uses ResidenceMatcher with 8 strategies:
   - Email matching (Demographic)
   - Name matching (Demographic) - Fuzzy name logic
   - Phone matching (Demographic)
   - Exact address (Residential)
   - Normalized address (Residential)
   - State route variations (OH-314, US-40)
   - Hyphenated road variations
   - Fuzzy address (Residential)

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
from src.tools.residence_matcher import ResidenceMatcher as ComprehensiveResidenceMatcher, MatchQuality as RMMatchQuality

# Load environment variables
load_dotenv()

# File paths
CSV_FILE = Path(__file__).parent.parent / 'data' / 'APPLICANTS_sign-up-today-2025-09-03.csv'
ZIPCODE_COUNTY_MAP = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'


class MatchQuality(Enum):
    """Match quality levels"""
    EXACT = "exact"           # Exact match
    GOOD = "good"             # Good match (email, name, normalized address)
    FUZZY = "fuzzy"           # Fuzzy match (partial address)
    DEMOGRAPHIC = "demographic"  # Matched via demographic data (email/name/phone)
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
            'demographic_matches': 0,  # Email, name, or phone matches
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
        """Match a single applicant to residence record using comprehensive 8-strategy matcher"""

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

        # Check if collections exist
        collection_name = self.get_residence_collection_name(county)
        if collection_name not in self.db.list_collection_names():
            self.stats['collection_not_found'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.NO_MATCH,
                match_details=f"Collection '{collection_name}' not found in database"
            )

        # Use comprehensive ResidenceMatcher with 8 strategies:
        # 1. Email matching (Demographic)
        # 2. Name matching (Demographic) - Fuzzy name logic
        # 3. Phone matching (Demographic)
        # 4. Exact address (Residential)
        # 5. Normalized address (Residential)
        # 6. State route variations (OH-314, US-40)
        # 7. Hyphenated road variations
        # 8. Fuzzy address (Residential)

        matcher = ComprehensiveResidenceMatcher(self.db, county)
        residence_ref, demographic_ref, match_method = matcher.match(
            phone=applicant.phone,
            email=applicant.email,
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            address=applicant.address,
            zipcode=applicant.zip_code
        )

        # Determine match quality based on method
        if not residence_ref and not demographic_ref:
            self.stats['no_matches'] += 1
            return MatchResult(
                applicant=applicant,
                match_quality=MatchQuality.NO_MATCH,
                match_details=f"No match found using any of the 8 strategies (method: {match_method})"
            )

        # Map match method to quality category
        match_quality = MatchQuality.GOOD
        if 'email' in match_method or 'name' in match_method or 'phone' in match_method:
            match_quality = MatchQuality.DEMOGRAPHIC
            self.stats['demographic_matches'] += 1
        elif 'exact' in match_method:
            match_quality = MatchQuality.EXACT
            self.stats['exact_matches'] += 1
        elif 'fuzzy' in match_method:
            match_quality = MatchQuality.FUZZY
            self.stats['fuzzy_matches'] += 1
        else:
            self.stats['good_matches'] += 1

        # Build residence record from reference
        residence_record = None
        if residence_ref:
            residence_record = {
                'parcel_id': residence_ref.parcel_id,
                'address': residence_ref.address,
                'parcel_zip': residence_ref.parcel_zip
            }

        return MatchResult(
            applicant=applicant,
            match_quality=match_quality,
            residence_record=residence_record,
            match_method=match_method,
            match_details=f"Matched via {match_method}" +
                         (f" to demographic: {demographic_ref.customer_name}" if demographic_ref else "") +
                         (f" at {residence_ref.address}" if residence_ref else "")
        )


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
        demographic = [r for r in results if r.match_quality == MatchQuality.DEMOGRAPHIC]
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

        # Print demographic matches (email/name/phone)
        if demographic:
            print(f"\n{'='*80}")
            print(f"DEMOGRAPHIC MATCHES (Email/Name/Phone) ({len(demographic)})")
            print(f"{'='*80}")
            for r in demographic[:10]:  # Show first 10
                print(f"\nEntry ID: {r.applicant.entry_id}")
                print(f"  Applicant: {r.applicant.first_name} {r.applicant.last_name}")
                print(f"  Email: {r.applicant.email}")
                print(f"  Phone: {r.applicant.phone}")
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

        print(f"\nTotal Applicants:         {total}")
        print(f"Exact Matches:            {self.stats['exact_matches']:4d} ({self._pct('exact_matches')}%)")
        print(f"Good Matches:             {self.stats['good_matches']:4d} ({self._pct('good_matches')}%)")
        print(f"Fuzzy Matches:            {self.stats['fuzzy_matches']:4d} ({self._pct('fuzzy_matches')}%)")
        print(f"Demographic Matches:      {self.stats['demographic_matches']:4d} ({self._pct('demographic_matches')}%)")
        print(f"  (Email/Name/Phone)")
        print(f"No Matches:               {self.stats['no_matches']:4d} ({self._pct('no_matches')}%)")
        print(f"\nIssues:")
        print(f"County Not Found:         {self.stats['county_not_found']:4d} ({self._pct('county_not_found')}%)")
        print(f"Collection Not Found:     {self.stats['collection_not_found']:4d} ({self._pct('collection_not_found')}%)")

        total_matched = self.stats['exact_matches'] + self.stats['good_matches'] + self.stats['fuzzy_matches'] + self.stats['demographic_matches']
        print(f"\nTotal Matched:            {total_matched:4d} ({total_matched/total*100:.1f}%)")
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
