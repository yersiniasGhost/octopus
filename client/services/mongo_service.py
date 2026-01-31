"""
MongoDB Service for Energy Conservation Client Portal.

Handles all database operations for user search, profile retrieval,
and comparable analysis.
"""
import sys
from pathlib import Path
from typing import Optional
from pymongo import MongoClient
from bson import ObjectId

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager
from client.services.programs import COUNTIES

logger = LogManager().get_logger(__name__)


class MongoService:
    """MongoDB data access layer for energy portal."""

    def __init__(self):
        env = EnvVars()
        self.mongo_host = env.get_env('MONGODB_HOST', 'localhost')
        self.mongo_port = int(env.get_env('MONGODB_PORT', '27017'))
        self.empower_db_name = env.get_env('MONGODB_DATABASE', 'empower_development')
        self.campaign_db_name = env.get_env('MONGODB_CAMPAIGN', 'campaign_data')

        self.client = MongoClient(f"mongodb://{self.mongo_host}:{self.mongo_port}")
        self.db_empower = self.client[self.empower_db_name]
        self.db_campaign = self.client[self.campaign_db_name]

        logger.info(f"MongoService initialized: {self.mongo_host}:{self.mongo_port}")

    def _get_demographic_collection(self, county: str):
        """Get demographic collection for a county."""
        return self.db_empower[f"{county}CountyDemographic"]

    def _get_residential_collection(self, county: str):
        """Get residential collection for a county."""
        return self.db_empower[f"{county}CountyResidential"]

    def _serialize_doc(self, doc: dict) -> dict:
        """Convert MongoDB document to JSON-serializable dict."""
        if doc is None:
            return None
        result = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                result[k] = str(v)
            elif isinstance(v, dict):
                result[k] = self._serialize_doc(v)
            elif isinstance(v, list):
                result[k] = [self._serialize_doc(i) if isinstance(i, dict) else
                            str(i) if isinstance(i, ObjectId) else i for i in v]
            else:
                result[k] = v
        return result

    def search_users(self, query: str, county: str, participants_only: bool = False, limit: int = 20) -> list:
        """
        Search for users by name.

        Args:
            query: Search string (name)
            county: County to search in
            participants_only: If True, only return users who are campaign participants
            limit: Maximum results to return

        Returns:
            List of matching users with basic info
        """
        if county not in COUNTIES:
            logger.warning(f"Invalid county: {county}")
            return []

        collection = self._get_demographic_collection(county)

        # Build search filter - case-insensitive regex on customer_name
        search_filter = {
            "customer_name": {"$regex": query, "$options": "i"}
        }

        logger.debug(f"Searching users: query='{query}', county={county}, participants_only={participants_only}")

        # Get matching users
        cursor = collection.find(
            search_filter,
            {"parcel_id": 1, "customer_name": 1, "address": 1, "_id": 0}
        ).limit(limit * 2 if participants_only else limit)  # Fetch extra if filtering

        results = []
        participant_ids = set()

        # If filtering by participants, get the participant list first
        if participants_only:
            participant_cursor = self.db_campaign["participants"].find({}, {"parcel_id": 1})
            participant_ids = {p.get("parcel_id") for p in participant_cursor if p.get("parcel_id")}
            logger.debug(f"Found {len(participant_ids)} participants in campaign database")

        for doc in cursor:
            parcel_id = doc.get("parcel_id")

            # Skip if filtering by participants and not in list
            if participants_only and parcel_id not in participant_ids:
                continue

            results.append({
                "id": parcel_id,
                "name": doc.get("customer_name", "Unknown"),
                "address": doc.get("address", ""),
                "county": county,
                "is_participant": parcel_id in participant_ids if participant_ids else None
            })

            if len(results) >= limit:
                break

        logger.info(f"Search found {len(results)} users for query '{query}'")
        return results

    def get_user_profile(self, parcel_id: str, county: str) -> Optional[dict]:
        """
        Get complete user profile including demographic and residential data.

        Args:
            parcel_id: User's parcel ID
            county: County name

        Returns:
            Complete user profile or None if not found
        """
        if county not in COUNTIES:
            logger.warning(f"Invalid county: {county}")
            return None

        demo_coll = self._get_demographic_collection(county)
        res_coll = self._get_residential_collection(county)

        # Get demographic data
        demo_doc = demo_coll.find_one({"parcel_id": parcel_id})
        if not demo_doc:
            logger.warning(f"No demographic data for parcel_id: {parcel_id}")
            return None

        # Get residential data
        res_doc = res_coll.find_one({"parcel_id": parcel_id})
        if not res_doc:
            logger.warning(f"No residential data for parcel_id: {parcel_id} in {county}County")

        # Check if participant
        participant_doc = self.db_campaign["participants"].find_one({"parcel_id": parcel_id})
        is_participant = participant_doc is not None

        # Build profile - handle -1 as "no data available"
        annual_kwh_cost = demo_doc.get("annual_kwh_cost", 0) or 0
        raw_gas_cost = demo_doc.get("annual_gas_cost")
        gas_available = raw_gas_cost is not None and raw_gas_cost != -1
        annual_gas_cost = raw_gas_cost if gas_available else None
        # Total only includes gas if available (not -1)
        total_energy_cost = annual_kwh_cost + (annual_gas_cost if gas_available else 0)
        estimated_income = demo_doc.get("estimated_income", 0) or 0

        # Calculate energy burden
        energy_burden_pct = 0
        if estimated_income > 0:
            energy_burden_pct = round((total_energy_cost / estimated_income) * 100, 1)

        # Get energy percentile from residential data (rounded to whole number)
        energy_percentile = None
        if res_doc and "energy_percentile" in res_doc:
            ep = res_doc.get("energy_percentile", {})
            if isinstance(ep, dict):
                energy_percentile = ep.get("percentile_rank")
            elif isinstance(ep, (int, float)):
                energy_percentile = ep
            # Round to whole number for cleaner UI display
            if energy_percentile is not None:
                energy_percentile = round(energy_percentile)
            else:
                logger.warning(f"energy_percentile field exists but percentile_rank missing for {parcel_id}")
        elif res_doc:
            logger.warning(f"No energy_percentile field in residential data for {parcel_id}")

        profile = {
            "parcel_id": parcel_id,
            "name": demo_doc.get("customer_name", "Unknown"),
            "address": demo_doc.get("address", ""),
            "county": county,
            "is_participant": is_participant,
            "demographic": {
                "estimated_income": estimated_income,
                "household_size": demo_doc.get("household_size", demo_doc.get("number_of_people", 1)) or 1,
                "annual_kwh_cost": round(annual_kwh_cost, 2),
                "annual_gas_cost": round(annual_gas_cost, 2) if gas_available else None,
                "total_energy_cost": round(total_energy_cost, 2),
                "energy_burden_pct": energy_burden_pct,
                "gas_available": gas_available
            },
            "home": {
                "living_area_sqft": res_doc.get("living_area_total") if res_doc else None,
                "story_height": res_doc.get("story_height") if res_doc else None,
                "age": res_doc.get("age") if res_doc else None,
                "bedrooms": res_doc.get("bedrooms") if res_doc else None,
                "bathrooms": res_doc.get("bathrooms") if res_doc else None
            },
            "energy_percentile": energy_percentile
        }

        # Get comparables summary
        comparables = self.get_comparables_summary(parcel_id, county)
        if comparables:
            profile["comparables"] = comparables
        else:
            logger.warning(f"No comparables data for {parcel_id}")

        # Log summary of missing data for debugging
        missing = []
        if not res_doc:
            missing.append("residential")
        if energy_percentile is None:
            missing.append("energy_percentile")
        if not comparables:
            missing.append("comparables")
        if profile["home"]["living_area_sqft"] is None:
            missing.append("living_area")
        if missing:
            logger.error(f"Profile incomplete for {parcel_id} ({profile['name']}): missing {', '.join(missing)}")

        logger.info(f"Retrieved profile for {parcel_id}: {profile['name']}")
        return profile

    def get_comparables_summary(self, parcel_id: str, county: str) -> Optional[dict]:
        """
        Get comparable homes analysis summary.

        Finds similar homes based on square footage and age, calculates
        average energy costs for comparison.
        """
        if county not in COUNTIES:
            return None

        res_coll = self._get_residential_collection(county)
        demo_coll = self._get_demographic_collection(county)

        # Get the target home's characteristics
        target_res = res_coll.find_one({"parcel_id": parcel_id})
        target_demo = demo_coll.find_one({"parcel_id": parcel_id})

        if not target_res or not target_demo:
            logger.debug(f"Comparables: missing res={not target_res}, demo={not target_demo} for {parcel_id}")
            return None

        sqft = target_res.get("living_area_total")
        age = target_res.get("age")

        if not sqft:
            logger.debug(f"Comparables: no living_area_total for {parcel_id}")
            return None

        # Define comparable range (±20% sqft, ±10 years age)
        sqft_low = sqft * 0.8
        sqft_high = sqft * 1.2

        match_filter = {
            "living_area_total": {"$gte": sqft_low, "$lte": sqft_high},
            "parcel_id": {"$ne": parcel_id}  # Exclude target
        }

        if age:
            match_filter["age"] = {"$gte": max(0, age - 10), "$lte": age + 10}

        # Get comparable parcel IDs
        comparable_parcels = [doc["parcel_id"] for doc in res_coll.find(match_filter, {"parcel_id": 1}).limit(100)]

        if not comparable_parcels:
            logger.debug(f"Comparables: no matching homes for {parcel_id} (sqft={sqft}, age={age})")
            return None

        # Get energy costs for comparables - separate electric and gas averages
        pipeline = [
            {"$match": {"parcel_id": {"$in": comparable_parcels}}},
            {"$project": {
                "kwh_cost": {"$ifNull": ["$annual_kwh_cost", 0]},
                "gas_cost": {"$ifNull": ["$annual_gas_cost", 0]},
                "total_cost": {"$add": [
                    {"$ifNull": ["$annual_kwh_cost", 0]},
                    {"$ifNull": ["$annual_gas_cost", 0]}
                ]}
            }},
            {"$group": {
                "_id": None,
                "avg_kwh_cost": {"$avg": "$kwh_cost"},
                "avg_gas_cost": {"$avg": "$gas_cost"},
                "avg_total_cost": {"$avg": "$total_cost"},
                "median_costs": {"$push": "$total_cost"},
                "count": {"$sum": 1}
            }}
        ]

        result = list(demo_coll.aggregate(pipeline))

        if not result:
            logger.debug(f"Comparables: aggregation returned empty for {parcel_id}")
            return None

        agg = result[0]
        avg_kwh = agg.get("avg_kwh_cost", 0)
        avg_gas = agg.get("avg_gas_cost", 0)
        avg_cost = agg.get("avg_total_cost", 0)
        costs = sorted(agg.get("median_costs", []))
        count = agg.get("count", 0)

        # Calculate median
        median_cost = 0
        if costs:
            mid = len(costs) // 2
            median_cost = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2

        # Calculate potential savings (exclude -1 gas values)
        user_kwh = target_demo.get("annual_kwh_cost", 0) or 0
        user_gas = target_demo.get("annual_gas_cost")
        user_has_gas = user_gas is not None and user_gas != -1
        user_gas = user_gas if user_has_gas else 0
        user_total = user_kwh + user_gas
        potential_savings = max(0, user_total - median_cost)

        return {
            "count": count,
            "avg_kwh_cost": round(avg_kwh, 2),
            "avg_gas_cost": round(avg_gas, 2),
            "avg_total_cost": round(avg_cost, 2),
            "median_total_cost": round(median_cost, 2),
            "potential_savings": round(potential_savings, 2),
            "comparison_criteria": {
                "sqft_range": f"{int(sqft_low)}-{int(sqft_high)} sq ft",
                "age_range": f"{max(0, age - 10)}-{age + 10} years" if age else "any"
            }
        }

    def is_participant(self, parcel_id: str) -> bool:
        """Check if a parcel_id is in the participants collection."""
        doc = self.db_campaign["participants"].find_one({"parcel_id": parcel_id})
        return doc is not None
