"""A created thermal document must carry both identifier spellings.

The 25 ThermalLoads collections are joined on `parcel_key` where the county has
one, and on a normalized `parcel_id` where it does not (T-04). Every pre-existing
Athens thermal document carries `parcel_key`; documents built by
`build_thermal_document` did not, because the recompute path that exercised it
upserted onto documents that already had the field.

T-07 is the first path that *creates* documents, so it is the first to expose
the gap. A keyless document is worse than an absent one: absent parcels are
reported missing, while a keyless document is counted by `count_documents` and
invisible to every parcel_key join, including the audit's own `best` column.

Aggregating multi-meter parcels remains T-06 and is not attempted here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from tests.mongo_fakes import FakeDB  # noqa: E402

from calculate_missing_thermal_loads_tool import (  # noqa: E402
    build_thermal_document,
    get_electrical_data,
)

BILLING = [{'date': '2025-01-01', 'days': 30, 'kwh': 900.0, 'hl': 800.0, 'cl': 10.0},
           {'date': '2025-02-01', 'days': 30, 'kwh': 850.0, 'hl': 750.0, 'cl': 12.0},
           {'date': '2025-03-01', 'days': 30, 'kwh': 700.0, 'hl': 500.0, 'cl': 40.0}]
MODEL = {'kwh_hl_slope': 0.04, 'kwh_cl_slope': 0.02, 'kwh_intercept': 500.0, 'kwh_r2': 0.8}


def _series(n):
    return {f'2025-{m:02d}-01': 100.0 + m for m in range(1, n + 1)}


def test_electrical_fetch_returns_the_parcel_key():
    db = FakeDB(electrical=[{'parcel_id': 'A1', 'parcel_key': 'KEY-A1',
                             'time_series_elec': _series(4)}],
                thermal=[], county='Testville')
    _data, _collisions, keys = get_electrical_data(db, 'Testville', ['A1'])
    assert keys == {'A1': 'KEY-A1'}


def test_county_without_parcel_key_yields_no_entry():
    db = FakeDB(electrical=[{'parcel_id': 'A1', 'time_series_elec': _series(4)}],
                thermal=[], county='Testville')
    _data, _collisions, keys = get_electrical_data(db, 'Testville', ['A1'])
    assert keys == {}, "Montgomery, Scioto, Hardin and Ross have no parcel_key on either side"


def test_document_carries_the_parcel_key_when_one_exists():
    doc = build_thermal_document('A1', BILLING, MODEL, parcel_key='KEY-A1')
    assert doc['parcel_key'] == 'KEY-A1'
    assert doc['parcel_id'] == 'A1'


def test_document_omits_the_field_rather_than_writing_null():
    """A null key would be indexed and would join against other nulls."""
    doc = build_thermal_document('A1', BILLING, MODEL, parcel_key=None)
    assert 'parcel_key' not in doc


def test_parcel_key_defaults_to_absent_for_existing_callers():
    doc = build_thermal_document('A1', BILLING, MODEL)
    assert 'parcel_key' not in doc
