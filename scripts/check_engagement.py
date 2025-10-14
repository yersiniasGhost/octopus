"""
Check engagement counts in MongoDB vs CSV
"""
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
host = os.getenv('MONGODB_HOST', 'localhost')
port = int(os.getenv('MONGODB_PORT', '27017'))
db_name = os.getenv('MONGODB_DATABASE', 'emailoctopus_db')

client = MongoClient(host, port)
db = client[db_name]

# Campaign ID from the CSV filename
target_campaign_id = 'cf115430-61a1-11f0-89cc-1be24f0429c5'

print("="*70)
print("ENGAGEMENT ANALYSIS")
print("="*70)

# Total participants
total_participants = db.participants.count_documents({})
print(f"\nTotal participants in DB: {total_participants}")

# Engaged participants (all campaigns)
engaged_all = db.participants.count_documents({
    '$or': [
        {'engagement.opened': True},
        {'engagement.clicked': True}
    ]
})
print(f"Total engaged (opened OR clicked): {engaged_all}")

opened_all = db.participants.count_documents({'engagement.opened': True})
clicked_all = db.participants.count_documents({'engagement.clicked': True})
print(f"  - Opened: {opened_all}")
print(f"  - Clicked: {clicked_all}")

# Campaigns
campaigns = list(db.campaigns.find({}, {'campaign_id': 1, 'name': 1, 'status': 1}))
print(f"\nTotal campaigns: {len(campaigns)}")

# Specific campaign
print(f"\n{'='*70}")
print(f"TARGET CAMPAIGN: {target_campaign_id}")
print(f"{'='*70}")

campaign = db.campaigns.find_one({'campaign_id': target_campaign_id})
if campaign:
    print(f"Campaign name: {campaign.get('name', 'N/A')}")
    print(f"Status: {campaign.get('status', 'N/A')}")

# Participants for this campaign
total_in_campaign = db.participants.count_documents({'campaign_id': target_campaign_id})
print(f"\nTotal participants: {total_in_campaign}")

engaged_in_campaign = db.participants.count_documents({
    'campaign_id': target_campaign_id,
    '$or': [
        {'engagement.opened': True},
        {'engagement.clicked': True}
    ]
})
print(f"Engaged (opened OR clicked): {engaged_in_campaign}")

opened_in_campaign = db.participants.count_documents({
    'campaign_id': target_campaign_id,
    'engagement.opened': True
})
clicked_in_campaign = db.participants.count_documents({
    'campaign_id': target_campaign_id,
    'engagement.clicked': True
})
print(f"  - Opened: {opened_in_campaign}")
print(f"  - Clicked: {clicked_in_campaign}")

# CSV comparison
print(f"\n{'='*70}")
print("CSV FILE COUNTS (from earlier analysis)")
print(f"{'='*70}")
print("Total engaged (opened OR clicked): 87")
print("  - Opened: 53")
print("  - Clicked: 41")

print(f"\n{'='*70}")
print("DISCREPANCY")
print(f"{'='*70}")
print(f"MongoDB engaged: {engaged_in_campaign}")
print(f"CSV engaged: 87")
print(f"Difference: {engaged_in_campaign - 87}")

# Show breakdown by campaign
print(f"\n{'='*70}")
print("ALL CAMPAIGNS ENGAGEMENT BREAKDOWN")
print(f"{'='*70}")

for camp in campaigns:
    camp_id = camp.get('campaign_id')
    count = db.participants.count_documents({
        'campaign_id': camp_id,
        '$or': [
            {'engagement.opened': True},
            {'engagement.clicked': True}
        ]
    })
    if count > 0:
        print(f"{camp.get('name', 'Unknown'):50s}: {count:5d} engaged")

client.close()
