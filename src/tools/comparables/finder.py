"""
Comparable Residence Finder

Finds comparable residences based on property characteristics, demographics,
and energy consumption patterns. Uses weighted similarity scoring to rank
candidates.

The core use case is finding homes similar to a target property to enable
fair energy efficiency comparisons - we want to compare homes of similar
size, age, and occupancy rather than comparing a 5000 sqft mansion to a
1500 sqft ranch.

Usage:
    from src.tools.comparables import ComparableFinder, ComparableFilters

    finder = ComparableFinder(db, county='FranklinCounty')

    # Find 10 comparable homes with same ZIP and similar size
    results = finder.find_comparables(
        parcel_id='12345',
        n_results=10,
        filters=ComparableFilters(same_zip=True, sqft_tolerance=500)
    )

    for comp in results.comparables:
        print(f"{comp.address}: {comp.score.overall_score:.2f} similarity")
"""
from typing import Optional, Dict, List, Tuple
from pymongo.database import Database

from src.utils.log_manager import LogManager
from .models import ComparableResult, ComparableScore, ComparableSearchResult
from .filters import ComparableFilters, ScoringWeights

logger = LogManager().get_logger(__name__)


class ComparableFinder:
    """
    Find comparable residences based on property characteristics.

    Combines data from multiple collections:
    - {County}Residential: Physical property data (sqft, stories, age, rooms)
    - {County}Demographic: Occupant data (household size, income, energy costs)
    - {County}ThermalLoads: Energy consumption patterns (heating/cooling loads)
    """

    def __init__(self, db: Database, county: str, weights: Optional[ScoringWeights] = None):
        """
        Initialize comparable finder.

        Args:
            db: MongoDB database instance
            county: County name (e.g., 'FranklinCounty', 'CuyahogaCounty')
            weights: Optional custom scoring weights (uses defaults if not provided)
        """
        self.db = db
        self.county = county
        self.weights = weights or ScoringWeights()

        # Collection names follow {County}{Type} pattern
        self.residential_coll = f"{county}Residential"
        self.demographic_coll = f"{county}Demographic"
        self.thermal_coll = f"{county}ThermalLoads"

    def find_comparables(self, parcel_id: str, n_results: int = 10,
                         filters: Optional[ComparableFilters] = None) -> ComparableSearchResult:
        """
        Find comparable residences for a target property.

        Args:
            parcel_id: Parcel ID of the target property
            n_results: Number of comparable results to return
            filters: Optional filter configuration

        Returns:
            ComparableSearchResult with ranked comparable properties
        """
        filters = filters or ComparableFilters()
        logger.info(f"Finding {n_results} comparables for parcel {parcel_id} in {self.county}")

        # Load target property data
        target_residence = self._get_residence(parcel_id)
        if not target_residence:
            logger.warning(f"Target parcel {parcel_id} not found in {self.residential_coll}")
            return ComparableSearchResult(
                target_parcel_id=parcel_id,
                county=self.county,
                comparables=[],
                total_candidates=0,
                search_filters_applied=filters.to_dict()
            )

        target_demographic = self._get_demographic(parcel_id)
        target_thermal = self._get_thermal(parcel_id)

        # Build MongoDB query from filters
        query = self._build_query(target_residence, target_demographic, filters)

        # Exclude target property from results
        if filters.exclude_parcel_ids:
            exclude_ids = list(filters.exclude_parcel_ids) + [parcel_id]
        else:
            exclude_ids = [parcel_id]
        query['parcel_id'] = {'$nin': exclude_ids}

        # Get candidate properties
        candidates = list(self.db[self.residential_coll].find(query))
        total_candidates = len(candidates)
        logger.info(f"Found {total_candidates} candidates matching query filters")

        # Score and rank candidates
        scored_candidates = []
        for candidate in candidates:
            cand_demographic = self._get_demographic(candidate['parcel_id'])
            cand_thermal = self._get_thermal(candidate['parcel_id'])

            score = self._calculate_similarity(
                target_residence, target_demographic,
                candidate, cand_demographic
            )

            # Apply post-query tolerance filters (for features not easily queryable)
            if self._passes_tolerance_filters(target_residence, target_demographic,
                                              candidate, cand_demographic, filters):
                result = ComparableResult.from_records(
                    candidate, cand_demographic, cand_thermal, score
                )
                scored_candidates.append(result)

        # Sort by similarity score (descending) and take top N
        scored_candidates.sort(key=lambda x: x.score.overall_score, reverse=True)
        top_results = scored_candidates[:n_results]

        # Calculate statistics
        avg_sqft_diff = None
        avg_age_diff = None
        avg_energy_cost = None

        if top_results:
            sqft_diffs = [r.score.sqft_diff for r in top_results if r.score.sqft_diff is not None]
            age_diffs = [r.score.age_diff for r in top_results if r.score.age_diff is not None]
            energy_costs = [r.annual_kwh_cost for r in top_results if r.annual_kwh_cost is not None]

            avg_sqft_diff = sum(sqft_diffs) / len(sqft_diffs) if sqft_diffs else None
            avg_age_diff = sum(age_diffs) / len(age_diffs) if age_diffs else None
            avg_energy_cost = sum(energy_costs) / len(energy_costs) if energy_costs else None

        return ComparableSearchResult(
            target_parcel_id=parcel_id,
            target_address=target_residence.get('address'),
            county=self.county,
            target_sqft=target_residence.get('living_area_total'),
            target_stories=target_residence.get('story_height'),
            target_age=target_residence.get('age'),
            target_household_size=self._get_household_size(target_demographic),
            comparables=top_results,
            total_candidates=total_candidates,
            search_filters_applied=filters.to_dict(),
            avg_sqft_diff=avg_sqft_diff,
            avg_age_diff=avg_age_diff,
            avg_energy_cost=avg_energy_cost
        )

    def find_comparables_for_address(self, address: str, zip_code: Optional[int] = None,
                                     n_results: int = 10,
                                     filters: Optional[ComparableFilters] = None) -> ComparableSearchResult:
        """
        Find comparable residences by address lookup.

        Args:
            address: Property address to search for
            zip_code: Optional ZIP code to narrow search
            n_results: Number of comparable results
            filters: Optional filter configuration

        Returns:
            ComparableSearchResult with ranked comparable properties
        """
        # Find parcel by address
        query = {'address': {'$regex': address, '$options': 'i'}}
        if zip_code:
            query['parcel_zip'] = zip_code

        target = self.db[self.residential_coll].find_one(query)
        if not target:
            logger.warning(f"Address '{address}' not found in {self.residential_coll}")
            return ComparableSearchResult(
                target_parcel_id='',
                target_address=address,
                county=self.county,
                comparables=[],
                total_candidates=0,
                search_filters_applied={}
            )

        return self.find_comparables(target['parcel_id'], n_results, filters)

    def _get_residence(self, parcel_id: str) -> Optional[Dict]:
        """Get residential data for a parcel"""
        if self.residential_coll not in self.db.list_collection_names():
            return None
        return self.db[self.residential_coll].find_one({'parcel_id': parcel_id})

    def _get_demographic(self, parcel_id: str) -> Optional[Dict]:
        """Get demographic data for a parcel"""
        if self.demographic_coll not in self.db.list_collection_names():
            return None
        return self.db[self.demographic_coll].find_one({'parcel_id': parcel_id})

    def _get_thermal(self, parcel_id: str) -> Optional[Dict]:
        """Get thermal load data for a parcel"""
        if self.thermal_coll not in self.db.list_collection_names():
            return None
        return self.db[self.thermal_coll].find_one({'parcel_id': parcel_id})

    def _get_household_size(self, demographic: Optional[Dict]) -> Optional[int]:
        """Extract household size from demographic record"""
        if not demographic:
            return None
        # Try enriched field first, fall back to utility-provided field
        size = demographic.get('household_size') or demographic.get('md_householdsize')
        if size and size > 0:
            return int(size)
        return None

    def _build_query(self, target_residence: Dict, target_demographic: Optional[Dict],
                     filters: ComparableFilters) -> Dict:
        """Build MongoDB query from filters"""
        query = {}

        # Geographic filters
        if filters.same_zip:
            target_zip = target_residence.get('parcel_zip')
            if target_zip and target_zip > 0:
                query['parcel_zip'] = target_zip

        if filters.same_city:
            target_city = target_residence.get('parcel_city')
            if target_city and target_city != 'NA':
                query['parcel_city'] = target_city

        if filters.zip_codes:
            query['parcel_zip'] = {'$in': filters.zip_codes}

        if filters.census_tract:
            query['census_tract'] = filters.census_tract

        # Square footage filters
        target_sqft = target_residence.get('living_area_total', 0)
        if filters.sqft_tolerance and target_sqft > 0:
            query['living_area_total'] = {
                '$gte': target_sqft - filters.sqft_tolerance,
                '$lte': target_sqft + filters.sqft_tolerance
            }
        else:
            sqft_conditions = {}
            if filters.sqft_min is not None:
                sqft_conditions['$gte'] = filters.sqft_min
            if filters.sqft_max is not None:
                sqft_conditions['$lte'] = filters.sqft_max
            if sqft_conditions:
                query['living_area_total'] = sqft_conditions

        # Story height filters
        target_stories = target_residence.get('story_height', 0)
        if filters.story_height_exact and target_stories > 0:
            query['story_height'] = target_stories
        elif filters.story_height_tolerance and target_stories > 0:
            query['story_height'] = {
                '$gte': target_stories - filters.story_height_tolerance,
                '$lte': target_stories + filters.story_height_tolerance
            }

        # Age filters
        target_age = target_residence.get('age', -1)
        if filters.age_tolerance and target_age > 0:
            query['age'] = {
                '$gte': max(0, target_age - filters.age_tolerance),
                '$lte': target_age + filters.age_tolerance
            }
        else:
            age_conditions = {}
            if filters.age_min is not None:
                age_conditions['$gte'] = filters.age_min
            if filters.age_max is not None:
                age_conditions['$lte'] = filters.age_max
            if age_conditions:
                query['age'] = age_conditions

        # Bedroom filters
        target_bedrooms = target_residence.get('bedrooms', -1)
        if filters.bedrooms_exact and target_bedrooms > 0:
            query['bedrooms'] = target_bedrooms
        elif filters.bedrooms_tolerance and target_bedrooms > 0:
            query['bedrooms'] = {
                '$gte': max(0, target_bedrooms - filters.bedrooms_tolerance),
                '$lte': target_bedrooms + filters.bedrooms_tolerance
            }
        else:
            br_conditions = {}
            if filters.bedrooms_min is not None:
                br_conditions['$gte'] = filters.bedrooms_min
            if filters.bedrooms_max is not None:
                br_conditions['$lte'] = filters.bedrooms_max
            if br_conditions:
                query['bedrooms'] = br_conditions

        # Bathroom filters
        bath_conditions = {}
        if filters.bathrooms_min is not None:
            bath_conditions['$gte'] = filters.bathrooms_min
        if filters.bathrooms_max is not None:
            bath_conditions['$lte'] = filters.bathrooms_max
        if bath_conditions:
            query['bathrooms'] = bath_conditions

        # Construction characteristic filters
        if filters.construction_quality:
            query['construction_quality'] = {'$in': filters.construction_quality}
        if filters.heat_type:
            query['heat_type'] = {'$in': filters.heat_type}
        if filters.air_conditioning:
            query['air_conditioning'] = {'$in': filters.air_conditioning}

        return query

    def _passes_tolerance_filters(self, target_res: Dict, target_demo: Optional[Dict],
                                  candidate_res: Dict, candidate_demo: Optional[Dict],
                                  filters: ComparableFilters) -> bool:
        """Check if candidate passes tolerance-based filters not easily expressed in MongoDB query"""

        # Household size tolerance (requires joining with demographic collection)
        if filters.household_size_tolerance is not None:
            target_size = self._get_household_size(target_demo)
            cand_size = self._get_household_size(candidate_demo)
            if target_size and cand_size:
                if abs(target_size - cand_size) > filters.household_size_tolerance:
                    return False

        if filters.household_size_exact:
            target_size = self._get_household_size(target_demo)
            cand_size = self._get_household_size(candidate_demo)
            if target_size and cand_size and target_size != cand_size:
                return False

        # Income tolerance
        if filters.income_tolerance is not None and target_demo and candidate_demo:
            target_income = target_demo.get('estimated_income', -1)
            cand_income = candidate_demo.get('estimated_income', -1)
            if target_income > 0 and cand_income > 0:
                if abs(target_income - cand_income) > filters.income_tolerance:
                    return False

        if filters.income_tolerance_pct is not None and target_demo and candidate_demo:
            target_income = target_demo.get('estimated_income', -1)
            cand_income = candidate_demo.get('estimated_income', -1)
            if target_income > 0 and cand_income > 0:
                pct_diff = abs(target_income - cand_income) / target_income
                if pct_diff > filters.income_tolerance_pct:
                    return False

        # Bathroom tolerance
        if filters.bathrooms_tolerance is not None:
            target_baths = target_res.get('bathrooms', -1)
            cand_baths = candidate_res.get('bathrooms', -1)
            if target_baths > 0 and cand_baths > 0:
                if abs(target_baths - cand_baths) > filters.bathrooms_tolerance:
                    return False

        return True

    def _calculate_similarity(self, target_res: Dict, target_demo: Optional[Dict],
                              candidate_res: Dict, candidate_demo: Optional[Dict]) -> ComparableScore:
        """
        Calculate similarity score between target and candidate properties.

        Uses weighted scoring across multiple features. Each feature score is
        normalized to 0-1 range, then combined using configured weights.
        """
        w = self.weights
        total_weight = 0.0
        weighted_sum = 0.0

        # Initialize score components
        sqft_score = 0.0
        story_score = 0.0
        age_score = 0.0
        bedrooms_score = 0.0
        bathrooms_score = 0.0
        household_score = 0.0
        income_score = 0.0

        sqft_diff = 0.0
        story_diff = 0.0
        age_diff = 0.0

        # Square footage similarity
        target_sqft = target_res.get('living_area_total', 0)
        cand_sqft = candidate_res.get('living_area_total', 0)
        if target_sqft > 0 and cand_sqft > 0:
            sqft_diff = abs(target_sqft - cand_sqft)
            sqft_score = max(0, 1 - (sqft_diff / w.sqft_reference_range))
            weighted_sum += sqft_score * w.sqft_weight
            total_weight += w.sqft_weight

        # Story height similarity
        target_stories = target_res.get('story_height', 0)
        cand_stories = candidate_res.get('story_height', 0)
        if target_stories > 0 and cand_stories > 0:
            story_diff = abs(target_stories - cand_stories)
            # Exact match = 1.0, each 0.5 story diff reduces score by 0.25
            story_score = max(0, 1 - (story_diff * 0.5))
            weighted_sum += story_score * w.story_weight
            total_weight += w.story_weight

        # Building age similarity
        target_age = target_res.get('age', -1)
        cand_age = candidate_res.get('age', -1)
        if target_age > 0 and cand_age > 0:
            age_diff = abs(target_age - cand_age)
            age_score = max(0, 1 - (age_diff / w.age_reference_range))
            weighted_sum += age_score * w.age_weight
            total_weight += w.age_weight

        # Bedroom similarity
        target_br = target_res.get('bedrooms', -1)
        cand_br = candidate_res.get('bedrooms', -1)
        if target_br > 0 and cand_br > 0:
            br_diff = abs(target_br - cand_br)
            bedrooms_score = max(0, 1 - (br_diff / 3))  # 3 bedroom diff = 0 score
            weighted_sum += bedrooms_score * w.bedrooms_weight
            total_weight += w.bedrooms_weight

        # Bathroom similarity
        target_bath = target_res.get('bathrooms', -1)
        cand_bath = candidate_res.get('bathrooms', -1)
        if target_bath > 0 and cand_bath > 0:
            bath_diff = abs(target_bath - cand_bath)
            bathrooms_score = max(0, 1 - (bath_diff / 2))  # 2 bathroom diff = 0 score
            weighted_sum += bathrooms_score * w.bathrooms_weight
            total_weight += w.bathrooms_weight

        # Household size similarity (from demographic data)
        target_hh = self._get_household_size(target_demo)
        cand_hh = self._get_household_size(candidate_demo)
        if target_hh and cand_hh:
            hh_diff = abs(target_hh - cand_hh)
            household_score = max(0, 1 - (hh_diff / 4))  # 4 person diff = 0 score
            weighted_sum += household_score * w.household_weight
            total_weight += w.household_weight

        # Income similarity (from demographic data)
        if target_demo and candidate_demo:
            target_income = target_demo.get('estimated_income', -1)
            cand_income = candidate_demo.get('estimated_income', -1)
            if target_income > 0 and cand_income > 0:
                income_diff = abs(target_income - cand_income)
                income_score = max(0, 1 - (income_diff / w.income_reference_range))
                weighted_sum += income_score * w.income_weight
                total_weight += w.income_weight

        # Calculate overall score
        overall_score = weighted_sum / total_weight if total_weight > 0 else 0.0

        return ComparableScore(
            overall_score=overall_score,
            sqft_score=sqft_score,
            story_score=story_score,
            age_score=age_score,
            bedrooms_score=bedrooms_score,
            bathrooms_score=bathrooms_score,
            household_score=household_score,
            income_score=income_score,
            sqft_diff=sqft_diff,
            story_diff=story_diff,
            age_diff=age_diff
        )
