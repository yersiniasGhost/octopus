# Thermal Slope Remediation TODO

**Scanned:** 2026-09-16 · **Database:** `empower_development` (localhost:27017)
**Scope:** 88 `*ElectricalDB` (4,138,839 docs) · 25 `*ThermalLoads` (794,636 docs) · 1 `*GasDB`
**Subject:** `scripts/calculate_missing_thermal_loads_tool.py`

## Headline numbers

| Measure | Count |
|---|---:|
| Electrical docs scanned | 4,138,839 |
| Parcels ready to compute now | 60,733 |
| Existing slopes now stale (aug2026 data) | 646,375 |
| Electrical docs with no `parcel_id` | 3,239,625 |
| Thermal docs with no provenance stamp | 749,785 |
| Thermal docs with null/zero heating slope | 22,430 |

---

## P0 — Blockers. Do these before any write to `*ThermalLoads`.

### T-01 · Gas regressions destroyed on re-run
- **Issue:** `insert_thermal_loads()` hardcodes `gas_hl_slope: -1`, `gas_cl_slope: -1` (and intercepts/r2).
- **Impact:** 126,987 `CuyahogaThermalLoads` docs hold real gas regressions (e.g. `gas_hl_slope: 0.00177, gas_hl_r2: 0.723`). Any re-run over Cuyahoga overwrites them with `-1`. Irreversible without a restore.
- **Action:** On upsert, use `$setOnInsert` for the gas block so existing gas values survive. Never `-1` over a populated field.
- **Priority:** Critical — data loss.

### T-02 · `parcel_id` type mismatch, 8 counties
- **Issue:** ThermalLoads stores `parcel_id` as `int`/`Int64`; ElectricalDB stores `str`. Belmont, Coshocton, Guernsey, Harrison, Holmes, Lawrence, Morgan, Muskingum = 66,285 docs. Belmont, Holmes and Muskingum mix `int` and `Int64` *within one collection*. Cuyahoga has 1,022 `int` on both sides.
- **Impact:** The tool's set difference (`get_missing_parcels`, line 203) does no normalization, so all 8 counties report **100% missing** and a run inserts a complete duplicate set (~66k docs).
- **Action:** Migration to `$toString` every `parcel_id` in the 8 collections; then a validator or unique index to hold the type.
- **Priority:** Critical — silent mass duplication.

### T-03 · No unique constraint, 875 duplicates already present
- **Issue:** `insert_thermal_loads()` only calls `insert_one()`. No unique index on `parcel_id` in any ThermalLoads collection (indexes are `_id_` and `parcel_key_1` only).
- **Impact:** 875 duplicate `parcel_id`s already in `CuyahogaThermalLoads`. Every future re-run compounds this. Downstream percentile ranking double-counts duplicated parcels.
- **Action:** Dedupe Cuyahoga (keep most recent `calculated_at`, else highest r²), then add `unique: true` index on the normalized `parcel_id`. Convert the write to `update_one(..., upsert=True)`.
- **Depends on:** T-02 (normalize types before the unique index).
- **Priority:** Critical.

### T-04 · Wrong join key — 1,622 phantom "missing" parcels
- **Issue:** The tool joins on `parcel_id`, which is **unindexed everywhere**. `parcel_key` is the normalized, indexed field (`parcel_key_1` exists on 21 of 25 county pairs).
- **Impact:** Joining on `parcel_id` falsely reports missing: Fayette 1,127, Huron 257, Hancock 237, Cuyahoga 1. Running as-is inserts 1,622 duplicate records for parcels that already have slopes. Fayette's IDs differ by zero-padding (`01001600000101` vs `8000900364800`).
- **Action:** Join on `parcel_key` with `parcel_id` fallback for the 4 counties that lack it.
- **Priority:** Critical.

### T-05 · `parcel_id` unindexed — collection scans
- **Issue:** `get_electrical_data()` queries `{'parcel_id': {'$in': [...1000]}}`. No `parcel_id` index exists on any of the 113 collections. Montgomery, Scioto, Hardin and Ross ElectricalDB have **only** `_id_`.
- **Impact:** Full scan per 1,000-parcel batch. Montgomery's 31,107 missing parcels = 32 scans of 339,334 docs.
- **Action:** `createIndex({parcel_id: 1})` across ElectricalDB + ThermalLoads, or adopt `parcel_key` per T-04.
- **Priority:** High — performance, not correctness.

### T-06 · Multi-meter parcels silently dropped
- **Issue:** `get_electrical_data()` assigns `data[parcel_id] = time_series` in a loop — last document wins.
- **Impact:** 16,419 excess eligible electrical docs share a `parcel_id` across 19 counties (Holmes 5,437; Lawrence 1,773; Coshocton 1,568; Belmont 1,542). These are multi-meter/multi-account parcels. All but one meter is discarded with no warning, so the regression runs on partial household load.
- **Action:** Decide the rule — sum concurrent meters, or pick the longest series — then log the collision count per run.
- **Priority:** High — silent wrong answers.

---

## P1 — Compute the genuine gap.

### T-07 · 60,733 parcels have no thermal record
- **Issue:** Eligible parcels (`parcel_id` present, ≥3 billing periods) with no ThermalLoads document, measured on the best available key.

| County | Missing | Naive (`parcel_id`) |
|---|---:|---:|
| Montgomery | 31,107 | 31,107 |
| Franklin | 17,671 | 17,671 |
| Cuyahoga | 10,529 | 10,530 |
| Ottawa | 782 | 782 |
| Hancock | 361 | 598 |
| Athens | 283 | 283 |
| **Total** | **60,733** | **62,355** |

- **Impact:** These parcels are absent from energy-percentile targeting in `generate_campaign_list_by_energy_percentile_tool.py`.
- **Action:** Run the tool per county once T-01…T-06 land.
- **Depends on:** T-01 through T-06.
- **Priority:** High.

### T-08 · Montgomery has no `parcel_key` at all
- **Issue:** Montgomery, Scioto, Hardin and Ross carry no `parcel_key` on either side.
- **Impact:** Montgomery is the single largest missing block (31,107) and cannot use the indexed join or the T-04 fix.
- **Action:** Backfill `parcel_key` using the same normalization the other 21 counties use.
- **Priority:** High.

---

## P2 — Refresh stale slopes.

### T-09 · 646,375 parcels have slopes older than their data
- **Issue:** Parcel-matched electrical docs stamped `last_utility_ingest: 'aug2026'` picked up new billing periods after their slopes were computed. Franklin alone: 246,138. Cuyahoga: 172,614. Montgomery: 78,690.
- **Impact:** Slopes regress against a truncated series. Downstream percentile ranking and campaign targeting use stale coefficients.
- **Action:** Add the update path (T-03 upsert), then recalculate where `last_utility_ingest` is newer than the thermal stamp.
- **Depends on:** T-03, T-10.
- **Priority:** High — largest correctness population.

### T-10 · 749,785 thermal docs carry no provenance
- **Issue:** Only `FranklinThermalLoads` has `calculated_at` (44,851 docs, all `2026-01-19`). The other 24 counties have none.
- **Impact:** Fresh and stale are indistinguishable, so incremental refresh is impossible — every refresh must be a full recompute.
- **Action:** Backfill `calculated_at`, `calculation_source`, and a new `input_delivery` watermark (the `last_utility_ingest` value the slopes were computed from). Make the tool always write all three.
- **Priority:** High — unblocks T-09.

---

## P3 — Quality and defects.

### T-11 · 22,430 records with null/absent/zero heating slope
- **Issue:** Cuyahoga 17,524 (15,954 `null`, i.e. gas-only records; 1,570 exactly `0.0` with `kwh_hl_cl_loads` full of `{'kwh': 0, 'date': 'NaT'}`), Franklin 2,157, remainder spread across 23 counties.
- **Impact:** Parcels present in the collection but carrying no usable electric signal — they pass an existence check and fail silently downstream.
- **Action:** Classify. `null` on a gas-only parcel is legitimate; `0.0` with `NaT` dates is corrupt input and should be recomputed or flagged.
- **Priority:** Medium.

### T-12 · Regression failure writes `0.0`, not an error
- **Issue:** Both `except` branches in `calculate_thermal_loads_for_parcel()` set slope/intercept/r² to `0.0`.
- **Impact:** A failed regression is indistinguishable from a genuine zero slope — this is how a share of T-11 was produced.
- **Action:** Write `None` plus a `calculation_error` reason. Never coerce a failure to a number.
- **Priority:** Medium.

### T-13 · 45,781 docs below the 3-period regression minimum
- **Issue:** Fewer than 3 billing periods, so `calculate_thermal_loads_for_parcel()` returns `{}` at line 313.
- **Impact:** Permanently ineligible until more deliveries arrive; currently indistinguishable from unprocessed parcels.
- **Action:** Mark as `ineligible: insufficient_periods` rather than leaving them absent, so audits stop re-counting them.
- **Priority:** Low.

---

## P4 — Separate project.

### T-14 · 3,239,625 electrical docs have no `parcel_id`
- **Issue:** 2,466,129 docs across 63 counties with no ThermalLoads collection, plus 773,496 inside the 25 thermal counties. Keyed by utility surrogate: `AES::Lisa Landis`, `DUKE::45206|2946 CLEINVIEW AVE`, `FE:OE:S335963995`. From the AEP/AES/Duke/FirstEnergy pre-enrollment ingest (commit `fbed58c`), ingested but never address-matched.
- **Impact:** 78% of the electrical corpus can never receive thermal loads. Butler (97,927), Hamilton (267,039), Stark (146,932), Summit (182,957) have zero eligible parcels.
- **Action:** Run `ResidenceMatcher` address→parcel matching as its own project. Not a fix to this tool.
- **Priority:** Low urgency, highest ceiling.

---

## Suggested sequence

1. **T-01** (stop the data loss) → **T-02** → **T-03** → **T-04** → **T-05**, **T-06**
2. **T-10** (provenance) → **T-08** (Montgomery key) → **T-07** (compute 60,733)
3. **T-09** (refresh 646,375)
4. **T-11**, **T-12**, **T-13**
5. **T-14** as a separate matching project

Audit queries: `scratchpad/thermal_gap2.py`, `scratchpad/join_audit.py` — not yet promoted to `scripts/`.
