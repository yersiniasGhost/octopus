"""
Tests for Comparable Residence Finder

Tests the ComparableFinder class using mock MongoDB data to verify:
- Filter application (geographic, physical, demographic)
- Similarity scoring calculations
- Result ranking and limiting
- Edge cases (missing data, no matches)
"""
import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, List

from src.tools.comparables import ComparableFinder, ComparableFilters
from src.tools.comparables.models import ComparableScore, ComparableResult
from src.tools.comparables.filters import ScoringWeights


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_residential_data() -> List[Dict]:
    """Sample residential property data"""
    return [
        {
            'parcel_id': 'TARGET001',
            'address': '123 MAIN ST',
            'parcel_city': 'COLUMBUS',
            'parcel_zip': 43210,
            'living_area_total': 2500,
            'story_height': 2.0,
            'age': 30,
            'bedrooms': 4,
            'bathrooms': 2.5,
            'construction_quality': 'GOOD',
            'heat_type': 'FORCED AIR',
            'air_conditioning': 'CENTRAL',
            'census_tract': '001234'
        },
        {
            'parcel_id': 'COMP001',
            'address': '125 MAIN ST',
            'parcel_city': 'COLUMBUS',
            'parcel_zip': 43210,
            'living_area_total': 2400,  # 100 sqft diff
            'story_height': 2.0,  # Same
            'age': 28,  # 2 years diff
            'bedrooms': 4,  # Same
            'bathrooms': 2.5,  # Same
            'construction_quality': 'GOOD',
            'heat_type': 'FORCED AIR',
            'air_conditioning': 'CENTRAL',
            'census_tract': '001234'
        },
        {
            'parcel_id': 'COMP002',
            'address': '200 OAK AVE',
            'parcel_city': 'COLUMBUS',
            'parcel_zip': 43210,
            'living_area_total': 3000,  # 500 sqft diff
            'story_height': 2.5,  # 0.5 story diff
            'age': 40,  # 10 years diff
            'bedrooms': 5,  # 1 bedroom diff
            'bathrooms': 3.0,  # 0.5 bathroom diff
            'construction_quality': 'EXCELLENT',
            'heat_type': 'FORCED AIR',
            'air_conditioning': 'CENTRAL',
            'census_tract': '001234'
        },
        {
            'parcel_id': 'COMP003',
            'address': '500 ELM ST',
            'parcel_city': 'DUBLIN',  # Different city
            'parcel_zip': 43017,  # Different ZIP
            'living_area_total': 2550,  # 50 sqft diff
            'story_height': 2.0,
            'age': 32,
            'bedrooms': 4,
            'bathrooms': 2.5,
            'construction_quality': 'GOOD',
            'heat_type': 'FORCED AIR',
            'air_conditioning': 'CENTRAL',
            'census_tract': '005678'
        },
        {
            'parcel_id': 'COMP004',
            'address': '700 PINE RD',
            'parcel_city': 'COLUMBUS',
            'parcel_zip': 43210,
            'living_area_total': 1500,  # 1000 sqft diff (very different)
            'story_height': 1.0,  # 1 story diff
            'age': 50,  # 20 years diff
            'bedrooms': 3,
            'bathrooms': 1.5,
            'construction_quality': 'FAIR',
            'heat_type': 'BASEBOARD',
            'air_conditioning': 'WINDOW',
            'census_tract': '001234'
        },
    ]


@pytest.fixture
def mock_demographic_data() -> List[Dict]:
    """Sample demographic data"""
    return [
        {
            'parcel_id': 'TARGET001',
            'household_size': 4,
            'md_householdsize': 4,
            'estimated_income': 75000,
            'annual_kwh_cost': 2500,
            'annual_gas_cost': 1200,
            'total_energy_burden': 0.049
        },
        {
            'parcel_id': 'COMP001',
            'household_size': 4,
            'md_householdsize': 4,
            'estimated_income': 80000,
            'annual_kwh_cost': 2300,
            'annual_gas_cost': 1100,
            'total_energy_burden': 0.043
        },
        {
            'parcel_id': 'COMP002',
            'household_size': 5,
            'md_householdsize': 5,
            'estimated_income': 95000,
            'annual_kwh_cost': 3200,
            'annual_gas_cost': 1500,
            'total_energy_burden': 0.049
        },
        {
            'parcel_id': 'COMP003',
            'household_size': 3,
            'md_householdsize': 3,
            'estimated_income': 70000,
            'annual_kwh_cost': 2400,
            'annual_gas_cost': 1150,
            'total_energy_burden': 0.051
        },
        {
            'parcel_id': 'COMP004',
            'household_size': 2,
            'md_householdsize': 2,
            'estimated_income': 45000,
            'annual_kwh_cost': 1800,
            'annual_gas_cost': 900,
            'total_energy_burden': 0.060
        },
    ]


@pytest.fixture
def mock_db(mock_residential_data, mock_demographic_data):
    """Create mock MongoDB database"""
    db = MagicMock()

    # Mock collection names
    db.list_collection_names.return_value = [
        'TestCountyResidential',
        'TestCountyDemographic',
        'TestCountyThermalLoads'
    ]

    # Create mock collections
    residential_coll = MagicMock()
    demographic_coll = MagicMock()
    thermal_coll = MagicMock()

    def residential_find_one(query):
        parcel_id = query.get('parcel_id')
        if parcel_id:
            for rec in mock_residential_data:
                if rec['parcel_id'] == parcel_id:
                    return rec
        return None

    def demographic_find_one(query):
        parcel_id = query.get('parcel_id')
        if parcel_id:
            for rec in mock_demographic_data:
                if rec['parcel_id'] == parcel_id:
                    return rec
        return None

    def residential_find(query):
        """Filter residential data based on query"""
        results = []
        for rec in mock_residential_data:
            passes = True

            # Check parcel_id exclusion
            if 'parcel_id' in query and '$nin' in query['parcel_id']:
                if rec['parcel_id'] in query['parcel_id']['$nin']:
                    passes = False

            # Check ZIP code
            if 'parcel_zip' in query and passes:
                if isinstance(query['parcel_zip'], dict):
                    if '$in' in query['parcel_zip']:
                        if rec['parcel_zip'] not in query['parcel_zip']['$in']:
                            passes = False
                else:
                    if rec['parcel_zip'] != query['parcel_zip']:
                        passes = False

            # Check city
            if 'parcel_city' in query and passes:
                if rec['parcel_city'] != query['parcel_city']:
                    passes = False

            # Check sqft range
            if 'living_area_total' in query and passes:
                sqft_query = query['living_area_total']
                if '$gte' in sqft_query and rec['living_area_total'] < sqft_query['$gte']:
                    passes = False
                if '$lte' in sqft_query and rec['living_area_total'] > sqft_query['$lte']:
                    passes = False

            # Check story height
            if 'story_height' in query and passes:
                sh_query = query['story_height']
                if isinstance(sh_query, dict):
                    if '$gte' in sh_query and rec['story_height'] < sh_query['$gte']:
                        passes = False
                    if '$lte' in sh_query and rec['story_height'] > sh_query['$lte']:
                        passes = False
                else:
                    if rec['story_height'] != sh_query:
                        passes = False

            # Check age range
            if 'age' in query and passes:
                age_query = query['age']
                if '$gte' in age_query and rec['age'] < age_query['$gte']:
                    passes = False
                if '$lte' in age_query and rec['age'] > age_query['$lte']:
                    passes = False

            # Check bedrooms
            if 'bedrooms' in query and passes:
                br_query = query['bedrooms']
                if isinstance(br_query, dict):
                    if '$gte' in br_query and rec['bedrooms'] < br_query['$gte']:
                        passes = False
                    if '$lte' in br_query and rec['bedrooms'] > br_query['$lte']:
                        passes = False
                else:
                    if rec['bedrooms'] != br_query:
                        passes = False

            if passes:
                results.append(rec)

        return results

    residential_coll.find_one = residential_find_one
    residential_coll.find = residential_find

    demographic_coll.find_one = demographic_find_one
    thermal_coll.find_one.return_value = None

    # Store collections for direct access in tests that need to override
    collections = {
        'TestCountyResidential': residential_coll,
        'TestCountyDemographic': demographic_coll,
        'TestCountyThermalLoads': thermal_coll
    }

    # Configure __getitem__ for collection access
    def get_collection(self, name):
        if name in collections:
            return collections[name]
        if 'Residential' in name:
            return residential_coll
        elif 'Demographic' in name:
            return demographic_coll
        elif 'ThermalLoads' in name:
            return thermal_coll
        return MagicMock()

    db.__getitem__ = lambda self, name: get_collection(db, name)

    return db


# =============================================================================
# Unit Tests - Scoring
# =============================================================================

class TestComparableScore:
    """Test similarity scoring calculations"""

    def test_identical_properties_score_1(self, mock_db, mock_residential_data):
        """Identical properties should score 1.0"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        # Compare property to itself (excluding parcel_id difference)
        target = mock_residential_data[0]
        candidate = target.copy()
        candidate['parcel_id'] = 'DIFFERENT'

        score = finder._calculate_similarity(target, None, candidate, None)

        assert score.overall_score == 1.0
        assert score.sqft_score == 1.0
        assert score.story_score == 1.0
        assert score.age_score == 1.0

    def test_similar_properties_high_score(self, mock_db, mock_residential_data):
        """Similar properties should score high"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        target = mock_residential_data[0]  # TARGET001
        similar = mock_residential_data[1]  # COMP001 - very similar

        score = finder._calculate_similarity(target, None, similar, None)

        assert score.overall_score > 0.9
        assert score.sqft_diff == 100  # 2500 vs 2400
        assert score.story_diff == 0.0  # Both 2.0
        assert score.age_diff == 2  # 30 vs 28

    def test_different_properties_low_score(self, mock_db, mock_residential_data):
        """Very different properties should score lower than similar ones"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        target = mock_residential_data[0]  # TARGET001 (2500 sqft, 2 story, 30 yr)
        similar = mock_residential_data[1]  # COMP001 - very similar
        different = mock_residential_data[4]  # COMP004 (1500 sqft, 1 story, 50 yr)

        score_similar = finder._calculate_similarity(target, None, similar, None)
        score_different = finder._calculate_similarity(target, None, different, None)

        # Different should score lower than similar
        assert score_different.overall_score < score_similar.overall_score
        assert score_different.sqft_diff == 1000
        assert score_different.story_diff == 1.0
        assert score_different.age_diff == 20

    def test_scoring_with_demographic_data(self, mock_db, mock_residential_data, mock_demographic_data):
        """Scoring should incorporate demographic data when available"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        target_res = mock_residential_data[0]
        target_demo = mock_demographic_data[0]
        similar_res = mock_residential_data[1]
        similar_demo = mock_demographic_data[1]

        score = finder._calculate_similarity(target_res, target_demo, similar_res, similar_demo)

        # Should have household and income scores
        assert score.household_score > 0
        assert score.income_score > 0


# =============================================================================
# Unit Tests - Filters
# =============================================================================

class TestComparableFilters:
    """Test filter configuration and application"""

    def test_same_zip_filter(self, mock_db):
        """same_zip filter should only return properties in same ZIP"""
        # Create custom mock that applies filters
        finder = ComparableFinder(mock_db, 'TestCounty')

        filters = ComparableFilters(same_zip=True)
        target_residence = {'parcel_zip': 43210, 'living_area_total': 2500}

        query = finder._build_query(target_residence, None, filters)

        assert 'parcel_zip' in query
        assert query['parcel_zip'] == 43210

    def test_sqft_tolerance_filter(self, mock_db):
        """sqft_tolerance should create range query"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        filters = ComparableFilters(sqft_tolerance=500)
        target_residence = {'living_area_total': 2500}

        query = finder._build_query(target_residence, None, filters)

        assert 'living_area_total' in query
        assert query['living_area_total']['$gte'] == 2000
        assert query['living_area_total']['$lte'] == 3000

    def test_story_height_exact_filter(self, mock_db):
        """story_height_exact should match exactly"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        filters = ComparableFilters(story_height_exact=True)
        target_residence = {'story_height': 2.0}

        query = finder._build_query(target_residence, None, filters)

        assert 'story_height' in query
        assert query['story_height'] == 2.0

    def test_age_tolerance_filter(self, mock_db):
        """age_tolerance should create range query"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        filters = ComparableFilters(age_tolerance=10)
        target_residence = {'age': 30}

        query = finder._build_query(target_residence, None, filters)

        assert 'age' in query
        assert query['age']['$gte'] == 20
        assert query['age']['$lte'] == 40

    def test_multiple_filters_combined(self, mock_db):
        """Multiple filters should combine correctly"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        filters = ComparableFilters(
            same_zip=True,
            sqft_tolerance=500,
            story_height_exact=True,
            age_tolerance=10
        )
        target_residence = {
            'parcel_zip': 43210,
            'living_area_total': 2500,
            'story_height': 2.0,
            'age': 30
        }

        query = finder._build_query(target_residence, None, filters)

        assert 'parcel_zip' in query
        assert 'living_area_total' in query
        assert 'story_height' in query
        assert 'age' in query

    def test_tolerance_filter_passes(self, mock_db, mock_residential_data, mock_demographic_data):
        """Test household size tolerance filter"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        filters = ComparableFilters(household_size_tolerance=1)

        target_res = mock_residential_data[0]
        target_demo = mock_demographic_data[0]  # household_size: 4

        # COMP001 has household_size: 4 (diff = 0) - should pass
        comp1_res = mock_residential_data[1]
        comp1_demo = mock_demographic_data[1]
        assert finder._passes_tolerance_filters(target_res, target_demo, comp1_res, comp1_demo, filters)

        # COMP004 has household_size: 2 (diff = 2) - should fail
        comp4_res = mock_residential_data[4]
        comp4_demo = mock_demographic_data[4]
        assert not finder._passes_tolerance_filters(target_res, target_demo, comp4_res, comp4_demo, filters)


# =============================================================================
# Integration Tests
# =============================================================================

class TestComparableFinder:
    """Integration tests for ComparableFinder"""

    def test_find_comparables_basic(self, mock_db, mock_residential_data, mock_demographic_data):
        """Basic comparable search should return results"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        results = finder.find_comparables('TARGET001', n_results=10)

        assert results.target_parcel_id == 'TARGET001'
        assert results.county == 'TestCounty'
        assert len(results.comparables) > 0

    def test_find_comparables_respects_n_results(self, mock_db, mock_residential_data):
        """Should return at most n_results"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        results = finder.find_comparables('TARGET001', n_results=2)

        assert len(results.comparables) <= 2

    def test_find_comparables_excludes_target(self, mock_db, mock_residential_data):
        """Target property should not appear in results"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        results = finder.find_comparables('TARGET001', n_results=10)

        parcel_ids = [c.parcel_id for c in results.comparables]
        assert 'TARGET001' not in parcel_ids

    def test_find_comparables_sorted_by_score(self, mock_db, mock_residential_data):
        """Results should be sorted by similarity score descending"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        results = finder.find_comparables('TARGET001', n_results=10)

        scores = [c.score.overall_score for c in results.comparables]
        assert scores == sorted(scores, reverse=True)

    def test_find_comparables_target_not_found(self, mock_db):
        """Should handle missing target gracefully"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        results = finder.find_comparables('NONEXISTENT', n_results=10)

        assert results.target_parcel_id == 'NONEXISTENT'
        assert len(results.comparables) == 0
        assert results.total_candidates == 0

    def test_find_comparables_with_filters(self, mock_db, mock_residential_data):
        """Filters should constrain results"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        filters = ComparableFilters(same_zip=True)
        results = finder.find_comparables('TARGET001', n_results=10, filters=filters)

        assert results.search_filters_applied.get('same_zip') is True
        # Verify all results have same ZIP as target (43210)
        for comp in results.comparables:
            assert comp.zip_code == 43210

    def test_statistics_calculated(self, mock_db, mock_residential_data, mock_demographic_data):
        """Statistics should be calculated from results"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        results = finder.find_comparables('TARGET001', n_results=10)

        # Stats should be populated if we have results
        if len(results.comparables) > 0:
            assert results.avg_sqft_diff is not None or results.avg_sqft_diff == 0


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_target_not_found_returns_empty(self, mock_db):
        """Should handle missing target gracefully"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        # Search for a parcel that doesn't exist in our mock data
        results = finder.find_comparables('NONEXISTENT_PARCEL', n_results=10)

        assert len(results.comparables) == 0
        assert results.total_candidates == 0

    def test_zero_sqft_handled(self, mock_db):
        """Should handle zero sqft values"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        target = {'living_area_total': 0, 'story_height': 2.0, 'age': 30}
        candidate = {'living_area_total': 2500, 'story_height': 2.0, 'age': 30}

        score = finder._calculate_similarity(target, None, candidate, None)

        # Should not crash, sqft component excluded from scoring
        assert score is not None

    def test_negative_age_excluded_from_scoring(self, mock_db):
        """Should exclude -1 sentinel values from scoring"""
        finder = ComparableFinder(mock_db, 'TestCounty')

        target = {'living_area_total': 2500, 'story_height': 2.0, 'age': 30, 'bedrooms': 4, 'bathrooms': 2}
        candidate = {'living_area_total': 2500, 'story_height': 2.0, 'age': -1, 'bedrooms': 4, 'bathrooms': 2}

        score = finder._calculate_similarity(target, None, candidate, None)

        # age_score should be 0 when candidate has -1 age
        assert score.age_score == 0.0
        # But other scores should still work
        assert score.sqft_score == 1.0
        assert score.story_score == 1.0

    def test_strict_zip_filter(self, mock_db):
        """Should filter strictly by ZIP code when same_zip=True"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        filters = ComparableFilters(same_zip=True)
        results = finder.find_comparables('TARGET001', n_results=10, filters=filters)

        # All results should have same ZIP as target (43210)
        for comp in results.comparables:
            assert comp.zip_code == 43210

    def test_very_narrow_filter_may_return_few_results(self, mock_db):
        """Very strict filters may return few or no results"""
        finder = ComparableFinder(mock_db, 'TestCounty')
        # Very strict filter: exact match on everything
        filters = ComparableFilters(
            same_zip=True,
            sqft_tolerance=50,  # Very tight
            story_height_exact=True,
            age_tolerance=5,
            bedrooms_exact=True
        )
        results = finder.find_comparables('TARGET001', n_results=10, filters=filters)

        # Should not crash, might return few or no results
        assert results is not None


# =============================================================================
# Custom Weights Tests
# =============================================================================

class TestCustomWeights:
    """Test custom scoring weights"""

    def test_custom_weights_applied(self, mock_db, mock_residential_data):
        """Custom weights should affect scoring"""
        # Heavy weight on sqft, ignore everything else
        weights = ScoringWeights(
            sqft_weight=10.0,
            story_weight=0.0,
            age_weight=0.0,
            bedrooms_weight=0.0,
            bathrooms_weight=0.0,
            household_weight=0.0,
            income_weight=0.0
        )

        finder = ComparableFinder(mock_db, 'TestCounty', weights=weights)

        target = mock_residential_data[0]
        similar_sqft = mock_residential_data[1]  # 2400 sqft (100 diff)
        diff_sqft = mock_residential_data[4]  # 1500 sqft (1000 diff)

        score_similar = finder._calculate_similarity(target, None, similar_sqft, None)
        score_diff = finder._calculate_similarity(target, None, diff_sqft, None)

        # With only sqft weighted, similar sqft property should score much higher
        assert score_similar.overall_score > score_diff.overall_score


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
