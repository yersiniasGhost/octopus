"""
Campaign routes for EmailOctopus campaign management
"""
from flask import Blueprint, render_template, jsonify, flash, request, send_file
from flask_login import login_required
import logging
import csv
from pathlib import Path

from app.services import EmailOctopusClient
from app.services.emailoctopus_client import (
    EmailOctopusAPIError,
    EmailOctopusAuthenticationError,
    EmailOctopusRateLimitError
)

logger = logging.getLogger(__name__)

campaigns_bp = Blueprint('campaigns', __name__)

# Path to enriched data directory
ENRICHED_DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'enriched'


@campaigns_bp.route('/campaigns')
@login_required
def campaigns_list():
    """
    Display list of EmailOctopus campaigns

    Shows all campaigns with pagination support.
    """
    try:
        # Get page number from query params (default to 1)
        page = request.args.get('page', 1, type=int)

        # Initialize EmailOctopus client
        client = EmailOctopusClient()

        # Test connection first
        if not client.test_connection():
            flash('Unable to connect to EmailOctopus API. Please check your API key.', 'danger')
            return render_template('campaigns/error.html',
                                   error='API connection failed')

        # Fetch campaigns
        result = client.get_campaigns(limit=100, page=page)

        campaigns = result.get('data', [])
        paging = result.get('paging', {})

        logger.info(f"Displaying {len(campaigns)} campaigns on page {page}")

        return render_template('campaigns/list.html',
                               campaigns=campaigns,
                               paging=paging,
                               current_page=page)

    except EmailOctopusAuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        flash('Authentication failed. Please check your EmailOctopus API key in .env', 'danger')
        return render_template('campaigns/error.html',
                               error='Authentication failed')

    except EmailOctopusRateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        flash('API rate limit exceeded. Please try again later.', 'warning')
        return render_template('campaigns/error.html',
                               error='Rate limit exceeded')

    except EmailOctopusAPIError as e:
        logger.error(f"API error: {str(e)}")
        flash(f'API error: {str(e)}', 'danger')
        return render_template('campaigns/error.html',
                               error=str(e))

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        flash('An unexpected error occurred. Please try again.', 'danger')
        return render_template('campaigns/error.html',
                               error='Unexpected error')


@campaigns_bp.route('/campaigns/<campaign_id>')
@login_required
def campaign_detail(campaign_id):
    """
    Display detailed view of a single campaign

    Args:
        campaign_id: UUID of the campaign
    """
    try:
        # Get page number and filter for participant pagination
        page = request.args.get('page', 1, type=int)
        filter_type = request.args.get('filter', 'all', type=str)

        # Initialize EmailOctopus client
        client = EmailOctopusClient()

        # Fetch campaign details
        campaign = client.get_campaign(campaign_id)

        # Fetch campaign reports/statistics
        try:
            reports = client.get_campaign_reports(campaign_id)
            # Debug: log report structure to help troubleshoot
            logger.debug(f"Reports structure: {reports}")
            logger.debug(f"Reports type: {type(reports)}")
            if reports:
                for key, value in reports.items():
                    logger.debug(f"  {key}: {value} (type: {type(value)})")
        except EmailOctopusAPIError:
            # Reports might not be available for all campaigns
            reports = None
            logger.warning(f"Reports not available for campaign {campaign_id}")

        # Fetch campaign participants (contacts) based on filter
        try:
            if filter_type == 'all':
                # Fetch all contacts from campaign list
                participants_result = client.get_campaign_contacts(campaign_id, limit=100, page=page)
                participants_raw = participants_result.get('data', [])
                # Filter by SUBSCRIBED status for 'all' view
                participants = [p for p in participants_raw if p.get('status') == 'SUBSCRIBED']
            elif filter_type == 'subscribed':
                # Fetch all contacts and filter by SUBSCRIBED status
                participants_result = client.get_campaign_contacts(campaign_id, limit=100, page=page)
                participants_raw = participants_result.get('data', [])
                participants = [p for p in participants_raw if p.get('status') == 'SUBSCRIBED']
            elif filter_type in ['opened', 'clicked', 'bounced', 'complained', 'unsubscribed']:
                # Fetch from specific campaign report endpoint
                participants_result = client.get_campaign_report_contacts(campaign_id, filter_type, limit=100, page=page)
                # Extract contact data from report structure
                participants = [item.get('contact', {}) for item in participants_result.get('data', [])]
            else:
                # Invalid filter, default to all subscribed
                participants_result = client.get_campaign_contacts(campaign_id, limit=100, page=page)
                participants_raw = participants_result.get('data', [])
                participants = [p for p in participants_raw if p.get('status') == 'SUBSCRIBED']
                filter_type = 'all'

            participants_paging = participants_result.get('paging', {})
            logger.info(f"Retrieved {len(participants)} participants for campaign {campaign_id} (filter: {filter_type})")
        except EmailOctopusAPIError as e:
            # Participants might not be available
            participants = []
            participants_paging = {}
            logger.warning(f"Participants not available for campaign {campaign_id}: {str(e)}")

        logger.info(f"Displaying details for campaign: {campaign.get('name', 'Unknown')}")

        return render_template('campaigns/detail.html',
                               campaign=campaign,
                               reports=reports,
                               participants=participants,
                               participants_paging=participants_paging,
                               current_page=page,
                               filter_type=filter_type)

    except EmailOctopusAuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        flash('Authentication failed. Please check your EmailOctopus API key.', 'danger')
        return render_template('campaigns/error.html',
                               error='Authentication failed')

    except EmailOctopusAPIError as e:
        logger.error(f"API error: {str(e)}")
        flash(f'Error fetching campaign: {str(e)}', 'danger')
        return render_template('campaigns/error.html',
                               error=str(e))

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        flash('An unexpected error occurred.', 'danger')
        return render_template('campaigns/error.html',
                               error='Unexpected error')


@campaigns_bp.route('/api/campaigns')
@login_required
def api_campaigns_list():
    """
    API endpoint to retrieve campaigns as JSON

    Query params:
        - page: Page number (default 1)
        - limit: Items per page (default 100, max 100)

    Returns:
        JSON response with campaigns data
    """
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 100, type=int)

        # Initialize EmailOctopus client
        client = EmailOctopusClient()

        # Fetch campaigns
        result = client.get_campaigns(limit=limit, page=page)

        return jsonify({
            'success': True,
            'data': result.get('data', []),
            'paging': result.get('paging', {}),
            'count': len(result.get('data', []))
        })

    except EmailOctopusAuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'authentication_failed',
            'message': 'Invalid API key or unauthorized'
        }), 401

    except EmailOctopusRateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'rate_limit_exceeded',
            'message': 'API rate limit exceeded'
        }), 429

    except EmailOctopusAPIError as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'api_error',
            'message': str(e)
        }), 500

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': 'An unexpected error occurred'
        }), 500


@campaigns_bp.route('/api/campaigns/<campaign_id>')
@login_required
def api_campaign_detail(campaign_id):
    """
    API endpoint to retrieve single campaign as JSON

    Args:
        campaign_id: UUID of the campaign

    Returns:
        JSON response with campaign data
    """
    try:
        # Initialize EmailOctopus client
        client = EmailOctopusClient()

        # Fetch campaign
        campaign = client.get_campaign(campaign_id)

        # Try to fetch reports
        reports = None
        try:
            reports = client.get_campaign_reports(campaign_id)
        except EmailOctopusAPIError:
            pass

        return jsonify({
            'success': True,
            'data': campaign,
            'reports': reports
        })

    except EmailOctopusAuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'authentication_failed',
            'message': 'Invalid API key or unauthorized'
        }), 401

    except EmailOctopusAPIError as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'api_error',
            'message': str(e)
        }), 500

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': 'An unexpected error occurred'
        }), 500


@campaigns_bp.route('/api/test-connection')
@login_required
def api_test_connection():
    """
    API endpoint to test EmailOctopus connection

    Returns:
        JSON response with connection status
    """
    try:
        client = EmailOctopusClient()
        is_connected = client.test_connection()

        return jsonify({
            'success': True,
            'connected': is_connected
        })

    except EmailOctopusAuthenticationError as e:
        return jsonify({
            'success': False,
            'connected': False,
            'error': 'authentication_failed',
            'message': str(e)
        }), 401

    except Exception as e:
        logger.error(f"Connection test error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'connected': False,
            'error': 'connection_failed',
            'message': str(e)
        }), 500


@campaigns_bp.route('/api/campaigns/<campaign_id>/enriched-data')
@login_required
def api_enriched_data(campaign_id):
    """
    API endpoint to retrieve enriched campaign data from CSV

    Args:
        campaign_id: UUID of the campaign

    Returns:
        JSON response with enriched data table
    """
    try:
        # Find enriched CSV file for this campaign
        enriched_file = None
        if ENRICHED_DATA_DIR.exists():
            for file in ENRICHED_DATA_DIR.glob(f'enriched_campaign_{campaign_id}_*.csv'):
                enriched_file = file
                break

        if not enriched_file or not enriched_file.exists():
            return jsonify({
                'success': False,
                'error': 'not_found',
                'message': 'Enriched data file not found for this campaign'
            }), 404

        # Read CSV file
        data = []
        with open(enriched_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            for row in reader:
                data.append(row)

        logger.info(f"Loaded {len(data)} rows from enriched data for campaign {campaign_id}")

        return jsonify({
            'success': True,
            'columns': columns,
            'data': data,
            'row_count': len(data),
            'filename': enriched_file.name
        })

    except Exception as e:
        logger.error(f"Error loading enriched data: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': f'Error loading enriched data: {str(e)}'
        }), 500


@campaigns_bp.route('/campaigns/<campaign_id>/download-enriched')
@login_required
def download_enriched(campaign_id):
    """
    Download enriched CSV file for a campaign

    Args:
        campaign_id: UUID of the campaign

    Returns:
        CSV file download
    """
    try:
        # Find enriched CSV file for this campaign
        enriched_file = None
        if ENRICHED_DATA_DIR.exists():
            for file in ENRICHED_DATA_DIR.glob(f'enriched_campaign_{campaign_id}_*.csv'):
                enriched_file = file
                break

        if not enriched_file or not enriched_file.exists():
            flash('Enriched data file not found for this campaign', 'warning')
            return render_template('campaigns/error.html',
                                 error='File not found'), 404

        logger.info(f"Downloading enriched data: {enriched_file.name}")

        return send_file(
            enriched_file,
            mimetype='text/csv',
            as_attachment=True,
            download_name=enriched_file.name
        )

    except Exception as e:
        logger.error(f"Error downloading enriched data: {str(e)}", exc_info=True)
        flash(f'Error downloading file: {str(e)}', 'danger')
        return render_template('campaigns/error.html',
                             error='Download failed'), 500


@campaigns_bp.route('/api/campaigns/<campaign_id>/savings-histogram')
@login_required
def api_savings_histogram(campaign_id):
    """
    API endpoint to generate histogram data for savings ranges

    Args:
        campaign_id: UUID of the campaign

    Returns:
        JSON response with histogram data (ranges, counts, opened counts)
    """
    try:
        # Find enriched CSV file for this campaign
        enriched_file = None
        if ENRICHED_DATA_DIR.exists():
            for file in ENRICHED_DATA_DIR.glob(f'enriched_campaign_{campaign_id}_*.csv'):
                enriched_file = file
                break

        if not enriched_file or not enriched_file.exists():
            return jsonify({
                'success': False,
                'error': 'not_found',
                'message': 'Enriched data file not found for this campaign'
            }), 404

        # Read CSV and extract savings and opened data
        savings_data = []
        with open(enriched_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Try different possible column names for savings
                savings_str = (row.get('annual_savings') or
                             row.get('AnnualSavings') or
                             row.get('annual_saving') or
                             row.get('monthly_saving') or
                             row.get('monthly_savings') or
                             row.get('MonthlySaving') or '0')

                opened = int(row.get('opened', 0))

                # Clean and parse savings value
                try:
                    # Remove currency symbols, commas, and whitespace
                    savings_clean = savings_str.replace('$', '').replace(',', '').strip()
                    if savings_clean:
                        savings = float(savings_clean)
                        savings_data.append({
                            'savings': savings,
                            'opened': opened
                        })
                except (ValueError, AttributeError):
                    continue

        if not savings_data:
            return jsonify({
                'success': False,
                'error': 'no_data',
                'message': 'No valid savings data found'
            }), 404

        # Calculate histogram bins
        all_savings = [d['savings'] for d in savings_data]
        min_savings = min(all_savings)
        max_savings = max(all_savings)

        # Create 10 bins
        num_bins = 10
        bin_width = (max_savings - min_savings) / num_bins if max_savings > min_savings else 1

        # Initialize bins
        bins = []
        for i in range(num_bins):
            bin_start = min_savings + (i * bin_width)
            bin_end = bin_start + bin_width
            bins.append({
                'range_start': round(bin_start, 2),
                'range_end': round(bin_end, 2),
                'range_label': f'${round(bin_start)}-${round(bin_end)}',
                'total_count': 0,
                'opened_count': 0
            })

        # Populate bins
        for data_point in savings_data:
            savings = data_point['savings']
            opened = data_point['opened']

            # Find appropriate bin
            bin_index = min(int((savings - min_savings) / bin_width), num_bins - 1)
            bins[bin_index]['total_count'] += 1
            if opened == 1:
                bins[bin_index]['opened_count'] += 1

        logger.info(f"Generated histogram with {num_bins} bins for campaign {campaign_id}")

        return jsonify({
            'success': True,
            'bins': bins,
            'total_participants': len(savings_data),
            'min_savings': round(min_savings, 2),
            'max_savings': round(max_savings, 2)
        })

    except Exception as e:
        logger.error(f"Error generating histogram data: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': f'Error generating histogram: {str(e)}'
        }), 500
