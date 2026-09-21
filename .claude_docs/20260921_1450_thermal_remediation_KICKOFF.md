# Thermal Slope Remediation — kickoff prompt (supersedes 20260916_1300)

Paste the block below after clearing context. Replace `<TASK>` with one task id.

---

We are working through a thermal-slope remediation on the octopus project,
branch `feature/campaign-weather`. I have cleared context, so read these first:

    .claude_docs/20260916_1300_thermal_slope_remediation_runbook.md   <- execution runbook, start here
    .claude_docs/20260916_1113_thermal_slope_remediation_todo.md      <- original findings

Today I want to do exactly one task: <TASK>

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

Start by confirming the current state matches the runbook Appendix ("Baseline
numbers to check against"), then tell me your plan for <TASK> before writing
anything.

---

## Where things stand (2026-09-21)

**Branch** `feature/campaign-weather`. Three commits landed, suite **187 passing**
(`python -m pytest tests/ -q -o addopts=""`).

| commit | what |
|---|---|
| `e245414` | Task 0 — backup tooling, checkpoints `cp00-baseline` + `cp00-thermal`, rollback drill proven on MorrowThermalLoads |
| `2cd8e07` | T-00 — per-county weather from Open-Meteo; `/home/warnd/` fallback deleted; null-`parcel_id` crash fixed |
| `4368843` | T-15 — single joint model, billing-period validity, clean-break schema, update-not-insert write path |

**No database writes have been made in any session.** Every task so far has been
code, tests and read-only measurement. The only data written is
`data/weather/*.csv` (gitignored) for six counties.

### Done
- **Task 0** — rollback proven. `cp00-baseline` (full, 1,003 MB) and `cp00-thermal`
  (25 collections, 135 MB) exist under `~/backups/octopus-thermal/`.
- **T-00** — weather follows `--county`, no fallback. Fetched for the six T-07
  counties only: Athens, Hancock, Ottawa, Cuyahoga, Franklin, Montgomery.
- **T-15** — specification chosen on evidence (S1, `kWh ~ heating + cooling`),
  billing-period validity filter (25–40 days), clean-break schema.
- **T-01** resolved incidentally — gas fields moved to `$setOnInsert`.
- **T-12** resolved incidentally — failures write `None` + `calculation_error`.

### Next task options

| Task | Why it's next | Blocks |
|---|---|---|
| **T-02** | Nine counties store `parcel_id` as int/Int64 in ThermalLoads against str in ElectricalDB (67,307 docs). Until fixed, the T-15 migration **inserts duplicates instead of replacing**. | the T-15 migration, T-03 |
| **T-15 migration** | Recompute 794,636 records. Blocked on T-02, weather for 19 counties, and a refresh of 3,265 participant copies. | — |
| **T-00 remainder** | Fetch weather for the other 19 counties: `python scripts/fetch_county_weather_hourly_tool.py --all --execute` (~5–8 min, ~77 MB). | T-09, full T-15 migration |
| **T-03** | Dedupe Cuyahoga's 875 duplicates, add the unique index. Depends on T-02. | — |
| **T-14a** | Address matching, 25 counties, ~99,000 recoverable parcels. Runbook resequences it ahead of T-07. | T-07 |

Recommended order: **T-02 → T-00 remainder → T-15 migration → T-03 → T-14a → T-07.**

### Open items, none blocking

1. **The published artifact is now partly wrong.**
   https://claude.ai/code/artifact/ef09ff18-b052-428a-871c-4c714f6c24ed
   It attributes the 72.8% negative heating slopes entirely to the omitted-cooling
   mechanism. That mechanism is real and the two parcel walk-throughs are correct,
   but the larger cause turned out to be gap rows pairing one month's kWh with a
   multi-year weather total. It is private and unshared. Ask before republishing.
2. **`below_min_periods` 23,146 vs T-13's 45,781** — different populations, never
   reconciled. Reconcile before starting T-13.
3. **Unrelated uncommitted work in the tree**, untouched across all three commits:
   `.gitignore`, `enrich_participants_franklin_demographics_tool.py`, three
   `aceee`/`text7x_8x` scripts and their `script_descriptions.md` entries, and
   `.claude_docs/20260916_1739_storage_reclamation_runbook.md`.
4. **Two metrics that proved unusable** are documented in T-15 so they are not
   repeated: share-of-negative-slopes, and fuel separation against `CuyahogaGasDB`.

### Things that will bite you
- `pytest` needs `-o addopts=""`.
- `mongodump` has no `--nsInclude`; the backup tool enumerates collections deliberately.
- The browse tool blocks `file:` URLs — serve locally over HTTP to preview an artifact.
- `pgrep -f "<pattern>"` matches your own shell when the pattern appears in your
  command line. Use `ps -eo pid,args | grep -E "<pattern>"` instead.
- Electrical fetches for a 900-parcel sample take 5–10 minutes. Background them.
