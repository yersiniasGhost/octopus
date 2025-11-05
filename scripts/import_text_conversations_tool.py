#!/usr/bin/env python3
"""
Tool: Import Text Conversations

Imports text conversation data from CSV into MongoDB participants collection.
Performs residence/demographic matching and creates participant engagement records.

This is a reusable tool for one-time imports/updates of text campaign data.

Usage:
    # Dry run (validation only)
    python scripts/import_text_conversations_tool.py --dry-run --verbose

    # Import conversations
    python scripts/import_text_conversations_tool.py --campaign-id 690b0058eadaad6f0e0dbfb3

    # Import with specific CSV file
    python scripts/import_text_conversations_tool.py --csv data/campaign_texting/custom.csv
"""
import os
import sys
import json
import re
import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv
from bson import ObjectId

from src.models.participant import Participant, TextEngagement
from src.models.common import ResidenceReference, DemographicReference
from src.models.campaign import Campaign, TextStatistics, CampaignStatCount
from src.tools.residence_matcher import ResidenceMatcher, PhoneNormalizer

load_dotenv()

# Default paths
DEFAULT_CSV = Path(__file__).parent.parent / 'data' / 'campaign_texting' / 'Empower_Saves_Texts_All.csv'
ZIPCODE_COUNTY_MAP = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'


class ConversationImporter:
    """Import text conversations with residence matching"""

    def __init__(self, csv_path: Path, campaign_id: str, dry_run: bool = False, verbose: bool = False, limit: Optional[int] = None):
        self.csv_path = csv_path
        self.campaign_id = campaign_id
        self.dry_run = dry_run
        self.verbose = verbose
        self.limit = limit

        # MongoDB connection
        self.mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        print(f"Connecting to MongoDB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db}")
        self.client = MongoClient(self.mongo_host, self.mongo_port)
        self.db = self.client[self.mongo_db]

        # Load zipcode mapping
        with open(ZIPCODE_COUNTY_MAP, 'r') as f:
            data = json.load(f)
            self.zipcode_map = data.get('zipcode_map', {})

        # Statistics
        self.stats = {
            'total_conversations': 0,
            'total_contacts': 0,
            'matched_residence': 0,
            'matched_demographic': 0,
            'no_match': 0,
            'created_participants': 0,
            'updated_participants': 0,
            'match_methods': defaultdict(int),
        }

        # Track unmatched contacts for CSV export
        self.unmatched_contacts = []

    def load_conversations(self) -> Dict[str, List[Dict]]:
        """
        Load conversations from CSV and group by phone number

        Returns:
            Dict mapping phone number to list of conversation records
        """
        print(f"\nLoading conversations from: {self.csv_path}")

        # Group conversations by phone
        conversations_by_phone = defaultdict(list)

        # Track phones seen in CSV to skip duplicates
        p_phones = set()
        row_idx = 0

        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                row_idx += 1

                # Check limit
                if self.limit and row_idx > self.limit:
                    print(f"LIMIT: Stopped after {self.limit} conversation rows")
                    break

                phone = row.get('Phone Number')
                if phone and phone in p_phones:
                    continue

                if phone:
                    norm_phone = PhoneNormalizer.normalize(phone)
                    conversations_by_phone[norm_phone].append(row)
                    p_phones.add(phone)

                self.stats['total_conversations'] += 1

                # Progress output
                if self.verbose and row_idx % 100 == 0:
                    print(f"  Loaded {row_idx} rows... ({len(conversations_by_phone)} unique contacts)")
                elif row_idx % 10000 == 0:
                    print(f"  Loaded {row_idx} rows...")

        self.stats['total_contacts'] = len(conversations_by_phone)
        print(f"Loaded {self.stats['total_conversations']} conversation records")
        print(f"Unique contacts: {self.stats['total_contacts']}")

        return conversations_by_phone

    def get_county_from_zipcode(self, zipcode) -> Optional[str]:
        """Map zipcode to county"""
        if not zipcode:
            return None
        clean_zip = re.sub(r'\D', '', str(zipcode))[:5]
        return self.zipcode_map.get(clean_zip)

    def get_county_from_city(self, city: str) -> Optional[str]:
        """Map city to county (fallback when County field and zipcode lookup fail)"""
        if not city:
            return None

        # Common Ohio city to county mappings
        city_map = {
            'columbus': 'FranklinCounty',
            'athens': 'AthensCounty',
            'cleveland': 'CuyahogaCounty',
            'cincinnati': 'HamiltonCounty',
            'toledo': 'LucasCounty',
            'akron': 'SummitCounty',
            'dayton': 'MontgomeryCounty',
            'youngstown': 'MahoningingCounty',
            'canton': 'StarkCounty',
            'lorain': 'LorainCounty',
            'hamilton': 'ButlerCounty',
            'springfield': 'ClarkCounty',
            'kettering': 'MontgomeryCounty',
            'elyria': 'LorainCounty',
            'newark': 'LickingCounty',
            'mansfield': 'RichlandCounty',
            'mentor': 'LakeCounty',
            'beavercreek': 'GreeneCounty',
            'strongsville': 'CuyahogaCounty',
            'dublin': 'FranklinCounty',
            'fairfield': 'ButlerCounty',
            'findlay': 'HancockCounty',
            'warren': 'TrumbullCounty',
            'lancaster': 'FairfieldCounty',
            'lima': 'AllenCounty',
            'huber heights': 'MontgomeryCounty',
            'westerville': 'FranklinCounty',
            'marion': 'MarionCounty',
            'grove city': 'FranklinCounty',
            'reynoldsburg': 'FranklinCounty',
            'upper arlington': 'FranklinCounty',
            'gahanna': 'FranklinCounty',
            'hilliard': 'FranklinCounty',
            'pickerington': 'FairfieldCounty',
            'worthington': 'FranklinCounty',
            'bexley': 'FranklinCounty',
            'whitehall': 'FranklinCounty',
            'groveport': 'FranklinCounty',
            'canal winchester': 'FranklinCounty',
        }

        city_lower = city.lower().strip()
        return city_map.get(city_lower)

    def match_to_residence(self, phone: str, conversation_data: List[Dict]) -> Tuple[Optional[ResidenceReference], Optional[DemographicReference], str]:
        """
        Match phone number to residence/demographic data using enhanced 8-strategy matching

        Args:
            phone: Normalized phone number
            conversation_data: List of conversation records for this phone

        Returns:
            (residence_ref, demographic_ref, match_method)
        """
        # Get contact info from first conversation record (all should be same)
        first_msg = conversation_data[0]

        # Extract all available contact fields
        email = first_msg.get('Email')
        first_name = first_msg.get('First Name')
        last_name = first_msg.get('Last Name')
        street = first_msg.get('Street')
        city = first_msg.get('City')
        state = first_msg.get('State')
        zipcode = first_msg.get('Zipcode')
        county_raw = first_msg.get('County')

        # Determine county with priority: County field > City lookup > Zipcode lookup
        county = None
        if county_raw:
            # County field is populated
            county = f"{county_raw}County" if not county_raw.endswith('County') else county_raw
        elif city:
            # Try city-to-county mapping (more reliable than broken zipcode cache)
            county = self.get_county_from_city(city)
            if county and self.verbose:
                print(f"  📍 Determined county from city: {city} → {county}")

        # Fallback to zipcode only if still no county
        if not county and zipcode:
            county = self.get_county_from_zipcode(zipcode)
            if county and self.verbose:
                print(f"  📍 Determined county from zipcode: {zipcode} → {county}")

        if not county:
            if self.verbose:
                print(f"  ⚠️  No county found for {city}/{zipcode}")
            return None, None, "no_county"

        # Use enhanced matcher with 8 strategies (now including email and name!)
        matcher = ResidenceMatcher(self.db, county=county)
        residence_ref, demographic_ref, match_method = matcher.match(
            phone=phone,
            email=email,
            first_name=first_name,
            last_name=last_name,
            address=street,
            zipcode=zipcode
        )

        # Update statistics
        if match_method == "no_match" or match_method == "collection_not_found":
            self.stats['no_match'] += 1
            if self.verbose:
                print(f"  ❌ No match for phone {phone} in {county}")
        else:
            if demographic_ref:
                self.stats['matched_demographic'] += 1
            if residence_ref:
                self.stats['matched_residence'] += 1
            self.stats['match_methods'][match_method] = self.stats['match_methods'].get(match_method, 0) + 1

            if self.verbose:
                parcel_id = residence_ref.parcel_id if residence_ref else demographic_ref.parcel_id if demographic_ref else "N/A"
                print(f"  ✅ Matched {phone} via {match_method} to {county}/{parcel_id}")

        return residence_ref, demographic_ref, match_method

    def import_conversations(self, conversations_by_phone: Dict[str, List[Dict]]):
        """
        Import conversations into participants collection

        Args:
            conversations_by_phone: Dict mapping phone to conversation records
        """
        print(f"\n{'='*80}")
        print(f"IMPORTING CONVERSATIONS")
        print(f"{'='*80}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE IMPORT'}")
        print(f"Campaign ID: {self.campaign_id}")

        participants_coll = self.db['participants']
        campaigns_coll = self.db['campaigns']

        # Load campaign
        campaign_oid = ObjectId(self.campaign_id)
        campaign_doc = campaigns_coll.find_one({'_id': campaign_oid})
        if not campaign_doc:
            raise ValueError(f"Campaign not found: {self.campaign_id}")

        campaign_name = campaign_doc.get('name', 'Unknown')
        print(f"Campaign: {campaign_name}")
        print(f"{'='*80}\n")

        # Statistics for campaign update
        total_sent = 0
        total_delivered = 0
        total_clicked = 0
        total_failed = 0
        total_opt_outs = 0

        # Track processed phones to avoid duplicates
        processed_phones = set()

        for idx, (phone, conversations) in enumerate(conversations_by_phone.items(), 1):
            # Skip if already processed in this run
            if phone in processed_phones:
                if self.verbose:
                    print(f"\n[{idx}/{self.stats['total_contacts']}] Skipping {phone} - already processed")
                continue

            # Mark as processed
            processed_phones.add(phone)
            # Progress output
            if self.verbose:
                first_msg = conversations[0]
                county = first_msg.get('County', 'Unknown')
                city = first_msg.get('City', 'Unknown')
                print(f"\n[{idx}/{self.stats['total_contacts']}] Processing {phone} ({city}, {county}) - {len(conversations)} messages")
            elif idx % 100 == 0:
                print(f"Processing contact {idx}/{self.stats['total_contacts']}...")

            # Check if participant already exists (cheap query)
            existing = participants_coll.find_one({'contact_id': phone})

            # Only skip matching if participant exists AND has references
            has_references = False
            if existing:
                has_residence = existing.get('residence') is not None
                has_demographic = existing.get('demographic') is not None
                has_references = has_residence or has_demographic

            if existing and has_references:
                # Reuse existing residence/demographic references (no matching needed!)
                if self.verbose:
                    print(f"  ♻️  Participant exists with references - reusing")

                # Extract existing references
                residence_ref = None
                demographic_ref = None
                if existing.get('residence'):
                    residence_ref = ResidenceReference(**existing['residence'])
                if existing.get('demographic'):
                    demographic_ref = DemographicReference(**existing['demographic'])

                match_method = "existing"
                self.stats['updated_participants'] += 1
            else:
                # New participant OR existing without references - do matching
                if self.verbose:
                    if existing:
                        print(f"  🔍 Participant exists but missing references - performing matching...")
                    else:
                        print(f"  🔍 New participant - performing residence matching...")

                residence_ref, demographic_ref, match_method = self.match_to_residence(phone, conversations)

                # Verbose output for match result
                if self.verbose:
                    if match_method in ("no_match", "no_county", "collection_not_found"):
                        print(f"  ❌ No match: {match_method}")
                    else:
                        ref_type = "residence" if residence_ref else "demographic"
                        parcel = residence_ref.parcel_id if residence_ref else (demographic_ref.parcel_id if demographic_ref else "N/A")
                        print(f"  ✅ Matched via {match_method} ({ref_type}: {parcel})")

                if existing:
                    self.stats['updated_participants'] += 1
                else:
                    self.stats['created_participants'] += 1

            # Track unmatched for CSV export
            if match_method in ("no_match", "no_county", "collection_not_found"):
                first_msg = conversations[0]
                self.unmatched_contacts.append({
                    'phone': phone,
                    'street': first_msg.get('Street'),
                    'city': first_msg.get('City'),
                    'state': first_msg.get('State'),
                    'zipcode': first_msg.get('Zipcode'),
                    'county': first_msg.get('County'),
                    'match_method': match_method,
                    'message_count': len(conversations)
                })

            # Create participant
            participant = Participant.from_text_conversation(
                phone=phone,
                campaign_id=self.campaign_id,
                conversation_data=conversations,
                residence_ref=residence_ref,
                demographic_ref=demographic_ref
            )

            # Extract engagement stats for campaign aggregation
            if participant.engagements:
                engagement = participant.engagements[0]  # Should have exactly one
                if isinstance(engagement, TextEngagement):
                    total_sent += engagement.messages_sent
                    total_delivered += engagement.messages_delivered
                    total_failed += engagement.messages_failed
                    # Approximation: clicked if replied
                    if engagement.replied:
                        total_clicked += 1
                    if engagement.opted_out:
                        total_opt_outs += 1

            if not self.dry_run:
                if existing:
                    # Update existing participant (add/update engagement)
                    participants_coll.update_one(
                        {'_id': existing['_id']},
                        {'$set': participant.to_mongo_dict()}
                    )
                else:
                    # Insert new participant
                    participants_coll.insert_one(participant.to_mongo_dict())

        # Update campaign statistics
        if not self.dry_run:
            campaign_stats = TextStatistics(
                sent=CampaignStatCount(unique=len(conversations_by_phone), total=total_sent),
                delivered=CampaignStatCount(unique=total_delivered, total=total_delivered),
                clicked=CampaignStatCount(unique=total_clicked, total=total_clicked),
                failed=CampaignStatCount(unique=total_failed, total=total_failed),
                opt_outs=CampaignStatCount(unique=total_opt_outs, total=total_opt_outs)
            )

            campaigns_coll.update_one(
                {'_id': campaign_oid},
                {'$set': {
                    'statistics': campaign_stats.dict() if hasattr(campaign_stats, 'dict') else campaign_stats.model_dump(),
                    'synced_at': datetime.now()
                }}
            )
            print(f"\n✅ Updated campaign statistics")

    def print_statistics(self):
        """Print import statistics"""
        print(f"\n{'='*80}")
        print(f"IMPORT STATISTICS")
        print(f"{'='*80}")

        print(f"\nConversations:")
        print(f"  Total conversation records: {self.stats['total_conversations']:,}")
        print(f"  Unique contacts:            {self.stats['total_contacts']:,}")

        print(f"\nMatching Results:")
        print(f"  Matched to residence:       {self.stats['matched_residence']:,}")
        print(f"  Matched to demographic:     {self.stats['matched_demographic']:,}")
        print(f"  No match:                   {self.stats['no_match']:,}")

        print(f"\nMatch Methods:")
        for method, count in sorted(self.stats['match_methods'].items()):
            print(f"  {method:20s}: {count:,}")

        print(f"\nParticipants:")
        print(f"  Created (new):              {self.stats['created_participants']:,}")
        print(f"  Updated (existing):         {self.stats['updated_participants']:,}")

        if self.stats['updated_participants'] > 0:
            print(f"\n⚡ Performance:")
            print(f"  Skipped expensive matching: {self.stats['updated_participants']:,} participants")
            print(f"  Only matched new contacts:  {self.stats['created_participants']:,} participants")

        print(f"{'='*80}")

    def write_unmatched_csv(self):
        """Write unmatched contacts to CSV for later processing"""
        if not self.unmatched_contacts:
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_path = Path(__file__).parent.parent / 'data' / 'tmp' / f'unmatched_contacts_{timestamp}.csv'

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['phone', 'street', 'city', 'state', 'zipcode', 'county', 'match_method', 'message_count']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.unmatched_contacts)

        print(f"\n📄 Wrote {len(self.unmatched_contacts)} unmatched contacts to: {csv_path}")

    def close(self):
        """Close MongoDB connection"""
        self.client.close()


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Import text conversations into MongoDB')
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV, help='CSV file path')
    parser.add_argument('--campaign-id', required=True, help='MongoDB Campaign _id')
    parser.add_argument('--dry-run', action='store_true', help='Validation only (no writes)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--limit', type=int, help='Limit number of conversation rows to process (for testing)')

    args = parser.parse_args()

    print(f"{'='*80}")
    print(f"TEXT CONVERSATIONS IMPORT TOOL")
    print(f"{'='*80}")
    print(f"Started at: {datetime.now()}")
    print(f"CSV file: {args.csv}")
    print(f"Campaign ID: {args.campaign_id}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE IMPORT'}")

    importer = ConversationImporter(
        csv_path=args.csv,
        campaign_id=args.campaign_id,
        dry_run=args.dry_run,
        verbose=args.verbose,
        limit=args.limit
    )

    try:
        conversations = importer.load_conversations()
        importer.import_conversations(conversations)
        importer.print_statistics()
        importer.write_unmatched_csv()

        print(f"\nCompleted at: {datetime.now()}")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        importer.close()


if __name__ == '__main__':
    sys.exit(main())
