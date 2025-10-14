"""Main application routes"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user
import logging
from pymongo import MongoClient

from app.services import EmailOctopusClient
from app.services.emailoctopus_client import EmailOctopusAPIError
from src.utils.envvars import EnvVars

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Landing page - public route"""
    return render_template('index.html', title='Welcome')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Dashboard - requires authentication

    Displays overview statistics from EmailOctopus API:
    - Total campaigns count
    - Active lists count
    - Total contacts count (sum across all lists)
    - Campaign statistics for charts
    """
    # Default counts (used if API fails)
    stats = {
        'total_campaigns': 0,
        'total_lists': 0,
        'total_contacts': 0,
        'api_connected': False
    }

    # Campaign chart data - structured for separate sorting
    campaign_data = {
        'sent_chart': {
            'names': [],
            'values': []
        },
        'engagement_chart': {
            'names': [],
            'opened': [],
            'clicked': []
        },
        'click_through_rate_chart': {
            'names': [],
            'values': []
        },
        'zipcode_chart': {
            'zipcodes': [],
            'opened': [],
            'clicked': []
        }
    }

    try:
        # Initialize EmailOctopus client
        client = EmailOctopusClient()

        # Fetch campaign count
        # Note: API returns max 100 per page, so we get first page to count
        campaigns_result = client.get_campaigns(limit=100, page=1)
        campaigns_data = campaigns_result.get('data', [])
        stats['total_campaigns'] = len(campaigns_data)

        # If there's a next page, we know there are more than 100
        # For now, we'll show the count from first page
        # Future enhancement: iterate through all pages for exact count

        # Fetch lists count
        lists_result = client.get_lists(limit=100, page=1)
        lists_data = lists_result.get('data', [])
        stats['total_lists'] = len(lists_data)

        # Calculate total contacts across all lists
        total_contacts = 0
        for lst in lists_data:
            # Each list object may have a counts field with subscriber info
            if 'counts' in lst and isinstance(lst['counts'], dict):
                # Get subscribed count (active contacts)
                subscribed = lst['counts'].get('subscribed', 0)
                if isinstance(subscribed, int):
                    total_contacts += subscribed

        stats['total_contacts'] = total_contacts
        stats['api_connected'] = True

        logger.info(f"Dashboard stats: campaigns={stats['total_campaigns']}, "
                   f"lists={stats['total_lists']}, contacts={stats['total_contacts']}")

    except EmailOctopusAPIError as e:
        logger.error(f"EmailOctopus API error on dashboard: {str(e)}")
        # Stats remain at default values (0)

    except Exception as e:
        logger.error(f"Unexpected error fetching dashboard stats: {str(e)}", exc_info=True)
        # Stats remain at default values (0)

    # Fetch campaign statistics from MongoDB for charts
    try:
        env = EnvVars()
        mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')
        client = MongoClient(mongo_uri)
        db = client['emailoctopus_db']

        # Get campaigns with statistics, sorted by name, limit to 20 most recent
        campaigns = list(db.campaigns.find(
            {},
            {'name': 1, 'campaign_id': 1, 'statistics': 1, '_id': 0}
        ).sort('sent_at', -1).limit(20))

        # Get campaign IDs for participant count lookup
        campaign_id_to_name = {}
        for campaign in campaigns:
            campaign_id = campaign.get('campaign_id')
            if campaign_id:
                campaign_id_to_name[campaign_id] = campaign.get('name', 'Unknown')

        # Get participant counts per campaign
        participant_counts = {}
        if campaign_id_to_name:
            pipeline = [
                {'$match': {'campaign_id': {'$in': list(campaign_id_to_name.keys())}}},
                {'$group': {
                    '_id': '$campaign_id',
                    'total_sent': {'$sum': 1}
                }}
            ]
            for result in db.participants.aggregate(pipeline):
                participant_counts[result['_id']] = result['total_sent']

        # Extract data for charts and prepare for sorting
        chart_data_items = []
        for campaign in campaigns:
            name = campaign.get('name', 'Unknown')
            campaign_id = campaign.get('campaign_id', '')
            stats_data = campaign.get('statistics', {})

            # Use participant count for sent, fall back to statistics
            sent_count = participant_counts.get(campaign_id, 0)
            if sent_count == 0:
                sent_count = stats_data.get('sent', {}).get('unique', 0)

            opened_count = stats_data.get('opened', {}).get('unique', 0)
            clicked_count = stats_data.get('clicked', {}).get('unique', 0)

            chart_data_items.append({
                'name': name,
                'sent': sent_count,
                'opened': opened_count,
                'clicked': clicked_count
            })

        # Calculate click-through rate (clicked / opened) for each campaign
        for item in chart_data_items:
            if item['opened'] > 0:
                item['ctr'] = (item['clicked'] / item['opened']) * 100  # as percentage
            else:
                item['ctr'] = 0

        # Sort by opened (highest to lowest) for first two charts
        opened_sorted = sorted(chart_data_items, key=lambda x: x['opened'], reverse=True)

        # Sort by click-through rate (highest to lowest) for third chart
        ctr_sorted = sorted(chart_data_items, key=lambda x: x['ctr'], reverse=True)

        # Populate campaign_data - first two charts use same ordering (by opened)
        campaign_data['sent_chart'] = {
            'names': [item['name'] for item in opened_sorted],
            'values': [item['sent'] for item in opened_sorted]
        }

        campaign_data['engagement_chart'] = {
            'names': [item['name'] for item in opened_sorted],
            'opened': [item['opened'] for item in opened_sorted],
            'clicked': [item['clicked'] for item in opened_sorted]
        }

        # Third chart independently sorted by click-through rate
        campaign_data['click_through_rate_chart'] = {
            'names': [item['name'] for item in ctr_sorted],
            'values': [round(item['ctr'], 1) for item in ctr_sorted]  # Round to 1 decimal
        }

        logger.info(f"Fetched chart data for {len(campaigns)} campaigns")

        # Fetch zipcode engagement data
        zipcode_pipeline = [
            {'$match': {'fields.ZIP': {'$exists': True, '$ne': None, '$ne': ''}}},
            {'$group': {
                '_id': '$fields.ZIP',
                'opened_count': {'$sum': {'$cond': ['$engagement.opened', 1, 0]}},
                'clicked_count': {'$sum': {'$cond': ['$engagement.clicked', 1, 0]}},
                'total': {'$sum': 1}
            }},
            {'$match': {
                'total': {'$gte': 10},
                '_id': {'$ne': None}  # Exclude None zipcodes
            }},
            {'$sort': {'opened_count': -1}},
            {'$limit': 20}  # Top 20 zipcodes by opened count
        ]

        zipcode_results = list(db.participants.aggregate(zipcode_pipeline))

        # Filter out any remaining None/empty zipcodes and convert to strings
        campaign_data['zipcode_chart'] = {
            'zipcodes': [str(result['_id']) for result in zipcode_results if result['_id']],
            'opened': [result['opened_count'] for result in zipcode_results if result['_id']],
            'clicked': [result['clicked_count'] for result in zipcode_results if result['_id']]
        }

        logger.info(f"Fetched zipcode engagement data for {len(zipcode_results)} zipcodes")

    except Exception as e:
        logger.error(f"Error fetching campaign chart data: {str(e)}", exc_info=True)
        # Campaign data remains empty

    return render_template('dashboard.html',
                          title='Dashboard',
                          user=current_user,
                          stats=stats,
                          campaign_data=campaign_data)
