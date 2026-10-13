"""Derived household features. Pure functions; every table they use is passed in from the registry."""

from typing import Dict, Optional, Tuple


def fpl_pct(income: float, hh_size: int, fpg: Dict) -> int:
    """Income as a percent of the HHS poverty guideline; sizes past the table add the per-person increment."""
    base = fpg['base']
    guideline = base[hh_size - 1] if hh_size <= len(base) else base[-1] + fpg['per_additional'] * (hh_size - len(base))
    return int(round(100 * income / guideline))


def ami_pct(income: float, hh_size: int, hud_county: Dict, extra_pct: float) -> int:
    """Income as a percent of AMI, scaled so the HUD 80% 'Low Income' limit for this size reads as 80."""
    limits = hud_county['limits']
    extra = limits[3] * extra_pct / 100 * (hh_size - len(limits))
    limit = limits[hh_size - 1] if hh_size <= len(limits) else limits[-1] + extra
    return int(round(80 * income / limit))


def annual_cost(vendor_cost: Optional[float], annual_kwh: Optional[int], fresh: bool,
                rate: Optional[float]) -> Tuple[Optional[int], Optional[int]]:
    """(cost, burden_basis): vendor cost (basis 1) when supplied, else kWh x rate (basis 0) for a fresh meter."""
    if vendor_cost is not None:
        return int(round(vendor_cost)), 1
    if annual_kwh is not None and fresh and rate is not None:
        return int(round(annual_kwh * rate)), 0
    return None, None


def energy_burden(cost: Optional[int], income: Optional[float]) -> Optional[float]:
    """Electric cost as a percent of income -- a lower bound, since gas is excluded."""
    return round(100 * cost / income, 1) if cost is not None and income else None


def hl_per_sqft(hl_slope: Optional[float], sqft: Optional[float]) -> Optional[float]:
    return round(hl_slope / sqft, 8) if hl_slope is not None and sqft else None
