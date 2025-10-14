#!/usr/bin/env python3
"""
Debug script to test participant fetching for a specific campaign
"""
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.emailoctopus_client import EmailOctopusClient
from src.utils.envvars import EnvVars

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Reduce noise
logging.getLogger('urllib3').setLevel(logging.WARNING)

def test_fetch(campaign_id: str):
    """Test fetching participants for a campaign"""
    print(f"\n{'='*80}")
    print(f"Testing participant fetch for campaign: {campaign_id}")
    print(f"{'='*80}\n")

    client = EmailOctopusClient()

    # Test each report type individually
    report_types = ['sent', 'opened', 'clicked', 'bounced', 'complained', 'unsubscribed']

    for report_type in report_types:
        print(f"\n--- Testing {report_type} report ---")
        try:
            page = 1
            total = 0

            while page <= 3:  # Only test first 3 pages
                print(f"Fetching page {page}...")
                result = client.get_campaign_report_contacts(
                    campaign_id,
                    report_type,
                    limit=100,
                    page=page
                )

                data = result.get('data', [])
                paging = result.get('paging', {})

                print(f"  Got {len(data)} contacts")
                print(f"  Paging info: {paging}")

                if not data:
                    print(f"  No more data for {report_type}")
                    break

                total += len(data)

                # Handle both dict and list paging responses
                if isinstance(paging, dict):
                    if not paging.get('next'):
                        print(f"  No next page for {report_type}")
                        break
                else:
                    # Empty list means no pagination
                    print(f"  No pagination for {report_type}")
                    break

                page += 1

            print(f"Total {report_type} contacts: {total}")

        except Exception as e:
            print(f"ERROR on {report_type}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_participant_fetch.py <campaign_id>")
        sys.exit(1)

    campaign_id = sys.argv[1]
    test_fetch(campaign_id)
