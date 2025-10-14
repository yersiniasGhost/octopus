"""
EmailOctopus data fetcher with pagination support

Handles fetching all campaigns and participants from EmailOctopus API
"""
import logging
import time
from typing import List, Dict, Optional, Generator
from datetime import datetime
from urllib.parse import unquote

from src.tools.emailoctopus_client import EmailOctopusClient, EmailOctopusAPIError

logger = logging.getLogger(__name__)


class EmailOctopusFetcher:
    """
    Fetches campaign and participant data from EmailOctopus API

    Handles pagination automatically and provides generator-based iteration
    for memory-efficient processing of large datasets.
    """

    def __init__(self, client: Optional[EmailOctopusClient] = None):
        """
        Initialize fetcher

        Args:
            client: EmailOctopus client instance (creates new one if not provided)
        """
        self.client = client or EmailOctopusClient()

    def fetch_all_campaigns(self) -> List[Dict]:
        """
        Fetch all campaigns from EmailOctopus API

        Returns:
            List of campaign dictionaries
        """
        logger.info("Fetching all campaigns from EmailOctopus...")
        campaigns = []
        page = 1

        while True:
            try:
                result = self.client.get_campaigns(limit=100, page=page)
                batch = result.get('data', [])

                if not batch:
                    break

                campaigns.extend(batch)
                logger.info(f"Fetched {len(batch)} campaigns (page {page}, total so far: {len(campaigns)})")

                # Check if there are more pages
                paging = result.get('paging', {})
                if not paging.get('next'):
                    break

                page += 1

            except EmailOctopusAPIError as e:
                logger.error(f"Error fetching campaigns page {page}: {e}")
                break

        logger.info(f"Fetched {len(campaigns)} total campaigns")
        return campaigns

    def fetch_campaign_with_statistics(self, campaign_id: str) -> Dict:
        """
        Fetch campaign details with statistics

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            Dictionary with 'campaign' and 'statistics' keys
        """
        try:
            campaign = self.client.get_campaign(campaign_id)
            statistics = self.client.get_campaign_summary(campaign_id)

            return {
                'campaign': campaign,
                'statistics': statistics
            }
        except EmailOctopusAPIError as e:
            logger.error(f"Error fetching campaign {campaign_id}: {e}")
            return {
                'campaign': None,
                'statistics': None
            }

    def fetch_all_participants(self, campaign_id: str) -> Generator[Dict, None, None]:
        """
        Fetch all participants for a campaign (generator for memory efficiency)

        Fetches from multiple sources:
        1. All subscribed contacts from campaign list
        2. Engagement data from report endpoints (opened, clicked, etc.)

        Args:
            campaign_id: EmailOctopus campaign UUID

        Yields:
            Participant dictionaries with engagement data
        """
        logger.info(f"Fetching participants for campaign {campaign_id}...")

        # Track contacts PER REPORT TYPE to avoid pagination loops
        # But allow same contact across different report types for engagement merging
        seen_per_report = {}
        total_contacts_yielded = 0

        # Fetch from all report endpoints to get complete engagement data
        report_types = ['sent', 'opened', 'clicked', 'bounced', 'complained', 'unsubscribed']

        for report_type in report_types:
            logger.info(f"Fetching {report_type} participants...")
            page = 1
            report_count = 0
            next_cursor = None  # For cursor-based pagination
            seen_per_report[report_type] = set()

            while True:
                try:
                    logger.info(f"  → Fetching {report_type} page {page}...")
                    result = self.client.get_campaign_report_contacts(
                        campaign_id,
                        report_type,
                        limit=100,
                        cursor=next_cursor  # Use cursor instead of page number
                    )
                    logger.info(f"  ✓ Received {report_type} page {page}")

                    batch = result.get('data', [])
                    if not batch:
                        logger.debug(f"  No data on {report_type} page {page}, moving to next report type")
                        break

                    # Track duplicates in this batch
                    new_in_batch = 0

                    # Process each contact in batch
                    for item in batch:
                        contact = item.get('contact', {})
                        contact_id = contact.get('id')

                        if not contact_id:
                            continue

                        # Check if we've already processed this contact in THIS report type
                        # (prevents pagination loops, but allows same contact across report types)
                        if contact_id in seen_per_report[report_type]:
                            continue

                        seen_per_report[report_type].add(contact_id)
                        total_contacts_yielded += 1
                        report_count += 1
                        new_in_batch += 1

                        # Add report type for engagement tracking
                        contact['_report_type'] = report_type

                        yield contact

                    # If entire batch was duplicates, pagination is looping - stop
                    if new_in_batch == 0 and len(batch) > 0:
                        logger.warning(f"  Page {page} returned only duplicates - pagination loop detected, stopping")
                        logger.info(f"  Completed {report_type}: {report_count} participants")
                        break

                    # Check pagination (can be dict or empty list for reports with no more pages)
                    paging = result.get('paging', {})
                    if isinstance(paging, dict):
                        next_url = paging.get('next')
                        if not next_url:
                            logger.info(f"  Completed {report_type}: {report_count} unique participants")
                            break

                        # Extract cursor from next URL (format: ...&last=CURSOR)
                        if 'last=' in next_url:
                            next_cursor = next_url.split('last=')[1].split('&')[0]
                            # URL decode to prevent double-encoding
                            next_cursor = unquote(next_cursor)
                        else:
                            next_cursor = None
                    else:
                        # Empty list or other non-dict means no pagination
                        logger.info(f"  Completed {report_type}: {report_count} unique participants (no pagination)")
                        break

                    page += 1

                    # Progress update every 10 pages
                    if page % 10 == 0:
                        logger.info(f"  📊 Progress: {report_count} unique {report_type} participants so far (page {page})")

                    # Add delay between requests to avoid rate limiting
                    time.sleep(0.5)  # 500ms delay between requests

                    # Safety limit to prevent infinite loops
                    if page > 1000:
                        logger.warning(f"  Reached page limit (1000) for {report_type}, stopping")
                        break

                except EmailOctopusAPIError as e:
                    logger.error(f"Error fetching {report_type} participants page {page}: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error fetching {report_type} page {page}: {e}")
                    break

        # Calculate unique contacts across all report types
        all_contacts = set()
        for contacts_set in seen_per_report.values():
            all_contacts.update(contacts_set)

        logger.info(f"Fetched {total_contacts_yielded} total participant records ({len(all_contacts)} unique contacts) for campaign {campaign_id}")

    def fetch_participants_by_engagement(self, campaign_id: str, report_type: str) -> List[Dict]:
        """
        Fetch participants filtered by engagement type

        Args:
            campaign_id: EmailOctopus campaign UUID
            report_type: Report type (opened, clicked, bounced, etc.)

        Returns:
            List of participant dictionaries
        """
        logger.info(f"Fetching {report_type} participants for campaign {campaign_id}...")
        participants = []
        page = 1

        while True:
            try:
                result = self.client.get_campaign_report_contacts(
                    campaign_id,
                    report_type,
                    limit=100,
                    page=page
                )

                batch = result.get('data', [])
                if not batch:
                    break

                # Extract contacts from wrapped structure
                contacts = [item.get('contact', {}) for item in batch]
                participants.extend(contacts)

                logger.info(f"Fetched {len(contacts)} {report_type} participants (page {page}, total: {len(participants)})")

                # Check pagination
                paging = result.get('paging', {})
                if not paging.get('next'):
                    break

                page += 1

            except EmailOctopusAPIError as e:
                logger.error(f"Error fetching {report_type} participants page {page}: {e}")
                break

        return participants

    def get_campaign_statistics_summary(self, campaign_id: str) -> Optional[Dict]:
        """
        Get campaign statistics summary

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            Statistics dictionary or None if error
        """
        try:
            return self.client.get_campaign_summary(campaign_id)
        except EmailOctopusAPIError as e:
            logger.error(f"Error fetching campaign statistics {campaign_id}: {e}")
            return None
