#!/usr/bin/env python3
"""
On-demand participant enrichment with demographic data via email matching.

Reads campaign CSV files, filters to participants who opened, matches by email
to demographic data across all counties, and generates enriched CSV output.
"""
import sys
import os
import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import pymongo
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class DemographicEnricher:
    """Enriches participant data with demographics via email matching"""

    def __init__(self):
        """Initialize connection to remote demographics database"""
        # Get RM database config from environment
        self.host = os.getenv('MONGODB_HOST_RM', '192.168.1.156')
        self.port = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.database = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        logger.info(f'Connecting to remote demographics: {self.host}:{self.port}/{self.database}')

        try:
            self.client = pymongo.MongoClient(
                self.host,
                self.port,
                serverSelectionTimeoutMS=5000
            )
            # Test connection
            self.client.server_info()
            self.db = self.client[self.database]
            logger.info('✓ Connected to remote demographics database')

            # Get list of demographic collections
            self.demographic_collections = [
                c for c in self.db.list_collection_names()
                if 'demographic' in c.lower() and 'county' in c.lower()
            ]
            logger.info(f'Found {len(self.demographic_collections)} demographic collections')

        except Exception as e:
            logger.error(f'✗ Failed to connect to remote database: {e}')
            raise

    def find_demographic(self, email: str) -> Optional[Dict]:
        """
        Find demographic record by email across all county collections

        Args:
            email: Email address to search for

        Returns:
            Demographic record dict or None if not found
        """
        if not email:
            return None

        email_lower = email.lower().strip()

        # Search across all demographic collections
        for collection_name in self.demographic_collections:
            collection = self.db[collection_name]
            record = collection.find_one({'email': email_lower})

            if record:
                # Add source collection to record
                record['_source_collection'] = collection_name
                return record

        return None

    def enrich_participant(self, participant: Dict) -> Dict:
        """
        Enrich single participant with demographic data

        Args:
            participant: Participant dict from CSV

        Returns:
            Enriched participant dict with customer_name field
        """
        email = participant.get('email', '')

        if not email:
            return participant

        # Find demographic match
        demo = self.find_demographic(email)

        if demo:
            # Add customer_name field (original format from demographics)
            participant['customer_name'] = demo.get('customer_name', '')
            participant['_matched'] = True
            participant['_source_county'] = demo.get('_source_collection', '').replace('CountyDemographic', '')
        else:
            participant['customer_name'] = ''
            participant['_matched'] = False
            participant['_source_county'] = ''

        return participant


class EnrichmentProcessor:
    """Processes CSV files for enrichment"""

    def __init__(self, csv_dir: str = 'data/exports', output_dir: str = 'data/enriched'):
        """
        Initialize processor

        Args:
            csv_dir: Directory containing campaign CSV files
            output_dir: Directory for enriched CSV output
        """
        self.csv_dir = Path(csv_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.enricher = DemographicEnricher()
        self.stats = {
            'total_participants': 0,
            'opened_participants': 0,
            'matched_participants': 0,
            'unmatched_participants': 0
        }
        self.unmatched_log = []

    def process_csv(self, csv_path: Path) -> Path:
        """
        Process single CSV file for enrichment

        Args:
            csv_path: Path to campaign CSV file

        Returns:
            Path to enriched CSV file
        """
        logger.info(f'Processing: {csv_path.name}')

        # Read CSV
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.stats['total_participants'] += len(rows)

        # Filter to opened participants
        opened_rows = [r for r in rows if r.get('opened', '').strip().upper() == 'YES']
        self.stats['opened_participants'] += len(opened_rows)

        logger.info(f'  Total: {len(rows)}, Opened: {len(opened_rows)}')

        # Enrich each opened participant
        enriched_rows = []
        for row in opened_rows:
            enriched = self.enricher.enrich_participant(row)
            enriched_rows.append(enriched)

            # Track statistics
            if enriched.get('_matched'):
                self.stats['matched_participants'] += 1
            else:
                self.stats['unmatched_participants'] += 1
                # Log unmatched for review
                self.unmatched_log.append({
                    'campaign': csv_path.name,
                    'email': row.get('email', ''),
                    'city': row.get('city', ''),
                    'zip': row.get('zip', '')
                })

        # Write enriched CSV
        output_path = self.output_dir / f'enriched_{csv_path.name}'

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            # Add customer_name to fieldnames
            fieldnames = list(rows[0].keys()) if rows else []
            if 'customer_name' not in fieldnames:
                # Insert customer_name after last_name
                if 'last_name' in fieldnames:
                    idx = fieldnames.index('last_name') + 1
                    fieldnames.insert(idx, 'customer_name')
                else:
                    fieldnames.append('customer_name')

            # Remove unwanted columns
            columns_to_remove = ['status', 'annual_cost']
            fieldnames = [f for f in fieldnames if f not in columns_to_remove]

            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()

            # Write only opened, enriched participants
            for row in enriched_rows:
                # Convert Yes/No to 1/0
                yes_no_fields = ['opened', 'clicked', 'bounced', 'complained', 'unsubscribed']
                for field in yes_no_fields:
                    if field in row:
                        value = row[field].strip().upper() if row[field] else ''
                        row[field] = '1' if value == 'YES' else '0'

                writer.writerow(row)

        logger.info(f'  ✓ Enriched {len(enriched_rows)} participants → {output_path.name}')
        logger.info(f'  Matched: {sum(1 for r in enriched_rows if r.get("_matched"))}')
        logger.info(f'  Unmatched: {sum(1 for r in enriched_rows if not r.get("_matched"))}')

        return output_path

    def process_all(self) -> None:
        """Process all campaign CSV files"""
        csv_files = list(self.csv_dir.glob('campaign_*.csv'))

        if not csv_files:
            logger.warning(f'No campaign CSV files found in {self.csv_dir}')
            return

        logger.info(f'Found {len(csv_files)} campaign CSV files')
        logger.info('=' * 80)

        for csv_file in csv_files:
            try:
                self.process_csv(csv_file)
            except Exception as e:
                logger.error(f'Error processing {csv_file.name}: {e}')

        # Write unmatched log
        self._write_unmatched_log()

        # Print summary
        self._print_summary()

    def _write_unmatched_log(self) -> None:
        """Write unmatched participants to log file"""
        if not self.unmatched_log:
            logger.info('No unmatched participants to log')
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = self.output_dir / f'unmatched_participants_{timestamp}.csv'

        with open(log_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['campaign', 'email', 'city', 'zip']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.unmatched_log)

        logger.info(f'\n✓ Unmatched log written: {log_path}')

    def _print_summary(self) -> None:
        """Print enrichment summary statistics"""
        logger.info('\n' + '=' * 80)
        logger.info('ENRICHMENT SUMMARY')
        logger.info('=' * 80)
        logger.info(f'Total participants in CSV files: {self.stats["total_participants"]:,}')
        logger.info(f'Participants who opened: {self.stats["opened_participants"]:,}')
        logger.info(f'Successfully matched: {self.stats["matched_participants"]:,}')
        logger.info(f'Unmatched (no demographic): {self.stats["unmatched_participants"]:,}')

        if self.stats['opened_participants'] > 0:
            match_rate = (self.stats['matched_participants'] / self.stats['opened_participants']) * 100
            logger.info(f'Match rate: {match_rate:.1f}%')

        logger.info('=' * 80)
        logger.info(f'\nEnriched files saved to: {self.output_dir}/')


def main():
    """Main entry point"""
    logger.info('Participant Demographic Enrichment Tool')
    logger.info('=' * 80)

    try:
        processor = EnrichmentProcessor()
        processor.process_all()
    except Exception as e:
        logger.error(f'Enrichment failed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
