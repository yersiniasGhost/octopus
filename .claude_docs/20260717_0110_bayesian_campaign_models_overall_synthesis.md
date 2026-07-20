# Campaign Modeling — The Whole Story in Plain Language

**Date:** 2026-07-17
**What was asked:** Predict clicks and applications from everything we know about EMPOWER Saves campaigns — message content, weather, timing, demographics — across seasonal groups and all campaigns together, and say which factors actually matter.
**What was run:** Twenty-plus Bayesian model fits (PyMC 5, GPU) across four outcome families (text clicks, email clicks, text replies, applications), each with formal out-of-sample comparisons and convergence checks. Details: [development](20260716_1920_bayesian_campaign_models_development.md) · [statistics](20260716_2345_bayesian_campaign_models_results.md) · [per-model plain language](20260717_0100_bayesian_campaign_models_plain_language_per_model.md).

---

## The five headline findings

### 1. Timing beats content — by a mile

For actual applications (the outcome that matters most), *when* a message lands dominates *what it says*. Sends in the **last week of a campaign wave** are dramatically enriched among application triggers (~80× odds, partly mechanical, still enormous after discounting); **first-of-wave** and **first-ever** contacts carry 4–6× odds. Meanwhile, across every outcome we modeled — applications, text clicks, email clicks, the engagement ladder, opt-outs — **not one of the six coded message themes shows a detectable effect**. This is the first analysis able to test themes on conversions (the 12 IMPACT campaigns were theme-coded on July 15), and the answer is consistently null at current sample sizes.

**Action:** invest in cadence design (deadline-proximity sends, strong opening touch), not copy-editing between the current themes. If theme effects are worth chasing, they need a real A/B design within a wave.

### 2. Cold weather sells a heating-assistance program — modestly, and only where conversion is visible

Colder send-windows raise application odds (2.5–3.7× per SD of heating-degree-days, robust to campaign-level pooling) and lean helpful for email clicks (cooler summer windows did better). But weather does nothing detectable for text clicks or replies in any season. Weather varies only *between* campaigns (12 winter clusters), so this is "suggestive and coherent," not proven — the same verdict as July 13, now with themes ruled out as a confounder.

**Action:** when a cold snap is forecast during an active wave, that's the week to send — cheap to act on, consistent with the evidence, low regret if the effect is smaller than estimated.

### 3. The program reaches its target population — and "engagement" means two different things

Lower-income households **click more** (texts: OR 0.94/SD; emails: 0.84) and **apply more** (0.80). But *higher*-income households **reply more** (1.08–1.24) and **opt out more** (1.22). Texting back — whether "YES", a question, or "STOP" — is a different behavior from quietly clicking a link and filing an application. Reply-rate dashboards therefore *undercount* engagement by exactly the households the program targets.

**Action:** don't use reply rate as the engagement KPI; use clicks (where tracked) and applications.

### 4. Campaign-to-campaign differences: huge for email and replies, negligible for text clicks

Text-click rates barely vary across campaigns (29–33%), so there's little headroom for campaign-level optimization of texts. Email campaigns vary 3× in click rate and reply rates vary wildly — but **none of that spread is explained by coded themes or weather** (formal model comparison: predictor blocks add zero skill). The likely real drivers — subject lines, send time-of-day, list composition — aren't captured in the data yet.

**Action:** log subject lines and send times as structured campaign metadata; that's where the unexplained email variance most plausibly lives.

### 5. You can only learn where the lights are on — and three switches are still off

Everything above is conditional on tracking coverage: text clicks exist only for Jan–Mar 2026 (12 campaigns), applications are only attributable in that same cohort, email conversions are invisible (1 attributed event in ~125k sends), and March 2026 replies appear to have stopped being ingested (flagged; worth a pipeline check). The seasonal comparisons the goal asked for are honest only for replies — and there, season mostly proxies *cohort* (different lists, agencies, channels), which is why we report "summer vs winter" descriptively rather than causally.

**Action (data investments, in value order):** (1) UTM parameters on email links, (2) subject-line/send-time metadata, (3) randomized theme assignment within one wave, (4) verify the March-2026 reply ingestion gap.

## Seasonal and pooled configurations — what they showed

- **Winter 2026** (the IMPACT cohort): the only place clicks and applications are observable; all conversion findings above are winter findings. Within-cohort, month/county/season are inseparable from campaign identity (each campaign = one month, one county) — a design limit, not a modeling choice.
- **Summer 2025**: carries almost all email data and most replies. Weather null on replies; cooler-window hint on email clicks; income-positive reply pattern present here too.
- **Pooled all-campaign models**: dominated by campaign heterogeneity (reply models) and regime differences; they confirm the seasonal fits' coefficients but add little — the seasonal/cohort splits are the more honest units of analysis.

## How much to trust this

Every fit went through prior checks, convergence gates, and posterior checks; the key models (applications, engagement ladder, winter replies, both pooling ladders) pass cleanly with zero divergences. The reply models at summer/pooled scale and the rare-event email fits trip the strictest gate (divergences in the campaign-effect "funnel") while their substantive coefficients are stable and well-mixed — flagged honestly in the results doc. The most important structural risks are attribution-related, not statistical: last-week enrichment has a known mechanical component, and channel comparisons measure *observability*, not persuasion.

## What was fixed along the way (affects past results)

- A silent data gate (`total_energy_burden`, ~8% winter coverage) had been shrinking winter frames to 8% of their size — the July-9 engagement-ladder fit is superseded by this session's refit.
- Winter models previously mixed collinear month/county/campaign effects (each winter campaign is one month + one county) — now corrected to campaign-only effects.
- GPU sampling was silently broken by a CUDA library conflict — fixed and documented (`scripts/gpu_env_tool.sh`).
