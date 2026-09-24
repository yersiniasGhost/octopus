# Thermal Slope Remediation — kickoff prompt for T-14a (supersedes 20260921_2233)

Paste the block below after clearing context.

---

We are resuming a thermal-slope remediation on the octopus project, branch
`feature/campaign-weather`. I have cleared context, so read these first:

    .claude_docs/20260924_0926_thermal_remediation_KICKOFF_T14a.md   <- status, read first
    .claude_docs/20260916_1300_thermal_slope_remediation_runbook.md  <- execution runbook

**T-02, T-03, T-04 and T-15 are all complete and committed. The database is in a
verified good state.** Today I want **T-14a** (address matching, 25 counties,
~99,000 recoverable parcels) and nothing else.

Ground rules:
- `source venv/bin/activate` before any Python.
- `pytest` needs `-o addopts=""` (pytest-cov is not installed).
- Verify with `scripts/audit_thermal_load_coverage_tool.py`, never an ad-hoc query.
- **Read the runbook section for the task you are about to run, AND the sections of
  every task it touches.** Not just its own stated blockers. See "How the last two
  bugs happened" — both came from trusting a task's blocker list.
- Take a checkpoint before any write, and show me the output of each write step
  before moving to the next.
- Do NOT start another task. If you find a problem belonging elsewhere, write it
  down and tell me — do not fix it.
- **Do not create thermal records as a side effect.** Creating the ~60,733 absent
  parcels is T-07 and has not been authorized.

Start by confirming the state matches "Where things stand" below.

---

## Where things stand (2026-09-24 09:26)

**Branch** `feature/campaign-weather`, HEAD `1315954`, 18 commits ahead of `master`.
Suite **282 passing** (`python -m pytest tests/ -q -o addopts=""`).

Four remediation tasks closed: **T-02** (parcel_id types), **T-03** (dedupe + unique
index), **T-04** (join key), **T-15** (single joint model, migrated).

### Verified state, measured 2026-09-23 after `1315954`

| Check | Value |
|---|---:|
| all 25 collections, documents | **794,636** |
| carry `kwh_model` | 774,374 |
| `types` thermal_non_string / mismatch | 0 / 0 |
| `duplicates` thermal_excess | 0 |
| `duplicates` electrical_excess | 16,419 |
| `coverage` missing, best key | 60,733 |
| `coverage` missing, naive parcel_id | 62,355 |
| `joinkey` phantom | 1,622 |
| `staleness` with_calculated_at | 774,374 |
| `staleness` without_provenance | 20,262 |
| `slopes` null_or_absent | 14,698 |
| `slopes` exactly_zero | 2,331 |
| `slopes` real_gas_slopes | **126,438** |
| participants carrying `thermal.*` | 3,265 (all `kwh_model`, zero legacy) |
| unique `parcel_id_1` index | `unique: true` on all 25 |

Any deviation means something changed outside this work — reconcile before proceeding.

**Un-migrated 20,262 is expected and fully accounted for:** 16,580 documents have no
electrical counterpart at all, 3,682 cannot be fitted. They keep their legacy fields
because nothing was written to them. Not a regression.

**`joinkey` phantom 1,622 is expected.** That column measures a property of the *data*
(two identifier spellings for one parcel), not of the tool. T-04 stopped the tool
acting on them. Reconciling the identifiers themselves has no task yet.

### Uncommitted, none of it mine — do not stage

`.gitignore`, `scripts/enrich_participants_franklin_demographics_tool.py`,
`scripts/analyze_aceee_campaign_association_tool.py`,
`scripts/append_dropped_rows_text7x_8x_tool.py`,
`scripts/fill_text7x_8x_demographics_from_county_tool.py`,
`.claude_docs/20260916_1739_storage_reclamation_runbook.md`,
`.claude_docs/20260921_2233_thermal_remediation_KICKOFF_T03_steps4-8.md` (last kickoff,
still untracked — ask me whether to commit it).

**Staging note.** `.claude_docs/script_descriptions.md` carries ~90 lines of unrelated
edits alongside the entries this work added. Stage only your own: build the blob from
`git show HEAD:<file>` plus your entry and `git update-index --cacheinfo`. `git add -p`
is unavailable — the harness blocks interactive flags.

### Checkpoints on disk (`~/backups/octopus-thermal`)

`cp00-baseline` (full, 1,003 MB) · `cp00-thermal` · `cp02-pre-typenorm` ·
`cp03-pre-dedupe` · `cp10-pre-singlemodel` (25 colls, 134.4 MB — the most recent
thermal rollback point).

Rollback: `python src/scripts/backup_mongo_collections_tool.py restore <label> --all --yes`

---

## T-14a — address matching, 25 counties

Runbook section: **T-14**, at the end of the file. T-14 was split on 2026-09-21:

- **T-14a** (this task): 792,059 unlinked electrical records in the 25 counties that
  *have* a `*CountyResidential` parcel table.
- **T-14b**: 2,466,129 records across the 63 counties with **no parcel table at all**.
  Not a matching problem, not actionable, keep out of this runbook.

**The measurement that sized it.** A 3,000-record Montgomery sample against
`MontgomeryCountyResidential`: **13.3%** whose exact address is already in the parcel
table (375/400 also agreeing on zip, of which **154 map to more than one parcel** and
need a tie-break), 69.6% where the street exists but that house number does not, 17.1%
where the street is absent. Formatting is **not** the obstacle — `1935 OAKDALE AVE` is
written exactly like `1942 OAKDALE AVE`, which is present. Extrapolated: roughly
**99,000 recoverable parcels**, ~7.4% of which need nothing but an exact join the
current pipeline is not doing.

**Caveat on that number:** one county, 3,000 records, taken in natural rather than
random order. Re-measure before trusting it.

Use `src/tools/residence_matcher.py`. Note `MontgomeryCountyResidential` holds 212,544
documents but only 160,280 distinct addresses, so the parcel side has duplication of
its own — the 154 multi-parcel matches are that duplication surfacing.

**Unlinked records are excluded, never deleted.** They carry real addresses and real
usage. `get_missing_parcels` and `get_target_parcels` both filter them out through
`_linked_electrical_rows`.

---

## How the last two bugs happened — read this before running anything

Both were mine, both were quiet, and both passed every check the runbook specifies.

**1. 1,622 phantom duplicates.** I ran T-15's `--recompute-all` without reading T-04.
T-15's blocker list names three prerequisites and I treated it as complete; T-04's own
section says plainly *"Running as-is inserts 1,622 duplicates for parcels that already
have slopes."* The warning was in the runbook, under a different task.
→ **Read the sections of every task your task touches, not just its stated blockers.**

**2. 1,127 Fayette parcels silently skipped.** My T-04 fix returned targets in the
*thermal* spelling to a lookup that queries the *electrical* collection. Those parcels
found no billing data and `main()`'s guard counted the miss as "insufficient data".
Document counts were clean, failed writes zero, exit code zero.
→ **A parcel needs both spellings for different purposes:** the electrical one to find
billing data, the thermal one as the upsert filter. `get_thermal_write_map()` pairs them.

**What actually caught both:** the number 1,127 recurring in a column nobody was
watching — first as "phantom", then "un-migrated", then "insufficient data". A metric
matching a known defect's cardinality is evidence, not coincidence.

**What did NOT catch them:** I checked document counts at the 3-county mark, saw
794,636 holding steady, and reported it as evidence of health. The only counties
processed by then were small ones with no join-key defect. A tripwire checked against a
population that cannot exhibit the defect is not a tripwire.

---

## Open items, none blocking T-14a

1. **`CuyahogaElectricalDB` holds 1,022 `int` `parcel_id`s** (`str 255,975 · int 1,022`).
   T-02's scope was ThermalLoads only and the audit's `mismatch` flag reads the thermal
   side alone, so it shows clean. Belongs to no task; needs one. **Relevant to T-14a** —
   it is the same identifier-hygiene family.
2. **`joinkey` phantom 1,622 is a data property, not a tool defect.** Reconciling the two
   identifier spellings has no task.
3. **Hardin, Montgomery, Ross and Scioto have no `parcel_key`** — only `_id_` and the
   T-03 `parcel_id_1`. The dual-index join handles this, but note Montgomery is both the
   T-14a sample county and a key-less one.
4. **331 pre-2015 electrical readings across 44 parcels** take a silent `0.0` heating
   load; weather starts 2015-01-01. 0.001% of 30,822,426 readings. Documented under T-00.
5. **`below_min_periods` 23,146 vs T-13's 45,781** — different populations, never
   reconciled. Reconcile before starting T-13.
6. **The dedupe tool's export and cross-check run AFTER the delete** in `--execute` mode,
   so the T-02 cross-check is a post-hoc confirmation rather than a gate. Run `--dry-run`
   first, which validates both with zero writes.
7. **The published artifact is partly wrong.**
   https://claude.ai/code/artifact/ef09ff18-b052-428a-871c-4c714f6c24ed
   It attributes the 72.8% negative heating slopes entirely to the omitted-cooling
   mechanism; the larger cause was gap rows pairing one month's kWh with a multi-year
   weather total. Private and unshared. Ask before republishing.

---

## Things that will bite you

- `pytest` needs `-o addopts=""`.
- `mongodump` has no `--nsInclude`; the backup tool enumerates collections deliberately.
- `pgrep -f "<pattern>"` matches your own shell. Use `ps -eo pid,args | grep -E "..."`.
- The harness blocks chained `sleep`. For a long job use `run_in_background` plus an
  `until <condition>; do sleep N; done` watcher, not a per-event monitor — one event per
  county costs a conversation turn each.
- The audit **normalizes on read**. Its `staleness.thermal_docs` counts *distinct
  normalized parcels*, not documents, so it read 260,064 for Cuyahoga while the raw
  count was still 260,939. It measures what the data *means*; some defects live in what
  the production code *compares*.
- `slopes.null_or_absent` and `slopes.exactly_zero` count **`kwh_hl_slope` (electric)**,
  not gas, via raw `count_documents`. Only `real_gas_slopes` is gas. The column adjacency
  invites the misreading.
- Programmatic edits that replace a span "up to the next top-level def" will silently
  swallow whatever sits between. One such edit deleted `get_missing_parcels`,
  `get_target_parcels` and `get_electrical_data`; the targeted test run was 12/12 green.
  **Run the full suite after any structural edit.**
- Re-running the migration is idempotent and safe (`update_one` upsert onto a unique
  index), and now costs ~1.6h rather than ~66h.

---

## Recommended order after T-14a

**T-07** (create the 60,733 absent thermal records — the tool's default mode is now
scoped to exactly this and will not overlap the recompute path) → **T-05/T-06** →
**T-13** (reconcile open item 5 first).

Gas re-add, when it comes: start from `exports/t03_dedupe_losers_*.json` and the 270
gas-only parcels it identifies.
