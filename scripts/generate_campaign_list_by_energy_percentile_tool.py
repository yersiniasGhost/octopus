#!/usr/bin/env python3
"""
Generate Campaign Lists by Energy Consumption Percentile

Creates CSV files of households sorted by highest energy consumption percentile,
bucketed by square footage ranges. Designed for targeted outreach campaigns.

Usage:
    # Generate for Franklin County with default zip codes
    python scripts/generate_campaign_list_by_energy_percentile_tool.py

    # Specify custom zip codes
    python scripts/generate_campaign_list_by_energy_percentile_tool.py --zips 43210,43222,43211

    # Custom output folder
    python scripts/generate_campaign_list_by_energy_percentile_tool.py --output-dir data/my-campaign

    # Minimum percentile threshold (only include 70th percentile and above)
    python scripts/generate_campaign_list_by_energy_percentile_tool.py --min-percentile 70

    # Filter by heating load data (for weatherization targeting)
    python scripts/generate_campaign_list_by_energy_percentile_tool.py --heating-load

    # Heating load with R² quality filter (default 0.5)
    python scripts/generate_campaign_list_by_energy_percentile_tool.py --heating-load --min-r2 0.6
"""
import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from src.tools.mongo import get_empower_db
from src.utils.log_manager import LogManager

load_dotenv()
logger = LogManager().get_logger(__name__)

# Default configuration for Franklin County campaign
DEFAULT_COUNTY = 'Franklin'
DEFAULT_ZIP_CODES = [43210, 43222, 43211, 43203, 43201, 43223, 43224, 43205, 43219]

# Square footage bucket definitions
SQFT_BUCKETS = [
    (0, 1000, 'under_1000_sqft'),
    (1000, 1500, '1000_to_1500_sqft'),
    (1500, 2000, '1500_to_2000_sqft'),
    (2000, 2500, '2000_to_2500_sqft'),
    (2500, 3000, '2500_to_3000_sqft'),
    (3000, float('inf'), 'over_3000_sqft'),
]


@dataclass
class HouseholdRecord:
    """Record for a household with energy percentile data"""
    parcel_id: str
    name: str
    address: str
    city: str
    zipcode: int
    sqft: float
    energy_percentile: float
    year_built: int = 0
    phone: str = ''
    in_demographic_db: bool = False
    # Heating load fields (optional, populated when --heating-load is used)
    kwh_hl_slope: Optional[float] = None
    kwh_r2: Optional[float] = None

    def to_csv_row(self, include_heating_load: bool = False) -> Dict:
        """Convert to CSV row dictionary"""
        row = {
            'Name': self.name,
            'Address': self.address,
            'City': self.city,
            'Zipcode': self.zipcode,
            'Phone': self.phone,
            'Sqft': int(self.sqft) if self.sqft else '',
            'Year_Built': self.year_built if self.year_built and self.year_built > 1800 else '',
            'Energy_Percentile': round(self.energy_percentile, 1),
            'In_Demographic_DB': 'Y' if self.in_demographic_db else 'N'
        }
        if include_heating_load:
            row['Heating_Load_Slope'] = round(self.kwh_hl_slope, 6) if self.kwh_hl_slope else ''
            row['Heating_Load_R2'] = round(self.kwh_r2, 3) if self.kwh_r2 else ''
        return row


def get_sqft_bucket(sqft: float) -> Optional[str]:
    """Determine which sqft bucket a property belongs to"""
    if not sqft or sqft <= 0:
        return None
    for min_sqft, max_sqft, bucket_name in SQFT_BUCKETS:
        if min_sqft <= sqft < max_sqft:
            return bucket_name
    return None


def fetch_households_by_zip(db, county: str, zip_codes: List[int],
                            min_percentile: float = 0) -> List[HouseholdRecord]:
    """
    Fetch households from county collections filtered by zip codes.

    Uses MongoDB aggregation to join residential and demographic data,
    filter by zip codes and percentile, then sort by highest percentile.

    Optimized: Projects early, uses pipeline lookup with limited fields.
    """
    county_normalized = county.replace('County', '').strip()
    residential_coll = f"{county_normalized}CountyResidential"
    demographic_coll = f"{county_normalized}CountyDemographic"

    logger.debug(f"Fetching from {residential_coll} for zips: {zip_codes}")

    # Optimized pipeline: filter and project early, use targeted lookup
    pipeline = [
        # Stage 1: Filter by zip codes and require energy percentile
        {
            '$match': {
                'parcel_zip': {'$in': zip_codes},
                'energy_percentile.percentile_rank': {'$exists': True, '$gte': min_percentile},
                'living_area_total': {'$gt': 0}
            }
        },
        # Stage 2: Project only needed fields BEFORE lookup (reduces memory)
        {
            '$project': {
                'parcel_id': 1,
                'address': 1,
                'parcel_city': 1,
                'parcel_zip': 1,
                'living_area_total': 1,
                'age': 1,
                'parcel_owner': 1,
                'energy_percentile': '$energy_percentile.percentile_rank'
            }
        },
        # Stage 3: Lookup demographic data with pipeline (fetches only needed fields)
        {
            '$lookup': {
                'from': demographic_coll,
                'let': {'pid': '$parcel_id'},
                'pipeline': [
                    {'$match': {'$expr': {'$eq': ['$parcel_id', '$$pid']}}},
                    {'$project': {'customer_name': 1, 'mobile': 1, '_id': 0}}
                ],
                'as': 'demographic'
            }
        },
        # Stage 4: Unwind demographic (may not exist for all)
        {
            '$unwind': {
                'path': '$demographic',
                'preserveNullAndEmptyArrays': True
            }
        },
        # Stage 5: Final project with computed fields
        {
            '$project': {
                'parcel_id': 1,
                'address': 1,
                'parcel_city': 1,
                'parcel_zip': 1,
                'living_area_total': 1,
                'age': 1,
                'parcel_owner': 1,
                'energy_percentile': 1,
                'customer_name': '$demographic.customer_name',
                'mobile': '$demographic.mobile',
                'has_demographic': {'$cond': [{'$ifNull': ['$demographic.customer_name', False]}, True, False]}
            }
        },
        # Stage 6: Sort by highest percentile first
        {
            '$sort': {'energy_percentile': -1}
        }
    ]

    cursor = db[residential_coll].aggregate(pipeline, allowDiskUse=True, batchSize=1000)

    households = []
    for doc in cursor:
        # Get name: prefer parcel_owner from residential, fall back to customer_name from demographic
        name = doc.get('parcel_owner', '') or doc.get('customer_name', '') or ''

        # Get phone - clean up invalid values
        phone = doc.get('mobile', '')
        if phone in (None, '', -1, '-1', 0, '0'):
            phone = ''
        else:
            phone = str(phone)

        # Get year built from residential 'age' field
        year_built = doc.get('age', 0)
        if year_built in (None, -1, '-1'):
            year_built = 0
        else:
            year_built = int(year_built) if year_built else 0

        record = HouseholdRecord(
            parcel_id=doc.get('parcel_id', ''),
            name=name,
            address=doc.get('address', ''),
            city=doc.get('parcel_city', ''),
            zipcode=doc.get('parcel_zip', 0),
            sqft=doc.get('living_area_total', 0),
            energy_percentile=doc.get('energy_percentile', 0),
            year_built=year_built,
            phone=phone,
            in_demographic_db=doc.get('has_demographic', False)
        )
        households.append(record)

    logger.debug(f"Found {len(households)} households with energy percentile data")
    return households


def fetch_households_with_heating_load(db, county: str, zip_codes: List[int],
                                       min_percentile: float = 0,
                                       min_r2: float = 0.0) -> List[HouseholdRecord]:
    """
    Fetch households with heating load data from ThermalLoads collection.

    Joins residential, demographic, and thermal load data. Filters by:
    - ZIP codes
    - Minimum energy percentile
    - Positive heating load slope (kwh_hl_slope > 0)
    - Minimum R2 fit quality (kwh_r2, the joint heating+cooling model fit)

    Sorts by heating load slope (highest first) for weatherization targeting.

    Optimized: Projects early, uses pipeline lookups with limited fields.
    """
    county_normalized = county.replace('County', '').strip()
    residential_coll = f"{county_normalized}CountyResidential"
    demographic_coll = f"{county_normalized}CountyDemographic"
    thermal_coll = f"{county_normalized}ThermalLoads"

    logger.debug(f"Fetching from {residential_coll} + {thermal_coll} for zips: {zip_codes}")

    # Build match criteria
    match_criteria = {
        'parcel_zip': {'$in': zip_codes},
        'living_area_total': {'$gt': 0}
    }
    if min_percentile > 0:
        match_criteria['energy_percentile.percentile_rank'] = {'$exists': True, '$gte': min_percentile}

    # Optimized pipeline: project early, use targeted lookups
    pipeline = [
        # Stage 1: Filter by zip codes and basic criteria
        {'$match': match_criteria},
        # Stage 2: Project only needed fields BEFORE lookups
        {
            '$project': {
                'parcel_id': 1,
                'address': 1,
                'parcel_city': 1,
                'parcel_zip': 1,
                'living_area_total': 1,
                'age': 1,
                'parcel_owner': 1,
                'energy_percentile': '$energy_percentile.percentile_rank'
            }
        },
        # Stage 3: Lookup thermal load data (only needed fields, with filter)
        {
            '$lookup': {
                'from': thermal_coll,
                'let': {'pid': '$parcel_id'},
                'pipeline': [
                    {'$match': {
                        '$expr': {'$eq': ['$parcel_id', '$$pid']},
                        'kwh_hl_slope': {'$gt': 0},
                        'kwh_r2': {'$gte': min_r2}
                    }},
                    {'$project': {'kwh_hl_slope': 1, 'kwh_r2': 1, '_id': 0}}
                ],
                'as': 'thermal'
            }
        },
        # Stage 4: Unwind thermal (require match)
        {'$unwind': '$thermal'},
        # Stage 5: Lookup demographic data (only needed fields)
        {
            '$lookup': {
                'from': demographic_coll,
                'let': {'pid': '$parcel_id'},
                'pipeline': [
                    {'$match': {'$expr': {'$eq': ['$parcel_id', '$$pid']}}},
                    {'$project': {'customer_name': 1, 'mobile': 1, '_id': 0}}
                ],
                'as': 'demographic'
            }
        },
        # Stage 6: Unwind demographic (optional)
        {'$unwind': {'path': '$demographic', 'preserveNullAndEmptyArrays': True}},
        # Stage 7: Final project
        {
            '$project': {
                'parcel_id': 1,
                'address': 1,
                'parcel_city': 1,
                'parcel_zip': 1,
                'living_area_total': 1,
                'age': 1,
                'parcel_owner': 1,
                'energy_percentile': 1,
                'kwh_hl_slope': '$thermal.kwh_hl_slope',
                'kwh_r2': '$thermal.kwh_r2',
                'customer_name': '$demographic.customer_name',
                'mobile': '$demographic.mobile',
                'has_demographic': {'$cond': [{'$ifNull': ['$demographic.customer_name', False]}, True, False]}
            }
        },
        # Stage 8: Sort by highest heating load slope
        {'$sort': {'kwh_hl_slope': -1}}
    ]

    cursor = db[residential_coll].aggregate(pipeline, allowDiskUse=True, batchSize=1000)

    households = []
    for doc in cursor:
        name = doc.get('parcel_owner', '') or doc.get('customer_name', '') or ''

        phone = doc.get('mobile', '')
        if phone in (None, '', -1, '-1', 0, '0'):
            phone = ''
        else:
            phone = str(phone)

        year_built = doc.get('age', 0)
        if year_built in (None, -1, '-1'):
            year_built = 0
        else:
            year_built = int(year_built) if year_built else 0

        record = HouseholdRecord(
            parcel_id=doc.get('parcel_id', ''),
            name=name,
            address=doc.get('address', ''),
            city=doc.get('parcel_city', ''),
            zipcode=doc.get('parcel_zip', 0),
            sqft=doc.get('living_area_total', 0),
            energy_percentile=doc.get('energy_percentile', 0),
            year_built=year_built,
            phone=phone,
            in_demographic_db=doc.get('has_demographic', False),
            kwh_hl_slope=doc.get('kwh_hl_slope'),
            kwh_r2=doc.get('kwh_r2')
        )
        households.append(record)

    logger.debug(f"Found {len(households)} households with heating load data")
    return households


def bucket_households(households: List[HouseholdRecord]) -> Dict[str, List[HouseholdRecord]]:
    """Organize households into sqft buckets"""
    buckets: Dict[str, List[HouseholdRecord]] = {bucket[2]: [] for bucket in SQFT_BUCKETS}

    for household in households:
        bucket_name = get_sqft_bucket(household.sqft)
        if bucket_name:
            buckets[bucket_name].append(household)

    return buckets


def write_csv_file(filepath: Path, households: List[HouseholdRecord],
                   include_heating_load: bool = False) -> int:
    """Write households to CSV file, return count written"""
    if not households:
        return 0

    fieldnames = ['Name', 'Address', 'City', 'Zipcode', 'Phone', 'Sqft', 'Year_Built', 'Energy_Percentile', 'In_Demographic_DB']
    if include_heating_load:
        fieldnames.extend(['Heating_Load_Slope', 'Heating_Load_R2'])

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for household in households:
            writer.writerow(household.to_csv_row(include_heating_load=include_heating_load))

    return len(households)


def process_and_save_zip(db, county: str, zipcode: int, output_dir: Path,
                         min_percentile: float, heating_load: bool,
                         min_r2: float) -> Dict[str, int]:
    """
    Fetch, process, and save a single ZIP code's data immediately.

    Returns dict of {bucket_name: record_count} for this ZIP.
    """
    # Fetch households for this ZIP
    if heating_load:
        households = fetch_households_with_heating_load(db, county, [zipcode], min_percentile, min_r2)
    else:
        households = fetch_households_by_zip(db, county, [zipcode], min_percentile)

    if not households:
        return {}

    # Create ZIP folder and save immediately
    zip_dir = output_dir / str(zipcode)
    zip_dir.mkdir(parents=True, exist_ok=True)

    # Bucket by sqft
    buckets = bucket_households(households)

    zip_results = {}
    for bucket_name, bucket_households_list in buckets.items():
        if bucket_households_list:
            filepath = zip_dir / f"{bucket_name}.csv"
            count = write_csv_file(filepath, bucket_households_list, include_heating_load=heating_load)
            zip_results[bucket_name] = count

    # Write combined file for this zipcode
    combined_filepath = zip_dir / "all_households.csv"
    combined_count = write_csv_file(combined_filepath, households, include_heating_load=heating_load)
    zip_results['all_households'] = combined_count

    return zip_results


def generate_campaign_lists(county: str, zip_codes: List[int], output_dir: Path,
                            min_percentile: float = 0, heating_load: bool = False,
                            min_r2: float = 0.0) -> Dict[str, Dict[str, int]]:
    """
    Generate campaign list CSV files organized by zipcode folders, then bucketed by sqft.

    Processes and saves each ZIP code immediately after fetching (streaming approach).

    Args:
        county: County name
        zip_codes: List of ZIP codes to include
        output_dir: Output directory path
        min_percentile: Minimum energy percentile threshold
        heating_load: If True, filter by heating load data and include in output
        min_r2: Minimum R² for heating load regression fit (only used if heating_load=True)

    Returns dict of {zipcode: {bucket_name: record_count}}
    """
    db = get_empower_db()

    # Create output directory upfront
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Process each ZIP code: fetch, process, and save immediately
    for i, zipcode in enumerate(zip_codes):
        print(f"  [{i+1}/{len(zip_codes)}] Processing ZIP {zipcode}...", end=" ", flush=True)

        zip_results = process_and_save_zip(
            db, county, zipcode, output_dir, min_percentile, heating_load, min_r2
        )

        if zip_results:
            results[str(zipcode)] = zip_results
            total = zip_results.get('all_households', 0)
            print(f"✓ {total:,} records saved")
        else:
            print(f"✓ 0 records (no matches)")

    return results


def get_unique_output_dir(base_dir: Path) -> Path:
    """
    Get a unique output directory path, adding numeric suffix if needed.

    If base_dir exists, tries base_dir_1, base_dir_2, etc.
    """
    if not base_dir.exists():
        return base_dir

    counter = 1
    while True:
        candidate = base_dir.parent / f"{base_dir.name}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 100:
            raise RuntimeError(f"Could not find unique directory name after 100 attempts")


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate campaign lists sorted by energy consumption percentile',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--county', type=str, default=DEFAULT_COUNTY,
                        help=f'County name (default: {DEFAULT_COUNTY})')
    parser.add_argument('--zips', type=str, default=None,
                        help='Comma-separated zip codes (default: Franklin County target zips)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory (default: data/campaign-list-YYYYMMDD-county)')
    parser.add_argument('--min-percentile', type=float, default=0,
                        help='Minimum energy percentile to include (default: 0)')
    parser.add_argument('--heating-load', action='store_true',
                        help='Filter by heating load data (joins ThermalLoads collection)')
    parser.add_argument('--min-r2', type=float, default=0.0,
                        help='Minimum R² for heating load fit quality (default: 0.0, no filtering)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    return parser.parse_args()


def main():
    args = parse_args()

    # Parse zip codes
    if args.zips:
        zip_codes = [int(z.strip()) for z in args.zips.split(',')]
    else:
        zip_codes = DEFAULT_ZIP_CODES

    # Determine output directory
    if args.output_dir:
        base_output_dir = Path(args.output_dir)
    else:
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
        county_lower = args.county.lower()
        # Use different folder name for heating load mode
        if args.heating_load:
            folder_name = f'campaign-list-{date_str}-{county_lower}-heating-load'
        else:
            folder_name = f'campaign-list-{date_str}-{county_lower}'
        base_output_dir = Path(__file__).parent.parent / 'data' / folder_name

    # Ensure we don't overwrite existing output
    output_dir = get_unique_output_dir(base_output_dir)

    print(f"\n{'='*60}")
    if args.heating_load:
        print("CAMPAIGN LIST GENERATOR - Heating Load Mode")
    else:
        print("CAMPAIGN LIST GENERATOR - Energy Percentile")
    print(f"{'='*60}")
    print(f"County: {args.county}")
    print(f"Zip codes: {zip_codes}")
    print(f"Min percentile: {args.min_percentile}")
    if args.heating_load:
        print(f"Heating load filter: ENABLED")
        print(f"Min R² threshold: {args.min_r2}")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}\n")

    # Generate the lists
    results = generate_campaign_lists(
        county=args.county,
        zip_codes=zip_codes,
        output_dir=output_dir,
        min_percentile=args.min_percentile,
        heating_load=args.heating_load,
        min_r2=args.min_r2
    )

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY BY ZIPCODE")
    print(f"{'='*60}")

    grand_total = 0
    for zipcode, zip_results in sorted(results.items()):
        zip_total = zip_results.get('all_households', 0)
        grand_total += zip_total
        print(f"\n  Zipcode {zipcode}: {zip_total:,} total records")
        for bucket, count in sorted(zip_results.items()):
            if bucket != 'all_households':
                print(f"    └─ {bucket}: {count:,}")

    print(f"\n{'─'*60}")
    print(f"  GRAND TOTAL: {grand_total:,} records across {len(results)} zipcodes")
    print(f"\nOutput directory: {output_dir}")
    print(f"{'='*60}\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
