# Bulk Need Analysis — P2 Implementation Plan (ingest repair + all 88 counties)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the 2026-08-19 electric-bill ingest defects in `{County}ElectricalDB`, then build
`analysis_households` for all 88 Ohio counties with the P2 rule changes, a per-county `analysis_coverage`
collection and a reconciliation tool.

**Architecture:** Two strands. (1) `src/tools/utility_bills/` gets shared parcel-resolution helpers
(`resolve.py`), fixed matching in `ingest.py`, and a database-only fold pass (`repair.py`) driven by
`scripts/repair_electrical_ingest_tool.py`; the `utility` backfill is the fixed ingest re-run over the
existing delivery files. (2) `src/analysis_engine/` gains registry entries (`nonres_kwh`, new thermal fields,
an `owner_age` fallback, AES rate, HUD limits for 88 counties), household/rule changes, extra gates,
`build --all`, `coverage.py` and `reconcile.py`. Pure functions stay pure and are unit-tested with fakes.

**Tech Stack:** Python 3.10 (`venv`), pymongo 4.15.3, pytest, `openpyxl` (already used by other tools; check
`pip show openpyxl` in Task 4 before relying on it). No new dependencies.

**Spec:** `.claude_docs/20261008_1713_bulk_need_analysis_design.md` — read **§15** (P2 decisions, approved
2026-10-13) first, then §14 and §6. Evidence scripts (uncommitted, user-owned until they say otherwise):
`scripts/profile_need_analysis_counties_tool.py`, `scripts/check_preingest_meter_duplication_tool.py`.

## Global Constraints

- Database `empower_development` via `src.tools.mongo.get_empower_db()`. Don't use `emailoctopus_db`.
- **The analysis engine never writes to a source collection.** The only source writes in P2 are the ingest repair
  (Task 3) and the `utility` backfill (Task 3), both on `{County}ElectricalDB`, both dry by default, both run live
  only after a gzip backup exists and the user gives an explicit go-ahead.
- Gas is excluded entirely; heat fuel is measured only (§14.1–2). Unknown is never coerced to 0.
- Stale = no read in 24 months → usage unknown, no computed bill. Usable thermal fit: `thermal_r2 ≥ 0.5`,
  `hl_slope ≥ 0`, not multi-unit.
- Surrogate meter `_id`s are HMAC-hashed with `ANALYSIS_ID_KEY` (`src/analysis_engine/ids.py`). Never rotate the key.
- No names, emails, phones, addresses, account numbers or `participant_id` in any analysis document, build record,
  coverage document or report printed by these tools. Repair reports print counts only.
- Stored percents: `fpl_pct`/`ami_pct` ceil, burden floored to 0.1, each after `round(x, 6)` (unchanged).
- `nonres_kwh` = **50000**; a household is `nonres` when `annual_kwh > 50000` (50,000 itself is not flagged).
- Thresholds and tables are read from the registry, never restated as literals in engine code.
- p99 document size < 1024 bytes (`bson.encode`).
- Python style: compact signatures on 1–2 lines (break only past 120 chars); match the docstring density of
  `src/tools/parcel_id.py`. DRY: reuse `normalize_address`, `ParcelIndex`, `identity`, `monthly_stats`,
  `summarize_usage`, `collection_name`; never copy them.
- Tests: `source venv/bin/activate && python -m pytest tests/ -q -o addopts=""`. Baseline: **369 passed**.
- Unrelated working-tree changes belong to the user and are **never staged**: `.claude_docs/script_descriptions.md`,
  `.gitignore`, `scripts/create_user.py`, `scripts/enrich_participants_franklin_demographics_tool.py`, `schema.md`,
  the kickoff docs, and untracked `scripts/*_tool.py` (including the two evidence scripts above). Stage exact paths
  only; never `git add -A` / `git add .`. New scripts this plan creates are listed in `.claude_docs/script_descriptions.md`
  only if the user agrees (that file carries their edits) — otherwise list them in the results doc.
- Branch `feature/need-analysis-p2`. Commit messages end with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Registry files are shared with bolt-od (`lib/analysis/registry/`); bolt-od re-copies them in P3. Do not edit bolt-od.

## Review Focus

1. **Condo address** (one service address → three residential parcels, two of which hold ElectricalDB docs): the
   ingest and the repair both leave it unmatched; nothing is folded. Pinned in Task 1
   (`test_two_candidate_parcels_resolve_to_none`) and Task 2 (`test_fold_skips_address_with_two_candidates`).
2. **Legitimate multi-meter parcel** (two pre-ingest docs on one parcel, plus one ingest-created doc): neither
   pre-ingest doc absorbs the new doc and none is deleted. Pinned in Task 2
   (`test_parcel_with_two_preingest_docs_is_not_folded`).
3. **Repair run twice**: the second dry run reports zero folds, zero deletes, zero utility writes. Pinned in Task 2
   (`test_repair_is_idempotent`) and Task 3 Step 6.
4. **Meter at exactly 50,000 kWh and at 50,001 kWh** with a vendor cost present: 50,000 is ranked normally; 50,001
   is `nonres`, out of the usage distribution, has no rate-computed cost, but keeps a vendor-cost burden. Pinned in
   Task 5 (`test_nonres_boundary`, `test_nonres_keeps_vendor_cost`).
5. **New county with a residential field the registry has never seen** (e.g. Ottawa `land_use`): the county build
   fails with the field named, other counties still build, exit code 1. Pinned in Task 6
   (`test_unmapped_field_fails_only_that_county`).

---

## File map

| File | Responsibility |
|---|---|
| `src/tools/parcel_id.py` (modify) | gains `identity()` (moved from `analysis_engine.sources`, re-exported there) |
| `src/tools/utility_bills/resolve.py` (create) | shared rules: `merge_target`, `series_conflict`, `address_index`, `resolve_address` |
| `src/tools/utility_bills/ingest.py` (modify) | matching via `ParcelIndex`/`resolve.py`; writes `utility`; writes `parcel_key` on new linked docs |
| `src/tools/utility_bills/repair.py` (create) | database-only fold of type-(b) and type-(c) duplicates for one county |
| `scripts/repair_electrical_ingest_tool.py` (create) | CLI: dry-run/execute repair per county, markdown report |
| `src/analysis_engine/registry/rules.json` (modify) | version, `usage.nonres_kwh`, burden wording, AES rate, HUD 88 counties |
| `src/analysis_engine/registry/fields.json` (modify) | version, `nonres`, `kwh_hl_intercept`, `kwh_hl_r2`, `kwh_cl_r2`, `owner_senior` |
| `src/analysis_engine/registry.py` (modify) | `FieldSpec.fallback_for`, validation of it |
| `src/analysis_engine/normalize.py` (modify) | `senior_age` transform |
| `scripts/build_hud_limits_table_tool.py` (create) | HUD FY2026 xlsx → `hud_low_income_fy2026.counties` JSON for 88 counties |
| `src/analysis_engine/household.py` (modify) | `nonres`, fallbacks, NaN-safe `utility` |
| `src/analysis_engine/rules.py` (modify) | `usage_ok` excludes `nonres` |
| `src/analysis_engine/archetypes.py` (modify) | denominators exclude `nonres`; `proxy_mask()` |
| `src/analysis_engine/report.py` (modify) | proxy split per archetype; `no measured source` |
| `src/analysis_engine/build.py` (modify) | new stats, gates (`nonres`, county, unmapped), coverage counters |
| `src/analysis_engine/coverage.py` (create) | assemble one `analysis_coverage` document per county |
| `src/analysis_engine/store.py` (modify) | `write_coverage` on both stores |
| `src/analysis_engine/sources.py` (modify) | re-export `identity`; `countykeys_collections()` |
| `src/analysis_engine/reconcile.py` (create) | independent source recounts vs `analysis_coverage` |
| `src/analysis_engine/cli.py` (modify) | `build --all`, `reconcile` subcommand |
| `scripts/scan_heat_type_fields_tool.py` (create) | read-only scan of Residential collections for heating-type fields |
| `tests/test_utility_bills_resolve.py`, `tests/test_utility_bills_repair.py`, `tests/test_utility_bills_ingest.py` (create) | ingest/repair tests |
| `tests/utility_fakes.py` (create) | a writable fake collection (`find`, `bulk_write`, `delete_many`) |
| `tests/test_analysis_coverage.py`, `tests/test_analysis_reconcile.py` (create) | coverage and reconciliation tests |
| existing `tests/test_analysis_*.py` (modify) | new cases listed per task |

---

### Task 1: Shared resolution rules and the ingest fix

**Files:**
- Modify: `src/tools/parcel_id.py` (add `identity`), `src/analysis_engine/sources.py` (import it from there)
- Create: `src/tools/utility_bills/resolve.py`, `tests/utility_fakes.py`, `tests/test_utility_bills_resolve.py`,
  `tests/test_utility_bills_ingest.py`
- Modify: `src/tools/utility_bills/ingest.py` (`process_county`, steps 2–4)

**Interfaces:**
- Produces: `identity(doc) -> Optional[Tuple[str, str]]` in `src.tools.parcel_id`;
  `merge_target(docs: List[Dict]) -> Optional[Dict]`; `series_conflict(a: Dict, b: Dict) -> bool`;
  `address_index(res_docs: Iterable[Dict]) -> Dict[str, List[Dict]]`;
  `resolve_address(parcels: List[Dict], zip5: str, existing: ParcelIndex) -> Tuple[Optional[Dict], str]`
  (returns `(residential_doc, 'unique'|'resolved'|'none'|'multi')`). `existing` maps a parcel to the list of its
  ElectricalDB docs.

Rules (spec §15.3):
- `merge_target`: one doc → that doc; several → the single doc **without** `source_delivery` (pre-ingest), else `None`.
- `series_conflict`: any shared date key whose readings differ.
- `resolve_address`: narrow the address's parcels to those whose `parcel_zip[:5]` equals `zip5` (parcels with no
  zip stay); one parcel → `'unique'`; several → keep those that resolve in `existing` to a non-`None`
  `merge_target`; exactly one → `'resolved'`; zero → `'none'`; more → `'multi'`.

- [ ] **Step 1: Move `identity`.** Cut `identity` from `src/analysis_engine/sources.py` into
  `src/tools/parcel_id.py` (below `parcel_id_of`, same docstring), and in `sources.py` write
  `from src.tools.parcel_id import ParcelIndex, identity, parcel_id_of, parcel_key_of`. Run the full suite: 369 pass.

- [ ] **Step 2: Write the failing resolve tests** in `tests/test_utility_bills_resolve.py`:

```python
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
```

- [ ] **Step 3: Run** `python -m pytest tests/test_utility_bills_resolve.py -q -o addopts=""` → FAIL (module missing).

- [ ] **Step 4: Implement** `src/tools/utility_bills/resolve.py`:

```python
"""Which parcel an ingested address belongs to, and which ElectricalDB document absorbs its readings.

Shared by ingest.py (new deliveries) and repair.py (folding the 2026-08-19 duplicates) so both apply one rule
(spec 20261008_1713 §15.3).
"""
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from src.tools.address_normalization import normalize_address
from src.tools.parcel_id import ParcelIndex


def merge_target(docs: List[Dict]) -> Optional[Dict]:
    """The one document to merge into: the only doc, else the only pre-ingest doc (no source_delivery)."""
    if len(docs) == 1:
        return docs[0]
    pre = [d for d in docs if not d.get('source_delivery')]
    return pre[0] if len(pre) == 1 else None


def series_conflict(a: Dict, b: Dict) -> bool:
    return any(a[k] != b[k] for k in a.keys() & b.keys())


def address_index(res_docs: Iterable[Dict]) -> Dict[str, List[Dict]]:
    index = defaultdict(list)
    for doc in res_docs:
        naddr = normalize_address(doc.get('address') or '')
        if naddr:
            index[naddr].append(doc)
    return index


def resolve_address(parcels: List[Dict], zip5: str, existing: ParcelIndex) -> Tuple[Optional[Dict], str]:
    """The residential parcel an address belongs to, with how it was decided (unique/resolved/none/multi)."""
    narrowed = [p for p in parcels if not p.get('parcel_zip') or str(p['parcel_zip'])[:5] == zip5] or parcels
    if len(narrowed) == 1:
        return narrowed[0], 'unique'
    with_doc = [p for p in narrowed if merge_target(existing.resolve(p)[0] or [])]
    if len(with_doc) == 1:
        return with_doc[0], 'resolved'
    return None, 'none' if not with_doc else 'multi'
```

(If `ParcelIndex.resolve` returns `(None, …)` for a miss, `or []` covers it; check its last line and keep the
expression consistent with it.)

- [ ] **Step 5: Run the resolve tests** → PASS.

- [ ] **Step 6: Write the writable fake** `tests/utility_fakes.py`:

```python
"""A writable in-memory collection for ingest and repair tests (find, bulk_write of UpdateOne, delete_many)."""


class WritableCollection:
    def __init__(self, docs):
        self.docs = {d['_id']: dict(d) for d in docs}
        self.deleted = []

    def find(self, _filter=None, _projection=None):
        return [dict(d) for d in self.docs.values()]

    def bulk_write(self, ops, ordered=False):
        for op in ops:
            flt, update, upsert = op._filter, op._doc, op._upsert
            match = [d for d in self.docs.values() if all(d.get(k) == v for k, v in flt.items())]
            if match:
                match[0].update(update['$set'])
            elif upsert:
                doc = {**flt, **update['$set']}
                doc.setdefault('_id', f"new{len(self.docs)}")
                self.docs[doc['_id']] = doc

    def delete_many(self, flt):
        for _id in flt['_id']['$in']:
            self.deleted.append(self.docs.pop(_id))


class WritableDB:
    def __init__(self, collections):
        self.collections = {name: WritableCollection(docs) for name, docs in collections.items()}

    def __getitem__(self, name):
        return self.collections[name]

    def list_collection_names(self):
        return list(self.collections)
```

(pymongo's `UpdateOne` keeps `_filter`, `_doc`, `_upsert`; verify with
`python -c "from pymongo import UpdateOne; print(vars(UpdateOne({'a':1},{'$set':{}})))"` and adjust the attribute
names if they differ.)

- [ ] **Step 7: Write the failing ingest tests** in `tests/test_utility_bills_ingest.py`:

```python
"""process_county: matched merges write utility, parcel_key spellings match, ambiguous addresses resolve once."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.utility_bills.ingest import process_county  # noqa: E402
from src.tools.utility_bills.record import AccountRecord  # noqa: E402
from tests.utility_fakes import WritableDB  # noqa: E402

D1 = '2026-05-15 00:00:00'


def _rec(addr='12 MAIN ST', zip5='43215', kwh=500.0, account='A1'):
    return AccountRecord('FE', 'CEI', account, 'X', addr, 'Columbus', 'OH', zip5, [('2026-05-15', kwh)])


def _db(elec, res):
    return WritableDB({'TestElectricalDB': elec, 'TestCountyResidential': res})


def _run(db, recs):
    return process_county(db, 'Test', recs, 'aug2026', False, set(db.list_collection_names()), log=lambda *_: None)


def test_matched_existing_doc_gets_utility_even_without_new_dates():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'time_series_elec': {D1: 500.0}}],
             [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'}])
    st = _run(db, [_rec()])
    assert db['TestElectricalDB'].docs['o1']['utility'] == 'FE' and st['utility_set'] == 1


def test_parcel_key_spelling_finds_existing_doc():
    db = _db([{'_id': 'o1', 'parcel_id': '0101', 'parcel_key': '101', 'time_series_elec': {}}],
             [{'_id': 'r1', 'parcel_id': '101', 'parcel_key': '101', 'address': '12 Main St'}])
    _run(db, [_rec()])
    assert set(db['TestElectricalDB'].docs) == {'o1'}
    assert db['TestElectricalDB'].docs['o1']['time_series_elec'][D1] == 500.0


def test_new_linked_doc_carries_parcel_key():
    db = _db([], [{'_id': 'r1', 'parcel_id': '101', 'parcel_key': '101', 'address': '12 Main St'}])
    _run(db, [_rec()])
    (doc,) = db['TestElectricalDB'].docs.values()
    assert doc['parcel_id'] == '101' and doc['parcel_key'] == '101' and doc['utility'] == 'FE'


def test_ambiguous_address_merges_into_the_single_candidate_with_a_doc():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': {'2024-05-15 00:00:00': 400.0}}],
             [{'_id': 'r1', 'parcel_id': 'A', 'address': '12 Main St'},
              {'_id': 'r2', 'parcel_id': 'B', 'address': '12 Main St'}])
    st = _run(db, [_rec()])
    assert set(db['TestElectricalDB'].docs) == {'o1'} and st['ambiguous_resolved'] == 1


def test_ambiguous_address_with_conflicting_series_stays_unmatched():
    db = _db([{'_id': 'o1', 'parcel_id': 'A', 'time_series_elec': {D1: 999.0}}],
             [{'_id': 'r1', 'parcel_id': 'A', 'address': '12 Main St'},
              {'_id': 'r2', 'parcel_id': 'B', 'address': '12 Main St'}])
    st = _run(db, [_rec()])
    assert 'FE:CEI:A1' in db['TestElectricalDB'].docs and st['ambiguous_conflict'] == 1
    assert db['TestElectricalDB'].docs['o1']['time_series_elec'] == {D1: 999.0}


def test_second_run_changes_nothing():
    db = _db([{'_id': 'o1', 'parcel_id': 'P1', 'time_series_elec': {}}],
             [{'_id': 'r1', 'parcel_id': 'P1', 'address': '12 Main St'}])
    _run(db, [_rec()])
    st = _run(db, [_rec()])
    assert st.get('docs_updated', 0) == 0 and st.get('utility_set', 0) == 0 and st['unchanged'] == 1
```

- [ ] **Step 8: Run** them → FAIL (`utility_set` missing, parcel_key spelling creates a second doc, etc.).

- [ ] **Step 9: Implement in `ingest.py` `process_county`.** Replace steps 2–4 with:
  - Step 2: `addr_parcels = address_index(db[res_name].find({}, {'parcel_id': 1, 'parcel_key': 1, 'address': 1,
    'parcel_zip': 1}))` when the Residential collection exists, else `{}`.
  - Step 4 moves before step 3: read existing docs with projection
    `{'parcel_id': 1, 'parcel_key': 1, 'time_series_elec': 1, 'utility': 1, 'source_delivery': 1}`; linked docs
    (`identity(doc) is not None`) are grouped by `identity` and added to a `ParcelIndex` as lists
    (`existing.add(group[0], group)`); unlinked docs go into `surrogates[_id] = doc`.
  - Step 3: for each `naddr, slot`: `parcel, how = resolve_address(addr_parcels.get(naddr, []), slot['rec'].zip5,
    existing)` (skip the call when the address has no parcels). Count `st['ambiguous_resolved']` for `'resolved'`,
    `st['ambiguous_address']` for `'multi'`. Key matched slots by `('p', parcel['_id'])` holding the residential
    doc; unmatched by `('s', rec.surrogate_key())`.
  - Diff/merge: for a matched slot, `target = merge_target(existing.resolve(parcel)[0] or [])`. For
    `how == 'resolved'` and `series_conflict(slot['dates'], target['time_series_elec'] or {})` → count
    `st['ambiguous_conflict']` and treat the slot as unmatched (surrogate). With a target: `new` = dates not in the
    target's series; `$set` holds `time_series_elec`/`monthly_stats`/`last_utility_ingest` only when `new`, plus
    `utility: rec.utility` when the target lacks `utility` (count `st['utility_set']`); no `$set` at all → `unchanged`.
    Without a target (no doc, or several pre-ingest docs on the parcel) → create a new linked doc with
    `parcel_id` and `parcel_key` from the residential doc (omit `parcel_key` if the residential doc has none).
  - Surrogate slots: unchanged behaviour (upsert by `_id`), plus `utility` set when an existing surrogate lacks it.
  - Keep the module docstring's merge policy text accurate (add: "matched docs also gain a missing `utility`").

- [ ] **Step 10: Run** the ingest and resolve tests → PASS; then the full suite → 369 + 14 = **383 pass**.

- [ ] **Step 11: Commit**

```bash
git add src/tools/parcel_id.py src/analysis_engine/sources.py src/tools/utility_bills/resolve.py \
  src/tools/utility_bills/ingest.py tests/utility_fakes.py tests/test_utility_bills_resolve.py \
  tests/test_utility_bills_ingest.py
git commit -m "fix(ingest): match parcels by parcel_key, resolve shared addresses, write utility on merge

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Database-only repair of existing duplicates

**Files:**
- Create: `src/tools/utility_bills/repair.py`, `scripts/repair_electrical_ingest_tool.py`,
  `tests/test_utility_bills_repair.py`

**Interfaces:**
- Consumes: `merge_target`, `series_conflict`, `address_index`, `resolve_address` (Task 1); `identity`,
  `ParcelIndex`; `monthly_stats` from `ingest.py`.
- Produces: `repair_county(db, county: str, dry_run: bool) -> Dict[str, int]` with keys `parcel_folds`,
  `address_folds`, `utility_from_fold`, `deleted`, `skipped_multi_preingest`, `skipped_conflict`,
  `skipped_multi_candidate`.

Fold rules (spec §15.3): **type (b)** — linked docs grouped by `identity`; every ingest-created doc
(`source_delivery` present) in a group folds into `merge_target(group)` when that is a pre-ingest doc; a group with
two or more pre-ingest docs is skipped (`skipped_multi_preingest`). **Type (c)** — each unlinked doc with
`service_address` resolves through `resolve_address(addr_parcels[normalize_address(service_address)],
service_zip5, existing)`; only `'resolved'` or `'unique'` with a `merge_target` fold. A fold unions the series
(skip with `skipped_conflict` when `series_conflict`), recomputes `monthly_stats`, sets `utility` and
`last_utility_ingest` from the folded doc when the target lacks them, and deletes the folded doc.

- [ ] **Step 1: Write the failing tests** `tests/test_utility_bills_repair.py`:

```python
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
```

- [ ] **Step 2: Run** → FAIL (module missing).

- [ ] **Step 3: Implement** `src/tools/utility_bills/repair.py` (~90 lines): load the county's ElectricalDB docs
  once; build the `ParcelIndex` of linked groups and `address_index` of the Residential collection (if present);
  plan folds in memory as `(target_id, folded_doc)` pairs (a target may absorb several docs — merge them in order,
  checking conflicts against the accumulated series); in live mode apply one `UpdateOne({'_id': target},
  {'$set': {...}})` per target via `bulk_write` in batches of 1000, then `delete_many({'_id': {'$in': ids}})` in
  batches of 10000 **only for docs whose target update was planned**. Never print addresses.

- [ ] **Step 4: Implement** `scripts/repair_electrical_ingest_tool.py`: `--county` (repeatable; default every
  `*ElectricalDB` collection), `--execute` (default dry run), `--report PATH` (markdown table of the counters per
  county plus totals). Same structure as `scripts/ingest_electric_bills_tool.py` (reuse its `fmt_table`; import it
  rather than copying). Module docstring states: "Requires a fresh backup; see the P2 plan Task 3."

- [ ] **Step 5: Run** the repair tests → PASS; full suite → **390 pass**.

- [ ] **Step 6: Commit**

```bash
git add src/tools/utility_bills/repair.py scripts/repair_electrical_ingest_tool.py tests/test_utility_bills_repair.py
git commit -m "feat(ingest): add database-only repair that folds 2026-08-19 duplicates

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Run the repair and the utility backfill (live data; two user gates)

No code. Each step's output goes into `.claude_docs/<YYYYMMDD_HHMM>_need_analysis_p2_repair.md`.

- [ ] **Step 1: Backup.**
  `mongodump --db empower_development --gzip --archive=backups/empower_development_<YYYYMMDD>_pre_p2_repair.archive.gz`
  restricted to the ElectricalDB collections (`--nsInclude 'empower_development.*ElectricalDB'`). Verify with
  `ls -la backups/` (expect roughly the size of the 2026-08-19 backup) and
  `mongorestore --gzip --archive=<file> --dryRun --nsInclude 'empower_development.*ElectricalDB' -v 2>&1 | tail -3`.
- [ ] **Step 2: Repair dry run.** `python scripts/repair_electrical_ingest_tool.py --report <scratch>/repair_dry.md`.
  Expect type-(b) folds near 415 (Huron 257, Cuyahoga 158) and type-(c) folds up to ~28k in the 23 counties plus
  ~10k in Cuyahoga and ~1.2k in Franklin. Any county with skips above 10% of its folds: report the counts.
- [ ] **Step 3: Backfill dry run.** `python scripts/ingest_electric_bills_tool.py --delivery jan2026 --delivery aug2026
  --report <scratch>/backfill_dry.md` (no `--execute`). Expect `utility_set` near 228k (23 counties) + 396k (P1
  counties) and `docs_updated` ≈ 0 (readings were merged on 2026-08-19).
- [ ] **Step 4: STOP — bring both dry-run reports to the user and wait for an explicit go-ahead.**
- [ ] **Step 5: Live.** Repair with `--execute`, then the backfill with `--execute`.
- [ ] **Step 6: Verify.** Re-run both dry runs: all fold/delete/utility counters 0.
  Re-run `scripts/check_preingest_meter_duplication_tool.py`: parcel overlaps 0; address overlaps only the skipped
  counts; no-utility docs ≈ only stale orphans (last read before 2024-10).
- [ ] **Step 7:** Commit the repair results doc (`git add` its exact path).

---

### Task 4: Registry for P2 (rules, fields, AES, HUD 88 counties)

**Files:**
- Modify: `src/analysis_engine/registry/rules.json`, `src/analysis_engine/registry/fields.json`,
  `src/analysis_engine/registry.py`, `src/analysis_engine/normalize.py`
- Create: `scripts/build_hud_limits_table_tool.py`
- Test: `tests/test_analysis_registry.py`, `tests/test_analysis_normalize.py`

**Interfaces:**
- Produces: `FieldSpec.fallback_for: Optional[str]`; transform `'senior_age'`; params `usage.nonres_kwh`;
  fields `nonres` (code 28, bool, derived), `kwh_hl_intercept` (29, float, round 5), `kwh_hl_r2` (30, float,
  round 3), `kwh_cl_r2` (31, float, round 3), `owner_senior` (32, bool, `stored: false`, demographic
  `paths: ["owner_age"]`, `transform: "senior_age"`, `fallback_for: "senior"`).

- [ ] **Step 1: Failing tests.** In `tests/test_analysis_normalize.py`:

```python
def test_senior_age_is_true_only():
    from src.analysis_engine.normalize import TRANSFORMS
    f = TRANSFORMS['senior_age']
    assert f(65) is True and f('72') is True and f(64) is None and f('abc') is None and f(-1) is None
```

  In `tests/test_analysis_registry.py`:

```python
def test_p2_registry_entries():
    reg = load_registry()
    assert reg.params('usage')['nonres_kwh'] == 50000
    assert reg.field('owner_senior').fallback_for == 'senior' and not reg.field('owner_senior').stored
    assert {'nonres', 'kwh_hl_intercept', 'kwh_hl_r2', 'kwh_cl_r2'} <= {f.name for f in reg.fields}
    assert reg.rate('AES', 'Montgomery') is not None
    assert len(reg.table('hud_low_income_fy2026')['counties']) == 88


def test_fallback_must_name_a_field():
    fields, rules = _docs()  # existing helper that loads both JSON files; add it if absent
    fields['fields'].append({'name': 'x', 'code': 99, 'type': 'bool', 'stored': False, 'fallback_for': 'nope',
                             'source': {'role': 'demographic', 'paths': ['a'], 'transform': 'senior_age'}})
    assert any('fallback_for' in e for e in validate(fields, rules))
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: `normalize.py`:** add
  `def _senior_age(value): number = _number(value); return True if number is not None and number >= 65 else None`
  (two lines, compact) and register `'senior_age'` in `TRANSFORMS`.
- [ ] **Step 4: `registry.py`:** `FieldSpec` gains `fallback_for: Optional[str] = None` (last field); `load_registry`
  passes `f.get('fallback_for')`; `_field_errors` appends `f"{name}: fallback_for names unknown field {x!r}"` when
  the target is not another field's name (validate after the loop, using the collected `names`).
- [ ] **Step 5: `fields.json`:** version `2026-10-13.1`; add the five fields above; remove `kwh_hl_intercept`,
  `kwh_hl_r2`, `kwh_cl_r2` from `ignored.thermal` and `owner_age` from `ignored.demographic`. Thermal fields read
  with `transform: "number"` from paths of the same name.
- [ ] **Step 6: `rules.json`:** version `2026-10-13.1`; `params.usage.nonres_kwh: 50000` and extend its `source` with
  "§15 Q1: above this annual kWh the meter is treated as likely non-residential"; change `energy_burden.source` to
  "ACEEE … high burden at or above 6%, severe at or above 10% (stored burden is floored, so ≥ on the stored value
  equals ≥ on the true value; spec §15 Q2)".
- [ ] **Step 7: AES rate.** From `f8612025.zip` (URL in `electric_rates_2025.source`), sheet *States*, Part A,
  state OH, utility **Dayton Power & Light Co / AES Ohio (EIA id 4922)**: price = residential revenue (thousand $)
  × 1000 / residential sales (MWh) / 1000, 8 decimals. Add `"AES": <price>` to `usd_per_kwh` and
  `"AES": "Dayton Power & Light Co (4922)"` to `eia_utility` (use the exact name in the file). If the 2025 file
  lists no row for 4922, stop and report to the main session.
- [ ] **Step 8: HUD table.** Write `scripts/build_hud_limits_table_tool.py`: read
  `Section8-FY26.xlsx` (URL in the table's source), keep `state_alpha == 'OH'`, map `County_Name` through
  `src.tools.county_weather.normalize_county` to the engine's county name (as `VanWert`, matching the
  `{County}ElectricalDB` prefix), emit `{"area": hud_area_name + " (" + fips/area code + ")",
  "median_family_income": median2026, "limits": [l80_1 … l80_8]}` per county, sorted, as JSON on stdout.
  Check that the output covers exactly the 88 ElectricalDB counties and reproduces the three P1 entries byte for byte;
  any difference stops the task. Paste the output into `hud_low_income_fy2026.counties`.
- [ ] **Step 9: Run** the registry/normalize tests → PASS; full suite → **393 pass**.
- [ ] **Step 10: Commit** (`git add` the four modified files, the tool and the two test files).
  Message: `feat(analysis): P2 registry — nonres threshold, thermal fit fields, owner_age fallback, AES, HUD 88`.

---

### Task 5: Household and rules changes (nonres, fallback, NaN utility, archetypes, report)

**Files:**
- Modify: `src/analysis_engine/household.py`, `rules.py`, `archetypes.py`, `report.py`
- Test: `tests/test_analysis_household.py`, `tests/test_analysis_rules.py`, `tests/test_analysis_archetypes.py`

**Interfaces:**
- Consumes: Task 4 registry entries.
- Produces: `Assembled.fallbacks: List[str]` (field names filled by a fallback); `proxy_mask(name: str, rules: Dict)
  -> int` in `archetypes.py`; `county_report()` archetype entries gain `proxy: int`; `format_report` prints
  `(measured M · proxy P)` when `proxy` > 0 and `no measured source` when `known == 0`.

- [ ] **Step 1: Failing tests** (use the existing helpers `_linked`, `_doc`, `elec`, `monthly_series` in each file):

```python
# tests/test_analysis_household.py
def test_nonres_boundary():
    at = _doc(elec('M1', monthly_series(2025, 8, [4000.0] * 11 + [6000.0]), utility='AEP'), ParcelMatch())
    above = _doc(elec('M2', monthly_series(2025, 8, [4000.0] * 11 + [6001.0]), utility='AEP'), ParcelMatch())
    assert 'nonres' not in at and 'annual_cost' in at
    assert above['nonres'] is True and 'annual_cost' not in above and above['annual_kwh'] > 50000


def test_nonres_keeps_vendor_cost():
    match = _linked(demographic={'parcel_key': 'K', 'annual_kwh_cost': 3000, 'estimated_income': 60000,
                                 'md_householdsize': 2})
    hh = _doc(elec('M3', monthly_series(2025, 8, [6000.0] * 12), parcel_key='K'), match)
    assert hh['nonres'] is True and hh['annual_cost'] == 3000 and hh['burden_basis'] == 1


def test_owner_age_fills_blank_senior_only():
    blank = _linked(demographic={'parcel_key': 'K', 'md_presence_of_senior': '', 'owner_age': 70})
    young = _linked(demographic={'parcel_key': 'K', 'owner_age': 50})
    flag = _linked(demographic={'parcel_key': 'K', 'md_presence_of_senior': 'No Senior Present', 'owner_age': 70})
    none = _linked(demographic={'parcel_key': 'K'})
    meter = elec('M4', parcel_key='K')
    assert _doc(meter, blank)['senior'] is True and 22 not in _doc(meter, blank).get('missing', [])
    assert 'senior' not in _doc(meter, young)
    assert _doc(meter, flag)['senior'] is False
    assert 'senior' not in _doc(meter, none)


def test_nan_utility_falls_back_to_county_default():
    hh = _doc(elec('M5', monthly_series(2025, 8, [900.0] * 12), utility=float('nan')), ParcelMatch())
    assert 'annual_cost' in hh


def test_thermal_fit_fields_are_stored():
    match = _linked(thermal={'parcel_key': 'K', 'kwh_hl_slope': 0.01, 'kwh_cl_slope': 0.02, 'kwh_r2': 0.7,
                             'kwh_hl_intercept': 12.5, 'kwh_hl_r2': 0.61, 'kwh_cl_r2': 0.55})
    hh = _doc(elec('M6', parcel_key='K'), match)
    assert hh['kwh_hl_intercept'] == 12.5 and hh['kwh_hl_r2'] == 0.61 and hh['kwh_cl_r2'] == 0.55
```

(Adjust `_linked(...)` keyword names to the helper's actual signature; `_doc` returns the assembled doc. If the
helper assembles without `finalize`, the `nonres` test still holds because the flag is set in `_derive`.)

```python
# tests/test_analysis_rules.py
def test_nonres_household_is_out_of_the_usage_distribution():
    hh = {'annual_kwh': 60000, 'months_usage': 12, 'last_read': 202609, 'nonres': True}
    assert not usage_ok(hh, REG.rules['params'], 202610)
    assert finalize(dict(hh), Distributions.from_values([1000, 60000], []), REG.rules, 202610)['dims'][3] == -1

# tests/test_analysis_archetypes.py
def test_denominators_exclude_nonres():
    match, known = compile_archetype('bill_assistance', REG.rules)
    assert {'nonres': {'$ne': True}} in match['$and'] and {'nonres': {'$ne': True}} in known['$and']
    match, known = compile_archetype('likely_no_benefit', REG.rules)
    assert {'nonres': {'$ne': True}} in known['$and']


def test_proxy_mask_covers_dims_used_by_the_archetype():
    assert proxy_mask('weatherization', REG.rules) == 1 << REG.dims.index('building_inefficiency') | 1 << 0
    assert proxy_mask('likely_no_benefit', REG.rules) == 0
```

  In `tests/test_analysis_cli.py` (or wherever `format_report` is tested) add:

```python
def test_format_report_shows_proxy_split_and_no_source():
    report = {'county': 'X', 'total': 10, 'dims': {}, 'archetypes': {
        'weatherization': {'n': 5, 'known': 8, 'proxy': 3}, 'electrification': {'n': 0, 'known': 0, 'proxy': 0}}}
    text = format_report(report, REG)
    assert '5 of 8 known-enough (measured 2 · proxy 3)' in text and 'no measured source' in text
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: `household.py`.**
  - `_derive`: `raw = elec.get('utility')`; `utility = raw.strip() if isinstance(raw, str) and raw.strip() else
    reg.default_utility(county)`. After the usage summary:
    `nonres = usage.annual_kwh is not None and usage.annual_kwh > reg.params('usage')['nonres_kwh']`; if `nonres`,
    `values['nonres'] = True` and call `annual_cost(vendor, None, fresh, rate)` (vendor cost still applies).
  - New `_apply_fallbacks(values, missing, reg) -> List[str]`: for each spec with `fallback_for`, pop
    `values[spec.name]`; when the target is absent from `values` and the popped value is present, set
    `values[target] = popped`, discard the target's code from `missing`, append the target name. Call it in
    `assemble` right after `_read_sources`; return the list in `Assembled(doc, unmapped, fallbacks)`.
- [ ] **Step 4: `rules.py`.** `usage_ok`: add `and not hh.get('nonres')`. Docstring: "…from a meter that is still
  reading and is not flagged non-residential".
- [ ] **Step 5: `archetypes.py`.** Define `NOT_NONRES = {'nonres': {'$ne': True}}`; append it to both `match` and
  `known` lists (for `no_known_need`, wrap: `known = {'$and': [_known_dim_count(..), NOT_NONRES]}`); an archetype
  whose `known` was `{}` becomes `{'$and': [NOT_NONRES]}`. Add `proxy_mask(name, rules)`: OR of `1 << index` for
  every `dim` clause in the archetype.
- [ ] **Step 6: `report.py`.** `county_report`: per archetype also count
  `{'$and': [{'county': county}, match, {'proxy': {'$bitsAnySet': mask}}]}` when `mask` (else 0). `format_report`:
  `no measured source` when `known == 0`; else append `(measured {n - proxy} · proxy {proxy})` when `proxy`.
  Update the `county_report` docstring.
- [ ] **Step 7: Run** the affected tests → PASS; full suite → **402 pass** (fix any P1 test that asserted the old
  `known == total` shape for archetypes with no field clauses — the denominator is now "not nonres").
- [ ] **Step 8: Commit** (exact paths). Message:
  `feat(analysis): flag non-residential usage, owner_age senior fallback, measured/proxy archetype split`.

---

### Task 6: Build — stats, gates, `--all`

**Files:**
- Modify: `src/analysis_engine/build.py`, `src/analysis_engine/cli.py`, `src/analysis_engine/report.py`
  (`summarize_build`)
- Test: `tests/test_analysis_build.py`, `tests/test_analysis_cli.py`

**Interfaces:**
- Produces: `check_gates(doc_count, source_count, sizes_sorted, surrogate_ids=0, nonres=(0, 0), wrong_county=0,
  unmapped=None) -> List[str]` (`nonres` = (pass-1 count of meters above the threshold, staged `nonres` docs);
  `unmapped` = `{'fields': {...}, 'values': {...}}`); `build['stats']` gains `nonres`, `fallbacks`
  (`{field: n}`), `priced`, `income_known`, `usable_fit`, `boundary` (`{'fpl_pct=175': n, …}`), `levels`
  (`[[n_-1, n_0, n_1, n_2] per dim]`); `run_build(..., counties)` unchanged; CLI `build --all`.

- [ ] **Step 1: Failing tests** in `tests/test_analysis_build.py`:

```python
def test_gates_p2():
    assert check_gates(3, 3, [100, 100, 100], nonres=(2, 1))[0].startswith('nonres')
    assert 'county' in check_gates(3, 3, [100] * 3, wrong_county=1)[0]
    assert 'unmapped' in check_gates(3, 3, [100] * 3, unmapped={'fields': {'residential': ['land_use']},
                                                                  'values': {}})[0]
    assert check_gates(3, 3, [100] * 3, nonres=(1, 1), unmapped={'fields': {}, 'values': {}}) == []


def test_unmapped_field_fails_only_that_county():
    db = FakeNamedDB({'AElectricalDB': [elec('E1', YEAR, surprise_field=1)], 'BElectricalDB': [elec('E2', YEAR)]})
    store = FakeStore()
    builds = [build_county(db, store, c, REG, NOW, KEY) for c in ('A', 'B')]
    assert [b['status'] for b in builds] == ['failed', 'ok'] and 'surprise_field' in builds[0]['error']


def test_build_stats_count_nonres_and_fallbacks():
    db = FakeNamedDB({
        'TElectricalDB': [elec('E1', monthly_series(2025, 8, [6000.0] * 12), parcel_key='K1'), elec('E2', YEAR)],
        'TCountyDemographic': [{'_id': 'D1', 'parcel_key': 'K1', 'owner_age': 80}]})
    build = build_county(db, FakeStore(), 'T', REG, NOW, KEY)
    assert build['stats']['nonres'] == 1 and build['stats']['fallbacks'] == {'senior': 1}
```

  The existing `_db()` fixture carries `surprise_field=1` on E2 (P1 reported unmapped fields without failing).
  Update `test_successful_build_replaces_only_its_county` to drop `surprise_field` from the fixture, and add
  `surprise_field` handling to the new test above instead. In `tests/test_analysis_cli.py`:

```python
def test_build_all_lists_every_electrical_collection(monkeypatch):
    from src.analysis_engine import cli
    seen = []
    monkeypatch.setattr(cli, 'run_build', lambda db, counties, *a, **k: seen.extend(counties) or 0)
    db = FakeNamedDB({'AElectricalDB': [], 'BElectricalDB': [], 'BCountyResidential': []})
    assert cli.main(['build', '--all', '--dry-run'], db=db) == 0 and seen == ['A', 'B']
```

  (`cli.main` loads the id key for `build`; set `ANALYSIS_ID_KEY` via `monkeypatch.setenv` as the existing CLI tests
  do.)

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: `build.py`.**
  - `_distributions` also returns the pass-1 count of meters whose assembled doc has `nonres` (return a
    `(Distributions, int)` tuple; update the one caller).
  - `_stage_households` counts: `nonres`, `fallbacks` (from `assembled.fallbacks`), `wrong_county`
    (`hh['county'] != county`), `priced` (`'annual_cost' in hh`), `income_known` (`'fpl_pct' in hh`), `usable_fit`
    (`usable_fit(hh, params)`), `boundary` for `fpl_pct == params.income_need.fpl_high / fpl_moderate`,
    `ami_pct == ami_moderate`, `energy_burden == energy_burden.moderate / high` (keys like `'fpl_pct=175'`, built
    from the registry values, never literals), and `levels[i][level + 1] += 1` per dim. Store them in
    `build['stats']`.
  - `check_gates` gains the three checks with messages `nonres pass-1 {a} != staged {b}`,
    `{n} document(s) carry another county`, and `unmapped fields/values: …` (list the names, cap at 20).
  - `build_county` passes the new arguments.
- [ ] **Step 4: `cli.py`.** `build` takes `--county` (append) **or** `--all` (mutually exclusive, one required).
  `--all` → `sorted(n[:-len(suffix)] for n in db.list_collection_names() if n.endswith(suffix))` with
  `suffix = collection_name('electrical', '')`. Docstring gains the `--all` example.
- [ ] **Step 5: `report.summarize_build`** prints `nonres {n:,} · priced {n:,} · income known {n:,} · usable fits
  {n:,}` and `fallbacks {dict}` when present.
- [ ] **Step 6: Run** → PASS; full suite → **406 pass**.
- [ ] **Step 7: Commit** (exact paths). Message: `feat(analysis): P2 gates, build stats and build --all`.

---

### Task 7: `analysis_coverage`

**Files:**
- Create: `src/analysis_engine/coverage.py`, `tests/test_analysis_coverage.py`
- Modify: `src/analysis_engine/store.py` (`COVERAGE = 'analysis_coverage'`, `write_coverage`),
  `src/analysis_engine/sources.py` (`countykeys_collections`), `src/analysis_engine/build.py`, `tests/analysis_fakes.py`

**Interfaces:**
- Consumes: `build` dict (stats from Task 6), `county_report()` (Task 5), `sources_present`.
- Produces: `countykeys_collections(db, county: str) -> Dict[str, str]` (role → collection name from the
  `CountyKeys` doc whose `normalize_county(county)` matches, using its `residential_data` / `demographic_data`
  keys; `{}` when none); `coverage_doc(build: Dict, report: Optional[Dict], countykeys: Dict[str, str],
  present: Dict[str, str], rules: Dict) -> Dict`; `MongoStore.write_coverage(doc)` replaces by `_id = county`;
  `DryRunStore`/`FakeStore` keep it in `self.coverage[county]`.

`coverage_doc` fields: `_id` (= county), `county`, `build_id` (the build's `_id`, or `built_at` in dry runs),
`built_at`, `meters`, `linked` (`doc_count − unlinked`), `stale`, `nonres`, `priced_share`, `income_known_share`,
`usable_fit_share` (each rounded to 4 places over `doc_count`), `boundary`, `levels` (dict dim → `{-1,0,1,2}`
counts), `archetypes` (from the report: `{name: {n, known, proxy}}`, absent in dry runs), `sources_present`
(sorted roles), `countykeys` (`{'missing': [names CountyKeys lists that don't exist], 'disagree': [roles whose
CountyKeys name differs from the pattern name]}`), `heat_fuel_source` (`'measured'` if
`levels['electrification']` has any known household else `'none'`), `fallbacks`.

- [ ] **Step 1: Failing tests** `tests/test_analysis_coverage.py`:

```python
"""One coverage document per county, built from the build's own counters."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.coverage import coverage_doc  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402

REG = load_registry()
BUILD = {'_id': 'b1', 'county': 'Hardin', 'built_at': datetime(2026, 10, 13, tzinfo=timezone.utc), 'doc_count': 10,
         'stats': {'unlinked': 4, 'stale': 1, 'nonres': 2, 'priced': 5, 'income_known': 3, 'usable_fit': 1,
                   'boundary': {'fpl_pct=175': 1}, 'fallbacks': {'senior': 2},
                   'levels': [[10, 0, 0, 0]] * 5 + [[10, 0, 0, 0]]}}


def test_coverage_shares_and_counts():
    doc = coverage_doc(BUILD, None, {}, {'electrical': 'HardinElectricalDB'}, REG.rules)
    assert doc['_id'] == 'Hardin' and doc['linked'] == 6 and doc['priced_share'] == 0.5
    assert doc['heat_fuel_source'] == 'none' and 'archetypes' not in doc


def test_countykeys_missing_collection_is_reported():
    doc = coverage_doc(BUILD, None, {'demographic': 'HardinCountyDemographic'},
                       {'electrical': 'HardinElectricalDB'}, REG.rules)
    assert doc['countykeys'] == {'missing': ['HardinCountyDemographic'], 'disagree': []}


def test_archetypes_come_from_the_report():
    report = {'archetypes': {'weatherization': {'n': 3, 'known': 5, 'proxy': 2}}}
    assert coverage_doc(BUILD, report, {}, {}, REG.rules)['archetypes']['weatherization']['proxy'] == 2
```

  In `tests/test_analysis_build.py`: `test_successful_build_writes_coverage` — after a successful `build_county`
  with `FakeStore`, `store.coverage['Franklin']['meters'] == <fixture meter count>`; a failed build writes no
  coverage.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `coverage.py` (~50 lines, pure), `countykeys_collections` in `sources.py`
  (lift the lookup from `scripts/profile_need_analysis_counties_tool.py:county_jobs` — `normalize_county` keyed
  `CountyKeys` docs, fields `residential_data` / `demographic_data`), `write_coverage` in both stores and
  `FakeStore`. In `build_county`, after `store.record_build(build)` and only when `build['status'] == 'ok'`:
  `report = county_report(db, county, reg) if isinstance(store, MongoStore) else None`;
  `store.write_coverage(coverage_doc(build, report, countykeys_collections(db, county), src.present, reg.rules))`
  (so `build['_id']` already holds the inserted id).
  `ensure_indexes` needs nothing new (`_id` = county). `record_build` must return the inserted id so `build_id` is
  real (`self.db[BUILDS].insert_one(...).inserted_id`; `build['_id']` set before coverage). Keep the import of
  `county_report` free of cycles (`report.py` imports `store.HOUSEHOLDS` only).
- [ ] **Step 4: Run** → PASS; full suite → **410 pass**.
- [ ] **Step 5: Commit** (exact paths). Message: `feat(analysis): analysis_coverage per county`.

---

### Task 8: Reconciliation tool

**Files:**
- Create: `src/analysis_engine/reconcile.py`, `tests/test_analysis_reconcile.py`
- Modify: `src/analysis_engine/cli.py` (`reconcile` subcommand)

**Interfaces:**
- Produces: `source_counts(db, county: str, build_month: int, reg: Registry) -> Dict[str, int]` (`meters`,
  `linked`, `stale`, `nonres`); `reconcile(db, counties: List[str], reg: Registry, build_month: int) ->
  List[Dict]` (one row per county: `county`, and per key `(source, coverage)`, `ok`); `sample_counties(db,
  rng_seed: int) -> List[str]` (Franklin; the largest linked county other than the P1 three; the largest fully
  unlinked county; Montgomery; one random other county, seeded); CLI
  `reconcile [--county C ...] [--seed N]` exits 1 on any mismatch.

Independence (spec §15.4): `meters` = `count_documents({})`; `linked` = `count_documents` with
`{'$or': [{'parcel_key': {'$nin': [None, '']}}, {'parcel_id': {'$nin': [None, '']}}]}`; `stale` = an aggregation
over `$objectToArray: '$time_series_elec'` taking `$max` of `k` and comparing its first 7 characters with the
24-month cutoff month (docs with readings only — docs with an empty series count as neither fresh nor stale, the
same as the engine's `last_read is not None` condition); `nonres` uses `summarize_usage` (shared helper, stated in
the docstring as the one non-independent count).

- [ ] **Step 1: Failing tests** (`FakeNamedDB` does not run aggregations — test `reconcile` against a tiny fake
  whose `count_documents`/`aggregate` return canned numbers, and test `sample_counties` on `FakeNamedDB` names):

```python
"""reconcile compares independent source counts with analysis_coverage and flags any difference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine import reconcile as rc  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402

REG = load_registry()


class _Coverage:
    def __init__(self, docs):
        self.docs = docs

    def find_one(self, flt):
        return self.docs.get(flt['_id'])


class _DB:
    def __init__(self, coverage):
        self.coverage = _Coverage(coverage)

    def __getitem__(self, name):
        return self.coverage


def test_match_and_mismatch(monkeypatch):
    monkeypatch.setattr(rc, 'source_counts', lambda db, c, m, r: {'meters': 10, 'linked': 6, 'stale': 1, 'nonres': 2})
    db = _DB({'A': {'meters': 10, 'linked': 6, 'stale': 1, 'nonres': 2},
              'B': {'meters': 9, 'linked': 6, 'stale': 1, 'nonres': 2}})
    rows = rc.reconcile(db, ['A', 'B'], REG, 202610)
    assert [r['ok'] for r in rows] == [True, False] and rows[1]['meters'] == (10, 9)


def test_missing_coverage_is_a_mismatch(monkeypatch):
    monkeypatch.setattr(rc, 'source_counts', lambda db, c, m, r: {'meters': 1, 'linked': 0, 'stale': 0, 'nonres': 0})
    assert rc.reconcile(_DB({}), ['Z'], REG, 202610)[0]['ok'] is False
```

  plus `test_sample_counties_is_seeded_and_covers_the_kinds` using `FakeNamedDB` with collections for Franklin,
  Montgomery, a linked county (has `CountyResidential`), an unlinked one and two others: same seed → same list;
  list contains Franklin and Montgomery; length 5.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (~70 lines) and the CLI subcommand (prints one line per county:
  `County: ok` or `County: MISMATCH meters 10 != 9 …`). **Step 4: Run** → PASS; full suite → **413 pass**.
- [ ] **Step 5: Commit** (exact paths). Message: `feat(analysis): reconcile coverage against source counts`.

---

### Task 9: Heat-type field scan (read-only)

**Files:** Create `scripts/scan_heat_type_fields_tool.py`.

- [ ] **Step 1:** For every `{County}CountyResidential` collection (via `collection_name('residential', c)` and
  `list_collection_names`), list field names matching `/heat|fuel|hvac|furnace/i` (sample 2,000 docs with
  `$sample`, union of keys) and, per matching field, the top 15 distinct values with counts. Print a table; write
  nothing to the database.
- [ ] **Step 2:** Run it. **Bring the result to the main session — do not edit `fields.json` here.** Mapping
  values to `heat_fuel` codes is a design decision (spec §15 Q4); the main session decides and, if anything maps,
  a follow-up commit adds the `value_map` entries with a test per county value.
- [ ] **Step 3:** Commit the script (exact path). Message: `chore(analysis): add read-only heat-type field scan`.

---

### Task 10: Dry run, verification, live build (live data; one user gate)

No new code unless a gate fails. Output goes into `.claude_docs/<YYYYMMDD_HHMM>_need_analysis_p2_results.md`
in the same shape as `20261012_1907_need_analysis_p1_results.md`.

- [ ] **Step 1: Dry run.** `/usr/bin/time -v python -m src.analysis_engine.cli build --all --dry-run` (log to
  scratch). Record per-county status, households, p99, nonres, fallbacks, unmapped; total wall time and peak RSS.
  Stop if peak RSS exceeds 4 GB.
- [ ] **Step 2: Triage failures.** Unmapped **fields** that are clearly irrelevant to the six dims go to the
  matching `ignored` list in `fields.json` (one commit listing them); any field that could feed a dimension, and every
  unmapped **value**, goes to the main session first. Re-run the dry run until all 88 pass.
- [ ] **Step 3: Expected deltas to check** (stop and report any surprise): Cuyahoga households ≈ 396,338 − ~10k
  folded; Franklin ≈ 475,376 − ~1.2k; Huron −257; Montgomery −19k…−31k; total nonres ≈ 59.5k + P1's ~17.8k (minus
  folded); P1 counties' `priced` share rises (utility backfilled).
- [ ] **Step 4: Spot checks.** Five random households each in Montgomery (prefer folded parcels), Holmes and Lucas:
  check `annual_kwh`, `last_read`, `nonres`, `annual_cost` (rate × kWh for the doc's utility), `senior` and its
  source against the ElectricalDB/Demographic documents. No addresses in the notes.
- [ ] **Step 5: STOP — bring the dry-run summary and spot checks to the user; wait for an explicit go-ahead.**
- [ ] **Step 6: Live build.** `python -m src.analysis_engine.cli build --all`. Then
  `python -m src.analysis_engine.cli reconcile` (sampled) → all ok. Verify: 88 `ok` builds with
  `rules_version 2026-10-13.1`; `analysis_coverage` holds 88 docs; no staging collections; PII check (no
  `customer_name`, `email`, `address`, `service_address`, `account_id` keys) = 0; hashed-id pattern holds.
- [ ] **Step 7:** Write and commit the results doc (exact path), including a "For the human" section (unpriced
  counts left, CountyKeys disagreements, heat-type scan outcome, Hancock thermal at 70%).

---

## Self-review notes (plan author)

- Spec coverage: §15.2 Q1 → Tasks 4–6; Q2 → Task 4 Step 6; Q3 → Task 5; Q4 → Tasks 4 (fields), 5 (`no measured
  source`), 9 (scan); Q5 → Task 6 (`boundary`, `income_known`) + Task 7; Q6a → unchanged code (multitenant stays
  unread); Q6b → Tasks 4–5; Q7/§15.3 → Tasks 1–3; §15.4 → Tasks 6–8, 10; §15.5 → Tasks 4–5; §15.6 → every task's
  tests + Tasks 3, 10.
- Test counts are cumulative targets; if a step adds a parametrized case, update the later targets instead of
  forcing the number.
