#!/usr/bin/env python3
"""
Tool: Create Text Campaign

Creates a text campaign record in MongoDB campaigns collection.
This is a reusable tool for setting up text/SMS campaigns.

Usage:
    python scripts/create_text_campaign_tool.py --name "Text1_Prequalified_Impact" --agency "IMPACT"
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv
import uuid

from src.models.campaign import Campaign, TextStatistics

load_dotenv()


def create_text_campaign(name: str, agency: str = "IMPACT", description: str = None) -> str:
    """
    Create a text campaign in MongoDB

    Args:
        name: Campaign name
        agency: Target agency/organization
        description: Optional campaign description

    Returns:
        Campaign ID (MongoDB _id)
    """
    # Connect to MongoDB
    mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
    mongo_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
    mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

    print(f"Connecting to MongoDB: {mongo_host}:{mongo_port}/{mongo_db}")
    client = MongoClient(mongo_host, mongo_port)
    db = client[mongo_db]
    campaigns_coll = db['campaigns']

    # Check if campaign already exists
    existing = campaigns_coll.find_one({'name': name, 'campaign_type': 'text'})
    if existing:
        campaign_id = str(existing['_id'])
        print(f"✅ Campaign '{name}' already exists with ID: {campaign_id}")
        client.close()
        return campaign_id

    # Create campaign
    campaign = Campaign(
        campaign_id=str(uuid.uuid4()),  # Generate UUID
        name=name,
        campaign_type='text',
        status='SENT',  # Mark as sent since we're importing historical data
        created_at=datetime.now(),
        sent_at=datetime.now(),
        target_audience=agency,
        message_body=description or f"Text campaign for {agency}",
        statistics=TextStatistics(),  # Will be updated during import
        synced_at=datetime.now()
    )

    # Insert into MongoDB
    result = campaigns_coll.insert_one(campaign.to_mongo_dict())
    campaign_id = str(result.inserted_id)

    print(f"✅ Created campaign '{name}' with ID: {campaign_id}")
    client.close()

    return campaign_id


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Create text campaign in MongoDB')
    parser.add_argument('--name', required=True, help='Campaign name')
    parser.add_argument('--agency', default='IMPACT', help='Target agency')
    parser.add_argument('--description', help='Campaign description')

    args = parser.parse_args()

    campaign_id = create_text_campaign(args.name, args.agency, args.description)
    print(f"\nCampaign ID: {campaign_id}")
