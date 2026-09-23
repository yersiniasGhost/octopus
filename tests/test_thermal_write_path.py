"""The thermal write path writes one document per parcel.

Before T-03 this used update_many, because no *ThermalLoads collection carried a
unique index on parcel_id and CuyahogaThermalLoads held 875 duplicate parcels.
Fanning the update across every copy was the only way to stop the duplicates
drifting apart -- each copy received identical corrected values.

T-03 removed the duplicates and made uniqueness a constraint, so the premise is
gone: the filter can now match at most one document, and update_many's extra
semantics only obscure that guarantee. These tests pin the narrower call, so a
later edit cannot quietly reintroduce a multi-document write against a
collection whose unique index would now reject the second copy anyway.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402


class RecordingCollection:
    """Records write calls instead of performing them."""

    def __init__(self, raises=None):
        self.calls = []
        self._raises = raises

    def update_one(self, filter_, update, upsert=False):
        self.calls.append(('update_one', filter_, update, upsert))
        if self._raises:
            raise self._raises
        return None

    def update_many(self, filter_, update, upsert=False):
        self.calls.append(('update_many', filter_, update, upsert))
        if self._raises:
            raise self._raises
        return None


class FakeDB:
    def __init__(self, collection):
        self._collection = collection

    def __getitem__(self, _name):
        return self._collection


BILLING = [{'period': '2026-01', 'kwh': 900, 'hdd': 700, 'cdd': 0}]
MODEL = {'kwh_hl_slope': 1.4, 'kwh_cl_slope': 0.6, 'kwh_intercept': 300, 'kwh_r2': 0.82}


def write(collection, **kwargs):
    return calc.write_thermal_loads(FakeDB(collection), 'Cuyahoga', '1234567890',
                                    BILLING, MODEL, **kwargs)


def test_writes_with_update_one():
    """The unique index guarantees one document, so one document is written."""
    collection = RecordingCollection()
    assert write(collection) is True
    assert [c[0] for c in collection.calls] == ['update_one']


def test_never_uses_update_many():
    """update_many was the pre-T-03 workaround; it must not come back."""
    collection = RecordingCollection()
    write(collection)
    assert 'update_many' not in [c[0] for c in collection.calls]


def test_upserts_so_a_new_parcel_is_created():
    collection = RecordingCollection()
    write(collection)
    _name, filter_, _update, upsert = collection.calls[0]
    assert upsert is True
    assert filter_ == {'parcel_id': '1234567890'}


def test_dry_run_writes_nothing():
    collection = RecordingCollection()
    assert write(collection, dry_run=True) is True
    assert collection.calls == []


def test_driver_failure_is_reported_not_raised():
    collection = RecordingCollection(raises=RuntimeError('duplicate key'))
    assert write(collection) is False
