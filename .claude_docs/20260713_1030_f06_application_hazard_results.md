# F6 — What precedes an intake-form application? (results)

**Date:** 2026-07-13
**Model:** `src/bayesian-fable/models/f06_application_hazard.py` (discrete-time hazard, exposure grain)
**Dataset:** `exports/application_exposure_dataset_20260713_0901.csv` (210,831 send-rows, 227 attributed events) via `scripts/export_application_exposure_dataset_tool.py`
**Request:** analyst memo (2026-07-13) — factors influencing intake-form completions across all EMPOWER Saves campaigns.

---

## 1. Framing correction

The memo asked to "look at every intake form completion and examine which factors
influenced the application." Case-only data cannot identify influence — every row
would be a converter. F6 instead models each deduped send as a Bernoulli trial:
**y = 1 iff that send is the best-confidence attributed trigger of the
participant's earliest application** (post-application sends censored; converters
whose trigger row fails a data gate dropped rather than mislabeled).

## 2. Two structural findings that reshape the questions

**(a) Channel comparisons are unanswerable.** Attribution runs through tracked
text clicks and mailer UTM codes. Email has no click→application path: 1
attributed event per 124,711 email sends vs 207 per ~84k text sends. Channel
coefficients measure attribution *observability*, not persuasion. Any future
channel analysis needs email UTM/landing instrumentation first.

**(b) Only the 2026 IMPACT text cohort is uniformly observable.** Text click
ingestion exists only for Jan–Mar 2026 (12 campaigns, 39,008 sends). All 207
attributed text events fall there; 2025 text sends cannot convert by
construction. The primary model (`impact2026`) is restricted accordingly —
otherwise the tracking regime launders into every campaign-level coefficient
(the naive all-text fit shows "all conversions in cold windows," which is
regime, not weather).

**(c) Message-theme codes are absent exactly where they're needed.** The six
`message_types` codes are populated on 142/163 campaigns — but on **zero of the
12 IMPACT-2026 campaigns**. The content/theme question is unanswerable in the
attributable cohort until someone codes those 12 campaigns (small, high-value
task).

## 3. Primary results — `impact2026` (38,166 sends, 201 events, converged: 0 divergences, r̂ = 1.00)

Baseline hazard ≈ 53 applications per 10,000 sends. Adjusted for county and
month varying intercepts, demographics, and each other:

| Factor | OR (94% HDI) | Reading |
|---|---|---|
| **Sent in last week of participant's wave** | **95 [65, 142]** | Dominant. Raw: 148/10k vs 3.5/10k outside the last week (42× unadjusted) |
| **First send of an agency wave** | 4.5 [2.3, 8.9] | Supports the analyst's "first in campaign" hypothesis |
| **First communication ever received** | 4.2 [2.0, 8.7] | Novelty effect beyond wave position |
| **HDD of send window** (per SD ≈ 89 °F·days) | 2.1 [1.6, 2.9] | Positive, but see §4 — only 6 distinct HDD values across 12 campaigns; raw tercile pattern is non-monotonic (48.5 → 21.5 → 89.2 per 10k) |
| Estimated income (per SD ≈ $22k) | 0.81 [0.69, 0.95] | Lower income → more applications (consistent with program fit) |
| CDD, days-since-prev, prior-send count, household size | ≈ 1, wide | No detectable effect |

Sensitivity: `strict` (drops attributions < 0.85 confidence) is within noise of
`core` on every coefficient — findings are not driven by soft attributions.

### 3.1 Contrasts on the outcome scale (applications per 10,000 sends)

Population counterfactuals from the posterior (all 38,166 sends re-scored with
one factor changed; `scripts/compute_f06_scenario_contrasts_tool.py`,
2026-07-14). Median [94% interval]:

| Scenario | Apps / 10k sends |
|---|---|
| Observed cohort as-is | 53 [46, 59] |
| Send NOT in last week of wave | 8 [6, 11] |
| Send in last week of wave | 628 [524, 764] |
| Not first send of wave | 43 [37, 50] |
| First send of wave | 160 [94, 308] |
| Not first-ever communication | 44 [38, 50] |
| First-ever communication | 159 [90, 281] |
| HDD at cohort mean (183) | 59 [49, 74] |
| HDD one SD colder (272) | 122 [77, 203] |
| Household income $25k | 59 [51, 67] |
| Household income $60k | 44 [35, 53] |

⚠ The last-week=1 counterfactual (628/10k) extrapolates the flag onto sends
compositionally unlike real last-week sends; the **observed** contrast — 148 vs
3.5 per 10k — is the safer headline number. The flag counterfactuals are the
model's adjusted view, not a forecast of what forcing every send into the last
week would achieve (doing so would also change what "last week" means).

## 4. Honest limitations

1. **The outcome is "tracked click → landing → application."** Conversions that
   bypassed the tracked link (phone, walk-in, untracked browse) are invisible.
2. **Weather rides on 12 campaign clusters.** The HDD coefficient survives
   month adjustment but the design cannot cleanly separate a Feb-cold-snap
   effect from Feb-campaign-content; the raw non-monotonic tercile pattern
   urges restraint. The analyst's HDD/CDD question gets a "suggestive positive
   for heating-season cold, not established."
3. **Last-week OR has a mechanical component** for the 51 `click_window`
   attributions (a lagged application attributes to the most recent send, which
   skews late-wave). The 156 same-day-click events (96% in last week) are
   genuine same-day responses, so the effect is mostly real, but 95× overstates
   a pure causal reading.
4. **First/last flags are participant-relative** (their own sequence of sends
   per agency), since schedules didn't react to conversions (224/250 converters
   kept receiving sends).
5. Sparse demographics (owner_age 36%, children 22%, senior 28%, adults 36%)
   were exported but not modeled — Franklin-only coverage would confound with
   geography.

## 5. What would improve the next iteration

1. **Code `message_types` on the 12 IMPACT-2026 campaigns** → unlocks the theme
   question where it's identifiable.
2. **Add UTM parameters to email links** → unlocks the channel question going
   forward.
3. News-article salience (GDELT day-level extreme-weather coverage) remains
   un-acquired; HDD/extreme-hours currently proxy the same construct.
4. More coded waves with within-month weather spread → real weather
   identification (H: `hdd × kwh_hl_slope` dose remains the sharper test, per
   the inputs catalog §4.3a).

## 6. Reproduce

```bash
source venv/bin/activate
python scripts/export_application_exposure_dataset_tool.py          # dataset CSV
export LD_LIBRARY_PATH=$(python -c "import glob,sys;print(':'.join(sorted(set(glob.glob(sys.prefix+'/lib/python3.10/site-packages/nvidia/*/lib')))))")
python src/bayesian-fable/run_fable.py f06 simulate                  # recovery gate (passed)
python src/bayesian-fable/run_fable.py f06 fit --variant impact2026 --sampler numpyro --no-loglik --target-accept 0.99
# sensitivity: --variant core | strict | text_only | campaign_re
```

Traces/summaries/reports: `data/inference/fable/f06_application_hazard/`.
