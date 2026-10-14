# Bulk Need Analysis — Design Spec

**Date:** 2026-10-08 · **Branch:** `feature/need-analysis` · **Status:** approved 2026-10-12, amended
the same day from P1 data profiling (§14)
**Repos:** octopus (analysis engine, Python) → bolt-od (explorer UI, tool of record)

---

## 1. Purpose

Analyse the *entire* Empower household dataset — not a campaign audience — to show, per county or set of
counties, (a) what data we have and what is missing, and (b) which households show need for, or benefit from,
energy assistance or mitigation, and which do not. No single program is targeted; generic need dimensions are
combined into program *archetypes*.

**Audiences:** internal team (exploration, targeting) and external partners (agencies, utilities, funders).
Partner use sets the bar: thresholds must be explicit and cited, missing data must be shown honestly, and
partner-facing output must be aggregate-only.

**Decomposition** — three sub-projects, each with its own spec → plan → build:

1. **Household data layer + coverage profiler** (this spec, octopus)
2. **Need explorer** (this spec, bolt-od)
3. **Bayesian benefit models** (separate spec later; interface fixed here in §9)

## 2. Decisions made during brainstorming

| Decision | Choice |
|---|---|
| Audience | Internal + external partners |
| Home | Engine built in octopus (reusing its code); final tools live in bolt-od; engine may later be ported to bolt-od as tool of record |
| Need dimensions | All six: income need, energy burden, building inefficiency, high usage, vulnerability, electrification |
| "In assistance" | Inferred from rules/models now; schema reserves an optional **enrollment** source for partner rosters (PIPP/HEAP/HWAP) later. Empower `applications` (303) used as validation |
| Data architecture | Materialized household table rebuilt from source (not live joins, not aggregates-only) |
| Document size | < 1 KB (p99); measured prototype 465 B fully populated, ~260–360 B typical |

## 3. Data facts this design rests on

Verified against `empower_development` / `schema.md` (2026-09-24 profile):

- `{County}ElectricalDB` covers 88 counties, ~4.14 M meter documents — the only all-county layer.
- `{County}CountyResidential` exists for 25 counties; `{County}CountyDemographic` for 21 (Franklin 48k,
  Cuyahoga 10k, most others < 2k); `{County}ThermalLoads` for ~25; gas only `CuyahogaGasDB`;
  `CuyahogaMultiTenant`, `OttawaMultiTenant` exist.
- ElectricalDB docs with null `parcel_id` (measured 2026-10-12): Franklin 216,887 / 475,376 (46 %),
  Cuyahoga 139,341 / 396,338 (35 %), Adams 8,283 / 8,283 (100 %) → cannot join to parcel layers.
- Missing values are encoded at least seven ways: absent field, `null`, sentinel `-1`, empty string `''`,
  float `NaN` (Cuyahoga Demographic: 412–472 per field), the strings `'nan'` / `'Unknown'`, and
  field-specific sentinels (Cuyahoga `poverty_level_percent = 0` co-occurs with `NaN` income).
- Some meters stopped reporting years ago (Cuyahoga: last readings in 2016, 2023, 2024).
- Demographic collections hold several docs for some parcels (Franklin: up to 35 on one `parcel_key`).
- **Gas is excluded from this analysis (decision 2026-10-12).** `CuyahogaGasDB` readings end 2016-02, and
  membership tracks ingest batch, not fuel (thermal runbook §fuel separation: AUC 0.45–0.55).
- Field names drift per county (`md_householdsize` vs `household_size`, `County` vs `county`, etc.).
- No enrollment / rate-code / PIPP / arrears fields exist anywhere.
- Thermal docs exclude multi-meter parcels (T-06).

## 4. Unit of analysis

**One document per electric service point** (one ElectricalDB doc). Rationale: assistance is per utility
account; a multi-unit parcel holds several bill-paying households with different burdens.

- Parcel-level attributes (Residential, Demographic) attach via `parcel_key`.
- **Multi-meter parcels**: each meter is its own household, `multi_unit = true`, inherits parcel
  attributes, receives no thermal slopes (consistent with T-06).
- **Meters without `parcel_id`**: kept as usage-only households; linkage shows `unlinked_parcel`.
- Raw `time_series_elec` and monthly arrays are **not** copied; derived values are stored and `_id`
  equals the source ElectricalDB `_id` (pointer for free).

## 5. Collections (all new, in `empower_development`, derived & rebuildable)

### 5.1 `analysis_households`

Flat, **sparse** (absent field = missing), readable field names, ints where precision allows.

```jsonc
{
  "_id": "<ElectricalDB _id>",
  "county": "Franklin",
  "parcel_key": "10-088712-00",          // absent when unlinked
  "link": 43,                            // source bitmask, see §5.4
  "multi_unit": true,
  // --- features (each present only if known) ---
  "income_est": 42000, "hh_size": 3, "fpl_pct": 168, "ami_pct": 42,
  "annual_kwh": 11840, "annual_cost": 1720, "energy_burden": 4.1, "burden_basis": 0,
  "usage_pctile": 71, "peak_ratio": 1.84, "months_usage": 12, "last_read": 202607,
  "hl_slope": 0.142, "cl_slope": 0.311, "thermal_r2": 0.82, "hl_per_sqft": 0.000094,
  "year_built": 1958, "sqft": 1510, "stories": 1, "home_value": 154000,
  "owner": true, "senior": false, "children": true, "length_residence": 7,
  "heat_fuel": 1,
  // --- quality ---
  "missing": [3, 17],                    // field codes linked-but-blank (sentinel/empty), §5.4
  // --- rule outputs ---
  "dims": [2, 0, 0, 0, 2, 0],            // levels, order fixed in §6
  "proxy": 0,                            // bitmask: which dims came from proxies
  "dim_sum": 4                           // sum of known levels (-1 excluded), for sorting
}
```

Indexes: `{county:1}`, `{parcel_key:1}`, `{county:1, "dims.0":1}` … one per dimension, `{link:1}`.

### 5.2 `analysis_builds` — one doc per county build

`county`, `built_at`, `registry_version`, `rules_version`, `status` (`ok|failed|staging`),
`sources_present` (which source collections exist for the county), `source_counts`, `doc_count`,
`size_p50/p99`, `cutpoints` (county-relative percentiles used for levels), `unmapped_fields`, `error`.

### 5.3 `analysis_coverage` — one doc per county

- Per feature: counts by state `present | linked_blank | source_unlinked | source_absent_for_county`.
- Per feature: histogram counts on **globally fixed bin edges** (defined in `fields.json`) — required so
  bins sum across counties.
- Per dimension: counts by level `-1/0/1/2`, split measured vs proxy.
- Per source: match counts (for county × source matrix).

### 5.4 Encodings (defined once in `registry/fields.json`, read by both repos)

- **`link` bits:** 0 electric · 1 residential · 2 demographic · 3 thermal · 4 gas (reserved, unused
  while gas is excluded) · 5 enrollment. Bit set = linked. "Absent for county" vs "no match" is derived
  from `analysis_builds.sources_present`.
- **`missing` codes:** each canonical feature carries an explicit, never-reused integer `code` in
  `fields.json` (not its list position, so reordering the file cannot renumber stored docs).
- **`burden_basis`:** 0 annual kWh × utility rate · 1 vendor-supplied electric cost. Both are
  electric-only and therefore lower bounds.
- **`heat_fuel`:** 1 electric heat pump · 2 electric resistance · 3 gas · 4 other — measured sources only
  (P1: Cuyahoga auditor `heat_type = HTP` → 1); absent = unknown. No fuel is inferred.
- **`last_read`:** `YYYYMM` of the meter's latest reading; usage-derived values are stored regardless,
  but usage dims and computed burden require it within `usage_max_age_months` of the build.
- **`dims` levels:** -1 unknown · 0 none · 1 moderate · 2 high. **Unknown is never coerced to 0.**

## 6. Need dimensions and rules (`registry/rules.json`)

Versioned; every threshold carries a `source` citation. Numeric tables (HHS 2026 Poverty Guidelines by
household size, HUD FY2026 80 % "Low Income" limits per county, EIA-861 2025 per-utility bundled residential
price) were **fetched from official sources on 2026-10-12 and are cited** — not typed from memory.
Program anchors: HEAP and PIPP Plus 175 % FPG, HWAP 200 % FPG (ODJFS, administrator since 2026-07-01).
Engine-internal heuristics (r2_min, freshness window) cite the spec section that set them.

`dims` order and logic:

| idx | Dimension | Level 2 | Level 1 | -1 Unknown when |
|---|---|---|---|---|
| 0 | Income need (`fpl_pct`, `ami_pct`) | ≤ 175 % FPL | ≤ 200 % FPL or ≤ 80 % AMI | income or hh_size missing (no default size) |
| 1 | Energy burden (`annual_cost ÷ income_est`) | ≥ 10 % | ≥ 6 % | income or cost missing |
| 2 | Building inefficiency (`hl_per_sqft` county rank; usable fit = `thermal_r2 ≥ r2_min` (0.5) ∧ `hl_slope ≥ 0` ∧ ¬multi_unit) | top 20 % in county | 20–40 %; or **proxy** built < 1980 w/o usable fit | no usable fit and no year_built |
| 3 | High usage (`annual_kwh` county percentile) | ≥ 90th | ≥ 75th | `months_usage < 12` or stale `last_read` |
| 4 | Vulnerability (senior, children, multi_unit/renter) | ≥ 2 modifiers | 1 modifier | all modifiers unknown |
| 5 | Electrification (measured `heat_fuel` only) | electric resistance (2) | — (gas rule removed with gas) | fuel unknown |

- `annual_cost`: vendor `annual_kwh_cost` when present (`burden_basis=1`), else `annual_kwh × utility rate`
  (`burden_basis=0`, fresh meters only). Gas cost is never added. Burden is a lower bound and labelled so.
- `ami_pct = 80 × income_est ÷ HUD 80 % limit for hh_size` (sizes > 8: +8 % of the 4-person limit per
  person, HUD methodology); `fpl_pct` sizes > 8 add the HHS per-person increment.
- County-relative cutpoints are computed in pass 1 of the build and stored in `analysis_builds.cutpoints`.
- Proxy-derived levels set the matching bit in `proxy` so UI can show measured-only.

**Program archetypes** — defined in `rules.json`, compiled to `$match` expressions at query time, never
stored on documents (tuning needs no rebuild):

| Archetype | Expression |
|---|---|
| Bill assistance candidate | income ≥ 2 |
| Weatherization candidate | income ≥ 1 ∧ inefficiency ≥ 1 ∧ ¬multi_unit |
| Electrification candidate | electrification = 2 ∧ (owner ∨ owner unknown) |
| Behavioural / efficiency (no income test) | high_usage ≥ 1 ∧ income = 0 |
| Likely no benefit | every known dim = 0 ∧ ≥ 4 dims known |

Every archetype count is reported with its **known-enough denominator** (households for which the
expression's inputs are all known).

## 7. Analysis engine (octopus)

```
src/analysis_engine/
  registry/fields.json      canonical features ← per-county source paths, sentinels, units, bins, codes
  registry/rules.json       thresholds, tables, dimension logic params, archetypes (with citations)
  registry.py               load + validate registry; expose encodings
  normalize.py              source doc → canonical values (sentinel/empty → missing)
  features.py               derived features (fpl_pct, burden, hl_per_sqft, usage pctile, peak_ratio)
  rules.py                  dimension levels + proxy bits from features and cutpoints
  build.py                  per-county two-pass build, staging collection, validation, swap
  coverage.py               analysis_coverage aggregation
  cli.py                    build_households --county X [--county Y] | --all [--dry-run]
```

Files stay small and single-purpose; reuse existing octopus helpers (`src/utils/envvars`, `log_manager`,
county key normalisation used by the thermal tools) rather than duplicating them.

**Build per county:** read sources → pass 1 compute features & county cutpoints → pass 2 assign levels →
write `analysis_households_staging_{county}` → validate → replace county docs in `analysis_households`
→ write `analysis_coverage` and `analysis_builds`.

## 8. Explorer (bolt-od)

Route `/analysis`, shared **scope bar** (reuse Audiences `FilterBar`): county multi-select + optional
dimension / archetype filters.

1. **Coverage** — Ohio county choropleth (metric selectable; static simplified county GeoJSON),
   county × source match matrix (absent vs low-match styled differently), field completeness stacked bars.
2. **Need** — six dimension tiles (stacked high/moderate/none/unknown, measured-only toggle), histograms
   for FPL %, burden %, hl_per_sqft, usage percentile with threshold lines from `rules.json`, two-dimension
   cross-tab heatmap, archetype counts with known-enough denominators.
3. **Households** (internal only) — drill-down from archetype/heatmap cell into existing
   `HouseholdTable` + `HouseholdDrawer`, plus a "Need profile" tab.

**Partner mode** (toggle; forced on for export): aggregates only, Households view hidden, small-cell
suppression (n < 11 → "<11"), coverage footnote on every chart, PNG + CSV export per chart.
No names, emails, or `participant_id` in any analysis view.

**Data access:** `lib/server/analysis-queries.ts` — pure pipeline builders (pattern of
`household-query.ts`), route handlers under `app/api/bolt/analysis/*`. County-only scopes sum precomputed
`analysis_coverage` docs; extra filters run live `$facet` on `analysis_households`.

**Charts:** hand-rolled SVG components (stacked bar, histogram, heatmap, choropleth) on open-design tokens;
no chart library.

**Registry sync:** octopus owns `fields.json`/`rules.json`; bolt-od holds a copy in
`lib/analysis/registry/` and shows a banner when its `registry_version` differs from the latest
`analysis_builds`. On engine port, the copy becomes canonical.

## 9. Bayesian interface (sub-project 3, spec later)

- Input: `analysis_households`; rule levels are baselines/priors.
- Goal: replace "unknown" with calibrated probabilities — hierarchical model with county partial pooling;
  `income_est` treated as a noisy measurement.
- Output: `analysis_posteriors`, `_id` = household `_id`, per target mean + 90 % interval, `model_version`;
  model cards in `analysis_models`. Same < 1 KB constraint.
- Validation: Empower applicants rank high (AUC, calibration); partner rosters later become labels.
- Reuse `src/bayesian-fable`, `src/bayesian_models/model_registry.py`.

## 10. Error handling

- Atomic county builds; a failed build leaves the previous version live and records `status: failed`.
- Source fields not in the registry are recorded in `analysis_builds.unmapped_fields` (never silent).
- Pre-swap gates: doc count = source meter count; p99 size < 1 KB; coverage sums = doc count.

## 11. Testing

- **octopus (pytest):** fixtures per schema variant (`-1`, `''`, `null`, absent, `md_*` vs plain names,
  multi-meter, unlinked); table-driven rule tests at each threshold boundary; unknown-not-zero tests;
  size test asserting a fully populated doc < 1 KB; build swap/rollback test.
- **bolt-od (vitest):** pipeline builders as pure functions; registry decoding (bitmask, levels, codes);
  coverage summing across counties; small-cell suppression.
- **Reconciliation tool:** compare `analysis_coverage` totals with live source counts for sampled counties.

## 12. Phases

| Phase | Deliverable | Repo |
|---|---|---|
| P1 | Registry (with cited tables) + builder for Franklin, Cuyahoga, Adams | octopus |
| P2 | All 88 counties, coverage, builds, reconciliation | octopus |
| P3 | `/analysis` Coverage view + county map | bolt-od |
| P4 | Need view, archetypes, household drill-down | bolt-od |
| P5 | Partner mode: suppression, footnotes, export | bolt-od |
| next | Sub-project 3 Bayesian spec | octopus |

P1 writes `analysis_households` and `analysis_builds`; `analysis_coverage` lands in P2 with the other
84 counties. P1 pre-swap gates are doc count = source meter count and p99 size < 1 KB.

## 13. Out of scope

Specific program enrollment workflows; geocoding / census-tract priors; writing to any source collection;
changes to Audiences behaviour beyond reusing its components; porting the engine to TypeScript.

## 14. Amendments (2026-10-12, from P1 data profiling)

1. **Gas excluded** (user decision): no GasDB reads, no gas cost in burden, no gas-based fuel inference;
   `gas_annual` dropped; electrification level 1 rule ("gas heat with high cooling slope") removed.
2. **No inferred fuel**: `heat_fuel` comes from measured sources only; `heat_fuel = 2 inferred` removed.
3. `smi_pct` → `ami_pct` (the §6 rule was always "80 % AMI"); HUD FY2026 per-county limits.
4. `burden_basis` re-encoded (0 rate-computed · 1 vendor), both electric-only.
5. `last_read` added; usage dims and computed burden require a fresh meter (`usage_max_age_months` 24).
6. Usable thermal fit also requires `hl_slope ≥ 0` (negative heating slopes are fit artifacts).
7. `missing` codes are explicit per field, not list positions.
8. Missing-value encodings extended to `NaN`, `'nan'`, `'Unknown'`, field-specific sentinels.
9. Open for P3 (bolt-od, not P1): adopt the comparables spec §8.1 provenance rule for which per-household
   fields the internal Need-profile tab may show (`income_est`, `hh_size`, and `fpl_pct` — which
   back-derives income — are purchased-overlay class); settle the route name together with the
   Campaigns/Reports review-path decision before claiming `/analysis` or `/reports`.

## 15. P2 decisions (2026-10-13, from the 85-county profile and the duplication check)

Evidence: `scripts/profile_need_analysis_counties_tool.py` (85 unbuilt counties, 3,258,842 meters) and
`scripts/check_preingest_meter_duplication_tool.py` (23 linked counties + Franklin, Cuyahoga). Both read-only.

### 15.1 Data facts

- 62 of the 85 counties are fully unlinked: no CountyKeys entry, no Residential, Demographic or ThermalLoads
  collection. Only usage dimensions are computable there; all other dimensions are unknown.
- CountyKeys names `{County}CountyDemographic` for Hardin, Montgomery, Ross and Scioto, which do not exist.
  The `X` / `XCounty` spellings in `participants.linkage.county_key` (14 counties) resolve to the same collections.
- Thermal fits for all 23 linked counties were recomputed 2026-09-23/24 (Hancock 70%); every county uses the
  same `hl+cl` kWh per °F-degree-hour fit. Rural slope medians are 2–9× Franklin's (see 15.2 Q4).
- The engine ranks percentiles itself (`rules.py`); the never-run `energy_percentile` refresh does not block P2.
- `utility` values are clean strings. AES (605,681 meters, 29 counties) has no rate in `electric_rates_2025`.
- 59,487 meters (1.8%) exceed 50,000 kWh/yr; 97.1% are unlinked. Duke feeds (residential-only) run 0.16–0.29%
  above 50k and max ≤ 1M; AEP/FE/AES feeds about 2%, with maxima up to 1.35 B kWh (Union).
- Ingest defects (2026-08-19, `src/tools/utility_bills/ingest.py`): (a) merges into existing docs never wrote
  `utility` (~228k docs in 23 counties, ~396k in P1 counties); (b) existing docs were matched on the raw
  `parcel_id` string, not `parcel_key` (415 certain duplicates: Huron 257, Cuyahoga 158); (c) addresses that
  map to several parcels were left unmatched and stored under a surrogate id beside the older linked doc
  (27.8k probable duplicates with zip, 40.8k upper bound; Montgomery 19–31k). P1 counts are inflated by about
  0.3% (Franklin) and 2.7% (Cuyahoga).
- About 91k unmerged pre-ingest docs in the 23 counties (91.6k in P1) last read 2016–2024. They stay households
  under the settled stale rule (usage unknown, no computed bill) and are counted in coverage.

### 15.2 Policy decisions

| # | Question | Decision |
|---|---|---|
| Q1 | Implausible usage | `annual_kwh > 50,000` (`usage.nonres_kwh` in rules.json) stores `nonres: true`. The doc is kept with `annual_kwh` for audit; usage dim, computed burden and the county percentile base treat its usage as unknown; archetype denominators exclude it; coverage counts it. |
| Q2 | Burden wording | Keep `≥` on the floored burden (floor(x) ≥ 6.0 ⇔ x ≥ 6.0). Cite as "at or above 6% / 10%". |
| Q3 | Inefficiency proxy | The pre-1980 proxy qualifies for Weatherization. Report and coverage split every Weatherization count into `measured` and `proxy`. |
| Q4 | Electrification | Keep the dimension and archetype. Counties with no mapped heat-fuel source report `no measured source`, not 0 of 0. The plan scans Residential collections for heating-type fields and maps any found. Store `kwh_hl_intercept`, `kwh_hl_r2`, `kwh_cl_r2` so a later amendment can infer electric heat/cooling from thermal fits and `peak_ratio`; that inference reopens §14.2 and is out of P2. |
| Q5 | Income coverage | Classify as stored (ceil on a banded estimate still classifies correctly at `≤`). Coverage reports per county the income-known share and the counts sitting exactly on tier boundaries; missing Demographic collections are a coverage gap, not a build error. |
| Q6a | CuyahogaMultiTenant | Not read. `multi_unit` stays "more than one meter on a parcel" in every county. |
| Q6b | owner_age → senior | True-only fallback: when the presence-of-senior flags are blank and `owner_age ≥ 65`, `senior = true`; otherwise unchanged. Flags win when present. `date_of_birth` is not read. Build summaries count the fallback additions. |
| Q7 | Ingest defects | Repair at the source before any P2 build (15.3), then rebuild P1 and build the 85 counties on clean data. |

### 15.3 Ingest repair (runs first)

1. Gzip `mongodump` of all 88 `{County}ElectricalDB` collections to `backups/`; no write before it exists.
2. Fix `ingest.py` (test first): merges also set a missing `utility`; existing docs are found by `parcel_key`;
   an address mapping to several parcels merges only when exactly one of those parcels holds an unmerged
   pre-ingest doc and the two series have no shared date with different readings.
3. `--repair` mode re-runs the fixed ingest over the same delivery files (excluding the mislabeled
   "AEP August 2026.zip" and the corrupt January AEP zip): it appends the surrogate doc's readings to the older
   doc (existing value wins on a conflicting date), writes `utility`, and deletes the surrogate doc. Dry by
   default, with a per-county report (utility backfills, type-(b) and type-(c) folds, skipped conflicts and
   multi-candidate addresses). The live run needs the user's explicit go-ahead. A second run reports zero changes.
4. Verify with `check_preingest_meter_duplication_tool.py`: `parcel_key` overlaps 0; address overlaps only the
   skipped cases; no-utility docs essentially only stale orphans.
5. Thermal fits are not recomputed in P2; folded parcels keep their fits (later refresh is optional).

This is the one P2 step that writes to a source collection; it is a data repair of the ingest, approved
2026-10-13, and does not change the "never write to source collections" rule for the analysis engine.

### 15.4 Build, gates, coverage, reconciliation

- Order: repair → rebuild Adams, Cuyahoga, Franklin → the 85 counties.
- `build --all` builds counties one at a time in one process with P1's per-county staging swap. A failing county
  records a failed `analysis_builds` entry and the loop continues; the run exits non-zero and nothing of the failed
  county is swapped in.
- Gates per county before swap: P1's (doc count = source meters, p99 < 1 KB, zero-meter refusal, no surrogate
  ids) plus: `nonres` count = meters above `nonres_kwh`; every doc's `county` = the built county; any unmapped
  field or value fails the county.
- Collection names keep the engine pattern plus existence check (`sources_present`); coverage compares them with
  CountyKeys where an entry exists and reports disagreements (CountyKeys covers only 23 counties).
- `analysis_coverage`: one rebuildable doc per county, written by the builder from its own counters: meters,
  linked, stale, `nonres`, priced share, income-known share, tier-boundary counts, usable-thermal share, per-dim
  known/unknown, archetype counts with Weatherization `measured`/`proxy`, source collections present/missing,
  heat-fuel source status, senior-fallback additions, `build_id`.
- Reconciliation tool: samples Franklin, a linked rural county, a fully unlinked county, Montgomery and one random
  county; recounts meters, linked, stale and >`nonres_kwh` with its own direct queries (not the engine's
  iterators); reports diffs against `analysis_coverage` and exits non-zero on any mismatch.

### 15.5 Registry changes (version `2026-10-13.1`)

- rules.json: `usage.nonres_kwh: 50000`; burden citation wording "at or above".
- fields.json: `nonres` (bool), `kwh_hl_intercept`, `kwh_hl_r2`, `kwh_cl_r2` (float, from thermal, moved off
  the ignored list); `senior` gains the `owner_age` true-only fallback.
- Tables: AES Ohio residential rate (EIA-861 2025, cited); HUD FY2026 low-income limits for all 88 counties
  (HUD file cited). ODJFS thresholds unchanged (statewide). `county_default_utility` stays at the three P1 counties;
  non-stale docs still lacking `utility` after repair are reported as unpriced, with no heuristic default.
- `household._derive` reads `utility` through the normalizer so NaN or non-strings mean missing, not a crash.

### 15.6 Verification

Unit tests for every item above (ingest fixes and idempotent repair; the 50,000/50,001 boundary; `nonres`
exclusions; measured/proxy split; `no measured source`; four senior-fallback cases; NaN utility; build-loop
failure isolation; coverage and reconciliation including a forced mismatch). Live sequence, each stage stopping
for the user: backup → repair dry run → **go-ahead** → live repair → duplication re-check → 88-county dry run
(per-county runtime, peak RSS, gates, unmapped, fallback and `nonres` counts) → reconciliation → spot checks
(5 households each in Montgomery, Holmes, Lucas against source) → **go-ahead** → live build → results doc.

### 15.7 Amendments 2026-10-13, from the Task 3 dry run

Approved by the user 2026-10-13.

1. The jan2026 AES delivery keyed accounts by customer name, aug2026 by numeric account, so each AES premise has
   two unlinked ingest docs at one service address (Greene ~46k pairs, Montgomery ~79k). Repair type (d): among
   unlinked ingest docs left after (c), a (utility, normalized address, zip5) group of exactly two docs from two
   deliveries folds the older delivery's doc into the newer one (order read from the tag's month and year); the
   newer `_id` is kept, which retires the name-bearing ids. Series conflicts and other group shapes are skipped.
2. Type (e): an unlinked ingest doc whose address resolves to a residential parcel with no doc, and which is the
   only remaining doc resolving there (counting 'none' addresses that would resolve there once it is linked), is
   linked in place (`parcel_id`, and `parcel_key` when present). No delete. Order (b) → (c) → (d) → (e).
3. The ingest never creates a doc for a parcel that already holds several docs (`skipped_multi_preingest`);
   re-ingests run with `--exclude AES:jan2026`.
4. Skip counters count only docs that end up neither deleted nor promoted, each once (last pass's reason);
   `skipped_none` (no candidate parcel holds a doc) are not duplicates and stay unlinked.
5. Ingest: a record matched to a parcel with no doc merges into the one existing doc whose `_id` is one of its
   surrogate keys, skips (`skipped_promote_multi`) when several exist, and creates a linked doc only when none does.
   A doc found by surrogate `_id` counts only if unlinked and at one of the record's addresses (else a collision).
6. Every fold that deletes a doc ((b), (c), (d)) sets the survivor's `merged_ids` to the sorted union of its own,
   the deleted doc's `_id` and the deleted doc's `merged_ids`; the ingest resolves a surrogate key through
   `merged_ids` as an alias (a doc's own `_id` wins, an alias claimed by two docs is not used, the same-meter rule
   applies), so re-ingesting a folded delivery re-creates nothing.
7. §15.3.3's "re-run the fixed ingest over the delivery files" was implemented as two steps: the database-only fold
   (`repair.py`, types (b)–(e), no delivery files read), then the fixed ingest over the deliveries as the `utility`
   backfill (`--exclude AES:jan2026`).
