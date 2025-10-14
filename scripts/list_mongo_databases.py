#!/usr/bin/env python3
"""
List all MongoDB databases and collections to diagnose connection issues.
"""
import sys
from pathlib import Path
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

def list_databases_and_collections():
    """List all databases and their collections."""
    # Try standard connection
    print("=" * 80)
    print("STANDARD MongoDB Connection (MONGODB_HOST)")
    print("=" * 80)
    host = os.getenv('MONGODB_HOST', 'localhost')
    port = int(os.getenv('MONGODB_PORT', '27017'))
    database = os.getenv('MONGODB_DATABASE', 'emailoctopus_db')

    print(f"Host: {host}:{port}")
    print(f"Database: {database}")
    print()

    try:
        client = MongoClient(host, port, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection

        # List all databases
        print("Available Databases:")
        for db_name in client.list_database_names():
            print(f"  - {db_name}")

        print(f"\nCollections in '{database}':")
        db = client[database]
        collections = db.list_collection_names()
        for coll_name in collections:
            count = db[coll_name].estimated_document_count()
            print(f"  - {coll_name}: {count:,} documents")

        print(f"\nTotal collections: {len(collections)}")

        client.close()

    except Exception as e:
        print(f"ERROR connecting to standard MongoDB: {e}")

    # Try _RM connection
    print("\n" + "=" * 80)
    print("REMOTE MongoDB Connection (MONGODB_HOST_RM)")
    print("=" * 80)
    host_rm = os.getenv('MONGODB_HOST_RM')
    port_rm = int(os.getenv('MONGODB_PORT_RM', '27017'))
    database_rm = os.getenv('MONGODB_DATABASE_RM')

    if not host_rm:
        print("MONGODB_HOST_RM not configured in .env")
        return

    print(f"Host: {host_rm}:{port_rm}")
    print(f"Database: {database_rm}")
    print()

    try:
        client_rm = MongoClient(host_rm, port_rm, serverSelectionTimeoutMS=5000)
        client_rm.server_info()  # Test connection

        # List all databases
        print("Available Databases:")
        for db_name in client_rm.list_database_names():
            print(f"  - {db_name}")

        if database_rm:
            print(f"\nCollections in '{database_rm}':")
            db_rm = client_rm[database_rm]
            collections_rm = db_rm.list_collection_names()

            # Separate demographic/residential from others
            demographic_collections = [c for c in collections_rm if 'Demographic' in c or 'Residential' in c]
            other_collections = [c for c in collections_rm if c not in demographic_collections]

            print(f"\nDemographic/Residential Collections ({len(demographic_collections)}):")
            for coll_name in sorted(demographic_collections):
                count = db_rm[coll_name].estimated_document_count()
                print(f"  - {coll_name}: {count:,} documents")

            if other_collections:
                print(f"\nOther Collections ({len(other_collections)}):")
                for coll_name in sorted(other_collections):
                    count = db_rm[coll_name].estimated_document_count()
                    print(f"  - {coll_name}: {count:,} documents")

            print(f"\nTotal collections: {len(collections_rm)}")

        client_rm.close()

    except Exception as e:
        print(f"ERROR connecting to remote MongoDB: {e}")

if __name__ == '__main__':
    list_databases_and_collections()
