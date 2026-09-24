"""T-06 exposure in T-07's write path: multi-meter parcels must not be guessed at.

`get_electrical_data` assigned `data[parcel_id] = time_series` inside the cursor
loop, so a parcel owning several eligible electrical documents kept whichever one
the cursor happened to yield last and discarded the rest without a word. On a
recompute that corrupts an existing slope; on T-07 it manufactures a new record
fitted on partial household load with nothing on the document to say so.

Measured against T-07's real target population, 37 parcels of 62,712 are affected
(36 Hancock, 1 Franklin). They are excluded rather than guessed at, and excluded
*visibly* -- the count comes back as its own bucket. Folding them into
"insufficient data" is the mistake that hid 1,127 Fayette parcels for a day.

Aggregating the meters properly is T-06 and is not attempted here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from tests.mongo_fakes import FakeDB  # noqa: E402

from calculate_missing_thermal_loads_tool import get_electrical_data  # noqa: E402


def _series(n):
    """n billing periods, enough to pass the >= 2 eligibility gate when n >= 2."""
    return {f'2025-{m:02d}-01': 100.0 + m for m in range(1, n + 1)}


def _db(docs):
    return FakeDB(electrical=docs, thermal=[], county='Testville')


def test_single_meter_parcel_is_returned():
    db = _db([{'parcel_id': 'A1', 'time_series_elec': _series(4)}])
    data, collisions, _keys = get_electrical_data(db, 'Testville', ['A1'])
    assert set(data) == {'A1'}
    assert collisions == {}


def test_two_eligible_documents_excludes_the_parcel():
    db = _db([
        {'parcel_id': 'A1', 'time_series_elec': _series(4)},
        {'parcel_id': 'A1', 'time_series_elec': _series(6)},
    ])
    data, collisions, _keys = get_electrical_data(db, 'Testville', ['A1'])
    assert 'A1' not in data, "a multi-meter parcel must not be fitted on one arbitrary meter"
    assert collisions == {'A1': 2}


def test_collision_reports_the_document_count():
    db = _db([{'parcel_id': 'A1', 'time_series_elec': _series(3)} for _ in range(6)])
    _, collisions, _keys = get_electrical_data(db, 'Testville', ['A1'])
    assert collisions == {'A1': 6}, "the report must carry how many meters, not just that there were several"


def test_ineligible_duplicate_is_not_a_collision():
    """One meter with real history plus a stub row is a single usable series."""
    db = _db([
        {'parcel_id': 'A1', 'time_series_elec': _series(5)},
        {'parcel_id': 'A1', 'time_series_elec': _series(1)},
    ])
    data, collisions, _keys = get_electrical_data(db, 'Testville', ['A1'])
    assert collisions == {}
    assert len(data['A1']) == 5


def test_collision_does_not_suppress_healthy_parcels():
    db = _db([
        {'parcel_id': 'A1', 'time_series_elec': _series(4)},
        {'parcel_id': 'B2', 'time_series_elec': _series(4)},
        {'parcel_id': 'B2', 'time_series_elec': _series(5)},
        {'parcel_id': 'C3', 'time_series_elec': _series(3)},
    ])
    data, collisions, _keys = get_electrical_data(db, 'Testville', ['A1', 'B2', 'C3'])
    assert set(data) == {'A1', 'C3'}
    assert collisions == {'B2': 2}


def test_parcel_with_no_eligible_data_is_absent_but_not_a_collision():
    db = _db([{'parcel_id': 'A1', 'time_series_elec': _series(1)}])
    data, collisions, _keys = get_electrical_data(db, 'Testville', ['A1'])
    assert data == {}
    assert collisions == {}
