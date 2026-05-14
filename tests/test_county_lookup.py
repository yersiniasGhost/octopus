"""Tests for the ZIP → county lookup utility.

Uses a small in-memory cache stub instead of the real JSON file so the tests
stay fast and independent of the production data.
"""
import pytest

from src.utils import county_lookup


@pytest.fixture(autouse=True)
def _stub_cache(monkeypatch):
    """Replace the real cache with a tiny deterministic map for each test."""
    primary = {
        '43204': 'Franklin',
        '43227': 'Franklin',
        '43302': 'Marion',
        '43907': 'Harrison',
        '44813': 'Huron',  # primary mapping (cache built first); also belongs to Richland
    }
    multi = {
        '44813': frozenset({'Huron', 'Richland'}),
    }
    monkeypatch.setattr(county_lookup, '_zipcode_map', primary)
    monkeypatch.setattr(county_lookup, '_multi_county', multi)
    yield
    county_lookup.reset_cache()


class TestLookupCounty:
    def test_known_zip(self):
        assert county_lookup.lookup_county('43204') == 'Franklin'

    def test_zip_plus_four(self):
        assert county_lookup.lookup_county('43204-1234') == 'Franklin'

    def test_short_zip_zero_pads(self):
        # zfill behavior — pads "5302" to "05302" (a real Massachusetts ZIP).
        # Not in our stubbed map → None, but the padding code path executes.
        assert county_lookup.lookup_county('5302') is None

    def test_unknown_zip(self):
        assert county_lookup.lookup_county('99999') is None

    @pytest.mark.parametrize('bad', [None, '', '   '])
    def test_empty_inputs_return_none(self, bad):
        assert county_lookup.lookup_county(bad) is None

    def test_strips_surrounding_whitespace(self):
        assert county_lookup.lookup_county('  43302  ') == 'Marion'

    def test_non_string_zip(self):
        assert county_lookup.lookup_county(43907) == 'Harrison'


class TestSuffixStripping:
    """Verifies the production cache shape is normalized correctly."""

    def test_loader_strips_county_suffix(self, monkeypatch, tmp_path):
        # Bypass the autouse stub and exercise the real _load path.
        county_lookup.reset_cache()
        cache_file = tmp_path / 'cache.json'
        cache_file.write_text(
            '{"zipcode_map": {"43204": "FranklinCounty", "43302": "MarionCounty"},'
            ' "multi_county": {"44813": ["HuronCounty", "RichlandCounty"]}}'
        )
        monkeypatch.setattr(county_lookup, '_CACHE_PATH', cache_file)
        monkeypatch.setattr(county_lookup, '_zipcode_map', None)
        monkeypatch.setattr(county_lookup, '_multi_county', None)

        assert county_lookup.lookup_county('43204') == 'Franklin'
        assert county_lookup.lookup_county('43302') == 'Marion'
        assert county_lookup.candidate_counties('44813') == frozenset({'Huron', 'Richland'})


class TestCandidateAndPlausibility:
    def test_single_county_zip_returns_singleton(self):
        assert county_lookup.candidate_counties('43204') == frozenset({'Franklin'})

    def test_multi_county_zip_returns_all(self):
        assert county_lookup.candidate_counties('44813') == frozenset({'Huron', 'Richland'})

    def test_unmappable_zip_returns_empty(self):
        assert county_lookup.candidate_counties('99999') == frozenset()

    def test_is_plausible_for_primary_match(self):
        assert county_lookup.is_plausible_county('43204', 'Franklin') is True

    def test_is_plausible_for_multi_county_alternate(self):
        # 'Richland' is a valid candidate for 44813 even though primary is 'Huron'
        assert county_lookup.is_plausible_county('44813', 'Richland') is True

    def test_is_implausible_when_county_not_in_set(self):
        assert county_lookup.is_plausible_county('43302', 'San Diego') is False

    @pytest.mark.parametrize('county', [None, ''])
    def test_is_implausible_for_empty_county(self, county):
        assert county_lookup.is_plausible_county('43204', county) is False


class TestResolveCounty:
    """Real-world resolution: keep plausible existing values, otherwise use primary."""

    def test_keeps_plausible_existing(self):
        # User said Richland for a Huron-primary multi-county ZIP — respect it
        assert county_lookup.resolve_county('44813', 'Richland') == 'Richland'

    def test_overwrites_impossible_existing(self):
        # 'San Diego' is not a candidate for 43302 → use primary 'Marion'
        assert county_lookup.resolve_county('43302', 'San Diego') == 'Marion'

    def test_fills_null_existing(self):
        assert county_lookup.resolve_county('43204', None) == 'Franklin'

    def test_returns_none_when_zip_unmappable(self):
        assert county_lookup.resolve_county('99999', None) is None

    def test_returns_none_when_zip_unmappable_even_with_existing(self):
        # ZIP not in cache → can't validate user's value → return None to defer
        # to caller (which can keep existing if it wants).
        assert county_lookup.resolve_county('99999', 'Whatever') is None
