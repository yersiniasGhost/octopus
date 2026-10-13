"""Need dimensions: county-relative percentiles, the six level functions, and finalize().

Levels: -1 unknown, 0 none, 1 moderate, 2 high. Unknown is never coerced to 0 (spec §5.4). Each level function
returns (level, is_proxy); proxy levels set the matching bit in `proxy` so the UI can show measured-only.
"""

import math
from bisect import bisect_right
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.analysis_engine.usage import is_fresh

UNKNOWN = -1
Level = Tuple[int, bool]


@dataclass(frozen=True)
class Distributions:
    """County values the percentile dimensions rank against; both lists are sorted."""
    annual_kwh: List[float]
    hl_per_sqft: List[float]

    @classmethod
    def from_values(cls, annual_kwh, hl_per_sqft) -> 'Distributions':
        return cls(sorted(annual_kwh), sorted(hl_per_sqft))


def percentile_rank(sorted_values: List[float], x: float) -> int:
    """Percent of values at or below x."""
    return int(100 * bisect_right(sorted_values, x) / len(sorted_values))


def quantile(sorted_values: List[float], pct: float) -> Optional[float]:
    if not sorted_values:
        return None
    return sorted_values[max(0, math.ceil(pct / 100 * len(sorted_values)) - 1)]


def usage_ok(hh: Dict, params: Dict, build_month: int) -> bool:
    """A full, plausible year from a meter that is still reading."""
    return (hh.get('annual_kwh') is not None and hh.get('months_usage', 0) >= 12
            and is_fresh(hh.get('last_read'), build_month, params['usage']['max_age_months']))


def usable_fit(hh: Dict, params: Dict) -> bool:
    """A thermal fit worth ranking: present, non-negative heating slope, adequate r², single-meter parcel."""
    return (hh.get('hl_per_sqft') is not None and hh.get('hl_slope', -1) >= 0
            and hh.get('thermal_r2', 0) >= params['building_inefficiency']['r2_min'] and not hh.get('multi_unit'))


def cutpoints(dist: Distributions, params: Dict) -> Dict:
    """The county values behind each percentile threshold, stored on analysis_builds for transparency."""
    usage, ineff = params['high_usage'], params['building_inefficiency']
    usage_mod_key = f"p{usage['moderate_pctile']}"
    usage_high_key = f"p{usage['high_pctile']}"
    ineff_mod_key = f"p{ineff['moderate_pctile']}"
    ineff_high_key = f"p{ineff['high_pctile']}"
    return {
        'annual_kwh': {
            'n': len(dist.annual_kwh),
            usage_mod_key: quantile(dist.annual_kwh, usage['moderate_pctile']),
            usage_high_key: quantile(dist.annual_kwh, usage['high_pctile'])
        },
        'hl_per_sqft': {
            'n': len(dist.hl_per_sqft),
            ineff_mod_key: quantile(dist.hl_per_sqft, ineff['moderate_pctile']),
            ineff_high_key: quantile(dist.hl_per_sqft, ineff['high_pctile'])
        }
    }


def _income(hh: Dict, p: Dict) -> Level:
    fpl, ami = hh.get('fpl_pct'), hh.get('ami_pct')
    if fpl is None:
        return UNKNOWN, False
    if fpl <= p['fpl_high']:
        return 2, False
    return (1 if fpl <= p['fpl_moderate'] or (ami is not None and ami <= p['ami_moderate']) else 0), False


def _burden(hh: Dict, p: Dict) -> Level:
    burden = hh.get('energy_burden')
    if burden is None:
        return UNKNOWN, False
    return (2 if burden >= p['high'] else 1 if burden >= p['moderate'] else 0), False


def _inefficiency(hh: Dict, p: Dict, pctile: Optional[int]) -> Level:
    if pctile is not None:
        return (2 if pctile >= p['high_pctile'] else 1 if pctile >= p['moderate_pctile'] else 0), False
    year = hh.get('year_built')
    if year is None:
        return UNKNOWN, False
    return (1 if year < p['proxy_built_before'] else 0), True


def _usage(pctile: Optional[int], p: Dict) -> Level:
    if pctile is None:
        return UNKNOWN, False
    return (2 if pctile >= p['high_pctile'] else 1 if pctile >= p['moderate_pctile'] else 0), False


def _vulnerability(hh: Dict) -> Level:
    owner, multi = hh.get('owner'), hh.get('multi_unit')
    housing = True if owner is False or multi is True else False if owner is True else None
    modifiers = [hh.get('senior'), hh.get('children'), housing]
    if all(m is None for m in modifiers):
        return UNKNOWN, False
    return min(sum(m is True for m in modifiers), 2), False


def _electrification(hh: Dict, p: Dict) -> Level:
    fuel = hh.get('heat_fuel')
    if fuel is None:
        return UNKNOWN, False
    return (2 if fuel in p['high_fuels'] else 0), False


def finalize(hh: Dict, dist: Distributions, rules: Dict, build_month: int) -> Dict:
    """Add usage_pctile, dims, proxy and dim_sum to an assembled household document."""
    p = rules['params']
    usage_pctile = percentile_rank(dist.annual_kwh, hh['annual_kwh']) \
        if dist.annual_kwh and usage_ok(hh, p, build_month) else None
    hl_pctile = percentile_rank(dist.hl_per_sqft, hh['hl_per_sqft']) \
        if dist.hl_per_sqft and usable_fit(hh, p) else None
    if usage_pctile is not None:
        hh['usage_pctile'] = usage_pctile
    levels = [_income(hh, p['income_need']), _burden(hh, p['energy_burden']),
              _inefficiency(hh, p['building_inefficiency'], hl_pctile), _usage(usage_pctile, p['high_usage']),
              _vulnerability(hh), _electrification(hh, p['electrification'])]
    hh['dims'] = [level for level, _ in levels]
    proxy = sum(1 << i for i, (_, is_proxy) in enumerate(levels) if is_proxy)
    if proxy:
        hh['proxy'] = proxy
    hh['dim_sum'] = sum(level for level in hh['dims'] if level > 0)
    return hh
