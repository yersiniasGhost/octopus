"""
County Analysis Routes - County-level data visualization and analysis

Provides visualization tools for analyzing demographic, income, and other
data at the county level with histograms, pie charts, and other metrics.
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from pymongo import MongoClient
from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

county_analysis_bp = Blueprint('county_analysis', __name__)


def get_mongo_client():
    """Get MongoDB client connection."""
    env = EnvVars()
    mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')
    return MongoClient(mongo_uri)


def get_available_counties():
    """Get list of available counties from demographic collections."""
    client = get_mongo_client()
    db = client['empower_development']
    collections = db.list_collection_names()

    counties = set()
    for name in collections:
        if name.endswith('CountyDemographic'):
            county = name.replace('CountyDemographic', '')
            counties.add(county)

    client.close()
    return sorted(list(counties))


@county_analysis_bp.route('/county-analysis')
@login_required
def county_analysis():
    """
    County Analysis page - visualize county-level data.

    Features:
    - County selector dropdown
    - Income distribution histogram
    - Income level pie chart
    - Extensible for additional analysis tools
    """
    try:
        counties = get_available_counties()

        logger.info(f"County Analysis page loaded by user {current_user.username}")

        return render_template(
            'county_analysis.html',
            title='County Analysis',
            user=current_user,
            counties=counties
        )

    except Exception as e:
        logger.error(f"Error loading county analysis page: {str(e)}", exc_info=True)
        return render_template(
            'county_analysis.html',
            title='County Analysis',
            user=current_user,
            counties=[],
            error=str(e)
        )


# Income bracket definitions (in dollars)
INCOME_BRACKETS = [
    (0, 15000, "$0-15k"),
    (15000, 25000, "$15k-25k"),
    (25000, 35000, "$25k-35k"),
    (35000, 50000, "$35k-50k"),
    (50000, 75000, "$50k-75k"),
    (75000, 100000, "$75k-100k"),
    (100000, 150000, "$100k-150k"),
    (150000, float('inf'), "$150k+"),
]


@county_analysis_bp.route('/api/county-analysis/income-distribution', methods=['POST'])
@login_required
def get_income_distribution():
    """
    API endpoint to get income distribution data for a county.

    Request JSON:
        {
            "county": "Franklin"  # County name without 'County' suffix
        }

    Response JSON:
        {
            "success": bool,
            "county": "Franklin",
            "histogram": {
                "labels": ["$0-15k", "$15k-25k", ...],
                "counts": [100, 200, 150, ...],
                "brackets": [[0, 15000], [15000, 25000], ...]
            },
            "total_records": 12345,
            "statistics": {
                "mean_income": 45000,
                "median_income": 42500,
                "min_income": 7500,
                "max_income": 175000
            }
        }
    """
    try:
        data = request.get_json()
        if not data or 'county' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'county' in request body"
            }), 400

        county = data['county'].strip()
        if not county:
            return jsonify({
                "success": False,
                "error": "County cannot be empty"
            }), 400

        logger.info(f"Income distribution query for county: {county} by user {current_user.username}")

        # Build collection name
        collection_name = f"{county}CountyDemographic"

        client = get_mongo_client()
        db = client['empower_development']

        # Check if collection exists
        if collection_name not in db.list_collection_names():
            client.close()
            return jsonify({
                "success": False,
                "error": f"Collection '{collection_name}' not found"
            }), 404

        collection = db[collection_name]

        # Count records in each income bracket
        labels = []
        counts = []
        brackets = []

        for low, high, label in INCOME_BRACKETS:
            if high == float('inf'):
                count = collection.count_documents({"estimated_income": {"$gte": low}})
            else:
                count = collection.count_documents({
                    "estimated_income": {"$gte": low, "$lt": high}
                })
            labels.append(label)
            counts.append(count)
            brackets.append([low, high if high != float('inf') else None])

        total_records = sum(counts)

        # Check if we have any valid income data
        if total_records == 0:
            total_in_collection = collection.count_documents({})
            missing_count = collection.count_documents({
                "$or": [
                    {"estimated_income": {"$exists": False}},
                    {"estimated_income": {"$lte": 0}}
                ]
            })

            client.close()

            return jsonify({
                "success": True,
                "county": county,
                "histogram": {"labels": labels, "counts": counts, "brackets": brackets},
                "total_records": 0,
                "total_in_collection": total_in_collection,
                "statistics": {},
                "data_status": "unavailable",
                "message": f"No valid estimated_income data for {county} County. {missing_count:,} records without income data."
            })

        # Calculate statistics using aggregation
        stats_pipeline = [
            {"$match": {"estimated_income": {"$gt": 0}}},
            {"$group": {
                "_id": None,
                "mean_income": {"$avg": "$estimated_income"},
                "min_income": {"$min": "$estimated_income"},
                "max_income": {"$max": "$estimated_income"}
            }}
        ]
        stats_result = list(collection.aggregate(stats_pipeline))

        # Get median (approximate via sorting)
        median_pipeline = [
            {"$match": {"estimated_income": {"$gt": 0}}},
            {"$sort": {"estimated_income": 1}},
            {"$skip": total_records // 2},
            {"$limit": 1},
            {"$project": {"estimated_income": 1}}
        ]
        median_result = list(collection.aggregate(median_pipeline))

        statistics = {}
        if stats_result:
            statistics["mean_income"] = round(stats_result[0]["mean_income"], 0)
            statistics["min_income"] = stats_result[0]["min_income"]
            statistics["max_income"] = stats_result[0]["max_income"]
        if median_result:
            statistics["median_income"] = median_result[0]["estimated_income"]

        client.close()

        return jsonify({
            "success": True,
            "county": county,
            "histogram": {
                "labels": labels,
                "counts": counts,
                "brackets": brackets
            },
            "total_records": total_records,
            "statistics": statistics
        })

    except Exception as e:
        logger.error(f"Income distribution error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@county_analysis_bp.route('/api/county-analysis/energy-burden-by-income', methods=['POST'])
@login_required
def get_energy_burden_by_income():
    """
    API endpoint to get energy burden distribution for a specific income bracket or all brackets.

    Request JSON:
        {
            "county": "Franklin",
            "bracket_index": 3  # Index into INCOME_BRACKETS (0-7), or "all" for all brackets
        }

    Response JSON:
        {
            "success": bool,
            "county": "Franklin",
            "income_bracket": "$35k-50k" or "All Brackets",
            "bracket_range": [35000, 50000] or null,
            "histogram": {
                "labels": ["0-2%", "2-4%", ...],
                "counts": [100, 200, ...]
            },
            "total_records": 1234,
            "statistics": {
                "mean_burden": 5.65,
                "median_burden": 4.55,
                "min_burden": 0.5,
                "max_burden": 25.0
            }
        }
    """
    try:
        data = request.get_json()
        if not data or 'county' not in data or 'bracket_index' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'county' or 'bracket_index' in request body"
            }), 400

        county = data['county'].strip()
        bracket_index_raw = data['bracket_index']

        # Check if requesting all brackets
        is_all_brackets = bracket_index_raw == "all" or bracket_index_raw is None

        if not is_all_brackets:
            bracket_index = int(bracket_index_raw)
            if not (0 <= bracket_index < len(INCOME_BRACKETS)):
                return jsonify({
                    "success": False,
                    "error": f"bracket_index must be between 0 and {len(INCOME_BRACKETS) - 1}, or 'all'"
                }), 400
            # Get bracket info
            low, high, bracket_label = INCOME_BRACKETS[bracket_index]
            bracket_range = [low, high if high != float('inf') else None]
        else:
            bracket_label = "All Brackets"
            bracket_range = None

        logger.info(f"Energy burden query for {county}, bracket {bracket_label} by {current_user.username}")

        collection_name = f"{county}CountyDemographic"

        client = get_mongo_client()
        db = client['empower_development']

        if collection_name not in db.list_collection_names():
            client.close()
            return jsonify({
                "success": False,
                "error": f"Collection '{collection_name}' not found"
            }), 404

        collection = db[collection_name]

        # Build filter based on bracket or all
        if is_all_brackets:
            # All brackets: only require valid income and energy burden
            match_filter = {
                "estimated_income": {"$gt": 0},
                "energy_burden_kwh": {"$gt": 0, "$lt": 100}
            }
        else:
            # Specific bracket: filter by income range
            if high == float('inf'):
                income_filter = {"estimated_income": {"$gte": low}}
            else:
                income_filter = {"estimated_income": {"$gte": low, "$lt": high}}

            match_filter = {
                **income_filter,
                "energy_burden_kwh": {"$gt": 0, "$lt": 100}
            }

        # Get all energy burden values for statistics
        cursor = collection.find(match_filter, {"energy_burden_kwh": 1})
        burden_values = [doc['energy_burden_kwh'] for doc in cursor]

        if not burden_values:
            client.close()
            return jsonify({
                "success": True,
                "county": county,
                "income_bracket": bracket_label,
                "bracket_range": bracket_range,
                "histogram": {"labels": [], "counts": []},
                "total_records": 0,
                "statistics": {},
                "message": f"No records found for {bracket_label}"
            })

        # Create histogram bins (0-2%, 2-4%, 4-6%, etc. up to 20%+)
        bin_edges = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 100]
        bin_labels = ["0-2%", "2-4%", "4-6%", "6-8%", "8-10%", "10-12%", "12-14%", "14-16%", "16-18%", "18-20%", "20%+"]

        # Count values in each bin
        bin_counts = [0] * len(bin_labels)
        for burden in burden_values:
            for i in range(len(bin_edges) - 1):
                if bin_edges[i] <= burden < bin_edges[i + 1]:
                    bin_counts[i] += 1
                    break

        # Calculate statistics (values are already percentages)
        mean_burden = sum(burden_values) / len(burden_values)
        sorted_values = sorted(burden_values)
        median_burden = sorted_values[len(sorted_values) // 2]
        min_burden = min(burden_values)
        max_burden = max(burden_values)

        client.close()

        return jsonify({
            "success": True,
            "county": county,
            "income_bracket": bracket_label,
            "bracket_range": bracket_range,
            "histogram": {
                "labels": bin_labels,
                "counts": bin_counts
            },
            "total_records": len(burden_values),
            "statistics": {
                "mean_burden": round(mean_burden, 2),
                "median_burden": round(median_burden, 2),
                "min_burden": round(min_burden, 2),
                "max_burden": round(max_burden, 2)
            }
        })

    except Exception as e:
        logger.error(f"Energy burden error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@county_analysis_bp.route('/api/county-analysis/percentile-distribution-by-income', methods=['POST'])
@login_required
def get_percentile_distribution_by_income():
    """
    API endpoint to get energy percentile distribution for a specific income bracket.

    Percentile is based on energy consumption compared to comparable homes
    (similar sqft, age, stories). Higher percentile = higher consumption.

    Request JSON:
        {
            "county": "Franklin",
            "bracket_index": 3  # Index into INCOME_BRACKETS (0-7), or "all"
        }

    Response JSON:
        {
            "success": bool,
            "county": "Franklin",
            "income_bracket": "$35k-50k",
            "histogram": {
                "labels": ["0-10%", "10-20%", ...],
                "counts": [100, 200, ...]
            },
            "total_records": 1234,
            "statistics": {
                "mean_percentile": 52.3,
                "median_percentile": 50.0,
                "min_percentile": 2.5,
                "max_percentile": 98.7
            }
        }
    """
    try:
        data = request.get_json()
        if not data or 'county' not in data or 'bracket_index' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'county' or 'bracket_index' in request body"
            }), 400

        county = data['county'].strip()
        bracket_index_raw = data['bracket_index']

        # Check if requesting all brackets
        is_all_brackets = bracket_index_raw == "all" or bracket_index_raw is None

        if not is_all_brackets:
            bracket_index = int(bracket_index_raw)
            if not (0 <= bracket_index < len(INCOME_BRACKETS)):
                return jsonify({
                    "success": False,
                    "error": f"bracket_index must be between 0 and {len(INCOME_BRACKETS) - 1}, or 'all'"
                }), 400
            low, high, bracket_label = INCOME_BRACKETS[bracket_index]
        else:
            bracket_label = "All Brackets"
            low, high = 0, float('inf')

        logger.info(f"Percentile distribution query for {county}, bracket {bracket_label} by {current_user.username}")

        # Collection names
        demographic_coll = f"{county}CountyDemographic"
        residential_coll = f"{county}CountyResidential"

        client = get_mongo_client()
        db = client['empower_development']

        # Verify collections exist
        collections = db.list_collection_names()
        if demographic_coll not in collections or residential_coll not in collections:
            client.close()
            return jsonify({
                "success": False,
                "error": f"Required collection(s) not found for {county} County"
            }), 404

        # Step 1: Get parcel_ids from Demographic that match the income bracket
        if is_all_brackets:
            income_filter = {"estimated_income": {"$gt": 0}}
        elif high == float('inf'):
            income_filter = {"estimated_income": {"$gte": low}}
        else:
            income_filter = {"estimated_income": {"$gte": low, "$lt": high}}

        # Get matching parcel_ids from demographic collection
        demo_cursor = db[demographic_coll].find(income_filter, {"parcel_id": 1})
        matching_parcel_ids = [doc['parcel_id'] for doc in demo_cursor]

        if not matching_parcel_ids:
            client.close()
            return jsonify({
                "success": True,
                "county": county,
                "income_bracket": bracket_label,
                "histogram": {"labels": [], "counts": []},
                "total_records": 0,
                "statistics": {},
                "message": f"No records found for {bracket_label}"
            })

        # Step 2: Get percentile values from Residential for those parcel_ids
        res_cursor = db[residential_coll].find(
            {
                "parcel_id": {"$in": matching_parcel_ids},
                "energy_percentile.percentile_rank": {"$exists": True, "$ne": None}
            },
            {"energy_percentile.percentile_rank": 1}
        )

        percentile_values = [
            doc['energy_percentile']['percentile_rank']
            for doc in res_cursor
            if doc.get('energy_percentile', {}).get('percentile_rank') is not None
        ]

        if not percentile_values:
            client.close()
            return jsonify({
                "success": True,
                "county": county,
                "income_bracket": bracket_label,
                "histogram": {"labels": [], "counts": []},
                "total_records": 0,
                "total_in_bracket": len(matching_parcel_ids),
                "statistics": {},
                "data_status": "pending",
                "message": f"Energy percentiles not yet calculated for {bracket_label}. Calculation may be in progress."
            })

        # Create histogram bins (0-10, 10-20, ..., 90-100)
        bin_edges = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100.1]
        bin_labels = ["0-10%", "10-20%", "20-30%", "30-40%", "40-50%",
                      "50-60%", "60-70%", "70-80%", "80-90%", "90-100%"]

        # Count values in each bin
        bin_counts = [0] * len(bin_labels)
        for pct in percentile_values:
            for i in range(len(bin_edges) - 1):
                if bin_edges[i] <= pct < bin_edges[i + 1]:
                    bin_counts[i] += 1
                    break

        # Calculate statistics
        mean_pct = sum(percentile_values) / len(percentile_values)
        sorted_values = sorted(percentile_values)
        median_pct = sorted_values[len(sorted_values) // 2]
        min_pct = min(percentile_values)
        max_pct = max(percentile_values)

        client.close()

        return jsonify({
            "success": True,
            "county": county,
            "income_bracket": bracket_label,
            "histogram": {
                "labels": bin_labels,
                "counts": bin_counts
            },
            "total_records": len(percentile_values),
            "total_in_bracket": len(matching_parcel_ids),
            "statistics": {
                "mean_percentile": round(mean_pct, 1),
                "median_percentile": round(median_pct, 1),
                "min_percentile": round(min_pct, 1),
                "max_percentile": round(max_pct, 1)
            }
        })

    except Exception as e:
        logger.error(f"Percentile distribution error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
