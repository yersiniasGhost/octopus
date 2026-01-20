"""
Explore Routes - Natural Language MongoDB Query Interface

Provides a conversational interface for exploring campaign and demographic data
using Claude AI to interpret queries and execute MongoDB operations.
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

explore_bp = Blueprint('explore', __name__)


@explore_bp.route('/explore')
@login_required
def explore():
    """
    Explore page - Natural language database query interface.

    Features:
    - Text input for natural language queries
    - Claude AI interprets and executes MongoDB queries
    - Results displayed as tables with pagination
    - Natural language response summarizing findings
    """
    from app.services.explore_service import ExploreService

    try:
        service = ExploreService()
        stats = service.get_collection_stats()
        counties = service.get_available_counties()

        logger.info(f"Explore page loaded by user {current_user.username}")

        return render_template(
            'explore.html',
            title='Explore Data',
            user=current_user,
            stats=stats,
            counties=counties
        )

    except Exception as e:
        logger.error(f"Error loading explore page: {str(e)}", exc_info=True)
        return render_template(
            'explore.html',
            title='Explore Data',
            user=current_user,
            stats={},
            counties=[],
            error=str(e)
        )


@explore_bp.route('/api/explore/query', methods=['POST'])
@login_required
def explore_query():
    """
    API endpoint for natural language queries.

    Request JSON:
        {
            "query": "Natural language query string",
            "method": "tools" | "python" (optional, defaults to "tools")
        }

    Response JSON:
        {
            "success": bool,
            "interpretation": "How Claude interpreted the query",
            "summary": "Natural language summary of results",
            "results": [
                {
                    "collection": "collection_name",
                    "count": 10,
                    "data": [...]
                }
            ],
            "metadata": {
                "query": "original query",
                "timestamp": "ISO timestamp",
                "total_records": 100,
                "method": "tools" | "python"
            }
        }
    """
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'query' in request body"
            }), 400

        query = data['query'].strip()
        if not query:
            return jsonify({
                "success": False,
                "error": "Query cannot be empty"
            }), 400

        if len(query) > 1000:
            return jsonify({
                "success": False,
                "error": "Query too long (max 1000 characters)"
            }), 400

        # Get the method - default to "tools" for the original service
        method = data.get('method', 'tools').lower()

        logger.info(f"Explore query from {current_user.username} [method={method}]: {query[:100]}...")

        if method == 'python':
            # Use the new Python script execution service
            from app.services.claude_service import ClaudeService
            service = ClaudeService()
        else:
            # Use the original tool-based service
            from app.services.explore_service import ExploreService
            service = ExploreService()

        result = service.explore(query)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Explore query error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "summary": "An unexpected error occurred while processing your query."
        }), 500


@explore_bp.route('/api/explore/stats')
@login_required
def explore_stats():
    """Get collection statistics for the explore page."""
    from app.services.explore_service import ExploreService

    try:
        service = ExploreService()
        stats = service.get_collection_stats()
        counties = service.get_available_counties()

        return jsonify({
            "success": True,
            "stats": stats,
            "counties": counties
        })

    except Exception as e:
        logger.error(f"Stats error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
