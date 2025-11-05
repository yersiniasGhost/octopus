#!/usr/bin/env python3
"""
Populate Applicants MongoDB Collection

This script reads the CSV file of applicants, performs enhanced matching
against county demographic and residential databases, and stores the results
in the 'applicants' collection.

Based on the enhanced matching strategy documented in:
.claude_docs/20251104_1535_Enhanced_Matching_Results.md

Usage:
    source venv/bin/activate
    python scripts/populate_applicants_db.py
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


class EnhancedMatcher:
    """Enhanced matching logic for applicants to county databases"""

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

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to 10 digits"""
        if not phone:
            return ""
        # Remove all non-numeric characters
        digits = re.sub(r'\D', '', phone)
        # Return last 10 digits if longer
        return digits[-10:] if len(digits) >= 10 else digits

    def _normalize_email(self, email: str) -> str:
        """Normalize email to lowercase"""
        return email.lower().strip() if email else ""

    def _match_by_email(self, email: str, county: str) -> Optional[Dict]:
        """Match applicant by email in demographic collection"""
        if not email or not county:
            return None

        collection_name = f"{county}CountyDemographic"
        if collection_name not in self.db.list_collection_names():
            return None

        collection = self.db[collection_name]
        email_normalized = self._normalize_email(email)

        # Try to find by email
        result = collection.find_one({"email": email_normalized})
        if result:
            return {
                'match_quality': 'demographic',
                'match_method': 'email',
                'match_details': f'Email match in {collection_name}',
                'demographic_record': result,
                'residence_record': self._get_residence_by_parcel(county, result.get('parcel_id')),
                'county': county
            }
        return None

    def _match_by_name(self, first_name: str, last_name: str, county: str, zip_code: str) -> Optional[Dict]:
        """Match applicant by name in demographic collection"""
        if not first_name or not last_name or not county:
            return None

        collection_name = f"{county}CountyDemographic"
        if collection_name not in self.db.list_collection_names():
            return None

        collection = self.db[collection_name]
        full_name = f"{first_name.upper()} {last_name.upper()}"

        # Try exact name match with ZIP filter
        query = {"customer_name": full_name}
        if zip_code:
            zip_int = int(zip_code[:5]) if zip_code else None
            if zip_int:
                query["parcel_zip"] = zip_int

        result = collection.find_one(query)
        if result:
            return {
                'match_quality': 'demographic',
                'match_method': 'name',
                'match_details': f'Name match in {collection_name}',
                'demographic_record': result,
                'residence_record': self._get_residence_by_parcel(county, result.get('parcel_id')),
                'county': county
            }

        # Try without ZIP filter
        result = collection.find_one({"customer_name": full_name})
        if result:
            return {
                'match_quality': 'demographic',
                'match_method': 'name',
                'match_details': f'Name match (no ZIP) in {collection_name}',
                'demographic_record': result,
                'residence_record': self._get_residence_by_parcel(county, result.get('parcel_id')),
                'county': county
            }

        return None

    def _match_by_phone(self, phone: str, county: str) -> Optional[Dict]:
        """Match applicant by phone number in demographic collection"""
        if not phone or not county:
            return None

        collection_name = f"{county}CountyDemographic"
        if collection_name not in self.db.list_collection_names():
            return None

        collection = self.db[collection_name]
        phone_normalized = self._normalize_phone(phone)

        if not phone_normalized:
            return None

        # Try to find by mobile
        result = collection.find_one({"mobile": phone_normalized})
        if result:
            return {
                'match_quality': 'demographic',
                'match_method': 'phone',
                'match_details': f'Phone match in {collection_name}',
                'demographic_record': result,
                'residence_record': self._get_residence_by_parcel(county, result.get('parcel_id')),
                'county': county
            }
        return None

    def _normalize_address(self, address: str) -> str:
        """Normalize address for matching"""
        if not address:
            return ""

        addr = address.upper().strip()
        # Remove punctuation
        addr = re.sub(r'[.,#]', '', addr)
        # Normalize whitespace
        addr = ' '.join(addr.split())

        # Common abbreviations
        replacements = {
            ' STREET': ' ST',
            ' AVENUE': ' AVE',
            ' ROAD': ' RD',
            ' DRIVE': ' DR',
            ' LANE': ' LN',
            ' COURT': ' CT',
            ' CIRCLE': ' CIR',
            ' BOULEVARD': ' BLVD',
            ' PARKWAY': ' PKWY',
        }

        for old, new in replacements.items():
            addr = addr.replace(old, new)

        return addr

    def _match_by_address(self, address: str, county: str) -> Optional[Dict]:
        """Match applicant by address in residential collection"""
        if not address or not county:
            return None

        collection_name = f"{county}CountyResidential"
        if collection_name not in self.db.list_collection_names():
            return None

        collection = self.db[collection_name]
        addr_normalized = self._normalize_address(address)

        # Try exact match
        result = collection.find_one({"address": addr_normalized})
        if result:
            return {
                'match_quality': 'good',
                'match_method': 'address_normalized',
                'match_details': f'Address match in {collection_name}',
                'residence_record': result,
                'demographic_record': self._get_demographic_by_parcel(county, result.get('parcel_id')),
                'county': county
            }

        return None

    def _get_residence_by_parcel(self, county: str, parcel_id: str) -> Optional[Dict]:
        """Get residence record by parcel ID"""
        if not county or not parcel_id:
            return None

        collection_name = f"{county}CountyResidential"
        if collection_name not in self.db.list_collection_names():
            return None

        return self.db[collection_name].find_one({"parcel_id": parcel_id})

    def _get_demographic_by_parcel(self, county: str, parcel_id: str) -> Optional[Dict]:
        """Get demographic record by parcel ID"""
        if not county or not parcel_id:
            return None

        collection_name = f"{county}CountyDemographic"
        if collection_name not in self.db.list_collection_names():
            return None

        return self.db[collection_name].find_one({"parcel_id": parcel_id})

    def match_applicant(self, csv_row: Dict) -> Dict:
        """
        Match applicant using multiple strategies in priority order

        Priority:
        1. Email (most reliable)
        2. Name (good for unique names)
        3. Phone (handles name variations)
        4. Address (fallback)

        Returns:
            Match result dictionary
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

        # Get county from ZIP
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

        # Try matching strategies in order
        # 1. Email match
        result = self._match_by_email(email, county)
        if result:
            return result

        # 2. Name match
        result = self._match_by_name(first_name, last_name, county, zip_code)
        if result:
            return result

        # 3. Phone match
        result = self._match_by_phone(phone, county)
        if result:
            return result

        # 4. Address match
        result = self._match_by_address(address, county)
        if result:
            return result

        # No match found
        collection_name = f"{county}CountyDemographic"
        collection_exists = collection_name in self.db.list_collection_names()

        return {
            'match_quality': 'no_match',
            'match_method': None,
            'match_details': f'No match found. Collection exists: {collection_exists}',
            'county': county,
            'residence_record': None,
            'demographic_record': None
        }


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
        'name': 0,
        'phone': 0,
        'address_normalized': 0,
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

    print(f"\n\n{'='*60}")
    print(f"✅ Processing Complete!")
    print(f"{'='*60}")
    print(f"Total processed: {processed}")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Errors: {errors}")
    print()
    print(f"Match Statistics:")
    print(f"  Email matches: {match_stats.get('email', 0)} ({match_stats.get('email', 0)/processed*100:.1f}%)")
    print(f"  Name matches: {match_stats.get('name', 0)} ({match_stats.get('name', 0)/processed*100:.1f}%)")
    print(f"  Phone matches: {match_stats.get('phone', 0)} ({match_stats.get('phone', 0)/processed*100:.1f}%)")
    print(f"  Address matches: {match_stats.get('address_normalized', 0)} ({match_stats.get('address_normalized', 0)/processed*100:.1f}%)")
    print(f"  No match: {match_stats.get('no_match', 0)} ({match_stats.get('no_match', 0)/processed*100:.1f}%)")
    print()

    total_matched = processed - match_stats.get('no_match', 0)
    match_rate = (total_matched / processed * 100) if processed > 0 else 0
    print(f"📊 Overall match rate: {match_rate:.1f}% ({total_matched}/{processed})")
    print()


if __name__ == '__main__':
    main()
