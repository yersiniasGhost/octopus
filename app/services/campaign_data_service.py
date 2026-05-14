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

import re
from pymongo import MongoClient
from typing import Dict, List, Any, Optional
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

    # Canonical unified_status values produced for text exposures.
    _TEXT_STATUS_ORDER = [
        'received', 'clicked', 'engaged', 'opted_out',
        'undeliverable', 'negative_response', 'converted', 'no_engagement',
    ]

    def get_text_campaign_detail(
        self,
        campaign_id: str,
        *,
        exposures_page: int = 1,
        exposures_per_page: int = 25,
        search: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Detail bundle for one text campaign: metadata, live engagement breakdown,
        top zip codes, attributed applications, and a paginated/searchable slice of
        exposures (joined to participants for customer_name display).

        Live counts come from `exposures` aggregations rather than the cached
        `campaigns.statistics` block (which the schema doc explicitly flags as
        drift-prone). Schema-tolerant aggregation handles both flat
        (`text_replied`) and nested (`text_engagement.replied`) exposure shapes.

        `search` matches case-insensitively against participant name, participant_id,
        zip, and city. Pagination is server-side via $facet (count + slice in one
        round-trip).
        """
        campaign = self.db.campaigns.find_one({'campaign_id': campaign_id})
        if not campaign:
            return {}

        exposures_match = {'campaign_id': campaign_id}

        # Unified status counts — the indexed, schema-agnostic source of truth.
        status_counts: Dict[str, int] = {s: 0 for s in self._TEXT_STATUS_ORDER}
        for r in self.db.exposures.aggregate([
            {'$match': exposures_match},
            {'$group': {'_id': '$unified_status', 'n': {'$sum': 1}}},
        ]):
            status_counts[r['_id'] or 'no_engagement'] = r['n']

        total_exposures = sum(status_counts.values())

        # Engagement event counts across both schema variants.
        # $ifNull falls back from nested to flat path so a single agg covers both.
        engagement_pipeline = [
            {'$match': exposures_match},
            {'$group': {
                '_id': None,
                'delivered': {'$sum': {'$cond': [
                    {'$ifNull': ['$text_engagement.delivered', '$text_delivered']}, 1, 0]}},
                'replied': {'$sum': {'$cond': [
                    {'$ifNull': ['$text_engagement.replied', '$text_replied']}, 1, 0]}},
                'opted_out': {'$sum': {'$cond': [
                    {'$ifNull': ['$text_engagement.opted_out', '$text_opted_out']}, 1, 0]}},
                'failed': {'$sum': {'$cond': [
                    {'$ifNull': ['$text_engagement.failed', '$text_failed']}, 1, 0]}},
                'clicked': {'$sum': {'$cond': [
                    {'$ifNull': ['$text_engagement.clicked', '$text_clicked']}, 1, 0]}},
            }},
        ]
        eng = next(iter(self.db.exposures.aggregate(engagement_pipeline)), {}) or {}
        eng.pop('_id', None)

        sent = total_exposures
        delivered = eng.get('delivered', 0)
        clicked = eng.get('clicked', 0)
        replied = eng.get('replied', 0)
        opted_out = eng.get('opted_out', 0)
        failed = eng.get('failed', 0) or status_counts.get('undeliverable', 0)

        def _rate(num, denom):
            return round((num / denom * 100), 2) if denom else 0.0

        engagement = {
            'sent': sent,
            'delivered': delivered,
            'clicked': clicked,
            'replied': replied,
            'opted_out': opted_out,
            'failed': failed,
            'delivery_rate': _rate(delivered, sent),
            'click_rate': _rate(clicked, delivered or sent),
            'reply_rate': _rate(replied, delivered or sent),
            'opt_out_rate': _rate(opted_out, delivered or sent),
        }

        # Top zips by exposure count — gives a quick geographic read.
        top_zips = list(self.db.exposures.aggregate([
            {'$match': {**exposures_match, 'contact_snapshot.zip': {'$nin': [None, '']}}},
            {'$group': {'_id': '$contact_snapshot.zip', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10},
        ]))

        # Other campaigns in the same campaign_group (Section 1/2 splits, retries, etc.).
        related = []
        cg = campaign.get('campaign_group')
        if cg:
            related = list(self.db.campaigns.find(
                {'campaign_group': cg, 'campaign_id': {'$ne': campaign_id}},
                {'campaign_id': 1, 'name': 1, 'sent_at': 1, 'statistics': 1},
            ).sort('sent_at', -1).limit(10))

        # Applications attributed to this campaign (via attribute_applications_to_campaigns).
        attributed_apps = self.db.applications.count_documents({
            'is_test': {'$ne': True},
            'attribution.likely_campaigns.campaign_id': campaign_id,
        })

        # Paginated/searchable recent exposures with $lookup for participant name.
        # Uses $facet to get filtered count + page slice in one round-trip.
        exposures_per_page = max(1, min(exposures_per_page, 200))
        exposures_page = max(1, exposures_page)
        skip = (exposures_page - 1) * exposures_per_page

        # Status filter is applied pre-lookup so the join only runs on the
        # filtered set — cheaper than filtering after the $lookup.
        early_match = dict(exposures_match)
        if status_filter and status_filter in self._TEXT_STATUS_ORDER:
            early_match['unified_status'] = status_filter

        pipeline: List[Dict[str, Any]] = [
            {'$match': early_match},
            {'$lookup': {
                'from': 'participants',
                'localField': 'participant_oid',
                'foreignField': '_id',
                'as': '_p',
                'pipeline': [{'$project': {
                    '_id': 0,
                    'demographics.customer_name': 1,
                    'residence.parcel_owner': 1,
                }}],
            }},
            {'$addFields': {
                # Prefer demographics.customer_name; fall back to residence.parcel_owner.
                '_name': {'$ifNull': [
                    {'$arrayElemAt': ['$_p.demographics.customer_name', 0]},
                    {'$arrayElemAt': ['$_p.residence.parcel_owner', 0]},
                ]},
            }},
        ]

        if search:
            rx = re.escape(search.strip())
            if rx:
                pipeline.append({'$match': {'$or': [
                    {'_name': {'$regex': rx, '$options': 'i'}},
                    {'participant_id': {'$regex': rx, '$options': 'i'}},
                    {'contact_snapshot.zip': {'$regex': rx, '$options': 'i'}},
                    {'contact_snapshot.city': {'$regex': rx, '$options': 'i'}},
                ]}})

        pipeline.append({'$facet': {
            'count': [{'$count': 'n'}],
            'rows': [
                # `_id` tiebreaker keeps pagination stable when many rows share sent_at.
                {'$sort': {'sent_at': -1, '_id': 1}},
                {'$skip': skip},
                {'$limit': exposures_per_page},
                {'$project': {
                    'participant_id': 1, 'unified_status': 1, 'sent_at': 1,
                    'contact_snapshot': 1, 'text_engagement': 1,
                    'text_clicked_at': 1, '_name': 1,
                }},
            ],
        }})

        facet = next(iter(self.db.exposures.aggregate(pipeline)), {}) or {}
        filtered_count = (facet.get('count') or [{}])[0].get('n', 0)
        recent_exposures = facet.get('rows', [])

        # Flatten engagement timestamp across both schema variants for the template.
        # The boolean flags are redundant with unified_status (which is hierarchical),
        # so we only surface clicked_at — the one signal status doesn't carry.
        for e in recent_exposures:
            te = e.get('text_engagement') or {}
            e['_clicked_at'] = te.get('clicked_at') or e.get('text_clicked_at')

        total_pages = max(1, (filtered_count + exposures_per_page - 1) // exposures_per_page)
        exposures_pagination = {
            'page': exposures_page,
            'per_page': exposures_per_page,
            'filtered_count': filtered_count,
            'total_pages': total_pages,
            'has_prev': exposures_page > 1,
            'has_next': exposures_page < total_pages,
            'prev_num': exposures_page - 1 if exposures_page > 1 else None,
            'next_num': exposures_page + 1 if exposures_page < total_pages else None,
            'search': search or '',
            'status_filter': status_filter or '',
        }

        return {
            'campaign': campaign,
            'engagement': engagement,
            'status_breakdown': [
                {'status': s, 'count': status_counts[s]}
                for s in self._TEXT_STATUS_ORDER if status_counts[s] > 0
            ],
            'top_zips': [{'zip': r['_id'], 'count': r['count']} for r in top_zips],
            'related_campaigns': related,
            'attributed_applications': attributed_apps,
            'recent_exposures': recent_exposures,
            'total_exposures': total_exposures,
            'exposures_pagination': exposures_pagination,
        }

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

        # Weekly time series, last 6 months. Snap to day=1 so we don't blow up
        # on day-31 months when the target month has fewer days (e.g. Mar 31 → Sep).
        target_month = ((now.month - 6 - 1) % 12) + 1
        target_year = now.year - (1 if now.month <= 6 else 0)
        six_months_ago = now.replace(year=target_year, month=target_month, day=1,
                                     hour=0, minute=0, second=0, microsecond=0)
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

    # Bin specifications shared by histogram builders.
    _AGE_BOUNDARIES = [0, 30, 45, 60, 75, 200]
    _AGE_LABELS = ['<30', '30-44', '45-59', '60-74', '75+']
    _INCOME_BOUNDARIES = [0, 20000, 40000, 60000, 80000, 10**9]
    _INCOME_LABELS = ['<20k', '20-40k', '40-60k', '60-80k', '80k+']
    _HH_BOUNDARIES = [1, 2, 3, 4, 5, 100]
    _HH_LABELS = ['1', '2', '3', '4', '5+']
    # total_energy_burden is stored as a percentage (e.g. 10.09 means 10.09% of income),
    # not a fraction. Boundaries match that scale; 200 caps observed outliers (max ~101).
    _BURDEN_BOUNDARIES = [0, 6, 10, 15, 200]
    _BURDEN_LABELS = ['<6%', '6-10%', '10-15%', '15%+']
    # Attribution channel taxonomy.
    _CHANNELS = ['text', 'email', 'mailer', 'letter']

    @staticmethod
    def _bucket_results_to_histogram(results, boundaries, labels):
        """Convert Mongo $bucket output to {labels, counts, n} dict in boundary order.

        Contract: caller picks `boundaries[-1]` wide enough that no real value
        overflows; pipelines below set `default: boundaries[-1]`, so any (currently
        impossible) overflow would land in a synthetic bucket whose `_id` is not
        among `boundaries[:-1]` and would be silently dropped from the histogram.
        """
        by_lower = {r['_id']: r['count'] for r in results}
        counts = [by_lower.get(boundaries[i], 0) for i in range(len(labels))]
        return {'labels': labels, 'counts': counts, 'n': sum(counts)}

    @staticmethod
    def _format_utm(results, null_label):
        """Convert Mongo group-by-UTM results to {labels, counts}, replacing None with null_label."""
        labels, counts = [], []
        for r in results:
            labels.append(r['_id'] if r['_id'] else null_label)
            counts.append(r['count'])
        return {'labels': labels, 'counts': counts}

    def _build_applicant_demographics(self) -> Dict[str, Any]:
        """Demographics tab: age/income/household-size histograms, energy burden, income-age scatter."""
        match_filter = {'is_test': {'$ne': True}}

        def _bucket_pipeline(field, boundaries):
            return [
                {'$match': {**match_filter, field: {'$ne': None, '$exists': True}}},
                {'$bucket': {
                    'groupBy': f'${field}',
                    'boundaries': boundaries,
                    'default': boundaries[-1],
                    'output': {'count': {'$sum': 1}},
                }},
            ]

        age_results = list(self.db.applications.aggregate(
            _bucket_pipeline('self_reported.age', self._AGE_BOUNDARIES)
        ))
        income_results = list(self.db.applications.aggregate(
            _bucket_pipeline('self_reported.household_income', self._INCOME_BOUNDARIES)
        ))
        hh_results = list(self.db.applications.aggregate(
            _bucket_pipeline('self_reported.household_members', self._HH_BOUNDARIES)
        ))

        # Energy burden — joined on email from applicants collection.
        burden_results = list(self.db.applicants.aggregate([
            {'$match': {'demographic_ref.total_energy_burden': {'$ne': None}}},
            # Inner join: keep only applicants whose email exists in applications.
            {'$lookup': {
                'from': 'applications',
                'localField': 'email',
                'foreignField': 'applicant.email',
                'as': '_match',
            }},
            {'$match': {'_match.0': {'$exists': True}}},
            {'$bucket': {
                'groupBy': '$demographic_ref.total_energy_burden',
                'boundaries': self._BURDEN_BOUNDARIES,
                'default': self._BURDEN_BOUNDARIES[-1],
                'output': {'count': {'$sum': 1}},
            }},
        ]))

        # Top 3 counties for scatter color coding.
        top_counties_results = list(self.db.applications.aggregate([
            {'$match': {**match_filter, 'address.county': {'$ne': None}}},
            {'$group': {'_id': '$address.county', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}, {'$limit': 3},
        ]))
        top_counties = [r['_id'] for r in top_counties_results]

        # Scatter points (income vs age), grouped client-side by county.
        scatter_points = list(self.db.applications.aggregate([
            {'$match': {
                **match_filter,
                'self_reported.age': {'$ne': None},
                'self_reported.household_income': {'$ne': None},
            }},
            {'$project': {
                'county': '$address.county',
                'age': '$self_reported.age',
                'income': '$self_reported.household_income',
                '_id': 0,
            }},
        ]))
        series_map = {c: [] for c in top_counties}
        series_map['Other'] = []
        for p in scatter_points:
            bucket = p['county'] if p['county'] in top_counties else 'Other'
            series_map[bucket].append({'x': p['age'], 'y': p['income']})

        burden = self._bucket_results_to_histogram(
            burden_results, self._BURDEN_BOUNDARIES, self._BURDEN_LABELS
        )
        burden['total'] = self.db.applications.count_documents(match_filter)

        return {
            'age': self._bucket_results_to_histogram(age_results, self._AGE_BOUNDARIES, self._AGE_LABELS),
            'income': self._bucket_results_to_histogram(income_results, self._INCOME_BOUNDARIES, self._INCOME_LABELS),
            'household_size': self._bucket_results_to_histogram(hh_results, self._HH_BOUNDARIES, self._HH_LABELS),
            'energy_burden': burden,
            'income_age_scatter': {
                # Drop empty series so the template's {% if series %} guard
                # correctly falls back to "No data" when there are no points.
                'series': [
                    {'county': c, 'points': series_map[c]}
                    for c in top_counties + ['Other'] if series_map[c]
                ],
            },
        }

    def _build_applicant_attribution(self) -> Dict[str, Any]:
        """Attribution tab: utm bars + per-channel exposures→applications conversion table."""
        match_filter = {'is_test': {'$ne': True}}

        def _utm_pipeline(field, top_n=None):
            pipe = [
                {'$match': match_filter},
                {'$group': {'_id': f'${field}', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
            ]
            if top_n:
                pipe.append({'$limit': top_n})
            return pipe

        utm_medium = self._format_utm(
            list(self.db.applications.aggregate(_utm_pipeline('attribution.utm.utm_medium'))),
            'Direct/Unknown',
        )
        utm_source = self._format_utm(
            list(self.db.applications.aggregate(_utm_pipeline('attribution.utm.utm_source', top_n=10))),
            '(none)',
        )
        utm_campaign = self._format_utm(
            list(self.db.applications.aggregate(_utm_pipeline('attribution.utm.utm_campaign', top_n=10))),
            '(none)',
        )

        # Channel conversion table — applications grouped by utm_medium (case-insensitive)
        # mapped to the same channel taxonomy used by exposures.
        channel_conversion = []
        for channel in self._CHANNELS:
            apps = self.db.applications.count_documents({
                **match_filter,
                'attribution.utm.utm_medium': {'$regex': f'^{channel}$', '$options': 'i'},
            })
            exposures = self.db.exposures.count_documents({'channel': channel})
            rate = round((apps / exposures * 100), 2) if exposures > 0 else 0.0
            channel_conversion.append({
                'channel': channel,
                'exposures': exposures,
                'applications': apps,
                'conversion_rate': rate,
            })

        return {
            'utm_medium': utm_medium,
            'utm_source': utm_source,
            'utm_campaign': utm_campaign,
            'channel_conversion': channel_conversion,
        }

    def get_applicant_dashboard_data(self) -> Dict[str, Any]:
        """Orchestrate the three per-tab builders. One failing tab does not crash the page."""
        result = {}
        for tab, builder in (
            ('overview', self._build_applicant_overview),
            ('demographics', self._build_applicant_demographics),
            ('attribution', self._build_applicant_attribution),
        ):
            try:
                result[tab] = builder()
            except Exception as e:
                logger.error(f"Applicant dashboard builder '{tab}' failed: {e}", exc_info=True)
                result[tab] = {}
        return result
