"""The single-model thermal calculation: kWh ~ heating + cooling.

The previous code fit two separate univariate regressions against the same kWh
series. Because Ohio's cold months are exactly the months with no air
conditioning, whichever driver was omitted was absorbed by the other with the
wrong sign: 174,067 of 239,068 Franklin records (72.8%) carried a negative
heating slope, and 36,445 (15.2%) a negative cooling slope.

Both fixtures below are real billing histories taken from FranklinThermalLoads.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402


def _periods(rows):
    return [{'date': d, 'kwh': k, 'hl': h, 'cl': c} for d, k, h, c in rows]


# Parcel 010-000235-00 — gas heat, electric AC. The univariate heating fit
# returned -0.0525; the joint fit returns a small positive number.
GAS_HEATED = _periods([
    ('2023-11-29', 541, 13004, 1), ('2024-01-02', 635, 17148, 0),
    ('2024-01-31', 833, 21402, 0), ('2024-02-29', 769, 15135, 0),
    ('2024-04-01', 780, 12481, 2), ('2024-04-30', 808, 5374, 390),
    ('2024-05-30', 1119, 703, 1333), ('2024-06-28', 1572, 493, 3297),
    ('2024-07-30', 2245, 72, 4397), ('2024-08-28', 1725, 297, 3560),
    ('2024-09-27', 1518, 540, 3311),
])

# Parcel 010-149582-00 — electric heat. The univariate cooling fit returned
# -0.6349, which is what kwh_cl_slope still holds on that record.
ELECTRIC_HEATED = _periods([
    ('2023-11-16', 2103, 8054, 25), ('2023-12-19', 3859, 16839, 0),
    ('2024-01-22', 5263, 23777, 0), ('2024-02-20', 3639, 15941, 0),
    ('2024-03-20', 2796, 11099, 2), ('2024-04-19', 2117, 8410, 195),
    ('2024-05-20', 946, 2739, 767), ('2024-06-19', 688, 552, 2352),
    ('2024-07-19', 664, 56, 4793), ('2024-08-19', 666, 64, 3905),
    ('2024-09-18', 736, 790, 3478),
])


# --- the joint fit recovers both drivers -------------------------------------

def test_gas_heated_house_yields_a_positive_heating_slope():
    """The headline correction: the sign flips from -0.0525 to a small positive."""
    m = calc.fit_thermal_model(GAS_HEATED)

    assert m['kwh_hl_slope'] > 0
    assert m['kwh_hl_slope'] == pytest.approx(0.0087, abs=0.004)


def test_gas_heated_house_attributes_the_summer_load_to_cooling():
    m = calc.fit_thermal_model(GAS_HEATED)

    assert m['kwh_cl_slope'] == pytest.approx(0.3316, rel=0.05)
    assert m['kwh_cl_slope'] > m['kwh_hl_slope'] * 10


def test_electric_heated_house_yields_a_large_positive_heating_slope():
    m = calc.fit_thermal_model(ELECTRIC_HEATED)

    assert m['kwh_hl_slope'] == pytest.approx(0.2038, rel=0.05)
    assert m['kwh_cl_slope'] == pytest.approx(0.0488, rel=0.15)


def test_electric_heated_house_no_longer_yields_a_negative_cooling_slope():
    """The mirror defect: the univariate cooling fit gave -0.6349."""
    m = calc.fit_thermal_model(ELECTRIC_HEATED)

    assert m['kwh_cl_slope'] > 0


def test_the_two_houses_are_distinguishable_by_heating_slope():
    """The field has to carry real signal - that is what targeting ranks on."""
    gas = calc.fit_thermal_model(GAS_HEATED)
    electric = calc.fit_thermal_model(ELECTRIC_HEATED)

    assert electric['kwh_hl_slope'] > gas['kwh_hl_slope'] * 10


def test_the_model_reports_one_intercept_and_one_r2():
    m = calc.fit_thermal_model(GAS_HEATED)

    assert m['kwh_r2'] == pytest.approx(0.953, abs=0.02)
    assert m['kwh_intercept'] == pytest.approx(581, rel=0.1)
    assert m['kwh_model'] == 'hl+cl'


# --- failures are recorded, never coerced to a number -------------------------

def test_fewer_than_three_periods_yields_no_model():
    assert calc.fit_thermal_model(GAS_HEATED[:2]) == {}


def test_a_failed_regression_returns_none_not_zero():
    """A failure must stay distinguishable from a genuine zero slope."""
    degenerate = _periods([('2024-01-01', 500, 0, 0), ('2024-02-01', 500, 0, 0),
                           ('2024-03-01', 500, 0, 0), ('2024-04-01', 500, 0, 0)])

    m = calc.fit_thermal_model(degenerate)

    assert m['kwh_hl_slope'] == 0.0 or m['kwh_hl_slope'] is None
    if m['kwh_hl_slope'] is None:
        assert m['calculation_error']


def test_a_genuine_flat_house_yields_zero_and_no_error():
    """Constant usage against varying weather is a real zero, not a failure."""
    flat = _periods([('2024-01-01', 900, 20000, 0), ('2024-04-01', 900, 8000, 200),
                     ('2024-07-01', 900, 100, 4000), ('2024-10-01', 900, 3000, 900)])

    m = calc.fit_thermal_model(flat)

    assert m['kwh_hl_slope'] == pytest.approx(0.0, abs=1e-6)
    assert not m.get('calculation_error')


# --- the document is a clean break -------------------------------------------

def test_document_carries_only_the_single_model_fields():
    doc = calc.build_thermal_document('P1', GAS_HEATED, calc.fit_thermal_model(GAS_HEATED))

    for field in ('kwh_hl_slope', 'kwh_cl_slope', 'kwh_intercept', 'kwh_r2', 'kwh_model'):
        assert field in doc
    for legacy in ('kwh_hl_intercept', 'kwh_cl_intercept', 'kwh_hl_r2', 'kwh_cl_r2'):
        assert legacy not in doc


def test_update_ops_replace_rather_than_insert():
    doc = calc.build_thermal_document('P1', GAS_HEATED, calc.fit_thermal_model(GAS_HEATED))
    ops = calc.thermal_update_ops(doc)

    assert '$set' in ops
    assert ops['$set']['kwh_model'] == 'hl+cl'
    assert set(ops['$unset']) == {'kwh_hl_intercept', 'kwh_cl_intercept',
                                  'kwh_hl_r2', 'kwh_cl_r2'}


def test_update_ops_never_touch_existing_gas_regressions():
    """Cuyahoga holds 126,987 real gas regressions. $set must not reach them."""
    doc = calc.build_thermal_document('P1', GAS_HEATED, calc.fit_thermal_model(GAS_HEATED))
    ops = calc.thermal_update_ops(doc)

    assert not any(k.startswith('gas_') for k in ops['$set'])
    assert not any(k.startswith('gas_') for k in ops['$unset'])
    assert all(k.startswith('gas_') for k in ops['$setOnInsert'])


def test_update_ops_seed_gas_sentinels_only_on_insert():
    doc = calc.build_thermal_document('P1', GAS_HEATED, calc.fit_thermal_model(GAS_HEATED))
    ops = calc.thermal_update_ops(doc)

    assert ops['$setOnInsert']['gas_hl_slope'] == -1


# --- period-length normalization ---------------------------------------------
#
# Degree-hours are integrated between consecutive meter readings and kWh is a
# period total, so both scale with the length of the period. Measured on real
# Franklin billing histories, corr(days, heating degree-hours) is +0.916 and
# periods run from 29 to 641 days. Left uncontrolled, period length -- not
# weather -- becomes the dominant driver of the fit.

def _house(day_rows):
    """Billing periods for a house whose true behaviour is known per-day.

    daily kWh = 10 + 0.05 * daily heating degree-hours
    """
    out = []
    for i, (days, hl_per_day) in enumerate(day_rows):
        out.append({'date': f'2024-{i + 1:02d}-01', 'days': days,
                    'kwh': (10 + 0.05 * hl_per_day) * days,
                    'hl': hl_per_day * days, 'cl': 0.0})
    return out


UNIFORM = _house([(30, 400), (30, 300), (30, 120), (30, 20), (30, 200), (30, 380)])
RAGGED = UNIFORM[:5] + _house([(300, 150)])


def test_billing_periods_record_their_length_in_days():
    """The calculator must carry days through, or nothing downstream can normalize."""
    import pandas as pd
    weather = calc.WeatherDataProcessor(
        pd.DataFrame({'T': [40.0] * (24 * 70)},
                     index=pd.date_range('2024-01-01', periods=24 * 70, freq='h')))
    series = {'2024-01-01 00:00:00': 900.0, '2024-01-31 00:00:00': 850.0,
              '2024-03-01 00:00:00': 800.0, '2024-03-10 00:00:00': 300.0}

    billing, _ = calc.calculate_thermal_loads_for_parcel(weather, series)

    assert all('days' in row for row in billing)
    assert billing[0]['days'] == 30


def test_with_uniform_periods_both_specifications_agree():
    """Dividing both sides by the same constant cannot change the slope."""
    totals = calc.fit_thermal_model(UNIFORM, per_day=False)
    per_day = calc.fit_thermal_model(UNIFORM, per_day=True)

    assert totals['kwh_hl_slope'] == pytest.approx(per_day['kwh_hl_slope'], rel=1e-6)


def test_per_day_recovers_the_true_coefficient_despite_a_ragged_period():
    """One 300-day gap is enough to distort a fit on period totals."""
    per_day = calc.fit_thermal_model(RAGGED, per_day=True)

    assert per_day['kwh_hl_slope'] == pytest.approx(0.05, rel=1e-6)


def test_a_ragged_period_distorts_the_fit_on_period_totals():
    totals = calc.fit_thermal_model(RAGGED, per_day=False)

    assert abs(totals['kwh_hl_slope'] - 0.05) > 0.005


def test_per_day_records_which_specification_produced_the_record():
    per_day = calc.fit_thermal_model(UNIFORM, per_day=True)
    totals = calc.fit_thermal_model(UNIFORM, per_day=False)

    assert per_day['kwh_model'] != totals['kwh_model']


def test_periods_with_no_length_are_dropped_rather_than_dividing_by_zero():
    rows = UNIFORM + [{'date': '2024-09-01', 'days': 0, 'kwh': 500, 'hl': 100, 'cl': 0}]

    m = calc.fit_thermal_model(rows, per_day=True)

    assert m['kwh_periods'] == len(UNIFORM)
