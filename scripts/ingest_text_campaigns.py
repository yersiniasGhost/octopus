#!/usr/bin/env python3
"""
Ingest text campaigns from RumbleUp/texting platform into campaign_data database.

Reads from: data/campaign_texting/compact/campaigns.csv
Writes to: campaign_data.campaigns collection

Usage:
    python scripts/ingest_text_campaigns.py [--dry-run]
"""
import argparse
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
import sys


def parse_timestamp(ts_str: str) -> datetime:
    """Parse timestamp string like '2025-05-02 17:16:42 GMT-0000'"""
    if pd.isna(ts_str):
        return None
    try:
        # Remove GMT-0000 suffix and parse
        clean = ts_str.replace(' GMT-0000', '').replace(' GMT+0000', '')
        return datetime.strptime(clean, '%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        return None


def build_campaign_doc(row: pd.Series) -> dict:
    """Build Campaign document from CSV row"""
    action = int(row['action'])

    return {
        'campaign_id': f"text_{action}",
        'name': row['Full name'] if pd.notna(row.get('Full name')) else row['Shortened name'],
        'agency': row['account'] if pd.notna(row.get('account')) else 'Ohio Partners for Affordable Energy',
        'channel': 'text',
        'message_type': row['type'] if pd.notna(row.get('type')) else 'SMS',
        'sent_at': parse_timestamp(row['sent_time']),
        'source_system': 'rumbleup',
        'source_file': 'Empower_Saves_Texts_All_stats.csv',
        'statistics': {
            'total_sent': int(row['sent']) if pd.notna(row.get('sent')) else 0,
            'delivered': int(row['delivered']) if pd.notna(row.get('delivered')) else 0,
            'received': int(row['received']) if pd.notna(row.get('received')) else 0,
            'dnd': int(row['dnd']) if pd.notna(row.get('dnd')) else 0,
            'bad': int(row['bad']) if pd.notna(row.get('bad')) else 0,
            'spam': int(row['spam']) if pd.notna(row.get('spam')) else 0,
            'landline': int(row['landline']) if pd.notna(row.get('landline')) else 0,
            'err': int(row['err']) if pd.notna(row.get('err')) else 0,
            'skipped': int(row['skipped']) if pd.notna(row.get('skipped')) else 0,
            'replies': int(row['replies']) if pd.notna(row.get('replies')) else 0,
            'engaged': int(row['replies']) if pd.notna(row.get('replies')) else 0,
            'receive_rate': float(row['delivered_percent']) / 100 if pd.notna(row.get('delivered_percent')) else 0.0,
            'engage_rate': float(row['replies_percent']) / 100 if pd.notna(row.get('replies_percent')) else 0.0,
        },
        'created_at': datetime.utcnow(),
        'synced_at': datetime.utcnow(),
        # Store action number for easy reference during exposure ingestion
        '_action_number': action,
    }


def main():
    parser = argparse.ArgumentParser(description='Ingest text campaigns into campaign_data')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing to database')
    args = parser.parse_args()

    print("=" * 80)
    print("TEXT CAMPAIGN INGESTION")
    print("=" * 80)

    # Load campaign data
    print("\n📥 Loading campaign data...")
    campaigns_df = pd.read_csv('/home/yersinia/devel/octopus/data/campaign_texting/compact/campaigns.csv')
    print(f"   Loaded {len(campaigns_df)} campaigns")

    # Connect to database
    client = MongoClient('localhost', 27017)
    db = client['campaign_data']

    # Check existing text campaigns
    existing_text = db.campaigns.count_documents({'channel': 'text'})
    print(f"\n📊 Existing text campaigns in database: {existing_text}")

    # Process campaigns
    print(f"\n{'📋 DRY-RUN MODE - No changes will be made' if args.dry_run else '💾 LIVE MODE - Writing to database'}")
    print("-" * 60)

    inserted = 0
    updated = 0
    errors = 0

    for idx, row in campaigns_df.iterrows():
        try:
            doc = build_campaign_doc(row)

            if args.dry_run:
                print(f"  Would upsert: {doc['campaign_id']} - {doc['name'][:50]}...")
            else:
                result = db.campaigns.update_one(
                    {'campaign_id': doc['campaign_id']},
                    {'$set': doc},
                    upsert=True
                )
                if result.upserted_id:
                    inserted += 1
                elif result.modified_count > 0:
                    updated += 1

        except Exception as e:
            print(f"  ❌ Error processing action {row.get('action')}: {e}")
            errors += 1

    # Summary
    print("\n" + "=" * 80)
    print("📊 INGESTION SUMMARY")
    print("=" * 80)

    if args.dry_run:
        print(f"\n  Campaigns to process: {len(campaigns_df)}")
        print("\n  Run without --dry-run to execute ingestion")
    else:
        print(f"\n  Inserted: {inserted}")
        print(f"  Updated:  {updated}")
        print(f"  Errors:   {errors}")

        # Verify
        total_text = db.campaigns.count_documents({'channel': 'text'})
        total_all = db.campaigns.count_documents({})
        print(f"\n  Total text campaigns now: {total_text}")
        print(f"  Total all campaigns: {total_all}")

    client.close()
    print("\n✅ Done!")

    return 0 if errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
