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
sys.path.insert(0, os.path.dirname(__file__))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402
from mongo_fakes import FakeDB  # noqa: E402


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


# --- recompute mode ----------------------------------------------------------

def _targets(electrical, thermal, recompute_all):
    return calc.get_target_parcels(FakeDB(electrical, thermal), 'Testville',
                                   recompute_all=recompute_all)


def test_default_mode_selects_only_parcels_without_thermal_loads():
    result = _targets([{'parcel_id': 'A'}, {'parcel_id': 'B'}], [{'parcel_id': 'A'}], False)

    assert result == ['B']


def test_recompute_mode_selects_parcels_that_already_have_a_record():
    """The single-model migration revisits records that already exist -- only those.

    This previously also asserted 'B', a parcel with no thermal record, which made
    recompute insert as a side effect. That is T-07's work and it broke T-15's own
    criterion that document counts not change; see tests/test_thermal_join_key.py.
    """
    result = _targets([{'parcel_id': 'A'}, {'parcel_id': 'B'}], [{'parcel_id': 'A'}], True)

    assert result == ['A']


def test_recompute_mode_still_excludes_unlinked_records():
    result = _targets([{'parcel_id': None}, {'parcel_id': 'A'}], [{'parcel_id': 'A'}], True)

    assert result == ['A']


def test_recompute_mode_ignores_thermal_records_with_no_electrical_data():
    """A parcel with no billing data cannot be recomputed, only left alone."""
    result = _targets([{'parcel_id': 'A'}], [{'parcel_id': 'A'}, {'parcel_id': 'Z'}], True)

    assert result == ['A']


# --- mixed parcel_id types (T-02) --------------------------------------------

def test_mixed_int_and_string_parcel_ids_sort_without_raising():
    """Cuyahoga carries 1,022 int parcel_ids alongside strings.

    Sorting them directly raises TypeError. Ordering is only for reproducible
    batching, so a string sort key is enough -- the values themselves are left
    untouched, because normalizing the stored type is T-02's migration.
    """
    result = _targets([{'parcel_id': 'B1'}, {'parcel_id': 2401889000},
                       {'parcel_id': 'A1'}],
                      [{'parcel_id': 'B1'}, {'parcel_id': 2401889000},
                       {'parcel_id': 'A1'}], True)

    assert len(result) == 3
    assert 2401889000 in result


def test_missing_mode_also_survives_mixed_types():
    result = _missing([{'parcel_id': 'B1'}, {'parcel_id': 2401889000}], [])

    assert len(result) == 2
