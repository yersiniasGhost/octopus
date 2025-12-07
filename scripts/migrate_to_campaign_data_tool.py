#!/usr/bin/env python3
"""
Migration Tool: Create campaign_data Database from CSV Exports

This tool migrates data from CSV exports and emailoctopus_db to a new
well-structured campaign_data database with:
- Normalized participants (one doc per unique person)
- Denormalized demographics/residence data
- Unified engagement status (no_engagement/received/engaged)
- Pre-computed engagement summaries

Usage:
    # Dry run - analyze what would be migrated
    python scripts/migrate_to_campaign_data_tool.py --dry-run

    # Live migration
    python scripts/migrate_to_campaign_data_tool.py --live

    # Specific phases
    python scripts/migrate_to_campaign_data_tool.py --live --phase setup
    python scripts/migrate_to_campaign_data_tool.py --live --phase import
    python scripts/migrate_to_campaign_data_tool.py --live --phase match
    python scripts/migrate_to_campaign_data_tool.py --live --phase summarize

    # Limit for testing
    python scripts/migrate_to_campaign_data_tool.py --live --limit 1000
"""
import os
import sys
import re
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

from src.tools.residence_matcher import ResidenceMatcher, PhoneNormalizer, AddressNormalizer
from src.models.campaign_data import (
    Participant, Campaign, CampaignExposure,
    Address, Linkage, Demographics, Residence, EnergySnapshot,
    EngagementSummary, ChannelEngagement, DataQuality,
    CampaignStatistics, ContactSnapshot, EnergyAtSend,
    Channel, UnifiedEngagement
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Constants
CSV_DIR = Path(__file__).parent.parent / 'data' / 'exports'
ZIPCODE_CACHE = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'

# Agency extraction from campaign name
AGENCIES = ['OHCAC', 'MVCAP', 'IMPACT', 'COAD']


@dataclass
class MigrationStats:
    """Track migration statistics"""
    # CSV processing
    csv_files_processed: int = 0
    csv_rows_processed: int = 0

    # Campaigns
    campaigns_created: int = 0
    campaigns_updated: int = 0

    # Participants
    unique_participants: int = 0
    participants_created: int = 0
    participants_updated: int = 0

    # Exposures
    exposures_created: int = 0
    exposures_skipped: int = 0

    # Matching
    matched_to_demographics: int = 0
    matched_to_residence: int = 0
    no_match: int = 0
    match_methods: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Engagement
    no_engagement_count: int = 0
    received_count: int = 0
    engaged_count: int = 0

    # Errors
    errors: int = 0

    def print_summary(self):
        """Print statistics summary"""
        print("\n" + "=" * 80)
        print("MIGRATION STATISTICS")
        print("=" * 80)

        print("\nCSV Processing:")
        print(f"  Files processed:        {self.csv_files_processed}")
        print(f"  Rows processed:         {self.csv_rows_processed:,}")

        print("\nCampaigns:")
        print(f"  Created:                {self.campaigns_created}")
        print(f"  Updated:                {self.campaigns_updated}")

        print("\nParticipants:")
        print(f"  Unique participants:    {self.unique_participants:,}")
        print(f"  Created:                {self.participants_created:,}")
        print(f"  Updated:                {self.participants_updated:,}")

        print("\nCampaign Exposures:")
        print(f"  Created:                {self.exposures_created:,}")
        print(f"  Skipped (duplicates):   {self.exposures_skipped:,}")

        print("\nCounty Matching:")
        print(f"  Matched demographics:   {self.matched_to_demographics:,}")
        print(f"  Matched residence:      {self.matched_to_residence:,}")
        print(f"  No match:               {self.no_match:,}")
        if self.match_methods:
            print("  Match methods:")
            for method, count in sorted(self.match_methods.items(), key=lambda x: -x[1]):
                print(f"    {method:25s}: {count:,}")

        print("\nEngagement Distribution:")
        print(f"  No engagement:          {self.no_engagement_count:,}")
        print(f"  Received:               {self.received_count:,}")
        print(f"  Engaged:                {self.engaged_count:,}")

        if self.errors > 0:
            print(f"\nErrors:                   {self.errors}")

        print("=" * 80 + "\n")


class CampaignDataMigrator:
    """Migrate data to campaign_data database"""

    def __init__(self, dry_run: bool = True, limit: Optional[int] = None):
        self.dry_run = dry_run
        self.limit = limit
        self.stats = MigrationStats()

        # Target database (campaign_data)
        self.mongo_host = os.getenv('MONGODB_HOST', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT', '27017'))
        self.target_db_name = 'campaign_data'

        # Source county database (empower_development)
        self.county_host = os.getenv('MONGODB_HOST_RM', 'localhost')
        self.county_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.county_db_name = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        # Connect
        logger.info(f"Target DB: {self.mongo_host}:{self.mongo_port}/{self.target_db_name}")
        logger.info(f"County DB: {self.county_host}:{self.county_port}/{self.county_db_name}")

        self.client = MongoClient(self.mongo_host, self.mongo_port)
        self.db = self.client[self.target_db_name]

        self.county_client = MongoClient(self.county_host, self.county_port)
        self.county_db = self.county_client[self.county_db_name]

        # Load zipcode cache
        self.zipcode_map = self._load_zipcode_cache()

        # In-memory participant index for deduplication
        self.participant_index: Dict[str, str] = {}  # canonical_id -> participant_id

    def _load_zipcode_cache(self) -> Dict[str, str]:
        """Load zipcode-to-county mapping"""
        if not ZIPCODE_CACHE.exists():
            logger.warning(f"Zipcode cache not found: {ZIPCODE_CACHE}")
            return {}

        with open(ZIPCODE_CACHE, 'r') as f:
            data = json.load(f)
        zipcode_map = data.get('zipcode_map', {})
        logger.info(f"Loaded {len(zipcode_map)} zipcode mappings")
        return zipcode_map

    def get_county_from_zipcode(self, zipcode: str) -> Optional[str]:
        """Map zipcode to county name"""
        if not zipcode:
            return None
        clean_zip = re.sub(r'\D', '', str(zipcode))[:5]
        return self.zipcode_map.get(clean_zip)

    # =========================================================================
    # Phase 1: Setup
    # =========================================================================

    def setup_database(self):
        """Create collections and indexes"""
        logger.info("Setting up database and indexes...")

        if self.dry_run:
            logger.info("[DRY RUN] Would create indexes")
            return

        # Participants indexes
        self.db.participants.create_index([("participant_id", ASCENDING)], unique=True)
        self.db.participants.create_index([("email", ASCENDING)], sparse=True)
        self.db.participants.create_index([("phone", ASCENDING)], sparse=True)
        self.db.participants.create_index([("address.zip", ASCENDING)])
        self.db.participants.create_index([("address.county", ASCENDING)])
        self.db.participants.create_index([("linkage.parcel_id", ASCENDING)], sparse=True)
        self.db.participants.create_index([("engagement_summary.unified_status", ASCENDING)])
        self.db.participants.create_index([("engagement_summary.ever_engaged", ASCENDING)])
        self.db.participants.create_index([("data_quality.analysis_ready", ASCENDING)])
        self.db.participants.create_index([("demographics.income_level", ASCENDING)])
        self.db.participants.create_index([("demographics.total_energy_burden", ASCENDING)])
        self.db.participants.create_index([
            ("data_quality.analysis_ready", ASCENDING),
            ("engagement_summary.unified_status", ASCENDING)
        ])

        # Campaigns indexes
        self.db.campaigns.create_index([("campaign_id", ASCENDING)], unique=True)
        self.db.campaigns.create_index([("agency", ASCENDING)])
        self.db.campaigns.create_index([("channel", ASCENDING)])
        self.db.campaigns.create_index([("sent_at", DESCENDING)])
        self.db.campaigns.create_index([
            ("agency", ASCENDING),
            ("channel", ASCENDING),
            ("sent_at", DESCENDING)
        ])

        # Campaign exposures indexes
        self.db.campaign_exposures.create_index([("participant_id", ASCENDING)])
        self.db.campaign_exposures.create_index([("campaign_id", ASCENDING)])
        self.db.campaign_exposures.create_index([
            ("participant_id", ASCENDING),
            ("campaign_id", ASCENDING)
        ], unique=True)
        self.db.campaign_exposures.create_index([("unified_status", ASCENDING)])
        self.db.campaign_exposures.create_index([
            ("channel", ASCENDING),
            ("unified_status", ASCENDING)
        ])
        self.db.campaign_exposures.create_index([("sent_at", DESCENDING)])

        logger.info("Database setup complete")

    # =========================================================================
    # Phase 2: Import CSV Data
    # =========================================================================

    def import_csv_data(self):
        """Import all CSV files from data/exports/"""
        logger.info(f"Importing CSV files from {CSV_DIR}")

        csv_files = sorted(CSV_DIR.glob("campaign_*.csv"))
        logger.info(f"Found {len(csv_files)} CSV files")

        for csv_file in csv_files:
            self._process_csv_file(csv_file)

            if self.limit and self.stats.csv_rows_processed >= self.limit:
                logger.info(f"Reached limit of {self.limit} rows")
                break

        logger.info(f"Imported {self.stats.csv_files_processed} files, {self.stats.csv_rows_processed:,} rows")

    def _process_csv_file(self, csv_path: Path):
        """Process a single CSV file"""
        logger.info(f"Processing: {csv_path.name}")

        # Extract campaign info from filename
        # Format: campaign_{uuid}_{name}.csv
        filename = csv_path.stem
        match = re.match(r'campaign_([a-f0-9-]+)_(.+)', filename)
        if not match:
            logger.warning(f"Could not parse filename: {filename}")
            return

        campaign_id = match.group(1)
        campaign_name = match.group(2)

        # Extract agency from name
        agency = None
        for ag in AGENCIES:
            if ag in campaign_name.upper():
                agency = ag
                break

        # Create/update campaign
        campaign = self._create_or_update_campaign(
            campaign_id=campaign_id,
            name=campaign_name,
            agency=agency,
            source_file=csv_path.name
        )

        # Process rows
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self._process_csv_row(row, campaign)
                self.stats.csv_rows_processed += 1

                if self.limit and self.stats.csv_rows_processed >= self.limit:
                    break

        self.stats.csv_files_processed += 1

    def _create_or_update_campaign(self, campaign_id: str, name: str,
                                    agency: Optional[str], source_file: str) -> Dict:
        """Create or update campaign document"""
        existing = self.db.campaigns.find_one({"campaign_id": campaign_id})

        if existing:
            self.stats.campaigns_updated += 1
            return existing

        # Parse sent_at from campaign name (format: _YYYYMMDD)
        sent_at = None
        date_match = re.search(r'_(\d{8})(?:_|$)', name)
        if date_match:
            try:
                sent_at = datetime.strptime(date_match.group(1), '%Y%m%d')
            except ValueError:
                pass

        # Extract message_type from name
        message_type = None
        name_lower = name.lower()
        for mt in ['webinar', 'crisis', 'savings', 'daily_cost', 'monthly', 'improve', 'surge']:
            if mt in name_lower:
                message_type = mt
                break

        campaign_doc = {
            "campaign_id": campaign_id,
            "name": name,
            "agency": agency,
            "channel": Channel.EMAIL.value,
            "message_type": message_type,
            "sent_at": sent_at,
            "source_system": "emailoctopus",
            "source_file": source_file,
            "statistics": CampaignStatistics().model_dump(),
            "created_at": datetime.utcnow(),
            "synced_at": datetime.utcnow()
        }

        if not self.dry_run:
            self.db.campaigns.insert_one(campaign_doc)

        self.stats.campaigns_created += 1
        return campaign_doc

    def _process_csv_row(self, row: Dict, campaign: Dict):
        """Process a single CSV row - create participant and exposure"""
        # Extract contact info
        email = row.get('email', '').strip().lower() or None
        phone = PhoneNormalizer.normalize(row.get('cell', ''))
        address = row.get('address', '').strip() or None
        city = row.get('city', '').strip() or None
        zipcode = row.get('zip', '').strip() or None

        # Determine canonical participant_id
        participant_id = email or phone
        if not participant_id:
            return  # Can't identify participant

        # Get or create participant
        participant = self._get_or_create_participant(
            participant_id=participant_id,
            email=email,
            phone=phone,
            address=address,
            city=city,
            zipcode=zipcode,
            row=row
        )

        # Create exposure
        self._create_exposure(participant, campaign, row)

    def _get_or_create_participant(self, participant_id: str, email: Optional[str],
                                    phone: Optional[str], address: Optional[str],
                                    city: Optional[str], zipcode: Optional[str],
                                    row: Dict) -> Dict:
        """Get existing participant or create new one"""
        # Check in-memory index first (for deduplication within this migration run)
        if participant_id in self.participant_index:
            # Already seen in this session - just update source_campaigns
            campaign_name = row.get('campaign_name', '')
            if campaign_name and not self.dry_run:
                self.db.participants.update_one(
                    {"participant_id": participant_id},
                    {"$addToSet": {"source_campaigns": campaign_name}}
                )
            self.stats.participants_updated += 1
            return {"participant_id": participant_id}  # Return minimal dict

        # Check database (for resuming interrupted migrations)
        existing = self.db.participants.find_one({"participant_id": participant_id})

        if existing:
            # Found in DB - add to index and update
            self.participant_index[participant_id] = participant_id
            campaign_name = row.get('campaign_name', '')
            if campaign_name and campaign_name not in existing.get('source_campaigns', []):
                if not self.dry_run:
                    self.db.participants.update_one(
                        {"participant_id": participant_id},
                        {"$addToSet": {"source_campaigns": campaign_name}}
                    )
                self.stats.participants_updated += 1
            return existing

        # Parse energy data from CSV
        energy_snapshot = self._parse_energy_snapshot(row)

        # Get county from zipcode
        county = self.get_county_from_zipcode(zipcode)

        # Build address object
        address_obj = Address(
            street=AddressNormalizer.normalize(address) if address else None,
            city=city,
            zip=zipcode,
            county=county,
            raw=address
        )

        participant_doc = Participant(
            participant_id=participant_id,
            email=email,
            phone=phone if phone else None,
            address=address_obj,
            linkage=Linkage(county_key=county.replace('County', '') if county else None),
            energy_snapshot=energy_snapshot,
            source_campaigns=[row.get('campaign_name', '')],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ).model_dump(by_alias=True, exclude={'id'})

        # Add to in-memory index
        self.participant_index[participant_id] = participant_id

        if not self.dry_run:
            try:
                self.db.participants.insert_one(participant_doc)
            except DuplicateKeyError:
                # Race condition - document was created by another process
                return self.db.participants.find_one({"participant_id": participant_id})

        self.stats.participants_created += 1
        self.stats.unique_participants += 1
        return participant_doc

    def _parse_energy_snapshot(self, row: Dict) -> EnergySnapshot:
        """Parse energy data from CSV row"""
        def parse_currency(val: str) -> Optional[float]:
            if not val:
                return None
            # Remove $ and commas: "$6,674.70" -> 6674.70
            cleaned = re.sub(r'[$,]', '', val)
            try:
                return float(cleaned)
            except ValueError:
                return None

        def parse_float(val: str) -> Optional[float]:
            if not val:
                return None
            try:
                return float(val)
            except ValueError:
                return None

        # Parse date from campaign_sent_at
        sent_at = None
        date_str = row.get('campaign_sent_at', '')
        if date_str:
            try:
                sent_at = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                pass

        return EnergySnapshot(
            kwh_annual=parse_float(row.get('kwh')),
            annual_cost=parse_currency(row.get('annual_cost')),
            annual_savings=parse_currency(row.get('annual_savings')),
            monthly_cost=parse_currency(row.get('monthly_cost')),
            monthly_saving=parse_currency(row.get('monthly_saving')),
            daily_cost=parse_currency(row.get('daily_cost')),
            snapshot_date=sent_at
        )

    def _create_exposure(self, participant: Dict, campaign: Dict, row: Dict):
        """Create campaign exposure document"""
        participant_id = participant['participant_id']
        campaign_id = campaign['campaign_id']

        # Check if exposure already exists
        existing = self.db.campaign_exposures.find_one({
            "participant_id": participant_id,
            "campaign_id": campaign_id
        })

        if existing:
            self.stats.exposures_skipped += 1
            return

        # Parse engagement
        opened = row.get('opened', '').lower() == 'yes'
        clicked = row.get('clicked', '').lower() == 'yes'
        bounced = row.get('bounced', '').lower() == 'yes'
        complained = row.get('complained', '').lower() == 'yes'
        unsubscribed = row.get('unsubscribed', '').lower() == 'yes'

        # Compute unified status
        if clicked:
            unified_status = UnifiedEngagement.ENGAGED.value
            self.stats.engaged_count += 1
        elif opened:
            unified_status = UnifiedEngagement.RECEIVED.value
            self.stats.received_count += 1
        else:
            unified_status = UnifiedEngagement.NO_ENGAGEMENT.value
            self.stats.no_engagement_count += 1

        # Parse sent_at
        sent_at = None
        date_str = row.get('campaign_sent_at', '')
        if date_str:
            try:
                sent_at = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                pass

        # Parse energy at send
        energy_snapshot = self._parse_energy_snapshot(row)
        energy_at_send = EnergyAtSend(
            kwh=energy_snapshot.kwh_annual,
            annual_cost=energy_snapshot.annual_cost,
            annual_savings=energy_snapshot.annual_savings,
            monthly_cost=energy_snapshot.monthly_cost,
            daily_cost=energy_snapshot.daily_cost
        )

        # Contact snapshot
        contact_snapshot = ContactSnapshot(
            email=row.get('email'),
            phone=row.get('cell'),
            address=row.get('address'),
            city=row.get('city'),
            zip=row.get('zip')
        )

        exposure_doc = CampaignExposure(
            participant_id=participant_id,
            campaign_id=campaign_id,
            agency=campaign.get('agency'),
            channel=Channel.EMAIL.value,
            sent_at=sent_at,
            email_opened=opened,
            email_clicked=clicked,
            email_bounced=bounced,
            email_complained=complained,
            email_unsubscribed=unsubscribed,
            unified_status=unified_status,
            contact_snapshot=contact_snapshot,
            energy_at_send=energy_at_send,
            created_at=datetime.utcnow()
        ).model_dump(by_alias=True, exclude={'id'})

        if not self.dry_run:
            try:
                self.db.campaign_exposures.insert_one(exposure_doc)
            except DuplicateKeyError:
                self.stats.exposures_skipped += 1
                return

        self.stats.exposures_created += 1

    # =========================================================================
    # Phase 3: Match to County Data
    # =========================================================================

    def match_county_data(self):
        """Match participants to county demographic/residential data"""
        logger.info("Matching participants to county data...")

        # Get all unmatched participants
        query = {
            "$or": [
                {"linkage.parcel_id": {"$exists": False}},
                {"linkage.parcel_id": None}
            ]
        }

        cursor = self.db.participants.find(query)
        total = self.db.participants.count_documents(query)
        logger.info(f"Found {total:,} unmatched participants")

        processed = 0
        for participant in cursor:
            self._match_participant(participant)
            processed += 1

            if processed % 500 == 0:
                logger.info(f"Matched {processed:,}/{total:,} participants...")

            if self.limit and processed >= self.limit:
                break

        logger.info(f"Matching complete: {self.stats.matched_to_demographics:,} demographics, "
                    f"{self.stats.matched_to_residence:,} residence, {self.stats.no_match:,} no match")

    def _match_participant(self, participant: Dict):
        """Match a single participant to county data"""
        county = participant.get('address', {}).get('county')
        if not county:
            self.stats.no_match += 1
            return

        # Clean county name (remove 'County' suffix if present)
        county_key = county.replace('County', '').strip()

        # Use existing ResidenceMatcher
        matcher = ResidenceMatcher(self.county_db, county=county)

        residence_ref, demographic_ref, match_method = matcher.match(
            phone=participant.get('phone'),
            email=participant.get('email'),
            first_name=None,  # Not available in CSV
            last_name=None,
            address=participant.get('address', {}).get('raw'),
            zipcode=participant.get('address', {}).get('zip')
        )

        if match_method in ("no_match", "collection_not_found"):
            self.stats.no_match += 1
            return

        self.stats.match_methods[match_method] += 1

        # Build update document
        update_doc = {
            "linkage.method": match_method,
            "linkage.confidence": 1.0 if "exact" in match_method else 0.8,
            "linkage.matched_at": datetime.utcnow(),
            "linkage.county_key": county_key,
            "updated_at": datetime.utcnow()
        }

        # Get demographics data
        if demographic_ref:
            self.stats.matched_to_demographics += 1
            update_doc["linkage.parcel_id"] = demographic_ref.parcel_id
            update_doc["data_quality.has_demographics"] = True

            # Fetch full demographic record
            demo_coll_name = f"{county}Demographic"
            if demo_coll_name in self.county_db.list_collection_names():
                demo_record = self.county_db[demo_coll_name].find_one(
                    {"parcel_id": demographic_ref.parcel_id}
                )
                if demo_record:
                    demographics = Demographics.from_county_record(demo_record)
                    update_doc["demographics"] = demographics.model_dump()

        # Get residence data
        if residence_ref:
            self.stats.matched_to_residence += 1
            if "linkage.parcel_id" not in update_doc:
                update_doc["linkage.parcel_id"] = residence_ref.parcel_id
            update_doc["data_quality.has_residence"] = True

            # Fetch full residential record
            res_coll_name = f"{county}Residential"
            if res_coll_name in self.county_db.list_collection_names():
                res_record = self.county_db[res_coll_name].find_one(
                    {"parcel_id": residence_ref.parcel_id}
                )
                if res_record:
                    residence = Residence.from_county_record(res_record)
                    update_doc["residence"] = residence.model_dump()

        if not self.dry_run:
            self.db.participants.update_one(
                {"participant_id": participant['participant_id']},
                {"$set": update_doc}
            )

    # =========================================================================
    # Phase 4: Compute Engagement Summaries
    # =========================================================================

    def compute_engagement_summaries(self):
        """Compute engagement summaries for all participants"""
        logger.info("Computing engagement summaries...")

        cursor = self.db.participants.find({})
        total = self.db.participants.count_documents({})
        logger.info(f"Processing {total:,} participants")

        processed = 0
        for participant in cursor:
            self._compute_participant_summary(participant)
            processed += 1

            if processed % 500 == 0:
                logger.info(f"Computed {processed:,}/{total:,} summaries...")

            if self.limit and processed >= self.limit:
                break

        logger.info("Engagement summary computation complete")

    def _compute_participant_summary(self, participant: Dict):
        """Compute engagement summary for a single participant"""
        participant_id = participant['participant_id']

        # Aggregate exposures
        pipeline = [
            {"$match": {"participant_id": participant_id}},
            {"$group": {
                "_id": "$channel",
                "exposures": {"$sum": 1},
                "received": {"$sum": {"$cond": [
                    {"$in": ["$unified_status", ["received", "engaged"]]}, 1, 0
                ]}},
                "engaged": {"$sum": {"$cond": [
                    {"$eq": ["$unified_status", "engaged"]}, 1, 0
                ]}},
                "min_date": {"$min": "$sent_at"},
                "max_date": {"$max": "$sent_at"}
            }}
        ]

        results = list(self.db.campaign_exposures.aggregate(pipeline))

        # Build summary
        by_channel = {
            "email": ChannelEngagement(),
            "text_morning": ChannelEngagement(),
            "text_evening": ChannelEngagement(),
            "mailer": ChannelEngagement(),
            "letter": ChannelEngagement()
        }

        total_exposures = 0
        total_received = 0
        total_engaged = 0
        first_date = None
        last_date = None

        for r in results:
            channel = r['_id'] or 'email'
            if channel in by_channel:
                by_channel[channel] = ChannelEngagement(
                    exposures=r['exposures'],
                    received=r['received'],
                    engaged=r['engaged']
                )

            total_exposures += r['exposures']
            total_received += r['received']
            total_engaged += r['engaged']

            if r['min_date']:
                if first_date is None or r['min_date'] < first_date:
                    first_date = r['min_date']
            if r['max_date']:
                if last_date is None or r['max_date'] > last_date:
                    last_date = r['max_date']

        # Determine unified status
        if total_engaged > 0:
            unified_status = UnifiedEngagement.ENGAGED.value
        elif total_received > 0:
            unified_status = UnifiedEngagement.RECEIVED.value
        else:
            unified_status = UnifiedEngagement.NO_ENGAGEMENT.value

        # Count unique campaigns
        campaign_count = self.db.campaign_exposures.count_documents(
            {"participant_id": participant_id}
        )

        engagement_summary = EngagementSummary(
            total_campaigns=campaign_count,
            total_exposures=total_exposures,
            by_channel={k: v.model_dump() for k, v in by_channel.items()},
            unified_status=unified_status,
            ever_received=total_received > 0,
            ever_engaged=total_engaged > 0,
            first_campaign_date=first_date,
            last_campaign_date=last_date,
            overall_receive_rate=total_received / total_exposures if total_exposures > 0 else 0.0,
            overall_engage_rate=total_engaged / total_exposures if total_exposures > 0 else 0.0
        )

        # Update data quality
        has_demographics = participant.get('data_quality', {}).get('has_demographics', False)
        has_residence = participant.get('data_quality', {}).get('has_residence', False)
        has_energy = bool(participant.get('energy_snapshot', {}).get('kwh_annual'))
        has_engagement = total_exposures > 0

        # Compute completeness score
        fields_present = sum([
            bool(participant.get('email')),
            bool(participant.get('phone')),
            bool(participant.get('address', {}).get('street')),
            has_demographics,
            has_residence,
            has_energy,
            has_engagement
        ])
        completeness_score = fields_present / 7.0

        data_quality = DataQuality(
            has_demographics=has_demographics,
            has_residence=has_residence,
            has_energy_snapshot=has_energy,
            has_engagement=has_engagement,
            completeness_score=completeness_score,
            analysis_ready=has_demographics and has_engagement
        )

        if not self.dry_run:
            self.db.participants.update_one(
                {"participant_id": participant_id},
                {"$set": {
                    "engagement_summary": engagement_summary.model_dump(),
                    "data_quality": data_quality.model_dump(),
                    "updated_at": datetime.utcnow()
                }}
            )

    # =========================================================================
    # Phase 5: Update Campaign Statistics
    # =========================================================================

    def update_campaign_statistics(self):
        """Update aggregate statistics on all campaigns"""
        logger.info("Updating campaign statistics...")

        cursor = self.db.campaigns.find({})
        total = self.db.campaigns.count_documents({})

        processed = 0
        for campaign in cursor:
            self._update_campaign_stats(campaign)
            processed += 1

        logger.info(f"Updated statistics for {processed} campaigns")

    def _update_campaign_stats(self, campaign: Dict):
        """Update statistics for a single campaign"""
        campaign_id = campaign['campaign_id']

        pipeline = [
            {"$match": {"campaign_id": campaign_id}},
            {"$group": {
                "_id": None,
                "total_sent": {"$sum": 1},
                "opened": {"$sum": {"$cond": ["$email_opened", 1, 0]}},
                "clicked": {"$sum": {"$cond": ["$email_clicked", 1, 0]}},
                "bounced": {"$sum": {"$cond": ["$email_bounced", 1, 0]}},
                "unsubscribed": {"$sum": {"$cond": ["$email_unsubscribed", 1, 0]}},
                "complained": {"$sum": {"$cond": ["$email_complained", 1, 0]}},
                "received": {"$sum": {"$cond": [
                    {"$in": ["$unified_status", ["received", "engaged"]]}, 1, 0
                ]}},
                "engaged": {"$sum": {"$cond": [
                    {"$eq": ["$unified_status", "engaged"]}, 1, 0
                ]}}
            }}
        ]

        results = list(self.db.campaign_exposures.aggregate(pipeline))

        if not results:
            return

        r = results[0]
        total_sent = r['total_sent'] or 1  # Avoid division by zero

        statistics = CampaignStatistics(
            total_sent=r['total_sent'],
            opened=r['opened'],
            clicked=r['clicked'],
            bounced=r['bounced'],
            unsubscribed=r['unsubscribed'],
            complained=r['complained'],
            received=r['received'],
            engaged=r['engaged'],
            receive_rate=r['received'] / total_sent,
            engage_rate=r['engaged'] / total_sent
        )

        if not self.dry_run:
            self.db.campaigns.update_one(
                {"campaign_id": campaign_id},
                {"$set": {
                    "statistics": statistics.model_dump(),
                    "synced_at": datetime.utcnow()
                }}
            )

    # =========================================================================
    # Main Entry Points
    # =========================================================================

    def run_full_migration(self):
        """Run complete migration"""
        logger.info("=" * 80)
        logger.info("CAMPAIGN DATA MIGRATION")
        logger.info("=" * 80)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"Limit: {self.limit or 'None'}")
        logger.info("=" * 80)

        self.run_phase('setup')
        self.run_phase('import')
        self.run_phase('match')
        self.run_phase('summarize')
        self.run_phase('stats')

        self.stats.print_summary()

    def run_phase(self, phase: str):
        """Run a specific migration phase"""
        logger.info(f"\n{'='*40}")
        logger.info(f"PHASE: {phase.upper()}")
        logger.info(f"{'='*40}")

        if phase == 'setup':
            self.setup_database()
        elif phase == 'import':
            self.import_csv_data()
        elif phase == 'match':
            self.match_county_data()
        elif phase == 'summarize':
            self.compute_engagement_summaries()
        elif phase == 'stats':
            self.update_campaign_statistics()
        else:
            logger.error(f"Unknown phase: {phase}")

    def close(self):
        """Close database connections"""
        self.client.close()
        self.county_client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate data to campaign_data database')
    parser.add_argument('--dry-run', action='store_true', help='Analyze without making changes')
    parser.add_argument('--live', action='store_true', help='Actually perform migration')
    parser.add_argument('--phase', choices=['setup', 'import', 'match', 'summarize', 'stats'],
                        help='Run specific phase only')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')

    args = parser.parse_args()

    if not args.dry_run and not args.live:
        print("ERROR: Must specify either --dry-run or --live")
        return 1

    dry_run = not args.live

    migrator = CampaignDataMigrator(dry_run=dry_run, limit=args.limit)

    try:
        if args.phase:
            migrator.run_phase(args.phase)
        else:
            migrator.run_full_migration()

        migrator.stats.print_summary()

        if dry_run:
            print("\n⚠️  DRY RUN - No changes were made")
            print("   Run with --live to perform actual migration")

        return 0

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1
    finally:
        migrator.close()


if __name__ == '__main__':
    sys.exit(main())
