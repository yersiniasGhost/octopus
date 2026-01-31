"""
Energy Conservation Client Portal - Flask Application

A single-page demo application for viewing energy profiles and
chatting with an AI energy conservation advisor.
"""
import sys
from pathlib import Path

# Add project root to path for shared utilities
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, request, jsonify
from src.utils.log_manager import LogManager
from client.config import Config
from client.services.mongo_service import MongoService
from client.services.programs import COUNTIES, get_eligible_programs, calculate_savings_estimate

# Initialize logging
logger = LogManager("client-app").get_logger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize services
mongo_service = MongoService()

# ---------------------
# Page Routes
# ---------------------

@app.route('/')
def index():
    """Serve the main single-page application."""
    return render_template('index.html', counties=COUNTIES)


# ---------------------
# API Routes
# ---------------------

@app.route('/api/counties', methods=['GET'])
def get_counties():
    """Return list of available counties."""
    return jsonify({
        'success': True,
        'counties': COUNTIES
    })


@app.route('/api/search', methods=['POST'])
def search_users():
    """Search for users by name with optional filters."""
    data = request.get_json() or {}

    query = data.get('query', '').strip()
    county = data.get('county', COUNTIES[0])
    participants_only = data.get('participants_only', False)

    if len(query) < 2:
        return jsonify({
            'success': False,
            'error': 'Search query must be at least 2 characters',
            'results': []
        })

    if county not in COUNTIES:
        return jsonify({
            'success': False,
            'error': f'Invalid county. Must be one of: {", ".join(COUNTIES)}',
            'results': []
        })

    logger.info(f"Search request: query='{query}', county={county}, participants_only={participants_only}")

    try:
        results = mongo_service.search_users(
            query=query,
            county=county,
            participants_only=participants_only,
            limit=20
        )

        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An error occurred while searching',
            'results': []
        }), 500


@app.route('/api/user/<path:parcel_id>', methods=['GET'])
def get_user_profile(parcel_id):
    """Get complete user profile with energy data and comparables."""
    logger.debug(f"Received profile request - raw parcel_id: '{parcel_id}'")

    county = request.args.get('county', COUNTIES[0])
    logger.debug(f"County from query: '{county}'")

    if county not in COUNTIES:
        return jsonify({
            'success': False,
            'error': f'Invalid county. Must be one of: {", ".join(COUNTIES)}'
        }), 400

    logger.info(f"Profile request: parcel_id={parcel_id}, county={county}")

    try:
        profile = mongo_service.get_user_profile(parcel_id, county)

        if profile:
            return jsonify({
                'success': True,
                'profile': profile
            })
        else:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404

    except Exception as e:
        logger.error(f"Profile error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An error occurred while loading profile'
        }), 500


@app.route('/api/programs', methods=['POST'])
def lookup_programs():
    """Look up eligible energy programs based on income and household size."""
    data = request.get_json() or {}

    annual_income = data.get('annual_income', 0)
    household_size = data.get('household_size', 1)

    try:
        programs = get_eligible_programs(annual_income, household_size)
        return jsonify({
            'success': True,
            'programs': programs
        })
    except Exception as e:
        logger.error(f"Programs lookup error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An error occurred while looking up programs'
        }), 500


@app.route('/api/savings', methods=['POST'])
def calculate_savings():
    """Calculate potential savings for a specific improvement."""
    data = request.get_json() or {}

    improvement_type = data.get('improvement_type')
    annual_energy_cost = data.get('annual_energy_cost', 0)

    if not improvement_type:
        return jsonify({
            'success': False,
            'error': 'improvement_type is required'
        }), 400

    try:
        estimate = calculate_savings_estimate(improvement_type, annual_energy_cost)

        if 'error' in estimate:
            return jsonify({
                'success': False,
                'error': estimate['error']
            }), 400

        return jsonify({
            'success': True,
            'estimate': estimate
        })
    except Exception as e:
        logger.error(f"Savings calculation error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An error occurred while calculating savings'
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat with the AI Energy Conservation Advisor.

    Note: Full AI integration will be added in Phase 3.
    This is a placeholder that returns a simple response.
    """
    data = request.get_json() or {}

    message = data.get('message', '').strip()
    user_context = data.get('user_context', {})
    conversation_history = data.get('conversation_history', [])

    if not message:
        return jsonify({
            'success': False,
            'error': 'Message is required'
        }), 400

    if not user_context.get('parcel_id'):
        return jsonify({
            'success': False,
            'error': 'User context is required'
        }), 400

    logger.info(f"Chat request: parcel_id={user_context.get('parcel_id')}, message='{message[:50]}...'")

    # Phase 1: Return placeholder response
    # Phase 3 will integrate with Claude API via AdvisorService
    response_text = (
        "Thank you for sharing that! I'm analyzing your response to identify "
        "potential energy-saving opportunities.\n\n"
        "**Note:** The AI advisor is being connected in Phase 3 of development. "
        "For now, this is a placeholder response."
    )

    return jsonify({
        'success': True,
        'response': response_text,
        'opportunities_added': [],
        'conversation_history': conversation_history + [
            {'role': 'user', 'content': message},
            {'role': 'assistant', 'content': response_text}
        ]
    })


# ---------------------
# Error Handlers
# ---------------------

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'success': False,
        'error': 'Resource not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


# ---------------------
# Main Entry Point
# ---------------------

if __name__ == '__main__':
    logger.info("Starting Energy Conservation Client Portal")
    app.run(
        host='0.0.0.0',
        port=5001,  # Different port than main app
        debug=Config.DEBUG
    )
