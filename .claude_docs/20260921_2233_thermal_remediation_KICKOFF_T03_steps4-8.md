# Thermal Slope Remediation — kickoff prompt for T-03 steps 4–8 (supersedes 20260921_1723)

Paste the block below after clearing context.

---

We are mid-way through T-03 of a thermal-slope remediation on the octopus project,
branch `feature/campaign-weather`. I have cleared context, so read these first:

    .claude_docs/20260921_2233_thermal_remediation_KICKOFF_T03_steps4-8.md   <- status, read first
    .claude_docs/20260916_1300_thermal_slope_remediation_runbook.md          <- execution runbook (T-03 at ~line 314)

**Steps 1–3 of T-03 are done: checkpoint taken, tests written, tool written, dry run
verified and approved. Nothing has been written to the database yet.** Today I want
steps 4–8 and nothing else.

Ground rules:
- `source venv/bin/activate` before any Python.
- Do NOT start any other task. If you find a problem belonging to a different task,
  write it down and tell me — do not fix it.
- `pytest` needs `-o addopts=""` (pytest-cov is not installed).
- Verify with `scripts/audit_thermal_load_coverage_tool.py`, never an ad-hoc query.
- Show me the output of each write step before moving to the next.
- **Gas is deprioritized.** The keep rule is electric-first and drops 549 gas models
  on purpose. Do not re-add a gas constraint, and do not treat the falling gas count
  as a regression.
- Commit when the task's "Done when" is satisfied, amended per "Done when, amended" below.

Start by confirming the state matches "Where things stand" below, then run step 4.

---

## Where things stand (2026-09-21 22:33)

**Branch** `feature/campaign-weather`, HEAD `7382954`. Seven thermal-remediation commits
landed (`e245414..7382954`) on top of nine earlier campaign-weather commits.
Suite **246 passing** (`python -m pytest tests/ -q -o addopts=""`) — 210 before T-03,
plus 36 in `tests/test_thermal_dedupe.py`.

**The database has been written to exactly once**, by T-02 (`465478b`). T-03 has written
nothing. Checkpoints `cp02-pre-typenorm` and `cp03-pre-dedupe` both exist.

### Uncommitted, and belonging to T-03 — stage exactly these three

| path | state |
|---|---|
| `scripts/dedupe_thermal_loads_tool.py` | new, untracked |
| `tests/test_thermal_dedupe.py` | new, untracked, 36 tests |
| `.claude_docs/script_descriptions.md` | **modified — your hunk is already written**, see staging note |

### Uncommitted and NOT yours — do not stage

`.gitignore`, `scripts/enrich_participants_franklin_demographics_tool.py`,
`scripts/analyze_aceee_campaign_association_tool.py`,
`scripts/append_dropped_rows_text7x_8x_tool.py`,
`scripts/fill_text7x_8x_demographics_from_county_tool.py`,
`.claude_docs/20260916_1739_storage_reclamation_runbook.md`.

**Staging note.** `script_descriptions.md` carries ~90 lines of unrelated edits *plus* the
`## dedupe_thermal_loads_tool.py` entry this task already added. Stage only that entry:
build the blob from `git show HEAD:<file>` plus your entry and `git update-index --cacheinfo`.
`git add -p` is unavailable — the harness blocks interactive flags.

### Verified state, measured 2026-09-21

| Check | Value now | After T-03 completes |
|---|---:|---:|
| `duplicates` thermal_excess | 875 (all Cuyahoga) | **0** |
| `types` thermal_non_string | 875 (all Cuyahoga) | 660 after step 4, **0** after step 5 |
| `slopes` real_gas_slopes | 126,987 | **126,438** (deliberate, see below) |
| `coverage` missing, best key | 60,733 | 60,733 unchanged |
| `coverage` missing, naive parcel_id | 62,355 | 62,355 unchanged |
| `joinkey` phantom | 1,622 | 1,622 unchanged |
| `duplicates` electrical_excess | 16,419 | 16,419 unchanged |
| `slopes` null_or_absent / exactly_zero | 16,279 / 6,151 | unchanged |
| `staleness` without_provenance | 749,785 | 749,785 unchanged |
| `CuyahogaThermalLoads` documents | 260,939 | **260,064** |
| all 25 collections, documents | 795,511 | **794,636** |

Any other deviation means something changed outside this work — reconcile before proceeding.

### Checkpoints on disk (`~/backups/octopus-thermal`)

`cp00-baseline` (full, 1,003 MB) · `cp00-thermal` (25 colls, 134.8 MB) ·
`cp02-pre-typenorm` (25 colls, 134.8 MB) · **`cp03-pre-dedupe` (25 colls, 134.6 MB,
created 19:48 — this is T-03's rollback point)**.

Rollback: `python src/scripts/backup_mongo_collections_tool.py restore cp03-pre-dedupe --collection CuyahogaThermalLoads`

---

## The decision that changed T-03, and what it costs

**Direction given 2026-09-21: deprioritize gas, electric consumption is the focus.**
Gas will be re-added more intelligently later.

The runbook's keep rule made "never drop a document carrying real gas slopes" an absolute
constraint. That is now **dropped**. The keep rule is:

    newest calculated_at → highest kwh_hl_r2 → longer kwh_hl_cl_loads → str parcel_id → lowest _id

Measured consequences across all 875 pairs:

| Decision | Pairs | Survivor |
|---|---:|---|
| int has higher `kwh_hl_r2` | 390 | int |
| str has **no electric model at all** (gas-only parcel) | 270 | int |
| str has higher `kwh_hl_r2` | 215 | str |

- Not one document in any pair carries `calculated_at`, so the primary rule never fires
  on this data — every pair resolves on r² alone, with no ties and no fallthrough to loads length.
- **660 losers are `str`**, so 660 `int` documents survive and step 5 converts 660.
- **549 dropped documents carry a fitted gas model**, so `real_gas_slopes` goes
  126,987 → 126,438. **This is intended. Do not "fix" it.**
- The 270 gas-only parcels are half that loss and are cleanly identifiable in the export
  (`kwh_hl_r2` absent + `gas_hl_slope` real) — a well-defined population for the later gas work.

Three recovery paths exist for the dropped gas: checkpoint `cp03-pre-dedupe`, the whole-document
JSON export written by step 4, and re-derivation from gas billing data.

---

## Steps 4–8, in order. Do not reorder.

### Step 4 — execute the dedupe

```bash
python scripts/dedupe_thermal_loads_tool.py --county Cuyahoga --execute \
  --t02-collisions exports/t02_parcel_id_collisions_20260921_155427.json
```

The approved dry run (19:52) reported: examined 260,939 · dup_parcels 875 · to_remove 875 ·
gas_dropped 549 · null_pid 0, and the cross-check confirmed the discovered key set is
*exactly* T-02's 875. **Expect identical numbers with `deleted` now 875.** If `to_remove`
is not 875 or the cross-check raises `CollisionSetMismatch`, stop and tell me.

The run writes `exports/t03_dedupe_losers_<timestamp>.json` containing all 875 losers whole,
before deleting. A dry-run export already exists at `exports/t03_dedupe_losers_20260921_195250.json`;
the execute run writes a second one. Keep both.

Verify: `--check duplicates` → `thermal_excess` **0** everywhere.

### Step 5 — re-run T-02 on the survivors, closing T-02

```bash
python scripts/normalize_thermal_parcel_id_types_tool.py --county Cuyahoga --dry-run
python scripts/normalize_thermal_parcel_id_types_tool.py --county Cuyahoga --execute
```

Expect **660 conversions planned, zero collisions** — the collisions are gone because
the contested documents are gone. Verify `--check types` → `thermal_non_string` **0**
and `mismatch` False for every county. **This closes T-02**, whose "Done when" has read
875 short since `465478b`. Say so explicitly in the commit message.

### Step 6 — the unique index across all 25 collections

```bash
python scripts/dedupe_thermal_loads_tool.py --create-unique-index --dry-run
python scripts/dedupe_thermal_loads_tool.py --create-unique-index --execute
```

Built *now*, not earlier, and this ordering is the whole point: MongoDB unique indexes compare
BSON value **including type**, so `int 123` and `"123"` are different index keys. An index built
before step 4 would have succeeded with all 875 duplicates still present and reported the
collection healthy. `create_unique_parcel_id_index()` re-groups on `normalize_parcel_id` and
raises `DuplicatesRemain` before touching the index, so the guard is real rather than trusting
the index to catch it.

**Fayette already carries a non-unique `parcel_id_1`.** Uniqueness cannot be added in place;
the tool drops it first. Expect Fayette to report a drop-then-create and the other 24 a plain create.

Verify by inspecting `index_information()` on all 25 for `unique: true` — the audit tool does
not check indexes.

### Step 7 — convert the write path

`scripts/calculate_missing_thermal_loads_tool.py:575`:

```python
db[thermal_coll].update_many({'parcel_id': parcel_id},
                             thermal_update_ops(document), upsert=True)
```

`update_many` is a workaround for the missing unique index, explained in the docstring at
lines 563–566 ("the collections carry no unique index on parcel_id (T-03) and Cuyahoga already
holds 875 duplicates"). After step 6 that reasoning is obsolete and the comment is **wrong**.

Convert to `update_one(..., upsert=True)` and rewrite the docstring to say the unique index is
what now guarantees one document per parcel. Tests first — `tests/test_thermal_missing_parcels.py`
and `tests/test_thermal_joint_model.py` cover this area; check whether either asserts on
`update_many` before changing it.

### Step 8 — verify and commit

```bash
python scripts/audit_thermal_load_coverage_tool.py --check all
python -m pytest tests/ -q -o addopts=""
```

Against the "After T-03 completes" column above. Suite must be ≥246 passing.

**Done when, amended:** zero thermal duplicates · `types` zero non-string · unique index
`unique: true` on all 25 · `update_one` upsert path live · **`real_gas_slopes` = 126,438,
not 126,987** — the runbook's "gas count still 126,987" is superseded by the electric-first
direction. Record the amendment in the commit and in the runbook's T-03 section so a later
reader does not treat 126,438 as a regression.

Commit message should record: T-03 complete, T-02 closed, the electric-first keep rule and
its 549-gas-model cost, and the export path that makes it reversible.

---

## Open items, none blocking steps 4–8

1. **`CuyahogaElectricalDB` holds 1,022 `int` `parcel_id`s** (`str 255,975 · int 1,022`).
   T-02's scope was ThermalLoads only and the audit's `mismatch` flag reads the thermal side
   alone, so it shows clean — but `get_missing_parcels()` compares raw values on **both** sides,
   so this is still a live mismatch source for Cuyahoga. Belongs to no existing task; needs one.
2. **The index inventory in the older docs is stale.** They claim every `*ThermalLoads` carries
   `_id_` and `parcel_key_1`. Actually **Fayette** also has a non-unique `parcel_id_1`, and
   **Hardin, Montgomery, Ross and Scioto have only `_id_`** — no `parcel_key_1` at all. That
   last fact may matter to T-04, which wants to join on `parcel_key`.
3. **331 pre-2015 electrical readings across 44 parcels** take a silent `0.0` heating load; the
   weather fetch starts 2015-01-01 while Ross's electrical series begins 2005-08-18. 0.001% of
   30,822,426 readings. Documented in the runbook's T-00 section.
4. **`get_missing_parcels()` logs distinct keys as "electrical records"** — Morgan logs
   "Found 1,351 electrical records" against 1,458 documents, the gap being `electrical_excess`
   collapsing into a set. Misleading log line, not a defect.
5. **`below_min_periods` 23,146 vs T-13's 45,781** — different populations, never reconciled.
   Reconcile before starting T-13.
6. **The published artifact is partly wrong.**
   https://claude.ai/code/artifact/ef09ff18-b052-428a-871c-4c714f6c24ed
   It attributes the 72.8% negative heating slopes entirely to the omitted-cooling mechanism;
   the larger cause was gap rows pairing one month's kWh with a multi-year weather total.
   Private and unshared. Ask before republishing.

## Things that will bite you

- `pytest` needs `-o addopts=""`.
- `mongodump` has no `--nsInclude`; the backup tool enumerates collections deliberately.
- `pgrep -f "<pattern>"` matches your own shell. Use `ps -eo pid,args | grep -E "<pattern>"`.
- The audit tool **normalizes on read** (`_norm` → `src/tools/parcel_id.normalize_parcel_id`).
  It measures what the data *means*; some defects live in what the production code *compares*.
  That is why step 6 verifies the index by `index_information()` rather than by the audit.
- Grouping duplicates on the raw `parcel_id` finds **nothing**. Always normalize first.
- `CuyahogaThermalLoads` is 446 MB across 260,939 documents. The dedupe tool reads it in two
  passes — `parcel_id` alone, then whole documents by `_id` for duplicated parcels only. Do not
  "simplify" that into one pass; and never rank on a projected document, which would see no
  `kwh_hl_r2` anywhere and silently fall through to the `_id` tie-break.
- Long scans: background them. The harness blocks bare `sleep` chaining.

## Recommended order after T-03

**T-15 migration** (recompute 794,636 records — both hard prerequisites, T-02 and T-00, are done;
the runbook also lists a refresh of 3,265 participant copies, not yet scoped) → **T-14a**
(address matching, 25 counties, ~99,000 recoverable parcels) → **T-07**.

Gas re-add, when it comes: start from `exports/t03_dedupe_losers_*.json` and the 270 gas-only
parcels it identifies.
