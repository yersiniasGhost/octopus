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


class FakeStore:
    """In-memory analysis_households with the staging/swap semantics of MongoStore."""

    def __init__(self, live=None, fail_on_stage=False, fail_on_swap=False):
        self.live = {doc['_id']: doc for doc in (live or [])}
        self.staging, self.builds, self.coverage, self.fail_on_stage = {}, [], {}, fail_on_stage
        self.fail_on_swap = fail_on_swap

    def reset_staging(self, county):
        self.staging[county] = {}

    def stage(self, county, docs):
        if self.fail_on_stage:
            raise IOError('disk full')
        self.staging[county].update({doc['_id']: doc for doc in docs})

    def swap(self, county):
        if self.fail_on_swap:
            raise IOError('connection lost')
        self.live = {k: d for k, d in self.live.items() if d['county'] != county}
        self.live.update(self.staging.pop(county))

    def discard_staging(self, county):
        self.staging.pop(county, None)

    def record_build(self, build):
        self.builds.append(build)

    def write_coverage(self, doc):
        self.coverage[doc['_id']] = doc
