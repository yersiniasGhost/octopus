"""Builders for analysis_engine tests: meter time series and ElectricalDB documents."""

from typing import Dict, List


def monthly_series(start_year: int, start_month: int, values: List[float]) -> Dict[str, float]:
    """One reading on the 15th of each month, keyed the way ElectricalDB stores time_series_elec."""
    series = {}
    for i, value in enumerate(values):
        year, month = divmod(start_month - 1 + i, 12)
        series[f'{start_year + year}-{month + 1:02d}-15 00:00:00'] = value
    return series


def elec(_id, series=None, **fields) -> Dict:
    """An ElectricalDB document; parcel_id / parcel_key / utility go in fields."""
    return {'_id': _id, 'time_series_elec': series or {}, **fields}
