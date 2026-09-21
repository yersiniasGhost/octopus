# Thermal Slope Remediation — Execution Runbook

**Created:** 2026-09-16 · **Branch:** `feature/campaign-weather` · **Database:** `empower_development` @ `localhost:27017`
**Findings document:** `.claude_docs/20260916_1113_thermal_slope_remediation_todo.md`
**Artifact:** https://claude.ai/code/artifact/b2b997c8-9bc9-4891-8cf6-505f3144c8a2

One task per session. Each task below is self-contained: it states its own preconditions,
backup checkpoint, build, test, dry run, execute, verify and rollback. You do not need the
findings document in context to run a task — everything needed is repeated here.

---

## 0. Standing rules

1. `source venv/bin/activate` before any Python. Non-negotiable — the tools import `pymongo`, `sklearn`, `pandas`.
2. **No write to `*ThermalLoads` without a checkpoint taken in the same session.** Checkpoints cost 21 seconds.
3. Every write script takes `--dry-run` and defaults to it. A script without a dry run does not get run.
4. Commit after each task. Restore points are cheap; re-deriving state is not.
5. New scripts go in `scripts/` with a `_tool` suffix and an entry in `.claude_docs/script_descriptions.md`.
   Reusable ones go in `src/scripts/` with an entry in `.claude_docs/tools.md`.
6. Verify with `scripts/audit_thermal_load_coverage_tool.py`, never with an ad-hoc query typed from memory.
7. **pytest needs `-o addopts=""`.** `pyproject.toml` sets
   `addopts = "-v --cov=app --cov-report=html --cov-report=term"`, but `pytest-cov` is **not installed**
   in the venv, so a bare `python -m pytest` fails with `unrecognized arguments: --cov=app` before
   collecting anything. Either run `python -m pytest tests/ -q -o addopts=""` or
   `pip install pytest-cov` once and drop the override. Baseline 2026-09-16: **111 passed**.
   (Corrected 2026-09-21: there **is** an `app` package — `tests/test_applicant_dashboard.py`
   imports `app.services.campaign_data_service` — so `--cov=app` is a valid target. The only
   problem is that `pytest-cov` is not installed. Baseline after T-00: **155 passed**.)

### Environment facts (measured 2026-09-16)

| Fact | Value |
|---|---|
| mongod | 7.0.30 |
| mongodump / mongorestore | 100.14.1 |
| Disk free on `/home` | 197 GB |
| Database size | 6.9 GB dataSize · 3.2 GB storage · 170 collections |
| All 25 `*ThermalLoads` | 0.99 GB — checkpoint takes **21s / 135 MB** |
| All 88 `*ElectricalDB` | 4.89 GB |
| Full-database archive | **94s / 957 MB** |

⚠️ `mongodump` has **no `--nsInclude`** flag (that is mongorestore only). The backup tool
enumerates collections and dumps them one at a time. Do not "simplify" it back.

---

## 1. Backup system

Tool: `src/scripts/backup_mongo_collections_tool.py` (tested — create, list and verify all pass).
Checkpoints live in `~/backups/octopus-thermal/<label>/`, override with `OCTOPUS_BACKUP_ROOT`.

```bash
source venv/bin/activate

# Checkpoint every *ThermalLoads collection (21s, 135 MB)
python src/scripts/backup_mongo_collections_tool.py create cp03-pre-dedupe --suffix ThermalLoads

# Whole database, single archive (94s, 957 MB) — baseline and pre-calculation only
python src/scripts/backup_mongo_collections_tool.py create cp00-baseline --full

# What do I have?
python src/scripts/backup_mongo_collections_tool.py list

# Prove a checkpoint restores — into a scratch db, production untouched
python src/scripts/backup_mongo_collections_tool.py verify cp03-pre-dedupe

# Roll back (destructive: drops, then restores)
python src/scripts/backup_mongo_collections_tool.py restore cp03-pre-dedupe --collection CuyahogaThermalLoads
python src/scripts/backup_mongo_collections_tool.py restore cp03-pre-dedupe --all --yes
```

Labels are refused if they already exist — checkpoints are never silently overwritten.

### Checkpoint schedule

| Label | Take before | Scope |
|---|---|---|
| `cp00-baseline` | anything at all | `--full` |
| `cp01-pre-gasfix` | T-01 | ThermalLoads |
| `cp02-pre-typenorm` | T-02 | ThermalLoads |
| `cp03-pre-dedupe` | T-03 | ThermalLoads |
| `cp04-pre-indexes` | T-05 | ThermalLoads |
| `cp05-pre-parcelkey` | T-08 | `--full` (writes to ElectricalDB) |
| `cp06-pre-compute` | T-07 | `--full` |
| `cp07-pre-provenance` | T-10 | ThermalLoads |
| `cp08-pre-refresh` | T-09 | `--full` |
| `cp09-pre-quality` | T-11 / T-12 | ThermalLoads |

Prune checkpoints once the phase after them is verified and committed. At ~135 MB each the
whole schedule is under 4 GB against 197 GB free — do not prune early to save space.

---

## Task 0 — Baseline and rollback drill

**Do this first. Nothing else runs until it passes.**

```bash
source venv/bin/activate
python src/scripts/backup_mongo_collections_tool.py create cp00-baseline --full
python src/scripts/backup_mongo_collections_tool.py create cp00-thermal --suffix ThermalLoads
python src/scripts/backup_mongo_collections_tool.py verify cp00-thermal
```

**Rollback drill.** The restore path has been exercised through `verify` (which restores into a
scratch database), but `restore --collection` against production has **not** been run. Prove it now,
while the database is still pristine, on the smallest collection:

```bash
# MorrowThermalLoads — 1,124 docs, the smallest in the set
python src/scripts/backup_mongo_collections_tool.py restore cp00-thermal --collection MorrowThermalLoads --yes
python scripts/audit_thermal_load_coverage_tool.py --check coverage --county Morrow
```

**Done when:** `verify` prints `VERIFIED` for all 25 collections, the drill restores Morrow to
1,124 documents, and `list` shows both checkpoints.

**If the drill fails:** stop. Do not proceed to any task that writes. A remediation without a
proven rollback is how the 126,987 gas records in T-01 get lost permanently.

---

## Task T-00 — Acquire weather data (PREREQUISITE, newly discovered)

**Priority:** Blocker for T-07 and T-09. Neither can run without this.

**Issue.** `calculate_missing_thermal_loads_tool.py` loaded weather in this order:
1. `--weather-file` if given
2. `data/franklin_weather_hourly.csv` — does not exist
3. Hardcoded fallback to `/home/warnd/Downloads/72428014821(2).csv`

**Correction (2026-09-21):** those NOAA files **are present and readable** — this runbook
originally said they were not. That makes the defect worse, not better: the fallback loads
successfully and silently. Coverage is `72428014821.csv` = 2008, `(2).csv` = 2023,
`(1).csv` = 2024-01-01 → **2024-11-11**, and the fallback list uses only the last two.

Measured billing-period span the slopes must regress against: **2015-02-13 (Cuyahoga) →
2026-08-09 (Montgomery)**. So roughly 21 months at the recent end had no weather at all, and
Cuyahoga was missing eight years at the old end. `heating_load()` returns `0.0` when fewer
than two observations fall in the window, so an uncovered billing period contributes a silent
zero to the regression rather than raising. Together with T-12 coercing failures to `0.0`,
there were two independent paths manufacturing fake zeros.

**Second issue — wrong station for five counties.** Station `72428014821` is John Glenn Columbus
International (KCMH), in **Franklin County**. The tool applies whatever file it loads to whatever
`--county` you pass. T-07's 60,733 parcels span Montgomery (Dayton), Cuyahoga (Cleveland, Lake Erie),
Ottawa (Port Clinton, Lake Erie), Hancock (Findlay) and Athens (Appalachian southeast). Columbus
degree-hours do not describe any of them. Running as-is produces slopes that look valid and are wrong.

**Build — DONE 2026-09-21.** NOAA per-station sourcing was **rejected** in favour of the
Open-Meteo archive already in use on this branch (`scripts/backfill_campaign_weather_tool.py`):
free, no API key, hourly °F, serves 1940 → ~5 days ago, and its `COUNTY_CENTROIDS` table already
covers exactly the 25 thermal counties. Trade-off accepted: ERA5 reanalysis on a ~9–25 km grid
rather than physical station observations, so recomputed Franklin slopes will shift slightly
against the 44,851 records stamped `2026-01-19`. The complete 2023 NOAA Franklin file remains on
disk if that comparison is ever wanted.

- `src/tools/county_weather.py` — `COUNTY_CENTROIDS`, `normalize_county`, `ARCHIVE_URL`,
  `SOURCE_TAG`, `centroid()`, `weather_csv_path()`, `resolve_weather_file()`. Extracted from
  `backfill_campaign_weather_tool.py`, which now imports them. One table, not two.
- `scripts/fetch_county_weather_hourly_tool.py` — `--county|--all`, `--start`, `--end`,
  `--dry-run` default. Writes `data/weather/{County}_hourly.csv` (`datetime,T`) plus a
  `.meta.json` provenance sidecar. Chunked by calendar year so one failure costs one year.
- Calculation tool: resolution is now `--weather-file` → `data/weather/{County}_hourly.csv` →
  **raise**. The `/home/warnd/` fallback is deleted and an unmapped county raises rather than
  silently using Franklin. Every written document carries `weather_source`,
  `weather_location` and `weather_range`.
- **Note:** `data/` is gitignored, so the fetched CSVs are not committed. Reproducibility comes
  from the fetch tool plus the sidecar. The `raise` is what keeps that failure loud.

**Also fixed inside T-00 — unlinked records crashed candidate selection.**
`get_missing_parcels()` built its electrical set with no null filter, so `parcel_id: None`
entered the set and `sorted()` raised
`TypeError: '<' not supported between instances of 'NoneType' and 'str'` — for **all six**
counties T-07 targets, not just Montgomery. The tool has therefore been unrunnable since the
pre-enrollment ingest in `fbed58c` introduced null-`parcel_id` documents, which explains why
nothing has been computed since the Franklin batch of `2026-01-19`.
Fix: skip falsy `parcel_id` when building both sets, and log how many were excluded. Nothing is
deleted — those records carry real addresses and real usage, and recovering them is T-14. This
makes the calculator agree with the audit tool, which already excludes `no_parcel_id` from
`eligible`.

**Test — DONE.** 31 tests across three files, suite 124 → **155 passed**.
- `tests/test_thermal_weather_selection.py` (15) — the station follows `--county`; an unmapped
  county raises and the message never mentions Franklin; a mapped-but-unfetched county raises
  and names the fetch tool; `--weather-file` overrides; all 25 thermal counties have a centroid;
  `from_clean_csv` parses the fetched format; provenance distinguishes two counties;
  heating/cooling degree-hours hand-checked over a flat 24-hour window (230.0 each);
  an uncovered window returns 0.0 — the fail-open behaviour, documented deliberately.
- `tests/test_county_weather_fetch.py` (9) — year chunking, payload parsing, nulls dropped while
  a genuine 0.0 °F reading survives, metadata sidecar.
- `tests/test_thermal_missing_parcels.py` (7) — null / absent / empty-string `parcel_id`
  excluded, no crash, thermal-side nulls don't mask real parcels.

**Dry run.**
```bash
python scripts/calculate_missing_thermal_loads_tool.py --county Franklin --limit 5 --dry-run --verbose
```
Expect: weather loads, observation count and date range print, 5 parcels compute, **nothing written**.

**Verify.** Date range covers every billing period in scope — the electrical series now runs through
the aug2026 delivery, so weather must too. A weather file ending in 2024 silently truncates
`heating_load()` to zero for later periods.

**Done when:** the dry run above completes for Franklin *and* Montgomery against **different
county weather series**, and r² on the 5 sample parcels is plausible (Franklin baseline: compare
against the 44,851 records stamped `2026-01-19`).

**Status 2026-09-21:** code and tests complete; weather not yet fetched. Candidate selection now
runs clean on real data — Montgomery 31,846 missing (198,762 unlinked excluded), Franklin 18,641
(216,887 excluded), Athens 293 (18,168 excluded) — and each then stops with a clear
"no weather data for X, fetch it first". Those counts remain above the audit's 31,107 / 17,671 /
283; the residual is T-02 type mismatches and T-04 phantoms, as expected.

---

## Phase P0 — Blockers

### T-01 — Gas regressions destroyed on re-run

**Priority:** Critical — irreversible data loss.

**Issue.** `insert_thermal_loads()` hardcodes `gas_hl_slope: -1`, `gas_cl_slope: -1` and their
intercepts and r². **126,987 `CuyahogaThermalLoads` documents hold real gas regressions** (sampled:
`gas_hl_slope 0.00177`, `gas_hl_r2 0.723`). Any re-run over Cuyahoga overwrites them with `-1`.

**Checkpoint:** `cp01-pre-gasfix` (ThermalLoads).

**Build.** In `insert_thermal_loads()`, split the document. Electric fields go in the update body;
the gas block moves to `$setOnInsert` so it is written only when creating a new document. Convert
`insert_one` to `update_one(..., upsert=True)` — this overlaps T-03, do them together if convenient.

**Test.** `tests/test_thermal_gas_preservation.py`
- upsert over a doc with real gas slopes leaves every `gas_*` field byte-identical
- upsert creating a new doc writes the `-1` sentinels
- electric fields update in both cases

**Dry run.**
```bash
python scripts/calculate_missing_thermal_loads_tool.py --county Cuyahoga --limit 20 --dry-run --verbose
```

**Execute.** No data migration — this is a code fix. It lands with the first write task that follows.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check slopes
```
`real_gas_slopes` must still total **126,987**. If it drops, restore immediately.

**Rollback.** `restore cp01-pre-gasfix --collection CuyahogaThermalLoads`

**Done when:** tests pass and the gas count is unchanged after a limited live run.

---

### T-02 — parcel_id type mismatch across eight counties

**Priority:** Critical — silent mass duplication.

**Issue.** ThermalLoads stores `parcel_id` as `int`/`Int64` while ElectricalDB stores `str`:
Belmont, Coshocton, Guernsey, Harrison, Holmes, Lawrence, Morgan, Muskingum — **66,285 documents**.
Belmont, Holmes and Muskingum mix `int` and `Int64` *within one collection*. Cuyahoga carries 1,022
`int` on both sides. Audit total across all nine: **67,307 non-string**.

`get_missing_parcels()` compares raw values with no normalization, so all eight counties report
**100% missing** and a run inserts a complete duplicate set.

**Checkpoint:** `cp02-pre-typenorm` (ThermalLoads).

**Build.** `scripts/normalize_thermal_parcel_id_types_tool.py`
- `--dry-run` default; `--county`; `--execute` to write
- `$toString` every non-string `parcel_id`, preserving leading-zero semantics
- report per county: examined, converted, already-string, collisions-created
- **collision guard:** if two docs normalize to the same string, report and skip — do not merge here,
  that is T-03's job

**Test.** `tests/test_parcel_id_normalization.py`
- `int` 2401889000 → `"2401889000"`
- `Int64` same
- existing `str` untouched
- a value with a leading zero survives the round trip
- collision detection fires on a seeded duplicate

**Dry run.**
```bash
python scripts/normalize_thermal_parcel_id_types_tool.py --county Morgan --dry-run   # smallest: 1,351 docs
python scripts/normalize_thermal_parcel_id_types_tool.py --dry-run                   # all nine
```
Expect 67,307 conversions planned, zero writes.

**Execute.** Smallest first, verifying between each: Morgan (1,351) → Holmes (2,847) → Harrison (3,007)
→ Guernsey (7,177) → Coshocton (7,421) → Belmont (11,932) → Lawrence (12,776) → Muskingum (19,774) → Cuyahoga (1,022).

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check types
```
`thermal_non_string` must be **0** and `mismatch` False for every county.
```bash
python scripts/audit_thermal_load_coverage_tool.py --check coverage
```
The eight counties must now read **0 missing** — they currently read 0 only because the audit
normalizes; after this task the raw data agrees with the audit.

**Rollback.** `restore cp02-pre-typenorm --all --yes`

**Done when:** `types` shows zero non-string, and `slopes` still totals 126,987 real gas slopes.

---

### T-03 — No unique constraint; 875 duplicates already present

**Priority:** Critical. **Depends on:** T-02 (normalize before indexing).

**Issue.** The tool only calls `insert_one()`. No ThermalLoads collection has a unique index on
`parcel_id` — present indexes are `_id_` and `parcel_key_1`. **875 duplicate `parcel_id`s already sit
in `CuyahogaThermalLoads`**, and downstream percentile ranking double-counts them.

**Checkpoint:** `cp03-pre-dedupe` (ThermalLoads).

**Build.** `scripts/dedupe_thermal_loads_tool.py`
- `--dry-run` default; `--county`; `--execute`
- keep rule: newest `calculated_at`; tie-break highest `kwh_hl_r2`; then longest `kwh_hl_cl_loads`
- **never** drop a doc carrying real gas slopes in favour of one that does not — cross-check T-01
- write the losers to `exports/` as JSON before deleting

Then create the unique index and convert the write path to `update_one(..., upsert=True)`.

**Test.** `tests/test_thermal_dedupe.py`
- newest `calculated_at` wins
- missing `calculated_at` falls through to r²
- a doc with real gas slopes is never dropped for one with `-1`
- unique index creation fails loudly while duplicates remain

**Dry run.**
```bash
python scripts/dedupe_thermal_loads_tool.py --county Cuyahoga --dry-run
```
Expect exactly **875** removals planned.

**Execute.**
```bash
python scripts/dedupe_thermal_loads_tool.py --county Cuyahoga --execute
```
Then the unique index across all 25 collections.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check duplicates
```
`thermal_excess` must be **0** everywhere. Confirm the index exists and is `unique: true`.

**Rollback.** `restore cp03-pre-dedupe --collection CuyahogaThermalLoads`

**Done when:** zero thermal duplicates, unique index in place on all 25, upsert path live, gas count still 126,987.

---

### T-04 — Wrong join key produces 1,622 phantom gaps

**Priority:** Critical. Code-only, no migration.

**Issue.** The tool joins on `parcel_id`, which is unindexed everywhere. `parcel_key` is the
normalized, indexed field and exists on 21 of 25 county pairs. Joining on `parcel_id` falsely reports
missing: **Fayette 1,127, Huron 257, Hancock 237, Cuyahoga 1 = 1,622 phantoms**. Fayette's identifiers
differ only by zero-padding (`01001600000101` vs `8000900364800`). Running as-is inserts 1,622
duplicates for parcels that already have slopes.

**Checkpoint:** none — no writes.

**Build.** In `get_missing_parcels()`, join on `parcel_key` when both sides have it; fall back to
normalized `parcel_id` for Montgomery, Scioto, Hardin and Ross. Log which key was used per county.

**Test.** `tests/test_thermal_join_key.py`
- county with `parcel_key` on both sides → key join, Fayette returns 0 missing
- county without → `parcel_id` fallback, logged
- normalization applied on both paths (guards against a T-02 regression)

**Dry run.**
```bash
python scripts/calculate_missing_thermal_loads_tool.py --county Fayette --dry-run --verbose
```
Expect **0 missing**, not 1,127.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check joinkey
```
`phantom` must total **1,622** before the fix and the tool must agree with `missing_by_parcel_key`
after it.

**Done when:** the tool's missing count equals the audit's `best` column for all 25 counties.

---

### T-05 — parcel_id unindexed; every batch is a collection scan

**Priority:** High — performance.

**Issue.** `get_electrical_data()` queries `{'parcel_id': {'$in': [...1000]}}`. No `parcel_id` index
exists on any of the 113 collections. Montgomery, Scioto, Hardin and Ross ElectricalDB have only
`_id_`. Montgomery's 31,107 missing parcels resolve to 32 full scans of 339,334 documents.

**Checkpoint:** `cp04-pre-indexes` (ThermalLoads) — index builds are additive, but cheap insurance.

**Build.** `scripts/create_thermal_pipeline_indexes_tool.py`
- `--dry-run` default; report which indexes exist and which would be created
- `{parcel_id: 1}` on the 88 ElectricalDB and 25 ThermalLoads (unique on ThermalLoads per T-03)
- `background=True`; report build time per collection

**Dry run.** Expect a list of exactly the missing indexes, no `createIndex` issued.

**Execute.** Smallest collections first. Monitor with `db.currentOp()` on Franklin, Cuyahoga,
Montgomery (the 300k+ collections).

**Verify.** `explain()` on the `$in` query shows `IXSCAN`, not `COLLSCAN`. Time a Montgomery dry run
before and after — record both numbers.

**Rollback.** `dropIndex('parcel_id_1')`. Cheap and safe.

**Done when:** every collection has the index and the Montgomery dry run shows a measured speedup.

---

### T-06 — Multi-meter parcels silently dropped

**Priority:** High — silent wrong answers.

**Issue.** `get_electrical_data()` assigns `data[parcel_id] = time_series` inside the cursor loop, so
the last document wins. **16,419 excess eligible documents share a `parcel_id`** across 19 counties —
Holmes 5,437, Lawrence 1,773, Coshocton 1,568, Belmont 1,542, Harrison 1,027. These are multi-meter
parcels; every meter but one is discarded without a warning and the regression runs on partial
household load.

**Checkpoint:** none for the analysis; the decision may trigger a recompute later.

**Build — analysis first, this one is a real decision.** Before changing behaviour, characterise the
collisions: are they concurrent meters on one property (sum them), the same meter re-delivered
(dedupe), or distinct units at one parcel (keep separate)? Sample Holmes, which has 5,437 excess
across only 434 ids — roughly 13 documents per id, which does not look like simple duplication.

Then implement the chosen rule and log collisions per run.

**Test.** `tests/test_multimeter_aggregation.py`
- two meters with overlapping dates aggregate per the chosen rule
- identical re-delivered series dedupes rather than doubling
- collision count is reported, never silent

**Dry run.**
```bash
python scripts/calculate_missing_thermal_loads_tool.py --county Holmes --limit 50 --dry-run --verbose
```
Expect a collision count in the output.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check duplicates
```
`electrical_excess` totals **16,419**. Confirm the tool now accounts for every one.

**Done when:** the rule is documented in `.claude_docs/`, tests pass, and no collision is silent.

---

## Sequencing change — T-14 moves before T-07 (decided 2026-09-21)

T-14 was originally deferred as a separate project to run after everything else. Measurement
during T-00 changed that call.

**Why it moves earlier.** New parcel links are *additive*: they enlarge the population of
computable parcels without invalidating anything already computed. T-00 is county-keyed, so
weather is unaffected. T-01/T-02/T-03/T-04/T-05/T-06/T-10/T-12 are code and integrity fixes on
existing data. T-09 refreshes existing slopes. **Only T-07 is affected, and only by having more
to do.** So the cost of leaving T-14 last is not rework — it is running the compute twice.

**Why it must not move earlier than P0.** Landing T-14 first pushes a large influx through a
pipeline that still overwrites 126,987 gas regressions with `-1`, has no unique index so
duplicates compound, keeps one meter per parcel, writes `0.0` on regression failure and — before
T-00 — applied Columbus degree-hours to Cleveland. That multiplies the damage by the size of the
influx. P0 is fixed-cost; T-07 scales with population. Cheap work first, expensive work last and
once.

**Revised order:** P0 (T-00 → T-01, T-12, T-04, T-06, T-02, T-03, T-05) → T-10, T-08 →
**T-14 (25-county scope only)** → T-07 once → T-09.

**Also note:** T-06's collision rule should be settled before T-14 lands, since address matching
will *increase* multi-meter collisions — characterising them on a population about to change
wastes the analysis.

---

## Phase P1 — Compute the genuine gap

### T-07 — 60,733 parcels have no thermal record

**Priority:** High. **Depends on:** T-00 (weather), T-01 → T-06, T-10, T-08, and — per the
sequencing change above — **T-14a**, so the compute runs once over the full population
(~60,733 currently linked plus ~99,000 recoverable) rather than twice.

| County | Missing | Naive (`parcel_id`) |
|---|---:|---:|
| Montgomery | 31,107 | 31,107 |
| Franklin | 17,671 | 17,671 |
| Cuyahoga | 10,529 | 10,530 |
| Ottawa | 782 | 782 |
| Hancock | 361 | 598 |
| Athens | 283 | 283 |
| **Total** | **60,733** | **62,355** |

**Checkpoint:** `cp06-pre-compute` (`--full`).

**Dry run — every county before any execute.**
```bash
for C in Athens Hancock Ottawa Cuyahoga Franklin Montgomery; do
  python scripts/calculate_missing_thermal_loads_tool.py --county $C --dry-run --verbose
done
```
The per-county missing count must match the table. A mismatch means a P0 fix regressed — stop.

**Execute.** Ascending order so failures are cheap: Athens (283) → Hancock (361) → Ottawa (782) →
Cuyahoga (10,529) → Franklin (17,671) → Montgomery (31,107).

Run a `--limit 100` execute on Athens first and inspect the written documents by hand before
committing to the full county.

**Verify after each county.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check coverage --county <Name>
python scripts/audit_thermal_load_coverage_tool.py --check slopes --county <Name>
```
- `best` (missing) → 0
- `exactly_zero` did not jump — a spike means T-12's silent-zero defect is manufacturing junk
- Cuyahoga's `real_gas_slopes` still 126,987

**Rollback.** `restore cp06-pre-compute` — full archive; restore only the affected collection.

**Done when:** all six counties read 0 missing and no new zero-slope population appeared.

---

### T-08 — Montgomery carries no parcel_key

**Priority:** High. Montgomery is the largest single block (31,107) and cannot use the T-04 indexed join.

**Issue.** Montgomery, Scioto, Hardin and Ross have no `parcel_key` on either side.

**Checkpoint:** `cp05-pre-parcelkey` (`--full` — this writes to ElectricalDB).

**Build.** `scripts/backfill_parcel_key_tool.py` — derive `parcel_key` using the identical
normalization the other 21 counties use. Read that normalization out of the existing data first;
do not invent one. Compare a sample of derived keys against a county that already has both fields.

**Test.** `tests/test_parcel_key_backfill.py`
- derived key matches the existing convention on a county that has both
- idempotent: a second run changes nothing
- collisions reported, never silently merged

**Dry run.** Report derived keys for 20 Montgomery parcels; eyeball against Franklin's convention.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check joinkey --county Montgomery
```
`has_parcel_key` flips to True and `missing_by_parcel_key` appears.

**Rollback.** `restore cp05-pre-parcelkey`.

**Done when:** all four counties have `parcel_key` and the join key check passes.

---

## Phase P2 — Refresh stale slopes

### T-09 — 646,375 parcels have slopes older than their data

**Priority:** High — the largest correctness population, ten times the missing set.
**Depends on:** T-00, T-03 (upsert), T-10 (provenance).

**Issue.** Parcel-matched electrical documents stamped `last_utility_ingest: 'aug2026'` gained billing
periods after their slopes were computed — Franklin 246,138, Cuyahoga 172,614, Montgomery 78,690.
Every one of those regressions ran against a truncated series, and percentile ranking and campaign
targeting are built on the stale coefficients.

**Checkpoint:** `cp08-pre-refresh` (`--full`).

**Build.** Add `--refresh-stale` to the calculation tool: select where the electrical
`last_utility_ingest` is newer than the thermal `input_delivery` watermark from T-10. Upsert, never
insert. Preserve gas per T-01.

**Test.** `tests/test_thermal_refresh.py`
- a parcel with a newer delivery is selected; one already current is not
- refresh updates in place — document count does not change
- `input_delivery` advances on write
- gas fields survive

**Dry run.**
```bash
python scripts/calculate_missing_thermal_loads_tool.py --county Ottawa --refresh-stale --dry-run --verbose
```
Start with Ottawa (8,564 aug2026 docs), not Franklin.

**Execute.** Ascending by volume. After each county, confirm the **document count is unchanged** —
a rise means the upsert is inserting and T-03 regressed. Stop immediately if so.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check staleness --county <Name>
python scripts/audit_thermal_load_coverage_tool.py --check duplicates --county <Name>
```
Spot-check ten parcels: the new slope should differ from the old, and r² should not collapse.
A large r² drop means the extra billing periods are being misaligned with weather — investigate
before continuing.

**Rollback.** `restore cp08-pre-refresh`.

**Done when:** every county's stale population is zero, counts unchanged, r² distribution sane.

---

### T-10 — 749,785 thermal docs carry no provenance

**Priority:** High — gates T-09.

**Issue.** Only `FranklinThermalLoads` has `calculated_at`: 44,851 documents, every one stamped
`2026-01-19`. The other 24 counties have none, so fresh and stale are indistinguishable and every
refresh must be a full recompute.

**Checkpoint:** `cp07-pre-provenance` (ThermalLoads).

**Build.** `scripts/backfill_thermal_provenance_tool.py` — add `calculated_at` (null where genuinely
unknown, **not** a fabricated date), `calculation_source`, and a new `input_delivery` watermark
recording which delivery the slopes were computed from. Where unknowable, write
`input_delivery: 'unknown'` — that is honest and still actionable: unknown sorts as stale.

Make the calculation tool always write all three going forward.

**Test.** `tests/test_thermal_provenance.py`
- backfill is idempotent
- existing Franklin `2026-01-19` stamps are not overwritten
- unknown provenance is recorded as unknown, never invented
- new writes carry all three fields

**Dry run.** Per-county counts of documents that would gain each field.

**Verify.**
```bash
python scripts/audit_thermal_load_coverage_tool.py --check staleness
```
`without_provenance` → 0 across all 25.

**Rollback.** `restore cp07-pre-provenance --all --yes`

**Done when:** every thermal document has all three fields and the tool writes them on every path.

---

## Phase P3 — Quality and defects

### T-11 — 22,430 records with null or zero heating slope

**Priority:** Medium. **Checkpoint:** `cp09-pre-quality` (ThermalLoads).

**Issue.** Audit totals: **16,279 null/absent** and **6,151 exactly zero**. Cuyahoga holds 17,524 —
15,954 `null` on gas-only parcels (legitimate) and 1,570 exactly `0.0` with `kwh_hl_cl_loads` full of
`{'kwh': 0, 'date': 'NaT'}` (corrupt). Franklin adds 2,157.

**Build.** Classify before touching anything. Gas-only null is correct and should be *labelled*, not
recomputed. `0.0` against `NaT` dates is corrupt input — recompute if the electrical series supports
it, flag if not.

**Verify.** `--check slopes`. The null population should shrink only by what was genuinely
recomputable; the `NaT` population should reach zero.

**Done when:** every remaining null/zero carries an explicit reason code.

---

### T-12 — Regression failure writes 0.0 instead of an error

**Priority:** Medium. Code-only, no migration.

**Issue.** Both `except` branches in `calculate_thermal_loads_for_parcel()` set slope, intercept and
r² to `0.0`. A failed regression becomes indistinguishable from a genuine zero slope — this is how a
share of T-11 was produced.

**Build.** Write `None` plus a `calculation_error` reason. Never coerce a failure into a number.

**Test.** `tests/test_thermal_regression_failure.py` — a forced failure yields `None` and a reason;
a genuine zero-slope parcel still yields `0.0` and is distinguishable.

**Done when:** tests pass. Land this **before** T-07 and T-09 if possible — it prevents both from
manufacturing new T-11 records.

---

### T-13 — 45,781 docs below the three-period minimum

**Priority:** Low.

**Issue.** Fewer than three billing periods, so `calculate_thermal_loads_for_parcel()` returns empty.
Permanently ineligible until more deliveries arrive, yet indistinguishable from unprocessed parcels.

**Build.** Mark `ineligible: insufficient_periods` with the period count, so audits stop re-counting
them as work.

**Verify.** `--check coverage` — `below_min_periods` totals 45,781 and every one is now labelled.

---

## Phase P4 — Separate project

### T-14 — 3,239,625 electrical docs have no parcel_id

**Priority:** Low urgency, highest ceiling. **This is not a fix to the thermal tool.**

2,466,129 documents across the 63 counties with no ThermalLoads collection, plus 773,496 inside the
25 that have one. All keyed by utility surrogate — `AES::Lisa Landis`,
`DUKE::45206|2946 CLEINVIEW AVE`, `FE:OE:S335963995`. They arrived with the AEP/AES/Duke/FirstEnergy
pre-enrollment ingest in commit `fbed58c` and were never address-matched.

**Scope correction (2026-09-21).** Only **25 of the 88** ElectricalDB counties have a
`*CountyResidential` parcel table — and they are exactly the 25 that already have ThermalLoads.
The other **63 counties have no parcel table at all**, so their 2,466,129 records cannot be
matched by any amount of matcher work. Butler, Hamilton, Stark and Summit all have electrical
data and nothing to match it against.

This splits T-14 into two distinct pieces:

- **T-14a — address matching, 25 counties.** 792,059 unlinked records against tables that exist.
  A 3,000-record Montgomery sample against `MontgomeryCountyResidential` found **13.3% whose
  exact address is already in the parcel table** (375/400 also agreeing on zip, of which 154 map
  to more than one parcel and need a tie-break), 69.6% where the street exists but that house
  number does not, and 17.1% where the street is absent. Formatting is *not* the obstacle —
  `1935 OAKDALE AVE` is written exactly like `1942 OAKDALE AVE`, which is present. Extrapolated,
  roughly **99,000 recoverable parcels**, of which ~7.4% need nothing but an exact join the
  current pipeline is not doing. Caveat: one county, 3,000 records in natural rather than random
  order. Use `src/tools/residence_matcher.py`.
- **T-14b — parcel data acquisition, 63 counties.** Not a matching problem. Nothing is actionable
  until parcel tables are obtained. Keep out of this runbook.

Note `MontgomeryCountyResidential` holds 212,544 documents but only 160,280 distinct addresses,
so the parcel side has duplication of its own.

---

## Appendix — verified command reference

```bash
cd /home/yersinia/devel/recover/octopus
source venv/bin/activate

# Audit (read-only, safe any time)
python scripts/audit_thermal_load_coverage_tool.py --check all
python scripts/audit_thermal_load_coverage_tool.py --check coverage --county Montgomery
python scripts/audit_thermal_load_coverage_tool.py --check types
python scripts/audit_thermal_load_coverage_tool.py --check joinkey
python scripts/audit_thermal_load_coverage_tool.py --check staleness
python scripts/audit_thermal_load_coverage_tool.py --check slopes
python scripts/audit_thermal_load_coverage_tool.py --check duplicates
python scripts/audit_thermal_load_coverage_tool.py --check all --json exports/thermal_audit.json

# Backup
python src/scripts/backup_mongo_collections_tool.py create <label> --suffix ThermalLoads
python src/scripts/backup_mongo_collections_tool.py create <label> --full
python src/scripts/backup_mongo_collections_tool.py list
python src/scripts/backup_mongo_collections_tool.py verify <label>
python src/scripts/backup_mongo_collections_tool.py restore <label> --collection <Name>
python src/scripts/backup_mongo_collections_tool.py restore <label> --all --yes

# Tests  (addopts override required - see standing rule 7)
python -m pytest tests/ -q -o addopts=""
python -m pytest tests/test_thermal_gas_preservation.py -v -o addopts=""
```

### Baseline numbers to check against (measured 2026-09-16, pre-remediation)

| Check | Expected |
|---|---:|
| `coverage` missing, best key | 60,733 |
| `coverage` missing, naive parcel_id | 62,355 |
| `joinkey` phantom | 1,622 |
| `types` thermal_non_string | 67,307 |
| `duplicates` thermal_excess | 875 |
| `duplicates` electrical_excess | 16,419 |
| `slopes` null_or_absent | 16,279 |
| `slopes` exactly_zero | 6,151 |
| `slopes` real_gas_slopes | 126,987 |
| `staleness` without_provenance | 749,785 |
| aug2026 parcel-matched docs | 646,375 |

Any deviation from these on a fresh audit means something changed since 2026-09-16 — reconcile
before proceeding.
