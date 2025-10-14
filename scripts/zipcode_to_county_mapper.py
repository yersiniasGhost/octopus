#!/usr/bin/env python3
"""
Build zipcode-to-county mapping from MongoDB collections.
Extracts county names from collection names and creates cached lookup.
"""
import json
import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set
from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class ZipcodeCountyMapper:
    """Build and cache zipcode-to-county mapping from MongoDB."""

    CACHE_FILE = Path(__file__).parent / '..' / 'data' / 'zipcode_to_county_cache.json'

    def __init__(self):
        # Connect to remote MongoDB with demographic data
        host = os.getenv('MONGODB_HOST_RM', '192.168.1.156')
        port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        database = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        logger.info(f"Connecting to MongoDB at {host}:{port}, database: {database}")

        self.client = MongoClient(host, port, serverSelectionTimeoutMS=5000)
        self.db = self.client[database]
        self.zipcode_map: Dict[str, str] = {}
        self.zipcode_multi: Dict[str, Set[str]] = defaultdict(set)

    def extract_county_from_collection(self, collection_name: str) -> str:
        """
        Extract county name from collection name.
        Examples: 'OttawaResidential' -> 'Ottawa'
                  'OttawaDemographic' -> 'Ottawa'
        """
        # Remove common suffixes
        for suffix in ['Residential', 'Demographic', 'Loads', 'Gas', 'Electrical']:
            if collection_name.endswith(suffix):
                return collection_name[:-len(suffix)]
        return collection_name

    def build_mapping(self):
        """Build zipcode-to-county mapping from all demographic collections."""
        logger.info("Building zipcode-to-county mapping from MongoDB...")

        # Get all collection names
        collections = self.db.list_collection_names()
        logger.info(collections)
        logger.info('------------')
        demographic_collections = [c for c in collections if 'Demographic' in c or 'Residential' in c]

        logger.info(f"Found {len(demographic_collections)} demographic/residential collections")

        for collection_name in demographic_collections:
            county_name = self.extract_county_from_collection(collection_name)
            logger.info(f"Processing {collection_name} -> {county_name} County")

            collection = self.db[collection_name]

            # Get distinct zipcodes from this county's collection
            # Using parcel_zip field
            zipcodes = collection.distinct('parcel_zip')

            logger.info(f"  Found {len(zipcodes)} unique zipcodes in {county_name}")

            for zipcode in zipcodes:
                if zipcode and zipcode != -1:  # Skip invalid zipcodes
                    zip_str = str(zipcode).zfill(5)  # Ensure 5 digits with leading zeros

                    # Track if zipcode appears in multiple counties
                    self.zipcode_multi[zip_str].add(county_name)

                    # Primary mapping (first occurrence wins)
                    if zip_str not in self.zipcode_map:
                        self.zipcode_map[zip_str] = county_name

        # Log multi-county zipcodes
        multi_county = {z: list(counties) for z, counties in self.zipcode_multi.items() if len(counties) > 1}
        if multi_county:
            logger.warning(f"Found {len(multi_county)} zipcodes spanning multiple counties")
            logger.debug(f"Multi-county zipcodes: {list(multi_county.items())[:5]}")

        logger.info(f"Mapping complete: {len(self.zipcode_map)} unique zipcodes mapped")
        return self.zipcode_map

    def save_cache(self):
        """Save mapping to JSON cache file."""
        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        cache_data = {
            'zipcode_map': self.zipcode_map,
            'multi_county': {z: list(counties) for z, counties in self.zipcode_multi.items() if len(counties) > 1}
        }

        with open(self.CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)

        logger.info(f"Cache saved to {self.CACHE_FILE}")

    @classmethod
    def load_cache(cls) -> Dict[str, str]:
        """Load cached mapping from file."""
        if not cls.CACHE_FILE.exists():
            raise FileNotFoundError(f"Cache file not found: {cls.CACHE_FILE}. Run mapper first.")

        with open(cls.CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        return cache_data['zipcode_map']

    def get_county_for_zipcode(self, zipcode: str) -> str:
        """Lookup county for a given zipcode."""
        zip_str = str(zipcode).zfill(5)
        return self.zipcode_map.get(zip_str, 'Unknown')


def main():
    """Build and save zipcode-to-county mapping."""
    mapper = ZipcodeCountyMapper()
    mapper.build_mapping()
    mapper.save_cache()

    # Print summary
    print(f"\n{'='*60}")
    print(f"Zipcode-to-County Mapping Complete")
    print(f"{'='*60}")
    print(f"Total zipcodes mapped: {len(mapper.zipcode_map)}")
    print(f"Multi-county zipcodes: {len([z for z, counties in mapper.zipcode_multi.items() if len(counties) > 1])}")
    print(f"Cache file: {mapper.CACHE_FILE}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
