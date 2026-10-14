"""One meter plus whatever parcel documents matched it -> one sparse household document."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.household import ParcelMatch, assemble  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.rules import Distributions, finalize  # noqa: E402
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
    assert doc['fpl_pct'] == math.ceil(100 * 60000 / (55720 + 5680))
    assert doc['ami_pct'] == math.ceil(80 * 60000 / (117750 + 89200 * 0.08))


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
    assert (doc['annual_cost'], doc['burden_basis'], doc['energy_burden']) == (1720, 1, 4.0)
    assert 'vendor_kwh_cost' not in doc


def test_percents_store_so_integer_thresholds_classify_exactly():
    reg_rules = REG.rules
    dist = Distributions.from_values([], [])
    demo = {'estimated_income': 47865.0, 'md_householdsize': 3.0, 'annual_kwh_cost': 1192.0}  # 175.2 % FPL
    doc = _doc(elec('E20', FULL_YEAR, parcel_id='20'), _linked(demographic=demo))
    assert doc['fpl_pct'] == 176 and finalize(doc, dist, reg_rules, BM)['dims'][0] == 1
    burden = _doc(elec('E21', FULL_YEAR, parcel_id='21'), _linked(demographic={
        'estimated_income': 20000.0, 'md_householdsize': 3.0, 'annual_kwh_cost': 1192.0}))  # 5.96 %
    assert burden['energy_burden'] == 5.9 and finalize(burden, dist, reg_rules, BM)['dims'][1] == 0


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


def test_nonres_boundary():
    at = _doc(elec('M1', monthly_series(2025, 8, [4000.0] * 11 + [6000.0]), utility='AEP'), ParcelMatch())
    above = _doc(elec('M2', monthly_series(2025, 8, [4000.0] * 11 + [6001.0]), utility='AEP'), ParcelMatch())
    assert 'nonres' not in at and 'annual_cost' in at
    assert above['nonres'] is True and 'annual_cost' not in above and above['annual_kwh'] > 50000


def test_nonres_keeps_vendor_cost():
    match = _linked(demographic={'parcel_key': 'K', 'annual_kwh_cost': 3000, 'estimated_income': 60000,
                                 'md_householdsize': 2})
    hh = _doc(elec('M3', monthly_series(2025, 8, [6000.0] * 12), parcel_key='K'), match)
    assert hh['nonres'] is True and hh['annual_cost'] == 3000 and hh['burden_basis'] == 1


def test_owner_age_fills_blank_senior_only():
    blank = _linked(demographic={'parcel_key': 'K', 'md_presence_of_senior': '', 'owner_age': 70})
    young = _linked(demographic={'parcel_key': 'K', 'owner_age': 50})
    flag = _linked(demographic={'parcel_key': 'K', 'md_presence_of_senior': 'No Senior Present', 'owner_age': 70})
    none = _linked(demographic={'parcel_key': 'K'})
    meter = elec('M4', parcel_key='K')
    assert _doc(meter, blank)['senior'] is True and 22 not in _doc(meter, blank).get('missing', [])
    assert 'senior' not in _doc(meter, young)
    assert _doc(meter, flag)['senior'] is False
    assert 'senior' not in _doc(meter, none)
    assert assemble(meter, blank, 'Franklin', BM, REG).fallbacks == ['senior']


def test_nan_utility_falls_back_to_county_default():
    hh = _doc(elec('M5', monthly_series(2025, 8, [900.0] * 12), utility=float('nan')), ParcelMatch())
    assert 'annual_cost' in hh


def test_missing_token_utility_string_falls_back_to_county_default():
    expected = _doc(elec('E1', FULL_YEAR), ParcelMatch(), 'Cuyahoga')['annual_cost']
    for token in ('nan', ' Unknown '):
        assert _doc(elec('E1', FULL_YEAR, utility=token), ParcelMatch(), 'Cuyahoga')['annual_cost'] == expected


def test_thermal_fit_fields_are_stored():
    match = _linked(thermal={'parcel_key': 'K', 'kwh_hl_slope': 0.01, 'kwh_cl_slope': 0.02, 'kwh_r2': 0.7,
                             'kwh_hl_intercept': 12.5, 'kwh_hl_r2': 0.61, 'kwh_cl_r2': 0.55})
    hh = _doc(elec('M6', parcel_key='K'), match)
    assert hh['kwh_hl_intercept'] == 12.5 and hh['kwh_hl_r2'] == 0.61 and hh['kwh_cl_r2'] == 0.55


def _mapped(**roles):
    return assemble(elec('E20', FULL_YEAR, parcel_id='20'), _linked(**roles), 'Franklin', BM, REG)


@pytest.mark.parametrize('raw,expected', [('Owner', True), ('Renter', False)])
def test_home_owner_maps_tenure(raw, expected):
    result = _mapped(demographic={'home_owner': raw})
    assert result.doc['owner'] is expected and result.unmapped_values == []


@pytest.mark.parametrize('raw,expected', [('ELECTRIC', 2), ('GAS', 3), ('OIL', 4)])
def test_heating_fuel_type_maps_fuel(raw, expected):
    result = _mapped(residential={'heating_fuel_type': raw})
    assert result.doc['heat_fuel'] == expected and result.unmapped_values == []


def test_heating_fuel_type_na_is_known_but_empty():
    result = _mapped(residential={'heating_fuel_type': 'NA'})
    assert 'heat_fuel' not in result.doc and result.unmapped_values == []


def test_heating_fuel_type_is_second_path_after_heat_type():
    both = _mapped(residential={'heat_type': 'HTP', 'heating_fuel_type': 'GAS'})
    assert both.doc['heat_fuel'] == 1
    assert _mapped(residential={'heating_fuel_type': 'GAS'}).doc['heat_fuel'] == 3
