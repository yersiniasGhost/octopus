"""T-03 -- dedupe duplicate parcel_id documents in *ThermalLoads.

CuyahogaThermalLoads holds 875 parcels twice: T-02 found one document storing
parcel_id as int and another storing the same digits as str, and skipped the
int rather than create a genuine duplicate key. Grouping on the raw value finds
nothing -- 123 != "123" in Python and in MongoDB alike -- so grouping is on
`src.tools.parcel_id.normalize_parcel_id`, the function the audit verifies with.

The keep rule is electric-first by explicit direction (2026-09-21): the survivor
is the document with the better *electric* thermal model, and a gas model on the
losing document does not save it. Gas is re-derived later from billing data, so
the plan *reports* the gas slopes it drops rather than protecting them. This
deviates from the runbook's "never drop a doc carrying real gas slopes" rule;
the deviation is the point of these tests, not an oversight.
"""
import os
import sys

import pytest
from bson import Int64, ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import dedupe_thermal_loads_tool as dedupe  # noqa: E402


def _doc(oid, pid, **fields):
    return {"_id": oid, "parcel_id": pid, **fields}


def _survivor_ids(plan):
    return [g.survivor["_id"] for g in plan.groups]


def _loser_ids(plan):
    return [loser["_id"] for g in plan.groups for loser in g.losers]


class TestGrouping:
    """Which documents are considered the same parcel."""

    def test_int_and_string_of_the_same_digits_are_one_group(self):
        # The whole of Cuyahoga's 875 duplicates are this shape.
        plan = dedupe.plan_dedupe([_doc(1, "1214052"), _doc(2, 1214052)])
        assert len(plan.groups) == 1
        assert plan.groups[0].key == "1214052"

    def test_bson_int64_groups_with_its_string(self):
        plan = dedupe.plan_dedupe([_doc(1, "1214052"), _doc(2, Int64(1214052))])
        assert len(plan.groups) == 1

    def test_a_parcel_appearing_once_forms_no_group(self):
        plan = dedupe.plan_dedupe([_doc(1, "1214052"), _doc(2, "1214054")])
        assert plan.groups == []
        assert plan.removed == 0

    def test_leading_zeros_keep_two_parcels_apart(self):
        # "0123456" and "123456" are different parcels, not a duplicate pair.
        plan = dedupe.plan_dedupe([_doc(1, "0123456"), _doc(2, "123456")])
        assert plan.groups == []

    def test_null_parcel_id_is_counted_but_never_grouped(self):
        plan = dedupe.plan_dedupe([_doc(1, None), _doc(2, None)])
        assert plan.groups == []
        assert plan.null_parcel_id == 2

    def test_three_copies_leave_one_survivor_and_two_losers(self):
        plan = dedupe.plan_dedupe(
            [_doc(1, "1", kwh_hl_r2=0.1), _doc(2, 1, kwh_hl_r2=0.9), _doc(3, "1", kwh_hl_r2=0.5)]
        )
        assert _survivor_ids(plan) == [2]
        assert sorted(_loser_ids(plan)) == [1, 3]
        assert plan.removed == 2


class TestKeepRule:
    """Which copy survives. Order: calculated_at, kwh_hl_r2, loads, determinism."""

    def test_newest_calculated_at_wins(self):
        plan = dedupe.plan_dedupe([
            _doc(1, "1", calculated_at="2026-01-01", kwh_hl_r2=0.9),
            _doc(2, 1, calculated_at="2026-06-01", kwh_hl_r2=0.1),
        ])
        assert _survivor_ids(plan) == [2]

    def test_a_document_without_calculated_at_loses_to_one_with_it(self):
        plan = dedupe.plan_dedupe([
            _doc(1, "1", kwh_hl_r2=0.9),
            _doc(2, 1, calculated_at="2026-01-01", kwh_hl_r2=0.1),
        ])
        assert _survivor_ids(plan) == [2]

    def test_without_calculated_at_the_higher_kwh_r2_wins(self):
        # No document in the real 875 carries calculated_at, so this is the
        # rule that actually decides 390 + 215 of them.
        plan = dedupe.plan_dedupe([_doc(1, "1", kwh_hl_r2=0.07), _doc(2, 1, kwh_hl_r2=0.42)])
        assert _survivor_ids(plan) == [2]

    def test_a_document_with_no_electric_model_loses_to_one_with_it(self):
        # 270 of the 875: a gas-only parcel whose str document has no
        # kwh_hl_r2 and an empty kwh_hl_cl_loads.
        plan = dedupe.plan_dedupe([
            _doc(1, "1", gas_hl_slope=0.0006, kwh_hl_cl_loads=[]),
            _doc(2, 1, kwh_hl_r2=0.007, kwh_hl_cl_loads=[{"kwh": 263}]),
        ])
        assert _survivor_ids(plan) == [2]

    def test_equal_r2_falls_through_to_the_longer_loads_series(self):
        plan = dedupe.plan_dedupe([
            _doc(1, "1", kwh_hl_r2=0.5, kwh_hl_cl_loads=[{"kwh": 1}]),
            _doc(2, 1, kwh_hl_r2=0.5, kwh_hl_cl_loads=[{"kwh": 1}, {"kwh": 2}]),
        ])
        assert _survivor_ids(plan) == [2]

    def test_a_total_tie_keeps_the_string_so_nothing_needs_converting_after(self):
        # T-03 is followed by a T-02 re-run. Keeping the str on a tie leaves
        # that re-run with one less document to touch.
        plan = dedupe.plan_dedupe([_doc(1, 1, kwh_hl_r2=0.5), _doc(2, "1", kwh_hl_r2=0.5)])
        assert _survivor_ids(plan) == [2]

    def test_a_total_tie_between_two_strings_keeps_the_lowest_id(self):
        # Determinism matters: a first-come-wins rule would pick a different
        # survivor on every run, because Mongo guarantees no cursor order.
        a, b = ObjectId("6663766400797bc448748724"), ObjectId("6663766b00797bc448763c0e")
        plan = dedupe.plan_dedupe([_doc(b, "1", kwh_hl_r2=0.5), _doc(a, "1", kwh_hl_r2=0.5)])
        assert _survivor_ids(plan) == [a]

    def test_the_decision_does_not_depend_on_document_order(self):
        forward = dedupe.plan_dedupe([_doc(1, "1", kwh_hl_r2=0.1), _doc(2, 1, kwh_hl_r2=0.9)])
        reverse = dedupe.plan_dedupe([_doc(2, 1, kwh_hl_r2=0.9), _doc(1, "1", kwh_hl_r2=0.1)])
        assert _survivor_ids(forward) == _survivor_ids(reverse) == [2]

    def test_a_non_numeric_r2_is_treated_as_absent_not_compared(self):
        plan = dedupe.plan_dedupe([_doc(1, "1", kwh_hl_r2=None), _doc(2, 1, kwh_hl_r2=0.01)])
        assert _survivor_ids(plan) == [2]


class TestGasIsReportedNotProtected:
    """Electric-first: a gas model does not save a weaker electric document."""

    def test_a_real_gas_slope_does_not_save_a_weaker_electric_document(self):
        plan = dedupe.plan_dedupe([
            _doc(1, "1", kwh_hl_r2=0.01, gas_hl_slope=0.0006),
            _doc(2, 1, kwh_hl_r2=0.90),
        ])
        assert _survivor_ids(plan) == [2]
        assert plan.gas_slopes_dropped == 1

    def test_a_sentinel_gas_slope_is_not_counted_as_dropped(self):
        for sentinel in (-1, 0, None):
            plan = dedupe.plan_dedupe([
                _doc(1, "1", kwh_hl_r2=0.01, gas_hl_slope=sentinel),
                _doc(2, 1, kwh_hl_r2=0.90),
            ])
            assert plan.gas_slopes_dropped == 0, sentinel

    def test_gas_on_the_survivor_is_not_counted_as_dropped(self):
        plan = dedupe.plan_dedupe([
            _doc(1, "1", kwh_hl_r2=0.90, gas_hl_slope=0.0006),
            _doc(2, 1, kwh_hl_r2=0.01),
        ])
        assert plan.gas_slopes_dropped == 0


class TestLosersAreExportable:
    def test_a_loser_is_carried_whole_so_it_can_be_restored_from_the_export(self):
        # The export is what makes the gas re-add a data problem later rather
        # than a restore-and-replay of the whole checkpoint.
        plan = dedupe.plan_dedupe([
            _doc(1, "1", kwh_hl_r2=0.01, gas_hl_slope=0.0006, gas_hl_r2=0.994),
            _doc(2, 1, kwh_hl_r2=0.90),
        ])
        loser = plan.groups[0].losers[0]
        assert loser["gas_hl_slope"] == 0.0006
        assert loser["gas_hl_r2"] == 0.994


class RecordingCollection:
    """Records deletes instead of performing them."""

    def __init__(self, docs=()):
        self._docs = list(docs)
        self.bulk_calls = []
        self.created_indexes = []

    def find(self, _filter=None, _projection=None):
        return iter(self._docs)

    def bulk_write(self, requests, ordered=True):
        self.bulk_calls.append(list(requests))

        class Result:
            deleted_count = len(requests)

        return Result()

    def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, kwargs))
        return "parcel_id_1"

    def index_information(self):
        return {"_id_": {"key": [("_id", 1)]}}

    def drop_index(self, name):
        self.created_indexes.append(("dropped", name))


class TestApplyDedupe:
    def test_dry_run_deletes_nothing(self):
        coll = RecordingCollection()
        plan = dedupe.plan_dedupe([_doc(1, "1", kwh_hl_r2=0.1), _doc(2, 1, kwh_hl_r2=0.9)])
        assert dedupe.apply_dedupe(coll, plan, execute=False) == 0
        assert coll.bulk_calls == []

    def test_execute_deletes_only_the_losers_by_id(self):
        coll = RecordingCollection()
        plan = dedupe.plan_dedupe([_doc(1, "1", kwh_hl_r2=0.1), _doc(2, 1, kwh_hl_r2=0.9)])
        assert dedupe.apply_dedupe(coll, plan, execute=True) == 1
        assert [op._filter for op in coll.bulk_calls[0]] == [{"_id": 1}]

    def test_deletes_are_batched(self):
        coll = RecordingCollection()
        docs = []
        for i in range(2500):
            docs += [_doc(f"a{i}", str(i), kwh_hl_r2=0.1), _doc(f"b{i}", int(i), kwh_hl_r2=0.9)]
        plan = dedupe.plan_dedupe(docs)
        dedupe.apply_dedupe(coll, plan, execute=True, batch_size=1000)
        assert [len(c) for c in coll.bulk_calls] == [1000, 1000, 500]

    def test_nothing_to_delete_issues_no_write(self):
        coll = RecordingCollection()
        plan = dedupe.plan_dedupe([_doc(1, "1")])
        assert dedupe.apply_dedupe(coll, plan, execute=True) == 0
        assert coll.bulk_calls == []


class TestUniqueIndex:
    """A unique index on parcel_id is only a constraint once types agree."""

    def test_creation_refuses_while_normalized_duplicates_remain(self):
        # MongoDB compares BSON type, so int 123 and "123" are different index
        # keys: createIndex would SUCCEED here and report the collection clean.
        # Refusing first is what makes the index mean something.
        coll = RecordingCollection([_doc(1, "1"), _doc(2, 1)])
        with pytest.raises(dedupe.DuplicatesRemain):
            dedupe.create_unique_parcel_id_index(coll, execute=True)
        assert coll.created_indexes == []

    def test_creation_proceeds_once_every_normalized_key_is_unique(self):
        coll = RecordingCollection([_doc(1, "1"), _doc(2, "2")])
        dedupe.create_unique_parcel_id_index(coll, execute=True)
        keys, kwargs = coll.created_indexes[0]
        assert keys == [("parcel_id", 1)]
        assert kwargs["unique"] is True

    def test_dry_run_creates_nothing(self):
        coll = RecordingCollection([_doc(1, "1"), _doc(2, "2")])
        dedupe.create_unique_parcel_id_index(coll, execute=False)
        assert coll.created_indexes == []

    def test_an_existing_non_unique_index_is_dropped_first(self):
        # FayetteThermalLoads already carries a non-unique parcel_id_1, and
        # MongoDB will not convert an index to unique in place.
        coll = RecordingCollection([_doc(1, "1"), _doc(2, "2")])
        coll.index_information = lambda: {
            "_id_": {"key": [("_id", 1)]},
            "parcel_id_1": {"key": [("parcel_id", 1)], "background": True},
        }
        dedupe.create_unique_parcel_id_index(coll, execute=True)
        assert coll.created_indexes[0] == ("dropped", "parcel_id_1")
        assert coll.created_indexes[1][1]["unique"] is True

    def test_an_index_that_is_already_unique_is_left_alone(self):
        coll = RecordingCollection([_doc(1, "1")])
        coll.index_information = lambda: {
            "parcel_id_1": {"key": [("parcel_id", 1)], "unique": True},
        }
        dedupe.create_unique_parcel_id_index(coll, execute=True)
        assert coll.created_indexes == []


class TestCollisionExportCrossCheck:
    """T-02 already enumerated every contested key. Diverging means drift."""

    def test_matching_keys_pass(self):
        plan = dedupe.plan_dedupe([_doc(1, "1214052"), _doc(2, 1214052)])
        dedupe.cross_check_against_t02(plan, {"1214052"})

    def test_a_key_t02_never_saw_is_reported(self):
        plan = dedupe.plan_dedupe([_doc(1, "1214052"), _doc(2, 1214052)])
        with pytest.raises(dedupe.CollisionSetMismatch) as exc:
            dedupe.cross_check_against_t02(plan, {"9999999"})
        assert "1214052" in str(exc.value)

    def test_a_key_t02_saw_that_is_no_longer_duplicated_is_reported(self):
        plan = dedupe.plan_dedupe([_doc(1, "1214052"), _doc(2, 1214052)])
        with pytest.raises(dedupe.CollisionSetMismatch):
            dedupe.cross_check_against_t02(plan, {"1214052", "1214054"})


class TwoPassCollection:
    """Records every find() so the two passes can be told apart.

    CuyahogaThermalLoads is 446 MB of BSON across 260,939 documents. Pulling all
    of them to find 875 duplicates would cost gigabytes of Python dicts, so the
    first pass reads parcel_id alone and the second fetches whole documents by
    _id -- the only field indexed on every collection.
    """

    def __init__(self, docs):
        self._docs = list(docs)
        self.finds = []

    def find(self, filter=None, projection=None):
        self.finds.append({"filter": filter, "projection": projection})
        docs = self._docs
        if filter and "_id" in filter:
            wanted = set(filter["_id"]["$in"])
            docs = [d for d in docs if d["_id"] in wanted]
        if projection:
            docs = [{k: v for k, v in d.items() if k in projection or k == "_id"} for d in docs]
        return iter(docs)

    def bulk_write(self, requests, ordered=True):
        class Result:
            deleted_count = len(requests)

        return Result()


class TestDedupeCountyReadsInTwoPasses:
    def _db(self, docs):
        return {"CuyahogaThermalLoads": TwoPassCollection(docs)}

    def test_the_first_pass_reads_parcel_id_alone(self):
        db = self._db([_doc(1, "1", kwh_hl_cl_loads=[{"kwh": 1}]), _doc(2, 1)])
        dedupe.dedupe_county(db, "Cuyahoga")
        assert db["CuyahogaThermalLoads"].finds[0]["projection"] == {"parcel_id": 1}

    def test_whole_documents_are_fetched_only_for_duplicated_parcels(self):
        db = self._db([_doc(1, "1"), _doc(2, 1), _doc(3, "999")])
        dedupe.dedupe_county(db, "Cuyahoga")
        second = db["CuyahogaThermalLoads"].finds[1]
        assert sorted(second["filter"]["_id"]["$in"]) == [1, 2]
        assert second["projection"] is None

    def test_the_survivor_is_chosen_from_the_whole_document_not_the_projection(self):
        # Ranking on a projected document would see no kwh_hl_r2 anywhere and
        # fall through to the _id tie-break, silently picking the wrong copy.
        db = self._db([_doc(1, "1", kwh_hl_r2=0.1), _doc(2, 1, kwh_hl_r2=0.9)])
        plan = dedupe.dedupe_county(db, "Cuyahoga")["plan"]
        assert _survivor_ids(plan) == [2]

    def test_the_plan_counts_the_whole_collection_not_just_the_duplicates(self):
        db = self._db([_doc(1, "1"), _doc(2, 1), _doc(3, "999"), _doc(4, None)])
        plan = dedupe.dedupe_county(db, "Cuyahoga")["plan"]
        assert plan.examined == 4
        assert plan.null_parcel_id == 1
        assert plan.removed == 1

    def test_a_collection_with_no_duplicates_makes_no_second_pass(self):
        db = self._db([_doc(1, "1"), _doc(2, "2")])
        dedupe.dedupe_county(db, "Cuyahoga")
        assert len(db["CuyahogaThermalLoads"].finds) == 1
