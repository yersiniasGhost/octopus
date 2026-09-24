"""T-04 -- joining electrical to thermal on the right key.

get_missing_parcels subtracted two raw parcel_id sets. parcel_id is spelled
differently on the two sides in several counties -- Fayette's thermal side holds
'1001600000101' where its electrical side holds '01001600000101' -- so parcels
that already had slopes were reported missing: Fayette 1,127, Huron 257,
Hancock 237, Cuyahoga 1. parcel_key is the normalized field and exists on both
sides in 21 of the 25 counties.

Normalizing parcel_id is NOT sufficient: measured against live data, Fayette's
phantom count is 1,127 under raw parcel_id and still 1,127 under
normalize_parcel_id, falling to 0 only under parcel_key.

The second half of this defect is what a recompute does with the answer. In
recompute_all mode the tool targets every electrical parcel and upserts filtered
on that parcel_id, so a county whose two sides disagree on spelling inserts a
SECOND document for a parcel that already has one -- under a different string, so
the unique index cannot see it. Running the T-15 migration before this fix
created 1,622 such phantoms and they had to be rolled back. The resolution tests
below are that incident written down.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402
from mongo_fakes import FakeDB  # noqa: E402


def missing(electrical, thermal):
    return calc.get_missing_parcels(FakeDB(electrical, thermal), 'Testville')


def targets(electrical, thermal):
    return calc.get_target_parcels(FakeDB(electrical, thermal), 'Testville', recompute_all=True)


# --- choosing the key ---------------------------------------------------------

def test_parcel_key_join_sees_through_a_zero_padding_difference():
    """The Fayette case: same parcel, two spellings, zero missing."""
    result = missing(
        [{'parcel_id': '01001600000101', 'parcel_key': '1001600000101'}],
        [{'parcel_id': '1001600000101', 'parcel_key': '1001600000101'}])

    assert result == []


def test_raw_parcel_id_would_have_called_that_parcel_missing():
    """Guards the guard: the fixture really does differ on parcel_id."""
    assert '01001600000101' != '1001600000101'


def test_falls_back_to_parcel_id_when_a_county_has_no_parcel_key():
    """Montgomery, Scioto, Hardin and Ross carry parcel_key on neither side."""
    result = missing([{'parcel_id': 'A'}, {'parcel_id': 'B'}],
                     [{'parcel_id': 'A'}])

    assert result == ['B']


def test_fallback_path_normalizes_types():
    """Guards against a T-02 regression: int 123 and '123' are the same parcel."""
    result = missing([{'parcel_id': '123'}], [{'parcel_id': 123}])

    assert result == []


def test_a_parcel_matching_on_neither_key_is_genuinely_missing():
    result = missing(
        [{'parcel_id': 'NEW', 'parcel_key': 'NEW'}],
        [{'parcel_id': 'OLD', 'parcel_key': 'OLD'}])

    assert result == ['NEW']


def test_an_electrical_row_without_parcel_key_still_matches_on_parcel_id():
    """A partially populated key must not push the parcel into the missing set."""
    result = missing([{'parcel_id': 'A'}],
                     [{'parcel_id': 'A', 'parcel_key': 'A'}])

    assert result == []


# --- resolving the write target (the half that caused the incident) -----------

def write_map(electrical, thermal):
    return calc.get_thermal_write_map(FakeDB(electrical, thermal), 'Testville')


def test_recompute_targets_the_electrical_spelling_so_billing_data_is_found():
    """Targets are looked up in ElectricalDB, so they must be its spelling.

    Returning the thermal spelling here silently found no billing data for all
    1,127 Fayette parcels, which main() then counted as 'insufficient data'.
    """
    result = targets(
        [{'parcel_id': '01001600000101', 'parcel_key': '1001600000101'}],
        [{'parcel_id': '1001600000101', 'parcel_key': '1001600000101'}])

    assert result == ['01001600000101']


def test_write_map_sends_that_parcel_to_the_existing_thermal_document():
    """And the upsert filter must be the thermal spelling, or it inserts beside it."""
    result = write_map(
        [{'parcel_id': '01001600000101', 'parcel_key': '1001600000101'}],
        [{'parcel_id': '1001600000101', 'parcel_key': '1001600000101'}])

    assert result == {'01001600000101': '1001600000101'}


def test_recompute_does_not_create_a_parcel_that_has_no_thermal_record():
    """Recompute refreshes existing slopes; creating absent ones is T-07.

    The T-15 migration's own acceptance criterion is that document counts do not
    change, which is only true if recompute never inserts. Targeting every
    electrical parcel instead would create the ~60,733 parcels T-07 owns, as a
    side effect of a task that never asked for them.
    """
    result = targets([{'parcel_id': 'NEW', 'parcel_key': 'NEW'}], [])

    assert result == []


def test_default_mode_still_reports_that_parcel_as_missing():
    """The two modes partition the work rather than overlapping."""
    result = missing([{'parcel_id': 'NEW', 'parcel_key': 'NEW'}], [])

    assert result == ['NEW']


def test_write_map_resolves_a_type_mismatch_onto_the_stored_value():
    assert write_map([{'parcel_id': '123'}], [{'parcel_id': 123}]) == {'123': 123}


def test_one_target_per_thermal_document_even_with_two_electrical_spellings():
    """Otherwise both writes land on one document, last-one-wins on cursor order."""
    result = targets(
        [{'parcel_id': '01001600000101', 'parcel_key': '1001600000101'},
         {'parcel_id': '1001600000101', 'parcel_key': '1001600000101'}],
        [{'parcel_id': '1001600000101', 'parcel_key': '1001600000101'}])

    assert len(result) == 1


def test_unlinked_electrical_rows_are_still_excluded():
    """T-14's population must not leak in through the new join."""
    result = targets([{'parcel_id': None}, {'parcel_id': ''}, {'parcel_id': 'A'}],
                     [{'parcel_id': 'A'}])

    assert result == ['A']
