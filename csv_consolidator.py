#!/usr/bin/env python3
"""
Consolidate EmailOctopus campaign CSV files with MongoDB demographic enrichment.

Output CSV format: ID (name/ID), Campaign, Opened, Clicked, Applied (always 0), County, Demographics

Usage:
    python csv_consolidator.py --input-dir ./data/exports --output enriched.csv --filter all
    python csv_consolidator.py --input-dir ./data/exports --output enriched.csv --filter engaged
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'empower_analytics' / 'src'))

from mongo_tools.mongo import Mongo
from config.log_wrapper import log
from zipcode_to_county_mapper import ZipcodeCountyMapper


@dataclass
class ConsolidatedRecord:
    """Output record format."""
    person_id: str              # Email or name
    campaign_name: str
    opened: str                 # Yes/No
    clicked: str                # Yes/No
    applied: int                # Always 0
    county: str                 # From MongoDB
    zipcode: str                # From CSV or MongoDB
    address: str                # From CSV
    name: str                   # From CSV or MongoDB
    email: str                  # From CSV
    cell: str                   # From CSV or MongoDB
    estimated_income: float     # From MongoDB
    energy_burden_kwh: float    # From MongoDB
    total_energy_burden: float  # From MongoDB


class MongoMatcher:
    """Match CSV records to MongoDB demographic data."""

    def __init__(self, mongo_db, zipcode_county_map: Dict[str, str]):
        self.db = mongo_db
        self.zipcode_county_map = zipcode_county_map

        # Build in-memory caches for performance
        self.email_cache: Dict[str, dict] = {}
        self.address_cache: Dict[str, dict] = {}
        self.cell_cache: Dict[str, dict] = {}

        log(__name__).info("Building in-memory lookup caches...")
        self._build_caches()

    def _build_caches(self):
        """Pre-load MongoDB data into memory for fast lookups."""
        collections = self.db.list_collection_names()
        demographic_collections = [c for c in collections if 'Demographic' in c]

        log(__name__).info(f"Loading data from {len(demographic_collections)} demographic collections...")

        for collection_name in demographic_collections:
            collection = self.db[collection_name]
            county_name = self._extract_county(collection_name)

            # Load all records from this collection
            cursor = collection.find({}, {
                'email': 1,
                'mobile': 1,
                'address': 1,
                'customer_name': 1,
                'parcel_zip': 1,
                'estimated_income': 1,
                'energy_burden_kwh': 1,
                'total_energy_burden': 1
            })

            count = 0
            for doc in cursor:
                doc['county'] = county_name

                # Index by email
                email = doc.get('email')
                if email and email != -1:
                    email_str = str(email).lower().strip()
                    if '@' in email_str:
                        self.email_cache[email_str] = doc

                # Index by address
                address = doc.get('address')
                if address:
                    addr_key = self._normalize_address(address)
                    self.address_cache[addr_key] = doc

                # Index by cell
                cell = doc.get('mobile')
                if cell and cell != -1:
                    cell_str = self._normalize_phone(str(cell))
                    if cell_str:
                        self.cell_cache[cell_str] = doc

                count += 1

            log(__name__).info(f"  {county_name}: {count} records indexed")

        log(__name__).info(f"Cache complete: {len(self.email_cache)} emails, "
                          f"{len(self.address_cache)} addresses, {len(self.cell_cache)} phones")

    def _extract_county(self, collection_name: str) -> str:
        """Extract county name from collection name."""
        for suffix in ['Residential', 'Demographic', 'Loads', 'Gas', 'Electrical']:
            if collection_name.endswith(suffix):
                return collection_name[:-len(suffix)]
        return collection_name

    def _normalize_address(self, address: str) -> str:
        """Normalize address for matching."""
        if not address:
            return ''
        addr = address.upper().strip()
        # Remove common variations
        addr = re.sub(r'\bSTREET\b', 'ST', addr)
        addr = re.sub(r'\bAVENUE\b', 'AVE', addr)
        addr = re.sub(r'\bROAD\b', 'RD', addr)
        addr = re.sub(r'\bDRIVE\b', 'DR', addr)
        addr = re.sub(r'\bCOURT\b', 'CT', addr)
        addr = re.sub(r'\s+', ' ', addr)
        return addr

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for matching."""
        if not phone:
            return ''
        # Extract digits only
        digits = re.sub(r'\D', '', str(phone))
        if len(digits) >= 10:
            return digits[-10:]  # Last 10 digits
        return ''

    def match_record(self, csv_row: dict) -> Optional[dict]:
        """
        Match CSV record to MongoDB using hierarchical strategy:
        1. Email exact match
        2. Address + Zip fuzzy match
        3. Cell phone match
        """
        # Strategy 1: Email match
        email = csv_row.get('email', '').lower().strip()
        if email in self.email_cache:
            return self.email_cache[email]

        # Strategy 2: Address match
        address = self._normalize_address(csv_row.get('address', ''))
        if address and address in self.address_cache:
            return self.address_cache[address]

        # Strategy 3: Cell phone match
        cell = self._normalize_phone(csv_row.get('cell', ''))
        if cell and cell in self.cell_cache:
            return self.cell_cache[cell]

        return None

    def get_county_from_zipcode(self, zipcode: str) -> str:
        """Lookup county from zipcode."""
        if not zipcode:
            return 'Unknown'
        zip_str = str(zipcode).zfill(5)
        return self.zipcode_county_map.get(zip_str, 'Unknown')


class CSVConsolidator:
    """Consolidate multiple CSV files with MongoDB enrichment."""

    def __init__(self, input_dir: Path, output_file: Path, filter_mode: str):
        self.input_dir = input_dir
        self.output_file = output_file
        self.filter_mode = filter_mode

        # Initialize MongoDB and matcher
        self.mongo = Mongo()
        self.zipcode_map = ZipcodeCountyMapper.load_cache()
        self.matcher = MongoMatcher(self.mongo.database, self.zipcode_map)

        # Statistics
        self.stats = {
            'total_records': 0,
            'engaged_records': 0,
            'matched_records': 0,
            'output_records': 0,
            'missing_county': 0
        }

    def should_include_record(self, row: dict) -> bool:
        """Determine if record should be included based on filter."""
        if self.filter_mode == 'all':
            return True
        elif self.filter_mode == 'engaged':
            opened = row.get('opened', '').strip().lower() == 'yes'
            clicked = row.get('clicked', '').strip().lower() == 'yes'
            return opened or clicked
        return False

    def process_csv_files(self) -> List[ConsolidatedRecord]:
        """Process all CSV files and consolidate."""
        consolidated = []
        csv_files = list(self.input_dir.glob('*.csv'))

        log(__name__).info(f"Processing {len(csv_files)} CSV files...")

        for csv_file in csv_files:
            log(__name__).info(f"Processing {csv_file.name}...")

            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    self.stats['total_records'] += 1

                    # Check if engaged
                    is_engaged = (row.get('opened', '').strip().lower() == 'yes' or
                                 row.get('clicked', '').strip().lower() == 'yes')
                    if is_engaged:
                        self.stats['engaged_records'] += 1

                    # Filter
                    if not self.should_include_record(row):
                        continue

                    # Match to MongoDB
                    mongo_match = self.matcher.match_record(row)

                    # Determine county
                    if mongo_match:
                        self.stats['matched_records'] += 1
                        county = mongo_match.get('county', 'Unknown')
                    else:
                        # Fallback to zipcode lookup
                        zipcode = row.get('zip', '')
                        county = self.matcher.get_county_from_zipcode(zipcode)

                    if county == 'Unknown':
                        self.stats['missing_county'] += 1

                    # Build consolidated record
                    person_id = row.get('email', '') or f"{row.get('first_name', '')} {row.get('last_name', '')}"

                    record = ConsolidatedRecord(
                        person_id=person_id.strip(),
                        campaign_name=row.get('campaign_name', ''),
                        opened=row.get('opened', 'No'),
                        clicked=row.get('clicked', 'No'),
                        applied=0,
                        county=county,
                        zipcode=row.get('zip', ''),
                        address=row.get('address', ''),
                        name=f"{row.get('first_name', '')} {row.get('last_name', '')}".strip(),
                        email=row.get('email', ''),
                        cell=row.get('cell', ''),
                        estimated_income=mongo_match.get('estimated_income', -1) if mongo_match else -1,
                        energy_burden_kwh=mongo_match.get('energy_burden_kwh', -1) if mongo_match else -1,
                        total_energy_burden=mongo_match.get('total_energy_burden', -1) if mongo_match else -1
                    )

                    consolidated.append(record)
                    self.stats['output_records'] += 1

        return consolidated

    def write_output(self, records: List[ConsolidatedRecord]):
        """Write consolidated records to CSV."""
        log(__name__).info(f"Writing {len(records)} records to {self.output_file}...")

        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
            if records:
                fieldnames = list(asdict(records[0]).keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for record in records:
                    writer.writerow(asdict(record))

        log(__name__).info(f"Output complete: {self.output_file}")

    def print_statistics(self):
        """Print processing statistics."""
        print(f"\n{'='*60}")
        print(f"CSV Consolidation Statistics")
        print(f"{'='*60}")
        print(f"Total input records:        {self.stats['total_records']:,}")
        print(f"Engaged records (O or C):   {self.stats['engaged_records']:,}")
        print(f"Matched to MongoDB:         {self.stats['matched_records']:,}")
        print(f"Output records:             {self.stats['output_records']:,}")
        print(f"Missing county data:        {self.stats['missing_county']:,}")
        print(f"Match rate:                 {self.stats['matched_records']/max(1,self.stats['output_records'])*100:.1f}%")
        print(f"{'='*60}\n")

    def run(self):
        """Execute consolidation pipeline."""
        records = self.process_csv_files()
        self.write_output(records)
        self.print_statistics()


def main():
    parser = argparse.ArgumentParser(
        description='Consolidate EmailOctopus CSV files with MongoDB enrichment'
    )
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path(__file__).parent / 'data' / 'exports',
        help='Directory containing CSV files (default: ./data/exports)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).parent / 'data' / 'consolidated_output.csv',
        help='Output CSV file path (default: ./data/consolidated_output.csv)'
    )
    parser.add_argument(
        '--filter',
        choices=['all', 'engaged'],
        default='all',
        help='Filter mode: "all" for all records, "engaged" for opened OR clicked'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.input_dir.exists():
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)

    # Run consolidation
    consolidator = CSVConsolidator(args.input_dir, args.output, args.filter)
    consolidator.run()


if __name__ == '__main__':
    main()
