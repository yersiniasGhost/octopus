"""process_county: matched merges write utility, parcel_key spellings match, ambiguous addresses resolve once."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

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


def test_two_addresses_on_one_parcel_merge_into_one_write():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'time_series_elec': {}}],
             [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'},
              {'_id': 'r2', 'parcel_id': 'P1', 'address': '14 Main St'}])
    recs = [_rec(), AccountRecord('FE', 'CEI', 'A2', 'X', '14 MAIN ST', 'Columbus', 'OH', '43215', [('2026-06-15', 600.0)])]
    st = _run(db, recs)
    assert set(db['TestElectricalDB'].docs['o1']['time_series_elec']) == {D1, '2026-06-15 00:00:00'}
    assert st['docs_updated'] == 1 and st['utility_set'] == 1
    st = _run(db, recs)
    assert st.get('docs_updated', 0) == 0 and st['unchanged'] == 1


RES = [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'}]


def test_multi_preingest_parcel_whose_doc_holds_the_dates_creates_nothing():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'utility': 'FE', 'time_series_elec': {D1: 500.0}},
              {'_id': 'o2', 'parcel_id': 'P1', 'utility': 'FE', 'time_series_elec': {}}], RES)
    st = _run(db, [_rec()])
    assert len(db['TestElectricalDB'].docs) == 2 and st.get('docs_created_parcel', 0) == 0
    assert st['unchanged'] == 1 and st.get('skipped_multi_preingest', 0) == 0


def test_multi_preingest_parcel_with_no_holder_is_skipped_not_duplicated():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'time_series_elec': {}},
              {'_id': 'o2', 'parcel_id': 'P1', 'time_series_elec': {}}], RES)
    st = _run(db, [_rec()])
    assert len(db['TestElectricalDB'].docs) == 2 and st.get('docs_created_parcel', 0) == 0
    assert st['skipped_multi_preingest'] == 1
    st = _run(db, [_rec()])
    assert len(db['TestElectricalDB'].docs) == 2 and st['skipped_multi_preingest'] == 1


def test_parcel_without_docs_still_creates_a_linked_doc():
    db = _db([], RES)
    st = _run(db, [_rec()])
    (doc,) = db['TestElectricalDB'].docs.values()
    assert doc['parcel_id'] == 'P1' and st['docs_created_parcel'] == 1


def test_surrogate_collision_keeps_first_records_dates():
    db = _db([], [])
    a = _rec(addr='1 OAK ST', account='NAME')
    b = AccountRecord('FE', 'CEI', 'NAME', 'X', '2 ELM ST', 'Columbus', 'OH', '43215', [('2026-06-15', 600.0)])
    st = _run(db, [a, b])
    (doc,) = db['TestElectricalDB'].docs.values()
    assert set(doc['time_series_elec']) == {D1} and st['surrogate_collision'] == 1


def test_matched_parcel_slots_still_union_across_addresses():
    db = _db([], [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'},
                  {'_id': 'r2', 'parcel_id': 'P1', 'address': '14 Main St'}])
    b = AccountRecord('FE', 'CEI', 'A2', 'X', '14 MAIN ST', 'Columbus', 'OH', '43215', [('2026-06-15', 600.0)])
    _run(db, [_rec(), b])
    (doc,) = db['TestElectricalDB'].docs.values()
    assert len(doc['time_series_elec']) == 2


def test_selected_sources_excludes_utility_in_delivery():
    from src.tools.utility_bills.ingest import selected_sources
    allsrc = selected_sources('jan2026')
    kept = selected_sources('jan2026', exclude={'aes'})
    assert any(s['utility'].lower() == 'aes' for s in allsrc) and len(kept) < len(allsrc)
    assert not any(s['utility'].lower() == 'aes' for s in kept)
    assert kept and all(s in allsrc for s in kept)
    assert selected_sources('jan2026', utilities={'aes', 'fe'}, exclude={'aes'}) == [s for s in kept if s['utility'].lower() == 'fe']


def test_parse_exclude_args_maps_delivery_to_utilities():
    from ingest_electric_bills_tool import COUNTY_COLS, parse_excludes
    assert parse_excludes(['AES:jan2026', 'fe:jan2026']) == {'jan2026': {'aes', 'fe'}}
    assert 'utility_set' in COUNTY_COLS and 'unchanged' in COUNTY_COLS


def test_parse_excludes_rejects_bad_utility_and_undelivered_delivery():
    import pytest
    from ingest_electric_bills_tool import parse_excludes
    for bad in ('AE:jan2026', 'AESS:jan2026', 'AES:nope2026'):
        with pytest.raises(SystemExit):
            parse_excludes([bad])
    with pytest.raises(SystemExit):
        parse_excludes(['AES:jan2026'], ['aug2026'])
    assert parse_excludes(['AES:jan2026'], ['jan2026', 'aug2026']) == {'jan2026': {'aes'}}


def test_surrogate_key_matching_a_linked_doc_is_a_collision_not_a_merge():
    db = _db([{'_id': 'FE:CEI:A1', 'parcel_id': 'P9', 'utility': 'FE', 'time_series_elec': {'2024-05-15 00:00:00': 400.0}}], [])
    st = _run(db, [_rec()])
    doc = db['TestElectricalDB'].docs['FE:CEI:A1']
    assert doc['parcel_id'] == 'P9' and set(doc['time_series_elec']) == {'2024-05-15 00:00:00'}
    assert st['surrogate_collision'] == 1 and st.get('docs_updated', 0) == 0 and len(db['TestElectricalDB'].docs) == 1


def test_no_doc_parcel_ignores_a_linked_doc_under_the_records_key():
    old = {'_id': 'FE:CEI:A1', 'parcel_id': 'X', 'utility': 'FE', 'service_address': '12 MAIN ST',
           'time_series_elec': {'2024-05-15 00:00:00': 400.0}}
    db = _db([dict(old)], [{'_id': 'r1', 'parcel_id': 'Y', 'address': '99 Pine St'}])
    st = _run(db, [_rec(addr='99 PINE ST')])
    assert st['docs_created_parcel'] == 1 and db['TestElectricalDB'].docs['FE:CEI:A1'] == old
    assert any(d.get('parcel_id') == 'Y' for d in db['TestElectricalDB'].docs.values())


def test_no_doc_parcel_ignores_an_unlinked_doc_at_another_address():
    old = {'_id': 'FE:CEI:A1', 'parcel_id': None, 'utility': 'FE', 'service_address': '12 MAIN ST',
           'time_series_elec': {'2024-05-15 00:00:00': 400.0}}
    db = _db([dict(old)], [{'_id': 'r1', 'parcel_id': 'Y', 'address': '99 Pine St'}])
    st = _run(db, [_rec(addr='99 PINE ST')])
    assert st['docs_created_parcel'] == 1 and db['TestElectricalDB'].docs['FE:CEI:A1'] == old


def test_unmatched_record_whose_key_holds_another_address_is_a_collision():
    old = {'_id': 'FE:CEI:A1', 'parcel_id': None, 'utility': 'FE', 'service_address': '12 MAIN ST',
           'time_series_elec': {'2024-05-15 00:00:00': 400.0}}
    db = _db([dict(old)], [])
    st = _run(db, [_rec(addr='77 ASH ST')])
    assert st['surrogate_collision'] == 1 and db['TestElectricalDB'].docs['FE:CEI:A1'] == old
    assert len(db['TestElectricalDB'].docs) == 1 and st.get('readings_added_new', 0) == 0
