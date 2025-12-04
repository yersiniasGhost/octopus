#!/usr/bin/env python3
"""
Debug script to check MongoDB data availability

This script:
1. Connects to MongoDB using environment variables
2. Lists all available collections
3. Counts documents in key collections
4. Shows sample participant data
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pymongo import MongoClient
from src.utils.envvars import EnvVars


def main():
    """Debug data availability."""
    print("\n" + "🔍 " * 20)
    print("MONGODB DATA DEBUG")
    print("🔍 " * 20 + "\n")

    try:
        # Get environment variables
        env = EnvVars()
        host = env.get_env('MONGODB_HOST', 'localhost')
        port = int(env.get_env('MONGODB_PORT', '27017'))
        octopus_db_name = env.get_env('MONGODB_OCTOPUS')
        county_db_name = env.get_env('MONGODB_DATABASE')

        print(f"MongoDB Configuration:")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print(f"  Octopus DB (MONGODB_OCTOPUS): {octopus_db_name or 'NOT SET ⚠️'}")
        print(f"  County DB (MONGODB_DATABASE): {county_db_name or 'NOT SET ⚠️'}")
        print()

        if not octopus_db_name:
            print("❌ MONGODB_OCTOPUS environment variable is not set!")
            print("   This is required for participant and campaign data.")
            return 1

        if not county_db_name:
            print("❌ MONGODB_DATABASE environment variable is not set!")
            print("   This is required for demographic and property data.")
            return 1

        # Connect to MongoDB
        print("Connecting to MongoDB...")
        client = MongoClient(host, port)
        octopus_db = client[octopus_db_name]
        county_db = client[county_db_name]
        print(f"✅ Connected successfully\n")

        # List collections from Octopus DB
        print("=" * 60)
        print(f"OCTOPUS DB COLLECTIONS ({octopus_db_name})")
        print("=" * 60)
        octopus_collections = octopus_db.list_collection_names()
        print(f"Found {len(octopus_collections)} collections:\n")
        for coll in sorted(octopus_collections):
            count = octopus_db[coll].count_documents({})
            print(f"  - {coll}: {count:,} documents")

        # List collections from County DB
        print("\n" + "=" * 60)
        print(f"COUNTY DB COLLECTIONS ({county_db_name})")
        print("=" * 60)
        county_collections = county_db.list_collection_names()
        print(f"Found {len(county_collections)} collections:\n")
        for coll in sorted(county_collections):
            count = county_db[coll].count_documents({})
            print(f"  - {coll}: {count:,} documents")

        # Check participants collection (in Octopus DB)
        print("\n" + "=" * 60)
        print("PARTICIPANTS COLLECTION (Octopus DB)")
        print("=" * 60)

        participants_count = octopus_db.participants.count_documents({})
        print(f"Total participants: {participants_count:,}\n")

        if participants_count > 0:
            # Sample participant
            sample = octopus_db.participants.find_one()
            print("Sample participant document:")
            print("-" * 60)

            # Pretty print key fields
            if sample:
                print(f"  _id: {sample.get('_id')}")
                print(f"  campaign_id: {sample.get('campaign_id')}")
                print(f"  email_address: {sample.get('email_address')}")
                print(f"  contact_id: {sample.get('contact_id')}")

                # Check engagement data
                engagement = sample.get('engagement', {})
                print(f"\n  Engagement:")
                print(f"    opened: {engagement.get('opened', 'N/A')}")
                print(f"    clicked: {engagement.get('clicked', 'N/A')}")
                print(f"    bounced: {engagement.get('bounced', 'N/A')}")
                print(f"    complained: {engagement.get('complained', 'N/A')}")
                print(f"    unsubscribed: {engagement.get('unsubscribed', 'N/A')}")

                # Check fields
                fields = sample.get('fields', {})
                print(f"\n  Custom Fields:")
                for key, value in list(fields.items())[:5]:
                    print(f"    {key}: {value}")
                if len(fields) > 5:
                    print(f"    ... ({len(fields) - 5} more fields)")

            # Count by campaign
            print("\n" + "-" * 60)
            print("Participants by campaign:")
            pipeline = [
                {"$group": {"_id": "$campaign_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            for result in octopus_db.participants.aggregate(pipeline):
                print(f"  {result['_id']}: {result['count']:,} participants")

            # Check engagement stats
            print("\n" + "-" * 60)
            print("Engagement statistics:")
            opened_count = octopus_db.participants.count_documents({"engagement.opened": True})
            clicked_count = octopus_db.participants.count_documents({"engagement.clicked": True})
            print(f"  Opened: {opened_count:,} ({opened_count/participants_count*100:.1f}%)")
            print(f"  Clicked: {clicked_count:,} ({clicked_count/participants_count*100:.1f}%)")

        else:
            print("⚠️  No participants found in database!")
            print("\nPossible reasons:")
            print("  1. Database has not been synced yet")
            print("  2. Wrong database name in MONGODB_DATABASE")
            print("  3. Data is in different collections")
            print("\nTo sync data, run:")
            print("  python -m src.sync.campaign_sync")

        # Check campaigns collection (in Octopus DB)
        print("\n" + "=" * 60)
        print("CAMPAIGNS COLLECTION (Octopus DB)")
        print("=" * 60)

        campaigns_count = octopus_db.campaigns.count_documents({})
        print(f"Total campaigns: {campaigns_count:,}\n")

        if campaigns_count > 0:
            # List campaigns
            print("Available campaigns:")
            for campaign in octopus_db.campaigns.find().limit(10):
                campaign_id = campaign.get('campaign_id', 'Unknown')
                name = campaign.get('name', 'No name')
                status = campaign.get('status', 'Unknown')
                print(f"  - {campaign_id[:30]}: {name} [{status}]")
        else:
            print("⚠️  No campaigns found in database!")

        # Check demographic collections (in County DB)
        print("\n" + "=" * 60)
        print("DEMOGRAPHIC COLLECTIONS (County DB)")
        print("=" * 60)

        demographic_colls = [c for c in county_collections if 'Demographic' in c]
        if demographic_colls:
            print(f"Found {len(demographic_colls)} demographic collections:\n")
            for coll in demographic_colls:
                count = county_db[coll].count_documents({})
                print(f"  - {coll}: {count:,} documents")

                if count > 0:
                    # Sample document
                    sample = county_db[coll].find_one()
                    if sample:
                        print(f"    Sample parcel_id: {sample.get('parcel_id')}")
                        print(f"    Has energy_burden: {sample.get('total_energy_burden', 'N/A') != -1}")
                        print(f"    Has income: {sample.get('estimated_income', 'N/A') != -1}")
        else:
            print("⚠️  No demographic collections found!")

        # Check residential collections (in County DB)
        print("\n" + "=" * 60)
        print("RESIDENTIAL COLLECTIONS (County DB)")
        print("=" * 60)

        residential_colls = [c for c in county_collections if 'Residential' in c]
        if residential_colls:
            print(f"Found {len(residential_colls)} residential collections:\n")
            for coll in residential_colls:
                count = county_db[coll].count_documents({})
                print(f"  - {coll}: {count:,} documents")
        else:
            print("⚠️  No residential collections found!")

        print("\n" + "=" * 60)
        print("DEBUG COMPLETE")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
