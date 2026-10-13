"""One meter plus whatever parcel documents matched it -> one sparse household document."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.household import ParcelMatch, assemble  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from tests.analysis_fakes import elec, monthly_series  # noqa: E402

REG = load_registry()
BM = 202610
FULL_YEAR = monthly_series(2025, 8, [900.0] * 11 + [1800.0])
STALE_YEAR = monthly_series(2015, 3, [700.0] * 12)


def _linked(**parcels):
    return ParcelMatch(linked=True, meters_on_parcel=1, **parcels)


def _doc(meter, match, county='Franklin'):
    return assemble(meter, match, county, BM, REG).doc


def test_unlinked_meter_is_usage_only():
    doc = _doc(elec('E1', FULL_YEAR, utility='AEP'), ParcelMatch(), 'Adams')
    assert doc['link'] == 1 and 'parcel_key' not in doc and 'multi_unit' not in doc
    assert (doc['annual_kwh'], doc['months_usage'], doc['last_read']) == (11700, 12, 202607)
    assert doc['annual_cost'] == int(round(11700 * 0.18972406)) and doc['burden_basis'] == 0
    assert 'energy_burden' not in doc and 'fpl_pct' not in doc and 'missing' not in doc


def test_meter_without_utility_uses_county_default_rate():
    doc = _doc(elec('E1', FULL_YEAR), ParcelMatch(), 'Cuyahoga')
    assert doc['annual_cost'] == int(round(11700 * 0.16217686))


def test_income_and_size_give_fpl_and_ami():
    demo = {'parcel_key': 'P1', 'estimated_income': 42000.0, 'md_householdsize': 3.0}
    doc = _doc(elec('E2', FULL_YEAR, parcel_key='P1'), _linked(demographic=demo))
    assert doc['fpl_pct'] == round(100 * 42000 / 27320) == 154
    assert doc['ami_pct'] == round(80 * 42000 / 80300) == 42
    assert doc['link'] == 1 | 4 and doc['parcel_key'] == 'P1' and doc['multi_unit'] is False


def test_household_size_nine_extends_both_tables():
    demo = {'estimated_income': 60000.0, 'md_householdsize': 9.0}
    doc = _doc(elec('E3', FULL_YEAR, parcel_id='9'), _linked(demographic=demo))
    assert doc['fpl_pct'] == round(100 * 60000 / (55720 + 5680))
    assert doc['ami_pct'] == round(80 * 60000 / (117750 + 89200 * 0.08))


def test_missing_household_size_leaves_income_unknown():
    demo = {'estimated_income': 42000.0, 'md_householdsize': -1.0}
    doc = _doc(elec('E4', FULL_YEAR, parcel_id='4'), _linked(demographic=demo))
    assert 'hh_size' not in doc and 'fpl_pct' not in doc and 'ami_pct' not in doc
    assert doc['income_est'] == 42000 and 2 in doc['missing']


def test_nan_income_is_blank_not_zero():
    demo = {'estimated_income': math.nan, 'md_householdsize': 2.0, 'poverty_level_percent': 0.0}
    doc = _doc(elec('E5', FULL_YEAR, parcel_id='5'), _linked(demographic=demo), 'Cuyahoga')
    assert 'income_est' not in doc and 'energy_burden' not in doc and 1 in doc['missing']


def test_vendor_cost_wins_and_ignores_staleness():
    demo = {'estimated_income': 42000.0, 'md_householdsize': 3.0, 'annual_kwh_cost': 1720.4}
    doc = _doc(elec('E6', STALE_YEAR, parcel_id='6'), _linked(demographic=demo))
    assert (doc['annual_cost'], doc['burden_basis'], doc['energy_burden']) == (1720, 1, 4.1)
    assert 'vendor_kwh_cost' not in doc


def test_stale_meter_gets_no_computed_cost():
    doc = _doc(elec('E7', STALE_YEAR, utility='AEP'), ParcelMatch(), 'Adams')
    assert doc['annual_kwh'] == 8400 and doc['last_read'] == 201602
    assert 'annual_cost' not in doc and 'burden_basis' not in doc


THERMAL = {'kwh_hl_slope': 0.142, 'kwh_cl_slope': 0.311, 'kwh_r2': 0.82}
RESIDENTIAL = {'living_area_total': 1510.0, 'age': 1958, 'story_height': 1.0, 'heat_type': 'FHA'}


def test_thermal_and_sqft_give_hl_per_sqft():
    doc = _doc(elec('E8', FULL_YEAR, parcel_id='8'), _linked(residential=RESIDENTIAL, thermal=THERMAL))
    assert doc['hl_per_sqft'] == round(0.142 / 1510, 8)
    assert (doc['year_built'], doc['sqft'], doc['stories'], doc['thermal_r2']) == (1958, 1510, 1.0, 0.82)
    assert 'heat_fuel' not in doc and doc['link'] == 1 | 2 | 8


def test_multi_meter_parcel_drops_thermal_but_keeps_link_bit():
    match = ParcelMatch(linked=True, meters_on_parcel=2, residential=RESIDENTIAL, thermal=THERMAL)
    doc = _doc(elec('E9', FULL_YEAR, parcel_id='9'), match)
    assert doc['multi_unit'] is True and doc['link'] & 8
    assert 'hl_slope' not in doc and 'hl_per_sqft' not in doc


def test_single_meter_linked_parcel_is_not_multi_unit():
    doc = _doc(elec('E10', FULL_YEAR, parcel_id='10'), _linked())
    assert doc['multi_unit'] is False


def test_heat_pump_is_measured_electric():
    doc = _doc(elec('E11', FULL_YEAR, parcel_id='11'), _linked(residential={'heat_type': 'HTP'}), 'Cuyahoga')
    assert doc['heat_fuel'] == 1


def test_md_blank_falls_back_and_unmapped_values_are_reported():
    demo = {'md_presence_of_senior': '', 'presence_of_senior': 'Yes', 'md_own_rent': 'Maybe'}
    result = assemble(elec('E12', FULL_YEAR, parcel_id='12'), _linked(demographic=demo), 'Franklin', BM, REG)
    assert result.doc['senior'] is True and 'owner' not in result.doc
    assert result.unmapped_values == [('owner', 'Maybe')]
    assert 22 not in result.doc.get('missing', [])
