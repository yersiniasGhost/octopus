"""Candidate selection in get_missing_parcels.

ElectricalDB holds 792,059 records inside the 25 thermal counties whose
parcel_id is null: real households with real addresses and real usage that
failed address matching during the AEP/AES/Duke/FirstEnergy pre-enrollment
ingest. They cannot receive thermal loads, because thermal loads are keyed by
parcel -- so they must not appear in the candidate set. They are excluded here,
never deleted: recovering them is T-14's job.

Before this, None entered the candidate set and sorted() raised
TypeError: '<' not supported between instances of 'NoneType' and 'str'
for all six counties T-07 targets.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402


class FakeCollection:
    """Returns every document regardless of filter.

    Deliberately ignores the query filter so these tests exercise the in-Python
    guard rather than a re-implementation of MongoDB semantics. The server-side
    filter in get_missing_parcels is a performance optimisation; the guard is
    what makes the result correct.
    """

    def __init__(self, docs):
        self._docs = docs

    def find(self, _filter=None, _projection=None):
        return iter(self._docs)

    def count_documents(self, _filter=None):
        return len(self._docs)


class FakeDB:
    def __init__(self, electrical, thermal):
        self._cols = {
            'TestvilleElectricalDB': FakeCollection(electrical),
            'TestvilleThermalLoads': FakeCollection(thermal),
        }

    def __getitem__(self, name):
        return self._cols[name]


def _missing(electrical, thermal):
    return calc.get_missing_parcels(FakeDB(electrical, thermal), 'Testville')


def test_null_parcel_ids_do_not_crash_the_sort():
    """The exact failure that blocked all six T-07 counties."""
    result = _missing([{'parcel_id': None}, {'parcel_id': 'B'}, {'parcel_id': 'A'}],
                      [{'parcel_id': 'A'}])

    assert result == ['B']


def test_unlinked_records_are_excluded_from_the_candidate_set():
    result = _missing([{'parcel_id': None}, {'parcel_id': None}, {'parcel_id': 'A'}],
                      [])

    assert result == ['A']


def test_absent_parcel_id_field_is_excluded():
    """Some ingests omit the key rather than storing null."""
    result = _missing([{'account_id': 'AES::SOMEONE'}, {'parcel_id': 'A'}], [])

    assert result == ['A']


def test_empty_string_parcel_id_is_excluded():
    result = _missing([{'parcel_id': ''}, {'parcel_id': 'A'}], [])

    assert result == ['A']


def test_a_county_of_entirely_unlinked_records_yields_no_candidates():
    """Butler, Hamilton, Stark and Summit shape: electrical data, no parcel links."""
    assert _missing([{'parcel_id': None}, {'parcel_id': None}], []) == []


def test_results_are_sorted():
    assert _missing([{'parcel_id': 'C'}, {'parcel_id': 'A'}, {'parcel_id': 'B'}], []) == ['A', 'B', 'C']


def test_thermal_side_nulls_do_not_break_the_difference():
    """A null on the thermal side must not mask a real electrical parcel."""
    result = _missing([{'parcel_id': 'A'}, {'parcel_id': 'B'}],
                      [{'parcel_id': None}, {'parcel_id': 'A'}])

    assert result == ['B']
