# Storage Reclamation — Execution Runbook

**Created:** 2026-09-16 · **Branch:** `feature/campaign-weather` · **Database:** `empower_development` @ `localhost:27017`
**Findings artifact:** https://claude.ai/code/artifact/d7348f88-b79f-4ba4-a6da-339d34c3d5e3
**Companion runbook:** `.claude_docs/20260916_1300_thermal_slope_remediation_runbook.md` (**read §3 before starting — two tasks here are blocked on it**)

One task per session. Each task is self-contained: it states its own preconditions, why the
space is recoverable, the evidence, the checkpoint to take, what to build, how to test it,
the dry run, the execute, the verification and the rollback. You do not need the audit
artifact in context to run a task — every number you need is repeated here.

---

## 0. Standing rules

1. `source venv/bin/activate` before any Python. Non-negotiable — the tools import `pymongo`.
2. **No write to any collection without a checkpoint taken in the same session.**
3. Every write script takes `--dry-run` and defaults to it. A script without a dry run does not get run.
4. Commit after each task. Restore points are cheap; re-deriving state is not.
5. New scripts go in `scripts/` with a `_tool` suffix and an entry in `.claude_docs/script_descriptions.md`.
   Reusable ones go in `src/scripts/` with an entry in `.claude_docs/tools.md`.
6. **pytest needs `-o addopts=""`.** `pyproject.toml` sets `addopts = "-v --cov=app ..."` but
   `pytest-cov` is not installed, so a bare `python -m pytest` fails before collecting anything.
   Run `python -m pytest tests/ -q -o addopts=""`. Baseline **measured 2026-09-16 17:45: 148 passed**
   in 0.85s. ⚠️ The companion thermal runbook still states 111 — that figure is stale (two test
   files were added since). Trust 148; correct the other runbook when you next touch it.
7. **Never run `compact` as the first action.** It is ranked #1 by size but executed **last** —
   every schema task below creates new free space that the same single compact pass reclaims.
   Compacting early means compacting twice and getting less back.
8. Field-drop tasks change the write path as well as the data. A task is not done when the
   documents are clean — it is done when the code that would re-add the field is also gone.

---

## 1. Environment facts (measured 2026-09-16)

| Fact | Value |
|---|---|
| mongod | 7.0.30 |
| mongodump / mongorestore | 100.14.1 |
| Disk free on `/home` | 197 GB |
| Collections | 170 · 6,790,915 documents · 283 indexes |
| Logical (BSON) size | 6,553 MB |
| File size on disk | 3,039 MB |
| Live bytes on disk | 1,778 MB |
| WiredTiger free space | 1,261 MB (41.5% of the file) |
| **True compression** | **3.68×** (`logical ÷ (storageSize − freeStorageSize)`) |
| `*ElectricalDB` (88 collections) | 2,222 MB storage — **73% of the database** |
| `*ThermalLoads` (25 collections) | 448 MB storage |
| Projected end state | **~682 MB** (78% reduction) |

⚠️ **Do not compute compression as `dataSize / storageSize`.** `storageSize` includes free
space, which yields a misleading 2.17×. Every disk estimate in this runbook uses live bytes.

⚠️ `mongodump` has **no `--nsInclude`** (that is mongorestore only). The backup tool enumerates
collections and dumps them one at a time. Do not "simplify" it back.

### How to read the savings numbers

**Logical MB is measured exactly** — from a full scan of every document, not a sample.
**Disk MB is an estimate** — logical bytes divided by the family's observed compression ratio.
That average is directionally wrong in two known ways, stated per task where it matters:

- Highly repetitive data (the `" 00:00:00"` suffix — the same nine bytes 70 million times)
  compresses far better than average, so its disk figure is an **over**estimate.
- High-entropy data (the `monthly_*` doubles) compresses worse than average, so its disk
  figure is an **under**estimate.

Judge a task by its logical figure and its risk. Treat disk figures as ±40%.

---

## 2. Backup system

Tool: `src/scripts/backup_mongo_collections_tool.py` — already built and tested.
Checkpoints live in `~/backups/octopus-thermal/<label>/`, override with `OCTOPUS_BACKUP_ROOT`.

```bash
source venv/bin/activate

# Checkpoint a family before a schema task
python src/scripts/backup_mongo_collections_tool.py create rc01-pre-index-drop --suffix ElectricalDB

# Whole database, single archive (94s, 957 MB) — take once before Phase B
python src/scripts/backup_mongo_collections_tool.py create rc00-baseline --full

# What do I have?
python src/scripts/backup_mongo_collections_tool.py list

# Prove a checkpoint restores — into a scratch db, production untouched
python src/scripts/backup_mongo_collections_tool.py verify rc01-pre-index-drop

# Roll back (destructive: drops, then restores)
python src/scripts/backup_mongo_collections_tool.py restore rc01-pre-index-drop --all --yes
```

⚠️ Checkpointing all 88 `*ElectricalDB` collections dumps **4.89 GB**. Budget time and disk.
For single-collection tasks use `--suffix` on the narrowest family that covers your writes.

### Proving a rollback actually rolled back

Tool: `src/scripts/collection_fingerprint_tool.py`. Document counts alone score a dropped
index as a pass. The fingerprint captures count + indexes + an order-independent content hash.

```bash
python src/scripts/collection_fingerprint_tool.py capture MorrowElectricalDB --out exports/rc_before.json
# ... do the thing, or roll back ...
python src/scripts/collection_fingerprint_tool.py capture MorrowElectricalDB --out exports/rc_after.json
python src/scripts/collection_fingerprint_tool.py compare exports/rc_before.json exports/rc_after.json
```

### Checkpoint schedule

| Label | Before | Scope |
|---|---|---|
| `rc00-baseline` | anything | `--full` |
| `rc01-pre-index-drop` | R-01 | `--suffix ElectricalDB` + note exposures separately |
| `rc02-pre-rekey` | R-02 | `--suffix ElectricalDB` |
| `rc03-pre-monthly` | R-03 | `--suffix ElectricalDB` |
| `rc04-pre-nulls` | R-04 | `--suffix ElectricalDB` |
| `rc05-pre-parcelkey` | R-05 | `--full` (touches four families) |
| `rc06-pre-migration` | R-06 | (exposures/participants/campaigns — use `--full`) |
| `rc07-pre-thermal-arrays` | R-07 | `--suffix ThermalLoads` |
| `rc08-pre-compact` | R-09 | `--full` |

---

## 3. ⚠️ Interaction with the thermal slope remediation

**Two tasks in this runbook are blocked on the thermal remediation finishing.** Read this
before scheduling anything.

`scripts/calculate_missing_thermal_loads_tool.py:418` writes `kwh_hl_cl_loads` — it is the
active tool in `.claude_docs/20260916_1300_thermal_slope_remediation_runbook.md`. That runbook
still has open tasks that **write to `*ThermalLoads`**: T-07 (fill 60,733 missing parcels),
T-09 (refresh 646,375 stale slopes), T-11/T-12/T-13 (slope defects).

| This task | Blocked on | Why |
|---|---|---|
| **R-07** (drop ThermalLoads regression inputs) | T-07, T-09, T-11, T-12, T-13 complete | Those arrays are the audit trail for exactly the slopes being remediated. Dropping them mid-remediation destroys the evidence for the work in flight. |
| **R-05** (drop `parcel_key`) | T-04 complete | T-04 migrates the thermal join off `parcel_key` onto `parcel_id`. Dropping `parcel_key` first breaks T-04's before/after comparison; doing it after is the natural cleanup that T-04 sets up. |

Everything else here is independent and can run today.

---

## 4. Execution order

**Execution order is deliberately not the size ranking.** Ordered by risk and dependency:

| Order | Task | Logical | ~Disk | Rewrites docs? | Depends on |
|---|---|---|---|---|---|
| 1 | **R-01** Drop 96 zero-read indexes | — | 50 MB | no | — |
| 2 | **R-02** Strip `" 00:00:00"` from series keys | 603 MB | 174 MB | yes | — |
| 3 | **R-03** Drop `monthly_*` | 1,862 MB | 538 MB | yes | — |
| 4 | **R-04** Remove wholly-null fields | 60 MB | 18 MB | yes | — |
| 5 | **R-05** Drop `parcel_key` | 68 MB | 56 MB | yes | thermal T-04 |
| 6 | **R-06** Drop `_migration` | 48 MB | 8 MB | yes | — |
| 7 | **R-07** Drop ThermalLoads input arrays | 765 MB | 193 MB | yes | thermal T-07/09/11/12/13 |
| 8 | **R-08** Shorten delivery-tag field names | 217 MB | 59 MB | yes | **optional — read the task first** |
| 9 | **R-09** Compact every collection | — | 1,261 MB | no | all of the above |
| — | **R-10** Normalize string `_id` | 126 MB | 18 MB | yes | **deferred — see task** |

**Expected test count after each task** (baseline 148, measured 2026-09-16):
R-01 → 153 · R-02 → 160 · R-03 → 163 · R-04 → 163 · R-05 → 170 · R-06 → 170 · R-07 → 170.
A number that does not match means a task added or lost a test it did not intend to.

R-02 through R-08 can be batched into one pass per collection if you prefer fewer rewrites —
see §5 for the combined-pass option, which is what we recommend once each task has passed
its own dry run individually.

---

## 5. Optional: the combined pass

Each of R-02, R-03, R-04, R-05, R-06 and R-08 rewrites every document in `*ElectricalDB`.
Running them separately rewrites 4.1M documents six times. Once **each task's dry run has
passed on its own**, you can apply them in a single `bulk_write` pass per collection.

Do not start here. Run each task's dry run individually first — a combined pass that fails
gives you no signal about which transform was wrong. Once all six dry runs are clean, set
`--combine` on `scripts/reclaim_electrical_storage_tool.py` (built in R-02, extended by each
later task) to apply every enabled transform in one pass, then take one checkpoint and one
compact for the lot.

---

## Task R-01 — Drop 96 zero-read indexes

**Recovers:** 50 MB of index bytes. No document rewrite. Fully reversible by recreating the index.

**Why:** 96 of the 138 non-`_id` indexes have served zero reads. Over half the bytes sit in
five `exposures` indexes, led by `participant_id_1_campaign_id_1` at 26 MB. 71 of the 96 are
`parcel_key_1` indexes, which R-05 removes the field for anyway.

**⚠️ The evidence is a 16-day window.** `$indexStats` counters reset when `mongod` restarts,
and this instance last started **2026-08-31 22:54 UTC**. An index reading zero here may still
serve a monthly or quarterly job. This task's first step is to *narrow that uncertainty*, not
to trust the number.

**Files:**
- Create: `scripts/audit_index_usage_tool.py`
- Create: `tests/test_index_usage_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_index_usage_audit.py
"""Unit tests for the index usage audit.

An index that is unused in the observed window is a candidate, not a verdict.
The classifier must never mark an index droppable while it backs a unique
constraint, a TTL, or the _id field, regardless of read count.
"""
from scripts.audit_index_usage_tool import classify_index


def test_zero_ops_plain_index_is_a_candidate():
    idx = {'name': 'parcel_key_1', 'ops': 0, 'spec': {'key': {'parcel_key': 1}}}
    assert classify_index(idx)['verdict'] == 'candidate'


def test_id_index_is_never_droppable():
    idx = {'name': '_id_', 'ops': 0, 'spec': {'key': {'_id': 1}}}
    assert classify_index(idx)['verdict'] == 'protected'


def test_unique_index_is_protected_even_at_zero_reads():
    idx = {'name': 'participant_id_1', 'ops': 0,
           'spec': {'key': {'participant_id': 1}, 'unique': True}}
    assert classify_index(idx)['verdict'] == 'protected'
    assert 'unique' in classify_index(idx)['reason']


def test_ttl_index_is_protected():
    idx = {'name': 'created_at_1', 'ops': 0,
           'spec': {'key': {'created_at': 1}, 'expireAfterSeconds': 86400}}
    assert classify_index(idx)['verdict'] == 'protected'


def test_used_index_is_kept():
    idx = {'name': 'campaign_id_1', 'ops': 4211, 'spec': {'key': {'campaign_id': 1}}}
    assert classify_index(idx)['verdict'] == 'keep'
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
source venv/bin/activate
python -m pytest tests/test_index_usage_audit.py -q -o addopts=""
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.audit_index_usage_tool'`.

- [ ] **Step 3: Write the classifier**

```python
# scripts/audit_index_usage_tool.py
#!/usr/bin/env python3
"""
Read-only audit of index usage across empower_development.

$indexStats counters reset on mongod restart, so a zero read count proves only
that the index was unused since the last restart. This tool reports the restart
time alongside every count so the window is never invisible, and refuses to mark
an index droppable when it enforces a constraint that reads cannot reveal
(unique, TTL, _id).

Never writes. There is no --execute flag.

Usage:
    python scripts/audit_index_usage_tool.py
    python scripts/audit_index_usage_tool.py --json exports/index_usage.json
    python scripts/audit_index_usage_tool.py --drop-script exports/drop_indexes.js
"""
import argparse
import json
import os
from collections import defaultdict

from pymongo import MongoClient

DEFAULT_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
DEFAULT_DB = os.environ.get('MONGODB_DATABASE', 'empower_development')


def classify_index(idx: dict) -> dict:
    """Classify one index as protected, candidate or keep.

    'candidate' never means 'drop' — it means 'unused in the observed window'.
    """
    spec = idx.get('spec') or {}
    if idx['name'] == '_id_' or list(spec.get('key', {})) == ['_id']:
        return {'verdict': 'protected', 'reason': '_id index cannot be dropped'}
    if spec.get('unique'):
        return {'verdict': 'protected', 'reason': 'enforces a unique constraint'}
    if 'expireAfterSeconds' in spec:
        return {'verdict': 'protected', 'reason': 'TTL index expires documents'}
    if idx['ops'] == 0:
        return {'verdict': 'candidate', 'reason': 'zero reads in observed window'}
    return {'verdict': 'keep', 'reason': f"{idx['ops']} reads in observed window"}


def collect(uri: str, db_name: str) -> dict:
    """Gather $indexStats for every collection plus the server start time."""
    client = MongoClient(uri)
    db = client[db_name]
    uptime = client.admin.command('serverStatus')
    rows, sizes = [], {}
    for name in sorted(db.list_collection_names()):
        coll = db[name]
        stats = next(coll.aggregate([{'$collStats': {'storageStats': {}}}]))['storageStats']
        sizes[name] = stats.get('indexSizes', {})
        specs = coll.index_information()
        for s in coll.aggregate([{'$indexStats': {}}]):
            idx = {'collection': name, 'name': s['name'], 'ops': s['accesses']['ops'],
                   'since': s['accesses']['since'].isoformat(),
                   'size': sizes[name].get(s['name'], 0),
                   'spec': {'key': dict(s['key']),
                            **{k: v for k, v in (specs.get(s['name']) or {}).items()
                               if k in ('unique', 'expireAfterSeconds', 'partialFilterExpression')}},
                   'docs': stats['count']}
            idx.update(classify_index(idx))
            rows.append(idx)
    client.close()
    return {'uptime_seconds': uptime['uptime'], 'indexes': rows}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--json', help='write full results to this path')
    p.add_argument('--drop-script', help='write a reviewable mongosh drop script')
    p.add_argument('--uri', default=DEFAULT_URI)
    p.add_argument('--database', default=DEFAULT_DB)
    a = p.parse_args()

    res = collect(a.uri, a.database)
    days = res['uptime_seconds'] / 86400
    by = defaultdict(list)
    for r in res['indexes']:
        by[r['verdict']].append(r)

    print(f"Observation window: {days:.1f} days since mongod start")
    if days < 30:
        print(f"  WARNING: {days:.1f} days is shorter than a monthly job cycle.")
        print("  Treat 'candidate' as 'confirm against your schedule', not 'drop'.")
    for verdict in ('protected', 'keep', 'candidate'):
        rows = by[verdict]
        mb = sum(r['size'] for r in rows) / 1048576
        print(f"\n{verdict.upper()}: {len(rows)} indexes, {mb:.1f} MB")
        if verdict == 'candidate':
            for r in sorted(rows, key=lambda x: -x['size']):
                print(f"  {r['collection']:<30} {r['name']:<36} "
                      f"{r['size']/1048576:7.2f} MB  docs={r['docs']}")

    if a.json:
        with open(a.json, 'w') as fh:
            json.dump(res, fh, indent=2)
        print(f"\nwrote {a.json}")
    if a.drop_script:
        with open(a.drop_script, 'w') as fh:
            fh.write("// REVIEW EVERY LINE BEFORE RUNNING.\n")
            fh.write(f"// Observation window: {days:.1f} days.\n")
            fh.write(f"const db = db.getSiblingDB('{a.database}');\n")
            for r in sorted(by['candidate'], key=lambda x: -x['size']):
                fh.write(f"db.getCollection('{r['collection']}')"
                         f".dropIndex('{r['name']}');  // {r['size']/1048576:.2f} MB\n")
        print(f"wrote {a.drop_script}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_index_usage_audit.py -q -o addopts=""
```

Expected: 5 passed.

- [ ] **Step 5: Run the audit and read the window warning**

```bash
python scripts/audit_index_usage_tool.py --json exports/index_usage_20260916.json
```

Expected: `PROTECTED` includes all 170 `_id_` indexes. `CANDIDATE` totals ~96 indexes / ~50 MB,
headed by `exposures / participant_id_1_campaign_id_1` at 26.00 MB.

- [ ] **Step 6: Confirm the candidates against code, not just reads**

```bash
# Anything naming a candidate index's field in a sort, hint or query
grep -rn "participant_id_1_campaign_id_1\|unified_status\|participant_oid" \
    --include=*.py --include=*.ts --include=*.tsx . | grep -v node_modules | grep -v /venv/
```

Record what you find in the commit message. An index backing a query that runs monthly will
show zero reads here and still be needed. If any candidate is referenced by a scheduled job,
move it out of the candidate list by hand before Step 8.

- [ ] **Step 7: Checkpoint**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc01-pre-index-drop --full
```

Indexes are cheap to rebuild, but the checkpoint also covers you if Step 8 is run against the
wrong database.

- [ ] **Step 8: Generate, review, and run the drop script**

```bash
python scripts/audit_index_usage_tool.py --drop-script exports/drop_indexes_20260916.js
less exports/drop_indexes_20260916.js          # READ IT. Every line.
mongosh "mongodb://localhost:27017" --file exports/drop_indexes_20260916.js
```

- [ ] **Step 9: Verify**

```bash
python scripts/audit_index_usage_tool.py
```

Expected: `CANDIDATE: 0 indexes, 0.0 MB`. Total index count drops from 283 to ~187.

- [ ] **Step 10: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc01-pre-index-drop --all --yes
```

- [ ] **Step 11: Commit**

```bash
git add scripts/audit_index_usage_tool.py tests/test_index_usage_audit.py \
        exports/index_usage_20260916.json .claude_docs/script_descriptions.md
git commit -m "chore(storage): drop 96 zero-read indexes, reclaim 50 MB

Adds audit_index_usage_tool.py, which reports index reads alongside the
observation window and refuses to mark unique/TTL/_id indexes droppable.
Window was 16 days; candidates confirmed against code references before drop."
```

---

## Task R-02 — Strip `" 00:00:00"` from time-series keys

**Recovers:** 603 MB logical, ~174 MB disk (**overestimate** — the suffix is the same nine
bytes repeated 70 million times and compresses extremely well; expect less).

**Why:** Every key in `time_series_elec` and `time_series_gas` is a 19-character timestamp
whose time component is always midnight. `"2016-03-02 00:00:00"` and `"2016-03-02"` carry
identical information; the nine trailing bytes are pure formatting.

**Evidence:** 68,245,508 electrical keys + 2,002,152 gas keys. **100%** carry the suffix —
there is not a single non-midnight key in the database.

**Why this is safe:** `monthly_stats()` in `src/tools/utility_bills/ingest.py:98` derives the
month with `k[5:7]`, which is unaffected. The merge policy keys on the date string, so the
transform must be applied to the *writer* and the *stored data* in the same task or the next
ingest will reintroduce 19-char keys alongside the 10-char ones.

**Files:**
- Create: `src/tools/series_keys.py`
- Create: `tests/test_series_keys.py`
- Create: `scripts/reclaim_electrical_storage_tool.py`
- Modify: `src/tools/utility_bills/ingest.py` (normalize on write)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_series_keys.py
"""Unit tests for time-series key normalization.

Stripping a midnight suffix is only safe when it cannot silently merge two
distinct readings. These tests pin the collision behaviour: a same-day pair
must raise rather than quietly lose a reading.
"""
import pytest

from src.tools.series_keys import normalize_key, normalize_series


def test_midnight_suffix_is_stripped():
    assert normalize_key('2016-03-02 00:00:00') == '2016-03-02'


def test_bare_date_is_unchanged():
    assert normalize_key('2016-03-02') == '2016-03-02'


def test_non_midnight_time_is_preserved():
    # No such key exists today; if one ever appears we must not destroy it.
    assert normalize_key('2016-03-02 06:30:00') == '2016-03-02 06:30:00'


def test_series_is_rekeyed_and_values_preserved():
    src = {'2016-03-02 00:00:00': 471, '2016-01-29 00:00:00': 587}
    assert normalize_series(src) == {'2016-03-02': 471, '2016-01-29': 587}


def test_already_normalized_series_is_returned_unchanged():
    src = {'2016-03-02': 471}
    assert normalize_series(src) == src


def test_colliding_keys_raise_rather_than_lose_a_reading():
    src = {'2016-03-02 00:00:00': 471, '2016-03-02': 999}
    with pytest.raises(ValueError, match='2016-03-02'):
        normalize_series(src)


def test_empty_series_is_handled():
    assert normalize_series({}) == {}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_series_keys.py -q -o addopts=""
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.series_keys'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# src/tools/series_keys.py
"""Canonical form for time-series dictionary keys.

Every key in time_series_elec / time_series_gas is a date at midnight, stored as
a 19-character timestamp. The nine trailing characters carry no information and
cost 603 MB across the database. This module is the single place that decides
what a series key looks like, so the writer and the migration cannot drift.
"""

MIDNIGHT_SUFFIX = ' 00:00:00'


def normalize_key(key: str) -> str:
    """Strip a midnight time component, leaving any real time in place."""
    if key.endswith(MIDNIGHT_SUFFIX):
        return key[:-len(MIDNIGHT_SUFFIX)]
    return key


def normalize_series(series: dict) -> dict:
    """Rekey a whole series, refusing to merge two readings onto one date."""
    out = {}
    for key, value in series.items():
        norm = normalize_key(key)
        if norm in out and out[norm] != value:
            raise ValueError(
                f'key collision on {norm}: {out[norm]!r} and {value!r} would merge')
        out[norm] = value
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_series_keys.py -q -o addopts=""
```

Expected: 7 passed.

- [ ] **Step 5: Normalize on write so ingest cannot reintroduce long keys**

In `src/tools/utility_bills/ingest.py`, add the import at the top:

```python
from src.tools.series_keys import normalize_key, normalize_series
```

Then normalize each incoming reading's date key at the point it enters a slot, and normalize
the merged series before it is written. The two write sites are the `$set` at line ~191
(`'time_series_elec': merged`) and the new-document dict at line ~198 (`'time_series_elec': dates`):

```python
            merged = normalize_series({**ts, **new})
            ...
                ops.append(UpdateOne({'_id': _id}, {'$set': {
                    'time_series_elec': merged, **monthly_stats(merged),
                    'last_utility_ingest': tag}}))
        else:
            ...
            dates = normalize_series(dates)
            doc = {'parcel_id': ident if kind == 'p' else None,
                   'time_series_elec': dates, **monthly_stats(dates),
                   ...
```

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

```bash
python -m pytest tests/ -q -o addopts=""
```

Expected: **160 passed** (148 baseline + 5 from R-01 + 7 new here).

- [ ] **Step 7: Write the migration tool**

```python
# scripts/reclaim_electrical_storage_tool.py
#!/usr/bin/env python3
"""
Storage reclamation pass over *ElectricalDB (and CuyahogaGasDB).

Applies one or more independent transforms to every document. Dry-run by default;
--execute writes. Each transform is opt-in so a task's dry run isolates one change,
and --combine applies every enabled transform in a single bulk_write per collection
once each has been proven on its own.

Transforms. Each is added by the task that needs it -- do not advertise a flag
before it is implemented; one that parses but does nothing is worse than none.
    --rekey-series    strip " 00:00:00" from time_series_elec / time_series_gas keys   (R-02)
    --drop-monthly    remove monthly_averages / monthly_minimums / monthly_maximums    (R-03)

Usage:
    python scripts/reclaim_electrical_storage_tool.py --rekey-series
    python scripts/reclaim_electrical_storage_tool.py --rekey-series --execute
    python scripts/reclaim_electrical_storage_tool.py --rekey-series --county Morrow --execute
"""
import argparse
import os

from pymongo import MongoClient, UpdateOne

from src.tools.series_keys import normalize_series

DEFAULT_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
DEFAULT_DB = os.environ.get('MONGODB_DATABASE', 'empower_development')
SERIES_FIELDS = ('time_series_elec', 'time_series_gas')
MONTHLY_FIELDS = ('monthly_averages', 'monthly_minimums', 'monthly_maximums')
BATCH = 1000


def target_collections(db, county: str = None) -> list:
    names = [n for n in db.list_collection_names()
             if n.endswith('ElectricalDB') or n.endswith('GasDB')]
    if county:
        names = [n for n in names if n.startswith(county)]
    return sorted(names)


def plan_document(doc: dict, opts) -> dict:
    """Return the {$set:..., $unset:...} update for one document, or {} for no change."""
    sets, unsets = {}, {}
    if opts.rekey_series:
        for field in SERIES_FIELDS:
            series = doc.get(field)
            if isinstance(series, dict) and series:
                norm = normalize_series(series)
                if norm != series:
                    sets[field] = norm
    if opts.drop_monthly:
        for field in MONTHLY_FIELDS:
            if field in doc:
                unsets[field] = ''
    update = {}
    if sets:
        update['$set'] = sets
    if unsets:
        update['$unset'] = unsets
    return update


def run(uri: str, db_name: str, opts) -> dict:
    client = MongoClient(uri)
    db = client[db_name]
    totals = {'scanned': 0, 'changed': 0, 'collections': 0, 'collisions': []}
    projection = {f: 1 for f in SERIES_FIELDS + MONTHLY_FIELDS}

    for name in target_collections(db, opts.county):
        coll = db[name]
        ops, scanned, changed = [], 0, 0
        for doc in coll.find({}, projection):
            scanned += 1
            try:
                update = plan_document(doc, opts)
            except ValueError as exc:
                totals['collisions'].append(f'{name}/{doc["_id"]}: {exc}')
                continue
            if not update:
                continue
            changed += 1
            ops.append(UpdateOne({'_id': doc['_id']}, update))
            if opts.execute and len(ops) >= BATCH:
                coll.bulk_write(ops, ordered=False)
                ops = []
        if opts.execute and ops:
            coll.bulk_write(ops, ordered=False)
        totals['scanned'] += scanned
        totals['changed'] += changed
        totals['collections'] += 1
        print(f'  {name:<30} scanned={scanned:<8} changed={changed}')

    client.close()
    return totals


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--rekey-series', action='store_true')
    p.add_argument('--drop-monthly', action='store_true')
    p.add_argument('--execute', action='store_true', help='write (default is a dry run)')
    p.add_argument('--county', help='restrict to one county, e.g. Morrow')
    p.add_argument('--uri', default=DEFAULT_URI)
    p.add_argument('--database', default=DEFAULT_DB)
    a = p.parse_args()

    if not (a.rekey_series or a.drop_monthly):
        p.error('enable at least one transform')
    print('EXECUTING (writes)' if a.execute else 'DRY RUN (no writes)')
    t = run(a.uri, a.database, a)
    print(f"\n{t['collections']} collections · {t['scanned']} scanned · {t['changed']} changed")
    if t['collisions']:
        print(f"\n{len(t['collisions'])} COLLISIONS — resolve before executing:")
        for c in t['collisions'][:20]:
            print(f'  {c}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 8: Dry run on one small county first**

```bash
python scripts/reclaim_electrical_storage_tool.py --rekey-series --county Morrow
```

Expected: `MorrowElectricalDB scanned=4611 changed=4611`, zero collisions.

- [ ] **Step 9: Dry run across everything**

```bash
python scripts/reclaim_electrical_storage_tool.py --rekey-series
```

Expected: 89 collections, 4,305,685 scanned, ~4,305,685 changed, **0 collisions**.
**If any collision is reported, stop.** A collision means two readings would merge onto one
date — resolve those documents by hand before executing.

- [ ] **Step 10: Checkpoint, then fingerprint the canary**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc02-pre-rekey --suffix ElectricalDB
python src/scripts/collection_fingerprint_tool.py capture MorrowElectricalDB --out exports/rc02_before.json
```

- [ ] **Step 11: Execute on the canary, verify, then the rest**

```bash
python scripts/reclaim_electrical_storage_tool.py --rekey-series --county Morrow --execute

mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
const d=db.MorrowElectricalDB.findOne({time_series_elec:{$exists:true}});
print("sample keys: "+Object.keys(d.time_series_elec).slice(0,3));'
```

Expected: keys print as `2016-03-02,2016-01-29,...` with no time component. Then:

```bash
python scripts/reclaim_electrical_storage_tool.py --rekey-series --execute
```

- [ ] **Step 12: Verify database-wide**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");let n=0;
db.getCollectionNames().filter(x=>x.endsWith("ElectricalDB")||x.endsWith("GasDB")).forEach(c=>{
 n+=db.getCollection(c).aggregate([
  {$project:{k:{$objectToArray:{$ifNull:["$time_series_elec",{}]}}}},{$unwind:"$k"},
  {$match:{"k.k":/ 00:00:00$/}},{$count:"n"}]).toArray().reduce((a,b)=>a+b.n,0);});
print("remaining suffixed keys: "+n);'
```

Expected: `remaining suffixed keys: 0`.

- [ ] **Step 13: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc02-pre-rekey --all --yes
python src/scripts/collection_fingerprint_tool.py capture MorrowElectricalDB --out exports/rc02_after.json
python src/scripts/collection_fingerprint_tool.py compare exports/rc02_before.json exports/rc02_after.json
```

Expected on a correct rollback: no differences reported.

- [ ] **Step 14: Commit**

```bash
git add src/tools/series_keys.py tests/test_series_keys.py \
        scripts/reclaim_electrical_storage_tool.py src/tools/utility_bills/ingest.py \
        .claude_docs/script_descriptions.md
git commit -m "perf(storage): strip midnight suffix from time-series keys

70.2M keys carried a constant ' 00:00:00' costing 603 MB logical. Adds
src/tools/series_keys.py as the single definition of a series key, normalizes
on write in the ingest engine so re-ingest cannot reintroduce long keys, and
migrates stored data. Collision-safe: same-date merges raise rather than drop
a reading."
```

---

## Task R-03 — Drop `monthly_averages` / `monthly_minimums` / `monthly_maximums`

**Recovers:** 1,862 MB logical, ~538 MB disk (**underestimate** — these are high-entropy
doubles that compress worse than the family average; expect more).

**Why:** Three cached aggregates, twelve keys each, stored in every document beside
`time_series_elec` — the exact source they are computed from. They are 38.5% of the
`*ElectricalDB` family and 52% of `CuyahogaGasDB`. This is the largest single item in the audit.

**Evidence:** 4,305,685 occurrences × ~151 bytes each. `monthly_stats()` already exists at
`src/tools/utility_bills/ingest.py:98` and recomputes all three from the merged series, so the
derivation is proven in code today.

**Read-path check — the reason this is tractable.** Three references exist outside the writer:

| Reference | Kind | Action |
|---|---|---|
| `src/tools/utility_bills/ingest.py:103-105` | writes them | remove the write |
| `src/models/county_electrical_data.py:11-13` | Pydantic model fields | remove the fields |
| `scripts/get_participant_profile_tool.py:210` | display dump | compute on the fly via `monthly_stats` |

**No query, index, or aggregation reads these fields.** Confirm before proceeding (Step 1).

**Files:**
- Modify: `src/tools/utility_bills/ingest.py` (stop writing)
- Modify: `src/models/county_electrical_data.py` (remove fields)
- Modify: `scripts/get_participant_profile_tool.py:210` (compute on read)
- Modify: `scripts/reclaim_electrical_storage_tool.py` (already has `--drop-monthly`)
- Create: `tests/test_monthly_stats_on_read.py`

- [ ] **Step 1: Prove nothing else reads them**

```bash
grep -rn "monthly_averages\|monthly_minimums\|monthly_maximums" \
    --include=*.py --include=*.js --include=*.ts --include=*.tsx . \
    | grep -v node_modules | grep -v /venv/
```

Expected: exactly the four lines in the table above (ingest.py appears twice — the docstring
and the function). **If any other reference appears, stop and re-scope this task.**

- [ ] **Step 2: Write the failing test**

```python
# tests/test_monthly_stats_on_read.py
"""The profile tool must derive monthly stats from the series, not read a cached field.

Once the cached fields are dropped, a reader that still calls .get('monthly_averages')
silently prints nothing instead of failing. These tests pin the derived behaviour.
"""
from src.tools.utility_bills.ingest import monthly_stats


def test_monthly_stats_derives_all_three_from_a_series():
    series = {'2016-01-11': 10, '2016-01-29': 20, '2016-03-02': 5}
    out = monthly_stats(series)
    assert out['monthly_averages']['1'] == 15.0
    assert out['monthly_minimums']['1'] == 10
    assert out['monthly_maximums']['1'] == 20
    assert out['monthly_averages']['3'] == 5.0


def test_monthly_stats_works_on_normalized_ten_char_keys():
    # R-02 shortened every key; the month slice must still land on the month.
    assert monthly_stats({'2016-07-09': 42})['monthly_averages'] == {'7': 42.0}


def test_monthly_stats_on_empty_series_is_empty():
    assert monthly_stats({}) == {'monthly_averages': {},
                                 'monthly_minimums': {},
                                 'monthly_maximums': {}}
```

- [ ] **Step 3: Run it — expect GREEN, not red**

```bash
python -m pytest tests/test_monthly_stats_on_read.py -q -o addopts=""
```

Expected: **3 passed.** This is deliberate. `monthly_stats()` already exists and already
handles all three cases (verified 2026-09-16: an empty series returns three empty dicts, and
the `k[5:7]` month slice works on both 19-char and 10-char keys). These are *characterization*
tests, not TDD red — they lock in the derivation’s behaviour **before** the cached fields are
deleted, so that a later change to `monthly_stats` is caught by a test rather than by a wrong
number in a participant profile.

If any of the three fails, `monthly_stats` has drifted since the audit. Stop and fix it before
dropping any data — until R-03 executes, the cached fields are the only copy.

- [ ] **Step 4: Stop writing the fields**

In `src/tools/utility_bills/ingest.py`, remove `**monthly_stats(merged)` from the `$set` at
line ~191 and `**monthly_stats(dates)` from the new-document dict at line ~198. Keep the
`monthly_stats` function — it is now the read-time deriver and R-03's tests cover it.

Update the module docstring at line 5-6, which currently promises the opposite:

```python
Merge policy: union new (date, kWh) readings into time_series_elec, never
overwriting an existing date key. Monthly aggregates are NOT stored — derive
them at read time with monthly_stats(); they cost 1.9 GB when cached (2026-09-16).
```

- [ ] **Step 5: Remove the model fields**

```python
# src/models/county_electrical_data.py
from src.utils.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField


''' Format for ______CountyElectrical collections.'''

class ElectricalData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: str
    time_series_elec: dict
```

⚠️ Note while you are here: `parcel_id: str` is not Optional, but 3,239,625 documents store
`parcel_id: null`. That mismatch predates this task and is tracked as T-14 in the thermal
runbook — do not fix it here, but do not be surprised by it either.

- [ ] **Step 6: Derive at read time in the profile tool**

At `scripts/get_participant_profile_tool.py:210`, replace the cached lookup:

```python
            from src.tools.utility_bills.ingest import monthly_stats
            series = electrical.get("time_series_elec") or {}
            dump("monthly_averages", monthly_stats(series)["monthly_averages"], indent="    ")
```

- [ ] **Step 7: Run the full suite**

```bash
python -m pytest tests/ -q -o addopts=""
```

Expected: **163 passed** (160 after R-02 + 3 new here).

- [ ] **Step 8: Dry run**

```bash
python scripts/reclaim_electrical_storage_tool.py --drop-monthly --county Morrow
python scripts/reclaim_electrical_storage_tool.py --drop-monthly
```

Expected: 89 collections, ~4,305,685 changed.

- [ ] **Step 9: Checkpoint and execute**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc03-pre-monthly --suffix ElectricalDB
python scripts/reclaim_electrical_storage_tool.py --drop-monthly --county Morrow --execute
python scripts/get_participant_profile_tool.py --help   # smoke: the read path still imports
python scripts/reclaim_electrical_storage_tool.py --drop-monthly --execute
```

- [ ] **Step 10: Verify**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");let n=0;
db.getCollectionNames().filter(x=>x.endsWith("ElectricalDB")||x.endsWith("GasDB")).forEach(c=>{
 n+=db.getCollection(c).countDocuments({monthly_averages:{$exists:true}});});
print("docs still carrying monthly_averages: "+n);
const s=db.stats(); print("dataSize now: "+(s.dataSize/1048576).toFixed(0)+" MB (was 6585)");'
```

Expected: `0`, and `dataSize` drops by roughly 1,800 MB.

- [ ] **Step 11: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc03-pre-monthly --all --yes
```

- [ ] **Step 12: Commit**

```bash
git add src/tools/utility_bills/ingest.py src/models/county_electrical_data.py \
        scripts/get_participant_profile_tool.py tests/test_monthly_stats_on_read.py \
        .claude_docs/script_descriptions.md
git commit -m "perf(storage): derive monthly aggregates instead of caching them

monthly_averages/minimums/maximums cost 1,862 MB logical while being pure
functions of time_series_elec in the same document. Removes the write, the
model fields and the cached read; the profile tool now derives via the
existing monthly_stats(). Largest single item in the 2026-09-16 audit."
```

---

## Task R-04 — Remove wholly-null fields

**Recovers:** 60 MB logical, ~18 MB disk.

**Why:** MongoDB stores an explicit `null` — it is not free. 243 field/collection pairs are
`null` in **every** document that has them. `HamiltonElectricalDB` carries `parcel_id: null`
and `account_id: null` in all 267,154 documents. Indexes on those fields index nothing useful.

**Evidence (largest):**

| Collection | Field | Null in |
|---|---|---|
| HamiltonElectricalDB | `account_id` | 267,154 / 267,154 |
| HamiltonElectricalDB | `parcel_id` | 267,154 / 267,154 |
| FranklinElectricalDB | `parcel_key` | 216,887 / 216,887 |
| FranklinElectricalDB | `account_id` | 215,568 / 215,568 |
| MontgomeryElectricalDB | `parcel_id` | 198,762 / 198,762 |
| SummitElectricalDB | `parcel_id` | 185,144 / 185,144 |

⚠️ **`parcel_id` is the exception — do not unset it.** A missing `parcel_id` and a null
`parcel_id` are different to the thermal remediation's `coverage` and `joinkey` checks, which
count `{'parcel_id': {'$ne': None}}`. `$ne: None` matches a *missing* field differently from a
*null* one in some query shapes, and T-14 in the thermal runbook owns those 3.2M documents.
**Restrict this task to `account_id` and `parcel_key`-adjacent leaf fields, and exclude
`parcel_id` explicitly.**

- [ ] **Step 1: Enumerate the candidates, excluding parcel_id**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");const out=[];
db.getCollectionNames().forEach(n=>{
 const c=db.getCollection(n), total=c.countDocuments({});
 if(!total) return;
 c.aggregate([{$project:{kv:{$objectToArray:"$$ROOT"}}},{$unwind:"$kv"},
  {$group:{_id:"$kv.k",n:{$sum:1},nulls:{$sum:{$cond:[{$eq:["$kv.v",null]},1,0]}}}},
  {$match:{$expr:{$and:[{$eq:["$n","$nulls"]},{$ne:["$_id","parcel_id"]}]}}}
 ],{allowDiskUse:true}).forEach(r=>out.push({c:n,f:r._id,n:r.n}));});
out.sort((a,b)=>b.n-a.n);
print("candidates: "+out.length);
out.slice(0,30).forEach(r=>print("  "+r.c.padEnd(30)+" "+r.f.padEnd(22)+" "+r.n));' \
  | tee exports/null_fields_20260916.txt
```

- [ ] **Step 2: Confirm each candidate field is not read**

```bash
cut -c34-55 exports/null_fields_20260916.txt | sort -u | tr -d ' ' | grep -v '^$' | while read f; do
  echo "--- $f: $(grep -rn "$f" --include=*.py . | grep -v node_modules | grep -v /venv/ | wc -l) refs"
done
```

A field with references is not automatically disqualified — a writer that sets it to null is
fine to remove along with the field. A *reader* that distinguishes null from missing is not.

- [ ] **Step 3: Checkpoint and unset**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc04-pre-nulls --full
```

Generate a reviewable script, read it, then run it:

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
print("// REVIEW BEFORE RUNNING. parcel_id is deliberately excluded.");
print("const db = db.getSiblingDB(\"empower_development\");");
db.getCollectionNames().forEach(n=>{
 const c=db.getCollection(n), total=c.countDocuments({});
 if(!total) return;
 c.aggregate([{$project:{kv:{$objectToArray:"$$ROOT"}}},{$unwind:"$kv"},
  {$group:{_id:"$kv.k",n:{$sum:1},nulls:{$sum:{$cond:[{$eq:["$kv.v",null]},1,0]}}}},
  {$match:{$expr:{$and:[{$eq:["$n","$nulls"]},{$ne:["$_id","parcel_id"]}]}}}
 ],{allowDiskUse:true}).forEach(r=>print("db.getCollection(\""+n+"\").updateMany({},{$unset:{\""+r._id+"\":\"\"}});"));});' \
  > exports/unset_nulls_20260916.js

less exports/unset_nulls_20260916.js       # READ IT
mongosh "mongodb://localhost:27017" --file exports/unset_nulls_20260916.js
```

- [ ] **Step 4: Verify**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
print("Hamilton account_id present: "+db.HamiltonElectricalDB.countDocuments({account_id:{$exists:true}}));
print("Hamilton parcel_id present:  "+db.HamiltonElectricalDB.countDocuments({parcel_id:{$exists:true}})+" (expected 267154 — untouched)");'
```

- [ ] **Step 5: Run the audit to confirm thermal checks are unaffected**

```bash
python scripts/audit_thermal_load_coverage_tool.py --check coverage
python scripts/audit_thermal_load_coverage_tool.py --check joinkey
```

Expected: identical to the 2026-09-16 baseline — 60,733 genuinely missing, 1,622 phantom.
**If these numbers move, roll back.** It means a null/missing distinction mattered.

- [ ] **Step 6: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc04-pre-nulls --all --yes
```

- [ ] **Step 7: Commit**

```bash
git add exports/null_fields_20260916.txt .claude_docs/script_descriptions.md
git commit -m "chore(storage): unset fields that are null in every document

243 field/collection pairs stored an explicit null in 100% of documents,
costing 60 MB logical. parcel_id deliberately excluded: null vs missing is
load-bearing for the thermal coverage/joinkey audits and is owned by T-14."
```

---

## Task R-05 — Drop the `parcel_key` field and its indexes

> **BLOCKED on thermal runbook T-04.** T-04 migrates the thermal join off `parcel_key` onto
> `parcel_id`. Doing this first breaks T-04's before/after comparison. Confirm T-04 is
> complete, then run this as the cleanup it sets up.

**Recovers:** 68 MB logical + 12.4 MB of indexes, ~56 MB disk total.

**Why:** `parcel_key` is `parcel_id` with leading zeros stripped — a derived value stored
alongside its source. All 71 `parcel_key_1` indexes have served zero reads.

**Evidence — this was verified, not assumed.** Across all 2,877,627 rows carrying the field:

```
parcel_key == ltrim(parcel_id, '0')   for 2,877,592 rows
exceptions                                          35 rows, all in FranklinCountyDemographic
```

⚠️ **Those 35 exceptions must be resolved before the field is dropped.** They are the only
rows where `parcel_key` carries information `parcel_id` does not.

**Files:**
- Create: `src/tools/parcel_keys.py`
- Create: `tests/test_parcel_keys.py`
- Modify: `scripts/reclaim_electrical_storage_tool.py` (add `--drop-parcel-key`)

- [ ] **Step 1: Inspect the 35 exceptions before anything else**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
db.FranklinCountyDemographic.find({$expr:{$ne:[
  {$toString:"$parcel_key"},{$ltrim:{input:{$toString:"$parcel_id"},chars:"0"}}]}},
  {parcel_id:1,parcel_key:1,_id:1}).forEach(d=>printjson(d));'
```

Decide per row whether `parcel_key` or `parcel_id` is correct, and record the decision in the
commit message. **Do not proceed until these 35 are reconciled.**

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parcel_keys.py
"""Unit tests for parcel_key derivation.

parcel_key is dropped from storage and derived on demand. If the derivation is
wrong the join silently misses rows, so the leading-zero rule is pinned here.
"""
from src.tools.parcel_keys import derive_parcel_key


def test_leading_zeros_are_stripped():
    assert derive_parcel_key('00101001') == '101001'


def test_dashed_identifier_keeps_internal_zeros():
    assert derive_parcel_key('010-000002-00') == '10-000002-00'


def test_identifier_without_leading_zero_is_unchanged():
    assert derive_parcel_key('30324005') == '30324005'


def test_long_numeric_identifier():
    assert derive_parcel_key('0372805502007') == '372805502007'


def test_none_returns_none():
    assert derive_parcel_key(None) is None


def test_non_string_is_coerced():
    assert derive_parcel_key(101001) == '101001'


def test_all_zeros_does_not_become_empty():
    assert derive_parcel_key('0000') == '0'
```

- [ ] **Step 3: Run it to verify it fails**

```bash
python -m pytest tests/test_parcel_keys.py -q -o addopts=""
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.parcel_keys'`.

- [ ] **Step 4: Write the implementation**

```python
# src/tools/parcel_keys.py
"""Derivation of parcel_key from parcel_id.

Verified 2026-09-16 across all 2,877,627 rows that stored both: parcel_key is
parcel_id with leading zeros stripped, with 35 exceptions in
FranklinCountyDemographic (reconciled in R-05). Storing the derived value cost
68 MB plus 12.4 MB of indexes that served zero reads.
"""


def derive_parcel_key(parcel_id) -> str:
    """Return the parcel_key form of a parcel_id: leading zeros stripped."""
    if parcel_id is None:
        return None
    text = str(parcel_id)
    stripped = text.lstrip('0')
    # '0000' must not collapse to '' — keep a single zero.
    return stripped if stripped else '0'
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_parcel_keys.py -q -o addopts=""
```

Expected: 7 passed.

- [ ] **Step 6: Add the `--drop-parcel-key` transform to the tool**

In `scripts/reclaim_electrical_storage_tool.py`, import the deriver, extend `plan_document`,
register the flag, and widen the guard:

```python
from src.tools.parcel_keys import derive_parcel_key
```

```python
    if opts.drop_parcel_key:
        key = doc.get('parcel_key')
        if key is not None and key == derive_parcel_key(doc.get('parcel_id')):
            unsets['parcel_key'] = ''
```

```python
    p.add_argument('--drop-parcel-key', action='store_true')
    ...
    if not (a.rekey_series or a.drop_monthly or a.drop_parcel_key):
        p.error('enable at least one transform')
```

Add `'parcel_key': 1, 'parcel_id': 1` to the `projection` dict in `run()`, or the deriver
receives `None` for every document and unsets nothing.

⚠️ The equality guard is the safety net: a `parcel_key` that does **not** match the derivation
is left in place rather than deleted. After Step 1 reconciles the 35 exceptions this should
unset every row — but the guard means a missed exception survives instead of being lost.

Add the flag to the tool’s docstring transform list while you are there.

- [ ] **Step 7: Replace the 16 code references**

```bash
grep -rn "parcel_key" --include=*.py . | grep -v node_modules | grep -v /venv/
```

For each read site, import `derive_parcel_key` and derive from `parcel_id`. For each write
site, delete the write. `scripts/audit_thermal_load_coverage_tool.py` uses `parcel_key` in its
`joinkey` check — that check exists to compare the two join keys, so **leave it reading both
until T-04 is signed off**, then simplify it.

- [ ] **Step 8: Full suite**

```bash
python -m pytest tests/ -q -o addopts=""
```

Expected: **170 passed** (163 after R-03 + 7 new here).

- [ ] **Step 9: Checkpoint, dry run, execute**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc05-pre-parcelkey --full
python scripts/reclaim_electrical_storage_tool.py --drop-parcel-key
python scripts/reclaim_electrical_storage_tool.py --drop-parcel-key --execute
```

The 71 `parcel_key_1` indexes are already gone if R-01 ran. If not:

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
db.getCollectionNames().forEach(n=>{const c=db.getCollection(n);
 if(Object.keys(c.getIndexes().reduce((a,i)=>(a[i.name]=1,a),{})).includes("parcel_key_1"))
   {c.dropIndex("parcel_key_1"); print("dropped on "+n);}});'
```

- [ ] **Step 10: Verify**

```bash
python scripts/audit_thermal_load_coverage_tool.py --check joinkey
python scripts/audit_thermal_load_coverage_tool.py --check coverage
```

Expected: coverage identical to baseline; `joinkey` phantom-gap count now reported as 0 or
n/a, because the wrong join key no longer exists.

- [ ] **Step 11: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc05-pre-parcelkey --all --yes
```

- [ ] **Step 12: Commit**

```bash
git add src/tools/parcel_keys.py tests/test_parcel_keys.py \
        scripts/reclaim_electrical_storage_tool.py .claude_docs/script_descriptions.md
git commit -m "refactor(storage): derive parcel_key instead of storing it

Verified across all 2,877,627 rows: parcel_key == ltrim(parcel_id, '0'), with
35 exceptions in FranklinCountyDemographic reconciled first. Removes 68 MB of
duplicated identifier and 12.4 MB of indexes that served zero reads. Follows
thermal T-04, which moved the join onto parcel_id."
```

---

## Task R-06 — Drop `_migration` scaffolding

**Recovers:** 48 MB logical, ~8 MB disk.

**Why:** Per-document migration bookkeeping left behind by
`scripts/migrate_to_campaign_data_tool.py`. It is 15% of `exposures` logical bytes and 23% of
`participants`.

**Evidence:** `exposures` 312,370 docs · `participants` 14,360 · `campaigns` 147.

**Read-path check:** `src/models/campaign_data.py:365,443,501` declare it as
`Optional[MigrationMetadata]` — already optional, so removing the data does not break the
model. `scripts/cleanup_duplicate_text_exposures_tool.py:134` *excludes* `_migration` from a
key comparison, so removing the field makes that exclusion a no-op rather than an error.

⚠️ Keep the migration *tool*; drop only the per-document residue. If you may ever need to
re-derive provenance, export it first — that is Step 1.

- [ ] **Step 1: Export the metadata before deleting it**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
["exposures","participants","campaigns"].forEach(n=>{
  db.getCollection(n).find({_migration:{$exists:true}},{_migration:1}).forEach(d=>
    print(n+"\t"+d._id+"\t"+JSON.stringify(d._migration)));});' \
  > exports/migration_metadata_20260916.tsv
wc -l exports/migration_metadata_20260916.tsv
```

Expected: 326,877 lines.

- [ ] **Step 2: Checkpoint**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc06-pre-migration --full
python src/scripts/collection_fingerprint_tool.py capture campaigns --out exports/rc06_before.json
```

- [ ] **Step 3: Unset**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
["exposures","participants","campaigns"].forEach(n=>{
  const r=db.getCollection(n).updateMany({_migration:{$exists:true}},{$unset:{_migration:""}});
  print(n+": modified "+r.modifiedCount);});'
```

Expected: `exposures: 312370`, `participants: 14360`, `campaigns: 147`.

- [ ] **Step 4: Verify the models still load**

```bash
python -c "
from src.models.campaign_data import *
print('campaign_data models import cleanly')"
python -m pytest tests/ -q -o addopts=""
```

Expected: **170 passed** — R-06 adds no tests; this confirms removing the data broke nothing.

- [ ] **Step 5: Remove the now-dead model fields**

Delete the three `migration: Optional[MigrationMetadata] = Field(None, alias="_migration")`
lines at `src/models/campaign_data.py:365,443,501`, and the `MigrationMetadata` class if
nothing else references it:

```bash
grep -rn "MigrationMetadata" --include=*.py . | grep -v /venv/
python -m pytest tests/ -q -o addopts=""
```

- [ ] **Step 6: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc06-pre-migration --all --yes
```

- [ ] **Step 7: Commit**

```bash
git add src/models/campaign_data.py exports/migration_metadata_20260916.tsv \
        .claude_docs/script_descriptions.md
git commit -m "chore(storage): drop per-document _migration scaffolding

326,877 documents carried migration bookkeeping from the campaign_data
migration, 48 MB logical. Metadata exported to
exports/migration_metadata_20260916.tsv before removal; model fields were
already Optional so nothing downstream changes."
```

---

## Task R-07 — Drop ThermalLoads raw regression inputs

> **BLOCKED on thermal runbook T-07, T-09, T-11, T-12, T-13.**
> `scripts/calculate_missing_thermal_loads_tool.py:418` writes `kwh_hl_cl_loads`. These arrays
> are the audit trail for exactly the slopes being remediated. **Do not run this until the
> thermal remediation is signed off.** Check that runbook's task list before starting.

**Recovers:** 765 MB logical, ~193 MB disk. 81% of the `*ThermalLoads` family.

**Why:** `kwh_hl_cl_loads` and `gas_hl_cl_loads` retain every regression input row beside the
already-computed `kwh_hl_slope`, `kwh_hl_intercept`, `kwh_hl_r2` and their gas/cooling
counterparts. The `kwh` values duplicate `time_series_elec` in the matching `*ElectricalDB`
collection; `hl`/`cl` are recomputable from weather plus usage.

**Evidence:** 10,420,325 kwh elements + 1,412,741 gas elements across 795,511 documents.
`CuyahogaThermalLoads` alone holds 4,379,199 kwh elements.

**The real question this task must answer first: is the recomputation reproducible?** If the
weather series used for the original regression is not reconstructable, these arrays are the
*only* record of the inputs and dropping them destroys reproducibility for 765 MB of savings.

- [ ] **Step 1: Establish that the inputs can be reconstructed**

`src/tools/county_weather.py` and `scripts/fetch_county_weather_hourly_tool.py` (added
2026-09-16) provide county-centroid weather for all 25 thermal counties. Confirm the
regression can be reproduced end to end for one parcel:

```bash
source venv/bin/activate
python scripts/get_participant_profile_tool.py --help
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
const d=db.MorrowThermalLoads.findOne({kwh_hl_cl_loads:{$ne:[]}});
print("parcel "+d.parcel_id+"  n_inputs="+d.kwh_hl_cl_loads.length+
      "  slope="+d.kwh_hl_slope+"  r2="+d.kwh_hl_r2);'
```

Take that parcel, recompute its slope from `time_series_elec` + fetched weather, and compare
to the stored `kwh_hl_slope`. **If you cannot reproduce it to within rounding, stop.** Keep
the arrays and mark this task rejected — 193 MB is not worth losing reproducibility.

- [ ] **Step 2: Decide the retention policy explicitly**

Record one of these in the commit message:

- **Drop entirely** — regression is reproducible on demand.
- **Keep an export** — dump the arrays to `exports/` as compressed JSON, then drop from Mongo.
- **Keep `n` only** — replace the array with its element count, preserving the "how many
  readings backed this slope" signal that `get_participant_profile_tool.py:221` displays,
  at ~4 bytes instead of ~700.

The third is the recommended default: it keeps the one value that is actually read while
recovering most of the space.

- [ ] **Step 3: Checkpoint and fingerprint the canary**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc07-pre-thermal-arrays --suffix ThermalLoads
python src/scripts/collection_fingerprint_tool.py capture MorrowThermalLoads --out exports/rc07_before.json
```

- [ ] **Step 4: Apply the chosen policy (shown for "keep n only")**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
db.getCollectionNames().filter(n=>n.endsWith("ThermalLoads")).forEach(n=>{
  const r=db.getCollection(n).updateMany({kwh_hl_cl_loads:{$exists:true}},[
    {$set:{kwh_n:{$size:{$ifNull:["$kwh_hl_cl_loads",[]]}},
           gas_n:{$size:{$ifNull:["$gas_hl_cl_loads",[]]}}}},
    {$unset:["kwh_hl_cl_loads","gas_hl_cl_loads"]}]);
  print(n+": "+r.modifiedCount);});'
```

Run it against `MorrowThermalLoads` alone first by adding `.filter(n=>n==="MorrowThermalLoads")`.

- [ ] **Step 5: Update the reader**

`scripts/get_participant_profile_tool.py:221-222` currently prints
`len(thermal.get("kwh_hl_cl_loads") or [])`. Change it to read `kwh_n`:

```python
            dump("kwh readings behind slope", thermal.get("kwh_n", 0), indent="    ")
```

Also update `src/models/county_loads_data.py:11` (`kwh_hl_cl_loads: list`) and
`scripts/calculate_missing_thermal_loads_tool.py:418` so new calculations write `kwh_n`
rather than the full array.

- [ ] **Step 6: Verify**

```bash
python -m pytest tests/ -q -o addopts=""
python scripts/audit_thermal_load_coverage_tool.py --check slopes
```

Expected: slope counts unchanged from baseline — 126,987 real gas slopes. The slopes
themselves are untouched; only the inputs were removed.

⚠️ `tests/test_collection_fingerprint.py:80` builds a fixture containing `kwh_hl_cl_loads`.
That is a fake document for hashing, not a schema assertion — leave it, or update it for
clarity. It must still pass.

- [ ] **Step 7: Rollback (only if needed)**

```bash
python src/scripts/backup_mongo_collections_tool.py restore rc07-pre-thermal-arrays --all --yes
python src/scripts/collection_fingerprint_tool.py capture MorrowThermalLoads --out exports/rc07_after.json
python src/scripts/collection_fingerprint_tool.py compare exports/rc07_before.json exports/rc07_after.json
```

- [ ] **Step 8: Commit**

```bash
git add scripts/get_participant_profile_tool.py src/models/county_loads_data.py \
        scripts/calculate_missing_thermal_loads_tool.py .claude_docs/script_descriptions.md
git commit -m "perf(storage): replace ThermalLoads regression inputs with a count

kwh_hl_cl_loads and gas_hl_cl_loads held 11.8M elements (765 MB logical, 81%
of the ThermalLoads family) beside the slopes computed from them. Reproduced
one parcel's regression from time_series_elec + county weather before removal.
Retains kwh_n/gas_n, the only value any reader used. Runs after the thermal
slope remediation, not during it."
```

---

## Task R-08 — Shorten the delivery-tag field names (OPTIONAL)

**Recovers:** 217 MB logical, ~59 MB disk. **Read the trade-off before doing this.**

**Why the audit flagged it, and why the framing changed on inspection.** `last_utility_ingest`
costs 124.5 MB and `source_delivery` 92.2 MB across 4.14M documents, and each holds one of
only two values (`"aug2026"`, `"jan2026"`). That looks like an enum problem. It is not:

```
BSON element = 1 type byte + field name + null terminator + value
"last_utility_ingest" -> 1 + 19 + 1 = 21 bytes of NAME
"aug2026"             -> 4 +  7 + 1 = 12 bytes of VALUE
                                      33 bytes total (matches the measured 33 B average)
```

**64% of the cost is the field name, not the value.** Shortening the value saves almost
nothing; the saving comes from renaming the fields, which trades 217 MB against readability
in every query, script and mental model that touches them.

**A correction worth recording:** these two fields look like duplicates and are not.
`source_delivery` is set once at document creation (`ingest.py:200`); `last_utility_ingest` is
updated on every merge (`ingest.py:193`). **1,394,178 documents have different values.**
`source_delivery` is first-seen provenance, `last_utility_ingest` is most-recent. Do not
"deduplicate" them.

**Recommendation: skip this task** unless the database is under real disk pressure. 59 MB is
2% of the file, and the other tasks recover 33× that without hurting legibility. It is
documented here so the decision is explicit rather than forgotten.

- [ ] **Step 1: If proceeding, confirm the read sites**

```bash
grep -rn "last_utility_ingest\|source_delivery" --include=*.py . | grep -v /venv/
```

Expected: 6 references — `scripts/audit_thermal_load_coverage_tool.py:49,60,137,138` (the
`staleness` check) and `src/tools/utility_bills/ingest.py:193,200`.

- [ ] **Step 2: If proceeding, rename behind a constant**

Add to `src/tools/utility_bills/ingest.py` and import everywhere rather than hard-coding the
short name in six places:

```python
FIELD_LAST_INGEST = 'lui'      # was 'last_utility_ingest' (R-08, 2026-09-16)
FIELD_SOURCE_DELIVERY = 'sd'   # was 'source_delivery'
```

Then rename in the data, checkpointing first (`rc08-pre-rename`, `--suffix ElectricalDB`):

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
db.getCollectionNames().filter(n=>n.endsWith("ElectricalDB")).forEach(n=>{
  const r=db.getCollection(n).updateMany({},
    {$rename:{"last_utility_ingest":"lui","source_delivery":"sd"}});
  print(n+": "+r.modifiedCount);});'
```

- [ ] **Step 3: Verify the staleness audit still works**

```bash
python scripts/audit_thermal_load_coverage_tool.py --check staleness
```

Expected: same delivery-tag distribution as baseline — aug2026 3,404,858 · jan2026 551,583.

- [ ] **Step 4: Commit, recording the decision either way**

```bash
git commit -m "perf(storage): shorten delivery-tag field names

OR, if skipped:

git commit --allow-empty -m "docs(storage): decline R-08 field-name shortening

64% of the 217 MB is field-name bytes, not values. Renaming recovers 59 MB
(2% of the file) at a permanent readability cost in every query. Declined
2026-09-16; revisit only under disk pressure. Also records that
source_delivery and last_utility_ingest are NOT duplicates — 1,394,178
documents differ (first-seen vs most-recent delivery)."
```

---

## Task R-09 — Compact every collection

> **Run this last.** Every task above creates new free space; one compact pass reclaims all of
> it. Running compact first means running it twice and getting less back.

**Recovers:** 1,261 MB as measured on 2026-09-16, plus whatever R-02 through R-08 freed —
expect substantially more than 1,261 MB by the time you get here.

**Why:** 41.5% of the file is WiredTiger free space: reusable by Mongo, but not returned to the
filesystem. Dozens of collections sit at almost exactly 49.5% free — the signature of a
full-collection rewrite, which is what every task above performs.

⚠️ **`compact` blocks writes on the collection while it runs** and holds an exclusive lock.
On a standalone `mongod` (which this is) there is no secondary to fail over to. Run it when
nothing else is using the database, largest collections first so an interruption still banks
the biggest wins.

- [ ] **Step 1: Full checkpoint**

```bash
python src/scripts/backup_mongo_collections_tool.py create rc08-pre-compact --full
```

- [ ] **Step 2: Record the before state**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");const s=db.stats();
print("dataSize    "+(s.dataSize/1048576).toFixed(0)+" MB");
print("storageSize "+(s.storageSize/1048576).toFixed(0)+" MB");
print("indexSize   "+(s.indexSize/1048576).toFixed(0)+" MB");' | tee exports/pre_compact_20260916.txt
```

- [ ] **Step 3: Compact, largest first, with progress**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");
const rows=db.getCollectionNames().map(n=>{
  const s=db.getCollection(n).aggregate([{$collStats:{storageStats:{}}}]).toArray()[0].storageStats;
  return {n:n, free:s.freeStorageSize||0, stor:s.storageSize};
}).filter(r=>r.free>1048576).sort((a,b)=>b.free-a.free);
print("compacting "+rows.length+" collections holding "+
      (rows.reduce((a,r)=>a+r.free,0)/1048576).toFixed(0)+" MB free");
rows.forEach(r=>{
  const t0=Date.now();
  db.runCommand({compact:r.n});
  const s=db.getCollection(r.n).aggregate([{$collStats:{storageStats:{}}}]).toArray()[0].storageStats;
  print(r.n.padEnd(30)+" "+(r.stor/1048576).toFixed(1)+" MB -> "+
        (s.storageSize/1048576).toFixed(1)+" MB  ("+((Date.now()-t0)/1000).toFixed(1)+"s)");});'
```

- [ ] **Step 4: Verify**

```bash
mongosh "mongodb://localhost:27017" --quiet --eval '
const db=db.getSiblingDB("empower_development");const s=db.stats();
let free=0;
db.getCollectionNames().forEach(n=>{
 free+=(db.getCollection(n).aggregate([{$collStats:{storageStats:{}}}]).toArray()[0]
        .storageStats.freeStorageSize||0);});
print("storageSize "+(s.storageSize/1048576).toFixed(0)+" MB");
print("free        "+(free/1048576).toFixed(0)+" MB ("+(100*free/s.storageSize).toFixed(1)+"%)");'
```

Expected: free space under 5% of the file; `storageSize` approaching the ~682 MB projection.

- [ ] **Step 5: Confirm the data survived**

```bash
python -m pytest tests/ -q -o addopts=""
python scripts/audit_thermal_load_coverage_tool.py --check all
```

Expected: full suite green; audit numbers match the post-remediation baseline.

- [ ] **Step 6: Commit the measurements**

```bash
git add exports/pre_compact_20260916.txt .claude_docs/script_descriptions.md
git commit -m "chore(storage): compact all collections after reclamation

Reclaims WiredTiger free space created by R-01..R-08 plus the 1,261 MB
present at the 2026-09-16 audit. Run last by design: every schema task
creates free space that a single compact pass returns to the filesystem."
```

---

## Task R-10 — Normalize oversized string `_id` (DEFERRED)

**Recovers:** 126 MB logical, ~18 MB disk. **Lowest value, highest risk in this runbook.**

**Why it was flagged:** 88 `*ElectricalDB` collections key on heterogeneous strings from 8 to
70 characters — 740,603 are 32-character hex UUIDs. They inflate the 120 MB of `_id_` indexes
and forfeit the creation timestamp an `ObjectId` carries for free. 89 of 170 collections have
no `_id` timestamp at all, which is why the audit's "oldest/newest document" column is blank
for every ElectricalDB.

**Why it is deferred, not scheduled:**

1. **`_id` is immutable.** Changing it means insert-new + delete-old for 3.5M documents, or a
   full collection rewrite — the most invasive operation in this runbook for the smallest disk
   return (18 MB, 0.6% of the file).
2. **The surrogate `_id` is load-bearing.** `src/tools/utility_bills/ingest.py` stores
   unmatched accounts under a *deterministic surrogate `_id`* so re-ingest is idempotent
   (`.claude_docs/script_descriptions.md`, ingest tool entry). Replacing those keys breaks
   idempotency unless the derivation is preserved exactly.
3. **It overlaps T-14.** The thermal runbook's T-14 owns the 3,239,625 electrical documents
   with no `parcel_id` — the same population that carries surrogate `_id`s.

**The genuine finding to carry forward — this one is worth acting on separately.** Several
collections store **both** `ObjectId` and `string` `_id` values:

```
AllenElectricalDB      25,658 ObjectId  +  16,999 string
AthensElectricalDB      7,287 ObjectId  +  18,168 string
BelmontElectricalDB    13,504 ObjectId  +   9,237 string
```

BSON sorts by *type* before value, so these collections cannot be paged consistently by `_id`.
That is a correctness issue, not a storage one, and it belongs in the thermal runbook's defect
list rather than here.

- [ ] **Step 1: Record the deferral rather than silently dropping it**

```bash
git commit --allow-empty -m "docs(storage): defer R-10 _id normalization

126 MB logical / 18 MB disk for a full rewrite of 3.5M immutable keys is the
worst ratio in the reclamation set, and the surrogate _id in the utility-bills
ingest is load-bearing for re-ingest idempotency. Deferred 2026-09-16.

Carries forward as a correctness issue, not a storage one: several
*ElectricalDB collections hold both ObjectId and string _id values
(AllenElectricalDB 25,658 + 16,999), so they cannot be paged consistently
by _id. Logged for the thermal remediation defect list."
```

---

## Appendix — verified command reference

```bash
source venv/bin/activate

# Audit (read-only, safe any time)
python scripts/audit_index_usage_tool.py
python scripts/audit_thermal_load_coverage_tool.py --check all

# Backup
python src/scripts/backup_mongo_collections_tool.py create <label> --suffix ElectricalDB
python src/scripts/backup_mongo_collections_tool.py create <label> --full
python src/scripts/backup_mongo_collections_tool.py list
python src/scripts/backup_mongo_collections_tool.py verify <label>
python src/scripts/backup_mongo_collections_tool.py restore <label> --all --yes

# Rollback proof
python src/scripts/collection_fingerprint_tool.py capture <Collection> --out exports/x.json
python src/scripts/collection_fingerprint_tool.py compare exports/before.json exports/after.json

# Reclamation (dry run by default)
python scripts/reclaim_electrical_storage_tool.py --rekey-series
python scripts/reclaim_electrical_storage_tool.py --rekey-series --county Morrow --execute

# Tests (addopts override required — see standing rule 6)
python -m pytest tests/ -q -o addopts=""
```

### Baseline numbers to check against (measured 2026-09-16, pre-reclamation)

| Metric | Value |
|---|---|
| Collections / documents | 170 / 6,790,915 |
| dataSize | 6,585 MB |
| storageSize | 3,039 MB |
| Live bytes | 1,778 MB |
| Free space | 1,261 MB (41.5%) |
| indexSize | 232 MB across 283 indexes |
| Zero-read non-`_id` indexes | 96 (49.9 MB) |
| `time_series_*` keys | 70,247,660 (100% suffixed) |
| `monthly_*` occurrences | 4,305,685 |
| ThermalLoads array elements | 11,833,066 |
| `parcel_key` rows | 2,877,627 (35 exceptions to the ltrim rule) |
| `_migration` docs | 326,877 |
| Delivery tags | aug2026 3,404,858 · jan2026 551,583 · null 182,398 |
| pytest baseline | **148 passed** (0.85s, measured 2026-09-16 17:45) |

### Collections with the most free space (compact targets)

| Collection | Free | Storage | % |
|---|---|---|---|
| CuyahogaElectricalDB | 182.2 MB | 363.4 MB | 50.1% |
| FranklinElectricalDB | 149.4 MB | 296.5 MB | 50.4% |
| CuyahogaThermalLoads | 119.3 MB | 240.7 MB | 49.6% |
| HamiltonElectricalDB | 80.1 MB | 194.8 MB | 41.1% |
| MontgomeryElectricalDB | 65.9 MB | 167.7 MB | 39.3% |
| FranklinThermalLoads | 48.3 MB | 97.1 MB | 49.7% |
| exposures | 41.1 MB | 87.6 MB | 46.9% |
| CuyahogaCountyResidential | 38.9 MB | 78.8 MB | 49.4% |
