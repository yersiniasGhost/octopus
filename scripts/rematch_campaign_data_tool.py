#!/usr/bin/env python3
"""
Tool: Rematch Unmatched Participants in campaign_data

This script fixes unmatched participants by:
1. Pulling phone/address from their campaign_exposures (contact_snapshot)
2. Re-running the 8-strategy ResidenceMatcher
3. Updating participant records with demographics/residence data

Usage:
    # Dry run
    python scripts/rematch_campaign_data_tool.py --dry-run

    # Live update
    python scripts/rematch_campaign_data_tool.py --live

    # With verbose output
    python scripts/rematch_campaign_data_tool.py --live --verbose

    # Limit for testing
    python scripts/rematch_campaign_data_tool.py --dry-run --limit 100
"""
import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

from src.tools.residence_matcher import ResidenceMatcher, PhoneNormalizer, AddressNormalizer
from src.models.campaign_data import Demographics, Residence, Linkage, DataQuality

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CampaignDataRematcher:
    """Rematch unmatched participants in campaign_data"""

    def __init__(self, dry_run: bool = True, verbose: bool = False, limit: Optional[int] = None):
        self.dry_run = dry_run
        self.verbose = verbose
        self.limit = limit

        # campaign_data database
        self.client = MongoClient('localhost', 27017)
        self.db = self.client['campaign_data']

        # County database
        county_host = os.getenv('MONGODB_HOST_RM', '192.168.1.156')
        county_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.county_client = MongoClient(county_host, county_port)
        self.county_db = self.county_client['empower_development']

        # Build ZIP-to-counties map (many ZIPs span multiple counties)
        self.zip_to_counties = self._build_zip_to_counties_map()

        # Stats
        self.stats = {
            'total_unmatched': 0,
            'processed': 0,
            'contact_data_found': 0,
            'newly_matched': 0,
            'still_unmatched': 0,
            'match_methods': defaultdict(int),
            'by_county': defaultdict(lambda: {'processed': 0, 'matched': 0})
        }

    def _build_zip_to_counties_map(self) -> Dict[str, list]:
        """Build map of ZIP codes to all counties that have data for that ZIP."""
        logger.info("Building ZIP-to-counties map...")
        zip_map = defaultdict(list)

        collections = self.county_db.list_collection_names()
        residential_colls = [c for c in collections if c.endswith('Residential')]

        for coll_name in residential_colls:
            county = coll_name.replace('Residential', '')
            # Get all ZIPs in this county
            zips = self.county_db[coll_name].distinct('parcel_zip')
            for z in zips:
                zip_str = str(z).zfill(5) if z else None
                if zip_str:
                    # Count records for this ZIP to prioritize counties with more data
                    count = self.county_db[coll_name].count_documents({'parcel_zip': z})
                    zip_map[zip_str].append((county, count))

        # Sort counties by record count (descending) for each ZIP
        for z in zip_map:
            zip_map[z].sort(key=lambda x: -x[1])
            zip_map[z] = [county for county, count in zip_map[z]]

        logger.info(f"Built ZIP map covering {len(zip_map)} ZIPs across {len(residential_colls)} counties")

        # Store list of all counties for fallback email search
        self.all_counties = [c.replace('Residential', '') for c in residential_colls]

        return dict(zip_map)

    def get_best_contact_data(self, participant_id: str) -> Dict:
        """
        Get the best contact data from campaign_exposures.

        Returns the most complete contact_snapshot (preferring ones with phone AND address).
        """
        exposures = self.db.campaign_exposures.find({"participant_id": participant_id})

        best = {'phone': None, 'address': None, 'city': None, 'zip': None}
        best_score = 0

        for exp in exposures:
            snap = exp.get('contact_snapshot', {})
            phone = snap.get('phone', '').strip() if snap.get('phone') else None
            address = snap.get('address', '').strip() if snap.get('address') else None
            city = snap.get('city', '').strip() if snap.get('city') else None
            zipcode = snap.get('zip', '').strip() if snap.get('zip') else None

            # Score: phone=2, address=2, city=1, zip=1
            score = 0
            if phone:
                score += 2
            if address:
                score += 2
            if city:
                score += 1
            if zipcode:
                score += 1

            if score > best_score:
                best_score = score
                best = {
                    'phone': phone,
                    'address': address,
                    'city': city,
                    'zip': zipcode
                }

            # If we have everything, stop looking
            if best_score >= 6:
                break

        return best

    def rematch_participants(self):
        """Rematch all unmatched participants"""
        logger.info("=" * 80)
        logger.info("REMATCH UNMATCHED PARTICIPANTS")
        logger.info("=" * 80)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")

        # Find unmatched participants
        query = {"data_quality.has_demographics": False}
        cursor = self.db.participants.find(query)
        total = self.db.participants.count_documents(query)
        self.stats['total_unmatched'] = total

        logger.info(f"Found {total:,} unmatched participants")

        if self.limit:
            logger.info(f"Limiting to {self.limit} participants")

        processed = 0
        for participant in cursor:
            self._process_participant(participant)
            processed += 1
            self.stats['processed'] += 1

            if processed % 500 == 0:
                logger.info(f"Processed {processed:,}/{total:,}...")

            if self.limit and processed >= self.limit:
                break

        self._print_stats()

    def _process_participant(self, participant: Dict):
        """Process a single participant"""
        participant_id = participant['participant_id']

        if self.verbose:
            logger.info(f"Processing: {participant_id[:40]}...")

        # Get best contact data from exposures
        contact_data = self.get_best_contact_data(participant_id)

        phone = contact_data.get('phone')
        address = contact_data.get('address')
        zipcode = contact_data.get('zip') or participant.get('address', {}).get('zip')

        if phone or address:
            self.stats['contact_data_found'] += 1

        if self.verbose:
            logger.info(f"  Phone: {phone}, Address: {address}, ZIP: {zipcode}")

        # Get all possible counties for this ZIP
        counties_to_try = []
        if zipcode:
            zip_key = zipcode[:5]
            counties_to_try = self.zip_to_counties.get(zip_key, [])

        # If no ZIP available, try email matching across ALL counties
        if not counties_to_try and participant.get('email'):
            counties_to_try = self.all_counties  # Search all counties for email
            if self.verbose:
                logger.info(f"  No ZIP, searching all {len(counties_to_try)} counties for email")

        if not counties_to_try:
            if self.verbose:
                logger.info(f"  No ZIP and no email, skipping")
            self.stats['still_unmatched'] += 1
            return

        # Try matching in each county (ordered by data volume)
        residence_ref = None
        demographic_ref = None
        match_method = "no_match"
        matched_county = None

        for county in counties_to_try:
            matcher = ResidenceMatcher(self.county_db, county=county)
            residence_ref, demographic_ref, match_method = matcher.match(
                phone=phone,
                email=participant.get('email'),
                first_name=None,
                last_name=None,
                address=address,
                zipcode=zipcode
            )

            if match_method not in ("no_match", "collection_not_found"):
                matched_county = county
                if self.verbose:
                    logger.info(f"  ✓ Matched in {matched_county} via {match_method}")
                break

        if match_method in ("no_match", "collection_not_found"):
            if self.verbose:
                logger.info(f"  No match found in {len(counties_to_try)} counties")
            self.stats['still_unmatched'] += 1
            return

        county = matched_county
        self.stats['by_county'][county]['processed'] += 1

        # Match found!
        self.stats['newly_matched'] += 1
        self.stats['match_methods'][match_method] += 1
        self.stats['by_county'][county]['matched'] += 1

        if self.verbose:
            logger.info(f"  ✓ Matched via {match_method}")

        # Build update
        update_doc = {
            "updated_at": datetime.utcnow()
        }

        # Update contact data on participant
        if phone and not participant.get('phone'):
            update_doc["phone"] = PhoneNormalizer.normalize(phone)
        if address and not participant.get('address', {}).get('raw'):
            update_doc["address.raw"] = address
            update_doc["address.street"] = AddressNormalizer.normalize(address)
        if county:
            update_doc["address.county"] = county

        # Update linkage
        county_key = county.replace('County', '').strip() if county else None
        update_doc["linkage.method"] = match_method
        update_doc["linkage.confidence"] = 1.0 if "exact" in match_method or match_method in ("email", "phone") else 0.8
        update_doc["linkage.matched_at"] = datetime.utcnow()
        update_doc["linkage.county_key"] = county_key

        # Get demographics
        if demographic_ref:
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

        # Get residence
        if residence_ref:
            if "linkage.parcel_id" not in update_doc:
                update_doc["linkage.parcel_id"] = residence_ref.parcel_id
            update_doc["data_quality.has_residence"] = True

            res_coll_name = f"{county}Residential"
            if res_coll_name in self.county_db.list_collection_names():
                res_record = self.county_db[res_coll_name].find_one(
                    {"parcel_id": residence_ref.parcel_id}
                )
                if res_record:
                    residence = Residence.from_county_record(res_record)
                    update_doc["residence"] = residence.model_dump()

        # Update analysis_ready flag
        has_demographics = update_doc.get("data_quality.has_demographics", False)
        has_engagement = participant.get('data_quality', {}).get('has_engagement', False)
        update_doc["data_quality.analysis_ready"] = has_demographics and has_engagement

        if not self.dry_run:
            self.db.participants.update_one(
                {"participant_id": participant_id},
                {"$set": update_doc}
            )

    def _print_stats(self):
        """Print statistics"""
        print("\n" + "=" * 80)
        print("REMATCH STATISTICS")
        print("=" * 80)

        print(f"\nParticipants:")
        print(f"  Total unmatched:        {self.stats['total_unmatched']:,}")
        print(f"  Processed:              {self.stats['processed']:,}")
        print(f"  Contact data found:     {self.stats['contact_data_found']:,}")

        print(f"\nResults:")
        print(f"  Newly matched:          {self.stats['newly_matched']:,}")
        print(f"  Still unmatched:        {self.stats['still_unmatched']:,}")

        if self.stats['newly_matched'] > 0 and self.stats['processed'] > 0:
            rate = self.stats['newly_matched'] / self.stats['processed'] * 100
            print(f"  New match rate:         {rate:.1f}%")

        if self.stats['match_methods']:
            print(f"\nMatch Methods:")
            for method, count in sorted(self.stats['match_methods'].items(), key=lambda x: -x[1]):
                print(f"  {method:25s}: {count:,}")

        if self.stats['by_county']:
            print(f"\nBy County (top 10):")
            sorted_counties = sorted(
                self.stats['by_county'].items(),
                key=lambda x: x[1]['processed'],
                reverse=True
            )[:10]
            for county, counts in sorted_counties:
                rate = (counts['matched'] / counts['processed'] * 100) if counts['processed'] > 0 else 0
                print(f"  {county:30s}: {counts['matched']:4d}/{counts['processed']:4d} ({rate:.1f}%)")

        print("=" * 80)

        if self.dry_run:
            print("\n⚠️  DRY RUN - No changes made")
            print("   Run with --live to apply changes")

    def close(self):
        """Close connections"""
        self.client.close()
        self.county_client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Rematch unmatched participants in campaign_data')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change')
    parser.add_argument('--live', action='store_true', help='Actually update database')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--limit', type=int, help='Limit participants to process')

    args = parser.parse_args()

    if not args.dry_run and not args.live:
        print("ERROR: Must specify --dry-run or --live")
        return 1

    dry_run = not args.live

    rematcher = CampaignDataRematcher(
        dry_run=dry_run,
        verbose=args.verbose,
        limit=args.limit
    )

    try:
        rematcher.rematch_participants()
        return 0
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1
    finally:
        rematcher.close()


if __name__ == '__main__':
    sys.exit(main())
