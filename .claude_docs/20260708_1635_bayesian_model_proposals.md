# New Bayesian Model Proposals — Grounded in Live Data (July 2026)

**Date:** 2026-07-08
**Purpose:** Propose the next model series using *live* MongoDB numbers, following the pymc-skill workflow (estimand → DAG → frame → likelihood → priors → checks). Companion to the [inputs catalog](20260708_0940_bayesian_model_inputs_catalog.md) (written without a live DB) and the [prior-work review](20260707_2325_bayesian_modeling_review_summary.md).
**Evidence source:** `scripts/analyze_bayesian_model_inputs_tool.py` run against `empower_development` on 2026-07-08.

---

## 1. What the live data changed

The catalog's plan was written from the schema doc. Five live findings materially reshape it:

| # | Finding (live) | Consequence |
|---|---|---|
| 1 | **Heating dose is unidentifiable.** The 89,092 exposure rows that have `kwh_hl_slope` + income + burden are 99.96% May–Sep 2025 sends (34 winter rows). Campaign HDD across dose rows: sd 21.9, only 26 rows > 100 HDD. Thermal slopes live in Gen-1 counties (Richland 42.6k, Marion 21.7k, Allen 12.9k rows); winter 2026 campaigns went to Franklin, which has no slopes. | The catalog's flagship `hdd × kwh_hl_slope` interaction is dead. **Pivot to the cooling side**: CDD sd 27.5 across dose rows, 48,257 rows with CDD > 30, and `kwh_cl_slope` has identical coverage. Same salience physics, opposite season. |
| 2 | **`income_level` covers 13.2% of participants; `estimated_income` covers 99.8%.** | M02–M05-style models keyed on `income_level` silently drop ~87% of rows. New models adjust with `estimated_income` (+ `household_size`, 98.7%). |
| 3 | **`applications` cannot see control-group conversions.** 303 applications, 286 matched — and 0 from participants never texted. All attribution methods run through tracked text/landing clicks. | The Text75-84 vs EGE-control model must take its outcome from the IMPACT approved-report CSV (the Jun-15 combined export), not from Mongo. `applications` remains valid for *within-texted* funnel modeling. |
| 4 | **Duplicate exposures: 129,488 pairs, exactly one extra row each** (352,576 raw → 223,088 deduped). | Mandatory dedupe before any Bernoulli model, or every duplicated exposure is double-weighted. |
| 5 | **Text click tracking is cohort-specific.** In slope counties, text clicks ≈ 0 (12 events / 24,327 rows) while replies are rich (1,866); in the full text frame clicks are rich (12,021 / 84,897). | `replied` is the universal text outcome; `clicked` only for the 2026 IMPACT text cohort. Don't pool clicked across tracking regimes. |

Also confirmed: county-key drift is real and big (`FranklinCounty` 6,974 vs `Franklin` 1,867; `Richland` vs `RichlandCounty`) — normalize before indexing; `annual_gas_cost` is 0% populated (H6 dual-fuel flag unavailable at participant grain); weather `ok` on 153/163 campaigns; `temp_mean` vs `hdd` correlation −0.94 (pick one temperature axis).

### Universal data-quality gates (apply to every model below)

1. Dedupe exposures on `(participant_id, campaign_id)`.
2. Normalize `county_key` (strip `County` suffix).
3. Filter campaigns to `weather.status == 'ok'` when weather is used; carry `county_recipient_share` as a robustness weight.
4. Adjust with `estimated_income`, not `income_level`.
5. Z-score continuous predictors in-model; persist `_scaler_params` (existing loader convention).

---

## 2. Proposed models

### W1 — Cooling-dose weather salience (flagship; new model directory `model_06_weather_dose`)

**Estimand.** Direct effect of recently-experienced cooling demand on engagement, *as moderated by the building's physical cooling sensitivity*: does weather work through felt bills? This is the first model to join Gen-1 physics to Gen-2 engagement.

**DAG / identification.**

```
S(month) ──→ W(cdd) ──→ Y            adjustment set {S, G} for the W main effect;
G(county) ──→ W                       the dose interaction cdd × kwh_cl_slope varies
G ──→ D ──→ Y                         WITHIN campaign, so campaign varying intercepts
campaign REs absorb residual M, A     absorb all campaign-level confounding of it.
```

The interaction is the sharp test: campaign-level shocks (message, agency, list) cannot mimic a coefficient that only exists as within-campaign heterogeneity in `kwh_cl_slope`.

**Frame (live numbers).** Dose subset: 89,092 deduped weather-ok exposures, 143 campaigns, ~7 counties after normalization. Two channel-specific fits:
- Email open: 64,765 rows, 2,544 events (3.9%).
- Text reply: 24,327 rows, 1,866 events (7.7%).

**Likelihood & structure.**

```
y ~ Bernoulli(logit_p)
logit_p = a
        + a_month[m]                       # S, non-centered RE or FE (8 levels)
        + a_county[g]                      # G, non-centered RE
        + a_campaign[c]                    # residual campaign-level variation
        + b_cdd    * z(cdd_base65)         # campaign-grain: effective N ≈ 143
        + b_slope  * z(kwh_cl_slope)
        + b_dose   * z(cdd) * z(kwh_cl_slope)    # ← headline parameter
        + b_inc * z(est_income) + b_burden * z(burden) + b_hh * z(household_size)
```

**Priors.** `a ~ Normal(logit(base rate), 1)` (≈ −3.2 email / −2.5 text); treatment block `Normal(0, 0.3)`; covariates `Normal(0, 0.5)`; RE scales `HalfNormal(0.5)`. Prior predictive check before sampling (skill workflow).

**Sensitivity / robustness.** (a) Refit with `kwh_cl_r2 ≥ 0.5` (keeps ~56% of slope-holders) — slopes are estimates, r² is their precision; (b) weight or subset by `county_recipient_share`; (c) report the HDD-side analogue as *not estimable* with today's data rather than fitting it.

**Risks.** `b_cdd` main effect has effective N ≈ 143 campaigns (wide posterior expected — that's honest); ~7 counties is few levels for a county RE (weakly-informative scale prior does the pooling); slope counties are a selected stratum ("among Gen-1-linkable participants").

### W2 — Weather main effects on text engagement (broad frame; `model_07_weather_text`)

**Estimand.** Total direct effect of window weather (temperature axis + cold-extremes axis) on text engagement across all counties — the catalog's priority (a), sized honestly.

**Frame.** Text slice of the base frame: 84,897 deduped weather-ok text rows, 86 campaigns, 30 counties. Outcome `replied` (3,611 events, universal across tracking regimes). Secondary fit on `clicked` restricted to the 2026 IMPACT cohort.

**Structure.** Like W1 minus the dose row: `b_temp * z(temp_mean)` + `b_freeze * z(freezing_hours)` (r = −0.77 between them; acceptable, but report joint posterior), month + county + campaign REs, same participant covariates. Weather is campaign-grain: within-month HDD sd is 66–67 in Jan–Feb 2026 (n=4 campaigns each) and ~18 in May 2025, near-zero Jul–Sep — so the winter contrast rides on few campaigns. Say so in the writeup; the posterior will show it.

**Why keep it alongside W1:** W1 answers *mechanism* (felt bills) in summer counties; W2 answers the *policy* question ("send more when it's cold/hot?") across the whole footprint. They share the loader.

### C1 — Text75-84 → IMPACT approval vs. EGE control (`model_08_text_conversion`)

**Estimand.** Intention-to-treat effect of being on a Text75-84 list on program approval, using the only real control group (EGE no-text).

**Frame.** The Jun-15 combined campaign-control export (11,240 parcel records: text cohort ∪ EGE control), outcome = approved flag from the IMPACT report roll-up. **Not** Mongo `applications` (finding #3: structurally blind to control conversions).

**Deliverable 1 is a covariate-balance table** (estimated_income, burden, household_size, county mix) between arms — computed *before* any fitting. If balanced: `approved ~ texted + county REs`. If not: add covariate adjustment and report both.

```
approved ~ Bernoulli(logit_p)
logit_p = a + b_text * texted + a_county[g] + b·z(covariates)
```

Priors: `b_text ~ Normal(0, 0.5)` (the Jun-15 raw ratio was ~4× — let the data earn it), rest as W1. Cohort sizes and approval counts per arm come from the export CSV at build time; E-value sensitivity for unmeasured list-construction confounding (model-04 convention).

**Within-texted funnel (C1b, optional extension).** Among the 7,417 texted cohort, 249 have Mongo applications (3.4%) — a valid *within-treated* funnel stage (`text → click → apply`) with attribution confidences (0.7–0.95) as weights.

### M01 baseline fit (prerequisite, no new code)

Nothing in the registry has ever been trained. Before any new model lands, fit `model_01_baseline` as-is (email open ~ annual cost + savings) to (a) shake out the training/GPU/persistence path end-to-end and (b) produce the reference LOO every comparison needs. Known caveat: it reads participant-grain data; keep it as a smoke test + reference, not a conclusion generator.

---

## 3. Comparison & validation plan

- Per skill workflow: prior predictive → NUTS (4 chains, `target_accept 0.9–0.95`, `log_likelihood=True`) → R-hat < 1.01 / ESS > 400 / 0 divergences → posterior predictive (calibration by campaign, by county) → LOO within outcome family only (email-open models vs each other; text-reply models vs each other).
- W1's decision output: posterior for `b_dose` (odds-ratio per 1-sd dose), plus counterfactual "hot-week vs mild-week send" contrast for a high-slope vs low-slope recipient.
- DRY note: reuse `src/bayesian_models/validation/` as the canonical gate; the skill's `scripts/model_diagnostics.py` only for ad-hoc plots — don't grow a third path.

## 4. Recommended order

1. **M01 smoke-test fit** (hours; unblocks the pipeline).
2. **W1 cooling dose** (new science; loader shared with W2).
3. **W2 broad weather effects** (same loader, different frame/outcome).
4. **C1 balance check → conversion model** (needs the IMPACT export join; highest stakeholder value if balance holds).
