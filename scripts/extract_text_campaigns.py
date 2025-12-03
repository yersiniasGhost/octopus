#!/usr/bin/env python3
"""
Extract text campaign data from Excel and import into MongoDB campaigns collection.

Reads text campaign statistics from Empower_Saves_Texts_All.xlsx (Stats sheet),
parses campaign metadata, and imports into MongoDB campaigns collection as type="text".

Usage:
    python scripts/extract_text_campaigns.py [--dry-run] [--output json|mongo] [--verbose]
"""

import sys
import re
import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.campaign import Campaign, TextStatistics, CampaignStatCount


def parse_shortened_name(name: str) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    """
    Parse campaign name in format: Text#_MessageKey_Agency_Time

    Examples:
        'Text1_Prequalified_Impact' → (1, 'Prequalified', 'Impact', None)
        'Text2_Money_OHCAC_Morning' → (2, 'Money', 'OHCAC', 'Morning')
        'Text15_Improvements' → (15, 'Improvements', 'NA', None)
        'Text35_Energy_Assistance_MVCAP' → (35, 'Energy_Assistance', 'MVCAP', None)
        'Text63_Time_Running_Out_IMPACT_morning' → (63, 'Time_Running_Out', 'IMPACT', 'morning')

    Args:
        name: Campaign shortened name from Excel

    Returns:
        Tuple of (text_number, message_key, agency, time_variant)
        Uses 'NA' for agency if not present in name
        Returns (None, None, None, None) if parsing fails completely
    """
    # Pattern: Text{number}_{key}_{agency}[_{time}]
    # Use non-greedy (.+?) for message_key to handle multi-word keys with underscores
    # Explicitly match known agencies: IMPACT, Impact, OHCAC, MVCAP, COAD, NA
    pattern = r'Text(\d+)_(.+?)_(IMPACT|Impact|OHCAC|MVCAP|COAD|NA)(?:_(.+))?$'
    match = re.match(pattern, name)

    if match:
        text_num = int(match.group(1))
        message_key = match.group(2)
        agency = match.group(3)
        time_variant = match.group(4)  # Optional, may be None
        return text_num, message_key, agency, time_variant

    # Fallback pattern for names without agency: Text{number}_{key}
    fallback_pattern = r'Text(\d+)_([^_]+)$'
    fallback_match = re.match(fallback_pattern, name)

    if fallback_match:
        text_num = int(fallback_match.group(1))
        message_key = fallback_match.group(2)
        agency = 'NA'  # Assign 'NA' for missing agency
        time_variant = None
        return text_num, message_key, agency, time_variant

    # If neither pattern matches, return None values
    return None, None, None, None


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """
    Parse datetime string from Excel format.

    Args:
        dt_str: DateTime string (e.g., '2025-05-02 17:13:48 GMT-0000')

    Returns:
        datetime object or None if parsing fails
    """
    if pd.isna(dt_str) or not dt_str:
        return None

    try:
        # Try parsing with timezone info first
        # Format: '2025-05-02 17:13:48 GMT-0000'
        dt_part = dt_str.split(' GMT')[0]
        return datetime.strptime(dt_part, '%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        try:
            # Fallback: try ISO format
            return datetime.fromisoformat(str(dt_str))
        except:
            return None


def extract_campaigns_from_excel(excel_path: Path, verbose: bool = False) -> List[Campaign]:
    """
    Extract text campaigns from Excel file.

    Args:
        excel_path: Path to Excel file
        verbose: Enable verbose output

    Returns:
        List of Campaign objects
    """
    if verbose:
        print(f"Reading Excel file: {excel_path}")

    # Read first sheet only (Stats sheet)
    df = pd.read_excel(excel_path, sheet_name=0)

    if verbose:
        print(f"Found {len(df)} rows in Excel file")

    campaigns = []
    skipped = 0

    for idx, row in df.iterrows():
        # Parse shortened name
        shortened_name = row['Shortened name']
        text_num, msg_key, agency, time_var = parse_shortened_name(shortened_name)

        if text_num is None:
            if verbose:
                print(f"  [SKIP] Row {idx}: Could not parse name '{shortened_name}'")
            skipped += 1
            continue

        # Parse timestamps
        sent_time = parse_datetime(row['sent_time'])
        update_time = parse_datetime(row['update_time'])

        if sent_time is None or update_time is None:
            if verbose:
                print(f"  [SKIP] Row {idx}: Missing required timestamps")
            skipped += 1
            continue

        # Create campaign object using unified Campaign model
        try:
            # Build TextStatistics
            sent_count = int(row['sent'])
            delivered_count = int(row['delivered'])
            replies_count = int(row['replies'])
            dnd_count = int(row['dnd'])

            statistics = TextStatistics(
                sent=CampaignStatCount(unique=sent_count, total=sent_count),
                delivered=CampaignStatCount(unique=delivered_count, total=delivered_count),
                clicked=CampaignStatCount(unique=replies_count, total=replies_count),  # Use replies as clicked
                failed=CampaignStatCount(unique=int(row['err']), total=int(row['err'])),
                opt_outs=CampaignStatCount(unique=dnd_count, total=dnd_count)
            )

            # Build campaign name from parsed components
            campaign_name = f"Text{text_num}_{msg_key}_{agency}"
            if time_var:
                campaign_name += f"_{time_var}"

            campaign = Campaign(
                campaign_id=str(row['campaignId']),
                name=campaign_name,
                campaign_type='text',
                status='SENT',  # Campaigns from Stats sheet are already sent
                created_at=sent_time,
                sent_at=sent_time,
                target_audience=agency,
                message_body=f"{msg_key} message campaign",
                statistics=statistics,
                synced_at=update_time
            )

            campaigns.append(campaign)

            if verbose:
                print(f"  [OK] Row {idx}: {campaign_name} "
                      f"(sent: {sent_count}, delivered: {delivered_count})")

        except Exception as e:
            if verbose:
                print(f"  [ERROR] Row {idx}: {str(e)}")
                import traceback
                traceback.print_exc()
            skipped += 1

    if verbose:
        print(f"\nExtraction complete: {len(campaigns)} campaigns extracted, {skipped} skipped")

    return campaigns


def save_to_mongodb(campaigns: List[Campaign], collection_name: str = 'campaigns',
                   verbose: bool = False) -> int:
    """
    Save campaigns to MongoDB.

    Args:
        campaigns: List of Campaign objects
        collection_name: MongoDB collection name
        verbose: Enable verbose output

    Returns:
        Number of campaigns inserted
    """
    if verbose:
        print(f"\nConnecting to MongoDB...")

    # Get MongoDB connection details from environment
    mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
    mongo_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
    mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

    if verbose:
        print(f"MongoDB: {mongo_host}:{mongo_port}/{mongo_db}")

    # Connect to MongoDB
    client = MongoClient(mongo_host, mongo_port)
    db = client[mongo_db]
    collection = db[collection_name]

    if verbose:
        print(f"Using collection: {collection_name}")
        print(f"Inserting {len(campaigns)} campaigns...")

    # Convert to dict format for MongoDB using to_mongo_dict()
    campaign_dicts = [campaign.to_mongo_dict() for campaign in campaigns]

    # Insert into MongoDB
    result = collection.insert_many(campaign_dicts)
    inserted_count = len(result.inserted_ids)

    if verbose:
        print(f"Successfully inserted {inserted_count} campaigns")
        print(f"Sample IDs: {result.inserted_ids[:3]}")

    client.close()
    return inserted_count


def save_to_json(campaigns: List[Campaign], output_path: Path, verbose: bool = False) -> None:
    """
    Save campaigns to JSON file.

    Args:
        campaigns: List of Campaign objects
        output_path: Output JSON file path
        verbose: Enable verbose output
    """
    if verbose:
        print(f"\nExporting to JSON: {output_path}")

    # Convert to dict format
    campaign_dicts = [campaign.to_mongo_dict() for campaign in campaigns]

    # Convert datetime objects to ISO format strings
    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(campaign_dicts, f, indent=2, default=json_serializer)

    if verbose:
        print(f"Exported {len(campaigns)} campaigns to {output_path}")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Extract text campaign data from Excel and import to MongoDB'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Parse and validate data without saving'
    )
    parser.add_argument(
        '--output',
        choices=['json', 'mongo', 'both'],
        default='mongo',
        help='Output destination (default: mongo)'
    )
    parser.add_argument(
        '--json-file',
        type=str,
        default='text_campaigns.json',
        help='JSON output filename (default: text_campaigns.json)'
    )
    parser.add_argument(
        '--collection',
        type=str,
        default='campaigns',
        help='MongoDB collection name (default: campaigns)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--excel-file',
        type=str,
        default='data/campaign_texting/Empower_Saves_Texts_All.xlsx',
        help='Path to Excel file (relative to project root)'
    )

    args = parser.parse_args()

    # Resolve paths
    project_root = Path(__file__).parent.parent
    excel_path = project_root / args.excel_file
    json_path = project_root / 'data' / args.json_file

    if not excel_path.exists():
        print(f"ERROR: Excel file not found: {excel_path}")
        return 1

    # Extract campaigns
    print(f"Extracting text campaigns from: {excel_path}")
    campaigns = extract_campaigns_from_excel(excel_path, verbose=args.verbose)

    if not campaigns:
        print("ERROR: No campaigns extracted")
        return 1

    print(f"\n{'='*60}")
    print(f"Extracted {len(campaigns)} text campaigns")
    print(f"{'='*60}")

    # Show sample
    if campaigns:
        sample = campaigns[0]
        print(f"\nSample campaign:")
        print(f"  Campaign ID: {sample.campaign_id}")
        print(f"  Name: {sample.name}")
        print(f"  Type: {sample.campaign_type}")
        print(f"  Agency: {sample.target_audience}")
        print(f"  Sent: {sample.statistics.sent.total}")
        print(f"  Delivered: {sample.statistics.delivered.total} ({sample.statistics.delivered.total/sample.statistics.sent.total*100:.1f}%)")
        print(f"  Replies: {sample.statistics.clicked.total}")

    # Handle dry-run
    if args.dry_run:
        print("\n[DRY RUN] Not saving data (use --output to save)")
        return 0

    # Save data
    if args.output in ['mongo', 'both']:
        try:
            count = save_to_mongodb(campaigns, args.collection, verbose=args.verbose)
            print(f"\n✓ Saved {count} campaigns to MongoDB collection '{args.collection}'")
        except Exception as e:
            print(f"\n✗ Failed to save to MongoDB: {e}")
            return 1

    if args.output in ['json', 'both']:
        try:
            save_to_json(campaigns, json_path, verbose=args.verbose)
            print(f"\n✓ Exported {len(campaigns)} campaigns to {json_path}")
        except Exception as e:
            print(f"\n✗ Failed to export to JSON: {e}")
            return 1

    print("\nExtraction complete!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
