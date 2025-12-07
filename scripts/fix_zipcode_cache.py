#!/usr/bin/env python3
"""
Fix the corrupted zipcode_to_county_cache.json

The current cache has bad data - AthensCountyDemographic contains ZIP codes from
all over the US, causing incorrect county mappings.

This script:
1. Queries each county collection for distinct ZIP codes
2. Uses authoritative Ohio ZIP code ranges to validate
3. Gives priority to correct county when ZIP appears in multiple collections
4. Removes non-Ohio ZIP codes from the mapping
"""
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, List, Tuple

from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / '.env')

# Ohio ZIP code ranges by county (authoritative data)
# Source: USPS ZIP code database for Ohio
OHIO_COUNTY_ZIP_RANGES = {
    'RichlandCounty': [
        (44901, 44907),  # Mansfield and surrounding
    ],
    'MarionCounty': [
        (43301, 43302),  # Marion
        (43314, 43322),  # Surrounding areas
        (43337, 43337),  # Prospect
    ],
    'MorrowCounty': [
        (43003, 43003),  # Ashley
        (43011, 43011),  # Centerburg
        (43019, 43019),  # Fredericktown
        (43314, 43315),  # Cardington
        (43338, 43338),  # Sparta
        (43340, 43340),  # Edison
        (43341, 43341),  # Marengo
        (43344, 43344),  # Mt. Gilead area
    ],
    'FranklinCounty': [
        (43001, 43004),  # Bexley, Blacklick
        (43016, 43017),  # Dublin
        (43026, 43026),  # Hilliard
        (43054, 43054),  # New Albany
        (43065, 43065),  # Powell
        (43068, 43068),  # Reynoldsburg
        (43081, 43082),  # Westerville
        (43085, 43085),  # Worthington
        (43110, 43110),  # Canal Winchester
        (43119, 43119),  # Galloway
        (43123, 43123),  # Grove City
        (43125, 43125),  # Groveport
        (43137, 43137),  # Lockbourne
        (43146, 43147),  # Commercial Point, Pickerington
        (43201, 43240),  # Columbus main
    ],
    'AthensCounty': [
        (45701, 45701),  # Athens
        (45710, 45780),  # Athens County area
    ],
    'FayetteCounty': [
        (43101, 43101),  # Bloomingburg
        (43115, 43115),  # Frankfort
        (43127, 43128),  # Jeffersonville, Greenfield
        (43145, 43145),  # Midland
        (43160, 43160),  # Washington Court House
    ],
    'OttawaCounty': [
        (43412, 43412),  # Curtice
        (43434, 43434),  # Genoa
        (43438, 43440),  # Lakeside, Marblehead, Oak Harbor
        (43449, 43449),  # Port Clinton
        (43452, 43452),  # Put-in-Bay
        (43456, 43456),  # Catawba Island
        (43464, 43464),  # Rocky Ridge
    ],
    'HuronCounty': [
        (44811, 44811),  # Bellevue
        (44817, 44817),  # Bloomville
        (44826, 44826),  # Collins
        (44839, 44839),  # Huron
        (44846, 44846),  # Milan
        (44847, 44847),  # Monroeville
        (44851, 44851),  # New London
        (44857, 44857),  # Norwalk
        (44865, 44865),  # Plymouth
        (44889, 44889),  # Willard
    ],
    'MontgomeryCounty': [
        (45301, 45301),  # Brookville
        (45305, 45306),  # Centerville, Clayton
        (45309, 45309),  # Englewood
        (45315, 45315),  # Clayton
        (45322, 45322),  # Englewood
        (45324, 45325),  # Fairborn
        (45327, 45327),  # Germantown
        (45342, 45342),  # Miamisburg
        (45344, 45344),  # New Carlisle
        (45371, 45371),  # Tipp City
        (45377, 45377),  # Vandalia
        (45381, 45381),  # West Carrollton
        (45384, 45385),  # West Milton, Xenia
        (45401, 45490),  # Dayton area
    ],
}


def is_ohio_zip(zipcode: int) -> bool:
    """Check if ZIP code is in Ohio (43xxx-45xxx range)"""
    return 43000 <= zipcode <= 45999


def get_authoritative_county(zipcode: int) -> str:
    """Get the authoritative county for a ZIP code based on known ranges"""
    for county, ranges in OHIO_COUNTY_ZIP_RANGES.items():
        for start, end in ranges:
            if start <= zipcode <= end:
                return county
    return None


def main():
    """Rebuild the zipcode cache with correct mappings"""
    # Connect to MongoDB
    host = os.getenv('MONGODB_HOST_RM', '192.168.1.156')
    port = int(os.getenv('MONGODB_PORT_RM', '27017'))
    database = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

    print(f"Connecting to MongoDB: {host}:{port}/{database}")
    client = MongoClient(host, port, serverSelectionTimeoutMS=5000)
    db = client[database]

    # Get all demographic/residential collections
    collections = db.list_collection_names()
    target_collections = [c for c in collections if 'Demographic' in c or 'Residential' in c]

    print(f"\nFound {len(target_collections)} collections to process:")
    for c in sorted(target_collections):
        print(f"  - {c}")

    # Collect ZIP codes from each county
    county_zips: Dict[str, Set[int]] = defaultdict(set)
    zip_counties: Dict[int, Set[str]] = defaultdict(set)

    print("\nExtracting ZIP codes from collections...")
    for coll_name in target_collections:
        # Extract county name from collection
        county = coll_name.replace('Demographic', '').replace('Residential', '')
        if not county.endswith('County'):
            county = f"{county}County"

        collection = db[coll_name]

        # Get distinct ZIP codes
        zips = collection.distinct('parcel_zip')

        ohio_zips = []
        non_ohio_zips = []

        for z in zips:
            if z and z != -1:
                try:
                    zip_int = int(z)
                    if is_ohio_zip(zip_int):
                        ohio_zips.append(zip_int)
                        county_zips[county].add(zip_int)
                        zip_counties[zip_int].add(county)
                    else:
                        non_ohio_zips.append(zip_int)
                except (ValueError, TypeError):
                    pass

        print(f"  {coll_name}: {len(ohio_zips)} Ohio ZIPs, {len(non_ohio_zips)} non-Ohio (ignored)")

    # Build the corrected mapping
    print("\nBuilding corrected ZIP → County mapping...")
    zipcode_map: Dict[str, str] = {}
    multi_county: Dict[str, List[str]] = {}

    # Statistics
    stats = {
        'total_zips': 0,
        'single_county': 0,
        'multi_county': 0,
        'authoritative_override': 0,
    }

    for zip_code in sorted(zip_counties.keys()):
        counties = zip_counties[zip_code]
        zip_str = str(zip_code).zfill(5)
        stats['total_zips'] += 1

        if len(counties) == 1:
            # Single county - use it
            zipcode_map[zip_str] = list(counties)[0]
            stats['single_county'] += 1
        else:
            # Multiple counties claim this ZIP
            stats['multi_county'] += 1
            multi_county[zip_str] = sorted(list(counties))

            # Check authoritative mapping first
            auth_county = get_authoritative_county(zip_code)
            if auth_county and auth_county in counties:
                zipcode_map[zip_str] = auth_county
                stats['authoritative_override'] += 1
                print(f"    ZIP {zip_str}: Using authoritative → {auth_county} (was: {counties})")
            else:
                # Prefer non-Athens county (Athens has bad data)
                non_athens = [c for c in counties if c != 'AthensCounty']
                if non_athens:
                    # Use alphabetically first non-Athens county
                    zipcode_map[zip_str] = sorted(non_athens)[0]
                    print(f"    ZIP {zip_str}: Preferring {sorted(non_athens)[0]} over AthensCounty")
                else:
                    zipcode_map[zip_str] = sorted(list(counties))[0]

    # Print statistics
    print(f"\n{'='*60}")
    print("CACHE REBUILD STATISTICS")
    print(f"{'='*60}")
    print(f"Total Ohio ZIP codes: {stats['total_zips']}")
    print(f"Single county mapping: {stats['single_county']}")
    print(f"Multi-county conflicts: {stats['multi_county']}")
    print(f"Authoritative overrides: {stats['authoritative_override']}")

    # Show county distribution
    print(f"\nZIP codes by county:")
    county_counts = defaultdict(int)
    for county in zipcode_map.values():
        county_counts[county] += 1
    for county, count in sorted(county_counts.items(), key=lambda x: -x[1]):
        print(f"  {county}: {count} ZIPs")

    # Save the cache
    cache_path = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'
    cache_data = {
        'zipcode_map': zipcode_map,
        'multi_county': multi_county
    }

    # Backup the old cache
    backup_path = cache_path.with_suffix('.json.bak')
    if cache_path.exists():
        import shutil
        shutil.copy(cache_path, backup_path)
        print(f"\nBacked up old cache to: {backup_path}")

    with open(cache_path, 'w') as f:
        json.dump(cache_data, f, indent=2, sort_keys=True)

    print(f"Saved corrected cache to: {cache_path}")
    print(f"{'='*60}\n")

    # Verify specific problem ZIPs
    print("Verification of previously problematic ZIPs:")
    problem_zips = ['44903', '44904', '43302', '43315']
    for z in problem_zips:
        county = zipcode_map.get(z, 'NOT FOUND')
        multi = multi_county.get(z, [])
        print(f"  {z} → {county}" + (f" (also in: {multi})" if multi else ""))

    client.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
