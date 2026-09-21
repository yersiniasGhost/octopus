"""Billing periods that are actually gaps in the data.

time_series_elec holds monthly meter readings. The calculator pairs consecutive
readings, taking kWh from the FIRST date and integrating degree-hours across the
span to the SECOND. When a reading is missing the span can be years wide, and
the row then pairs one month's kWh with a multi-year weather total.

Real example, Cuyahoga parcel 30324005: a 2,369-day span carrying 471 kWh and
738,887 heating degree-hours -- 36x the largest legitimate value in that same
parcel's history. Dropping 4 such rows out of 39 flips its heating coefficient
from -0.00637 to +0.00565. These rows are not long billing periods; they are
absent data wearing a period's clothes.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402


def _cold_weather(days=1200):
    """A constant 40F so heating degree-hours accrue steadily and predictably."""
    hours = days * 24
    return calc.WeatherDataProcessor(
        pd.DataFrame({'T': [40.0] * hours},
                     index=pd.date_range('2015-01-01', periods=hours, freq='h')))


def _series(*pairs):
    return {date: kwh for date, kwh in pairs}


def test_a_multi_year_span_is_dropped_rather_than_fitted():
    series = _series(('2015-01-05 00:00:00', 500.0), ('2015-02-04 00:00:00', 520.0),
                     ('2015-03-06 00:00:00', 480.0),
                     ('2017-06-01 00:00:00', 510.0),   # 818-day gap
                     ('2017-07-01 00:00:00', 495.0))

    billing, _ = calc.calculate_thermal_loads_for_parcel(_cold_weather(), series)

    assert all(row['days'] <= calc.PERIOD_MAX_DAYS for row in billing)
    assert not any(row['days'] > 100 for row in billing)


def test_ordinary_monthly_periods_are_kept():
    series = _series(('2015-01-05 00:00:00', 500.0), ('2015-02-04 00:00:00', 520.0),
                     ('2015-03-06 00:00:00', 480.0), ('2015-04-05 00:00:00', 460.0))

    billing, _ = calc.calculate_thermal_loads_for_parcel(_cold_weather(), series)

    assert len(billing) == 3
    assert all(28 <= row['days'] <= 31 for row in billing)


def test_a_span_beyond_the_tolerance_is_dropped_even_if_it_looks_plausible():
    """A 60-day span still pairs one month's kWh with two months of weather."""
    series = _series(('2015-01-05 00:00:00', 500.0), ('2015-03-06 00:00:00', 520.0),
                     ('2015-04-05 00:00:00', 480.0), ('2015-05-05 00:00:00', 470.0))

    billing, _ = calc.calculate_thermal_loads_for_parcel(_cold_weather(), series)

    assert all(row['days'] <= calc.PERIOD_MAX_DAYS for row in billing)


def test_an_implausibly_short_span_is_also_dropped():
    """Two readings three days apart cannot both be monthly totals."""
    series = _series(('2015-01-05 00:00:00', 500.0), ('2015-01-08 00:00:00', 12.0),
                     ('2015-02-07 00:00:00', 520.0), ('2015-03-09 00:00:00', 480.0),
                     ('2015-04-08 00:00:00', 460.0))

    billing, _ = calc.calculate_thermal_loads_for_parcel(_cold_weather(), series)

    assert all(row['days'] >= calc.PERIOD_MIN_DAYS for row in billing)


def test_dropped_periods_are_counted_never_silent():
    series = _series(('2015-01-05 00:00:00', 500.0), ('2015-02-04 00:00:00', 520.0),
                     ('2015-03-06 00:00:00', 480.0), ('2015-04-05 00:00:00', 460.0),
                     ('2017-06-01 00:00:00', 510.0), ('2017-07-01 00:00:00', 495.0))

    _, model = calc.calculate_thermal_loads_for_parcel(_cold_weather(), series)

    assert model['kwh_periods_dropped'] == 1


def test_a_parcel_left_with_too_few_valid_periods_yields_no_model():
    """Gaps must not be replaced by a fit on one or two surviving rows."""
    series = _series(('2015-01-05 00:00:00', 500.0),
                     ('2016-06-01 00:00:00', 520.0),
                     ('2017-11-01 00:00:00', 480.0),
                     ('2017-12-01 00:00:00', 495.0))

    _, model = calc.calculate_thermal_loads_for_parcel(_cold_weather(), series)

    assert model == {}


def test_the_tolerance_matches_a_monthly_read_cycle():
    assert calc.PERIOD_MIN_DAYS >= 20
    assert calc.PERIOD_MAX_DAYS <= 45
    assert calc.PERIOD_MIN_DAYS < 30 < calc.PERIOD_MAX_DAYS
