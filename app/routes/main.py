"""Main application routes"""
from flask import Blueprint, render_template, request, jsonify, send_from_directory
from flask_login import login_required, current_user
from pymongo import MongoClient
from pathlib import Path
import math

from app.services import EmailOctopusClient
from app.services.emailoctopus_client import EmailOctopusAPIError
from app.services.campaign_data_service import CampaignDataService
from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

main_bp = Blueprint('main', __name__)

# Project root for serving inference model artifacts
PROJECT_ROOT = Path(__file__).parent.parent.parent


@main_bp.route('/static/inference/<path:filepath>')
def serve_inference_files(filepath):
    """
    Serve static files from data/inference directory.
    Used for model artifacts (DAG images, trace plots, etc.)
    """
    inference_dir = PROJECT_ROOT / 'data' / 'inference'
    return send_from_directory(inference_dir, filepath)


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
        db_name = env.get_env('MONGODB_OCTOPUS') or env.get_env('MONGODB_DATABASE') or 'empower_development'
        client = MongoClient(mongo_uri)
        db = client[db_name]

        # Filter to email-channel campaigns. Unified docs use either
        # `channel` or `campaign_type` inconsistently across import sources.
        campaigns = list(db.campaigns.find(
            {'$or': [{'channel': 'email'}, {'campaign_type': 'email'}]},
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


@main_bp.route('/dashboard/applicants')
@login_required
def applicants_dashboard():
    """Applicant visualization dashboard — Overview / Demographics / Attribution tabs."""
    empty_data = {
        'overview': {
            'kpis': {'total_applicants': 0, 'this_month': 0, 'match_rate_pct': 0.0,
                     'top_county': None, 'top_channel': None},
            'time_series': {'labels': [], 'counts': []},
            'match_quality': {'labels': [], 'counts': []},
            'recent_applicants': [],
        },
        'demographics': {
            'age': {'labels': [], 'counts': [], 'n': 0},
            'income': {'labels': [], 'counts': [], 'n': 0},
            'household_size': {'labels': [], 'counts': [], 'n': 0},
            'energy_burden': {'labels': [], 'counts': [], 'n': 0, 'total': 0},
            'income_age_scatter': {'series': []},
        },
        'attribution': {
            'utm_medium': {'labels': [], 'counts': []},
            'utm_source': {'labels': [], 'counts': []},
            'utm_campaign': {'labels': [], 'counts': []},
            'channel_conversion': [],
        },
    }
    try:
        service = CampaignDataService()
        data = service.get_applicant_dashboard_data()
        # Backfill any missing tab with empty defaults so the template never KeyErrors.
        # The orchestrator sets failed tabs to {} (per-builder isolation), which is falsy.
        for tab, default in empty_data.items():
            if not data.get(tab):
                data[tab] = default
        logger.info(f"Applicants dashboard loaded — {data['overview']['kpis']}")
        return render_template('dashboards/applicants.html',
                              title='Applicant Dashboard',
                              user=current_user,
                              data=data)
    except Exception as e:
        logger.error(f"Error loading applicants dashboard: {str(e)}", exc_info=True)
        return render_template('dashboards/applicants.html',
                              title='Applicant Dashboard',
                              user=current_user,
                              data=empty_data)


@main_bp.route('/inference-models')
@login_required
def inference_models():
    """
    Inference models page - ML models for campaign optimization

    Displays registered Bayesian models with:
    - Model selector dropdown
    - DAG visualization
    - Model fit results
    - Effectiveness metrics
    - Inference interface
    """
    from src.bayesian_models.model_registry import get_registry
    from pathlib import Path
    import json

    registry = get_registry()
    models = registry.get_all_models()

    # Get selected model from query params
    selected_model_id = request.args.get('model', None)
    selected_model = None
    model_status = None
    model_config = None
    dag_image = None
    dag_text = None
    fit_results = None
    effectiveness = None
    trace_plots = []

    # Validation data
    validation_data = None
    validation_plots = {}

    # Data ingestion summary
    data_summary = None

    if selected_model_id:
        metadata = registry.get_model_metadata(selected_model_id)
        if metadata:
            selected_model = metadata.to_dict()
            model_status = registry.get_model_status(selected_model_id)

            # Try to load additional model config
            model_dir = registry.models_dir / selected_model_id
            config_path = model_dir / 'config.yaml'
            if config_path.exists():
                import yaml
                with open(config_path, 'r') as f:
                    model_config = yaml.safe_load(f)

            # Get output directory from registry (data/inference/{model_id})
            from src.bayesian_models.base_model import MODELS_OUTPUT_DIR
            model_output_dir = MODELS_OUTPUT_DIR / selected_model_id

            # Check for DAG image in diagrams folder
            diagrams_dir = model_output_dir / 'diagrams'
            if diagrams_dir.exists():
                dag_files = list(diagrams_dir.glob('dag*.png')) + list(diagrams_dir.glob('dag*.svg'))
                if dag_files:
                    # Serve from static route that maps to data/inference
                    dag_image = f'/static/inference/{selected_model_id}/diagrams/{dag_files[0].name}'

            # Generate text-based DAG representation if no image
            if not dag_image and model_config:
                # Check for model_structure in config
                model_structure = model_config.get('model_structure', {})
                if model_structure:
                    priors = model_structure.get('priors', [])
                    likelihood = model_structure.get('likelihood', {})
                    linear_model = model_structure.get('linear_model', '')

                    dag_lines = ["<strong>Model Structure:</strong>"]
                    if priors:
                        dag_lines.append("<br><strong>Priors:</strong>")
                        for p in priors:
                            dag_lines.append(f"&nbsp;&nbsp;{p['name']} ~ {p['distribution']}")
                    if linear_model:
                        dag_lines.append(f"<br><strong>Linear Model:</strong><br>&nbsp;&nbsp;{linear_model}")
                    if likelihood:
                        dag_lines.append(f"<br><strong>Likelihood:</strong><br>&nbsp;&nbsp;{likelihood['name']} ~ {likelihood['distribution']}")
                    dag_text = "".join(dag_lines)
                else:
                    # Fallback to predictors if available
                    predictors = model_config.get('predictors', [])
                    outcome = model_config.get('outcome', 'y')
                    if predictors:
                        dag_lines = [f"<strong>Outcome:</strong> {outcome}", "<strong>Predictors:</strong>"]
                        for p in predictors:
                            dag_lines.append(f"  - {p}")
                        dag_text = "<br>".join(dag_lines)

            # Load fit results if available
            reports_dir = model_output_dir / 'reports'
            if reports_dir.exists():
                # Look for the most recent results file
                result_files = sorted(reports_dir.glob('results_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                if result_files:
                    with open(result_files[0], 'r') as f:
                        fit_results = json.load(f)
                else:
                    # Fallback to fit_summary.json
                    fit_file = reports_dir / 'fit_summary.json'
                    if fit_file.exists():
                        with open(fit_file, 'r') as f:
                            fit_results = json.load(f)

                eff_file = reports_dir / 'effectiveness.json'
                if eff_file.exists():
                    with open(eff_file, 'r') as f:
                        effectiveness = json.load(f)

            # Load trace plots
            if diagrams_dir.exists():
                for plot_file in diagrams_dir.glob('trace*.png'):
                    trace_plots.append(f'/static/inference/{selected_model_id}/diagrams/{plot_file.name}')

            # Load validation report if available
            if reports_dir.exists():
                validation_files = sorted(reports_dir.glob('validation_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                if validation_files:
                    with open(validation_files[0], 'r') as f:
                        validation_data = json.load(f)

            # Load validation plots if available
            validation_dir = diagrams_dir / 'validation'
            if validation_dir.exists():
                plot_names = ['treatment_effects', 'e_values', 'forest', 'ppc', 'trace']
                for plot_name in plot_names:
                    plot_file = validation_dir / f'{plot_name}.png'
                    if plot_file.exists():
                        validation_plots[plot_name] = f'/static/inference/{selected_model_id}/diagrams/validation/{plot_name}.png'

            # Load data ingestion summary if available
            from src.bayesian_models.data_summary import load_data_summary_for_model
            try:
                summary = load_data_summary_for_model(selected_model_id)
                if summary:
                    data_summary = summary.to_dict()
            except Exception as e:
                logger.warning(f"Could not load data summary for {selected_model_id}: {e}")

            # Load dynamic options for select fields (e.g., campaign_id)
            if model_status and model_status.get('is_trained'):
                try:
                    model_instance = registry.load_model_instance(selected_model_id)
                    if model_instance and hasattr(model_instance, 'get_dynamic_options'):
                        dynamic_options = model_instance.get_dynamic_options()
                        # Merge dynamic options into inference_params
                        if dynamic_options and 'inference_params' in selected_model:
                            for param in selected_model['inference_params']:
                                param_name = param.get('name')
                                if param_name in dynamic_options:
                                    param['options'] = dynamic_options[param_name]
                except Exception as e:
                    logger.warning(f"Could not load dynamic options for {selected_model_id}: {e}")

    return render_template('inference_models.html',
                          title='Inference Models',
                          user=current_user,
                          models=models,
                          selected_model=selected_model,
                          model_status=model_status,
                          model_config=model_config,
                          dag_image=dag_image,
                          dag_text=dag_text,
                          fit_results=fit_results,
                          effectiveness=effectiveness,
                          trace_plots=trace_plots,
                          validation_data=validation_data,
                          validation_plots=validation_plots,
                          data_summary=data_summary)


@main_bp.route('/inference-models/<model_id>/run', methods=['POST'])
@login_required
def run_inference(model_id):
    """
    Run inference with a trained model

    Accepts form data with inference parameters,
    returns JSON with prediction results.
    """
    from src.bayesian_models.model_registry import get_registry

    registry = get_registry()
    model_status = registry.get_model_status(model_id)

    if not model_status or not model_status.get('is_trained'):
        return jsonify({'success': False, 'error': 'Model is not trained'})

    try:
        # Load the model instance
        model_instance = registry.load_model_instance(model_id)
        if not model_instance:
            return jsonify({'success': False, 'error': 'Could not load model'})

        # Get inference parameters from form
        # Handle multiselect params (multiple values for same key)
        inference_params = {}
        multiselect_params = set()

        # Identify multiselect parameters from model metadata
        metadata = registry.get_model_metadata(model_id)
        if metadata:
            for param in metadata.inference_params:
                if param.param_type == 'multiselect':
                    multiselect_params.add(param.name)

        # Process form values
        for key in request.form.keys():
            if key in multiselect_params:
                # Get all values for multiselect fields as list
                inference_params[key] = request.form.getlist(key)
            else:
                inference_params[key] = request.form.get(key)

        # Validate parameters
        is_valid, error = model_instance.validate_inference_params(inference_params)
        if not is_valid:
            return jsonify({'success': False, 'error': error})

        # Run inference
        results = model_instance.predict(inference_params)

        return jsonify({'success': True, 'results': results})

    except Exception as e:
        logger.error(f"Error running inference for {model_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})


@main_bp.route('/inference-models/<model_id>/validate', methods=['POST'])
@login_required
def run_validation(model_id):
    """
    Run validation on a trained model.

    Returns JSON with validation report and optional base64-encoded plots.
    """
    from src.bayesian_models.model_registry import get_registry
    from src.bayesian_models.validation import ModelValidator
    import arviz as az
    import json

    registry = get_registry()
    model_status = registry.get_model_status(model_id)

    if not model_status or not model_status.get('is_trained'):
        return jsonify({'success': False, 'error': 'Model is not trained'})

    try:
        # Load the model instance
        model_instance = registry.load_model_instance(model_id)
        if not model_instance:
            return jsonify({'success': False, 'error': 'Could not load model'})

        # Get latest trace
        latest_trace = model_instance.get_latest_trace()
        if not latest_trace:
            return jsonify({'success': False, 'error': 'No trained model trace found'})

        trace = az.from_netcdf(latest_trace)

        # Load treatment effects if available
        treatment_effects = None
        if model_instance.reports_dir.exists():
            results_files = sorted(model_instance.reports_dir.glob('results_*.json'))
            if results_files:
                with open(results_files[-1], 'r') as f:
                    results = json.load(f)
                    treatment_effects = results.get('treatment_effects')

        # Create validator and run
        validator = ModelValidator(
            trace,
            model_name=model_instance.metadata.name,
            treatment_effects=treatment_effects
        )

        # Check if plots are requested
        include_plots = request.form.get('include_plots', 'false').lower() == 'true'
        skip_loo = request.form.get('skip_loo', 'false').lower() == 'true'

        report = validator.full_validation(include_loo=not skip_loo)

        # Generate plots if requested
        plots = {}
        if include_plots:
            output_dir = model_instance.diagrams_dir / 'validation'
            plots = validator.generate_all_plots(output_dir, return_base64=True)

        # Save validation report
        from datetime import datetime
        report_path = model_instance.reports_dir / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        validator.save_report(report_path)

        return jsonify({
            'success': True,
            'report': report,
            'plots': plots,
            'report_path': str(report_path)
        })

    except Exception as e:
        logger.error(f"Error running validation for {model_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})


@main_bp.route('/dashboard/modeling')
@login_required
def modeling_dashboard():
    """
    Bayesian modeling and inference dashboard
    """
    from src.bayesian_models.model_registry import get_registry

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


@main_bp.route('/analysis')
@login_required
def analysis():
    """
    Analysis page - tools for creating participant lists based on selection criteria.

    Provides functionality to:
    - Filter participants by county, demographics, engagement metrics
    - Create targeted lists for campaigns
    - Export filtered participant data
    """
    return render_template('analysis.html',
                          title='Participant Analysis',
                          user=current_user)
