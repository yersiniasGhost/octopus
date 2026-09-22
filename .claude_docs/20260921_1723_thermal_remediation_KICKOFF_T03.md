# Thermal Slope Remediation — kickoff prompt for T-03 (supersedes 20260921_1450)

Paste the block below after clearing context.

---

We are working through a thermal-slope remediation on the octopus project,
branch `feature/campaign-weather`. I have cleared context, so read these first:

    .claude_docs/20260921_1723_thermal_remediation_KICKOFF_T03.md    <- status, read first
    .claude_docs/20260916_1300_thermal_slope_remediation_runbook.md  <- execution runbook

Today I want to do exactly one task: **T-03 — dedupe Cuyahoga's 875 duplicates and add the
unique index.**

Ground rules:
- `source venv/bin/activate` before any Python.
- Do NOT start any other task. If you find a problem belonging to a different
  task, write it down and tell me — do not fix it.
- Take the checkpoint the runbook specifies for this task BEFORE any write, using
  `src/scripts/backup_mongo_collections_tool.py`. No checkpoint, no write.
- Write the tests first, then the script. Every write script is `--dry-run` by
  default and needs `--execute` to touch data.
- Show me the dry-run output and wait for my go-ahead before executing.
- Verify with `scripts/audit_thermal_load_coverage_tool.py`, never an ad-hoc query.
- New scripts: `scripts/` with a `_tool` suffix, plus an entry in
  `.claude_docs/script_descriptions.md`. Reusable ones go in `src/scripts/` or
  `src/tools/` with an entry in `.claude_docs/tools.md`.
- Commit when the task's "Done when" is satisfied.
- `pytest` needs `-o addopts=""` (pytest-cov is not installed).

Start by confirming the current state matches the "Baseline numbers, corrected" table
in the kickoff doc — **not** the runbook Appendix, which is now stale in one row — then
tell me your plan for T-03 before writing anything.

---

## Where things stand (2026-09-21 17:23)

**Branch** `feature/campaign-weather`. Five commits landed, suite **210 passing**
(`python -m pytest tests/ -q -o addopts=""`).

| commit | what |
|---|---|
| `e245414` | Task 0 — backup tooling, checkpoints `cp00-baseline` + `cp00-thermal`, rollback drill |
| `2cd8e07` | T-00 — per-county weather from Open-Meteo; `/home/warnd/` fallback deleted |
| `4368843` | T-15 — single joint model, billing-period validity, clean-break schema |
| `35f1b40` | kickoff prompt (superseded by this document) |
| `465478b` | **T-02 — 66,432 of 67,307 `parcel_id`s normalized. First database write.** |
| `40818bb` | **T-00 remainder — weather for all 25 counties, 57 MB under `data/weather/`** |

**The database has been written to once**, by T-02. Checkpoint `cp02-pre-typenorm`
was taken first and still exists.

### Baseline numbers, corrected

The runbook Appendix was measured 2026-09-16. One row has intentionally changed since.
Confirm against **this** table:

| Check | Expected now | vs runbook Appendix |
|---|---:|---|
| `coverage` missing, best key | 60,733 | unchanged |
| `coverage` missing, naive parcel_id | 62,355 | unchanged |
| `joinkey` phantom | 1,622 | unchanged |
| `types` thermal_non_string | **875** | **was 67,307 — T-02 converted 66,432** |
| `duplicates` thermal_excess | 875 | unchanged — this is T-03's target |
| `duplicates` electrical_excess | 16,419 | unchanged |
| `slopes` null_or_absent | 16,279 | unchanged |
| `slopes` exactly_zero | 6,151 | unchanged |
| `slopes` real_gas_slopes | 126,987 | unchanged |
| `staleness` without_provenance | 749,785 | unchanged |
| aug2026 parcel-matched docs | 646,375 | unchanged |

Any other deviation means something changed outside these commits — reconcile before proceeding.

### Checkpoints on disk

`cp00-baseline` (full, 1,003 MB) · `cp00-thermal` (25 collections, 135 MB) ·
`cp02-pre-typenorm` (25 collections, 135 MB). T-03 takes `cp03-pre-dedupe`.

---

## T-03 — what the runbook says, and four things it does not

The runbook's T-03 section (line ~314) is still accurate on scope, keep rule and
verification. Read it. These four facts were discovered during T-02 and are not in it.

### 1. The 875 duplicates are int/str type pairs, not two strings

`CuyahogaThermalLoads` holds 875 pairs where one document has `parcel_id` as `int`
and the other as `str` of the same digits. T-02 deliberately did **not** convert those
875 ints — its collision guard skipped them, because converting would have created a
genuine duplicate key. They are exactly the 875 in `duplicates thermal_excess`; the
counts match because they are the same documents.

**Consequence:** a dedupe that groups by raw `parcel_id` will find *nothing*, because
`123 != "123"` in Python and in MongoDB alike. Group by
`src.tools.parcel_id.normalize_parcel_id` — the same function the audit verifies with.

**The loser candidates are already enumerated.** T-02 exported every contested key with
the `_id` of the skipped int document:

    exports/t02_parcel_id_collisions_20260921_155427.json

875 entries, each `{'key': ..., 'ids': [...], 'reason': 'string document already holds this key'}`.
Consume that file rather than rediscovering it. Do **not** assume the int document is
the loser — apply the runbook's keep rule (newest `calculated_at`; tie-break highest
`kwh_hl_r2`; then longest `kwh_hl_cl_loads`; never drop a document carrying real gas
slopes for one that does not). A prior session observed that the two members of a pair
hold *different* thermal data, so the choice is real.

### 2. A unique index will NOT catch type-mismatch duplicates

MongoDB unique indexes compare BSON values including type. `int 123` and `"123"` are
different index keys, so `createIndex({parcel_id: 1}, {unique: true})` would **succeed
while the duplicates remain**, and report healthy. That is false confidence, not a check.

**Correct order — do not reorder:**

1. Dedupe (drop the losers, keeping one document per normalized key)
2. Re-run T-02 on the survivors:
   `python scripts/normalize_thermal_parcel_id_types_tool.py --county Cuyahoga --execute`
   This should convert the ~875 surviving ints and take `types` to **0**, closing T-02.
3. *Then* create the unique index across all 25 collections.

Building the index at step 3 rather than step 1 is what makes it a real constraint.

### 3. The write path uses `update_many` as a workaround that the index will break

`scripts/calculate_missing_thermal_loads_tool.py:575`:

```python
db[thermal_coll].update_many({'parcel_id': parcel_id},
                             thermal_update_ops(document), upsert=True)
```

The comment at lines 563–566 explains why: the collections carry no unique index, so
every existing copy is updated to identical values rather than one of them being picked
arbitrarily. Once T-03 lands, that reasoning is obsolete and the comment is wrong.
Convert to `update_one(..., upsert=True)` and rewrite the comment to say the unique
index is what now guarantees one document per parcel. Leaving `update_many` behind a
unique index is not harmful, but it documents a constraint that no longer exists.

Present indexes on every `*ThermalLoads`: `_id_` and `parcel_key_1`. None unique.

### 4. T-03 closes T-02

T-02's "Done when" is *zero* non-string, and it currently reads 875. Those 875 are
step 2 above. When T-03 finishes, say so explicitly in the commit — otherwise the
875 looks like an unexplained remainder to whoever reads `types` next.

---

## Open items, none blocking T-03

1. **`CuyahogaElectricalDB` holds 1,022 `int` `parcel_id`s** (`str 255,975 · int 1,022`).
   T-02's scope was ThermalLoads only, and the audit's `mismatch` flag reads the thermal
   side alone, so it now shows clean. But `get_missing_parcels()` compares raw values on
   **both** sides, so this is still a live mismatch source for Cuyahoga. It belongs to no
   existing task and needs one. Do not fix it inside T-03.
2. **331 pre-2015 electrical readings across 44 parcels** take a silent `0.0` heating load,
   because the weather fetch starts 2015-01-01 while the electrical series begins
   2005-08-18 (Ross). 0.001% of 30,822,426 readings. Documented in the runbook's T-00
   section with the reasoning; revisit only if a parcel-level defect traces to one of them.
3. **`get_missing_parcels()` logs distinct keys as "electrical records".** Morgan logs
   "Found 1,351 electrical records" against 1,458 documents — the gap is `electrical_excess`
   collapsing into a set. Misleading log line, not a defect.
4. **`below_min_periods` 23,146 vs T-13's 45,781** — different populations, never
   reconciled. Reconcile before starting T-13.
5. **The published artifact is partly wrong.**
   https://claude.ai/code/artifact/ef09ff18-b052-428a-871c-4c714f6c24ed
   It attributes the 72.8% negative heating slopes entirely to the omitted-cooling
   mechanism; the larger cause turned out to be gap rows pairing one month's kWh with a
   multi-year weather total. Private and unshared. Ask before republishing.
6. **Unrelated uncommitted work in the tree**, untouched across all five commits:
   `.gitignore`, `enrich_participants_franklin_demographics_tool.py`, three
   `aceee`/`text7x_8x` scripts, and `.claude_docs/20260916_1739_storage_reclamation_runbook.md`.
   `script_descriptions.md` carries 90 lines of unrelated edits — stage only your own hunk
   (build the blob from `git show HEAD:<file>` plus your entry and
   `git update-index --cacheinfo`; `git add -p` is unavailable, the harness blocks
   interactive flags).

## Things that will bite you

- `pytest` needs `-o addopts=""`.
- `mongodump` has no `--nsInclude`; the backup tool enumerates collections deliberately.
- `pgrep -f "<pattern>"` matches your own shell. Use `ps -eo pid,args | grep -E "<pattern>"`.
- The audit tool **normalizes on read** (`_norm` → `src/tools/parcel_id.normalize_parcel_id`).
  That is why it reported the eight type-mismatched counties healthy all along. It measures
  what the data *means*; some defects live in what the production code *compares*. For T-03,
  verify the unique index by inspecting `index_information()` for `unique: true`, and
  confirm the dedupe against `--check duplicates`.
- Long fetches and scans: background them. The harness blocks bare `sleep` chaining.

## Recommended order after T-03

**T-15 migration** (recompute 794,636 records — both hard prerequisites, T-02 and T-00,
are now done; the runbook also lists a refresh of 3,265 participant copies, which has not
been scoped) → **T-14a** (address matching, 25 counties, ~99,000 recoverable parcels) →
**T-07**.
