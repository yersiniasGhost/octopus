#!/usr/bin/env python3
"""
Search for demographic/residential collections across all databases.
"""
import os
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

def find_demographic_collections():
    """Search for demographic/residential collections in all databases."""
    host_rm = os.getenv('MONGODB_HOST_RM')
    port_rm = int(os.getenv('MONGODB_PORT_RM', '27017'))

    if not host_rm:
        print("MONGODB_HOST_RM not configured in .env")
        return

    print(f"Connecting to {host_rm}:{port_rm}...")
    print()

    try:
        client = MongoClient(host_rm, port_rm, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection

        # Search each database for demographic/residential collections
        for db_name in client.list_database_names():
            # Skip system databases
            if db_name in ['admin', 'config', 'local']:
                continue

            db = client[db_name]
            collections = db.list_collection_names()

            # Filter for demographic/residential collections
            demographic_collections = [c for c in collections if 'Demographic' in c or 'Residential' in c]

            if demographic_collections:
                print("=" * 80)
                print(f"Database: {db_name}")
                print("=" * 80)
                print(f"\nFound {len(demographic_collections)} demographic/residential collections:\n")

                for coll_name in sorted(demographic_collections):
                    try:
                        count = db[coll_name].estimated_document_count()
                        # Get a sample document to check structure
                        sample = db[coll_name].find_one()
                        has_parcel_zip = 'parcel_zip' in sample if sample else False

                        print(f"  - {coll_name}: {count:,} documents (parcel_zip: {has_parcel_zip})")
                    except Exception as e:
                        print(f"  - {coll_name}: ERROR - {e}")

                print(f"\nTotal: {len(demographic_collections)} collections")
                print()

        client.close()

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    find_demographic_collections()
