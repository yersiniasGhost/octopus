"""
Energy Percentile Calculator

Calculates energy consumption percentile rank for properties relative to
comparable homes. Uses scipy.stats.percentileofscore for robust percentile
calculation that handles ties and edge cases.

Interpretation: A property at the 65th percentile uses MORE electricity
than 65% of comparable homes (higher percentile = higher consumption).

Usage:
    from src.tools.comparables import EnergyPercentileCalculator

    calculator = EnergyPercentileCalculator(db, county='Franklin')
    result = calculator.calculate_percentile(parcel_id='010-000002-00')
    print(f"Percentile: {result.percentile_rank:.1f}")
"""
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pymongo.database import Database
from scipy import stats

from src.utils.log_manager import LogManager
from .finder import ComparableFinder
from .filters import ComparableFilters

logger = LogManager().get_logger(__name__)


@dataclass
class PercentileResult:
    """Result of percentile calculation for a single property"""
    parcel_id: str
    annual_kwh: Optional[float] = None
    percentile_rank: Optional[float] = None
    comparable_count: int = 0
    comparable_annual_kwh: List[float] = field(default_factory=list)

    # Criteria used to find comparables (for transparency)
    comparable_criteria: Dict = field(default_factory=dict)

    # Metadata
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if percentile was successfully calculated"""
        return self.percentile_rank is not None and self.error is None

    def to_dict(self) -> Dict:
        """Convert to dictionary for MongoDB storage"""
        return {
            'annual_kwh': self.annual_kwh,
            'percentile_rank': self.percentile_rank,
            'comparable_count': self.comparable_count,
            'comparable_criteria': self.comparable_criteria,
            'calculated_at': self.calculated_at,
            'error': self.error
        }


@dataclass
class TieredFilterConfig:
    """Configuration for tiered filter relaxation"""
    # Tier 1: Core (always applied)
    sqft_pct: float = 0.20  # ±20% of target sqft
    age_tolerance: int = 20  # ±20 years
    story_height_exact: bool = True

    # Tier 2: Location
    same_zip: bool = True

    # Minimum comparables before relaxing filters
    min_comparables: int = 30

    # Relaxation steps (applied in order if min not met)
    relaxation_steps: List[str] = field(default_factory=lambda: [
        'expand_sqft_to_30pct',
        'remove_zip_constraint',
        'expand_age_to_30_years',
        'remove_story_constraint',
        'expand_sqft_to_50pct'
    ])


class EnergyPercentileCalculator:
    """
    Calculate energy consumption percentile for properties relative to comparables.

    Uses a tiered approach to finding comparables:
    1. Tier 1 (Core): sqft ±20%, age ±20 years, same story height
    2. Tier 2 (Location): same ZIP code

    If insufficient comparables found, progressively relaxes constraints.
    """

    def __init__(self, db: Database, county: str, config: Optional[TieredFilterConfig] = None):
        """
        Initialize calculator.

        Args:
            db: MongoDB database instance
            county: County name (e.g., 'Franklin', 'Cuyahoga')
            config: Optional tiered filter configuration
        """
        self.db = db
        self.county = county
        self.config = config or TieredFilterConfig()

        # Normalize county name for collection access
        county_normalized = county.replace('County', '').strip()
        self.electrical_coll = f"{county_normalized}ElectricalDB"
        self.residential_coll = f"{county_normalized}CountyResidential"

        # Initialize comparable finder
        self.finder = ComparableFinder(db, f"{county_normalized}County")

    def calculate_percentile(self, parcel_id: str, min_months: int = 6) -> PercentileResult:
        """
        Calculate energy percentile for a single property.

        Args:
            parcel_id: Target property parcel ID
            min_months: Minimum months of data required (default 6)

        Returns:
            PercentileResult with percentile rank and metadata
        """
        result = PercentileResult(parcel_id=parcel_id)

        # Get target property's annual kWh
        target_kwh = self._get_annual_kwh(parcel_id, min_months)
        if target_kwh is None:
            result.error = f"Insufficient electrical data (need {min_months}+ months)"
            logger.warning(f"Parcel {parcel_id}: {result.error}")
            return result

        result.annual_kwh = target_kwh

        # Get target property characteristics for filtering
        target_residence = self.db[self.residential_coll].find_one({'parcel_id': parcel_id})
        if not target_residence:
            result.error = "Property not found in residential collection"
            logger.warning(f"Parcel {parcel_id}: {result.error}")
            return result

        # Find comparables with tiered filter relaxation
        comparables, criteria = self._find_comparables_with_relaxation(target_residence)
        result.comparable_criteria = criteria

        if len(comparables) < 10:
            result.error = f"Insufficient comparables found ({len(comparables)} < 10)"
            logger.warning(f"Parcel {parcel_id}: {result.error}")
            return result

        # BATCH fetch annual kWh for all comparables (optimized)
        comparable_kwh = self._batch_get_annual_kwh(comparables, min_months)

        result.comparable_count = len(comparable_kwh)
        result.comparable_annual_kwh = comparable_kwh

        if len(comparable_kwh) < 10:
            result.error = f"Insufficient comparables with electrical data ({len(comparable_kwh)} < 10)"
            logger.warning(f"Parcel {parcel_id}: {result.error}")
            return result

        # Calculate percentile using scipy
        # 'rank' method: average of 'weak' and 'strict' - handles ties well
        result.percentile_rank = stats.percentileofscore(comparable_kwh, target_kwh, kind='rank')

        logger.info(f"Parcel {parcel_id}: {result.annual_kwh:.0f} kWh, "
                   f"{result.percentile_rank:.1f}th percentile "
                   f"(n={result.comparable_count})")

        return result

    def _get_annual_kwh(self, parcel_id: str, min_months: int = 6) -> Optional[float]:
        """
        Calculate annualized kWh from electrical time series.

        Args:
            parcel_id: Property parcel ID
            min_months: Minimum months of data required

        Returns:
            Annualized kWh or None if insufficient data
        """
        doc = self.db[self.electrical_coll].find_one({'parcel_id': parcel_id})
        if not doc or 'time_series_elec' not in doc:
            return None

        return self._calculate_annual_kwh_from_doc(doc, min_months)

    def _calculate_annual_kwh_from_doc(self, doc: Dict, min_months: int = 6) -> Optional[float]:
        """Calculate annual kWh from an electrical document"""
        time_series = doc.get('time_series_elec')
        if not time_series:
            return None

        # Get valid (positive) readings
        valid_readings = [v for v in time_series.values() if v and v > 0]

        if len(valid_readings) < min_months:
            return None

        # Annualize: total * (12 / months_of_data)
        total_kwh = sum(valid_readings)
        months = len(valid_readings)
        annual_kwh = total_kwh * 12 / months

        return annual_kwh

    def _batch_get_annual_kwh(self, parcel_ids: List[str], min_months: int = 6) -> List[float]:
        """
        Batch fetch annual kWh for multiple parcels (optimized single query).

        Args:
            parcel_ids: List of parcel IDs
            min_months: Minimum months of data required

        Returns:
            List of valid annual kWh values (excludes properties with insufficient data)
        """
        # Single query to fetch all electrical data
        cursor = self.db[self.electrical_coll].find(
            {'parcel_id': {'$in': parcel_ids}},
            {'parcel_id': 1, 'time_series_elec': 1}
        )

        annual_kwh_values = []
        for doc in cursor:
            kwh = self._calculate_annual_kwh_from_doc(doc, min_months)
            if kwh is not None:
                annual_kwh_values.append(kwh)

        return annual_kwh_values

    def _find_comparables_with_relaxation(self, target: Dict) -> Tuple[List[str], Dict]:
        """
        Find comparables using tiered filters with progressive relaxation.

        Returns:
            Tuple of (list of comparable parcel_ids, criteria dict used)
        """
        target_sqft = target.get('living_area_total', 0)
        target_age = target.get('age', 0)
        target_stories = target.get('story_height', 0)
        target_zip = target.get('parcel_zip', 0)

        cfg = self.config

        # Build initial criteria (Tier 1 + Tier 2)
        criteria = {
            'sqft_range': [target_sqft * (1 - cfg.sqft_pct), target_sqft * (1 + cfg.sqft_pct)],
            'age_range': [target_age - cfg.age_tolerance, target_age + cfg.age_tolerance],
            'story_height': target_stories if cfg.story_height_exact else None,
            'zip': target_zip if cfg.same_zip else None,
            'relaxations_applied': []
        }

        # Try initial query
        query = self._build_query(criteria)
        parcel_ids = self._execute_query(query, target['parcel_id'])

        # Progressive relaxation if needed
        relaxation_idx = 0
        while len(parcel_ids) < cfg.min_comparables and relaxation_idx < len(cfg.relaxation_steps):
            step = cfg.relaxation_steps[relaxation_idx]
            criteria['relaxations_applied'].append(step)

            if step == 'expand_sqft_to_30pct':
                criteria['sqft_range'] = [target_sqft * 0.7, target_sqft * 1.3]
            elif step == 'remove_zip_constraint':
                criteria['zip'] = None
            elif step == 'expand_age_to_30_years':
                criteria['age_range'] = [target_age - 30, target_age + 30]
            elif step == 'remove_story_constraint':
                criteria['story_height'] = None
            elif step == 'expand_sqft_to_50pct':
                criteria['sqft_range'] = [target_sqft * 0.5, target_sqft * 1.5]

            query = self._build_query(criteria)
            parcel_ids = self._execute_query(query, target['parcel_id'])

            logger.debug(f"Relaxation '{step}': {len(parcel_ids)} comparables")
            relaxation_idx += 1

        return parcel_ids, criteria

    def _build_query(self, criteria: Dict) -> Dict:
        """Build MongoDB query from criteria dict"""
        query = {'living_area_total': {'$gt': 0}}  # Require valid sqft

        if criteria.get('sqft_range'):
            query['living_area_total'] = {
                '$gte': criteria['sqft_range'][0],
                '$lte': criteria['sqft_range'][1]
            }

        if criteria.get('age_range'):
            query['age'] = {
                '$gte': max(1800, criteria['age_range'][0]),  # Sanity check
                '$lte': criteria['age_range'][1]
            }

        if criteria.get('story_height'):
            query['story_height'] = criteria['story_height']

        if criteria.get('zip'):
            query['parcel_zip'] = criteria['zip']

        return query

    def _execute_query(self, query: Dict, exclude_parcel: str) -> List[str]:
        """Execute query and return list of parcel IDs"""
        query['parcel_id'] = {'$ne': exclude_parcel}
        cursor = self.db[self.residential_coll].find(query, {'parcel_id': 1})
        return [doc['parcel_id'] for doc in cursor]

    def update_property_percentile(self, parcel_id: str, target_collection: Optional[str] = None) -> PercentileResult:
        """
        Calculate percentile and store in database.

        Args:
            parcel_id: Property parcel ID
            target_collection: Collection to update (default: residential collection)

        Returns:
            PercentileResult with calculation results
        """
        result = self.calculate_percentile(parcel_id)

        if not result.is_valid:
            return result

        # Update the property document
        collection = target_collection or self.residential_coll
        update_doc = {'$set': {'energy_percentile': result.to_dict()}}

        self.db[collection].update_one({'parcel_id': parcel_id}, update_doc)
        logger.info(f"Updated {collection} for parcel {parcel_id}")

        return result

    def batch_calculate(self, parcel_ids: List[str], update_db: bool = False,
                        progress_callback=None) -> List[PercentileResult]:
        """
        Calculate percentiles for multiple properties.

        Args:
            parcel_ids: List of parcel IDs to process
            update_db: If True, update database with results
            progress_callback: Optional callback(current, total) for progress

        Returns:
            List of PercentileResult objects
        """
        results = []
        total = len(parcel_ids)

        for i, parcel_id in enumerate(parcel_ids):
            if update_db:
                result = self.update_property_percentile(parcel_id)
            else:
                result = self.calculate_percentile(parcel_id)

            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total)

        # Summary stats
        valid_results = [r for r in results if r.is_valid]
        logger.info(f"Batch complete: {len(valid_results)}/{total} successful")

        return results
