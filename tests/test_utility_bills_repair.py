"""repair_county folds ingest-created duplicates into their pre-ingest document and deletes them."""
import sys
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
