# Bayesian Campaign Models — Development (clicks + applications, pooled & seasonal)

**Date:** 2026-07-16
**Goal:** Predict the two conversion-relevant outcomes — **link clicks** and **intake applications** — from campaign, weather, message-theme, sequence, and demographic inputs, across seasonal subsets and the pooled all-campaign collection; identify the most consequential predictors in each configuration.
**Stack:** PyMC 5.25.1, NUTS via NumPyro/JAX 0.6.2 on an NVIDIA RTX A6000 (CUDA backend; see §7).
**Framework:** `src/bayesian-fable/` (Statistical Rethinking workflow: estimand → DAG → generative simulation → prior predictive → fit → diagnostics gate → posterior predictive → contrasts). This document covers the *development*; results live in the companion results artifact.

---

## 1. Outcome inventory and what is identifiable where

Profiling `empower_development.exposures` ⋈ `campaigns` (2026-07-16):

| Outcome | Events | Trials | Where observed | Season coverage |
|---|---|---|---|---|
| `text_clicked` | 12,027 | ~39k sends | Jan–Mar 2026 IMPACT cohort only (12 campaigns) | **winter only** (tracking regime) |
| `email_clicked` | 280 | ~125k sends | all 63 email campaigns | 62/63 campaigns are summer 2025 |
| `applied` (attributed) | 227 | ~211k send-rows | attribution runs through tracked text clicks | **winter only** (F6 finding) |
| `replied` | 3,627 | ~204k text sends | all text campaigns, both regimes | **summer 2025 + winter 2026** |

Three structural facts shape every configuration choice:

1. **Text click tracking exists only for the 2026 IMPACT cohort.** 2025 text sends cannot register clicks *by construction*. Any model that pools across regimes launders the tracking change into its coefficients, so text-click and application models are restricted to the IMPACT cohort (this is also why "seasonal text-click models" cannot exist — there is no summer click data to fit).
2. **Season ≈ cohort.** Summer = 2025 agencies/lists/channels; winter = 2026 IMPACT. Seasonal contrasts are honest only for `replied` (the one outcome observed in both), and even there differences read as *season + cohort*, not season alone.
3. **Message themes were coded onto the 12 IMPACT campaigns on 2026-07-15.** The Jul-13 application model could not ask the theme question (all theme dummies were constant in the attributable cohort); this run can. That refit is one of the main deliverables here.

## 2. Universal data gates (enforced in `core/frames.py`)

Unchanged from the series design (doc 20260709_1745): dedupe exposures on `(participant, campaign)` (129k duplicate pairs); normalize `county_key`; weather models require `campaigns.weather.status == 'ok'`; adjust with `estimated_income` (99.8% coverage) never `income_level` (13.2%); z-score continuous predictors in-model and persist scalers; `replied` is the cross-regime text outcome.

## 3. Model forms

All engagement models share one hierarchical Bernoulli skeleton (`models/engagement.py`), per Rethinking Ch. 13 (multiple cluster types, all non-centered):

```
y_i ~ Bernoulli(logit_p_i)
logit_p_i = a  +  a_month[m_i] + a_county[g_i] + a_campaign[c_i]     (non-centered REs)
          + Σ_k b_k · z(x_k,i)          continuous terms (weather, demographics)
          + Σ_t b_t · theme_t,i         binary message-theme dummies, entered RAW
a        ~ Normal(logit(base rate), 1)
b_weather ~ Normal(0, 0.3);  b_theme ~ Normal(0, 0.5);  b_demog ~ Normal(0, 0.5)
sigma_RE ~ Exponential(2), offsets ~ Normal(0,1)
```

**New this run:** a `binary_terms` path in the shared builder. Theme dummies stay 0/1 (not z-scored) so `exp(b)` is directly the odds ratio for "campaign carried this theme"; constant columns are skipped, not errored (themes can go constant inside a seasonal subset).

The application model (F6) is a **discrete-time hazard** at the send grain: every deduped send is a Bernoulli trial, y=1 iff that send is the best-confidence attributed trigger of the participant's earliest application; post-application sends are censored. Its intercept prior centers on the empirical base-rate logit (~250 events / ~300k rows); sequence features (prior-send count, recency, wave position) enter alongside weather, themes, and demographics.

### 3.1 The predictor-ladder design (new models F7/F8)

"Which predictors are most consequential" is asked two ways:

- **Within a model:** posterior magnitudes/odds ratios with 94% HDIs.
- **Between models:** a nested variant ladder on ONE frame, PSIS-LOO compared — which predictor *block* buys out-of-sample skill beyond cluster structure:

| Rung | Adds |
|---|---|
| `re_only` | varying intercepts only (month + county + campaign) |
| `demog` | + income, household size, energy burden |
| `weather` | demog + temp_mean, freezing_hours (F7) / hot_hours (F8) |
| `themes` | demog + six message-theme dummies |
| `full` | demog + weather + themes |

Clusters enter every rung, so a block only wins LOO by explaining variation the REs cannot simply absorb. `core.workflow.fit_ladder()` owns the invariant that LOO is only compared within a single frame; F1's pooling ladder was refactored onto it (DRY).

## 4. Configuration matrix (this run)

| # | Model | Outcome | Frame / season | Purpose |
|---|---|---|---|---|
| 1 | F1 ladder | text_clicked (Binomial) | 12 IMPACT campaigns | click heterogeneity + shrinkage reference |
| 2 | F1 ladder | email_clicked (Binomial) | 63 email campaigns | rare-click heterogeneity reference |
| 3 | **F7 ladder ×5** | text_clicked | IMPACT winter 2026 (~38k rows) | most-consequential-predictor ladder for the rich click outcome |
| 4 | **F8 ladder ×5** + full refit | email_clicked | summer 2025 collection (~125k rows) | same ladder, rare-event regime |
| 5 | F2 | replied | summer 2025 | seasonal configuration |
| 6 | F2 | replied | winter 2026 | seasonal configuration |
| 7 | F2 | replied | pooled all campaigns | all-campaign collection (Jul-9 fit failed its gate; refit at target_accept 0.95) |
| 8 | **F6 refit** | applied | IMPACT winter 2026 | theme question, unlocked by the 2026-07-15 backfill |
| 9 | **F6 + campaign REs** | applied | IMPACT winter 2026 | how much theme/weather signal survives within-campaign pooling |

Sampling: NumPyro NUTS, 4 chains; ladders keep pointwise log-likelihood for LOO (draws trimmed to 500/chain on the 125k-row email frame for memory; a separate 1500-draw no-loglik run supplies F8's coefficients); hazard fits use `target_accept 0.99` per F6 guidance. Every fit passes the shared gate: R̂ < 1.01, ESS > 400, zero divergences, prior- and posterior-predictive checks persisted under `data/inference/fable/<model_id>/`.

## 5. Identification (what coefficients mean)

- **Demographics** vary at row grain → cleanly identified within campaigns; read as adjusted associations.
- **Weather and themes vary at the campaign grain.** F7 has 12 campaign clusters, F8 has 63. With campaign REs present, these coefficients report *what survives partial pooling across campaigns* — deliberately conservative. The generative recovery test (§6) quantifies exactly this shrinkage.
- **Applications:** the F6 DAG closes weather backdoors with {month, county}; channel contrasts measure attribution *observability*, not persuasion (email conversions are structurally invisible), hence the IMPACT-text restriction.
- **Seasonal splits** are cohort-confounded (fact #2) and are presented as descriptive regime contrasts.

## 6. Generative validation (known-answer tests)

The new `binary_terms` path was validated by simulation before touching real data (McElreath's parameter-recovery gate):

- **40 simulated campaigns** (the realistic scale): 10/12 parameters recovered in the 89% HDI; the two misses were campaign-grain terms pulled toward zero by RE competition — the *designed* behavior the caveats in §5 describe.
- **150 simulated campaigns:** 9/12 with all misses marginal (e.g. truth 0.05 vs HDI [0.055, 0.091]); at 89% coverage ~1.3 misses of 12 are expected by chance. Direction and magnitude recovered throughout → estimator consistent, code path correct.

Earlier gates for the reused machinery (F1/F2/F3/F5/F6 recovery) passed in the Jul 9–13 sessions and were not re-run.

## 7. GPU environment (repro note)

`jax.devices()` fell back to CPU with `RuntimeError: Unable to load cuSPARSE`. Root cause: the system CUDA **12.4** toolkit (`/usr/local/cuda`, driver 550) shadows the venv's pip-installed CUDA **12.9** userland — `libcublas.so.12` (12.9) resolved the *system* `libcublasLt.so.12` (12.4), which lacks `cublasLtGetEnvironmentMode`. Fix (persisted in `scripts/gpu_env_tool.sh`): prepend every `venv/.../nvidia/*/lib` directory to `LD_LIBRARY_PATH` and set `XLA_PYTHON_CLIENT_PREALLOCATE=false`. Verified: `[CudaDevice(id=0)]`, matmul on `cuda:0`.

## 8. Files touched this run

- `models/engagement.py` — `binary_terms` in builder + simulator (campaign-grain flags)
- `models/f07_text_click.py`, `models/f08_email_click.py` — **new** predictor-ladder models
- `models/f02_weather_text.py` — `summer`/`winter` seasonal variants
- `models/f06_application_hazard.py` — `impact2026_re` combined variant
- `models/f01_campaign_pooling.py` — `--outcome` support (+ tracking-regime gate for `text_clicked`), `fit_all` → shared `fit_ladder`
- `core/frames.py` — campaign month on the Binomial frame (regime/season gating)
- `core/workflow.py` — `fit_ladder()` (variant sweep + PSIS-LOO + persisted comparison)
- `run_fable.py` — f07/f08 registration, `--outcome`, variant-suffixed output dirs, generic ladder mode
- `scripts/gpu_env_tool.sh`, `scripts/run_bayesian_campaign_models_tool.sh` — environment + sweep driver

Reproduce: `./scripts/run_bayesian_campaign_models_tool.sh` (logs in `data/inference/fable/logs/`).
