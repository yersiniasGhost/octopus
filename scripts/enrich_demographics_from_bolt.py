#!/usr/bin/env python3
"""
Enrich existing demographic documents with additional fields from BOLT analysis files.

Only updates existing documents - does not create new ones.
Tracks and reports records that couldn't be matched.
"""

import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import os
import re

# File configurations with column mappings
FILE_CONFIGS = [
    {
        'name': 'Fayette',
        'file': 'fayette_EmpowerSaves_BOLT Analysis_20250310.xlsx',
        'county_collection': 'FayetteCountyDemographic',
        'parcel_col': 'Parcel_Number_U',
        'address_col': 'parcel_address',
    },
    {
        'name': 'Allen',
        'file': 'allen__EmpowerSaves_BOLT Analysis_20250310.xlsx',
        'county_collection': 'AllenCountyDemographic',
        'parcel_col': 'parcel_id',
        'address_col': 'ServiceAddress',
    },
    {
        'name': 'Richland',
        'file': 'Richland_EmpowerSaves_BOL Analysis_20250317.xlsx',
        'county_collection': 'RichlandCountyDemographic',
        'parcel_col': None,  # No parcel_id - will match on address
        'address_col': 'SERVICE_ADDRESS',
    },
    {
        'name': 'OHCAC',
        'file': 'EmpowerSaves-OHCAC_BOLT ANALYSIS_2050228.xlsx',
        'county_collection': None,  # Multiple counties - need to determine
        'parcel_col': None,
        'address_col': 'SERVICE_ADDRESS',
    },
    {
        'name': 'HHWP',
        'file': 'HHWP_EmpowerSaves_BOLT Analysis_20250220.xlsx',
        'county_collection': None,  # Multiple counties based on 'county' column
        'parcel_col': 'PARCEL_ID',
        'address_col': 'address',
    },
    {
        'name': 'IMPACT',
        'file': 'IMPACT_EmpowerSaves_BOLT ANALYSIS_with costs_for texting_20250509.xlsx',
        'county_collection': 'FranklinCountyDemographic',  # IMPACT is Franklin County
        'parcel_col': 'parcel_id',
        'address_col': 'ServiceAddress1',
    },
    {
        'name': 'COAD',
        'file': 'EmpowerSaves_COAD_BOLT Analysis_with costs_20250507.xlsx',
        'county_collection': None,  # Multiple counties based on 'County' column
        'parcel_col': None,
        'address_col': 'ServiceAddress',
    },
]

# Universal field mappings (column name variations -> standardized field name)
FIELD_MAPPINGS = {
    'owner_age': ['Age in Two-Year Increments - 1st Individual', 'age'],
    'number_of_adults': ['Number of Adults'],
    'marital_status': ['Marital Status'],
    'presence_of_children': ['Presence of Children'],
    'gender': ['Gender - Input Individual'],
    'dwelling_type': ['Dwelling Type'],
    'home_owner': ['Home Owner / Renter'],
    'length_of_residence': ['Home Length of Residence', 'MD_LengthOfResidence'],
    'presence_of_senior': ['MD_PresenceOfSenior'],
    'education': ['MD_Education'],
    'ethnic_group': ['MD_EthnicGroup'],
    'estimated_home_value': ['MD_EstimatedHomeValue'],
    'date_of_birth': ['MD_DateOfBirth'],
    'household_size': ['MD_HouseholdSize'],
    'occupation': ['MD_Occupation'],
    'children_age_range': ['MD_ChildrenAgeRange'],
}


def normalize_address(addr):
    """Normalize address for matching."""
    if pd.isna(addr):
        return None
    addr = str(addr).upper().strip()
    # Remove common variations
    addr = re.sub(r'\s+', ' ', addr)
    addr = re.sub(r'\.$', '', addr)
    return addr


def normalize_parcel_id(parcel):
    """Normalize parcel ID for matching."""
    if pd.isna(parcel):
        return None
    # Convert to string and remove common formatting
    parcel = str(parcel).strip()
    # Remove dashes and spaces for comparison
    parcel_clean = re.sub(r'[-\s]', '', parcel)
    return parcel_clean


def get_field_value(row, field_name, columns):
    """Get field value from row using column mapping."""
    possible_cols = FIELD_MAPPINGS.get(field_name, [])
    for col in possible_cols:
        if col in columns and col in row.index:
            val = row[col]
            if pd.notna(val):
                return val
    return None


def extract_demographics(row, columns):
    """Extract demographic fields from a row."""
    demographics = {}

    for field_name in FIELD_MAPPINGS.keys():
        val = get_field_value(row, field_name, columns)
        if val is not None:
            # Clean up values
            if field_name == 'owner_age' and isinstance(val, (int, float)):
                val = int(val)
            elif field_name == 'marital_status':
                val = 'Married' if val == 'M' else 'Single' if val == 'S' else str(val)
            elif field_name == 'presence_of_children':
                val = 'Yes' if val == 'Y' else 'No' if val == 'N' else str(val)
            elif field_name == 'home_owner':
                val = 'Owner' if val == 'O' else 'Renter' if val == 'R' else str(val)
            elif field_name == 'gender':
                val = 'Male' if val == 'M' else 'Female' if val == 'F' else str(val)
            elif field_name == 'presence_of_senior':
                val = 'Yes' if 'Senior Present' in str(val) else 'No' if 'No Senior' in str(val) else str(val)
            elif isinstance(val, float) and val == int(val):
                val = int(val)

            demographics[field_name] = val

    return demographics


def process_file(config, base_dir, emp_db, dry_run=False):
    """Process a single BOLT analysis file."""
    filepath = os.path.join(base_dir, config['file'])

    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return {'matched': 0, 'unmatched': 0, 'unmatched_records': []}

    print(f"\n{'='*60}")
    print(f"Processing: {config['name']}")
    print(f"File: {config['file']}")
    print(f"{'='*60}")

    # Read file
    print("  Reading Excel file...")
    df = pd.read_excel(filepath)
    print(f"  Loaded {len(df):,} records with {len(df.columns)} columns")

    columns = set(df.columns)
    parcel_col = config['parcel_col']
    address_col = config['address_col']
    county_collection = config['county_collection']

    # Check for county column if no fixed collection
    county_col = None
    if county_collection is None:
        for col in ['County', 'county', 'COUNTY']:
            if col in columns:
                county_col = col
                break

    matched = 0
    unmatched = 0
    unmatched_records = []
    updates_by_collection = {}

    print("  Matching records to existing documents...")

    for idx, row in df.iterrows():
        if idx % 10000 == 0 and idx > 0:
            print(f"    Processed {idx:,} records...")

        # Determine target collection
        target_collection = county_collection
        if target_collection is None and county_col:
            county_name = row.get(county_col)
            if pd.notna(county_name):
                # Normalize county name to collection name
                county_name = str(county_name).strip().title().replace(' ', '')
                if not county_name.endswith('County'):
                    county_name += 'County'
                target_collection = f"{county_name}Demographic"

        if target_collection is None:
            unmatched += 1
            continue

        # Get collection
        if target_collection not in emp_db.list_collection_names():
            unmatched += 1
            if len(unmatched_records) < 100:
                unmatched_records.append({
                    'reason': f'Collection not found: {target_collection}',
                    'address': row.get(address_col) if address_col else None,
                })
            continue

        coll = emp_db[target_collection]

        # Try to match by parcel_id first
        match_doc = None
        match_query = None

        if parcel_col and parcel_col in row.index:
            parcel = row[parcel_col]
            if pd.notna(parcel):
                parcel_norm = normalize_parcel_id(parcel)
                # Try exact match first
                match_doc = coll.find_one({'parcel_id': str(parcel)})
                if not match_doc:
                    # Try normalized match
                    match_doc = coll.find_one({'parcel_id': {'$regex': f'^{parcel_norm}', '$options': 'i'}})
                match_query = f"parcel_id={parcel}"

        # Fall back to address matching if no parcel match
        if not match_doc and address_col and address_col in row.index:
            addr = row[address_col]
            if pd.notna(addr):
                addr_norm = normalize_address(addr)
                if addr_norm:
                    match_doc = coll.find_one({'address': {'$regex': f'^{re.escape(addr_norm[:20])}', '$options': 'i'}})
                    match_query = f"address={addr_norm[:30]}"

        if match_doc:
            # Extract demographics and prepare update
            demographics = extract_demographics(row, columns)

            if demographics:
                if target_collection not in updates_by_collection:
                    updates_by_collection[target_collection] = []

                updates_by_collection[target_collection].append({
                    '_id': match_doc['_id'],
                    'updates': demographics
                })
                matched += 1
        else:
            unmatched += 1
            if len(unmatched_records) < 100:
                unmatched_records.append({
                    'query': match_query,
                    'address': row.get(address_col) if address_col else None,
                    'parcel': row.get(parcel_col) if parcel_col else None,
                })

    # Apply updates
    if not dry_run:
        print("  Applying updates to database...")
        for coll_name, updates in updates_by_collection.items():
            coll = emp_db[coll_name]
            for update in updates:
                coll.update_one(
                    {'_id': update['_id']},
                    {'$set': {
                        **update['updates'],
                        'enriched_at': datetime.utcnow(),
                        'enriched_from': config['file'],
                    }}
                )
            print(f"    {coll_name}: {len(updates)} documents updated")
    else:
        print("  [DRY RUN] Would update:")
        for coll_name, updates in updates_by_collection.items():
            print(f"    {coll_name}: {len(updates)} documents")

    print(f"\n  Results: {matched:,} matched, {unmatched:,} unmatched")

    return {
        'matched': matched,
        'unmatched': unmatched,
        'unmatched_records': unmatched_records,
        'updates_by_collection': {k: len(v) for k, v in updates_by_collection.items()}
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Enrich demographic documents from BOLT files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--file', type=str, help='Process only specific file (by name: Fayette, Allen, etc.)')
    parser.add_argument('--limit', type=int, help='Limit rows to process per file (for testing)')
    args = parser.parse_args()

    base_dir = 'data2/demographics'

    client = MongoClient('localhost', 27017)
    emp_db = client['empower_development']

    print("=" * 60)
    print("DEMOGRAPHIC ENRICHMENT FROM BOLT ANALYSIS FILES")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"Base directory: {base_dir}")

    # Filter configs if specific file requested
    configs = FILE_CONFIGS
    if args.file:
        configs = [c for c in configs if c['name'].lower() == args.file.lower()]
        if not configs:
            print(f"File not found: {args.file}")
            return

    all_results = {}
    all_unmatched = []

    for config in configs:
        result = process_file(config, base_dir, emp_db, dry_run=args.dry_run)
        all_results[config['name']] = result
        all_unmatched.extend([
            {'file': config['name'], **r} for r in result['unmatched_records']
        ])

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_matched = sum(r['matched'] for r in all_results.values())
    total_unmatched = sum(r['unmatched'] for r in all_results.values())

    print(f"\n{'File':<15} {'Matched':>10} {'Unmatched':>12}")
    print("-" * 40)
    for name, result in all_results.items():
        print(f"{name:<15} {result['matched']:>10,} {result['unmatched']:>12,}")
    print("-" * 40)
    print(f"{'TOTAL':<15} {total_matched:>10,} {total_unmatched:>12,}")

    # Save unmatched records
    if all_unmatched:
        unmatched_file = 'data2/demographics/unmatched_records.csv'
        unmatched_df = pd.DataFrame(all_unmatched[:1000])  # Limit to first 1000
        unmatched_df.to_csv(unmatched_file, index=False)
        print(f"\nUnmatched records saved to: {unmatched_file}")
        print(f"(Showing first 1000 of {len(all_unmatched)} unmatched)")

    client.close()


if __name__ == '__main__':
    main()
