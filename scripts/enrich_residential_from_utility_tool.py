#!/usr/bin/env python3
"""
Enrich FranklinCountyResidential with Customer Names from Utility Files

Reads AEP utility CSV files, extracts CustomerName by address, and updates
the parcel_owner field in FranklinCountyResidential MongoDB collection.

Usage:
    python scripts/enrich_residential_from_utility_tool.py --county Franklin
    python scripts/enrich_residential_from_utility_tool.py --county Franklin --dry-run
    python scripts/enrich_residential_from_utility_tool.py --county Franklin --limit 1000
"""
import argparse
import csv
import math
import re
import sys
from pathlib import Path
from typing import Dict, Set, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from pymongo import UpdateOne
from src.tools.address_normalization import normalize_address, normalize_address_keep_unit, is_valid_person_name
from src.tools.mongo import get_empower_db
from src.utils.log_manager import LogManager

load_dotenv()
logger = LogManager().get_logger(__name__)

# Utility file paths
UTILITY_FILES = {
    'Franklin': [
        Path('/home/warnd/empower/data/CountyData/FranklinCounty/AEP_CSP.csv'),
        Path('/home/warnd/empower/data/CountyData/FranklinCounty/AEP_OPCO.csv'),
    ]
}


def extract_names_from_utility_files(utility_files: list, verbose: bool = False) -> Dict[Tuple[str, str], str]:
    """
    Extract customer names from utility CSV files.

    Uses two-pass approach to exclude multi-unit addresses:
    1. First pass: identify base addresses that have multiple units
    2. Second pass: only keep single-unit addresses

    Returns dict mapping (normalized_address, zip) -> customer_name
    """
    # First pass: collect all data and detect multi-unit addresses
    raw_data = []  # List of (base_addr, full_addr, zipcode, name)
    units_per_base = defaultdict(set)  # (base_addr, zip) -> set of full addresses

    for file_path in utility_files:
        if not file_path.exists():
            logger.warning(f"Utility file not found: {file_path}")
            continue

        logger.info(f"Pass 1 - Scanning {file_path.name} for multi-unit detection...")

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader):
                if i % 100000 == 0 and i > 0:
                    print(f"  Scanned {i:,} rows...", flush=True)

                name = row.get('CustomerName', '').strip()
                address = row.get('ServiceAddress1', '').strip()
                zipcode = row.get('ServicePostalCode', '').strip()

                if zipcode and len(zipcode) >= 5:
                    zipcode = zipcode[:5]

                if not address or not zipcode:
                    continue

                if not is_valid_person_name(name):
                    continue

                base_addr = normalize_address(address)  # With apartment stripping
                full_addr = normalize_address_keep_unit(address)  # Without stripping
                key = (base_addr, zipcode)

                units_per_base[key].add(full_addr)
                raw_data.append((base_addr, full_addr, zipcode, name))

    # Identify multi-unit addresses (more than one unique full address per base)
    multi_unit_keys = {k for k, v in units_per_base.items() if len(v) > 1}
    logger.info(f"Found {len(multi_unit_keys):,} multi-unit addresses to exclude")

    # Second pass: build address->name mapping, excluding multi-unit
    address_to_name = {}
    duplicates = defaultdict(set)
    excluded_multi_unit = 0

    print(f"  Pass 2 - Building single-unit address mappings...", flush=True)
    for base_addr, full_addr, zipcode, name in raw_data:
        key = (base_addr, zipcode)

        # Skip multi-unit addresses
        if key in multi_unit_keys:
            excluded_multi_unit += 1
            continue

        if key in address_to_name:
            if address_to_name[key] != name:
                duplicates[key].add(address_to_name[key])
                duplicates[key].add(name)
        else:
            address_to_name[key] = name

    logger.info(f"Extracted {len(address_to_name):,} single-unit address->name mappings")
    logger.info(f"Excluded {excluded_multi_unit:,} records from multi-unit buildings")
    logger.info(f"Found {len(duplicates):,} addresses with multiple names (kept first)")

    return address_to_name


def update_residential_collection(db, county: str, address_to_name: Dict[Tuple[str, str], str],
                                   dry_run: bool = False, limit: int = None) -> Dict[str, int]:
    """
    Update parcel_owner in residential collection using address->name mapping.
    """
    residential_coll = f"{county}CountyResidential"

    # Find records without owner
    query = {'$or': [{'parcel_owner': None}, {'parcel_owner': ''}, {'parcel_owner': {'$exists': False}}]}

    cursor = db[residential_coll].find(query, {'_id': 1, 'address': 1, 'parcel_zip': 1})

    if limit:
        cursor = cursor.limit(limit)

    updates = []
    matched = 0
    not_matched = 0

    for doc in cursor:
        address = doc.get('address', '')
        zipcode = doc.get('parcel_zip')

        # parcel_zip is INTEGER in MongoDB, utility ZIP is string
        # Handle all numeric types consistently, including NaN
        if zipcode is not None:
            if isinstance(zipcode, float):
                if math.isnan(zipcode):
                    zipcode = None
                else:
                    zipcode = str(int(zipcode))
            elif isinstance(zipcode, int):
                zipcode = str(zipcode)
            else:
                zipcode = str(zipcode)[:5]  # Take first 5 chars if string

        norm_addr = normalize_address(address)
        key = (norm_addr, zipcode)

        if key in address_to_name:
            matched += 1
            updates.append(UpdateOne(
                {'_id': doc['_id']},
                {'$set': {'parcel_owner': address_to_name[key]}}
            ))
        else:
            not_matched += 1

        if (matched + not_matched) % 10000 == 0:
            print(f"  Checked {matched + not_matched:,} records, {matched:,} matches...", flush=True)

    results = {
        'checked': matched + not_matched,
        'matched': matched,
        'not_matched': not_matched,
        'updated': 0
    }

    if updates and not dry_run:
        logger.info(f"Executing {len(updates):,} updates...")
        result = db[residential_coll].bulk_write(updates, ordered=False)
        results['updated'] = result.modified_count
        logger.info(f"Updated {result.modified_count:,} records")
    elif updates and dry_run:
        logger.info(f"DRY RUN: Would update {len(updates):,} records")
        results['updated'] = len(updates)

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Enrich residential records with customer names from utility files',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--county', type=str, default='Franklin', help='County name')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of records to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print(f"""
{'='*60}
  ENRICH RESIDENTIAL DATA WITH UTILITY CUSTOMER NAMES
{'='*60}
  County: {args.county}
  Dry run: {args.dry_run}
  Limit: {args.limit or 'None'}
{'='*60}
""", flush=True)

    # Get utility files for county
    if args.county not in UTILITY_FILES:
        print(f"Error: No utility files configured for {args.county}")
        sys.exit(1)

    utility_files = UTILITY_FILES[args.county]

    # Step 1: Extract names from utility files
    print("Step 1: Extracting customer names from utility files...", flush=True)
    address_to_name = extract_names_from_utility_files(utility_files, args.verbose)

    if not address_to_name:
        print("No names extracted from utility files")
        sys.exit(1)

    # Step 2: Connect to MongoDB and update
    print("\nStep 2: Connecting to MongoDB...", flush=True)
    db = get_empower_db()

    # Step 3: Update residential collection
    print("\nStep 3: Updating residential collection...", flush=True)
    results = update_residential_collection(db, args.county, address_to_name, args.dry_run, args.limit)

    # Summary
    print(f"""
{'='*60}
  RESULTS
{'='*60}
  Records checked:    {results['checked']:,}
  Matches found:      {results['matched']:,}
  No match:           {results['not_matched']:,}
  Records updated:    {results['updated']:,}

  Match rate: {100*results['matched']/results['checked']:.1f}%
{'='*60}
""", flush=True)


if __name__ == '__main__':
    main()
