# What Each Model Found — In Plain Language

**Date:** 2026-07-17 · Companion to the [statistical results](20260716_2345_bayesian_campaign_models_results.md) and [development notes](20260716_1920_bayesian_campaign_models_development.md). One section per model; the cross-model story lives in the synthesis artifact (d).

---

## F1 — "How different are campaigns from each other?" (click rates)

**Text messages (the 12 winter 2026 IMPACT campaigns):** Almost identical. Roughly 31 of every 100 text recipients click the link, and the busiest and quietest campaigns only range from about 29 to 33. Practical read: for texts, *which* campaign a message belongs to tells you very little — don't expect big wins from re-engineering text campaign content alone.

**Emails (63 campaigns, summer 2025):** Very different from each other. The average email gets about 2 clicks per 1,000 recipients, but campaigns routinely land anywhere from 1 to 3+ per 1,000 — a threefold spread. Practical read: something about individual email campaigns genuinely matters. The catch (see F8): it isn't the message themes or the weather we have on record.

*Technical note:* both conclusions come from a "pooling ladder" — three models that assume campaigns are identical / unrelated / partially related. The partially-related model wins both times, which is what justifies using campaign effects in every other model.

## F7 — "What predicts whether a text recipient clicks?"

We compared five versions of the model, each adding a block of predictors (household demographics; send-window weather; message themes), and scored each on its ability to predict clicks for people it hasn't seen.

**Only demographics helped.** Households with lower estimated income and smaller households click a bit more often, and those effects are measured precisely. Weather and message themes added *nothing* — the model predicts clicks just as well without them. Even the demographic effects are modest: they shift a ~31% click rate by roughly ±1–2 percentage points per step, not tens of points.

**Practical read:** among people who receive a program text, clicking is close to a coin-flip weighted by need — not something the message wording or a cold snap visibly changes. (Caveat: all 12 campaigns ran Jan–Mar 2026 in single counties, so weather and themes only vary *between* 12 campaigns — a weak lens. A deliberately varied test — same content across different weeks, or A/B themes within a wave — would sharpen this a lot.)

## F8 — "What predicts whether an email recipient clicks?"

Email clicks are rare (about 2 per 1,000), so we asked the question at the campaign level: can weather or themes explain why some of the 63 campaigns got triple the clicks of others?

**No measured factor explains the spread.** Models with weather, themes, both, or neither all predict campaign click counts equally well. The individual-level model adds two suggestive signals: sends during *cooler* summer windows did somewhat better, and lower-income recipients clicked somewhat more — but the campaign-to-campaign differences remain mostly unexplained. Candidate explanations we can't test with current data: subject lines, send time-of-day, list freshness.

**Practical read:** email campaign performance varies a lot for reasons not in our coded data. If email matters going forward, capture subject-line and send-time metadata — and add UTM tracking so email conversions become visible at all.

## F2 — "Do people reply to texts more in certain weather?" (by season)

We fit the reply model three ways: winter 2026 only, summer 2025 only, and all campaigns pooled.

**Weather doesn't move replies in any season.** Temperature and extreme-hours effects are indistinguishable from zero every time. What *does* stand out:

- **Campaigns differ wildly in reply rates** — far more than for clicks. Some campaigns generate essentially zero replies (including every March 2026 send, which looks like a data-ingestion gap rather than behavior — flagged for follow-up).
- **Higher-income households reply more** (clearest in winter). That's the opposite of clicks and applications — see the synthesis for what we make of it.

*Honest label:* the summer and pooled fits technically fail our strictest quality gate (the sampler struggles with the extreme campaign-to-campaign spread), but the substantive conclusions are stable across all three fits, including the winter one that passes cleanly.

## F5 — "Does a message theme lift engagement overall?" (none → clicked → replied)

Treating engagement as a ladder (no engagement < clicked < replied) on the winter cohort, now with the freshly coded message themes: **no theme reliably moves people up the ladder**; a couple lean slightly negative. Lower income and smaller households nudge engagement up slightly. This refit replaces a July-9 version that unknowingly used only 8% of the cohort (a data-coverage bug fixed this session) and couldn't see themes at all (they weren't coded yet).

**Opt-outs (companion model):** themes don't drive opt-outs either — and *higher*-income households opt out more, the same direction as replies. Replying STOP is still replying: income predicts "texting back" in general, not positivity.

## F6 — "What precedes an actual application?" (refit with themes)

The July-13 finding stands, now strengthened: **timing is everything, content is nothing we can detect.**

- A send landing in the **last week of a participant's campaign wave** is associated with ~80× higher odds of being the send that precedes an application (with a known mechanical component — read as "strongly enriched," not literally 80×).
- Being the **first send of a wave** (~6×) or the **first contact ever** (~4×) also helps — novelty matters.
- **Colder send windows** help (2.5–3.7× per SD of heating-degree-days), surviving adjustment for campaign identity.
- **Lower-income households apply more** (~20% higher odds per $22k lower income) — the program is reaching its target population.
- **All six message themes: no detectable effect** on applications, now testable for the first time thanks to the July-15 theme backfill. If anything, "urgency/deadline" and "personalized/qualified" lean negative.

Both versions of the model (with and without campaign-level pooling) agree.

---

### One-paragraph caveat that applies everywhere

Clicks are only tracked for the 12 winter-2026 IMPACT text campaigns, applications are only attributable within that same cohort, and email conversions are structurally invisible (no UTM tracking). Every conclusion above is conditional on where the lights are on. The three highest-value data investments remain: email UTM parameters, subject-line/send-time metadata, and deliberately varied (ideally randomized) message themes within a wave.
