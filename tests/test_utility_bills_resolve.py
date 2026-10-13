"""Shared rules the ingest and the repair use to pick a parcel and a document to merge into."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.parcel_id import ParcelIndex  # noqa: E402
from src.tools.utility_bills.resolve import address_index, merge_target, resolve_address, series_conflict  # noqa: E402

PRE = {'_id': 'o1', 'parcel_id': '0101', 'parcel_key': '101'}
NEW = {'_id': 'n1', 'parcel_id': '101', 'parcel_key': '101', 'source_delivery': 'aug2026'}


def _existing(*groups):
    index = ParcelIndex()
    for docs in groups:
        index.add(docs[0], list(docs))
    return index


def test_merge_target_prefers_the_single_preingest_doc():
    assert merge_target([PRE]) is PRE
    assert merge_target([NEW, PRE]) is PRE
    assert merge_target([PRE, dict(PRE, _id='o2')]) is None
    assert merge_target([NEW, dict(NEW, _id='n2')]) is None


def test_series_conflict_only_on_shared_dates_with_different_readings():
    assert not series_conflict({'2024-01-15 00:00:00': 5.0}, {'2025-01-15 00:00:00': 6.0})
    assert not series_conflict({'2024-01-15 00:00:00': 5.0}, {'2024-01-15 00:00:00': 5.0})
    assert series_conflict({'2024-01-15 00:00:00': 5.0}, {'2024-01-15 00:00:00': 7.0})


def test_address_index_groups_parcels_by_normalized_address():
    idx = address_index([{'parcel_id': 'A', 'address': '12 Main Street'}, {'parcel_id': 'B', 'address': '12 MAIN ST'},
                         {'parcel_id': 'C', 'address': ''}])
    assert [p['parcel_id'] for p in next(iter(idx.values()))] == ['A', 'B'] and len(idx) == 1


def test_unique_address_resolves_without_existing_docs():
    assert resolve_address([{'parcel_id': 'A'}], '43215', _existing()) == ({'parcel_id': 'A'}, 'unique')


def test_one_candidate_with_a_doc_resolves():
    a, b = {'parcel_id': 'A', 'parcel_zip': '43215'}, {'parcel_id': 'B', 'parcel_zip': '43215'}
    assert resolve_address([a, b], '43215', _existing([dict(PRE, parcel_id='A', parcel_key=None)])) == (a, 'resolved')


def test_two_candidate_parcels_resolve_to_none():
    a, b = {'parcel_id': 'A'}, {'parcel_id': 'B'}
    existing = _existing([{'_id': 'x', 'parcel_id': 'A'}], [{'_id': 'y', 'parcel_id': 'B'}])
    assert resolve_address([a, b], '43215', existing) == (None, 'multi')


def test_zip_narrows_candidates_before_counting():
    a, b = {'parcel_id': 'A', 'parcel_zip': '43215-1234'}, {'parcel_id': 'B', 'parcel_zip': '44101'}
    assert resolve_address([a, b], '43215', _existing()) == (a, 'unique')


def test_no_candidate_with_a_doc_is_none():
    assert resolve_address([{'parcel_id': 'A'}, {'parcel_id': 'B'}], '43215', _existing()) == (None, 'none')


def test_duplicate_rows_for_one_parcel_are_a_unique_candidate():
    a = {'parcel_id': 'A', 'parcel_zip': '43215'}
    assert resolve_address([a, dict(a)], '43215', _existing()) == (a, 'unique')
