"""
Export matched participant and county data to CSV

Columns:
- Name (FirstName LastName)
- Campaign name
- County
- Opened (0/1)
- Clicked (0/1)
- Applied (always 0)
- Age (from demographic data)
- Income (from demographic data)
- Year home built (calculated from residential age)
"""
import os
import sys
import csv
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the matching script
from match_participants_optimized import (
    OptimizedParticipantMatcher,
    MatchResult,
    MatchQuality
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MatchedDataExporter:
    """Export matched participant and county data to CSV"""

    def __init__(self):
        """Initialize MongoDB connections"""
        # MONGO_DB - participant data
        self.mongo_host = os.getenv('MONGODB_HOST', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT', '27017'))
        self.mongo_db = os.getenv('MONGODB_DATABASE', 'emailoctopus_db')

        # Connect to database
        logger.info(f"Connecting to participant DB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db}")
        self.client = MongoClient(self.mongo_host, self.mongo_port)
        self.db = self.client[self.mongo_db]

        # Cache for campaign names
        self.campaign_cache = {}
        self._load_campaign_cache()

    def _load_campaign_cache(self):
        """Load campaign ID to name mapping"""
        logger.info("Loading campaign names...")
        campaigns = self.db.campaigns.find({}, {'campaign_id': 1, 'name': 1})

        for campaign in campaigns:
            campaign_id = campaign.get('campaign_id')
            campaign_name = campaign.get('name', 'Unknown')
            self.campaign_cache[campaign_id] = campaign_name

        logger.info(f"Loaded {len(self.campaign_cache)} campaign names")

    def get_campaign_name(self, campaign_id: str) -> str:
        """Get campaign name from cache"""
        return self.campaign_cache.get(campaign_id, 'Unknown')

    def extract_csv_row(self, match_result: MatchResult) -> Dict:
        """
        Extract CSV row data from match result

        Returns dictionary with all required fields
        """
        participant = match_result.participant_data
        engagement = participant.get('engagement', {})

        campaign_id = participant.get('campaign_id', '')
        campaign_name = self.get_campaign_name(campaign_id)

        # Engagement (as 0/1)
        opened = 1 if engagement.get('opened', False) else 0
        clicked = 1 if engagement.get('clicked', False) else 0
        applied = 0  # Always 0 as requested

        # Initialize fields
        name = ''
        county = match_result.county_name or ''
        age = None
        income = None
        year_built = None

        # Extract county data if matched
        if match_result.match_quality != MatchQuality.NO_MATCH and match_result.county_record:
            demo_record = match_result.county_record

            # Name - from demographic data customer_name
            name = demo_record.get('customer_name', '')

            # Age - from demographic data
            # Field name is 'age in two-year increments - 1st individual'
            age = demo_record.get('age in two-year increments - 1st individual')
            if age is None or age == -1:
                age = None

            # Income - from demographic data
            income = demo_record.get('estimated_income')
            if income is None or income == -1:
                income = None

            # Year built - from residential data (no conversion, use actual year)
            if match_result.residential_record:
                res_record = match_result.residential_record
                year_built = res_record.get('age')

                if year_built is not None and year_built == -1:
                    year_built = None

        return {
            'Name': name,
            'Campaign': campaign_name,
            'County': county,
            'Opened': opened,
            'Clicked': clicked,
            'Applied': applied,
            'Age': age if age is not None else '',
            'Income': income if income is not None else '',
            'YearBuilt': year_built if year_built is not None else ''
        }

    def export_to_csv(self, match_results: List[MatchResult], output_path: str):
        """
        Export match results to CSV file (only matched records with names)

        Args:
            match_results: List of MatchResult objects
            output_path: Path to output CSV file
        """
        logger.info(f"Exporting {len(match_results)} results to {output_path}")

        # CSV headers
        fieldnames = [
            'Name',
            'Campaign',
            'County',
            'Opened',
            'Clicked',
            'Applied',
            'Age',
            'Income',
            'YearBuilt'
        ]

        # Count matches for reporting
        matched_count = 0
        unmatched_count = 0

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in match_results:
                row = self.extract_csv_row(result)

                # Only export rows with names (matched to county data)
                if row['Name']:
                    writer.writerow(row)
                    matched_count += 1
                else:
                    unmatched_count += 1

        logger.info(f"Export complete:")
        logger.info(f"  - Matched records exported: {matched_count}")
        logger.info(f"  - Unmatched records skipped: {unmatched_count}")
        logger.info(f"  - Total records processed: {len(match_results)}")

    def export_unmatched_debug(self, match_results: List[MatchResult], output_path: str, limit: int = 10):
        """
        Export first N unmatched participants to debug CSV

        Args:
            match_results: List of MatchResult objects
            output_path: Path to output debug CSV file
            limit: Number of unmatched records to export (default: 10)
        """
        logger.info(f"Exporting up to {limit} unmatched participants for debugging to {output_path}")

        # Debug CSV headers - include participant fields
        fieldnames = [
            'Email',
            'FirstName',
            'LastName',
            'Address',
            'City',
            'ZIP',
            'Cell',
            'Campaign',
            'County_Lookup',
            'Opened',
            'Clicked',
            'Match_Quality',
            'Match_Method'
        ]

        count = 0
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in match_results:
                # Only export unmatched records
                if result.match_quality == MatchQuality.NO_MATCH:
                    participant = result.participant_data
                    fields = participant.get('fields', {})
                    engagement = participant.get('engagement', {})
                    campaign_id = participant.get('campaign_id', '')

                    row = {
                        'Email': result.participant_email,
                        'FirstName': fields.get('FirstName', ''),
                        'LastName': fields.get('LastName', ''),
                        'Address': fields.get('Address', ''),
                        'City': fields.get('City', ''),
                        'ZIP': fields.get('ZIP', ''),
                        'Cell': fields.get('Cell', ''),
                        'Campaign': self.get_campaign_name(campaign_id),
                        'County_Lookup': result.county_name or 'NO_ZIPCODE',
                        'Opened': 1 if engagement.get('opened', False) else 0,
                        'Clicked': 1 if engagement.get('clicked', False) else 0,
                        'Match_Quality': result.match_quality.value,
                        'Match_Method': result.match_method or 'none'
                    }

                    writer.writerow(row)
                    count += 1

                    if count >= limit:
                        break

        logger.info(f"Debug export complete: {count} unmatched records exported")

    def close(self):
        """Close database connections"""
        self.client.close()


def main():
    """Main execution"""
    logger.info("Starting matched data export process...")

    # Run matching
    logger.info("Step 1: Running participant matching...")
    matcher = OptimizedParticipantMatcher()

    try:
        results = matcher.run_matching()
        matcher.print_statistics()
    finally:
        matcher.close()

    # Export to CSV
    logger.info("\nStep 2: Exporting to CSV...")
    exporter = MatchedDataExporter()

    try:
        # Generate output filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = Path(__file__).parent.parent / 'data' / 'exports'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f'matched_participants_{timestamp}.csv'
        debug_path = output_dir / f'unmatched_debug_{timestamp}.csv'

        # Export matched records
        exporter.export_to_csv(results, str(output_path))

        # Export debug CSV with unmatched records
        exporter.export_unmatched_debug(results, str(debug_path), limit=50)

        # Count missing data statistics
        matched_count = sum(1 for r in results if r.match_quality != MatchQuality.NO_MATCH)
        unmatched_count = len(results) - matched_count
        no_zipcode = sum(1 for r in results if not r.county_name)
        with_zipcode_unmatched = unmatched_count - no_zipcode

        print("\n" + "="*70)
        print("EXPORT COMPLETE")
        print("="*70)
        print(f"Matched output: {output_path}")
        print(f"Debug output:   {debug_path}")
        print()
        print(f"Total participants processed: {len(results)}")
        print(f"  ✓ Matched (exported):       {matched_count} ({matched_count/len(results)*100:.1f}%)")
        print(f"  ✗ Unmatched (not exported): {unmatched_count} ({unmatched_count/len(results)*100:.1f}%)")
        print()
        print("Missing Data Breakdown:")
        print(f"  - No zipcode:               {no_zipcode}")
        print(f"  - Had zipcode, no match:    {with_zipcode_unmatched}")
        print("="*70 + "\n")

    except Exception as e:
        logger.error(f"Error during export: {e}", exc_info=True)
        return 1
    finally:
        exporter.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
