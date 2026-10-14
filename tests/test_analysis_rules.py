"""Six need dimensions, each -1 unless its inputs are known. Boundaries are tested on both sides."""

import sys
from pathlib import Path

import bson

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.rules import Distributions, cutpoints, finalize, percentile_rank, quantile, usage_ok  # noqa: E402

RULES = load_registry().rules
BM = 202610
DIST = Distributions.from_values(list(range(100, 10001, 100)), [i / 1e6 for i in range(1, 101)])
FRESH = {'annual_kwh': 5000, 'months_usage': 12, 'last_read': 202607}


def _dims(**hh):
    return finalize(dict(hh), DIST, RULES, BM)['dims']


def test_percentiles_and_quantiles():
    values = list(range(1, 101))
    assert percentile_rank(values, 90) == 90 and percentile_rank(values, 100) == 100 and percentile_rank(values, 0) == 0
    assert quantile(values, 75) == 75 and quantile([], 75) is None


def test_income_need_boundaries():
    assert _dims(fpl_pct=175)[0] == 2
    assert _dims(fpl_pct=176)[0] == 1 and _dims(fpl_pct=200)[0] == 1
    assert _dims(fpl_pct=201, ami_pct=80)[0] == 1
    assert _dims(fpl_pct=201, ami_pct=81)[0] == 0 and _dims(fpl_pct=201)[0] == 0
    assert _dims()[0] == -1


def test_energy_burden_boundaries():
    assert [_dims(energy_burden=b)[1] for b in (10.0, 9.9, 6.0, 5.9)] == [2, 1, 1, 0]
    assert _dims()[1] == -1


def test_high_usage_uses_county_percentile():
    assert _dims(**{**FRESH, 'annual_kwh': 9000})[3] == 2
    assert _dims(**{**FRESH, 'annual_kwh': 7500})[3] == 1
    assert _dims(**{**FRESH, 'annual_kwh': 7400})[3] == 0
    assert finalize(dict(FRESH, annual_kwh=9000), DIST, RULES, BM)['usage_pctile'] == 90


def test_stale_meter_usage_is_unknown():
    hh = finalize({'annual_kwh': 9000, 'months_usage': 12, 'last_read': 201602}, DIST, RULES, BM)
    assert hh['dims'][3] == -1 and 'usage_pctile' not in hh
    assert _dims(annual_kwh=9000, months_usage=11, last_read=202607)[3] == -1


FIT = {'hl_slope': 0.1, 'thermal_r2': 0.8, 'year_built': 1958}


def test_inefficiency_ranks_usable_fits():
    assert _dims(**FIT, hl_per_sqft=0.000081)[2] == 2
    assert _dims(**FIT, hl_per_sqft=0.000061)[2] == 1
    assert _dims(**FIT, hl_per_sqft=0.000010)[2] == 0


def test_negative_slope_is_not_a_usable_fit():
    hh = finalize({'hl_slope': -0.2, 'thermal_r2': 0.9, 'hl_per_sqft': -0.0001, 'year_built': 1958}, DIST, RULES, BM)
    assert hh['dims'][2] == 1 and hh['proxy'] == 1 << 2


def test_inefficiency_proxies_and_unknown():
    assert _dims(hl_slope=0.1, thermal_r2=0.4, hl_per_sqft=0.00009, year_built=1990)[2] == 0
    assert _dims(multi_unit=True, hl_slope=0.1, thermal_r2=0.9, hl_per_sqft=0.00009)[2] == -1
    assert _dims()[2] == -1


def test_vulnerability_counts_modifiers():
    assert _dims(senior=True, children=True)[4] == 2
    assert _dims(senior=True, children=True, owner=False)[4] == 2
    assert _dims(owner=False)[4] == 1 and _dims(multi_unit=True)[4] == 1
    assert _dims(senior=False, children=False, owner=True)[4] == 0
    assert _dims(multi_unit=False)[4] == -1 and _dims()[4] == -1


def test_electrification_uses_measured_fuel_only():
    assert _dims(heat_fuel=2)[5] == 2 and _dims(heat_fuel=1)[5] == 0 and _dims()[5] == -1


def test_unknown_is_never_zero_and_dim_sum_skips_unknown():
    empty = finalize({}, DIST, RULES, BM)
    assert empty['dims'] == [-1] * 6 and empty['dim_sum'] == 0 and 'proxy' not in empty
    assert finalize({'fpl_pct': 100, 'senior': True}, DIST, RULES, BM)['dim_sum'] == 3


def test_cutpoints_record_the_thresholds_used():
    cuts = cutpoints(DIST, RULES['params'])
    assert cuts['annual_kwh'] == {'n': 100, 'p75': 7500, 'p90': 9000}
    assert cuts['hl_per_sqft']['n'] == 100 and cuts['hl_per_sqft']['p80'] == 80 / 1e6


def test_fully_populated_document_is_under_1kb():
    hh = {'_id': 'AEP:CSP:43002|4601 BALDWIN RD WEST SIDE', 'county': 'Franklin', 'parcel_key': '010-123456-00',
          'link': 15, 'multi_unit': False, 'income_est': 42000, 'hh_size': 3, 'fpl_pct': 154, 'ami_pct': 42,
          'annual_kwh': 11840, 'annual_cost': 2246, 'energy_burden': 5.3, 'burden_basis': 0, 'peak_ratio': 1.84,
          'months_usage': 12, 'last_read': 202607, 'hl_slope': 0.14211, 'cl_slope': 0.31102, 'thermal_r2': 0.823,
          'hl_per_sqft': 0.00009411, 'year_built': 1958, 'sqft': 1510, 'stories': 1.5, 'home_value': 154000,
          'owner': True, 'senior': False, 'children': True, 'length_residence': 7, 'heat_fuel': 1,
          'missing': [17, 18, 19, 20, 21, 22, 23, 24]}
    assert len(bson.encode(finalize(hh, DIST, RULES, BM))) < 1024


def test_nonres_household_is_out_of_the_usage_distribution():
    hh = {'annual_kwh': 60000, 'months_usage': 12, 'last_read': 202609, 'nonres': True}
    assert not usage_ok(hh, RULES['params'], BM)
    assert finalize(dict(hh), Distributions.from_values([1000, 60000], []), RULES, BM)['dims'][3] == -1
