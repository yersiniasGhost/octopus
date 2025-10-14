"""
MongoDB writer with upsert logic for incremental sync
"""
import logging
from typing import Dict, List
from datetime import datetime

from pymongo.errors import PyMongoError, DuplicateKeyError

from src.tools.mongo import Mongo
from src.models.campaign import Campaign
from src.models.participant import Participant

logger = logging.getLogger(__name__)


class MongoDBWriter:
    """
    Writes campaign and participant data to MongoDB with incremental sync support

    Uses upsert operations to handle both new inserts and updates of existing records.
    """

    def __init__(self, mongo: Mongo):
        """
        Initialize MongoDB writer

        Args:
            mongo: Mongo singleton instance
        """
        self.mongo = mongo
        self.db = mongo.database

    def upsert_campaign(self, campaign: Campaign) -> bool:
        """
        Insert or update campaign in MongoDB

        Args:
            campaign: Campaign model instance

        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.db.campaigns.update_one(
                {'campaign_id': campaign.campaign_id},
                {'$set': campaign.to_mongo_dict()},
                upsert=True
            )

            if result.upserted_id:
                logger.info(f"Inserted new campaign: {campaign.name} ({campaign.campaign_id})")
            elif result.modified_count > 0:
                logger.info(f"Updated campaign: {campaign.name} ({campaign.campaign_id})")
            else:
                logger.debug(f"No changes for campaign: {campaign.name} ({campaign.campaign_id})")

            return True

        except PyMongoError as e:
            logger.error(f"Error upserting campaign {campaign.campaign_id}: {e}")
            return False

    def upsert_participant(self, participant: Participant) -> bool:
        """
        Insert or update participant in MongoDB with engagement data merging

        Uses $setOnInsert for initial data and $max for engagement flags to preserve
        True values across multiple report fetches (sent, opened, clicked, etc.)

        Args:
            participant: Participant model instance

        Returns:
            True if successful, False otherwise
        """
        try:
            participant_dict = participant.to_mongo_dict()

            # Extract engagement data for special handling
            engagement = participant_dict.pop('engagement', {})

            # Build update operations
            update_ops = {
                '$set': participant_dict,  # Update all non-engagement fields
                # Use $max to keep True values (True > False in MongoDB)
                '$max': {
                    'engagement.opened': engagement.get('opened', False),
                    'engagement.clicked': engagement.get('clicked', False),
                    'engagement.bounced': engagement.get('bounced', False),
                    'engagement.complained': engagement.get('complained', False),
                    'engagement.unsubscribed': engagement.get('unsubscribed', False)
                }
            }

            result = self.db.participants.update_one(
                {
                    'campaign_id': participant.campaign_id,
                    'contact_id': participant.contact_id
                },
                update_ops,
                upsert=True
            )

            if result.upserted_id:
                logger.debug(f"Inserted participant: {participant.email_address} for campaign {participant.campaign_id}")
            elif result.modified_count > 0:
                logger.debug(f"Updated participant: {participant.email_address} for campaign {participant.campaign_id}")

            return True

        except DuplicateKeyError:
            # This shouldn't happen due to unique index, but handle gracefully
            logger.warning(f"Duplicate participant: {participant.email_address} in campaign {participant.campaign_id}")
            return True
        except PyMongoError as e:
            logger.error(f"Error upserting participant {participant.email_address}: {e}")
            return False

    def upsert_participants_bulk(self, participants: List[Participant]) -> Dict[str, int]:
        """
        Bulk insert/update participants for efficiency with engagement merging

        Uses $max operator to preserve True engagement values across multiple
        report type fetches (sent, opened, clicked, etc.)

        Args:
            participants: List of Participant model instances

        Returns:
            Dictionary with counts of inserted, updated, and failed records
        """
        if not participants:
            return {'inserted': 0, 'updated': 0, 'failed': 0}

        stats = {'inserted': 0, 'updated': 0, 'failed': 0}

        # Process in batches of 100 for memory efficiency
        batch_size = 100
        for i in range(0, len(participants), batch_size):
            batch = participants[i:i + batch_size]

            for participant in batch:
                try:
                    participant_dict = participant.to_mongo_dict()

                    # Extract engagement data for special handling
                    engagement = participant_dict.pop('engagement', {})

                    # Build update operations
                    update_ops = {
                        '$set': participant_dict,  # Update all non-engagement fields
                        # Use $max to keep True values (True > False in MongoDB)
                        '$max': {
                            'engagement.opened': engagement.get('opened', False),
                            'engagement.clicked': engagement.get('clicked', False),
                            'engagement.bounced': engagement.get('bounced', False),
                            'engagement.complained': engagement.get('complained', False),
                            'engagement.unsubscribed': engagement.get('unsubscribed', False)
                        }
                    }

                    result = self.db.participants.update_one(
                        {
                            'campaign_id': participant.campaign_id,
                            'contact_id': participant.contact_id
                        },
                        update_ops,
                        upsert=True
                    )

                    if result.upserted_id:
                        stats['inserted'] += 1
                    elif result.modified_count > 0:
                        stats['updated'] += 1

                except PyMongoError as e:
                    logger.error(f"Error in bulk upsert: {e}")
                    stats['failed'] += 1

        logger.info(f"Bulk upsert complete: {stats['inserted']} inserted, "
                   f"{stats['updated']} updated, {stats['failed']} failed")

        return stats

    def get_campaign_by_id(self, campaign_id: str) -> Dict:
        """
        Retrieve campaign from MongoDB by campaign_id

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            Campaign document or empty dict if not found
        """
        try:
            campaign = self.db.campaigns.find_one({'campaign_id': campaign_id})
            return campaign or {}
        except PyMongoError as e:
            logger.error(f"Error fetching campaign {campaign_id}: {e}")
            return {}

    def get_participants_for_campaign(self, campaign_id: str) -> List[Dict]:
        """
        Retrieve all participants for a campaign

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            List of participant documents
        """
        try:
            participants = list(self.db.participants.find({'campaign_id': campaign_id}))
            return participants
        except PyMongoError as e:
            logger.error(f"Error fetching participants for campaign {campaign_id}: {e}")
            return []

    def get_sync_statistics(self) -> Dict[str, int]:
        """
        Get overall sync statistics

        Returns:
            Dictionary with counts of campaigns and participants
        """
        try:
            campaign_count = self.db.campaigns.count_documents({})
            participant_count = self.db.participants.count_documents({})

            return {
                'total_campaigns': campaign_count,
                'total_participants': participant_count
            }
        except PyMongoError as e:
            logger.error(f"Error fetching sync statistics: {e}")
            return {
                'total_campaigns': 0,
                'total_participants': 0
            }

    def get_campaigns_needing_sync(self, hours: int = 24) -> List[str]:
        """
        Get list of campaign IDs that haven't been synced recently

        Args:
            hours: Number of hours to consider "recent"

        Returns:
            List of campaign_ids needing sync
        """
        try:
            cutoff_time = datetime.now() - datetime.timedelta(hours=hours)

            campaigns = self.db.campaigns.find(
                {'synced_at': {'$lt': cutoff_time}},
                {'campaign_id': 1}
            )

            return [c['campaign_id'] for c in campaigns]

        except PyMongoError as e:
            logger.error(f"Error fetching campaigns needing sync: {e}")
            return []
