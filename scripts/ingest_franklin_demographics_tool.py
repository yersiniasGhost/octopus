#!/usr/bin/env python3
"""
Ingest Franklin County demographic data from Melissa Data enriched CSV into MongoDB.

Converts string-based income brackets to numeric values and maps CSV fields
to the existing FranklinCountyDemographic schema.

Usage:
    python scripts/ingest_franklin_demographics_tool.py --dry-run
    python scripts/ingest_franklin_demographics_tool.py --limit 100
    python scripts/ingest_franklin_demographics_tool.py
"""

import argparse
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import os
import re
from dotenv import load_dotenv

load_dotenv()

# Income bracket to numeric mapping
# Maps MD_HouseholdIncome string ranges to (midpoint, level)
INCOME_MAPPING = {
    '$0-$15,000': (10000, 1),
    '$15,001-$20,000': (17500, 2),
    '$20,001-$30,000': (25000, 3),
    '$30,001-$40,000': (35000, 4),
    '$40,001-$50,000': (45000, 5),
    '$50,001-$60,000': (55000, 5),  # Maps to level 5 (closest)
    '$60,001-$75,000': (62500, 6),
    '$75,001-$100,000': (87500, 7),
    '$100,001-$125,000': (112500, 8),
    '$125,001-$150,000': (137500, 9),
    '$150,001+': (175000, 9),
}

DEFAULT_CSV_PATH = 'data/demographic/20260121-frankline/all_not_in_demographic_db_FINAL.csv'
DATABASE = 'empower_development'
COLLECTION = 'FranklinCountyDemographic'


def normalize_address(addr):
    """Normalize address for duplicate detection."""
    if pd.isna(addr):
        return None
    addr = str(addr).upper().strip()
    addr = re.sub(r'\s+', ' ', addr)
    addr = re.sub(r'\.$', '', addr)
    return addr


def parse_income(income_str):
    """Convert income bracket string to (estimated_income, income_level) tuple."""
    if pd.isna(income_str) or not income_str:
        return (-1, -1)

    income_str = str(income_str).strip()
    if income_str in INCOME_MAPPING:
        return INCOME_MAPPING[income_str]

    # Try to handle any unexpected formats
    return (-1, -1)


def parse_mobile(mobile_str):
    """Parse mobile phone number to integer, return -1 if invalid."""
    if pd.isna(mobile_str) or not mobile_str:
        return -1

    # Remove non-numeric characters
    digits = re.sub(r'\D', '', str(mobile_str))
    if len(digits) >= 10:
        return int(digits[:10])
    return -1


def parse_household_size(size_val):
    """Parse household size to float."""
    if pd.isna(size_val):
        return -1.0
    try:
        return float(size_val)
    except (ValueError, TypeError):
        return -1.0


def build_document(row):
    """Build a MongoDB document from a CSV row."""
    # Parse income
    estimated_income, income_level = parse_income(row.get('MD_HouseholdIncome'))

    # Build customer name
    first_name = str(row.get('First Name', '')).strip() if pd.notna(row.get('First Name')) else ''
    last_name = str(row.get('Last Name', '')).strip() if pd.notna(row.get('Last Name')) else ''
    if first_name and last_name:
        customer_name = f"{first_name} {last_name}"
    elif row.get('Name') and pd.notna(row.get('Name')):
        customer_name = str(row.get('Name')).strip()
    else:
        customer_name = ''

    # Parse zipcode
    zipcode = row.get('Zipcode', '')
    if pd.notna(zipcode):
        # Extract numeric part of zipcode (handle 43201-3379 format)
        zip_match = re.match(r'(\d{5})', str(zipcode))
        parcel_zip = int(zip_match.group(1)) if zip_match else -1
    else:
        parcel_zip = -1

    doc = {
        'customer_name': customer_name.upper(),
        'address': normalize_address(row.get('Address')),
        'service_city': str(row.get('City', '')).upper().strip() if pd.notna(row.get('City')) else '',
        'parcel_zip': parcel_zip,
        'parcel_id': '',  # Not available in this data
        'email': str(row.get('MD_EMAIL', '')).lower().strip() if pd.notna(row.get('MD_EMAIL')) else '',
        'mobile': parse_mobile(row.get('MD_MOBILE')),
        'estimated_income': float(estimated_income),
        'income_level': float(income_level),
        'md_householdsize': parse_household_size(row.get('MD_HouseholdSize')),
        # Energy fields - not available in this data, set to -1
        'annual_kwh_cost': -1.0,
        'annual_gas_cost': -1.0,
        'energy_burden_kwh': -1.0,
        'energy_burden_gas': -1.0,
        'total_energy_burden': -1.0,
        # Vehicle fields
        'cars': [],
        'number_of_vehicles': -1,
        # Metadata
        'source': 'melissa_data_20260121',
        'ingested_at': datetime.utcnow(),
        # Additional MD fields worth preserving
        'md_own_rent': str(row.get('MD_OwnRent', '')).strip() if pd.notna(row.get('MD_OwnRent')) else '',
        'md_estimated_home_value': str(row.get('MD_EstimatedHomeValue', '')).strip() if pd.notna(row.get('MD_EstimatedHomeValue')) else '',
        'md_education': str(row.get('MD_Education', '')).strip() if pd.notna(row.get('MD_Education')) else '',
        'md_marital_status': str(row.get('MD_MaritalStatus', '')).strip() if pd.notna(row.get('MD_MaritalStatus')) else '',
        'md_gender': str(row.get('MD_DemographicsGender', '')).strip() if pd.notna(row.get('MD_DemographicsGender')) else '',
        'md_occupation': str(row.get('MD_Occupation', '')).strip() if pd.notna(row.get('MD_Occupation')) else '',
        'md_length_of_residence': str(row.get('MD_LengthOfResidence', '')).strip() if pd.notna(row.get('MD_LengthOfResidence')) else '',
        'md_presence_of_children': str(row.get('MD_PresenceOfChildren', '')).strip() if pd.notna(row.get('MD_PresenceOfChildren')) else '',
        'md_presence_of_senior': str(row.get('MD_PresenceOfSenior', '')).strip() if pd.notna(row.get('MD_PresenceOfSenior')) else '',
        'md_median_household_income': str(row.get('MD_MedianHouseholdIncome', '')).strip() if pd.notna(row.get('MD_MedianHouseholdIncome')) else '',
        # Property data from source
        'sqft': float(row.get('Sqft')) if pd.notna(row.get('Sqft')) else -1.0,
        'year_built': int(row.get('Year_Built')) if pd.notna(row.get('Year_Built')) else -1,
        'energy_percentile': float(row.get('Energy_Percentile')) if pd.notna(row.get('Energy_Percentile')) else -1.0,
    }

    return doc


def check_duplicate(coll, address, parcel_zip):
    """Check if a record with the same address already exists."""
    if not address:
        return None

    query = {'address': address}
    if parcel_zip and parcel_zip > 0:
        query['parcel_zip'] = parcel_zip

    return coll.find_one(query)


def main():
    parser = argparse.ArgumentParser(description='Ingest Franklin County demographic data')
    parser.add_argument('--csv', default=DEFAULT_CSV_PATH, help='Path to CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Preview without inserting')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--skip-duplicates', action='store_true', default=True,
                        help='Skip records that already exist (default: True)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("=" * 70)
    print("FRANKLIN COUNTY DEMOGRAPHIC INGESTION")
    print("=" * 70)
    print(f"CSV File: {args.csv}")
    print(f"Database: {DATABASE}")
    print(f"Collection: {COLLECTION}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Limit: {args.limit or 'None'}")
    print()

    # Load CSV
    print("Loading CSV file...")
    df = pd.read_csv(args.csv, low_memory=False)
    total_rows = len(df)
    print(f"Loaded {total_rows:,} records")

    if args.limit:
        df = df.head(args.limit)
        print(f"Limited to {len(df):,} records")

    # Connect to MongoDB
    client = MongoClient(os.getenv('MONGODB_URI'))
    db = client[DATABASE]
    coll = db[COLLECTION]

    initial_count = coll.count_documents({})
    print(f"Current collection count: {initial_count:,}")
    print()

    # Process records
    stats = {
        'processed': 0,
        'inserted': 0,
        'duplicates': 0,
        'errors': 0,
        'income_mapped': 0,
        'income_missing': 0,
    }

    documents_to_insert = []

    print("Processing records...")
    for idx, row in df.iterrows():
        stats['processed'] += 1

        try:
            doc = build_document(row)

            # Track income mapping stats
            if doc['income_level'] > 0:
                stats['income_mapped'] += 1
            else:
                stats['income_missing'] += 1

            # Check for duplicates
            if args.skip_duplicates:
                existing = check_duplicate(coll, doc['address'], doc['parcel_zip'])
                if existing:
                    stats['duplicates'] += 1
                    if args.verbose:
                        print(f"  SKIP (dup): {doc['address']}")
                    continue

            documents_to_insert.append(doc)

            if args.verbose and stats['processed'] <= 5:
                print(f"\nSample document #{stats['processed']}:")
                for k, v in doc.items():
                    if k != 'ingested_at':
                        print(f"  {k}: {v}")

        except Exception as e:
            stats['errors'] += 1
            print(f"  ERROR row {idx}: {e}")

        # Progress update
        if stats['processed'] % 5000 == 0:
            print(f"  Processed {stats['processed']:,} / {len(df):,}...")

    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total processed: {stats['processed']:,}")
    print(f"Duplicates skipped: {stats['duplicates']:,}")
    print(f"Errors: {stats['errors']:,}")
    print(f"Ready to insert: {len(documents_to_insert):,}")
    print(f"Income mapped: {stats['income_mapped']:,}")
    print(f"Income missing: {stats['income_missing']:,}")
    print()

    # Insert documents
    if args.dry_run:
        print("DRY RUN - No documents inserted")
        print(f"Would insert {len(documents_to_insert):,} documents")
    else:
        if documents_to_insert:
            print(f"Inserting {len(documents_to_insert):,} documents...")
            result = coll.insert_many(documents_to_insert)
            stats['inserted'] = len(result.inserted_ids)
            print(f"Inserted {stats['inserted']:,} documents")

            final_count = coll.count_documents({})
            print(f"Final collection count: {final_count:,}")
        else:
            print("No documents to insert")

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)

    return stats


if __name__ == '__main__':
    main()
