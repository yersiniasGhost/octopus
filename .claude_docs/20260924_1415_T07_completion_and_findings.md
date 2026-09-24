# T-07 — executed 2026-09-24. Completion record and findings

Companion to `.claude_docs/20260916_1300_thermal_slope_remediation_runbook.md` (T-07).
Run ahead of T-14a at the user's direction; see "Sequencing" below for why that was sound.

## Result

**59,550 thermal records created** across the six counties that had gaps.
All 25 collections: **794,636 -> 854,186** documents.
`coverage best` missing: **60,733 -> 1,183** (98.1% of the gap closed).
Suite **293 passing** (`python -m pytest tests/ -q -o addopts=""`).

| County | Targets | Written | Insufficient | Multi-meter held back | `best` before | after |
|---|---:|---:|---:|---:|---:|---:|
| Athens | 293 | 279 | 14 | 0 | 283 | 4 |
| Hancock | 369 | 323 | 10 | 36 | 361 | 38 |
| Ottawa | 793 | 766 | 27 | 0 | 782 | 16 |
| Cuyahoga | 10,770 | 10,361 | 409 | 0 | 10,529 | 168 |
| Franklin | 18,641 | 17,163 | 1,477 | 1 | 17,671 | 508 |
| Montgomery | 31,846 | 30,658 | 1,188 | 0 | 31,107 | 449 |
| **Total** | **62,712** | **59,550** | **3,125** | **37** | **60,733** | **1,183** |

Every county's write count matched its dry-run prediction exactly, and every
post-county document total matched the predicted total. The execute driver gated
on both and would have halted on either.

**T-07 is NOT "0 missing" as the runbook's done-criterion asks, and cannot be.**
The 1,183 residual is 37 parcels deliberately held back pending T-06 plus 1,146
the audit counts eligible (>=3 periods) that the regression cannot fit. Closing
those is not a compute problem.

### Integrity checks, all six counties

| Check | Before | After | Note |
|---|---:|---:|---|
| documents, all 25 | 794,636 | **854,186** | +59,550, reconciles exactly |
| `real_gas_slopes` | 126,438 | **126,438** | unchanged across 10,361 Cuyahoga inserts — T-01's `$setOnInsert` held |
| `null_or_absent` | 14,698 | **14,698** | all pre-existing Cuyahoga; zero new nulls |
| `calculation_error` on new docs | — | **0** | no regression failed |
| `exactly_zero` | 2,331 | **2,458** | +127, and exactly 127 new docs carry `kwh_hl_slope == 0` |
| `thermal_excess` duplicates | 0 | **0** | unique index held across 59,550 upserts |
| `types` non-string / mismatch | 0 / 0 | **0 / 0** | |
| `electrical_excess` | 16,419 | 16,419 | untouched — T-06 not attempted |

The +127 exactly-zero is **0.21%** of the new records against a pre-existing rate
of 0.29%: the new cohort is slightly *cleaner* on this measure, so the runbook's
"`exactly_zero` did not jump" criterion is met and reconciled to the document.

## Two defects found during the run, both fixed

### 1. Created documents carried no `parcel_key`

`build_thermal_document` never wrote it. **Unreachable until now:** T-15's
recompute upserted onto documents that already had the field, so only a path that
*creates* documents could expose it. T-07 is that path.

Caught by the audit's `best` column not moving: the first Athens execute wrote 279
records and `missing_by_parcel_id` fell 283 -> 4 while `missing_by_parcel_key` and
`best` stayed frozen at **283**, because the audit joins on `parcel_key` where the
county has one.

**A keyless document is worse than an absent one.** An absent parcel is *reported*
missing; a keyless document is counted by `count_documents` and invisible to every
`parcel_key` join. The run would have finished with 59,550 records written, a clean
exit code, and the coverage number barely moving.

Fix: `get_electrical_data` carries the key out of the scan it already performs (no
second pass); `write_thermal_loads` and `build_thermal_document` thread it through;
it is **omitted rather than written null** where the county has none, since a null
key is indexed and joins against other nulls. The 279 bad records were exported to
`exports/t07_athens_rollback_20260924.json`, deleted, and rewritten.
Tests: `tests/test_thermal_parcel_key_write.py` (5).

**Montgomery's 30,658 new documents correctly have no `parcel_key`** — its
electrical side has none either (0 documents carry one). That is T-08's population,
and the T-04 dual-index join resolves it on normalized `parcel_id`.

### 2. Multi-meter parcels would have been fitted on one arbitrary meter

`get_electrical_data` assigned `data[parcel_id] = time_series` inside the cursor
loop: last document wins, silently (T-06, 16,419 excess documents across 19
counties). On a recompute that corrupts an existing slope; on T-07 it manufactures
a **new** record fitted on partial household load with nothing to say so.

Exposure was measured before deciding, by `scripts/analyze_t07_multimeter_overlap_debug.py`:
**37 of 62,712 targets (0.06%)** — 36 Hancock, 1 Franklin, and none in
Athens/Ottawa/Cuyahoga/Montgomery. The collection-wide 16,419 sits almost entirely
in Holmes, Lawrence, Coshocton, Belmont and Harrison, all of which had **zero**
missing parcels. That measurement is what allowed T-07 to precede T-06.

The 37 are **excluded and reported in their own `Multi-meter (excluded)` bucket**,
never folded into "insufficient data" — a genuine exclusion tallied as something
else is how 1,127 Fayette parcels stayed invisible through a clean run.
Aggregating the meters remains T-06's decision and was not guessed at.
Tests: `tests/test_multimeter_exclusion.py` (6).

## Finding: the new cohort's negative heating slopes

Not a defect. Recorded because it is structural and unfixable by re-running.

| County | New | neg. heating | Existing (`hl+cl`) | neg. heating |
|---|---:|---:|---:|---:|
| Athens | 279 | 26.5% | 6,963 | 15.0% |
| Hancock | 323 | 16.4% | 4,323 | 27.0% |
| Ottawa | 766 | 25.3% | 11,395 | 26.3% |
| Cuyahoga | 10,361 | 19.6% | 243,412 | 19.7% |
| **Franklin** | 17,163 | **43.9%** | 238,377 | **28.9%** |
| Montgomery | 30,658 | 25.3% | 108,726 | 27.2% |
| **Total** | **59,550** | **29.6%** | **613,196** | **24.7%** |

**Mechanism, measured rather than assumed.** These parcels have roughly half the
billing history of the existing population (median 11 periods against 22) because
they only appear in deliveries from 2025-08 onward. Refitting *established* Athens
parcels (21+ periods) on only that recent window moved them from **14.6% -> 22.8%**
negative — so a large part of the gap is a statistical property of fitting 11
periods instead of 24, not anything about these houses. Both cohorts have full
12-month seasonal coverage and comparable consumption (median 782 vs 894 kWh/period),
so seasonal sampling is not the cause.

**Franklin is the outlier worth following up.** It is precisely the county whose
negative-heating rate T-15's joint model drove from 72.8% down to 28.9%; its new
cohort landing at 43.9% suggests the joint fit is less effective on short recent
histories there. Relevant to T-09 (refresh) and T-11 (quality). **Not investigated.**

Downstream: percentile ranking and campaign targeting consume these slopes, and
this cohort is noisier than the population it joins.

## Sequencing: T-07 before T-14a

The runbook's 2026-09-21 decision put T-14a first so "the compute runs once" —
written when compute cost 0.3001 s/parcel, making a duplicate run ~5 hours. After
the degree-hour optimization landed at 0.0074 s/parcel the duplicate run costs
**~8 minutes**. The premise expired; running T-07 first is now the cheaper order.
T-14a's ~99,000 recovered parcels will need a second T-07 pass, at that price.

Dependencies verified individually rather than trusted: T-01 and T-12 are landed in
code (`$setOnInsert` gas sentinels; `calculation_error` instead of `0.0`). T-08 is
moot for T-07 — the T-04 dual join resolved all 108,726 Montgomery records on
normalized `parcel_id`. T-05 is **not** done and did not matter: the `$in` query is
a confirmed `COLLSCAN`, measured at 0.09 s per 1,000-id batch, ~3 seconds for all of
Montgomery.

## Operational gotchas discovered

- **`--full` checkpoints cannot restore a single collection.** `restore
  cp06-pre-compute --collection AthensThermalLoads` fails with `'AthensThermalLoads'
  is not in checkpoint` — the archive registers as one "collection". Granular
  rollback needs a `--suffix` checkpoint. `cp06b-pre-compute-thermal` (25
  collections, 220.5 MB) was taken for this reason and is the current thermal
  rollback point.
- The audit's `exactly_zero` and a Python `== 0.0` filter disagree on Athens (13 vs
  5). Pre-existing, int-vs-float in the raw `count_documents`, same type-comparison
  family as T-02. Belongs to no task.
- `get_target_parcels` returns **more** parcels than the audit calls missing (62,712
  vs 60,733): the audit gates eligibility at >=3 billing periods, the tool does not,
  and the >=2 gate is applied later in `get_electrical_data`. The runbook's "the
  per-county missing count must match the table, a mismatch means a P0 fix regressed
  — stop" will fire spuriously. It is two-stage filtering, not a regression.

## Checkpoints

`cp06-pre-compute` (full, 1,088.9 MB, pre-T-07) and `cp06b-pre-compute-thermal`
(25 collections, 220.5 MB, the granular pre-T-07 thermal state, taken after the
Athens rollback). Earlier: `cp00-baseline`, `cp00-thermal`, `cp02-pre-typenorm`,
`cp03-pre-dedupe`, `cp10-pre-singlemodel`.

## Open items carried forward

1. **T-06 still unfixed**; 37 parcels held back by T-07 await it, and 16,419 excess
   documents across 19 counties still resolve last-wins on any recompute of those
   counties.
2. **Franklin's new cohort at 43.9% negative heating** — see above. No task.
3. **`input_delivery` is still not written.** T-10 specifies three provenance
   fields; the tool writes `calculated_at` and `calculation_source` only. The 59,550
   new documents will need backfilling along with everything else when T-10 lands.
4. T-14a will add ~99,000 parcels needing a second T-07 pass (~8 min).
5. Everything in the T-14a kickoff's open-items list still stands: Cuyahoga
   electrical `int` parcel_ids, joinkey phantom 1,622, `below_min_periods` 23,146 vs
   T-13's 45,781, the dedupe tool's post-hoc cross-check, the partly-wrong artifact.
