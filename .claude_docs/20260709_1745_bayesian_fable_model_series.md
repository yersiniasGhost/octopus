# Bayesian-Fable Model Series — Design and Proposal

**Date:** 2026-07-09
**Location:** `src/bayesian-fable/`
**Method:** Statistical Rethinking (McElreath) workflow — for each model: estimand → DAG → generative simulation → statistical model → prior predictive → fit → diagnostics → posterior predictive → contrasts on the outcome scale.
**Companions:** [prior-work review](20260707_2325_bayesian_modeling_review_summary.md), [inputs catalog](20260708_0940_bayesian_model_inputs_catalog.md), [live-data proposals](20260708_1635_bayesian_model_proposals.md).

---

## 1. Relationship to previous implementations

Two prior generations exist and are **not** copied here:

- **Gen 1** (`~/devel/empower/src/bayesian`): appliance-level generative baseload models and energy disaggregation. Physics, not engagement. What *is* carried forward — because it is the single most insightful artifact of Gen 1 — is the **generative-first habit**: every fable model ships a `simulate()` that draws synthetic data from the assumed causal process, so parameter recovery is checked before real data is touched (Rethinking's "test the model on data where you know the answer").
- **Gen 2** (`src/bayesian_models/`): registry of flat/hierarchical logistic engagement models (M01–M05, click models, messaging_effectiveness). None ever trained. Two elements are deliberately reused rather than reinvented (DRY):
  - `src/bayesian_models/validation/` as the **canonical diagnostics gate** (R-hat/ESS/divergences, LOO, E-values) — fable adds no third diagnostics path.
  - Model 04's causal conventions (explicit DAG, adjustment-set documentation, non-centered county effects, E-value sensitivity) as the stylistic template.

Everything else — estimands, likelihoods, frames — is new, driven by the July-8 live-data findings (dedupe requirement, `estimated_income` over `income_level`, cooling-side pivot, control-group outcome living in the IMPACT export CSV, cohort-specific click tracking).

## 2. Universal data gates (enforced in `core/frames.py`, not per-model)

1. Dedupe exposures on `(participant_id, campaign_id)` — 129k duplicate pairs exist.
2. Normalize `county_key` (strip `County` suffix) before indexing.
3. Weather models filter `campaigns.weather.status == 'ok'`; carry `county_recipient_share` for robustness.
4. Adjust with `estimated_income` (99.8% coverage), never `income_level` (13.2%).
5. Z-score continuous predictors in-model; persist scaler params alongside traces.
6. `replied` is the universal text outcome; `clicked` only within the 2026 IMPACT cohort.

## 3. The series

| ID | Module | Estimand | Rethinking concepts | Grain / frame |
|----|--------|----------|---------------------|---------------|
| F1 | `f01_campaign_pooling` | How much do campaigns differ in engagement rate, and how much should individual campaign estimates shrink? | Partial pooling ladder (Ch. 13 reedfrogs): complete / no / partial pooling, LOO comparison, shrinkage | Campaign (Binomial, ~86–160 rows) |
| F2 | `f02_weather_text` | Total direct effect of window weather (temperature + cold-extremes) on text replies | Multiple cluster types (month, county, campaign), non-centered parameterization, backdoor adjustment {S, G} | Exposure (~85k text rows) |
| F3 | `f03_cooling_dose` | Does weather act through *felt bills*? CDD × cooling-slope interaction | Interactions (Ch. 8), within-cluster identification, precision-weight robustness (`kwh_cl_r2`) | Exposure (~89k dose rows) |
| F4 | `f04_text_conversion_itt` | Intention-to-treat effect of Text75–84 assignment on IMPACT approval vs EGE no-text control | Covariate balance before fitting, adjustment vs balance, E-value sensitivity | Parcel/participant (combined export CSV, ~11.2k) |
| F5 | `f05_engagement_ordered` | How do message treatments shift the whole engagement *ladder* (none < clicked < replied), and separately the opt-out pole? | Ordered-categorical outcome with cumulative logit cutpoints (Ch. 12), competing negative outcome | Exposure (2026 IMPACT text cohort) |

### F1 — Campaign pooling ladder (the reference model)

Three nested models on campaign-level Binomial counts `k_c / n_c`:

```
complete:  k_c ~ Binomial(n_c, p),          logit(p) = a
none:      k_c ~ Binomial(n_c, p_c),        logit(p_c) = a_c,  a_c ~ N(0, 1.5) independently
partial:   k_c ~ Binomial(n_c, p_c),        a_c ~ N(a_bar, sigma),  a_bar ~ N(-2.5, 1), sigma ~ Exp(1)
```

Purpose: (a) quantifies campaign heterogeneity (posterior `sigma`, ICC) — the justification for every campaign RE downstream; (b) produces the reference LOO nothing in Gen 2 ever produced; (c) fits in seconds, shaking out the whole persist/diagnose pipeline before the expensive models run. Fit separately per outcome family (email `opened`, text `replied`).

### F2 — Weather → text engagement (policy question: "send when it's cold?")

```
replied ~ Bernoulli(logit_p)
logit_p = a + a_month[m] + a_county[g] + a_campaign[c]          (all non-centered)
        + b_temp   * z(temp_mean_f)
        + b_freeze * z(freezing_hours)
        + b_inc * z(est_income) + b_burden * z(burden) + b_hh * z(household_size)
```

Identification per catalog DAG (a): W ← S → Y and W ← G → D/B → Y backdoors closed by {month, county}. Campaign REs absorb residual message/agency/list variation. Honest caveat baked into the report: weather varies at the campaign grain, so effective N for `b_temp` ≈ 86 campaigns; `temp_mean` × `freezing_hours` posterior correlation is reported (r ≈ −0.77 in the data).

Priors: `a ~ N(logit(0.043), 1)`; weather block `N(0, 0.3)`; covariates `N(0, 0.5)`; RE scales `Exponential(2)`.

### F3 — Cooling-dose salience (mechanism question: "does weather work through felt bills?")

F2's structure plus the headline interaction:

```
+ b_cdd   * z(cdd_base65)
+ b_slope * z(kwh_cl_slope)
+ b_dose  * z(cdd_base65) * z(kwh_cl_slope)      ← the estimand
```

The dose term varies **within** campaign (slope differs across recipients of the same send), so campaign-level confounders (message, agency, list) cannot mimic it — the sharpest identification available in this dataset. The HDD/heating analogue is documented as *not estimable* (34 winter dose rows) rather than fit. Robustness refit: `kwh_cl_r2 ≥ 0.5` subset (slopes are estimates; r² is their precision). Decision output: counterfactual hot-week vs mild-week send contrast for a high-slope vs low-slope household, on the probability scale.

### F4 — Text75–84 → IMPACT approval ITT (the only real control group)

- **Deliverable 1 is not a model**: covariate balance table (income, burden, household size, county mix) between text and EGE-control arms, produced by `--balance`.
- Model: `approved ~ Bernoulli(logit⁻¹(a + b_text·texted + a_county[g] + Σ b·z(x)))`, `b_text ~ N(0, 0.5)` — the observed ~4× raw ratio must be earned through the likelihood, not assumed in the prior.
- Outcome comes from the IMPACT approved-report roll-up in the combined campaign-control export CSV — **not** Mongo `applications`, which is structurally blind to control-arm conversions (all attribution paths run through tracked text clicks).
- E-value sensitivity for unmeasured list-construction confounding (the lists were built from these same county collections).
- ⚠ Input dependency: the Jun-15 combined export (11,240 parcels) is not currently present in this repo; the loader takes `--csv` with documented required columns.

### F5 — Ordered engagement ladder (new outcome family)

Engagement intensity is ordinal, not binary: `no_engagement < clicked < replied`. A cumulative-logit model (ordered cutpoints `κ₁ < κ₂`) lets message treatments shift the whole ladder at once instead of fitting separate, incompatible Bernoullis:

```
R_i ~ OrderedLogistic(phi_i, kappa)
phi_i = a_campaign[c] + Σ_t b_t · has_type_t + b_inc·z(inc) + b_burden·z(burden)
kappa ~ N(0, 1.5), ordered transform
```

Restricted to the 2026 IMPACT text cohort (the only regime where clicks are tracked — finding #5). Opt-out is *not* forced onto the ladder (it is qualitatively different, not "less engagement"); it gets a companion Bernoulli with the same linear predictor structure, reported side-by-side, so a message type that raises replies *and* raises opt-outs is visible as such.

## 4. Folder layout

```
src/bayesian-fable/
  README.md
  run_fable.py              # CLI: python src/bayesian-fable/run_fable.py <model> <simulate|prior|fit> [...]
  core/
    bootstrap.py            # sys.path shim (folder name has a hyphen → not importable as src.bayesian-fable)
    frames.py               # data gates + frame assembly (exposure / campaign-binomial / ITT-csv)
    workflow.py             # prior-pred → sample → validation gate → post-pred → persist
  models/
    f01_campaign_pooling.py
    f02_weather_text.py
    f03_cooling_dose.py
    f04_text_conversion_itt.py
    f05_engagement_ordered.py
```

Every model module exposes the same protocol: `simulate(rng, n)` (generative synthetic frame + true params), `load_frame(**kw)` (real data via `core.frames`), `build(frame)` (returns `pm.Model` with named coords/dims). `run_fable.py <model> simulate` fits on synthetic data and reports parameter recovery — the McElreath validation step — without touching MongoDB.

Outputs land in `data/inference/fable/<model_id>/` (traces `.nc`, `summary.json`, scaler params), matching Gen 2's output convention.

**Naming note:** the folder is `bayesian-fable` as requested; the hyphen makes it un-importable as a Python package (`src.bayesian-fable` is a syntax error), so `run_fable.py` bootstraps `sys.path` with both the repo root (for `src.bayesian_models.validation`) and its own directory (for `core`/`models`). Rename to `bayesian_fable` later if package imports from the web app are ever needed.

## 5. Validation & comparison plan

- Gates (via `src.bayesian_models.validation.check_convergence`): R-hat < 1.01, ESS > 400, zero divergences; sampling `draws=2000, tune=1000, chains=4, target_accept=0.9–0.95, log_likelihood=True`.
- LOO comparisons only within an outcome family: F1's ladder against itself; F2 vs F3 (same frame restricted to dose rows); F5 against an unordered-categorical baseline if warranted.
- Posterior predictive calibration grouped by campaign and by county (the two cluster types that could be misspecified).

## 6. Recommended execution order

1. **F1** — seconds to fit; end-to-end pipeline smoke test + reference LOO.
2. **F3** — flagship science (shares its loader with F2).
3. **F2** — same loader, broader frame, policy framing.
4. **F4** — highest stakeholder value; blocked on locating/regenerating the combined campaign-control export.
5. **F5** — new outcome family; enrich with `message_body` NLP features later.
