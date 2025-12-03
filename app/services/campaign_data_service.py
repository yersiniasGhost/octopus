"""
Campaign Data Service - Multi-database access layer

Handles data access for campaigns across multiple databases:
- Email campaigns (emailoctopus_db)
- Text/SMS campaigns (empowersaves_development_db)
- Mailer campaigns (empowersaves_development_db)
- Letter campaigns (empowersaves_development_db)
"""

from pymongo import MongoClient
from typing import Dict, List, Any, Optional
from src.utils.envvars import EnvVars
import logging

logger = logging.getLogger(__name__)


class CampaignDataService:
    """
    Unified data access service for campaigns across multiple databases.
    """

    def __init__(self):
        env = EnvVars()
        mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')

        self.client = MongoClient(mongo_uri)
        self.email_db = self.client['emailoctopus_db']
        self.empower_db = self.client['empower']  # Changed from empowersaves_development_db

    # ========================================
    # EMAIL CAMPAIGN METHODS (emailoctopus_db)
    # ========================================

    def get_email_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get email campaigns from emailoctopus_db"""
        try:
            return list(self.email_db.campaigns.find(
                {'campaign_type': 'email'}
            ).sort('sent_at', -1).limit(limit))
        except Exception as e:
            logger.error(f"Error fetching email campaigns: {str(e)}")
            return []

    def get_email_stats(self) -> Dict[str, Any]:
        """Aggregate email campaign statistics - ONLY email campaigns"""
        try:
            # Get total EMAIL campaign count (filter by campaign_type)
            total_campaigns = self.email_db.campaigns.count_documents({'campaign_type': 'email'})

            # Get aggregate statistics - ONLY for email campaigns
            pipeline = [
                {'$match': {'campaign_type': 'email'}},  # Filter to email campaigns only
                {'$group': {
                    '_id': None,
                    'total_sent': {'$sum': '$statistics.sent.unique'},
                    'total_opened': {'$sum': '$statistics.opened.unique'},
                    'total_clicked': {'$sum': '$statistics.clicked.unique'}
                }}
            ]
            result = list(self.email_db.campaigns.aggregate(pipeline))

            stats = result[0] if result else {}
            stats['total_campaigns'] = total_campaigns

            return stats
        except Exception as e:
            logger.error(f"Error fetching email stats: {str(e)}")
            return {'total_campaigns': 0, 'total_sent': 0, 'total_opened': 0, 'total_clicked': 0}

    def get_email_participants_count(self) -> int:
        """Count participants contacted via email campaigns"""
        try:
            return self.email_db.participants.count_documents({
                'email_address': {'$ne': None}
            })
        except Exception as e:
            logger.error(f"Error counting email participants: {str(e)}")
            return 0

    # ========================================
    # TEXT CAMPAIGN METHODS (empowersaves_development_db)
    # ========================================

    def get_text_campaigns(self, page: int = 1, per_page: int = 20) -> List[Dict]:
        """Get text campaigns from emailoctopus_db.text_campaigns with pagination"""
        try:
            # Calculate skip value for pagination
            skip = (page - 1) * per_page

            # Text campaigns are stored in emailoctopus_db.text_campaigns
            campaigns = list(self.email_db.text_campaigns.find({}).sort('sent_time', -1).skip(skip).limit(per_page))

            # Transform to match expected structure
            for campaign in campaigns:
                # Map agency and message_key to name if name doesn't exist
                if 'name' not in campaign:
                    agency = campaign.get('agency', 'Unknown')
                    message_key = campaign.get('message_key', 'Unknown')
                    campaign['name'] = f"{agency} - {message_key}"

                # Add campaign_type for consistency
                campaign['campaign_type'] = 'text'

                # Map sent_time to sent_at for consistency
                if 'sent_time' in campaign and 'sent_at' not in campaign:
                    campaign['sent_at'] = campaign['sent_time']

                # Create statistics structure matching email campaigns
                campaign['statistics'] = {
                    'sent': {'unique': campaign.get('sent_count', 0)},
                    'delivered': {'unique': campaign.get('delivered_count', 0)},
                    'clicked': {'unique': campaign.get('responses_count', 0)},
                    'failed': {'unique': campaign.get('error_count', 0)}
                }

            return campaigns
        except Exception as e:
            logger.error(f"Error fetching text campaigns: {str(e)}")
            return []

    def get_text_campaigns_count(self) -> int:
        """Get total count of text campaigns"""
        try:
            return self.email_db.text_campaigns.count_documents({})
        except Exception as e:
            logger.error(f"Error counting text campaigns: {str(e)}")
            return 0

    def get_text_stats(self) -> Dict[str, Any]:
        """Aggregate text campaign statistics from emailoctopus_db.text_campaigns"""
        try:
            # Get total campaign count from text_campaigns collection
            total_campaigns = self.email_db.text_campaigns.count_documents({})

            # Get aggregate statistics using actual field names
            pipeline = [
                {'$group': {
                    '_id': None,
                    'total_sent': {'$sum': '$sent_count'},
                    'total_delivered': {'$sum': '$delivered_count'},
                    'total_clicked': {'$sum': '$responses_count'},
                    'total_failed': {'$sum': '$error_count'}
                }}
            ]
            result = list(self.email_db.text_campaigns.aggregate(pipeline))

            if result:
                stats = result[0]
                stats['total_campaigns'] = total_campaigns
                # Remove the _id field from aggregation
                stats.pop('_id', None)
            else:
                stats = {
                    'total_campaigns': total_campaigns,
                    'total_sent': 0,
                    'total_delivered': 0,
                    'total_clicked': 0,
                    'total_failed': 0
                }

            return stats
        except Exception as e:
            logger.error(f"Error fetching text stats: {str(e)}")
            return {'total_campaigns': 0, 'total_sent': 0, 'total_delivered': 0, 'total_clicked': 0}

    def get_text_participants_count(self) -> int:
        """Count participants contacted via text campaigns"""
        try:
            return self.empower_db.participants.count_documents({
                'phone_number': {'$ne': None}
            })
        except Exception as e:
            logger.error(f"Error counting text participants: {str(e)}")
            return 0

    # ========================================
    # MAILER CAMPAIGN METHODS (empowersaves_development_db)
    # ========================================

    def get_mailer_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get mailer campaigns from empowersaves_development_db"""
        try:
            return list(self.empower_db.campaigns.find(
                {'campaign_type': 'mailer'}
            ).sort('sent_at', -1).limit(limit))
        except Exception as e:
            logger.error(f"Error fetching mailer campaigns: {str(e)}")
            return []

    def get_mailer_stats(self) -> Dict[str, Any]:
        """Get mailer campaign statistics"""
        try:
            total_campaigns = self.empower_db.campaigns.count_documents({'campaign_type': 'mailer'})
            return {'total_campaigns': total_campaigns}
        except Exception as e:
            logger.error(f"Error fetching mailer stats: {str(e)}")
            return {'total_campaigns': 0}

    # ========================================
    # LETTER CAMPAIGN METHODS (empowersaves_development_db)
    # ========================================

    def get_letter_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get letter campaigns from empowersaves_development_db"""
        try:
            return list(self.empower_db.campaigns.find(
                {'campaign_type': 'letter'}
            ).sort('sent_at', -1).limit(limit))
        except Exception as e:
            logger.error(f"Error fetching letter campaigns: {str(e)}")
            return []

    def get_letter_stats(self) -> Dict[str, Any]:
        """Get letter campaign statistics"""
        try:
            total_campaigns = self.empower_db.campaigns.count_documents({'campaign_type': 'letter'})
            return {'total_campaigns': total_campaigns}
        except Exception as e:
            logger.error(f"Error fetching letter stats: {str(e)}")
            return {'total_campaigns': 0}

    # ========================================
    # APPLICANT METHODS (Conversions)
    # ========================================

    def get_total_applicants_count(self) -> int:
        """Count total applicants across all campaigns"""
        try:
            return self.empower_db.applicants.count_documents({})
        except Exception as e:
            logger.error(f"Error counting applicants: {str(e)}")
            return 0

    def get_recent_applicants(self, limit: int = 10) -> List[Dict]:
        """Get most recent applicants"""
        try:
            applicants = list(self.empower_db.applicants.find(
                {},
                {
                    'first_name': 1,
                    'last_name': 1,
                    'email': 1,
                    'city': 1,
                    'county': 1,
                    'zip_code': 1,
                    'created_at': 1,
                    'match_info.match_quality': 1,
                    '_id': 0
                }
            ).sort('created_at', -1).limit(limit))
            return applicants
        except Exception as e:
            logger.error(f"Error fetching recent applicants: {str(e)}")
            return []

    def get_applicants_by_county(self) -> Dict[str, int]:
        """Get applicant count by county"""
        try:
            pipeline = [
                {'$match': {'county': {'$ne': None, '$exists': True}}},
                {'$group': {
                    '_id': '$county',
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ]
            results = list(self.empower_db.applicants.aggregate(pipeline))
            return {result['_id']: result['count'] for result in results}
        except Exception as e:
            logger.error(f"Error fetching applicants by county: {str(e)}")
            return {}

    def get_applicant_match_quality_stats(self) -> Dict[str, int]:
        """Get applicant match quality statistics"""
        try:
            pipeline = [
                {'$group': {
                    '_id': '$match_info.match_quality',
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}}
            ]
            results = list(self.empower_db.applicants.aggregate(pipeline))
            return {result['_id']: result['count'] for result in results if result['_id']}
        except Exception as e:
            logger.error(f"Error fetching match quality stats: {str(e)}")
            return {}

    def get_applicant_summary_stats(self) -> Dict[str, Any]:
        """Get comprehensive applicant statistics"""
        try:
            total_count = self.get_total_applicants_count()
            by_county = self.get_applicants_by_county()
            match_quality = self.get_applicant_match_quality_stats()

            return {
                'total': total_count,
                'by_county': by_county,
                'match_quality': match_quality,
                'top_counties': list(by_county.items())[:5] if by_county else []
            }
        except Exception as e:
            logger.error(f"Error fetching applicant summary stats: {str(e)}")
            return {
                'total': 0,
                'by_county': {},
                'match_quality': {},
                'top_counties': []
            }

    # ========================================
    # CROSS-CHANNEL ANALYTICS
    # ========================================

    def get_all_campaign_stats(self) -> Dict[str, Any]:
        """Get aggregated stats for all campaign types"""
        return {
            'email': self.get_email_stats(),
            'text': self.get_text_stats(),
            'mailer': self.get_mailer_stats(),
            'letter': self.get_letter_stats()
        }

    def get_recent_campaigns_all_types(self, limit: int = 10) -> List[Dict]:
        """Get most recent campaigns across all types"""
        try:
            # Combine campaigns from both databases
            email_campaigns = list(self.email_db.campaigns.find(
                {},
                {'name': 1, 'campaign_type': 1, 'sent_at': 1, '_id': 0}
            ).sort('sent_at', -1).limit(limit))

            # Set campaign_type for email campaigns if not set
            for campaign in email_campaigns:
                if 'campaign_type' not in campaign:
                    campaign['campaign_type'] = 'email'

            other_campaigns = list(self.empower_db.campaigns.find(
                {'campaign_type': {'$in': ['text', 'mailer', 'letter']}},
                {'name': 1, 'campaign_type': 1, 'sent_at': 1, '_id': 0}
            ).sort('sent_at', -1).limit(limit))

            # Merge and sort by sent_at
            all_campaigns = email_campaigns + other_campaigns
            all_campaigns.sort(key=lambda x: x.get('sent_at', ''), reverse=True)

            return all_campaigns[:limit]
        except Exception as e:
            logger.error(f"Error fetching recent campaigns: {str(e)}")
            return []

    def get_overall_conversion_stats(self) -> Dict[str, Any]:
        """Calculate overall conversion statistics"""
        try:
            # Total participants (all channels)
            email_participants = self.get_email_participants_count()
            text_participants = self.get_text_participants_count()
            total_participants = email_participants + text_participants

            # Total applicants
            total_applicants = self.get_total_applicants_count()

            # Calculate conversion rate
            conversion_rate = 0.0
            if total_participants > 0:
                conversion_rate = (total_applicants / total_participants) * 100

            return {
                'participants': {
                    'email': email_participants,
                    'text': text_participants,
                    'total': total_participants
                },
                'applicants': {
                    'total': total_applicants
                },
                'conversion': {
                    'rate': round(conversion_rate, 2),
                    'ratio': f"{total_applicants}/{total_participants}"
                }
            }
        except Exception as e:
            logger.error(f"Error calculating conversion stats: {str(e)}")
            return {
                'participants': {'email': 0, 'text': 0, 'total': 0},
                'applicants': {'total': 0},
                'conversion': {'rate': 0.0, 'ratio': '0/0'}
            }
