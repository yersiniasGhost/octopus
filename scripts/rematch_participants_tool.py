#!/usr/bin/env python3
"""
Tool: Re-match Participants to Demographics

Re-runs residence/demographic matching for participants who currently lack references.
Uses the corrected zipcode-to-county cache and 8-strategy ResidenceMatcher.

Usage:
    # Dry run (show what would change)
    python scripts/rematch_participants_tool.py --dry-run

    # Dry run with verbose output
    python scripts/rematch_participants_tool.py --dry-run --verbose

    # Live update (actually write changes)
    python scripts/rematch_participants_tool.py --live

    # Limit to specific count (for testing)
    python scripts/rematch_participants_tool.py --dry-run --limit 100
"""
import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

from src.tools.residence_matcher import ResidenceMatcher, PhoneNormalizer

load_dotenv()

ZIPCODE_COUNTY_MAP = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'


class ParticipantRematcher:
    """Re-match participants lacking residence/demographic references"""

    def __init__(self, dry_run: bool = True, verbose: bool = False, limit: Optional[int] = None):
        self.dry_run = dry_run
        self.verbose = verbose
        self.limit = limit

        # MongoDB - county data (has demographic/residential collections)
        self.mongo_host = os.getenv('MONGODB_HOST_RM', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.mongo_db = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        print(f"Connecting to MongoDB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db}")
        self.client = MongoClient(self.mongo_host, self.mongo_port)
        self.db = self.client[self.mongo_db]

        # Load zipcode mapping
        print(f"Loading zipcode cache: {ZIPCODE_COUNTY_MAP}")
        with open(ZIPCODE_COUNTY_MAP, 'r') as f:
            data = json.load(f)
            self.zipcode_map = data.get('zipcode_map', {})
        print(f"  Loaded {len(self.zipcode_map)} zipcode mappings")

        # Statistics
        self.stats = {
            'total_unmatched': 0,
            'processed': 0,
            'matched_residence': 0,
            'matched_demographic': 0,
            'still_no_match': 0,
            'no_county': 0,
            'no_zipcode': 0,
            'match_methods': defaultdict(int),
            'by_county': defaultdict(lambda: {'processed': 0, 'matched': 0}),
        }

    def get_county_from_zipcode(self, zipcode) -> Optional[str]:
        """Map zipcode to county"""
        if not zipcode:
            return None
        clean_zip = re.sub(r'\D', '', str(zipcode))[:5]
        return self.zipcode_map.get(clean_zip)

    def find_unmatched_participants(self):
        """Find participants without residence_ref or demographic_ref"""
        print("\nFinding participants without demographic/residence references...")

        # Query for participants lacking references
        query = {
            '$or': [
                {'residence_ref': {'$exists': False}},
                {'residence_ref': None},
                {'demographic_ref': {'$exists': False}},
                {'demographic_ref': None},
            ]
        }

        participants_coll = self.db['participants']
        total = participants_coll.count_documents(query)
        self.stats['total_unmatched'] = total

        print(f"  Found {total:,} participants without references")

        if self.limit:
            print(f"  Limiting to first {self.limit} participants")
            cursor = participants_coll.find(query).limit(self.limit)
        else:
            cursor = participants_coll.find(query)

        return cursor

    def extract_participant_info(self, participant: Dict) -> Dict:
        """Extract contact info from participant record"""
        fields = participant.get('fields', {})

        return {
            '_id': participant.get('_id'),
            'contact_id': participant.get('contact_id'),
            'email': participant.get('email_address'),
            'phone': fields.get('Cell') or participant.get('contact_id'),
            'first_name': fields.get('FirstName'),
            'last_name': fields.get('LastName'),
            'address': fields.get('Address'),
            'city': fields.get('City'),
            'zipcode': fields.get('ZIP'),
            'has_engagement': bool(participant.get('engagement')),
        }

    def match_participant(self, info: Dict) -> Tuple[Optional[Dict], Optional[Dict], str]:
        """
        Match participant to residence/demographic data

        Returns:
            (residence_ref_dict, demographic_ref_dict, match_method)
        """
        zipcode = info.get('zipcode')
        if not zipcode:
            self.stats['no_zipcode'] += 1
            return None, None, "no_zipcode"

        county = self.get_county_from_zipcode(zipcode)
        if not county:
            self.stats['no_county'] += 1
            return None, None, "no_county"

        # Track by county
        self.stats['by_county'][county]['processed'] += 1

        # Use ResidenceMatcher with 8 strategies
        matcher = ResidenceMatcher(self.db, county=county)
        residence_ref, demographic_ref, match_method = matcher.match(
            phone=info.get('phone'),
            email=info.get('email'),
            first_name=info.get('first_name'),
            last_name=info.get('last_name'),
            address=info.get('address'),
            zipcode=zipcode
        )

        if match_method in ("no_match", "collection_not_found"):
            self.stats['still_no_match'] += 1
            return None, None, match_method

        # Convert to dicts for MongoDB storage
        residence_dict = residence_ref.model_dump() if residence_ref else None
        demographic_dict = demographic_ref.model_dump() if demographic_ref else None

        if residence_dict:
            self.stats['matched_residence'] += 1
        if demographic_dict:
            self.stats['matched_demographic'] += 1

        self.stats['match_methods'][match_method] += 1
        self.stats['by_county'][county]['matched'] += 1

        return residence_dict, demographic_dict, match_method

    def rematch_all(self):
        """Re-match all unmatched participants"""
        print(f"\n{'='*80}")
        print(f"RE-MATCHING PARTICIPANTS")
        print(f"{'='*80}")
        print(f"Mode: {'DRY RUN (no changes)' if self.dry_run else 'LIVE UPDATE'}")
        print(f"{'='*80}\n")

        participants_coll = self.db['participants']
        cursor = self.find_unmatched_participants()

        for idx, participant in enumerate(cursor, 1):
            self.stats['processed'] += 1

            info = self.extract_participant_info(participant)

            if self.verbose:
                print(f"\n[{idx}] Processing {info['contact_id']} (ZIP: {info.get('zipcode', 'N/A')})")

            residence_dict, demographic_dict, match_method = self.match_participant(info)

            if self.verbose:
                if residence_dict or demographic_dict:
                    parcel = residence_dict.get('parcel_id') if residence_dict else demographic_dict.get('parcel_id')
                    print(f"  ✅ Matched via {match_method} → parcel {parcel}")
                else:
                    print(f"  ❌ {match_method}")

            # Update if matched and not dry run
            if (residence_dict or demographic_dict) and not self.dry_run:
                update = {}
                if residence_dict:
                    update['residence_ref'] = residence_dict
                if demographic_dict:
                    update['demographic_ref'] = demographic_dict

                participants_coll.update_one(
                    {'_id': info['_id']},
                    {'$set': update}
                )

            # Progress output
            if not self.verbose and idx % 500 == 0:
                print(f"  Processed {idx:,} participants...")

    def print_statistics(self):
        """Print re-matching statistics"""
        print(f"\n{'='*80}")
        print(f"RE-MATCHING STATISTICS")
        print(f"{'='*80}")

        print(f"\nParticipants:")
        print(f"  Total without references:   {self.stats['total_unmatched']:,}")
        print(f"  Processed:                  {self.stats['processed']:,}")

        print(f"\nMatching Results:")
        matched = self.stats['matched_residence'] + self.stats['matched_demographic']
        print(f"  Matched to residence:       {self.stats['matched_residence']:,}")
        print(f"  Matched to demographic:     {self.stats['matched_demographic']:,}")
        print(f"  Total newly matched:        {matched:,}")
        print(f"  Still no match:             {self.stats['still_no_match']:,}")
        print(f"  No zipcode:                 {self.stats['no_zipcode']:,}")
        print(f"  No county for zipcode:      {self.stats['no_county']:,}")

        if matched > 0 and self.stats['processed'] > 0:
            rate = (matched / self.stats['processed']) * 100
            print(f"\n  Match rate:                 {rate:.1f}%")

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

        print(f"\n{'='*80}")

        if self.dry_run:
            print("\n⚠️  DRY RUN - No changes were made to the database")
            print("    Run with --live to apply these changes")
        else:
            print(f"\n✅ Updated {matched:,} participant records")

    def close(self):
        """Close MongoDB connection"""
        self.client.close()


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Re-match participants to demographic data')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change (no writes)')
    parser.add_argument('--live', action='store_true', help='Actually update the database')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--limit', type=int, help='Limit number of participants to process')

    args = parser.parse_args()

    # Require explicit --live or --dry-run
    if not args.dry_run and not args.live:
        print("ERROR: Must specify either --dry-run or --live")
        print("  --dry-run: Show what would change without modifying database")
        print("  --live:    Actually update participant records")
        return 1

    dry_run = not args.live

    print(f"{'='*80}")
    print(f"PARTICIPANT RE-MATCHING TOOL")
    print(f"{'='*80}")
    print(f"Started at: {datetime.now()}")

    rematcher = ParticipantRematcher(
        dry_run=dry_run,
        verbose=args.verbose,
        limit=args.limit
    )

    try:
        rematcher.rematch_all()
        rematcher.print_statistics()
        print(f"\nCompleted at: {datetime.now()}")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        rematcher.close()


if __name__ == '__main__':
    sys.exit(main())
