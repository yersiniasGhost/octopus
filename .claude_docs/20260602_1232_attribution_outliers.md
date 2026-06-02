# Campaign Attribution Outliers — for click-data ingestion review

**Date:** 2026-06-02
**Context:** Generated while running `scripts/attribute_click_conversions_tool.py` (lag 7d, click-only) to backfill `attribution.likely_campaigns` on converted applications. These are the applications the click-based rule could **not** attribute. Flagged here because several show a plausible campaign touch that is only a *receipt* (no click) — which may indicate **missing/under-ingested click data** rather than a genuine non-engaged conversion. Re-check after the click-ingestion audit.

## Summary
| Bucket | Count | Meaning |
|---|---|---|
| No click signal in 7d window | 31 | Application has a nearby send but no *click* within 7 days before the app (received-only, or click landed after the app, or click >7d away) |
| No matched participant | 15 | Application has no `participant_match.participant_oid`, so no exposures to read |
| Same-day receipt (deferred) | 4 | Same-day delivery, no click — attributable at conf 0.70 if `--include-receipt` is later enabled |

Applications carrying a real UTM (25) are intentionally excluded — they belong to a separate `utm_direct` rule, not behavioral attribution.

## 1. No click signal within 7-day window (31)
`nearest` = closest dated exposure to the application (abs days); `CLICK`/`recv` = whether that touch was clicked. Rows marked **CLICK** clicked a campaign but *outside* the 7-day window (or the click post-dates the application) — prime candidates to re-check once click timestamps are validated.

| app | entry_date | participant | oid…6 | nearest exposure |
|----|------------|-------------|-------|------------------|
| 463 | 2026-01-26 | DIANNA TOLBERT | aeb882 | nearest 3d (2026-01-23) text_impact_winter_75 recv |
| 465 | 2026-01-27 | HALL, CHERYL K | aeb383 | nearest 4d (2026-01-23) text_impact_winter_75 recv |
| 466 | 2026-01-27 | MARRERO, MARIA J | aeaab1 | nearest 4d (2026-01-23) text_impact_winter_76 recv |
| 467 | 2026-01-27 | MARRERO, MARIA J | aeaab1 | nearest 4d (2026-01-23) text_impact_winter_76 recv |
| 469 | 2026-01-28 | BRITTANY PRICE | aeb4c3 | nearest 5d (2026-01-23) text_impact_winter_75 recv |
| 470 | 2026-01-29 | CYDNE KNOX | aeb5ec | nearest 6d (2026-01-23) text_impact_winter_75 recv |
| 471 | 2026-02-02 | TERRIE WEBB | aec519 | nearest 10d (2026-01-23) text_impact_winter_76 recv |
| 516 | 2026-02-05 | HANNAH POWELL | aeb6a7 | nearest 1d (2026-02-04) text_impact_wcp_77 recv |
| 527 | 2026-02-06 | BETHANY HATHEWAY | aebd39 | nearest 2d (2026-02-04) text_impact_wcp_77 recv |
| 528 | 2026-02-07 | YENSI PENA | aebc2a | nearest 3d (2026-02-04) text_impact_wcp_77 recv |
| 529 | 2026-02-07 | BECKY BOWMAN | aec5cd | nearest 3d (2026-02-04) text_impact_wcp_78 recv |
| 530 | 2026-02-09 | MARY PATTON | aec39d | nearest 5d (2026-02-04) text_impact_wcp_78 recv |
| 535 | 2026-02-12 | LEANN LAWSON | aeb6d7 | nearest 8d (2026-02-04) text_impact_wcp_77 **CLICK** |
| 536 | 2026-02-12 | CHAD J SHEPHERD | aeca15 | nearest 8d (2026-02-04) text_impact_wcp_78 **CLICK** |
| 537 | 2026-02-13 | BETHANY HATHEWAY | aebd39 | nearest 9d (2026-02-04) text_impact_wcp_77 recv |
| 538 | 2026-02-15 | LAWSON, KATHLEEN M | aeab31 | nearest 11d (2026-02-04) text_impact_wcp_77 recv |
| 539 | 2026-02-17 | JACQUELINE OSBORNE | aec197 | nearest 13d (2026-02-04) text_impact_wcp_78 recv |
| 540 | 2026-02-21 | LORETTA GORE | aebf11 | nearest 29d (2026-01-23) text_impact_winter_75 **CLICK** |
| 541 | 2026-02-23 | DURGA CHAPAGAI | aec3be | nearest 19d (2026-02-04) text_impact_wcp_78 recv |
| 542 | 2026-02-23 | KERSHNER, ED | aeb409 | nearest 19d (2026-02-04) text_impact_wcp_77 recv |
| 574 | 2026-03-09 | MARGARITA STEWART | aec3f2 | nearest 10d (2026-02-27) text_impact_cold_80 **CLICK** |
| 575 | 2026-03-09 | DURGA CHAPAGAI | aec3be | nearest 14d (2026-03-23) EGE_WinterCrisis_2026 recv |
| 576 | 2026-03-10 | KEVIN STEWART | aeb28d | nearest 11d (2026-02-27) text_impact_cold_79 recv |
| 577 | 2026-03-10 | MARRERO, MARIA J | aeaab1 | nearest 13d (2026-03-23) EGE_WinterCrisis_2026 recv |
| 581 | 2026-03-15 | TERRIE WEBB | aec519 | nearest 8d (2026-03-23) EGE_WinterCrisis_2026 recv |
| 604 | 2026-03-24 | ALI, KURESHO S | aeaca2 | nearest 1d (2026-03-23) EGE_WinterCrisis_2026 recv |
| 607 | 2026-03-25 | ALETHA HARPER | aebdb0 | nearest 2d (2026-03-27) text_impact_endssoon_81 **CLICK** (click post-dates app) |
| 691 | 2026-04-06 | JOHANNA MARSHALL | aebee6 | nearest 14d (2026-03-23) EGE_WinterCrisis_2026 recv |
| 692 | 2026-04-06 | SANDRA ROCKHOLD | aec9eb | nearest 14d (2026-03-23) EGE_WinterCrisis_2026 recv |
| 693 | 2026-04-10 | ARNOLD CALHOUN | aeb227 | nearest 10d (2026-03-31) text_impact_lastday_83 recv |
| 694 | 2026-04-14 | FREDRICK WHITE | aeb613 | nearest 22d (2026-03-23) EGE_WinterCrisis_2026 recv |

**Patterns to investigate during click-ingestion audit:**
- **WCP Text77/78 (2026-02-04 send):** a cluster (#516, #527, #528, #529, #530) applied 1–5 days later showing only *receipt*. Given the same send produced 44 attributed Text77 clickers, these "received-only but applied" cases plausibly have **uningested clicks**.
- **`CLICK`-but-out-of-window (#535, #536, #540, #574):** clicked the campaign but >7 days before applying — confirm whether the long lag is real or whether `t_clicked_at` is mis-stamped (note: known issue — Text75–84 click ingestion stamped `t_clicked_at` at ingest time 2026-05-14, not true click time).
- **#607 ALETHA HARPER:** click is dated *after* the application — impossible causally; almost certainly a click-timestamp ingestion artifact.

## 2. No matched participant (15)
These applications have no `participant_match.participant_oid`, so no exposure history is available. All are landing-page (`reduceenergyburdenohio.com`) submissions. Worth re-running participant matching before attribution.

| app | entry_date | source_url |
|----|------------|-----------|
| 396 | 2026-01-23 | reduceenergyburdenohio.com |
| 413 | 2026-01-23 | reduceenergyburdenohio.com |
| 421 | 2026-01-23 | reduceenergyburdenohio.com |
| 468 | 2026-01-28 | reduceenergyburdenohio.com |
| 493 | 2026-02-04 | reduceenergyburdenohio.com |
| 501 | 2026-02-04 | reduceenergyburdenohio.com |
| 504 | 2026-02-04 | reduceenergyburdenohio.com |
| 598 | 2026-03-22 | reduceenergyburdenohio.com |
| 600 | 2026-03-23 | reduceenergyburdenohio.com |
| 602 | 2026-03-23 | reduceenergyburdenohio.com |
| 603 | 2026-03-23 | reduceenergyburdenohio.com |
| 605 | 2026-03-24 | reduceenergyburdenohio.com |
| 606 | 2026-03-24 | reduceenergyburdenohio.com |
| 608 | 2026-03-25 | reduceenergyburdenohio.com |
| 626 | 2026-03-27 | reduceenergyburdenohio.com |

## 3. Same-day receipt candidates (4) — deferred
Same-day delivery, no recorded click. Would attribute at conf 0.70 via `--include-receipt`. Deferred pending click-data review (a missing click would upgrade these to 0.95 same-day-click).

| app | entry_date | participant | oid…6 | would-link |
|----|------------|-------------|-------|-----------|
| 559 | 2026-02-27 | INGER A COOPER | aeb927 | text_impact_cold_79 |
| 565 | 2026-02-27 | ELIZABETH MARTIN | aeb5b6 | text_impact_cold_79 |
| 601 | 2026-03-23 | SANDRA ROCKHOLD | aec9eb | EGE_WinterCrisis_2026 (5187fe36…) |
| 675 | 2026-03-31 | TERESA THORPE | aeb89c | text_impact_lastday_83 |

## Re-check procedure (after click ingestion fix)
1. Re-run `scripts/attribute_click_conversions_tool.py` (dry-run) — newly-ingested clicks should move section-1 "recv" rows into the attributable set automatically (idempotent; won't touch already-linked apps).
2. For section-2 (no match), re-run participant matching, then re-run attribution.
3. Decide on `--include-receipt` for the residual section-3 cases.
