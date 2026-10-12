"""A meter's time_series_elec -> months covered, last reading, annual kWh and peak ratio.

The raw series is never copied to the household document; only these derived values are (spec §4).
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Usage:
    months_usage: int
    last_read: Optional[int]
    annual_kwh: Optional[int] = None
    peak_ratio: Optional[float] = None


def _yyyymm(day: date) -> int:
    return day.year * 100 + day.month


def months_between(earlier: int, later: int) -> int:
    """Whole months from one YYYYMM to another."""
    return (later // 100 * 12 + later % 100) - (earlier // 100 * 12 + earlier % 100)


def is_fresh(last_read: Optional[int], build_month: int, max_age_months: int) -> bool:
    """True when the meter read within max_age_months of the build month."""
    return last_read is not None and months_between(last_read, build_month) <= max_age_months


def _readings(series: Optional[Dict]) -> List[Tuple[date, float]]:
    rows = []
    for key, value in (series or {}).items():
        try:
            day = datetime.strptime(str(key)[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            continue
        rows.append((day, float(value)))
    return sorted(rows)


def summarize_usage(series: Optional[Dict], min_span_days: int, max_span_days: int) -> Usage:
    """Summarize one meter. Annual values need the latest 12 readings to span a plausible year."""
    rows = _readings(series)
    if not rows:
        return Usage(months_usage=0, last_read=None)
    latest = rows[-1][0]
    months = len({_yyyymm(day) for day, _ in rows if (latest - day).days < 365})
    base = Usage(months_usage=min(months, 12), last_read=_yyyymm(latest))
    year = rows[-12:]
    span = (year[-1][0] - year[0][0]).days
    total = sum(value for _, value in year)
    if len(year) < 12 or not min_span_days <= span <= max_span_days or total <= 0:
        return base
    peak = max(value for _, value in year) / (total / 12)
    return Usage(base.months_usage, base.last_read, int(round(total)), round(peak, 2))
