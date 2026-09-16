"""Unit tests for the collection fingerprint tool.

The fingerprint is the evidence a rollback actually rolled back: a restore that
returns the right document count while dropping an index, or while returning
different documents, must not score as a pass. These tests use a small fake
collection rather than a mock so the production code path is exercised for real.
"""
import pytest

from src.scripts.collection_fingerprint_tool import (
    compare_fingerprints,
    content_hash,
    fingerprint_collection,
    index_fingerprint,
)


class FakeCollection:
    """Duck-types the three pymongo methods the fingerprint reads."""

    def __init__(self, docs, indexes):
        self._docs = docs
        self._indexes = indexes

    def count_documents(self, _filter):
        return len(self._docs)

    def index_information(self):
        return self._indexes

    def find(self, _filter=None, **_kwargs):
        return iter(self._docs)


MORROW_INDEXES = {
    '_id_': {'key': [('_id', 1)], 'v': 2},
    'parcel_key_1': {'key': [('parcel_key', 1)], 'v': 2},
}


# --- content_hash -----------------------------------------------------------

def test_content_hash_is_independent_of_document_order():
    """A restore may return documents in a different order; that is not a change."""
    a = [{'parcel_id': '1', 'kwh_hl_slope': 0.5}, {'parcel_id': '2', 'kwh_hl_slope': 0.9}]
    b = list(reversed(a))

    assert content_hash(a) == content_hash(b)


def test_content_hash_is_independent_of_key_order_within_a_document():
    a = [{'parcel_id': '1', 'kwh_hl_slope': 0.5}]
    b = [{'kwh_hl_slope': 0.5, 'parcel_id': '1'}]

    assert content_hash(a) == content_hash(b)


def test_content_hash_changes_when_a_field_value_changes():
    before = [{'parcel_id': '1', 'kwh_hl_slope': 0.5}]
    after = [{'parcel_id': '1', 'kwh_hl_slope': 0.6}]

    assert content_hash(before) != content_hash(after)


def test_content_hash_changes_when_a_document_is_lost():
    before = [{'parcel_id': '1'}, {'parcel_id': '2'}]
    after = [{'parcel_id': '1'}]

    assert content_hash(before) != content_hash(after)


def test_content_hash_handles_bson_types():
    """Documents carry ObjectId and datetime; plain json.dumps would raise."""
    from datetime import datetime

    from bson import ObjectId

    docs = [{'_id': ObjectId('65f1c2a4b3d4e5f6a7b8c9d0'),
             'calculated_at': datetime(2026, 1, 19),
             'kwh_hl_cl_loads': [{'kwh': 0, 'date': 'NaT'}]}]

    assert isinstance(content_hash(docs), str)


# --- index_fingerprint ------------------------------------------------------

def test_index_fingerprint_records_each_index_key():
    fp = index_fingerprint(MORROW_INDEXES)

    assert fp['_id_'] == {'key': [['_id', 1]], 'unique': False}
    assert fp['parcel_key_1'] == {'key': [['parcel_key', 1]], 'unique': False}


def test_index_fingerprint_records_uniqueness():
    """T-03 adds a unique index; losing the unique flag on restore must be visible."""
    fp = index_fingerprint({'parcel_id_1': {'key': [('parcel_id', 1)], 'unique': True}})

    assert fp['parcel_id_1']['unique'] is True


# --- fingerprint_collection -------------------------------------------------

def test_fingerprint_collection_captures_count_indexes_and_content():
    col = FakeCollection([{'parcel_id': '1'}, {'parcel_id': '2'}], MORROW_INDEXES)

    fp = fingerprint_collection(col)

    assert fp['count'] == 2
    assert set(fp['indexes']) == {'_id_', 'parcel_key_1'}
    assert fp['content_hash'] == content_hash([{'parcel_id': '1'}, {'parcel_id': '2'}])


# --- compare_fingerprints ---------------------------------------------------

def test_compare_reports_no_differences_for_an_unchanged_collection():
    col = FakeCollection([{'parcel_id': '1'}], MORROW_INDEXES)
    fp = fingerprint_collection(col)

    assert compare_fingerprints(fp, fp) == []


def test_compare_reports_a_dropped_index():
    """The Morrow drill's real risk: --drop destroys parcel_key_1 and the count still matches."""
    docs = [{'parcel_id': '1'}]
    before = fingerprint_collection(FakeCollection(docs, MORROW_INDEXES))
    after = fingerprint_collection(FakeCollection(docs, {'_id_': {'key': [('_id', 1)], 'v': 2}}))

    diffs = compare_fingerprints(before, after)

    assert len(diffs) == 1
    assert 'parcel_key_1' in diffs[0]


def test_compare_reports_a_count_change():
    before = fingerprint_collection(FakeCollection([{'parcel_id': '1'}, {'parcel_id': '2'}], {}))
    after = fingerprint_collection(FakeCollection([{'parcel_id': '1'}], {}))

    diffs = compare_fingerprints(before, after)

    assert any('count' in d for d in diffs)


def test_compare_reports_changed_content_at_an_identical_count():
    """Same number of documents, different values - the silent corruption case."""
    before = fingerprint_collection(FakeCollection([{'parcel_id': '1', 'kwh_hl_slope': 0.5}], {}))
    after = fingerprint_collection(FakeCollection([{'parcel_id': '1', 'kwh_hl_slope': 0.0}], {}))

    diffs = compare_fingerprints(before, after)

    assert before['count'] == after['count']
    assert any('content' in d for d in diffs)


def test_compare_reports_an_added_index():
    docs = [{'parcel_id': '1'}]
    before = fingerprint_collection(FakeCollection(docs, {'_id_': {'key': [('_id', 1)], 'v': 2}}))
    after = fingerprint_collection(FakeCollection(docs, MORROW_INDEXES))

    diffs = compare_fingerprints(before, after)

    assert any('parcel_key_1' in d for d in diffs)
