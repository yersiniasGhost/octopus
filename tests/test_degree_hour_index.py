"""Precomputed cumulative degree-hours, and its equivalence to the per-period loop.

heating_load/cooling_load integrated by walking the hourly weather rows inside
each billing period with DataFrame.iterrows(). Every parcel in a county re-walked
the same shared county series, ~21 billing periods x 2 thresholds deep: measured
at 98% of the T-15 recompute's runtime, and ~24 billion row visits across 794,636
parcels over 25 county tables holding 2.6 million rows between them.

The clipping has to happen hourly -- degree-hours count only hours past the base
temperature, and clipping does not commute with averaging, so period-level
temperature would change the physics. But it only has to happen ONCE per county.
Each hourly pair's contribution is a fixed quantity; cumulative-sum them and any
period's degree-hours is a difference of two entries.

These tests pin the cumulative index and, critically, pin it against a reference
copy of the original loop -- including the two quirks the original has and the
replacement must keep: a pair accrues only when BOTH endpoints are past the
threshold, and a NaN row is transparent to the pairing rather than breaking it.

Hand-checked integration cases for heating_load/cooling_load themselves live in
tests/test_thermal_weather_selection.py and are not repeated here.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402


def processor(temps, start='2026-01-05', freq='h'):
    return calc.WeatherDataProcessor(
        pd.DataFrame({'T': temps},
                     index=pd.date_range(start, periods=len(temps), freq=freq)))


def reference_load(proc, start, end, threshold, heating):
    """The original iterrows loop, verbatim in behaviour. The specification.

    Kept here so the replacement is pinned against what it replaced, not against
    a restatement of what it was believed to do.
    """
    tdf = proc.weather[(proc.weather.index >= start) & (proc.weather.index <= end)]
    if len(tdf) < 2:
        return 0.0
    integral = 0.0
    prev_temp = None
    in_period = False
    for _idx, row in tdf.iterrows():
        temp = row['T']
        if pd.isna(temp):
            continue
        past = temp <= threshold if heating else temp > threshold
        if past:
            if prev_temp is not None and in_period:
                avg = (temp + prev_temp) / 2
                integral += (threshold - avg) * proc.dt if heating else (avg - threshold) * proc.dt
            in_period = True
        else:
            in_period = False
        prev_temp = temp
    return max(0.0, integral)


# --- the cumulative index itself ---------------------------------------------

def test_cumulative_index_starts_at_zero_and_spans_every_non_nan_row():
    """One entry per non-NaN row, so entry i is the total over the first i pairs."""
    proc = processor([52.0, 52.0, np.nan, 52.0])

    cum = proc.cumulative_degree_hours(62.0, 'heating')

    assert cum[0] == 0.0
    assert len(cum) == 3


def test_flat_sub_threshold_series_accrues_a_constant_amount_per_pair():
    """24 hourly readings at 52F, base 62F: each pair contributes 10F x 1h."""
    proc = processor([52.0] * 24)

    cum = proc.cumulative_degree_hours(62.0, 'heating')

    assert cum[1] == pytest.approx(10.0)
    assert cum[23] == pytest.approx(230.0)


def test_a_warm_hour_breaks_the_run_so_its_pairs_contribute_nothing():
    """Series 60,60,70,60,60 at base 62: only the 60-60 pairs accrue, 2.0 each."""
    proc = processor([60.0, 60.0, 70.0, 60.0, 60.0])

    cum = proc.cumulative_degree_hours(62.0, 'heating')

    assert np.diff(cum).tolist() == pytest.approx([2.0, 0.0, 0.0, 2.0])


def test_a_nan_row_is_transparent_to_the_pairing():
    """60, NaN, 60 at base 62 accrues one pair, exactly as the original loop did.

    The original `continue`d on NaN without resetting prev_temp or the in-period
    flag, so the readings either side of a gap pair with each other and the gap
    contributes a single dt regardless of its true length. Preserved deliberately:
    changing it would move every slope in the database.
    """
    proc = processor([60.0, np.nan, 60.0])

    cum = proc.cumulative_degree_hours(62.0, 'heating')

    assert cum[-1] == pytest.approx(2.0)


def test_cooling_uses_a_strict_comparison_against_the_base():
    """Heating counts temp <= base; cooling counts temp > base. 72F is not cooling."""
    proc = processor([72.0, 72.0])

    assert proc.cumulative_degree_hours(72.0, 'cooling')[-1] == pytest.approx(0.0)


def test_index_is_built_once_and_reused():
    """The whole point: one pass per county, not one per billing period."""
    proc = processor([52.0] * 24)

    first = proc.cumulative_degree_hours(62.0, 'heating')
    second = proc.cumulative_degree_hours(62.0, 'heating')

    assert first is second


def test_separate_thresholds_get_separate_indexes():
    proc = processor([52.0] * 24)

    assert proc.cumulative_degree_hours(62.0, 'heating') is not \
        proc.cumulative_degree_hours(65.0, 'heating')


def test_unknown_mode_is_rejected():
    proc = processor([52.0] * 24)

    with pytest.raises(ValueError):
        proc.cumulative_degree_hours(62.0, 'sideways')


# --- equivalence with the loop it replaces -----------------------------------

def realistic_series(n=2000, seed=11):
    """Hourly temperatures that cross both bases repeatedly, with gaps."""
    rng = np.random.default_rng(seed)
    hours = np.arange(n)
    seasonal = 50 + 25 * np.sin(2 * np.pi * hours / (24 * 365))
    daily = 10 * np.sin(2 * np.pi * hours / 24)
    temps = seasonal + daily + rng.normal(0, 3, n)
    temps[rng.choice(n, size=n // 50, replace=False)] = np.nan   # scattered gaps
    return temps


@pytest.mark.parametrize('heating,threshold', [(True, 62.0), (False, 72.0)])
def test_matches_the_original_loop_across_many_windows(heating, threshold):
    proc = processor(realistic_series())
    index = proc.weather.index
    starts = pd.date_range(index.min(), index.max() - pd.Timedelta(days=5), periods=60)

    for start in starts:
        end = start + pd.Timedelta(days=3)
        expected = reference_load(proc, start, end, threshold, heating)
        actual = (proc.heating_load(start, end, threshold) if heating
                  else proc.cooling_load(start, end, threshold))
        assert actual == pytest.approx(expected, abs=1e-6), f"window {start}"


def test_matches_the_original_loop_on_a_window_shorter_than_two_readings():
    proc = processor(realistic_series())
    start = proc.weather.index[5]

    assert proc.heating_load(start, start) == reference_load(proc, start, start, 62.0, True)


def test_matches_the_original_loop_outside_the_covered_range():
    proc = processor(realistic_series())
    start, end = pd.Timestamp('2030-01-01'), pd.Timestamp('2030-02-01')

    assert proc.heating_load(start, end) == reference_load(proc, start, end, 62.0, True)
