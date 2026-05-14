"""Unit tests for income normalization in src/utils/application_parsers.py.

Covers existing behavior (plain numbers, currency, monthly, European,
malformed thousands seps) plus the post-2026-04-27 fixes:
- Range parsing returns the midpoint
- Multi-token raw input is refused (no silent digit concatenation)
"""
import pytest

from src.utils.application_parsers import normalize_income


class TestNormalizeIncomeExistingBehavior:
    @pytest.mark.parametrize("raw,expected", [
        ("35000", 35000.0),
        ("35,000", 35000.0),
        ("$100,000", 100000.0),
        ("28.000", 28000.0),         # European thousands separator
        ("100,00.00", 10000.0),      # Misplaced comma — first valid float wins
        ("36, 000", 36000.0),        # Comma + whitespace typo
    ])
    def test_plain_and_malformed_numerics(self, raw, expected):
        amount, returned_raw = normalize_income(raw)
        assert amount == pytest.approx(expected)
        assert returned_raw == raw

    @pytest.mark.parametrize("raw,expected_annual", [
        ("1850mo", 22200.0),
        ("1850/mo", 22200.0),
        ("1850 per month", 22200.0),
        ("1850 monthly", 22200.0),
        ("894.60 month", 10735.20),  # regression: 'mo\b' fails inside 'month'
        ("$2,500/month", 30000.0),
    ])
    def test_monthly_converts_to_annual(self, raw, expected_annual):
        amount, _ = normalize_income(raw)
        assert amount == pytest.approx(expected_annual)

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_empty_inputs_return_none(self, raw):
        assert normalize_income(raw) == (None, None)

    def test_zero_string(self):
        assert normalize_income("0") == (0.0, "0")


class TestNormalizeIncomeRanges:
    @pytest.mark.parametrize("raw,expected_midpoint", [
        ("21,000-22,000", 21500.0),
        ("21000-22000", 21500.0),
        ("21,000 - 22,000", 21500.0),
        ("$40,000-$50,000", 45000.0),
        ("21000 to 22000", 21500.0),
        ("21,000–22,000", 21500.0),  # en-dash
        ("21,000—22,000", 21500.0),  # em-dash
    ])
    def test_range_returns_midpoint(self, raw, expected_midpoint):
        amount, _ = normalize_income(raw)
        assert amount == pytest.approx(expected_midpoint)

    def test_range_with_monthly_suffix(self):
        # "$1,500-$2,000 mo" → midpoint 1750/mo → 21000/yr
        amount, _ = normalize_income("$1,500-$2,000 mo")
        assert amount == pytest.approx(21000.0)

    def test_inverted_range_falls_through(self):
        # high < low → not treated as a range; falls to multi-token rejection
        amount, raw = normalize_income("50000-10000")
        assert amount is None
        assert raw == "50000-10000"


class TestNormalizeIncomeKSuffix:
    @pytest.mark.parametrize("raw,expected", [
        ("50k", 50000.0),
        ("$50K", 50000.0),
        ("75k", 75000.0),
    ])
    def test_k_suffix_single_value(self, raw, expected):
        amount, _ = normalize_income(raw)
        assert amount == pytest.approx(expected)

    @pytest.mark.parametrize("raw,expected_midpoint", [
        ("$55k-$75k", 65000.0),
        ("Between 55-75k", 65000.0),  # k on right propagates to left
        ("50k-100k", 75000.0),
        ("$40k to $60k", 50000.0),
    ])
    def test_k_suffix_range(self, raw, expected_midpoint):
        amount, _ = normalize_income(raw)
        assert amount == pytest.approx(expected_midpoint)


class TestNormalizeIncomeAmbiguous:
    """Free-text with multiple disjoint numbers is refused, not concatenated."""

    @pytest.mark.parametrize("raw", [
        "1200 and$1245 $45",
        "approx 50000 or maybe 60000",
        "12 34 56",
    ])
    def test_multiple_tokens_return_none(self, raw):
        amount, returned_raw = normalize_income(raw)
        assert amount is None
        assert returned_raw == raw

    def test_no_numerics_returns_none(self):
        amount, raw = normalize_income("not sure")
        assert amount is None
        assert raw == "not sure"
