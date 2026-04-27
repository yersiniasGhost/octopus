"""
Campaign Data Service - Unified data access layer

All collections live in the unified `empower_development` database
(MONGODB_OCTOPUS / MONGODB_CAMPAIGN both point here).

Collections used:
- campaigns: all channels (email, text, mailer, letter) distinguished by
  channel / campaign_type fields
- exposures: per-participant send records, channel-tagged (system of record
  for "how many participants did we reach via channel X")
- applications: applicant submissions (system of record for conversions)
- participants: unified person records
"""

from pymongo import MongoClient
from typing import Dict, List, Any
from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


# Mixed-schema tolerant filters: some docs use `channel`, others `campaign_type`.
def _channel_filter(channel: str) -> Dict[str, Any]:
    return {'$or': [{'channel': channel}, {'campaign_type': channel}]}


class CampaignDataService:
    """Unified data access service for campaigns across all channels."""

    def __init__(self):
        env = EnvVars()
        mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')
        db_name = env.get_env('MONGODB_OCTOPUS') or env.get_env('MONGODB_DATABASE') or 'empower_development'

        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    # ========================================
    # EMAIL CAMPAIGN METHODS
    # ========================================

    def get_email_campaigns(self, limit: int = 20) -> List[Dict]:
        return list(self.db.campaigns.find(_channel_filter('email')).sort('sent_at', -1).limit(limit))

    def get_email_stats(self) -> Dict[str, Any]:
        """Aggregate email campaign statistics from unified campaigns collection.

        Handles mixed statistics shape: legacy docs nest as
        `statistics.opened.unique`, newer docs use a flat int `statistics.opened`.
        """
        match = _channel_filter('email')
        total_campaigns = self.db.campaigns.count_documents(match)

        # Coalesce nested-vs-flat statistics shapes via $ifNull on the nested path.
        pipeline = [
            {'$match': match},
            {'$group': {
                '_id': None,
                'total_sent': {'$sum': {'$ifNull': ['$statistics.sent.unique', {'$ifNull': ['$statistics.total_sent', 0]}]}},
                'total_opened': {'$sum': {'$ifNull': ['$statistics.opened.unique', {'$ifNull': ['$statistics.opened', 0]}]}},
                'total_clicked': {'$sum': {'$ifNull': ['$statistics.clicked.unique', {'$ifNull': ['$statistics.clicked', 0]}]}}
            }}
        ]
        result = list(self.db.campaigns.aggregate(pipeline))
        stats = result[0] if result else {'total_sent': 0, 'total_opened': 0, 'total_clicked': 0}
        stats['total_campaigns'] = total_campaigns
        stats.pop('_id', None)
        return stats

    def get_email_participants_count(self) -> int:
        """Distinct participants reached via email (from exposures, system of record)."""
        return len(self.db.exposures.distinct('participant_id', {'channel': 'email'}))

    # ========================================
    # TEXT CAMPAIGN METHODS
    # ========================================

    def get_text_campaigns(self, page: int = 1, per_page: int = 20) -> List[Dict]:
        skip = (page - 1) * per_page
        match = _channel_filter('text')
        campaigns = list(
            self.db.campaigns.find(match).sort('sent_at', -1).skip(skip).limit(per_page)
        )

        # Normalize legacy fields the template expects
        for c in campaigns:
            if 'name' not in c:
                c['name'] = f"{c.get('agency','Unknown')} - {c.get('message_key', c.get('message_type','Unknown'))}"
            c.setdefault('campaign_type', 'text')
            if 'sent_time' in c and 'sent_at' not in c:
                c['sent_at'] = c['sent_time']

            # Legacy template expects: statistics.{sent,delivered,clicked,failed}.unique
            stats = c.get('statistics') or {}
            def _u(v):
                return v.get('unique', 0) if isinstance(v, dict) else (v or 0)
            c['statistics'] = {
                'sent': {'unique': _u(stats.get('sent')) or stats.get('total_sent') or c.get('sent_count', 0)},
                'delivered': {'unique': _u(stats.get('delivered')) or c.get('delivered_count', 0)},
                'clicked': {'unique': _u(stats.get('clicked')) or c.get('responses_count', 0)},
                'failed': {'unique': _u(stats.get('failed')) or c.get('error_count', 0)},
            }
        return campaigns

    def get_text_campaigns_count(self) -> int:
        return self.db.campaigns.count_documents(_channel_filter('text'))

    def get_text_stats(self) -> Dict[str, Any]:
        match = _channel_filter('text')
        total_campaigns = self.db.campaigns.count_documents(match)

        pipeline = [
            {'$match': match},
            {'$group': {
                '_id': None,
                'total_sent': {'$sum': {'$ifNull': ['$statistics.sent.unique', {'$ifNull': ['$statistics.total_sent', {'$ifNull': ['$sent_count', 0]}]}]}},
                'total_delivered': {'$sum': {'$ifNull': ['$statistics.delivered.unique', {'$ifNull': ['$statistics.delivered', {'$ifNull': ['$delivered_count', 0]}]}]}},
                'total_clicked': {'$sum': {'$ifNull': ['$statistics.clicked.unique', {'$ifNull': ['$statistics.clicked', {'$ifNull': ['$responses_count', 0]}]}]}},
                'total_failed': {'$sum': {'$ifNull': ['$statistics.failed.unique', {'$ifNull': ['$statistics.failed', {'$ifNull': ['$error_count', 0]}]}]}},
            }}
        ]
        result = list(self.db.campaigns.aggregate(pipeline))
        stats = result[0] if result else {'total_sent': 0, 'total_delivered': 0, 'total_clicked': 0, 'total_failed': 0}
        stats['total_campaigns'] = total_campaigns
        stats.pop('_id', None)
        return stats

    def get_text_participants_count(self) -> int:
        return len(self.db.exposures.distinct('participant_id', {'channel': 'text'}))

    # ========================================
    # MAILER / LETTER CAMPAIGN METHODS
    # ========================================

    def get_mailer_campaigns(self, limit: int = 20) -> List[Dict]:
        return list(self.db.campaigns.find(_channel_filter('mailer')).sort('sent_at', -1).limit(limit))

    def get_mailer_stats(self) -> Dict[str, Any]:
        return {'total_campaigns': self.db.campaigns.count_documents(_channel_filter('mailer'))}

    def get_letter_campaigns(self, limit: int = 20) -> List[Dict]:
        return list(self.db.campaigns.find(_channel_filter('letter')).sort('sent_at', -1).limit(limit))

    def get_letter_stats(self) -> Dict[str, Any]:
        return {'total_campaigns': self.db.campaigns.count_documents(_channel_filter('letter'))}

    # ========================================
    # APPLICANT METHODS (Conversions) — backed by `applications` collection
    # Documents are projected to the flat shape the template expects.
    # ========================================

    def get_total_applicants_count(self) -> int:
        # Exclude test records (is_test=True flagged for QA exclusions)
        return self.db.applications.count_documents({'is_test': {'$ne': True}})

    def get_recent_applicants(self, limit: int = 10) -> List[Dict]:
        """Return recent applications projected to the flat legacy template shape."""
        cursor = self.db.applications.find(
            {'is_test': {'$ne': True}}
        ).sort('created_at', -1).limit(limit)

        flattened = []
        for a in cursor:
            applicant = a.get('applicant') or {}
            address = a.get('address') or {}
            pm = a.get('participant_match') or {}
            flattened.append({
                'first_name': applicant.get('first_name'),
                'last_name': applicant.get('last_name'),
                'email': applicant.get('email'),
                'city': address.get('city'),
                'county': address.get('county'),
                'zip_code': address.get('zip'),
                'created_at': a.get('created_at'),
                'match_info': {
                    'match_quality': pm.get('match_method'),
                },
            })
        return flattened

    def get_applicants_by_county(self) -> Dict[str, int]:
        pipeline = [
            {'$match': {'is_test': {'$ne': True}, 'address.county': {'$ne': None, '$exists': True}}},
            {'$group': {'_id': '$address.county', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10},
        ]
        results = self.db.applications.aggregate(pipeline)
        return {r['_id']: r['count'] for r in results}

    def get_applicant_match_quality_stats(self) -> Dict[str, int]:
        """Breakdown by match method (email / address / phone / etc.)."""
        pipeline = [
            {'$match': {'is_test': {'$ne': True}}},
            {'$group': {'_id': '$participant_match.match_method', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
        ]
        results = self.db.applications.aggregate(pipeline)
        return {r['_id']: r['count'] for r in results if r['_id']}

    def get_applicant_summary_stats(self) -> Dict[str, Any]:
        total_count = self.get_total_applicants_count()
        by_county = self.get_applicants_by_county()
        match_quality = self.get_applicant_match_quality_stats()
        return {
            'total': total_count,
            'by_county': by_county,
            'match_quality': match_quality,
            'top_counties': list(by_county.items())[:5],
        }

    # ========================================
    # CROSS-CHANNEL ANALYTICS
    # ========================================

    def get_all_campaign_stats(self) -> Dict[str, Any]:
        return {
            'email': self.get_email_stats(),
            'text': self.get_text_stats(),
            'mailer': self.get_mailer_stats(),
            'letter': self.get_letter_stats(),
        }

    def get_overall_conversion_stats(self) -> Dict[str, Any]:
        email_participants = self.get_email_participants_count()
        text_participants = self.get_text_participants_count()
        total_participants = email_participants + text_participants

        total_applicants = self.get_total_applicants_count()

        conversion_rate = (total_applicants / total_participants * 100) if total_participants > 0 else 0.0

        return {
            'participants': {
                'email': email_participants,
                'text': text_participants,
                'total': total_participants,
            },
            'applicants': {'total': total_applicants},
            'conversion': {
                'rate': round(conversion_rate, 2),
                'ratio': f"{total_applicants}/{total_participants}",
            },
        }

    # ========================================
    # APPLICANT DASHBOARD (per-tab builders)
    # ========================================

    def _build_applicant_overview(self) -> Dict[str, Any]:
        """Overview tab data: KPIs, weekly time series, match quality donut, recent applicants."""
        from datetime import datetime, timezone

        match_filter = {'is_test': {'$ne': True}}
        total = self.db.applications.count_documents(match_filter)

        # This-month count
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month = self.db.applications.count_documents({
            **match_filter, 'entry_date': {'$gte': month_start}
        })

        # Match rate
        matched = self.db.applications.count_documents({
            **match_filter, 'participant_match.match_method': {'$ne': None}
        })
        match_rate_pct = round((matched / total * 100), 1) if total > 0 else 0.0

        # Top county
        top_county_results = list(self.db.applications.aggregate([
            {'$match': {**match_filter, 'address.county': {'$ne': None}}},
            {'$group': {'_id': '$address.county', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}, {'$limit': 1},
        ]))
        top_county = top_county_results[0]['_id'] if top_county_results else None

        # Top channel
        top_channel_results = list(self.db.applications.aggregate([
            {'$match': {**match_filter, 'attribution.utm.utm_medium': {'$ne': None}}},
            {'$group': {'_id': '$attribution.utm.utm_medium', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}, {'$limit': 1},
        ]))
        top_channel = top_channel_results[0]['_id'] if top_channel_results else None

        # Weekly time series, last 6 months
        six_months_ago = now.replace(hour=0, minute=0, second=0, microsecond=0)
        six_months_ago = six_months_ago.replace(month=((now.month - 6 - 1) % 12) + 1,
                                                 year=now.year - (1 if now.month <= 6 else 0))
        ts_results = list(self.db.applications.aggregate([
            {'$match': {**match_filter, 'entry_date': {'$gte': six_months_ago}}},
            {'$group': {
                '_id': {'$dateTrunc': {'date': '$entry_date', 'unit': 'week'}},
                'count': {'$sum': 1},
            }},
            {'$sort': {'_id': 1}},
        ]))
        time_series = {
            'labels': [r['_id'].strftime('%Y-%m-%d') for r in ts_results if r['_id']],
            'counts': [r['count'] for r in ts_results if r['_id']],
        }

        # Match quality donut (null bucketed as 'unmatched')
        mq_results = list(self.db.applications.aggregate([
            {'$match': match_filter},
            {'$group': {'_id': '$participant_match.match_method', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
        ]))
        match_quality = {
            'labels': [(r['_id'] if r['_id'] else 'unmatched') for r in mq_results],
            'counts': [r['count'] for r in mq_results],
        }

        # Recent 25 applicants (flat shape, JSON-safe)
        recent_cursor = self.db.applications.find(match_filter).sort('entry_date', -1).limit(25)
        recent_applicants = []
        for a in recent_cursor:
            applicant = a.get('applicant') or {}
            address = a.get('address') or {}
            utm = (a.get('attribution') or {}).get('utm') or {}
            pm = a.get('participant_match') or {}
            entry_date = a.get('entry_date')
            recent_applicants.append({
                'name': f"{applicant.get('first_name','')} {applicant.get('last_name','')}".strip() or '(unknown)',
                'county': address.get('county'),
                'zip': address.get('zip'),
                'channel': utm.get('utm_medium'),
                'entry_date': entry_date.isoformat() if hasattr(entry_date, 'isoformat') else (entry_date or ''),
                'match_method': pm.get('match_method'),
            })

        return {
            'kpis': {
                'total_applicants': total,
                'this_month': this_month,
                'match_rate_pct': match_rate_pct,
                'top_county': top_county,
                'top_channel': top_channel,
            },
            'time_series': time_series,
            'match_quality': match_quality,
            'recent_applicants': recent_applicants,
        }
