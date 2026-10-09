# Bulk Need Analysis — Design Spec

**Date:** 2026-10-08 · **Branch:** `feature/need-analysis` · **Status:** draft for review
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
- ~28 % of ElectricalDB docs (Franklin sample) have null `parcel_id` → cannot join to parcel layers.
- Missing values are encoded four ways: absent field, `null`, sentinel `-1`, empty string `''`.
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
  "income_est": 42000, "hh_size": 3, "fpl_pct": 168, "smi_pct": 52,
  "annual_kwh": 11840, "annual_cost": 1720, "energy_burden": 4.1, "burden_basis": 0,
  "usage_pctile": 71, "peak_ratio": 1.84, "months_usage": 12,
  "hl_slope": 0.142, "cl_slope": 0.311, "thermal_r2": 0.82, "hl_per_sqft": 0.000094,
  "year_built": 1958, "sqft": 1510, "stories": 1, "home_value": 154000,
  "owner": true, "senior": false, "children": true, "length_residence": 7,
  "heat_fuel": 2, "gas_annual": 640,
  // --- quality ---
  "missing": [3, 17],                    // field codes linked-but-blank (sentinel/empty), §5.4
  // --- rule outputs ---
  "dims": [2, 0, 0, 0, 2, 2],            // levels, order fixed in §6
  "proxy": 32,                           // bitmask: which dims came from proxies
  "dim_sum": 6                           // sum of known levels (-1 excluded), for sorting
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

- **`link` bits:** 0 electric · 1 residential · 2 demographic · 3 thermal · 4 gas · 5 enrollment.
  Bit set = linked. "Absent for county" vs "no match" is derived from `analysis_builds.sources_present`.
- **`missing` codes:** integer index of each canonical feature in `fields.json`.
- **`burden_basis`:** 0 electric-only (lower bound) · 1 electric + gas · 2 vendor-supplied cost.
- **`heat_fuel`:** 1 electric (measured) · 2 electric (inferred from winter kWh slope) · 3 gas (measured) · 4 other (measured); absent = unknown.
- **`dims` levels:** -1 unknown · 0 none · 1 moderate · 2 high. **Unknown is never coerced to 0.**

## 6. Need dimensions and rules (`registry/rules.json`)

Versioned; every threshold carries a `source` citation. Numeric tables (HHS Federal Poverty Guidelines by
household size, Ohio State Median Income, per-utility residential average rate) are **fetched from official
sources during P1 and cited** — not typed from memory.

`dims` order and logic:

| idx | Dimension | Level 2 | Level 1 | -1 Unknown when |
|---|---|---|---|---|
| 0 | Income need (`fpl_pct`, `smi_pct`) | ≤ 175 % FPL | ≤ 200 % FPL or ≤ 80 % AMI | income or hh_size missing (no default size) |
| 1 | Energy burden (`annual_cost ÷ income_est`) | ≥ 10 % | ≥ 6 % | income missing |
| 2 | Building inefficiency (`hl_per_sqft` county rank, `thermal_r2 ≥ r2_min`, default 0.5) | top 20 % in county | 20–40 %; or **proxy** built < 1980 w/o usable fit | no usable fit and no year_built |
| 3 | High usage (`annual_kwh` county percentile) | ≥ 90th | ≥ 75th | `months_usage < 12` |
| 4 | Vulnerability (senior, children, multi_unit/renter) | ≥ 2 modifiers | 1 modifier | all modifiers unknown |
| 5 | Electrification (heat_fuel or **proxy**: inferred from winter kWh slope) | electric-resistance heat signature | gas heat with high cooling slope | no fit and fuel unknown |

- `annual_cost`: vendor `annual_kwh_cost` when present (`burden_basis=2`), else `annual_kwh × utility rate`
  (+ gas when linked). Electric-only burden is a lower bound and labelled so.
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

## 13. Out of scope

Specific program enrollment workflows; geocoding / census-tract priors; writing to any source collection;
changes to Audiences behaviour beyond reusing its components; porting the engine to TypeScript.
