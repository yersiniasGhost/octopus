#!/usr/bin/env python3
"""
Migrate Existing Campaigns to Add campaign_type Field

This script adds campaign_type='email' to all existing campaigns in the database
that don't have a campaign_type field yet (existing EmailOctopus campaigns).

Usage:
    source venv/bin/activate
    python scripts/migrate_campaigns_add_type.py
"""
import os
import sys
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()


def main():
    """Main migration function"""
    # Connect to MongoDB (local instance for EmailOctopus data)
    mongo_host = os.getenv('MONGODB_HOST', 'localhost')
    mongo_port = os.getenv('MONGODB_PORT', '27017')
    mongo_db = os.getenv('MONGODB_DATABASE', 'empower')

    mongo_uri = f'mongodb://{mongo_host}:{mongo_port}/'

    print("=" * 80)
    print("Campaign Type Migration")
    print("=" * 80)
    print(f"📡 Connecting to: {mongo_uri}")
    print(f"🗄️  Database: {mongo_db}")
    print()

    client = MongoClient(mongo_uri)
    db = client[mongo_db]
    campaigns_collection = db['campaigns']

    # Check total campaigns
    total_campaigns = campaigns_collection.count_documents({})
    print(f"Total campaigns in database: {total_campaigns}")

    # Check campaigns without campaign_type
    missing_type = campaigns_collection.count_documents({"campaign_type": {"$exists": False}})
    print(f"Campaigns without campaign_type: {missing_type}")
    print()

    if missing_type == 0:
        print("✅ All campaigns already have campaign_type field. No migration needed.")
        return

    # Show sample campaign before migration
    print("📄 Sample campaign BEFORE migration:")
    sample_before = campaigns_collection.find_one({"campaign_type": {"$exists": False}})
    if sample_before:
        print(f"   Name: {sample_before.get('name', 'N/A')}")
        print(f"   Fields: {list(sample_before.keys())}")
        print(f"   Has campaign_type: {'campaign_type' in sample_before}")
    print()

    # Perform migration
    print("🔄 Starting migration...")
    print()

    result = campaigns_collection.update_many(
        {"campaign_type": {"$exists": False}},
        {
            "$set": {
                "campaign_type": "email",
                "migrated_at": datetime.now()
            }
        }
    )

    print("=" * 80)
    print("✅ Migration Complete!")
    print("=" * 80)
    print(f"Matched documents: {result.matched_count}")
    print(f"Modified documents: {result.modified_count}")
    print()

    # Verify migration
    print("🔍 Verifying migration...")

    # Count by campaign_type
    type_counts = list(campaigns_collection.aggregate([
        {
            "$group": {
                "_id": "$campaign_type",
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"count": -1}}
    ]))

    print("\nCampaigns by type:")
    for stat in type_counts:
        campaign_type = stat['_id'] if stat['_id'] else 'null'
        count = stat['count']
        print(f"  {campaign_type}: {count}")

    # Show sample campaign after migration
    print("\n📄 Sample campaign AFTER migration:")
    sample_after = campaigns_collection.find_one({"campaign_type": "email"})
    if sample_after:
        print(f"   Name: {sample_after.get('name', 'N/A')}")
        print(f"   Campaign Type: {sample_after.get('campaign_type', 'N/A')}")
        print(f"   Migrated At: {sample_after.get('migrated_at', 'N/A')}")
    print()

    # Verify no campaigns are missing campaign_type
    still_missing = campaigns_collection.count_documents({"campaign_type": {"$exists": False}})
    if still_missing == 0:
        print("✅ SUCCESS: All campaigns now have campaign_type field")
    else:
        print(f"⚠️  WARNING: {still_missing} campaigns still missing campaign_type")

    print()


if __name__ == '__main__':
    main()
