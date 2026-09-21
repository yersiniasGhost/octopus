"""Parcel identifier normalization, shared by the audit and the T-02 normalizer.

ThermalLoads stores parcel_id as int/Int64 in nine counties while ElectricalDB
stores str, so `get_missing_parcels()` -- which subtracts two raw Python sets --
sees 123 != "123" and reports every parcel missing. T-02 converts the thermal
side to str.

The normalization that decides *what* string a value becomes must be the same
function the audit uses to verify the result, or the verification stops
verifying the thing that was written. Hence `src/tools/parcel_id.py`.

Deliberately NOT the normalization in scripts/enrich_demographics_from_bolt.py:
that one strips dashes and spaces, which would turn "24-01889-000" into
"2401889000" and break the very join this task repairs.
"""
import os
import sys

import pytest
from bson import Int64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.parcel_id import normalize_parcel_id  # noqa: E402


class TestNormalizeParcelId:
    def test_int_becomes_its_decimal_string(self):
        assert normalize_parcel_id(2401889000) == "2401889000"

    def test_bson_int64_becomes_the_same_string_as_int(self):
        assert normalize_parcel_id(Int64(2401889000)) == "2401889000"

    def test_existing_string_is_returned_unchanged(self):
        assert normalize_parcel_id("2401889000") == "2401889000"

    def test_leading_zeros_survive_untouched(self):
        # CuyahogaElectricalDB holds 11,371 leading-zero parcel_ids. Stripping
        # one would make the document permanently unjoinable.
        assert normalize_parcel_id("0123456") == "0123456"

    def test_embedded_punctuation_survives_untouched(self):
        assert normalize_parcel_id("24-01889-000") == "24-01889-000"

    def test_surrounding_whitespace_is_stripped(self):
        assert normalize_parcel_id("  2401889000  ") == "2401889000"

    def test_none_stays_none(self):
        assert normalize_parcel_id(None) is None

    def test_whitespace_only_becomes_none_not_empty_string(self):
        # An empty parcel_id is absence, not a joinable key of "".
        assert normalize_parcel_id("   ") is None

    def test_empty_string_becomes_none(self):
        assert normalize_parcel_id("") is None


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import normalize_thermal_parcel_id_types_tool as norm  # noqa: E402


def _doc(oid, pid):
    return {"_id": oid, "parcel_id": pid}


class TestPlanConversions:
    """The pure planning core: documents in, a decision per document out.

    Kept free of Mongo so every branch is reachable with plain dicts, the same
    way tests/test_thermal_missing_parcels.py exercises get_missing_parcels.
    """

    def test_int_is_planned_for_conversion_to_its_string(self):
        plan = norm.plan_conversions([_doc(1, 2401889000)])
        assert plan.conversions == [(1, "2401889000")]
        assert plan.collisions == []

    def test_bson_int64_is_planned_for_conversion(self):
        plan = norm.plan_conversions([_doc(1, Int64(2401889000))])
        assert plan.conversions == [(1, "2401889000")]

    def test_string_document_is_counted_but_never_written(self):
        plan = norm.plan_conversions([_doc(1, "2401889000")])
        assert plan.conversions == []
        assert plan.already_string == 1

    def test_null_parcel_id_is_neither_converted_nor_a_collision(self):
        plan = norm.plan_conversions([_doc(1, None)])
        assert plan.conversions == []
        assert plan.collisions == []
        assert plan.null_parcel_id == 1

    def test_int_colliding_with_an_existing_string_is_skipped(self):
        # Cuyahoga's 875 duplicates are exactly this shape. Converting would
        # create a genuine duplicate key; merging is T-03's job, not this one.
        plan = norm.plan_conversions([_doc(1, "2401889000"), _doc(2, 2401889000)])
        assert plan.conversions == []
        assert [c["key"] for c in plan.collisions] == ["2401889000"]
        assert plan.collisions[0]["ids"] == [2]

    def test_two_non_strings_normalizing_alike_are_both_skipped(self):
        plan = norm.plan_conversions([_doc(1, 2401889000), _doc(2, Int64(2401889000))])
        assert plan.conversions == []
        assert plan.collisions[0]["ids"] == [1, 2]

    def test_collision_detection_does_not_depend_on_document_order(self):
        # Mongo returns documents in no guaranteed order. A first-come-wins
        # guard would convert doc 2 here and skip it in the test above.
        plan = norm.plan_conversions([_doc(2, 2401889000), _doc(1, "2401889000")])
        assert plan.conversions == []
        assert [c["key"] for c in plan.collisions] == ["2401889000"]

    def test_a_whitespace_padded_string_still_claims_the_key(self):
        plan = norm.plan_conversions([_doc(1, "  2401889000  "), _doc(2, 2401889000)])
        assert plan.conversions == []
        assert plan.collisions[0]["ids"] == [2]

    def test_unrelated_parcels_convert_alongside_a_collision(self):
        plan = norm.plan_conversions(
            [_doc(1, "2401889000"), _doc(2, 2401889000), _doc(3, 1234567890)]
        )
        assert plan.conversions == [(3, "1234567890")]
        assert len(plan.collisions) == 1

    def test_leading_zero_string_is_left_alone_not_rewritten(self):
        plan = norm.plan_conversions([_doc(1, "0123456")])
        assert plan.conversions == []
        assert plan.already_string == 1


class RecordingCollection:
    """Records bulk_write calls instead of performing them."""

    def __init__(self, docs=()):
        self._docs = list(docs)
        self.bulk_calls = []

    def find(self, _filter=None, _projection=None):
        return iter(self._docs)

    def bulk_write(self, requests, ordered=True):
        self.bulk_calls.append(list(requests))

        class Result:
            modified_count = len(requests)

        return Result()


class TestApplyConversions:
    def test_dry_run_issues_no_write(self):
        coll = RecordingCollection()
        modified = norm.apply_conversions(coll, [(1, "2401889000")], execute=False)
        assert coll.bulk_calls == []
        assert modified == 0

    def test_execute_updates_by_id_not_by_parcel_id(self):
        # parcel_id is unindexed until T-05; filtering on it would turn every
        # update into a collection scan. _id is always indexed.
        coll = RecordingCollection()
        norm.apply_conversions(coll, [(1, "2401889000")], execute=True)
        assert len(coll.bulk_calls) == 1
        op = coll.bulk_calls[0][0]
        assert op._filter == {"_id": 1}
        assert op._doc == {"$set": {"parcel_id": "2401889000"}}

    def test_execute_with_nothing_to_convert_issues_no_write(self):
        coll = RecordingCollection()
        assert norm.apply_conversions(coll, [], execute=True) == 0
        assert coll.bulk_calls == []

    def test_conversions_are_batched(self):
        coll = RecordingCollection()
        pairs = [(i, str(i)) for i in range(2500)]
        norm.apply_conversions(coll, pairs, execute=True, batch_size=1000)
        assert [len(c) for c in coll.bulk_calls] == [1000, 1000, 500]
