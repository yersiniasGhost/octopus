"""Main application routes"""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
import logging
from pymongo import MongoClient
import math

from app.services import EmailOctopusClient
from app.services.emailoctopus_client import EmailOctopusAPIError
from app.services.campaign_data_service import CampaignDataService
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
    Main multi-channel dashboard - shows all campaign types
    """
    try:
        # Initialize campaign data service
        service = CampaignDataService()

        # Get stats for all campaign types
        all_stats = service.get_all_campaign_stats()

        # Get recent campaigns across all types
        recent_campaigns = service.get_recent_campaigns_all_types(limit=10)

        # Get conversion stats
        conversion_stats = service.get_overall_conversion_stats()

        # Get detailed applicant information
        recent_applicants = service.get_recent_applicants(limit=10)
        applicant_summary = service.get_applicant_summary_stats()

        logger.info(f"Main dashboard loaded - {all_stats}")

        return render_template('dashboard.html',
                              title='Multi-Channel Dashboard',
                              user=current_user,
                              all_stats=all_stats,
                              recent_campaigns=recent_campaigns,
                              conversion_stats=conversion_stats,
                              recent_applicants=recent_applicants,
                              applicant_summary=applicant_summary)

    except Exception as e:
        logger.error(f"Error loading main dashboard: {str(e)}", exc_info=True)
        # Return empty stats on error
        return render_template('dashboard.html',
                              title='Multi-Channel Dashboard',
                              user=current_user,
                              all_stats={
                                  'email': {'total_campaigns': 0},
                                  'text': {'total_campaigns': 0},
                                  'mailer': {'total_campaigns': 0},
                                  'letter': {'total_campaigns': 0}
                              },
                              recent_campaigns=[],
                              conversion_stats={
                                  'participants': {'total': 0},
                                  'applicants': {'total': 0},
                                  'conversion': {'rate': 0.0}
                              },
                              recent_applicants=[],
                              applicant_summary={
                                  'total': 0,
                                  'by_county': {},
                                  'match_quality': {},
                                  'top_counties': []
                              })


@main_bp.route('/dashboard/email')
@login_required
def email_dashboard():
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

        # Get ONLY email campaigns with statistics, sorted by name, limit to 20 most recent
        campaigns = list(db.campaigns.find(
            {'campaign_type': 'email'},  # Filter to only email campaigns
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

        # Fetch zipcode engagement data - ONLY for email campaign participants
        zipcode_pipeline = [
            {'$match': {
                'campaign_id': {'$in': list(campaign_id_to_name.keys())},  # Only email campaigns
                'fields.ZIP': {'$exists': True, '$ne': None, '$ne': ''}
            }},
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

    return render_template('dashboards/email.html',
                          title='Email Campaign Dashboard',
                          user=current_user,
                          stats=stats,
                          campaign_data=campaign_data)


@main_bp.route('/dashboard/text')
@login_required
def text_dashboard():
    """
    Text/SMS campaign dashboard with pagination
    """
    try:
        # Initialize campaign data service
        service = CampaignDataService()

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 20

        # Get text campaign stats
        stats = service.get_text_stats()

        # Get total count for pagination
        total_campaigns = service.get_text_campaigns_count()
        total_pages = math.ceil(total_campaigns / per_page) if total_campaigns > 0 else 1

        # Ensure page is within valid range
        page = max(1, min(page, total_pages))

        # Get text campaigns for current page
        campaigns = service.get_text_campaigns(page=page, per_page=per_page)

        # Calculate pagination info
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_campaigns,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }

        logger.info(f"Text dashboard loaded - page {page}/{total_pages}, {len(campaigns)} campaigns")

        return render_template('dashboards/text.html',
                              title='Text Campaign Dashboard',
                              user=current_user,
                              stats=stats,
                              campaigns=campaigns,
                              pagination=pagination)

    except Exception as e:
        logger.error(f"Error loading text dashboard: {str(e)}", exc_info=True)
        # Return empty stats on error
        return render_template('dashboards/text.html',
                              title='Text Campaign Dashboard',
                              user=current_user,
                              stats={'total_campaigns': 0, 'total_sent': 0, 'total_delivered': 0, 'total_clicked': 0},
                              campaigns=[],
                              pagination={'page': 1, 'total_pages': 1, 'has_prev': False, 'has_next': False})


@main_bp.route('/dashboard/mailer')
@login_required
def mailer_dashboard():
    """
    Mailer campaign dashboard (TBD stub)
    """
    return render_template('dashboards/mailer_tbd.html',
                          title='Mailer Campaign Dashboard',
                          user=current_user)


@main_bp.route('/dashboard/letter')
@login_required
def letter_dashboard():
    """
    Letter campaign dashboard (TBD stub)
    """
    return render_template('dashboards/letter_tbd.html',
                          title='Letter Campaign Dashboard',
                          user=current_user)


@main_bp.route('/dashboard/modeling')
@login_required
def modeling_dashboard():
    """
    Bayesian modeling and inference dashboard
    """
    from src.causal_models.model_registry import get_registry

    # Get model registry
    registry = get_registry()

    # Get all available models
    models = registry.get_all_models()

    # Get selected model from query params
    selected_model_id = request.args.get('model', None)
    selected_model = None

    if selected_model_id:
        selected_model = registry.get_model_metadata(selected_model_id)
        if selected_model:
            selected_model = selected_model.to_dict()

    return render_template('dashboards/modeling.html',
                          title='Bayesian Model and Inference Dashboard',
                          user=current_user,
                          models=models,
                          selected_model=selected_model,
                          selected_model_id=selected_model_id)
