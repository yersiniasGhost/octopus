#!/usr/bin/env python3
"""
Test Enhanced Campaign Model

Tests the new multi-channel Campaign model with all 4 campaign types.
Creates sample campaigns for text, mailer, and letter types.

Usage:
    source venv/bin/activate
    python scripts/test_campaign_model.py
"""
import os
import sys
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.campaign import (
    Campaign,
    EmailStatistics,
    TextStatistics,
    MailerStatistics,
    LetterStatistics,
    CampaignStatCount
)

load_dotenv()


def test_existing_email_campaign():
    """Test that existing email campaigns load correctly"""
    print("=" * 80)
    print("Test 1: Load Existing Email Campaign")
    print("=" * 80)

    mongo_host = os.getenv('MONGODB_HOST', 'localhost')
    mongo_port = os.getenv('MONGODB_PORT', '27017')
    mongo_db = os.getenv('MONGODB_DATABASE', 'empower')

    client = MongoClient(f'mongodb://{mongo_host}:{mongo_port}/')
    db = client[mongo_db]

    # Load an existing email campaign
    campaign_data = db.campaigns.find_one({"campaign_type": "email"})

    if campaign_data:
        try:
            campaign = Campaign(**campaign_data)
            print(f"✅ Successfully loaded email campaign")
            print(f"   Name: {campaign.name}")
            print(f"   Type: {campaign.campaign_type}")
            print(f"   Subject: {campaign.subject}")
            print(f"   Statistics type: {type(campaign.statistics).__name__}")
            print(f"   Opened: {campaign.statistics.opened.unique}")
            return True
        except Exception as e:
            print(f"❌ Error loading campaign: {e}")
            return False
    else:
        print("❌ No email campaigns found")
        return False


def create_sample_text_campaign():
    """Create a sample text/SMS campaign"""
    print("\n" + "=" * 80)
    print("Test 2: Create Text/SMS Campaign")
    print("=" * 80)

    campaign = Campaign(
        campaign_id=str(uuid.uuid4()),
        name="OHCAC_Summer_Crisis_SMS_20251104",
        campaign_type="text",
        status="SENT",
        created_at=datetime.now(),
        sent_at=datetime.now(),
        message_body="Final days to apply for Ohio's Summer Energy Crisis Program! Visit our website to learn more.",
        sender_phone="+15551234567",
        sms_provider="Twilio",
        target_audience="OHCAC",
        cost_per_send=0.0075,
        total_cost=75.00,
        statistics=TextStatistics(
            sent=CampaignStatCount(unique=10000, total=10000),
            delivered=CampaignStatCount(unique=9850, total=9850),
            clicked=CampaignStatCount(unique=245, total=312),
            failed=CampaignStatCount(unique=150, total=150),
            opt_outs=CampaignStatCount(unique=12, total=12)
        )
    )

    print(f"✅ Created text campaign")
    print(f"   Name: {campaign.name}")
    print(f"   Type: {campaign.campaign_type}")
    print(f"   Message: {campaign.message_body[:50]}...")
    print(f"   Provider: {campaign.sms_provider}")
    print(f"   Statistics type: {type(campaign.statistics).__name__}")
    print(f"   Delivered: {campaign.statistics.delivered.unique}/{campaign.statistics.sent.unique}")
    print(f"   Click rate: {campaign.statistics.clicked.unique/campaign.statistics.delivered.unique*100:.1f}%")

    return campaign


def create_sample_mailer_campaign():
    """Create a sample physical mailer campaign"""
    print("\n" + "=" * 80)
    print("Test 3: Create Physical Mailer Campaign")
    print("=" * 80)

    campaign = Campaign(
        campaign_id=str(uuid.uuid4()),
        name="IMPACT_Energy_Savings_Mailer_20251104",
        campaign_type="mailer",
        status="SENT",
        created_at=datetime.now(),
        sent_at=datetime.now(),
        template_id="postcard_6x9_energy",
        print_vendor="Lob",
        postage_class="Standard",
        envelope_type="Postcard 6x9",
        color_printing=True,
        double_sided=True,
        target_audience="IMPACT",
        cost_per_send=0.68,
        total_cost=3400.00,
        statistics=MailerStatistics(
            printed=5000,
            mailed=5000,
            delivered=4750,
            returned=85,
            estimated_delivery_rate=95.0
        )
    )

    print(f"✅ Created mailer campaign")
    print(f"   Name: {campaign.name}")
    print(f"   Type: {campaign.campaign_type}")
    print(f"   Template: {campaign.template_id}")
    print(f"   Vendor: {campaign.print_vendor}")
    print(f"   Postage: {campaign.postage_class}")
    print(f"   Statistics type: {type(campaign.statistics).__name__}")
    print(f"   Mailed: {campaign.statistics.mailed}")
    print(f"   Delivery rate: {campaign.statistics.estimated_delivery_rate}%")
    print(f"   Cost per piece: ${campaign.cost_per_send}")

    return campaign


def create_sample_letter_campaign():
    """Create a sample letter campaign"""
    print("\n" + "=" * 80)
    print("Test 4: Create Letter Campaign")
    print("=" * 80)

    campaign = Campaign(
        campaign_id=str(uuid.uuid4()),
        name="COAD_Crisis_Application_Letter_20251104",
        campaign_type="letter",
        status="SENT",
        created_at=datetime.now(),
        sent_at=datetime.now(),
        template_id="letter_crisis_app_formal",
        print_vendor="PostGrid",
        postage_class="First Class",
        envelope_type="#10 Window",
        color_printing=False,
        double_sided=False,
        target_audience="COAD",
        cost_per_send=1.25,
        total_cost=1875.00,
        statistics=LetterStatistics(
            printed=1500,
            mailed=1500,
            delivered=1425,
            returned=42,
            certified_mail=0
        )
    )

    print(f"✅ Created letter campaign")
    print(f"   Name: {campaign.name}")
    print(f"   Type: {campaign.campaign_type}")
    print(f"   Template: {campaign.template_id}")
    print(f"   Vendor: {campaign.print_vendor}")
    print(f"   Postage: {campaign.postage_class}")
    print(f"   Envelope: {campaign.envelope_type}")
    print(f"   Statistics type: {type(campaign.statistics).__name__}")
    print(f"   Mailed: {campaign.statistics.mailed}")
    print(f"   Returned: {campaign.statistics.returned}")
    print(f"   Cost per letter: ${campaign.cost_per_send}")

    return campaign


def save_sample_campaigns(campaigns):
    """Save sample campaigns to database"""
    print("\n" + "=" * 80)
    print("Test 5: Save Sample Campaigns to Database")
    print("=" * 80)

    mongo_host = os.getenv('MONGODB_HOST', 'localhost')
    mongo_port = os.getenv('MONGODB_PORT', '27017')
    mongo_db = os.getenv('MONGODB_DATABASE', 'empower')

    client = MongoClient(f'mongodb://{mongo_host}:{mongo_port}/')
    db = client[mongo_db]

    saved_count = 0
    for campaign in campaigns:
        try:
            result = db.campaigns.insert_one(campaign.to_mongo_dict())
            print(f"✅ Saved {campaign.campaign_type} campaign: {campaign.name}")
            saved_count += 1
        except Exception as e:
            print(f"❌ Error saving campaign: {e}")

    print(f"\nSaved {saved_count}/{len(campaigns)} sample campaigns")

    # Show final counts by type
    print("\n📊 Campaign counts by type:")
    pipeline = [
        {
            "$group": {
                "_id": "$campaign_type",
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    type_counts = list(db.campaigns.aggregate(pipeline))
    total = 0
    for stat in type_counts:
        count = stat['count']
        total += count
        print(f"   {stat['_id']}: {count}")
    print(f"   Total: {total}")


def main():
    """Run all tests"""
    print("\n🧪 Testing Enhanced Campaign Model")
    print()

    # Test 1: Load existing email campaign
    success = test_existing_email_campaign()

    if not success:
        print("\n⚠️  Warning: Could not load existing email campaigns")

    # Test 2-4: Create sample campaigns
    text_campaign = create_sample_text_campaign()
    mailer_campaign = create_sample_mailer_campaign()
    letter_campaign = create_sample_letter_campaign()

    # Test 5: Save to database
    save_sample_campaigns([text_campaign, mailer_campaign, letter_campaign])

    print("\n" + "=" * 80)
    print("✅ All Tests Complete!")
    print("=" * 80)
    print()


if __name__ == '__main__':
    main()
