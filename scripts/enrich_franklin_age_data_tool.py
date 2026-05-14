#!/usr/bin/env python3
"""
Enrich FranklinCountyDemographic records with age data from Melissa Data CSV.

Calculates owner_age from MD_DateOfBirth and updates existing records
matched by normalized address.

Usage:
    python scripts/enrich_franklin_age_data_tool.py --dry-run
    python scripts/enrich_franklin_age_data_tool.py --limit 100
    python scripts/enrich_franklin_age_data_tool.py
"""

import argparse
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import os
import re
from dotenv import load_dotenv

load_dotenv()

DEFAULT_CSV_PATH = 'data/demographic/20260121-frankline/all_not_in_demographic_db_FINAL.csv'
DATABASE = 'empower_development'
COLLECTION = 'FranklinCountyDemographic'


def normalize_address(addr):
    """Normalize address for matching - reused from ingest_franklin_demographics_tool.py"""
    if pd.isna(addr):
        return None
    addr = str(addr).upper().strip()
    addr = re.sub(r'\s+', ' ', addr)
    addr = re.sub(r'\.$', '', addr)
    return addr


def parse_date_of_birth(dob_val):
    """Parse MD_DateOfBirth (YYYYMM format) to date string and calculate age."""
    if pd.isna(dob_val):
        return None, None

    try:
        dob_int = int(dob_val)
        year = dob_int // 100
        month = dob_int % 100

        if year < 1900 or year > 2020 or month < 1 or month > 12:
            return None, None

        # Calculate age as of current year
        current_year = datetime.now().year
        age = current_year - year

        # Adjust if birthday hasn't occurred yet this year
        current_month = datetime.now().month
        if month > current_month:
            age -= 1

        # Format as YYYYMM string for storage
        dob_str = f"{year}{month:02d}"

        return dob_str, age
    except (ValueError, TypeError):
        return None, None


def parse_presence_of_senior(val):
    """Normalize presence of senior field."""
    if pd.isna(val) or not val:
        return None

    val_str = str(val).strip().lower()
    if 'senior present' in val_str or val_str == 'yes':
        return 'Yes'
    elif 'no senior' in val_str or val_str == 'no':
        return 'No'
    return None


def parse_children_age_range(val):
    """Parse children age range field."""
    if pd.isna(val) or not val:
        return None
    return str(val).strip()


def parse_marital_status(val):
    """Normalize marital status."""
    if pd.isna(val) or not val:
        return None

    val_str = str(val).strip()
    if 'married' in val_str.lower():
        return 'Married'
    elif 'single' in val_str.lower():
        return 'Single'
    return val_str


def parse_number_of_adults(household_size, presence_of_children):
    """Estimate number of adults based on household size and children presence."""
    if pd.isna(household_size) or household_size <= 0:
        return None

    size = int(household_size)
    if presence_of_children and 'present' in str(presence_of_children).lower():
        # Assume at least 1 child if children present
        return max(1, size - 1)
    return size


def build_enrichment_data(row):
    """Build enrichment fields from CSV row."""
    dob_str, owner_age = parse_date_of_birth(row.get('MD_DateOfBirth'))
    presence_of_senior = parse_presence_of_senior(row.get('MD_PresenceOfSenior'))
    children_age_range = parse_children_age_range(row.get('MD_ChildrenAgeRange'))
    marital_status = parse_marital_status(row.get('MD_MaritalStatus'))
    presence_of_children = row.get('MD_PresenceOfChildren')
    household_size = row.get('MD_HouseholdSize')
    number_of_adults = parse_number_of_adults(household_size, presence_of_children)

    # Only include fields that have values
    enrichment = {}

    if owner_age is not None:
        enrichment['owner_age'] = owner_age
    if dob_str is not None:
        enrichment['date_of_birth'] = dob_str
    if presence_of_senior is not None:
        enrichment['presence_of_senior'] = presence_of_senior
    if children_age_range is not None:
        enrichment['children_age_range'] = children_age_range
    if marital_status is not None:
        enrichment['marital_status'] = marital_status
    if number_of_adults is not None:
        enrichment['number_of_adults'] = number_of_adults

    # Add length of residence if available
    if pd.notna(row.get('MD_LengthOfResidence')):
        enrichment['length_of_residence'] = str(row.get('MD_LengthOfResidence')).strip()

    # Add estimated home value if available
    if pd.notna(row.get('MD_EstimatedHomeValue')):
        val_str = str(row.get('MD_EstimatedHomeValue')).strip()
        # Parse numeric value from string like "$827,000"
        match = re.search(r'[\d,]+', val_str)
        if match:
            try:
                enrichment['estimated_home_value'] = int(match.group().replace(',', ''))
            except ValueError:
                pass

    return enrichment


def main():
    parser = argparse.ArgumentParser(description='Enrich Franklin County demographic data with age')
    parser.add_argument('--csv', default=DEFAULT_CSV_PATH, help='Path to CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Preview without updating')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--force', action='store_true', help='Update even if owner_age already exists')
    args = parser.parse_args()

    print("=" * 70)
    print("FRANKLIN COUNTY AGE DATA ENRICHMENT")
    print("=" * 70)
    print(f"CSV File: {args.csv}")
    print(f"Database: {DATABASE}")
    print(f"Collection: {COLLECTION}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Force Update: {args.force}")
    print(f"Limit: {args.limit or 'None'}")
    print()

    # Load CSV
    print("Loading CSV file...")
    df = pd.read_csv(args.csv, low_memory=False)
    total_rows = len(df)
    print(f"Loaded {total_rows:,} records")

    # Filter to only rows with date of birth
    df_with_dob = df[df['MD_DateOfBirth'].notna()].copy()
    print(f"Records with MD_DateOfBirth: {len(df_with_dob):,}")

    if args.limit:
        df_with_dob = df_with_dob.head(args.limit)
        print(f"Limited to {len(df_with_dob):,} records")

    # Connect to MongoDB
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    client = MongoClient(mongo_uri)
    db = client[DATABASE]
    coll = db[COLLECTION]

    initial_count = coll.count_documents({})
    already_enriched = coll.count_documents({'owner_age': {'$exists': True, '$gt': 0}})
    print(f"Current collection count: {initial_count:,}")
    print(f"Already enriched with owner_age: {already_enriched:,}")
    print()

    # Build address lookup from existing records
    print("Building address index from existing records...")
    existing_records = {}
    for doc in coll.find({}, {'_id': 1, 'address': 1, 'parcel_zip': 1, 'owner_age': 1}):
        addr = doc.get('address')
        if addr:
            key = (addr, doc.get('parcel_zip'))
            existing_records[key] = {
                '_id': doc['_id'],
                'has_age': doc.get('owner_age') is not None and doc.get('owner_age', 0) > 0
            }
    print(f"Indexed {len(existing_records):,} existing records")
    print()

    # Process records
    stats = {
        'processed': 0,
        'matched': 0,
        'updated': 0,
        'skipped_no_match': 0,
        'skipped_already_enriched': 0,
        'skipped_no_age': 0,
        'errors': 0,
    }

    updates = []

    print("Processing CSV records...")
    for idx, row in df_with_dob.iterrows():
        stats['processed'] += 1

        try:
            # Normalize address for matching
            addr = normalize_address(row.get('Address'))
            if not addr:
                stats['skipped_no_match'] += 1
                continue

            # Parse zipcode
            zipcode = row.get('Zipcode', '')
            parcel_zip = None
            if pd.notna(zipcode):
                zip_match = re.match(r'(\d{5})', str(zipcode))
                if zip_match:
                    parcel_zip = int(zip_match.group(1))

            # Try to find match
            key = (addr, parcel_zip)
            match = existing_records.get(key)

            # Also try without zip if no match
            if not match:
                for k, v in existing_records.items():
                    if k[0] == addr:
                        match = v
                        break

            if not match:
                stats['skipped_no_match'] += 1
                continue

            stats['matched'] += 1

            # Skip if already enriched (unless force)
            if match['has_age'] and not args.force:
                stats['skipped_already_enriched'] += 1
                continue

            # Build enrichment data
            enrichment = build_enrichment_data(row)

            if 'owner_age' not in enrichment:
                stats['skipped_no_age'] += 1
                continue

            # Add metadata
            enrichment['enriched_at'] = datetime.utcnow()
            enrichment['enriched_from'] = os.path.basename(args.csv)

            updates.append({
                '_id': match['_id'],
                'enrichment': enrichment
            })

            if args.verbose and len(updates) <= 5:
                print(f"\nSample enrichment #{len(updates)}:")
                print(f"  Address: {addr}")
                for k, v in enrichment.items():
                    if k != 'enriched_at':
                        print(f"  {k}: {v}")

        except Exception as e:
            stats['errors'] += 1
            if args.verbose:
                print(f"  ERROR row {idx}: {e}")

        # Progress update
        if stats['processed'] % 5000 == 0:
            print(f"  Processed {stats['processed']:,} / {len(df_with_dob):,}... (matched: {stats['matched']:,})")

    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total processed: {stats['processed']:,}")
    print(f"Matched to existing: {stats['matched']:,}")
    print(f"Skipped (no match): {stats['skipped_no_match']:,}")
    print(f"Skipped (already enriched): {stats['skipped_already_enriched']:,}")
    print(f"Skipped (no age in CSV): {stats['skipped_no_age']:,}")
    print(f"Errors: {stats['errors']:,}")
    print(f"Ready to update: {len(updates):,}")
    print()

    # Apply updates
    if args.dry_run:
        print("DRY RUN - No documents updated")
        print(f"Would update {len(updates):,} documents")

        # Show age distribution preview
        if updates:
            ages = [u['enrichment'].get('owner_age') for u in updates if u['enrichment'].get('owner_age')]
            if ages:
                print(f"\nAge distribution preview:")
                print(f"  Mean: {sum(ages)/len(ages):.1f} years")
                print(f"  Min: {min(ages)} years")
                print(f"  Max: {max(ages)} years")
                seniors = sum(1 for a in ages if a >= 65)
                print(f"  Seniors (65+): {seniors} ({100*seniors/len(ages):.1f}%)")
    else:
        if updates:
            print(f"Updating {len(updates):,} documents...")
            for i, update in enumerate(updates):
                coll.update_one(
                    {'_id': update['_id']},
                    {'$set': update['enrichment']}
                )
                stats['updated'] += 1

                if (i + 1) % 1000 == 0:
                    print(f"  Updated {i + 1:,} / {len(updates):,}...")

            print(f"Updated {stats['updated']:,} documents")

            final_enriched = coll.count_documents({'owner_age': {'$exists': True, '$gt': 0}})
            print(f"Total records with owner_age: {final_enriched:,}")
        else:
            print("No documents to update")

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)

    return stats


if __name__ == '__main__':
    main()
