"""process_county: matched merges write utility, parcel_key spellings match, ambiguous addresses resolve once."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.utility_bills.ingest import process_county  # noqa: E402
from src.tools.utility_bills.record import AccountRecord  # noqa: E402
from tests.utility_fakes import WritableDB  # noqa: E402

D1 = '2026-05-15 00:00:00'


def _rec(addr='12 MAIN ST', zip5='43215', kwh=500.0, account='A1'):
    return AccountRecord('FE', 'CEI', account, 'X', addr, 'Columbus', 'OH', zip5, [('2026-05-15', kwh)])


def _db(elec, res):
    return WritableDB({'TestElectricalDB': elec, 'TestCountyResidential': res})


def _run(db, recs):
    return process_county(db, 'Test', recs, 'aug2026', False, set(db.list_collection_names()), log=lambda *_: None)


def test_matched_existing_doc_gets_utility_even_without_new_dates():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'time_series_elec': {D1: 500.0}}],
             [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'}])
    st = _run(db, [_rec()])
    assert db['TestElectricalDB'].docs['o1']['utility'] == 'FE' and st['utility_set'] == 1


def test_parcel_key_spelling_finds_existing_doc():
    db = _db([{'_id': 'o1', 'parcel_id': '0101', 'parcel_key': '101', 'time_series_elec': {}}],
             [{'_id': 'r1', 'parcel_id': '101', 'parcel_key': '101', 'address': '12 Main St'}])
    _run(db, [_rec()])
    assert set(db['TestElectricalDB'].docs) == {'o1'}
    assert db['TestElectricalDB'].docs['o1']['time_series_elec'][D1] == 500.0


def test_new_linked_doc_carries_parcel_key():
    db = _db([], [{'_id': 'r1', 'parcel_id': '101', 'parcel_key': '101', 'address': '12 Main St'}])
    _run(db, [_rec()])
    (doc,) = db['TestElectricalDB'].docs.values()
    assert doc['parcel_id'] == '101' and doc['parcel_key'] == '101' and doc['utility'] == 'FE'


def test_ambiguous_address_merges_into_the_single_candidate_with_a_doc():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': {'2024-05-15 00:00:00': 400.0}}],
             [{'_id': 'r1', 'parcel_id': 'A', 'address': '12 Main St'},
              {'_id': 'r2', 'parcel_id': 'B', 'address': '12 Main St'}])
    st = _run(db, [_rec()])
    assert set(db['TestElectricalDB'].docs) == {'o1'} and st['ambiguous_resolved'] == 1


def test_ambiguous_address_with_conflicting_series_stays_unmatched():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': {D1: 999.0}}],
             [{'_id': 'r1', 'parcel_id': 'A', 'address': '12 Main St'},
              {'_id': 'r2', 'parcel_id': 'B', 'address': '12 Main St'}])
    st = _run(db, [_rec()])
    assert 'FE:CEI:A1' in db['TestElectricalDB'].docs and st['ambiguous_conflict'] == 1
    assert db['TestElectricalDB'].docs['o1']['time_series_elec'] == {D1: 999.0}


def test_second_run_changes_nothing():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'time_series_elec': {}}],
             [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'}])
    _run(db, [_rec()])
    st = _run(db, [_rec()])
    assert st.get('docs_updated', 0) == 0 and st.get('utility_set', 0) == 0 and st['unchanged'] == 1
