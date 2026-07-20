# Bayesian Modeling Review — Prior Work Across empower and octopus

**Date:** 2026-07-07
**Purpose:** Survey and summarize all previous Bayesian modeling work before designing a new series of models (Statistical Rethinking / McElreath style). Review of the newly installed `pymc` skill included. No new models were created for this review.

---

## Overview

There are **two distinct generations** of Bayesian work, both in PyMC, both following the McElreath workflow (estimand → DAG → generative simulation → statistical model → fit), pointed at different questions:

1. **Generation 1 (Jan 2024, `~/devel/empower`):** physics-based disaggregation of household energy bills.
2. **Generation 2 (Oct 2025 – May 2026, `octopus`):** campaign engagement (email open/click) models in a registry-based software system.

---

## Generation 1: Energy Physics Models (`~/devel/empower`, Jan 2024)

**Goal:** decompose a household's utility consumption into weather-driven heating/cooling load vs. weather-independent baseload, using Ohio county parcel/CAMA data (Cuyahoga, Hamilton, Geauga), utility bills, and hourly weather.

### Themes (in dependency order)

1. **Thermal load features** — `WeatherLoads.ipynb` (classical, no PyMC). Integrated heating/cooling load (∫T dt below ~62°F / above ~72°F) from hourly NREL PSM3 and Iowa State ASOS station data, joined to per-parcel square footage. Produces the `Hl`/`Cl` predictors used everywhere downstream. Conceptual ancestor of the freezing/hot threshold-hour metrics added to campaigns in July 2026.

2. **Heating/cooling slope screening** — `HeatingSlopeModel.ipynb` (classical). Per-building slope of energy vs. heat load (electric and gas). Classifies homes into archetypes (gas-heated, electric-heat, AC-dominated summer users) and finds intervention candidates via savings vs. age/sqft comparables. Mature and production-usable when work stopped.

3. **Baseload — two competing approaches:**
   - *Top-down regression* (`Baseloads vs SQFT.ipynb`, PyMC): `E_bl = E_nom + m_sf·R_sf + m_N·R_N` with Gamma sqft prior and Categorical head-count prior; prior predictive checks included.
   - *Bottom-up generative aggregation* (`Baseloads Via Aggregation.ipynb` + `src/bayesian/baseload_models.py`, PyMC): appliance-level dataclasses (fridge, hot water tank, freezer, clothes, stove, lighting, devices), each with Categorical ownership gates (Cincinnati ownership priors), Normal power-rating priors, and usage hours linear in household size; total baseload is the Deterministic sum. Fridge model is a `pm.Mixture` over 1-vs-2 fridge components. Freshly modularized in `Model Reworking.ipynb` when work stopped.

4. **AC power model** — `AC Power Consumption.ipynb` (PyMC). Piecewise/duty-cycle cooling power against per-county monthly temperature distributions pulled from MongoDB (`climate.py` helper). Generative model and priors in place; real-data statistical section left as a stub.

5. **Full disaggregation** — `Disaggregation Approach.ipynb` (PyMC, most complete inference work). Hierarchical regression of total kWh on heat load and sqft (~1,500 homes subsample), Gamma likelihoods for strictly positive kWh, heat-load-dependent Gamma parameters, posterior predictive checks and trace diagnostics. Evolving toward `E = baseload + efficiency × heat_load` with empirically-informed priors fed back from fits. `CombiningModels.ipynb` is an incomplete scratch pad stitching baseload + climate together.

### Supporting pipeline (`src/bayesian/`)
- `ingest_ohio.py` — loads county CAMA building and tax CSVs into MongoDB (`building_information`, `tax_information`), joins them per parcel via `$lookup`.
- `query_ohio.py` — returns tidy per-parcel 12-month kWh + sqft DataFrames filtered by property class.

### Where it stopped
Feature engineering and slope screening were mature. The open frontier was a single hierarchical model jointly disaggregating a bill into baseload + weather-driven load + efficiency. The AC model and combined model had unfitted real-data sections.

---

## Generation 2: Campaign Engagement Models (`octopus`, Oct 2025 – May 2026)

**Goal:** model who engages with outreach campaigns (email opens/clicks). Built as a config-driven system: `src/bayesian_models/` registry with per-model directories (`config.yaml` + `model.py`), training scripts in `src/bayesian_scripts/`, shared `validation/` package (r-hat/ESS/divergences), and a Flask modeling dashboard.

### Registered models

| Model | Status | Outcome | Structure | Data source |
|---|---|---|---|---|
| model_01_baseline | active | open | Flat logistic: annual cost, savings. Priors N(0,2)/N(0,1) | Mongo `participants` |
| model_02_energy_burden | active | open | Flat logistic: burden (positive-biased prior N(0.5,1)), income, household size | Mongo `participants` |
| model_03_demographics | active | open | Adds kWh cost to model 02 | Mongo `participants` |
| model_04_campaign_effects | **beta** | click | **Causal treatment-effects**: 6 message-type treatments, DAG + backdoor documentation, E-value sensitivity plan, county varying intercepts (non-centered), ICC | Mongo `campaigns` + `participants` + `exposures` |
| model_05_rate_energy_income | active | click | **Varying intercepts and slopes** by income category (non-centered). GPU/NumPyro default | Mongo `participants` |
| click_model | active | click | Flat pooled logistic (income, burden, age). Config claims county hierarchy but implementation is flat. GPU default | Mongo `participants` + per-county `*Demographic` |
| click_model_02 | active | click | Adds house age via `*Residential` collections. Flat pooled. GPU default | Mongo, synthetic fallback |
| messaging_effectiveness | active | open → click | **Two-stage funnel**, campaign random intercepts per stage (non-centered), msg-type/location/seasonal effects | Pickle `data/processed/messaging_poc_data.pkl` |

Sampler defaults across trainers: draws=2000, tune=1000, chains=4, target_accept 0.9–0.95.

### Supporting research and docs
- `.claude_docs/research_bayesian_performance_20251015.md` — PyMC vs Stan vs Rust comparison. Conclusion: stay on PyMC with JAX/NumPyro backend (~11× speedup on GPU at ~160k obs; GPU worthwhile above ~50k obs). Motivated the `--gpu` flags in newer trainers.
- `.claude_docs/BAYESIAN_MODELING_PROGRESSION.md` + `MODEL_PROGRESSION_SUMMARY.md` — master roadmap: 10-model progression (baseline → burden → demographics → property → campaign hierarchy → geographic hierarchy → crossed effects → interactions → time series → spatial CAR), with hypotheses H1–H21 and comparison criteria (LOO-CV, WAIC, posterior predictive checks).
- `.claude_docs/bayesian_model_system.md` — architecture and how-to-add-a-model guide.

### Critical finding: nothing is trained
No traces, no `data/inference/` outputs, no `models/` directory anywhere. Every model is code-complete but unfit. The system is mid-build-out, not serving results.

### Rough edges to address before new work
- Three stale legacy files superseded by directory-based models: `model_01_baseline_legacy.py`, `model_02_energy_burden.py`, `messaging_effectiveness_model.py`.
- Output-path inconsistency: `base_model.py` targets `data/inference/`, but `click_model`'s `train_model.py` writes to `models/`.
- `click_model`/`click_model_02` configs tagged hierarchical/county-level, but implementations are flat pooled regressions.
- `messaging_effectiveness` depends on a pickle produced by `src/bayesian_scripts_orig/prepare_messaging_data.py` instead of reading MongoDB like the rest.
- Progression rungs 6–10 (geographic hierarchy, crossed effects, interactions, time series, spatial) unbuilt.

---

## The `pymc` Skill (`.claude/skills/pymc/`)

PyMC 5.x workflow guide aligned with existing project practices: standardize predictors, weakly informative priors, prior predictive checks before fitting, non-centered hierarchies, R-hat < 1.01 / ESS > 400 / zero-divergence gates, posterior predictive checks, LOO/WAIC comparison with Pareto-k reliability checks.

Bundled assets:
- `scripts/model_diagnostics.py` — `check_diagnostics()` and `create_diagnostic_report()` (trace/rank/autocorrelation/energy plots, summary CSV).
- `scripts/model_comparison.py` — `compare_models()` (LOO/WAIC), `check_loo_reliability()`, `model_averaging()`.
- `assets/` — linear regression and non-centered hierarchical model templates.
- `references/` — distribution selection catalog, sampling/inference troubleshooting, workflow cookbook.

**DRY note:** the skill's diagnostics overlap with `src/bayesian_models/validation/`. Decide once which is canonical when new models are built, rather than accumulating a third diagnostics path.

---

## Observations for the Next Model Series

- Model 04 (campaign effects) is the best in-repo template for McElreath-style causal work: explicit DAG, backdoor-path documentation, E-value sensitivity plan, non-centered county hierarchy.
- The two generations connect naturally but have never been joined: Gen-1 produced physical energy features (heat-load slopes, baseload estimates), Gen-2 models engagement — and no model yet uses weather as a predictor of campaign response, despite all 153 campaigns having been enriched with threshold-hour weather data (July 2026, `feature/campaign-weather` branch).
- Candidate directions for the new series (undecided as of this review): weather → campaign response; Text75-84 → IMPACT conversion (treatment-effect analysis with the EGE no-text control group); resuming the M1–M10 email progression; or another dataset.
