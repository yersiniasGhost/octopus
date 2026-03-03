#!/usr/bin/env python3
"""
Attribute applications to likely campaigns.

This script links applications to the campaigns that likely influenced them:

1. UTM Direct (highest confidence):
   - Parse utm_medium, utm_campaign, utm_content from source URL
   - Match to campaigns by channel type and timing

2. Date Window (fallback):
   - Find campaigns sent to applicant's county within N days before application
   - Weight by recency and channel type

Usage:
    python scripts/attribute_applications_to_campaigns.py
    python scripts/attribute_applications_to_campaigns.py --window-days 14
    python scripts/attribute_applications_to_campaigns.py --dry-run
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient
from pymongo.collection import Collection
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class CampaignAttributor:
    """Attribute applications to likely influential campaigns."""

    # Map UTM medium values to campaign channel types
    UTM_MEDIUM_TO_CHANNEL = {
        'letter': 'letter',
        'sms': 'text',
        'text': 'text',
        'email': 'email',
        'mailer': 'mailer'
    }

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "empower_development"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.applications: Collection = self.db.applications
        self.campaigns: Collection = self.db.campaigns
        self.exposures: Collection = self.db.exposures

    def get_channel_from_utm(self, utm_medium: Optional[str]) -> Optional[str]:
        """Map UTM medium to campaign channel."""
        if not utm_medium:
            return None
        return self.UTM_MEDIUM_TO_CHANNEL.get(utm_medium.lower())

    def find_campaigns_by_utm(self, app: dict) -> List[dict]:
        """Find campaigns matching UTM parameters.

        Uses UTM content (e.g., "COAD Wednesday", "MVCAP Friday") to match
        specific campaign sends.
        """
        matches = []
        utm = app.get('attribution', {}).get('utm', {})

        if not utm.get('utm_source'):
            return matches

        channel = self.get_channel_from_utm(utm.get('utm_medium'))
        utm_content = utm.get('utm_content', '')
        entry_date = app.get('entry_date')

        if not entry_date:
            return matches

        # Build query based on available UTM data
        query = {}

        if channel:
            query['campaign_type'] = channel

        # Look for campaigns sent within 30 days before application
        query['sent_at'] = {
            '$gte': entry_date - timedelta(days=30),
            '$lte': entry_date
        }

        campaigns = list(self.campaigns.find(query))

        for camp in campaigns:
            confidence = 0.7  # Base confidence for UTM match

            # Boost confidence if utm_content matches campaign name patterns
            if utm_content:
                camp_name = camp.get('name', '').lower()
                utm_lower = utm_content.lower()

                # Check for agency/timing patterns in utm_content
                # e.g., "COAD Wednesday" -> campaign targeting COAD on Wednesday
                if any(word in camp_name for word in utm_lower.split()):
                    confidence = 0.9

            # Boost for recency (campaigns closer to application date)
            days_before = (entry_date - camp.get('sent_at', entry_date)).days
            if days_before <= 3:
                confidence = min(confidence + 0.05, 0.95)
            elif days_before <= 7:
                confidence = min(confidence + 0.02, 0.95)

            matches.append({
                'campaign_id': camp['campaign_id'],
                'confidence': round(confidence, 2),
                'method': 'utm_direct'
            })

        return matches

    def find_campaigns_by_date_window(self, app: dict, window_days: int = 14) -> List[dict]:
        """Find campaigns by date proximity and county.

        For applications without UTM data, find campaigns that:
        1. Were sent within window_days before the application
        2. Targeted the applicant's county (via exposures)
        """
        matches = []
        entry_date = app.get('entry_date')
        county = app.get('address', {}).get('county')
        participant_id = app.get('participant_match', {}).get('participant_id')

        if not entry_date:
            return matches

        # Date window
        start_date = entry_date - timedelta(days=window_days)
        end_date = entry_date

        # Strategy 1: If matched to participant, use their exposure history
        if participant_id:
            exposures = list(self.exposures.find({
                'participant_id': participant_id,
                'sent_at': {'$gte': start_date, '$lte': end_date}
            }))

            for exp in exposures:
                days_before = (entry_date - exp.get('sent_at', entry_date)).days

                # Calculate confidence based on recency
                if days_before <= 3:
                    confidence = 0.8
                elif days_before <= 7:
                    confidence = 0.6
                else:
                    confidence = 0.4

                # Boost for engaged exposures
                if exp.get('unified_status') == 'engaged':
                    confidence = min(confidence + 0.15, 0.85)
                elif exp.get('unified_status') == 'received':
                    confidence = min(confidence + 0.05, 0.85)

                matches.append({
                    'campaign_id': exp['campaign_id'],
                    'confidence': round(confidence, 2),
                    'method': 'date_window'
                })

            return matches

        # Strategy 2: Find campaigns targeting the county in the time window
        if county:
            # Get campaigns in the window
            campaigns = list(self.campaigns.find({
                'sent_at': {'$gte': start_date, '$lte': end_date}
            }))

            for camp in campaigns:
                days_before = (entry_date - camp.get('sent_at', entry_date)).days

                # Lower base confidence for county-only matching
                if days_before <= 3:
                    confidence = 0.5
                elif days_before <= 7:
                    confidence = 0.35
                else:
                    confidence = 0.2

                matches.append({
                    'campaign_id': camp['campaign_id'],
                    'confidence': round(confidence, 2),
                    'method': 'county_exposure'
                })

        return matches

    def attribute_application(self, app: dict, window_days: int = 14) -> List[dict]:
        """Attribute a single application to likely campaigns.

        Priority:
        1. UTM direct match (if UTM params present)
        2. Date window match (fallback)

        Returns deduplicated list sorted by confidence.
        """
        matches = []

        # Try UTM first
        utm = app.get('attribution', {}).get('utm', {})
        if utm.get('utm_source'):
            matches = self.find_campaigns_by_utm(app)

        # Fall back to date window if no UTM matches
        if not matches:
            matches = self.find_campaigns_by_date_window(app, window_days)

        # Deduplicate by campaign_id, keeping highest confidence
        seen = {}
        for m in matches:
            cid = m['campaign_id']
            if cid not in seen or m['confidence'] > seen[cid]['confidence']:
                seen[cid] = m

        # Sort by confidence descending
        result = sorted(seen.values(), key=lambda x: x['confidence'], reverse=True)

        return result

    def run_attribution(self, window_days: int = 14, dry_run: bool = False) -> Dict:
        """Run attribution for all applications.

        Args:
            window_days: Days before application to look for campaigns
            dry_run: If True, don't update database

        Returns:
            Statistics dict
        """
        stats = {
            'total': 0,
            'attributed': 0,
            'utm_direct': 0,
            'date_window': 0,
            'county_exposure': 0,
            'no_match': 0,
            'avg_campaigns_per_app': 0
        }

        total_campaigns = 0
        apps = list(self.applications.find({}))
        stats['total'] = len(apps)

        logger.info(f"Running attribution for {len(apps)} applications (window={window_days} days)")

        for app in apps:
            matches = self.attribute_application(app, window_days)

            if matches:
                stats['attributed'] += 1
                total_campaigns += len(matches)

                # Track primary attribution method
                primary_method = matches[0]['method']
                if primary_method == 'utm_direct':
                    stats['utm_direct'] += 1
                elif primary_method == 'date_window':
                    stats['date_window'] += 1
                elif primary_method == 'county_exposure':
                    stats['county_exposure'] += 1

                if not dry_run:
                    self.applications.update_one(
                        {'_id': app['_id']},
                        {'$set': {'attribution.likely_campaigns': matches}}
                    )
            else:
                stats['no_match'] += 1

        if stats['attributed'] > 0:
            stats['avg_campaigns_per_app'] = round(total_campaigns / stats['attributed'], 2)

        return stats

    def print_attribution_summary(self):
        """Print summary of attribution results."""
        total = self.applications.count_documents({})
        attributed = self.applications.count_documents({
            'attribution.likely_campaigns': {'$exists': True, '$ne': []}
        })

        # Method distribution
        pipeline = [
            {'$match': {'attribution.likely_campaigns.0': {'$exists': True}}},
            {'$project': {'method': {'$arrayElemAt': ['$attribution.likely_campaigns.method', 0]}}},
            {'$group': {'_id': '$method', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        method_dist = list(self.applications.aggregate(pipeline))

        # Confidence distribution
        pipeline = [
            {'$match': {'attribution.likely_campaigns.0': {'$exists': True}}},
            {'$project': {'confidence': {'$arrayElemAt': ['$attribution.likely_campaigns.confidence', 0]}}},
            {'$bucket': {
                'groupBy': '$confidence',
                'boundaries': [0, 0.3, 0.5, 0.7, 0.9, 1.0],
                'default': 'other',
                'output': {'count': {'$sum': 1}}
            }}
        ]
        confidence_dist = list(self.applications.aggregate(pipeline))

        # Top campaigns by attribution count
        pipeline = [
            {'$unwind': '$attribution.likely_campaigns'},
            {'$group': {
                '_id': '$attribution.likely_campaigns.campaign_id',
                'count': {'$sum': 1},
                'avg_confidence': {'$avg': '$attribution.likely_campaigns.confidence'}
            }},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]
        top_campaigns = list(self.applications.aggregate(pipeline))

        print("\n" + "=" * 60)
        print("CAMPAIGN ATTRIBUTION SUMMARY")
        print("=" * 60)
        print(f"\nTotal applications: {total}")
        print(f"Attributed: {attributed} ({100 * attributed / total:.1f}%)" if total else "")

        print("\nAttribution Method Distribution:")
        for item in method_dist:
            print(f"  {item['_id']}: {item['count']}")

        print("\nConfidence Distribution:")
        for item in confidence_dist:
            bucket = item['_id']
            if bucket == 'other':
                continue
            print(f"  {bucket:.1f}-{bucket + 0.2:.1f}: {item['count']}")

        print("\nTop 10 Attributed Campaigns:")
        for item in top_campaigns:
            print(f"  {item['_id']}: {item['count']} apps (avg conf: {item['avg_confidence']:.2f})")

        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Attribute applications to campaigns')
    parser.add_argument('--window-days', type=int, default=14,
                        help='Days before application to look for campaigns (default: 14)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run without updating database')
    parser.add_argument('--summary-only', action='store_true',
                        help='Only print attribution summary')

    args = parser.parse_args()

    attributor = CampaignAttributor()

    if args.summary_only:
        attributor.print_attribution_summary()
        return

    stats = attributor.run_attribution(
        window_days=args.window_days,
        dry_run=args.dry_run
    )

    print("\nAttribution Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    if not args.dry_run:
        attributor.print_attribution_summary()


if __name__ == '__main__':
    main()
