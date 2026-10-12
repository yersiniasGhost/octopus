"""A meter's time series -> how much of a year we have, when it last read, and its annual total."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.usage import is_fresh, months_between, summarize_usage  # noqa: E402
from tests.analysis_fakes import monthly_series  # noqa: E402


def _summary(series):
    return summarize_usage(series, 300, 400)


def test_full_year_gives_annual_total_and_peak_ratio():
    usage = _summary(monthly_series(2025, 8, [900.0] * 11 + [1800.0]))
    assert usage.annual_kwh == 11700 and usage.months_usage == 12 and usage.last_read == 202607
    assert usage.peak_ratio == round(1800 / (11700 / 12), 2)


def test_only_the_latest_twelve_readings_count():
    usage = _summary(monthly_series(2024, 8, [100.0] * 12 + [500.0] * 12))
    assert usage.annual_kwh == 6000 and usage.last_read == 202607


def test_partial_year_has_no_annual_total():
    usage = _summary(monthly_series(2026, 1, [400.0] * 7))
    assert usage.months_usage == 7 and usage.annual_kwh is None and usage.peak_ratio is None


def test_twelve_readings_spread_over_a_gap_have_no_annual_total():
    series = monthly_series(2023, 1, [400.0] * 6)
    series.update(monthly_series(2025, 1, [400.0] * 6))
    assert _summary(series).annual_kwh is None


def test_bad_readings_are_dropped():
    series = monthly_series(2025, 8, [900.0] * 12)
    series['2026-07-15 00:00:00'] = float('nan')
    series['not a date'] = 5.0
    series['2026-06-15 00:00:00'] = -40.0
    usage = _summary(series)
    assert usage.annual_kwh is None and usage.months_usage == 10


def test_empty_series():
    assert _summary({}) == _summary(None)
    assert _summary({}).months_usage == 0 and _summary({}).last_read is None


def test_stale_meter_is_summarized_but_not_fresh():
    usage = _summary(monthly_series(2015, 3, [700.0] * 12))
    assert usage.annual_kwh == 8400 and usage.last_read == 201602
    assert months_between(201602, 202610) == 128
    assert not is_fresh(usage.last_read, 202610, 24)
    assert is_fresh(202607, 202610, 24) and is_fresh(202410, 202610, 24) and not is_fresh(None, 202610, 24)
