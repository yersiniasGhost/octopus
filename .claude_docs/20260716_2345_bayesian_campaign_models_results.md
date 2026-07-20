# Bayesian Campaign Models — Results & Statistical Metrics

**Date:** 2026-07-16/17 (GPU sweep; NumPyro NUTS on RTX A6000)
**Companion docs:** [model development](20260716_1920_bayesian_campaign_models_development.md) · plain-language versions (c/d artifacts, same date)
**Outputs:** `data/inference/fable/<model_id>/` (traces, summaries, reports) · logs in `data/inference/fable/logs/`
**Conventions:** coefficients are on the log-odds scale for z-scored continuous predictors (OR = odds ratio per +1 SD) and raw 0/1 for theme dummies (OR = campaign carries the theme vs not). Intervals are 89% HDIs unless noted. Convergence gate: R̂ < 1.01, bulk ESS > 400, zero divergences.

---

## 1. Fit inventory & convergence

| Config | Model | Frame | n (events) | Gate | Notes |
|---|---|---|---|---|---|
| Text-click pooling ladder | F1×3 | 12 IMPACT campaigns | 39,099 (12,027) | ✅ all three | Pareto-k warnings on partial/none (influential campaigns) |
| Email-click pooling ladder | F1×3 | 63 email campaigns | ~125k (280) | ✅ all three | same |
| Text-click predictor ladder | F7×5 | IMPACT winter, exposure grain | 38,248 (11,780) | ⚠ ESS 354–417 on 2 variants | 0 divergences; 500-draw economy mode; coefficients re-run at 2,000 draws |
| Email-click predictor ladder | F8×4 | campaign grain (63 rows) | 118,960 (249) | ✅ @0.99 | rare-event funnel (~10 div. @0.9); clean at target_accept 0.99, top pair swaps within noise |
| Email-click coefficients | F8 full_exposure | exposure grain | 118,960 (249) | ⚠ 1 divergence | near-pass; all R̂=1.00, ESS>1700 |
| Replies, winter 2026 | F2 | IMPACT cohort | 38,248 (~423) | ✅ | campaign-only REs (see §2) |
| Replies, summer 2025 | F2 | summer subset | 163,419 (~3.2k) | ❌ 134 div. (RE funnel) | substantive β's clean (R̂=1.00, ESS>3k) |
| Replies, pooled | F2 | all text campaigns | 201,667 (~3.6k) | ❌ 63 divergences | see §5 caveat; substantive β's clean (R̂=1.00) |
| Applications + themes | F6 | IMPACT winter | 38,166 (201) | ✅ | first fit able to ask the theme question |
| Applications + themes + campaign REs | F6 | IMPACT winter | 38,166 (201) | ✅ | robustness of F6 under within-campaign pooling |
| Engagement ladder (refit) | F5 | IMPACT winter | 38,248 | ✅ | Jul-9 fit used 3,249 rows (burden gate) — superseded |
| Opt-out companion | F5 | IMPACT winter | 38,248 | ✅ | income OR 1.22 — mirrors the reply pattern |

## 2. Structural findings that reshaped the fits (this session)

1. **Covariate-coverage trap:** `total_energy_burden` covers ~8% of the IMPACT winter cohort. Requiring it silently drops 39k → 3.2k rows. All winter models now adjust with `estimated_income` + `household_size` only; the Jul-9 F5 fit (and any winter row in the Jul-9 pooled F2) was affected and is superseded.
2. **RE collinearity in the IMPACT cohort:** each of the 12 winter campaigns is single-month *and* single-county, so month/county/campaign varying intercepts are mutually collinear there → degenerate ridge, ~150 divergences/fit, and 30× slower sampling. Winter models use campaign REs only; month/county/season contrasts are **not separable from campaign identity** in that cohort. (Email/summer frames keep all three RE sets: 46/63 email campaigns are multi-county, 10–17 campaigns/month.)
3. **March 2026 replies are zero** across ~11.7k text sends — a probable reply-ingestion regime edge, inflating pooled campaign heterogeneity (§5).

## 3. Campaign heterogeneity in click rates (F1 pooling ladders)

PSIS-LOO, per outcome family (higher elpd = better; partial pooling wins both):

| Frame | complete | none | **partial** | σ_campaign | ICC | mean rate |
|---|---|---|---|---|---|---|
| Text clicks (12 campaigns) | −91.5 | −64.2 | **−63.9** | 0.103 [0.060, 0.142] | 0.003 | 30.9% (a_bar −0.806) |
| Email clicks (63 campaigns) | −190.9 | −229.4 | **−165.3** | 0.624 [0.461, 0.778] | 0.107 | 0.18% (a_bar −6.327) |

Text campaigns cluster tightly around a ~31% click rate (±1σ ⇒ 28.7–33.1%): campaign identity explains almost nothing, so campaign-level predictors (themes, weather) have a **low ceiling** for text clicks. Email campaigns vary >3× (±1σ ⇒ 0.10–0.33%): which email goes out genuinely matters. The email `none` model collapses (p_loo ≈ 94 on 63 rows — classic rare-event overfit); shrinkage is doing real work.

## 4. Email clicks — coefficients (F8 `full_exposure`, 249 events)

Adjusted for month/county/campaign REs and each other:

| Predictor | β (mean ± sd) | 89% HDI | OR |
|---|---|---|---|
| temp_mean_f (per SD) | −0.265 ± 0.156 | [−0.494, −0.010] | **0.77** — cooler send-windows → more clicks |
| hot_hours (per SD) | −0.038 ± 0.125 | [−0.245, 0.153] | 0.96 (null) |
| estimated_income (per SD ≈ $22k) | −0.177 ± 0.095 | [−0.325, −0.023] | **0.84** — lower income → more clicks |
| total_energy_burden (per SD) | −0.163 ± 0.092 | [−0.309, −0.020] | 0.85 — *lower* burden → more clicks |
| household_size | −0.064 ± 0.068 | [−0.171, 0.044] | 0.94 (null) |
| six message themes | all | HDIs span 1 by wide margins | 0.97–1.28 (indeterminate at 249 events) |
| σ_month / σ_county / σ_campaign | 0.32 / **0.76** / 0.64 | — | county structure is the largest cluster effect |

Gate: 1 divergence (of 6,000 post-warmup transitions) — formally a near-miss; R̂ = 1.00 everywhere, min ESS 1,780.

## 5. Replies by season (F2)

| | Winter 2026 (IMPACT) | Pooled (all text) | Summer 2025 |
|---|---|---|---|
| n (replies) | 38,248 (~423) | 201,667 (~3.6k) | 163,419 (~3.2k) |
| Gate | ✅ 0 div. | ❌ 63 div. (RE funnel) | ❌ 134 div. (RE funnel) |
| b_temp_mean_f | −0.27 [−0.74, 0.18] | −0.09 [−0.49, 0.33] | −0.12 [−0.50, 0.27] |
| extremes axis | freezing 0.21 [−0.27, 0.65] | freezing 0.07 [−0.34, 0.50] | hot −0.07 [−0.48, 0.32] |
| b_estimated_income | **+0.212 [0.145, 0.280]** (OR 1.24) | +0.112 (OR 1.12) | +0.074 [0.041, 0.110] (OR 1.08) |
| b_household_size | −0.085 [−0.166, −0.004] | −0.051 | −0.041 [−0.072, −0.009] |
| σ_campaign | 2.54 [1.53, 3.52] | 4.07 [3.49, 4.60] | 4.04 [3.48, 4.60] |

Two things stand out. **(a) Income flips sign for replies**: higher-income participants reply *more* (winter OR 1.24/SD), while clicks and applications go the other way — replying to a text is a different behavior from clicking a link or filing an application. **(b) Campaign heterogeneity in replies is enormous** (σ 2.5–4.1 on the logit scale), partly real (auto-reply prompts differ by campaign) and partly regime (March-2026 zero-reply ingestion). The pooled model's 63 divergences sit in that RE funnel; its substantive coefficients (R̂=1.00, ESS>3k) are consistent with the seasonal fits but the fit is flagged as failing the strict gate. Weather main effects on replies are indistinguishable from zero in every configuration — the Jul-9 conclusion survives the refit.

## 6. Applications — the theme question answered (F6 refits, 201 events)

The 2026-07-15 message-theme backfill made the 12 IMPACT campaigns codeable for the first time. Odds ratios (94% HDI), `impact2026` variant / `impact2026_re` (campaign REs) variant:

| Factor | OR (impact2026) | OR (with campaign REs) | p(β>0) |
|---|---|---|---|
| Sent in last week of wave | **79 [54, 118]** | **81 [54, 122]** | 1.00 |
| First send of agency wave | 6.0 [3.0, 12.2] | 6.4 [3.2, 13.0] | 1.00 |
| First-ever communication | 3.8 [1.8, 8.0] | 4.0 [1.9, 8.5] | 1.00 |
| HDD of send window (per SD) | 3.7 [2.4, 5.7] | 2.5 [1.1, 4.9] | 0.98–1.00 |
| days_since_prev | 1.15 | 1.19 | 0.92–0.96 |
| estimated_income (per SD) | **0.80 [0.68, 0.94]** | 0.80 [0.67, 0.94] | 0.005 |
| **All six themes** | 0.59–1.23, HDIs span 1 | 0.63–1.16, HDIs span 1 | 0.11–0.68 |
| CDD, prior-send count, household size | ≈1, wide | ≈1, wide | — |

**Timing dwarfs content.** No message theme moves the application hazard detectably at 201 events; if anything `urgency_deadline` and `personalized_qualified` lean *negative* (p(β>0) ≈ 0.11–0.19). The wave-timing effects replicate the Jul-13 fit almost exactly and survive within-campaign pooling; HDD shrinks 3.7 → 2.5 under campaign REs (expected — weather is campaign-grain) but remains credibly positive. The mechanical last-week caveat from the Jul-13 writeup (click-window attributions skew late-wave) still applies: read 79 as "strongly enriched," not a pure causal 79×.

## 7. Engagement ladder refit (F5, none < clicked < replied)

On the corrected 38k-row frame with themes: all five estimable theme coefficients are null-to-slightly-negative on the whole ladder (e.g. urgency −0.31 [−0.94, 0.26]); income and household size have small negative effects (−0.04/−0.05 per SD); σ_campaign = 0.059 — once clicks dominate the ladder, campaigns are nearly interchangeable, matching F1-text. Cutpoints κ = [0.41, 4.17] (clicking is common, replying rare). The Jul-9 F5 fit (3,249 rows, burden-gated, no themes) is superseded.

## 8. Predictor-ladder LOO comparisons (F7 text clicks / F8 email clicks)

**F7 — text clicks, IMPACT winter (38,248 sends, 11,780 clicks), exposure grain, 500 draws/chain:**

| rank | variant | elpd_loo | Δelpd | dSE |
|---|---|---|---|---|
| 0 | **demog** | −23,569.9 | 0 | — |
| 1 | weather | −23,570.0 | 0.05 | 0.46 |
| 2 | themes | −23,570.0 | 0.08 | 0.74 |
| 3 | full | −23,570.5 | 0.53 | 0.77 |
| 4 | re_only | −23,593.0 | **23.0** | 7.1 |

No Pareto-k warnings. **Demographics is the only block that buys out-of-sample skill** (Δ23 ± 7 over REs-only); adding weather or themes on top changes nothing (Δ ≤ 0.5, within 1 SE — `full` is slightly *worse*, a pure complexity penalty). Coefficients from the full variant: income −0.061 [−0.081, −0.043] (OR 0.94/SD) and household size −0.048 [−0.066, −0.030] (OR 0.95/SD) — small but precisely estimated; every weather and theme HDI straddles zero; σ_campaign = 0.087, matching F1's finding that text-click rates barely differ by campaign. Ladder fits show 0 divergences; ESS on a few intercept/σ params sits at 354–417 (500-draw economy mode) — below the 400 gate for two variants, immaterial to the ranking; the reported full-variant coefficients come from the 2,000-draw refit.

**F8 — email clicks, summer collection (63 campaign-Binomial rows, 249 events):**

Final fits at target_accept 0.99 (0 divergences; LOO compare `20260717_012736`):

| rank | variant | elpd_loo | Δelpd | dSE |
|---|---|---|---|---|
| 0 | full | −149.97 | 0 | — |
| 1 | weather | −149.98 | 0.01 | 1.0 |
| 2 | re_only | −150.53 | 0.56 | 1.9 |
| 3 | themes | −151.22 | 1.25 | 1.3 |

**All four rungs are statistically tied** — neither weather nor themes explains the 3× campaign-to-campaign variation in email click rates (themes carry a small overfit penalty). Whatever makes one email campaign out-click another is not captured by coded themes or send-window weather (candidates: subject lines, list composition, send-time-of-day). Caveats: p_loo ≈ 34–36 on 63 rows (the per-campaign overdispersion RE strains PSIS; Pareto-k warnings present). The initial target_accept 0.9 fits showed ~10 divergences each (rare-event funnel) and ranked `weather` nominally first; the clean 0.99 rerun swaps `full` and `weather` at the top by Δelpd = 0.01 — a hundredth of a dSE, i.e. run-to-run jitter that only reinforces the tie.

## 8.1 Where the "most consequential predictors" live (LOO + posterior evidence)

| Outcome | What matters (evidence) | What doesn't |
|---|---|---|
| **Applications** | Wave timing (last-week OR ≈ 79-81; first-in-wave ≈ 6; first-contact ≈ 4), cold send-windows (HDD OR 2.5–3.7), low income (OR 0.80) | all six themes, CDD, prior-send count, household size |
| **Text clicks** | demographics only (LOO Δ23): low income, small household — and even those are small (OR ≈ 0.94/SD) | weather, themes, campaign identity (σ=0.09) |
| **Email clicks** | campaign identity (σ=0.62, ICC 0.11), county (σ=0.76); cooler windows lean helpful (OR 0.77, exposure grain) | themes; heat extremes; blocks at campaign grain (LOO tied) |
| **Replies** | campaign identity, overwhelmingly (σ 2.5–4.1); higher income (OR 1.08–1.24) | weather in every season/pooled config |

## 9. Reproduce

```bash
./scripts/run_bayesian_campaign_models_tool.sh   # main sweep
./scripts/run_bayesian_reruns_tool.sh            # post-fix follow-ups
python scripts/summarize_fable_results_tool.py   # consolidated tables
```
