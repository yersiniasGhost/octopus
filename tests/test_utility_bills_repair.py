"""repair_county folds ingest-created duplicates into their pre-ingest document and deletes them."""
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


from src.tools.utility_bills.repair import repair_county  # noqa: E402
from tests.utility_fakes import WritableDB  # noqa: E402

OLD = {'2024-03-15 00:00:00': 400.0}
NEW = {'2026-05-15 00:00:00': 500.0}


def _db(elec, res=()):
    return WritableDB({'TestElectricalDB': elec, 'TestCountyResidential': list(res)})


def test_parcel_key_duplicate_folds_into_preingest_doc():
    db = _db([{'_id': 'o1', 'parcel_id': '0101', 'parcel_key': '101', 'time_series_elec': dict(OLD)},
              {'_id': 'n1', 'parcel_id': '101', 'parcel_key': '101', 'time_series_elec': dict(NEW),
               'utility': 'FE', 'source_delivery': 'aug2026', 'last_utility_ingest': 'aug2026'}])
    st = repair_county(db, 'Test', dry_run=False)
    doc = db['TestElectricalDB'].docs['o1']
    assert st['parcel_folds'] == 1 and st['deleted'] == 1 and 'n1' not in db['TestElectricalDB'].docs
    assert doc['time_series_elec'] == {**OLD, **NEW} and doc['utility'] == 'FE'


def test_parcel_with_two_preingest_docs_is_not_folded():
    db = _db([{'_id': 'o1', 'parcel_key': '101', 'time_series_elec': {}},
              {'_id': 'o2', 'parcel_key': '101', 'time_series_elec': {}},
              {'_id': 'n1', 'parcel_key': '101', 'time_series_elec': dict(NEW), 'source_delivery': 'aug2026'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_multi_preingest'] == 1 and len(db['TestElectricalDB'].docs) == 3


def test_surrogate_at_shared_address_folds_into_the_single_candidate():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': dict(OLD)},
              {'_id': 'AES::77', 'parcel_id': None, 'time_series_elec': dict(NEW), 'utility': 'AES',
               'service_address': '12 MAIN ST', 'service_zip5': '45402', 'source_delivery': 'aug2026'}],
             [{'parcel_id': 'A', 'address': '12 Main St', 'parcel_zip': '45402'},
              {'parcel_id': 'B', 'address': '12 Main St', 'parcel_zip': '45402'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['address_folds'] == 1 and db['TestElectricalDB'].docs['o1']['utility'] == 'AES'


def test_fold_skips_address_with_two_candidates():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': {}},
              {'_id': 'o2', 'parcel_id': 'B', 'time_series_elec': {}},
              {'_id': 's1', 'parcel_id': None, 'time_series_elec': dict(NEW), 'service_address': '12 MAIN ST',
               'service_zip5': '45402', 'source_delivery': 'aug2026'}],
             [{'parcel_id': 'A', 'address': '12 Main St'}, {'parcel_id': 'B', 'address': '12 Main St'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_multi_candidate'] == 1 and 's1' in db['TestElectricalDB'].docs


def test_conflicting_series_is_skipped():
    db = _db([{'_id': 'o1', 'parcel_key': '101', 'time_series_elec': {'2026-05-15 00:00:00': 1.0}},
              {'_id': 'n1', 'parcel_key': '101', 'time_series_elec': dict(NEW), 'source_delivery': 'aug2026'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_conflict'] == 1 and st['deleted'] == 0
    assert 'n1' in db['TestElectricalDB'].docs
    assert db['TestElectricalDB'].docs['o1']['time_series_elec'] == {'2026-05-15 00:00:00': 1.0}


def test_dry_run_writes_nothing():
    elec = [{'_id': 'o1', 'parcel_key': '101', 'time_series_elec': dict(OLD)},
            {'_id': 'n1', 'parcel_key': '101', 'time_series_elec': dict(NEW), 'source_delivery': 'aug2026'}]
    db = _db(elec)
    st = repair_county(db, 'Test', dry_run=True)
    assert st['parcel_folds'] == 1 and set(db['TestElectricalDB'].docs) == {'o1', 'n1'}
    assert db['TestElectricalDB'].docs['o1']['time_series_elec'] == OLD


def test_repair_is_idempotent():
    db = _db([{'_id': 'o1', 'parcel_key': '101', 'time_series_elec': dict(OLD)},
              {'_id': 'n1', 'parcel_key': '101', 'time_series_elec': dict(NEW), 'source_delivery': 'aug2026'}])
    repair_county(db, 'Test', dry_run=False)
    st = repair_county(db, 'Test', dry_run=False)
    assert st['parcel_folds'] == st['address_folds'] == st['deleted'] == 0


RES = [{'parcel_id': 'A', 'address': '12 Main St'}]


def test_preingest_unlinked_doc_is_left_alone():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': dict(OLD)},
              {'_id': 'u1', 'parcel_id': None, 'time_series_elec': dict(NEW), 'service_address': '12 MAIN ST',
               'service_zip5': '45402'}], RES)
    st = repair_county(db, 'Test', dry_run=False)
    assert st['address_folds'] == 0 and 'u1' in db['TestElectricalDB'].docs


def test_address_fold_into_parcel_with_two_preingest_docs_is_counted():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': {}},
              {'_id': 'o2', 'parcel_id': 'A', 'time_series_elec': {}},
              {'_id': 's1', 'parcel_id': None, 'time_series_elec': dict(NEW), 'service_address': '12 MAIN ST',
               'service_zip5': '45402', 'source_delivery': 'aug2026'}], RES)
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_multi_preingest'] == 1 and 's1' in db['TestElectricalDB'].docs


def test_unmatched_target_at_write_time_raises_before_any_delete():
    db = _db([{'_id': 'o1', 'parcel_key': '101', 'time_series_elec': dict(OLD)},
              {'_id': 'n1', 'parcel_key': '101', 'time_series_elec': dict(NEW), 'source_delivery': 'aug2026'}])
    coll = db['TestElectricalDB']
    real = coll.bulk_write

    def vanish(ops, ordered=False):
        coll.docs.pop('o1')
        return real(ops, ordered)

    coll.bulk_write = vanish
    with pytest.raises(RuntimeError):
        repair_county(db, 'Test', dry_run=False)
    assert coll.deleted == [] and 'n1' in coll.docs


JAN = {'2025-12-15 00:00:00': 300.0}


def _sur(_id, delivery, ts, addr='9 OAK ST', zip5='45402', utility='AES'):
    return {'_id': _id, 'parcel_id': None, 'time_series_elec': dict(ts), 'utility': utility, 'service_address': addr,
            'service_zip5': zip5, 'source_delivery': delivery, 'last_utility_ingest': delivery}


def test_jan_aug_pair_folds_into_the_aug_doc():
    db = _db([_sur('AES::SMITH', 'jan2026', JAN), _sur('AES::77', 'aug2026', NEW)])
    st = repair_county(db, 'Test', dry_run=False)
    docs = db['TestElectricalDB'].docs
    assert st['delivery_folds'] == 1 and st['deleted'] == 1 and set(docs) == {'AES::77'}
    assert docs['AES::77']['time_series_elec'] == {**JAN, **NEW}


def test_three_docs_at_one_address_are_not_folded():
    db = _db([_sur('j1', 'jan2026', JAN), _sur('a1', 'aug2026', NEW), _sur('a2', 'aug2026', OLD)])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_cross_delivery'] == 3 and st['delivery_folds'] == st['deleted'] == 0
    assert len(db['TestElectricalDB'].docs) == 3


def test_jan_aug_pair_with_conflicting_series_is_skipped():
    db = _db([_sur('j1', 'jan2026', {'2026-05-15 00:00:00': 1.0}), _sur('a1', 'aug2026', NEW)])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_conflict'] == 1 and st['delivery_folds'] == st['deleted'] == 0
    assert db['TestElectricalDB'].docs['a1']['time_series_elec'] == NEW and 'j1' in db['TestElectricalDB'].docs


def test_delivery_order_comes_from_the_tag_not_the_insert_order():
    db = _db([_sur('a1', 'aug2026', NEW), _sur('j1', 'jan2026', JAN)])
    repair_county(db, 'Test', dry_run=False)
    assert set(db['TestElectricalDB'].docs) == {'a1'}


OAK = [{'parcel_id': 'P', 'parcel_key': 'PK', 'address': '9 Oak St', 'parcel_zip': '45402'}]


def test_pair_at_a_no_doc_parcel_folds_then_promotes_the_survivor():
    db = _db([_sur('AES::SMITH', 'jan2026', JAN), _sur('AES::77', 'aug2026', NEW)], OAK)
    st = repair_county(db, 'Test', dry_run=False)
    docs = db['TestElectricalDB'].docs
    assert st['delivery_folds'] == st['promoted'] == st['deleted'] == 1 and set(docs) == {'AES::77'}
    assert docs['AES::77']['parcel_id'] == 'P' and docs['AES::77']['parcel_key'] == 'PK'
    assert docs['AES::77']['time_series_elec'] == {**JAN, **NEW}


def test_single_orphan_surrogate_is_promoted_with_parcel_key():
    db = _db([_sur('s1', 'aug2026', NEW)], OAK)
    st = repair_county(db, 'Test', dry_run=False)
    doc = db['TestElectricalDB'].docs['s1']
    assert st['promoted'] == 1 and st['deleted'] == 0 and (doc['parcel_id'], doc['parcel_key']) == ('P', 'PK')
    assert doc['time_series_elec'] == NEW


def test_promotion_without_parcel_key_sets_only_parcel_id():
    db = _db([_sur('s1', 'aug2026', NEW)], [{'parcel_id': 'P', 'address': '9 Oak St'}])
    repair_county(db, 'Test', dry_run=False)
    doc = db['TestElectricalDB'].docs['s1']
    assert doc['parcel_id'] == 'P' and 'parcel_key' not in doc


def test_two_surrogates_resolving_to_one_no_doc_parcel_are_not_promoted():
    db = _db([_sur('s1', 'aug2026', NEW, utility='FE'), _sur('s2', 'aug2026', OLD, addr='9 OAK STREET')],
             OAK + [{'parcel_id': 'P', 'parcel_key': 'PK', 'address': '9 Oak Street', 'parcel_zip': '45402'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_promote_multi'] == 2 and st['promoted'] == 0
    assert all(d['parcel_id'] is None for d in db['TestElectricalDB'].docs.values())


def test_orphans_reaching_one_parcel_by_different_spellings_are_not_promoted():
    db = _db([_sur('s1', 'aug2026', NEW), _sur('s2', 'aug2026', OLD, addr='5 ELM ST')],
             OAK + [{'parcel_id': 'P', 'address': '5 Elm St'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_promote_multi'] == 2 and st['promoted'] == 0


def test_surrogate_that_would_resolve_to_a_promoted_parcel_blocks_the_promotion():
    db = _db([_sur('s1', 'aug2026', NEW), _sur('s2', 'aug2026', OLD, addr='5 ELM ST')],
             OAK + [{'parcel_id': 'P', 'address': '5 Elm St'}, {'parcel_id': 'Q', 'address': '5 Elm St'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_none'] == 1 and st['skipped_promote_multi'] == 1 and st['promoted'] == 0
    assert repair_county(db, 'Test', dry_run=False) == st


def test_none_outcome_is_counted():
    db = _db([_sur('s1', 'aug2026', NEW)],
             [{'parcel_id': 'A', 'address': '9 Oak St'}, {'parcel_id': 'B', 'address': '9 Oak St'}])
    st = repair_county(db, 'Test', dry_run=False)
    assert st['skipped_none'] == 1 and st['promoted'] == st['deleted'] == 0


ACTIONS = ['parcel_folds', 'address_folds', 'delivery_folds', 'promoted', 'utility_from_fold', 'deleted']


def test_second_run_after_delivery_fold_and_promotion_reports_zeros():
    db = _db([_sur('AES::SMITH', 'jan2026', JAN), _sur('AES::77', 'aug2026', NEW),
              _sur('s9', 'aug2026', OLD, addr='1 X')], OAK)
    dry = repair_county(db, 'Test', dry_run=True)
    assert repair_county(db, 'Test', dry_run=False) == dry
    st = repair_county(db, 'Test', dry_run=False)
    assert {k: st[k] for k in ACTIONS} == dict.fromkeys(ACTIONS, 0) and st['skipped_promote_multi'] == 0


def test_promoted_doc_is_unchanged_by_an_aug_ingest_rerun():
    from src.tools.utility_bills.ingest import process_county
    from src.tools.utility_bills.record import AccountRecord
    db = _db([_sur('AES::SMITH', 'jan2026', JAN), _sur('AES::77', 'aug2026', NEW)], OAK)
    repair_county(db, 'Test', dry_run=False)
    rec = AccountRecord('AES', '', '77', 'X', '9 OAK ST', 'Dayton', 'OH', '45402', [('2026-05-15', 500.0)])
    st = process_county(db, 'Test', [rec], 'aug2026', False, set(db.list_collection_names()), log=lambda *_: None)
    assert st['unchanged'] == 1 and st['matched_parcels'] == 1 and len(db['TestElectricalDB'].docs) == 1
