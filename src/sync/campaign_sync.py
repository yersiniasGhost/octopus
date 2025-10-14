"""
Main campaign sync orchestrator

Coordinates fetching data from EmailOctopus, storing in MongoDB, and exporting to CSV.
"""
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime

from src.sync.emailoctopus_fetcher import EmailOctopusFetcher
from src.sync.mongodb_writer import MongoDBWriter
from src.sync.csv_writer import CSVWriter
from src.models.campaign import Campaign
from src.models.participant import Participant
from src.tools.mongo import Mongo

logger = logging.getLogger(__name__)


class CampaignSync:
    """
    Orchestrates complete campaign data synchronization

    Workflow:
    1. Fetch all campaigns from EmailOctopus
    2. For each campaign:
       a. Fetch campaign details and statistics
       b. Upsert campaign to MongoDB
       c. Fetch all participants with engagement data
       d. Upsert participants to MongoDB
       e. Export participants to CSV
    3. Report sync statistics
    """

    def __init__(self, export_dir: str = "data/exports"):
        """
        Initialize campaign sync orchestrator

        Args:
            export_dir: Directory for CSV exports
        """
        # Initialize components
        self.mongo = Mongo()

        self.fetcher = EmailOctopusFetcher()
        self.mongodb_writer = MongoDBWriter(self.mongo)
        self.csv_writer = CSVWriter(export_dir)

        # Sync statistics
        self.stats = {
            'campaigns_processed': 0,
            'campaigns_inserted': 0,
            'campaigns_updated': 0,
            'participants_inserted': 0,
            'participants_updated': 0,
            'csv_files_created': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }

    def sync_all_campaigns(self, campaign_ids: Optional[List[str]] = None) -> Dict:
        """
        Sync all campaigns or specific campaign IDs

        Args:
            campaign_ids: Optional list of specific campaign IDs to sync
                        If None, syncs all campaigns

        Returns:
            Dictionary with sync statistics
        """
        self.stats['start_time'] = datetime.now()
        logger.info("=" * 80)
        logger.info("Starting campaign sync...")
        logger.info("=" * 80)

        # Ensure indexes exist
        try:
            self.mongo.ensure_indexes()
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

        # Fetch campaigns
        if campaign_ids:
            # Sync specific campaigns
            campaigns = []
            for campaign_id in campaign_ids:
                data = self.fetcher.fetch_campaign_with_statistics(campaign_id)
                if data['campaign']:
                    campaigns.append(data['campaign'])
            logger.info(f"Syncing {len(campaigns)} specific campaigns")
        else:
            # Sync all campaigns
            campaigns = self.fetcher.fetch_all_campaigns()
            logger.info(f"Syncing all {len(campaigns)} campaigns")

        # Process each campaign
        for i, campaign_data in enumerate(campaigns, 1):
            campaign_id = campaign_data.get('id')
            campaign_name = campaign_data.get('name', 'Untitled')

            logger.info("-" * 80)
            logger.info(f"Processing campaign {i}/{len(campaigns)}: {campaign_name}")
            logger.info(f"Campaign ID: {campaign_id}")

            try:
                # Sync this campaign
                self.sync_campaign(campaign_id)

                # Add small delay between campaigns to avoid rate limiting
                if i < len(campaigns):  # Don't sleep after last campaign
                    time.sleep(1.0)
                self.stats['campaigns_processed'] += 1

            except Exception as e:
                logger.error(f"Error processing campaign {campaign_id}: {e}")
                self.stats['errors'] += 1

        # Final statistics
        self.stats['end_time'] = datetime.now()
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        logger.info("=" * 80)
        logger.info("Campaign sync complete!")
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"Campaigns processed: {self.stats['campaigns_processed']}")
        logger.info(f"Participants inserted: {self.stats['participants_inserted']}")
        logger.info(f"Participants updated: {self.stats['participants_updated']}")
        logger.info(f"CSV files created: {self.stats['csv_files_created']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("=" * 80)

        return self.stats

    def sync_campaign(self, campaign_id: str) -> bool:
        """
        Sync a single campaign with all its data

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Fetch campaign details and statistics
            logger.info("  → Fetching campaign details and statistics...")
            data = self.fetcher.fetch_campaign_with_statistics(campaign_id)

            if not data['campaign']:
                logger.error(f"  ✗ Failed to fetch campaign {campaign_id}")
                return False

            # 2. Create Campaign model
            campaign = Campaign.from_emailoctopus(
                data['campaign'],
                statistics=data['statistics']
            )

            # 3. Upsert campaign to MongoDB
            logger.info("  → Saving campaign to MongoDB...")
            success = self.mongodb_writer.upsert_campaign(campaign)
            if not success:
                logger.error("  ✗ Failed to save campaign to MongoDB")
                return False

            # Track whether this was new or updated
            existing = self.mongodb_writer.get_campaign_by_id(campaign_id)
            if existing:
                self.stats['campaigns_updated'] += 1
            else:
                self.stats['campaigns_inserted'] += 1

            # 4. Fetch and sync participants
            logger.info("  → Fetching participants...")
            participant_models = []

            for contact_data in self.fetcher.fetch_all_participants(campaign_id):
                report_type = contact_data.pop('_report_type', None)
                participant = Participant.from_emailoctopus(
                    contact_data,
                    campaign_id=campaign_id,
                    report_type=report_type
                )
                participant_models.append(participant)

            logger.info(f"  → Saving {len(participant_models)} participants to MongoDB...")
            bulk_stats = self.mongodb_writer.upsert_participants_bulk(participant_models)

            self.stats['participants_inserted'] += bulk_stats['inserted']
            self.stats['participants_updated'] += bulk_stats['updated']

            # 5. Export to CSV from MongoDB (to get merged engagement data)
            logger.info("  → Exporting to CSV from MongoDB...")
            campaign_dict = {
                'campaign_id': campaign.campaign_id,
                'name': campaign.name,
                'sent_at': campaign.sent_at
            }
            # Get participants from MongoDB with merged engagement data
            mongo_participants = self.mongodb_writer.get_participants_for_campaign(campaign.campaign_id)
            csv_path = self.csv_writer.export_campaign_from_dicts(campaign_dict, mongo_participants)

            logger.info(f"  ✓ Exported to: {csv_path}")
            self.stats['csv_files_created'] += 1

            logger.info(f"  ✓ Campaign sync complete")
            return True

        except Exception as e:
            logger.error(f"  ✗ Error syncing campaign {campaign_id}: {e}", exc_info=True)
            return False

    def sync_incremental(self, hours: int = 24) -> Dict:
        """
        Incremental sync: only sync campaigns that haven't been updated recently

        Args:
            hours: Number of hours to consider "recent"

        Returns:
            Dictionary with sync statistics
        """
        logger.info(f"Running incremental sync (campaigns older than {hours} hours)...")

        campaign_ids = self.mongodb_writer.get_campaigns_needing_sync(hours)

        if not campaign_ids:
            logger.info("All campaigns are up to date")
            return self.stats

        logger.info(f"Found {len(campaign_ids)} campaigns needing sync")
        return self.sync_all_campaigns(campaign_ids=campaign_ids)

    def get_sync_stats(self) -> Dict:
        """Get current sync statistics"""
        return self.stats

    def export_all_to_csv(self) -> int:
        """
        Export all campaigns from MongoDB to CSV files

        Useful for regenerating CSV exports without re-fetching from API.

        Returns:
            Number of CSV files created
        """
        logger.info("Exporting all campaigns from MongoDB to CSV...")

        try:
            # Get all campaigns from MongoDB
            campaigns = list(self.mongo.database.campaigns.find({}))
            logger.info(f"Found {len(campaigns)} campaigns in MongoDB")

            csv_count = 0
            for campaign in campaigns:
                campaign_id = campaign.get('campaign_id')

                # Get participants for this campaign
                participants = self.mongodb_writer.get_participants_for_campaign(campaign_id)

                if not participants:
                    logger.warning(f"No participants found for campaign {campaign_id}")
                    continue

                # Export to CSV
                csv_path = self.csv_writer.export_campaign_from_dicts(campaign, participants)
                logger.info(f"Exported {campaign.get('name')}: {csv_path}")
                csv_count += 1

            logger.info(f"Successfully exported {csv_count} campaigns to CSV")
            return csv_count

        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return 0
