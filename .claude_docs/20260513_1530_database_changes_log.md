# Database Changes — Running Log

**Started:** 2026-05-13 15:30 PDT
**Database:** `empower_development` on `localhost:27017`
**Base schema reference:** [`20260513_1508_database_schema.md`](20260513_1508_database_schema.md)

This document tracks every schema/data change made to `empower_development` from 2026-05-13 onward, so consumers of this database can be updated in lockstep.

---

## How to read this log

Each entry below describes one logical change (one PR-equivalent unit of work), with:

- **Date / change ID** — when and a stable identifier
- **What changed** — collection(s), field(s), index(es) added/removed/renamed/repurposed
- **Why** — the motivating reason
- **Backwards compatibility** — what still works vs what breaks
- **Migration applied** — script name + counts of docs updated
- **Consumer impact** — which external consumers (see registry below) need attention, and what specifically

**Add new entries at the top of the log** (reverse chronological).

---

## Known external consumers of `empower_development`

Anyone changing this database should sanity-check these consumers before merging.

### 1. `oc-empower` agent tool — `/home/yersinia/devel/oc-empower/workspace-campaign-participants/db/`

**What it is:** A **read-only** MongoDB explorer CLI for an OpenClaw AI agent. Used to answer ad-hoc questions about campaigns, participants, exposures, and county data.

**Files:**
- `explore.py` — argparse CLI entry point
- `mongo_ops.py` — all DB operations
- `serializer.py` — BSON-to-JSON helpers

**Schema couplings (the only things that can break it):**

| Coupling | Where | Breaks if… |
|---|---|---|
| Allowed DBs hardcoded | `mongo_ops.py:13` — `ALLOWED_DBS = ("campaign_data", "empower_development")` | The `empower_development` DB is renamed. (Note: `campaign_data` is already a dead reference — removing it from MongoDB is harmless.) |
| `<County>CountyDemographic` collection-name pattern | `mongo_ops.py:257` (`search_by_name`) and `mongo_ops.py:392` (`get_counties`) | We rename/drop any `*CountyDemographic` collection, or change the suffix convention. |
| Demographic field names projected | `mongo_ops.py:263` — `customer_name`, `address`, `service_city`, `email`, `mobile`, `parcel_id` | We rename any of these six fields in `<County>CountyDemographic` collections. The tool would still run but return blanks for renamed fields. |

**What is *not* coupled** (i.e., safe to change without touching this tool):
- All fields on `participants`, `campaigns`, `exposures`, `applications`, `applicants`
- The `unified_status` value set
- `text_engagement` / `email_engagement` sub-document shapes
- New collections, new indexes, new fields anywhere
- Anything in `<County>CountyResidential`, `<County>ElectricalDB`, `<County>GasDB`, `<County>ThermalLoads`, `<County>MultiTenant`

The tool inspects documents generically (`schema`, `sample`, `find`, `aggregate`, `top-values`, `describe`) — adding fields or new statuses is fully transparent to it. **Most of the changes we're about to make won't affect this consumer at all.**

### 2. Octopus itself — `/home/yersinia/devel/octopus/`

Pydantic models in `src/models/` are the authoritative shape. Ingest/analysis scripts in `scripts/` and `src/` depend on them. Every change here MUST update the corresponding model.

---

## Change template (copy this for each new entry)

```markdown
### YYYY-MM-DD HH:MM — change-id

**Type:** schema | data | index | migration

**Collection(s):** `name1`, `name2`

**Summary:** One sentence describing the change.

**Detail:**
- Field/collection/index added/changed/removed
- Before/after if applicable

**Rationale:** Why we did it.

**Migration:**
- Script: `scripts/<name>.py`
- Docs updated: N inserted / M modified / K deleted
- Reversible? yes/no (and how)

**Backwards compatibility:**
- ✅ Still works: …
- ⚠ Breaks: …

**Consumer impact:**
- **oc-empower tool:** no impact / specific change needed (file:line)
- **Octopus Pydantic models:** updated in `src/models/<file>.py:line` / no change
- **Octopus ingest scripts:** scripts touched
- **Other:** …

**Verification:** how I confirmed the change went in cleanly (sample query, count, etc.)
```

---

## Changes

*(reverse chronological — newest at the top)*

### 2026-05-13 21:05 — backfill-text-campaign-message-body

**Type:** data (field backfill)

**Collection(s):** `campaigns` (86 docs updated)

**Summary:** Populated `campaigns.message_body` with the actual SMS template for every text campaign that had a usable source. Prior to this, 88 of 89 text campaigns held a meaningless placeholder of the form `"<slot> message campaign"` (e.g., `"Prequalified message campaign"`) — a label, not the SMS body — and the Text75-84 IMPACT-drop campaigns held `null`. The detail page now shows the real message that was sent.

**Sources:**

- **74 campaigns** (Text1-Text74): rendered SMS body from `data/campaign_texting/Empower_Saves_Texts_All.csv`, joined to `data/campaign_texting/Empower_Saves_Texts_All_stats.csv` on the `action` ↔ `Contacted in Project` column. Per-recipient tokens (address, first name, dollar amounts) normalized to `{ADDRESS}`, `{FIRSTNAME}`, `{AMOUNT}` placeholders before picking the modal form per campaign.
- **12 campaigns** (Text75-84, WCP Text2): campaign-brief template from `data/campaign_texting/text_content.txt`, matched to the campaign by slot keyword (`LastDay`→Final Day, `EndsSoon`→Time running out, `Cold`→Stay Cool, `Winter`→Stay Cool, `WCP`→Summer Crisis Program).
- **3 campaigns** skipped (no source matched): `Text15_Improvements_NA`, `Text17_Improved_MVCAP`, `OHCAC_Summer_Crisis_SMS_20251104` — already had usable content or no source available.

**Update gating:** Only overwrites null/empty or the legacy `"<slot> message campaign"` placeholder. Real existing content is left alone unless `--force`.

**Effect on app:** `/dashboard/text/<campaign_id>` now shows a "Message Sent" card above Campaign Information with the rendered template body. Personalization tokens remain visible as `{ADDRESS}`, `{FIRSTNAME}`, `<VD_FirstName>`, etc.

**Tool:** `scripts/backfill_text_campaign_message_body_tool.py` — idempotent, dry-run by default, `--apply` to write, `--force` to overwrite real bodies, `--verbose` for per-campaign output.

---

### 2026-05-13 19:35 — backfill-participant-customer-name

**Type:** data (denormalization backfill)

**Collection(s):** `participants` (6,872 docs updated)

**Summary:** Filled `participants.demographics.customer_name` from the per-county `<County>CountyDemographic` source collections, joined via `linkage.parcel_id`. The participant collection is a denormalized snapshot of the county demographics, but the original import left customer_name null for the majority of participants (e.g., only ~8% populated for Text81's audience). The names existed all along in `FranklinCountyDemographic` — they just hadn't been copied across.

**Counts:**

- Scanned: 6,890 participants with `customer_name` null/empty AND a `linkage.parcel_id`
- Matched in county DB: 6,872 (99.7% of candidates)
- Updated: 6,872
- 18 unmatched (parcel not present in county demographic, or `county_key` doesn't normalize cleanly)

All updates were in Franklin county; other counties had no nameless-but-parcel-linked participants.

**Effect on app:** Text-campaign detail page (`/dashboard/text/<campaign_id>`) shows participant names on virtually every row instead of just the few that had names pre-backfill.

**Tool:** `scripts/backfill_participant_customer_name_tool.py` — idempotent, dry-run by default, supports `--county <name>` for targeted runs.

---

### 2026-05-13 18:50 — fix4-apply-cross-file-clicks

**Type:** data (mass update_many across 6 campaigns) — Decision 3 reversal for remediation

**Collection(s):** `exposures` (38 docs updated)

**Summary:** Fix #4 from the Text75-84 follow-up list. Applied cross-file click evidence to the 6 owning campaigns where Stage 4b audit revealed 103 (phone × cross-file-slug) sightings without a matching click record. After per-phone deduplication, 38 unique exposures were updated. **Effectively reverses Decision 3** (the original "stay in lane" rule) for the remediation pass, after the audit confirmed the cross-file signal is real — not snapshot-timing noise.

**Per-campaign promotions (received → clicked, plus click flag + clicked_at set to write-time):**

| Campaign | Promotions |
|---|---:|
| text_impact_winter_75   |  7 |
| text_impact_winter_76   |  8 |
| text_impact_wcp_77      | 13 |
| text_impact_wcp_78      |  3 |
| text_impact_cold_79     |  3 |
| text_impact_cold_80     |  4 |
| text_impact_endssoon_81 |  0 (already 100% covered by Stage 4) |
| text_impact_endssoon_82 |  0 (already 100% covered) |
| text_impact_lastday_83  |  0 (already 100% covered) |
| text_impact_lastday_84  |  0 (already 100% covered) |
| **TOTAL**               | **38** |

**Tool:** `scripts/apply_cross_file_text_clicks_tool.py` (default dry-run; `--apply`). Aggregates click_<slug> tokens from all 10 files' Tags columns, dedups by (slug, phone), looks up exposures by `(owning_campaign_id, contact_snapshot.phone)`, applies same precedence as Stage 4 (received → clicked; engaged/opted_out → audit only; undeliverable → skip). Idempotent.

**Rationale:**
- Stage 4b's 103 flagged discrepancies (0.48% of cross-file sightings) were initially thought to be vendor snapshot-timing noise. Investigation showed they're real clicks that the originating campaign's own export missed (likely captured late by the vendor in subsequent exports). Stage 4's "stay in lane" policy meant we left those signals on the floor.
- Fix #4 captures them by giving each owning campaign credit for any click_<slug> token found anywhere — same per-doc precedence rules apply.
- Side benefit: re-running Stage 4b audit shows **0 discrepancies** post-fix.

**Migration:**
- Reversible: undo by reversing the 38 status promotions and unsetting the click flag, but harder without the apply timestamp. Full rollback via `mongorestore` from `backups/empower_development_20260513_174120/` followed by re-running Stage 0-4 of the chain.
- Idempotent on re-run (confirmed: second --apply was a no-op).

**Backwards compatibility:**
- ✅ Existing readers see 38 more `unified_status=clicked` docs across 6 of the 10 Text75-84 campaigns.
- ✅ Audit re-run confirms 0 discrepancies remain.

**Consumer impact:**
- **oc-empower tool**: no impact.
- **Octopus**: downstream click-based analyses now have 38 additional click signals.

**Verification:**
- `apply_cross_file_text_clicks_tool.py` 2nd run (post-apply): 0 ops needed, idempotent.
- `audit_text75_84_cross_file_clicks_tool.py` post-fix: "✅ No discrepancies — every cross-file click token is corroborated."

---

### 2026-05-13 18:45 — fix1-backfill-wcp-text2-clicked-flag

**Type:** data (mass update_many on 2 campaigns)

**Collection(s):** `exposures` (2,111 docs updated)

**Summary:** Fix #1 from the Text75-84 follow-up list. Backfilled `text_engagement.clicked = true` on the 2,111 docs in the older WCP Text2 Section 1/2 campaigns (Jan 2026) that had `unified_status: "clicked"` but no underlying nested-field flag. `clicked_at` intentionally left as-is (original click timestamps unknown; better than fabricating them).

**Affected campaigns:**
- `bf86a179-5c5e-469f-95ec-14a679bd2434` — WCP Text2 Section 1 (Jan 2026): 1,066 docs
- `afb3d74b-aaa5-4be2-9dbd-4de1b5def74d` — WCP Text2 Section 2 (Jan 2026): 1,045 docs

**Operation:**
```javascript
db.exposures.updateMany(
  {campaign_id: {$in: ['bf86a179-...', 'afb3d74b-...']},
   unified_status: 'clicked',
   'text_engagement.clicked': {$ne: true}},
  {$set: {'text_engagement.clicked': true}}
)
// matched=2111 modified=2111  (0.02s)
```

**Tool:** `scripts/backfill_wcp_text2_clicked_flag_tool.py` (default dry-run; `--apply`). Idempotent.

**Rationale:**
- The two WCP Text2 campaigns predate the May-2026 `mark_clicked_from_csv_tool.py` work that wrote the now-migrated legacy `text_clicked: True` field. Their `unified_status: "clicked"` was apparently set imperatively at the original ingest time without populating the channel-specific flag.
- After today's `compute_unified_status` rewrite (Stage 0), calling that method on these docs would downgrade them from "clicked" to "received" (since the underlying flag is null). Setting the flag locks in their status under the new precedence ladder.

**Migration:**
- Reversible: `db.exposures.updateMany({campaign_id: {$in: [bf86, afb3]}}, {$unset: {'text_engagement.clicked': ''}})` — but only safe if we know the exact set; the post-state has 1,066 + 1,045 docs with flag=true, exactly matching the unified_status=clicked count.
- Idempotent on re-run (confirmed by `$ne: true` filter).

**Backwards compatibility:**
- ✅ No status changes (1,066 + 1,045 remain `clicked` as before).
- ✅ `compute_unified_status` now produces the same `clicked` value when called on these docs.
- ✅ Nested-field views and unified-status views are now consistent.

**Consumer impact:**
- **oc-empower tool**: no impact.
- **Octopus**: downstream analyses on `text_engagement.clicked=True` now include these 2,111 historical clicks (were previously missing).

**Verification:**
- Post-state: bf86 has status=clicked=1066, flag=True=1066. afb3 has status=clicked=1045, flag=True=1045. Both pairs match.

---

### 2026-05-13 18:32 — text75-84-stage4b-cross-file-audit

**Type:** investigation only (no DB writes)

**Collection(s):** `exposures` (read-only scan)

**Summary:** Stage 4b cross-file coverage audit per Decision 3. For each of the 10 RumbleUp xlsx files, scanned the Tags column for `click_<slug>` tokens belonging to OTHER campaigns and verified the owning campaign has matching `text_engagement.clicked=true` exposures. Result: 21,358 cross-file sightings total; 103 unique phone+slug discrepancies (0.48%); 18 file/slug pairs with at least one mismatch. Per Decision 3, no auto-fix performed — report-only.

**Audit findings:**
- 4 file/slug combinations had perfect coverage: `pRJQ` in Text81/Text82 (Text83/84 own the slug), `iXJM` in Text83 (Text81 owns), `Ytxw` in Text84 (Text82 owns).
- 18 other combinations show small numbers of phones (1-13 per pair) where one file's Tags column claims a click but the owning campaign's exposure doesn't have the click flag set.
- Common pattern: certain phones (e.g. `6142050504`, `6142046218`, `6145814643`) appear across multiple discrepancies — likely contacts who clicked late in their journey, after the originating campaign's vendor export but before later campaigns' exports.

**Likely explanation (not investigated further):** RumbleUp's Conversations export captures the click state at the time of export. A contact who clicks the original Text77 link a week after Text77's export but before Text79's export would show `click_sMcs` in Text79's Tags but not in Text77's. The 103 phones flagged here mostly fall into this category. Not a data bug; just a snapshot-timing artifact.

**Detail:** Full per-file/per-slug audit output written to `.claude_docs/20260513_text75_84_cross_file_audit.txt` (150 lines, includes all 103 phones with `--verbose-missing` flag).

**Tool:** `scripts/audit_text75_84_cross_file_clicks_tool.py` (read-only, no apply flag).

**Consumer impact:** None (read-only).

**Verification:** Per-file owned-slug coverage (each file's own slug → its own campaign) was 100% in every case during Stage 4 — confirmed by the apply tool's 0 missing phones. The 103 cross-file discrepancies are a secondary signal that won't affect downstream analysis of canonical per-campaign click data.

**Final state across the 10 affected campaigns** (after Stage 0+3+4):

| campaign_id | total exposures | unified_status=clicked | text_engagement.clicked=true |
|---|---:|---:|---:|
| text_impact_winter_75   | 3,707 | 1,051 | 1,053 |
| text_impact_winter_76   | 3,711 | 1,013 | 1,020 |
| text_impact_wcp_77      | 3,170 | 1,005 | 1,008 |
| text_impact_wcp_78      | 3,210 |   989 |   991 |
| text_impact_cold_79     | 3,059 |   952 |   956 |
| text_impact_cold_80     | 3,077 | 1,005 | 1,011 |
| text_impact_endssoon_81 | 2,977 |   955 |   955 |
| text_impact_endssoon_82 | 2,974 |   961 |   961 |
| text_impact_lastday_83  | 2,908 |   944 |   945 |
| text_impact_lastday_84  | 2,906 |   976 |   978 |
| **TOTAL**               | **31,699** | **9,851** | **9,878** |

Difference column ("text_engagement.clicked - status=clicked" = 27): the 27 audit-only docs where the contact has `engaged` or `opted_out` status but also clicked the link (terminal status preserved; click flag set for analytics).

**Database totals (post-Stage-4):**
- Total exposures: 344,069
- Total `unified_status=clicked`: 11,962 (was 5,250 pre-Stage-3; +6,712 net)
- Total `text_engagement.clicked=true`: 9,878 (was 0 pre-Stage-0 except for the now-migrated 1,134)
- Total legacy `text_clicked` field: **0** (was 17,901)

---

### 2026-05-13 18:25 — text75-84-stage4-apply-clicks

**Type:** data (mass update_many across 10 campaigns)

**Collection(s):** `exposures` (9,878 docs touched: 9,851 status-promoted + 27 audit-only)

**Summary:** Stage 4 of Text75-84 ingest. Applied `click_<slug>` tag matches from each of the 10 vendor xlsx files to the corresponding campaign's exposures, per Decision 3 (strictly stay-in-lane — only this file's own slug is processed). 100% phone-coverage match (every file-side clicker has a corresponding DB exposure). Follows the precedence ladder from `Exposure.compute_unified_status` and `mark_clicked_from_csv_tool.py`: received/no_engagement → promote to clicked; engaged/opted_out → audit-only (set text_engagement.clicked but keep status); undeliverable → skip.

**Per-file outcome:**

| File | Clickers | Exposures found | Promoted (→ clicked) | Audit-only (engaged/opted_out kept) | Skipped (undel.) | Phones missing |
|---|---:|---:|---:|---:|---:|---:|
| Text75 (Winter S1) | 1,053 | 1,053 | 1,051 | 2 | 0 | 0 |
| Text76 (Winter S2) | 1,020 | 1,020 | 1,013 | 7 | 0 | 0 |
| Text77 (WCP S1)    | 1,008 | 1,008 | 1,005 | 3 | 0 | 0 |
| Text78 (WCP S2)    |   991 |   991 |   989 | 2 | 0 | 0 |
| Text79 (Cold S1)   |   956 |   956 |   952 | 4 | 0 | 0 |
| Text80 (Cold S2)   | 1,011 | 1,011 | 1,005 | 6 | 0 | 0 |
| Text81 (EndsSoon S1)| 955 |   955 |   955 | 0 | 0 | 0 |
| Text82 (EndsSoon S2)| 961 |   961 |   961 | 0 | 0 | 0 |
| Text83 (LastDay S1) | 945 |   945 |   944 | 1 | 0 | 0 |
| Text84 (LastDay S2) | 978 |   978 |   976 | 2 | 0 | 0 |
| **TOTAL** | **9,878** | **9,878** | **9,851** | **27** | **0** | **0** |

**Per-doc mutation:**
- Promote case: `$set: {unified_status: 'clicked', text_engagement.clicked: true, text_engagement.clicked_at: <utc-now>}`
- Audit case (status was engaged or opted_out): `$set: {text_engagement.clicked: true, text_engagement.clicked_at: <utc-now>}`  (no status change — engaged/opted_out beat clicked)

**Net change in `unified_status: "clicked"` count** (in scope: text_impact_winter_75/76, text_impact_wcp_77/78, text_impact_cold_79/80, text_impact_endssoon_81/82, text_impact_lastday_83/84):
  - Before this stage (after Stage 3): 0
  - After this stage: 9,851

**Net change in `text_engagement.clicked: true` count** (same scope):
  - Before this stage (after Stage 0+3): 0
  - After this stage: 9,878 (= 9,851 promoted + 27 audit-only)

**Reads:** all 3 tag columns of each file's Conversations sheet ('Msg Tags', 'Contact Tags', 'Tags' — the third is where `click_<slug>` tokens live; the existing impact-cold helper misses it; this tool reads it explicitly).

**Lookup keys:** matched by `(campaign_id, contact_snapshot.phone)` rather than `(campaign_id, participant_id)`. This is the correct path for dual-phone-contacts where multiple phones fold to one participant: each phone's exposure gets its own click flag, not just the canonical one.

**Tool:** `scripts/apply_text75_84_clicks_tool.py` (default dry-run; `--apply`; `--files key1,key2` filter). Idempotent: re-running finds the already-clicked exposures and counts them in the `idemp` column (no writes).

**Rationale:**
- Resolves the final stage of the multi-stage Text75-84 ingest plan. Surfaces every click signal from each file's canonical Conversations sheet without double-attribution from cross-contamination tags.
- 100% phone coverage validates the Stage 3 ingest — every file-side clicker has a matching DB exposure to update.
- The 27 audit-only cases are interesting: a contact who BOTH replied (engaged) or opted out AND clicked the link. We preserve the higher-precedence status but record the click for analytics.

**Migration:**
- Reversible: `db.exposures.updateMany({unified_status: 'clicked', 'text_engagement.clicked': true, 'text_engagement.clicked_at': {$gte: <approx 18:25 UTC>}}, {$set: {unified_status: 'received'}, $unset: {'text_engagement.clicked': '', 'text_engagement.clicked_at': ''}})` would undo the promote cases. The audit cases are harder to undo without backup since they only changed a sub-field. Full rollback via `mongorestore` from `backups/empower_development_20260513_174120/`.
- Idempotent on re-run.

**Backwards compatibility:**
- ✅ Existing analytical queries reading `unified_status: "clicked"` now see 9,851 more docs in the 10 affected campaigns. This is the intended outcome.
- ✅ Pydantic readers validate without changes.
- ⚠ The 2 unknown WCP Text2 (Jan 2026) campaigns still carry their pre-existing 2,111 `unified_status: clicked` docs that have no `text_engagement.clicked=true` underlying signal. Same caveat as previous entries — separate cleanup if/when desired.

**Consumer impact:**
- **oc-empower tool**: no impact (generic explorer).
- **Octopus**: ready for Stage 4b cross-file coverage audit. Per Decision 3, that audit is report-only; no further writes expected.

**Verification:**
- Per-file counts match brief expectations (1,053 / 1,020 / 1,008 / 991 / 956 / 1,011 / 955 / 961 / 945 / 978 = 9,878).
- 0 phones in any file lacking a matching exposure — confirms Stage 3 ingest captured every contact.
- 0 undeliverable skips means every clicker had a delivered message — sensible (you can't click a link you didn't receive).

---

### 2026-05-13 18:18 — text75-84-stage3-wipe-create-reset

**Type:** data (massive) + schema-adjacent (no field changes)

**Collection(s):** `exposures` (-7,641 wiped, +13,798 inserted, 1,134 status-reset), `campaigns` (-2, +4 = net +2), `participants` (~14K source_campaigns updates, 268 opt-outs flagged)

**Summary:** Stage 3 of Text75-84 ingest. Wiped stale Text75/76 data ingested from the now-superseded `*_COLORCODED.xlsx` files; created fresh ingests from the current `data/campaign-updated-20260512/` versions. Created new campaigns for Text77/78 (previously not in DB). Reset Text83's 1,134 imperative click promotions back to `received` (Stage 4 will re-apply 945 from the new file, net effect after Stage 4: -189 clicked).

**Detail per file:**
- **Text75 (Winter S1)**: deleted campaign UUID `761dc8cf-b8d6-43c4-b76e-d6d6cdc99d6e` (1 doc) + its 3,820 exposures. Created `text_impact_winter_75` + 3,707 fresh exposures (3,710 contacts, 3 testers skipped). Engagement dist: 3,106 received / 528 undeliverable / 7 negative_response / 66 opted_out. 66 opt-outs flagged with `do_not_contact: true`.
- **Text76 (Winter S2)**: deleted `1fae2148-a61a-4cf7-ab16-6873db90838c` (1 doc) + 3,821 exposures. Created `text_impact_winter_76` + 3,711 fresh exposures. Engagement: 3,091 received / 521 undel / 12 neg_resp / 87 opted_out. 87 opt-outs flagged.
- **Text77 (WCP S1)**: created `text_impact_wcp_77` (new) + 3,170 exposures. Engagement: 2,994 received / 132 undel / 6 neg_resp / 38 opted_out. 38 opt-outs flagged.
- **Text78 (WCP S2)**: created `text_impact_wcp_78` (new) + 3,210 exposures. Engagement: 2,977 received / 151 undel / 5 neg_resp / 77 opted_out. 77 opt-outs flagged.
- **Text83 (LastDay S1)**: `update_many({campaign_id: 'text_impact_lastday_83', unified_status: 'clicked'}, {$set: {unified_status: 'received'}, $unset: {'text_engagement.clicked': '', 'text_engagement.clicked_at': ''}})` — 1,134 matched, 1,134 modified.

**Key implementation notes:**
- All 13,798 new exposure docs carry BOTH `participant_id` (natural key) AND `participant_oid` (surrogate FK) at insert time. No follow-up backfill needed.
- New exposure docs use the proper nested `text_engagement.{delivered,replied,opted_out,failed,clicked,clicked_at}` shape; no top-level `text_clicked` is written.
- All 13,798 contacts matched an existing participant in `db.participants` — 0 new participants created. This matched Stage 1's heuristic ("participants with source_campaigns == [this campaign only]: 0" across all relevant campaigns).
- Reads the third tag column `'Tags'` (not just `'Msg Tags'`+`'Contact Tags'`) — see investigate_text75_84_state_tool.py for why the existing impact-cold helper misses it.
- Does NOT write any `participants.engagement_summary` fields (per 2026-05-13 16:30 drop).
- 3 testers per file consistently skipped (RumbleUp accounts with `tester`/`test_phone` tags).

**Source:** new RumbleUp xlsx files at `data/campaign-updated-20260512/` (10 files; this stage touched 5 of them).

**Tool:** `scripts/ingest_text75_84_exposures_tool.py` (default dry-run; `--apply` to write). Per-file action via `FILE_PLAN` table (`wipe`/`create`/`reset_clicks`). `--files text75,text83` flag to limit scope.

**Apply timing:** ~30s wallclock for all 5 files including index build, dry-run readouts, and inserts.

**Rationale:**
- Text75/76: stale source-file linkage (`*_COLORCODED.xlsx`) had +110/+107 surplus contacts vs the new updated file (3,820 vs 3,710). New file is canonical (per user decision 2026-05-13).
- Text77/78: never ingested. New campaigns created.
- Text83: existing 1,134 clicks (May 5 yellow-row CSV) exceed the new file's 945 click_pRJQ tokens by 189. New file canonical (per user decision); Stage 4 will re-apply the 945 in the new file.
- Text79/80/81/82/84: existing exposures already correct (delta -3 to -5 vs file, no click data yet). Stage 4 will add clicks; no exposure-level changes needed here.

**Migration:**
- Reversible: `mongorestore --gzip --db empower_development backups/empower_development_20260513_174120/empower_development` restores pre-Stage-0+ state.
- Idempotent? Partially: re-running `--apply` would re-wipe Text75/76 (delete + re-insert clean), no-op the Text77/78 upsert but DOUBLE the exposures (no pre-insert dedup), no-op the Text83 reset (no docs left with unified_status=clicked). For Text83 a second --apply is safe; for Text77/78 it would dup the exposures.

**Backwards compatibility:**
- ✅ Existing readers of `exposures` work unchanged — new docs match the established shape (now with the nested `text_engagement.clicked` field properly nullable).
- ✅ Existing readers of `campaigns` see the new IDs (`text_impact_winter_75`, etc.).
- ⚠ The two old UUID-keyed campaigns are gone. Any external references to `761dc8cf-...` or `1fae2148-...` will 404. Grep produced no references in either octopus or oc-empower.
- ⚠ `text_impact_lastday_83` campaign currently shows 0 clicked exposures until Stage 4 runs. Stage 4 will mark 945.

**Consumer impact:**
- **oc-empower tool**: no impact (generic explorer).
- **Octopus Pydantic models**: no model changes here (Stage 0 already added the click fields).
- **Octopus ingest scripts**: not touched. The legacy ingest_impact_* tools are still in place; they shouldn't be re-run against these 5 campaigns.

**Verification:**
- Per-file final exposure counts match the engagement_dist totals (3,707 / 3,711 / 3,170 / 3,210 / 2,908 for the 5 campaigns).
- Spot-check participant_oid coverage on the new exposures will be checked in the Stage 4 preamble.

---

### 2026-05-13 18:05 — skip-stage2-not-actual-duplicates

**Type:** investigation only (no DB change)

**Collection(s):** `exposures` (3 doc-pairs investigated, 0 modified)

**Summary:** Stage 2 of the Text75-84 ingest work planned to delete 3 duplicate `(participant_id, campaign_id)` exposure pairs flagged by Stage 1. Investigation revealed these are NOT duplicates — they're two distinct vendor sends (one per phone number) for the same contact (email `ggdavies.101@gmail.com`) whose two phones (`6145078892` @ 1392 BRYSON RD and `6145371470` @ 903 GARDEN RD) were both folded under `participant_id=6145078892` by the matcher. Deleting either record per pair would lose a real send event. **Decision: leave the 6 records in place; do not delete.**

**Detail:**
- 3 affected pairs (each has 2 docs):
  - `text_impact_cold_79` / `6145078892` — docs `69cf51dacb47428d810e8f2f` (phone 6145371470 / 903 GARDEN RD) and `69cf51dacb47428d810e95cb` (phone 6145078892 / 1392 BRYSON RD)
  - `text_impact_endssoon_81` / `6145078892` — docs `69efdbc730c02522aa00394d` and `69efdbc730c02522aa0041bf`
  - `text_impact_lastday_83` / `6145078892` — docs `69efdbca30c02522aa00508c` and `69efdbca30c02522aa0058fe`
- All 3 pairs have the same shape: identical `created_at` and `sent_at`, but `contact_snapshot.phone` and `contact_snapshot.address` differ. Two different actual SMS sends, two different phones.
- Phone `6145371470` does not exist as its own participant in `db.participants`. Only `6145078892` exists, keyed by email.
- Tool created but not run with `--apply`: `scripts/cleanup_duplicate_text_exposures_tool.py` (kept for future use if real dups are ever found).

**Rationale:** Compound `(participant_id, campaign_id)` index is non-unique precisely so we can preserve dual-phone send fidelity. Deleting on the "looks duplicate" surface signal would discard real engagement evidence. The right cleanup for this case (if any) is to split the conflated participant into two — out of scope here.

**Migration:** N/A (no writes).

**Backwards compatibility:** N/A.

**Consumer impact:** None.

**Follow-up flagged:** When the identity-merge cleanup happens (the 10 dual-keyed participants also deferred from this work), consider whether to also split conflated single-participant-with-two-phones cases like this one. ~1 known case so far.

**Verification:** Sample contact_snapshots inspected confirm the dual-phone hypothesis; participant lookup confirms `6145371470` isn't its own participant.

---

### 2026-05-13 17:52 — migrate-text-engagement-clicked

**Type:** schema (Pydantic field added) + data ($rename + $unset on 17,901 docs) + code (compute_unified_status rewrite) + backup

**Collection(s):** `exposures` (17,901 docs touched; 1,134 modified-with-data, 16,767 modified-cleanup-only)

**Summary:** Folded the legacy top-level `text_clicked` / `text_clicked_at` fields into the proper nested path `text_engagement.clicked` / `text_engagement.clicked_at`, mirroring the existing `email_engagement.clicked` shape. Updated `Exposure.compute_unified_status` text branch to recognize the new field with explicit precedence (opted_out > undeliverable > engaged > clicked > received > no_engagement). This is Stage 0 of the Text75–84 click-ingestion work.

**Detail:**
- **Backup:** Fresh mongodump at `backups/empower_development_20260513_174120/` (322 MB gzipped) taken before any writes. Restorable via `mongorestore --gzip --db empower_development <path>/empower_development`.
- **Pydantic update:** `src/models/campaign_data.py:247` — added `clicked: Optional[bool]` + `clicked_at: Optional[datetime]` to `TextEngagement`. Mirrors `EmailEngagement.clicked` exactly.
- **Logic update:** `src/models/campaign_data.py:505` — rewrote text branch of `compute_unified_status` with new precedence:
  - opted_out → OPTED_OUT (terminal)
  - failed → UNDELIVERABLE (terminal)
  - replied → ENGAGED
  - clicked → CLICKED *(new)*
  - read/delivered → RECEIVED
  - else → NO_ENGAGEMENT

  Note: this normalizes a pre-existing inconsistency. Old order put delivered/read above opted_out/failed, so a (delivered=True, opted_out=True) doc resolved to RECEIVED — wrong. The migration tool counted such drift-candidate docs and reported 0 in the current data (impact-cold tool sets delivered=False for opted_out, avoiding the issue). Future writers calling `compute_unified_status` get the corrected ladder.
- **Migration script:** `scripts/migrate_text_engagement_clicked_tool.py` (default dry-run, `--apply` to write). Two-pass design:
  ```
  Pass A (1,134 True docs):
    db.exposures.update_many({'text_clicked': True},
      [{'$set': {'text_engagement.clicked': '$text_clicked',
                 'text_engagement.clicked_at': '$text_clicked_at'}},
       {'$unset': ['text_clicked', 'text_clicked_at']}])
    → matched=1134 modified=1134 (0.18s)

  Pass B (16,767 False docs):
    db.exposures.update_many({'text_clicked': False},
      [{'$unset': ['text_clicked', 'text_clicked_at']}])
    → matched=16767 modified=16767 (0.24s)
  ```
- **Apply-run verification:**
  ```
  Remaining with legacy text_clicked field: 0    (was 17,901)
  Total with text_engagement.clicked=True: 1,134 (== source True count)
  Sample post-mig: text_engagement={'delivered': null, ..., 'clicked': True, 'clicked_at': 2026-05-05 22:23:33}
  ```
- **Source of legacy True docs:** `mark_clicked_from_csv_tool.py` run on 2026-05-05 against the Text83 yellow-row CSV. All 1,134 docs are in campaign `text_impact_lastday_83`.
- **Source of legacy False docs:** the `TAG_ENGAGEMENT['received'/'opted_out'/...]` default in `ingest_impact_cold_20260310_campaign_tool.py:53-65` and its 4 derivatives (winter / wcp / endssoon-lastday / leads) emit `text_clicked: False` at the top level of every exposure they create. Spread across Text79-84.

**Rationale:**
- Resolves Decision 1 of the Text75–84 ingest design: model field over off-model. We're about to write ~10K more click promotions in Stage 4; off-model debt would only compound.
- Symmetric with `EmailEngagement.clicked` — eliminates schema asymmetry that was historical accident.
- Sets up `compute_unified_status` to be safely callable in Stage 3/4 ingest paths without needing the imperative override that mark_clicked_from_csv_tool.py implemented.

**Migration:**
- Reversible: `mongorestore --gzip --db empower_development backups/empower_development_20260513_174120/empower_development`. Or selectively: `db.exposures.updateMany({'text_engagement.clicked': True}, [{$set: {text_clicked: '$text_engagement.clicked', text_clicked_at: '$text_engagement.clicked_at'}}, {$unset: ['text_engagement.clicked', 'text_engagement.clicked_at']}])` — but the unset-False docs cannot be reversed without restore (we discarded that signal as noise).

**Backwards compatibility:**
- ✅ Existing reads against `unified_status` work identically (status string unchanged for all docs).
- ✅ Pydantic `TextEngagement` validates docs with or without the new fields.
- ⚠ The 4 legacy ingest scripts (`scripts/ingest_impact_*`) still write `text_clicked: False` at the top level. If re-run on the current DB, they'll re-create the legacy field. Per user direction these scripts are being replaced — but if any are re-run, re-running this migration is safe (idempotent).
- ⚠ `scripts/mark_clicked_from_csv_tool.py` still writes `text_clicked: True` / `text_clicked_at` at the top level. Should be updated to write to `text_engagement.clicked` directly in a follow-up, OR replaced entirely by Stage 4's apply tool.

**Consumer impact:**
- **oc-empower tool:** no impact (generic explorer; field name renames are transparent).
- **Octopus Pydantic models:** updated (`src/models/campaign_data.py:247, :505`).
- **Octopus readers:** no required changes; status strings unchanged.
- **Octopus ingest scripts:** not updated. New ingest path (Stage 3/4) will write the nested field directly.

**Known follow-up flagged for later:**
The 4,116 docs with `unified_status: "clicked"` but NO legacy `text_clicked` field were NOT touched by this migration:
- Text75 (1,009 docs) and Text76 (996 docs) — will be wiped in Stage 3 of the current work
- WCP Text2 Section 1 (`bf86a179-...`, 1,066 docs) and Section 2 (`afb3d74b-...`, 1,045 docs), both from 2026-01-10 — these older campaigns retain `unified_status: "clicked"` without an underlying `text_engagement.clicked=True`. Either backfill those 2,111 docs with `text_engagement.clicked=True` in a follow-up cleanup script, or leave the status as-is (the next time `compute_unified_status` runs on those docs, it would downgrade them since `text_engagement.clicked` is absent). Decision out of scope here.

**Verification:**
- All 1,134 originally-True docs now have `text_engagement.clicked=True` (count match).
- All 16,767 originally-False docs no longer have `text_clicked` field (count match).
- Sample doc resolved correctly: `_id=69efdbca30c02522aa004f69` shows `status=clicked` (unchanged) with `text_engagement.clicked=True`, `text_engagement.clicked_at=2026-05-05 22:23:33`, no `text_clicked` field.
- Re-running with `--apply` is a no-op (idempotent — confirmed by dry-run logic).

---

### 2026-05-13 17:40 — add-applications-participant-oid

**Type:** schema (nested field added) + data (590 docs updated) + index (added) + tool generalization

**Collection(s):** `applications` (590 of 615 docs touched, new index `participant_match.participant_oid_1`)

**Summary:** Mirrored the exposures FK pattern on `applications`: added `participant_match.participant_oid` alongside the existing `participant_match.participant_id` natural key, populated via the (now generalized) `populate_participant_oid_tool.py`, and built a single-key index on the new field.

**Detail:**
- **Tool generalized** to support any collection + any field path. Added args:
  - `--collection` (default `exposures`)
  - `--natural-key-field` (default `participant_id`; supports dotted paths)
  - `--surrogate-key-field` (default `participant_oid`; supports dotted paths)
  The exposures invocation still works with defaults; idempotency verified post-refactor (re-running on exposures plans 0 ops).
- **Applications backfill** (`--collection applications --natural-key-field participant_match.participant_id --surrogate-key-field participant_match.participant_oid --apply`):
  ```
  Total applications:                                615
  Already had participant_match.participant_oid:       0
  With populated natural key:                        593
  Distinct natural-key values:                       454
    Matched to a participant:                        451
    Orphan (no participant): 3 → ['6142823217', '6143683479', '6143736621']
  UpdateMany ops:                                    451  (1 batch)
  Result:                                            590 matched, 590 modified
  ```
- Document accounting: 615 = 590 backfilled + 22 with null `participant_match.participant_id` (matcher found nothing) + 3 with orphan phone-keyed participant_ids.
- **Pydantic update**: `ParticipantMatch.participant_oid: Optional[PyObjectId] = None` added (`src/models/application.py:79`).
- **Index added**: single-key ASC on `participant_match.participant_oid`, built in 0.04s.

**Rationale:** Same as the exposures case — surrogate-key option-value for identity merges and future query patterns, without changing the canonical key today. With both `exposures.participant_oid` and `applications.participant_match.participant_oid` populated, an aggregation can join exposures → applications via either the natural or the surrogate path.

**Migration:**
- `scripts/populate_participant_oid_tool.py --collection applications --natural-key-field participant_match.participant_id --surrogate-key-field participant_match.participant_oid --apply`
- Reversible: `db.applications.updateMany({}, {$unset: {'participant_match.participant_oid': ''}})` plus `db.applications.drop_index('participant_match.participant_oid_1')`.

**Backwards compatibility:**
- ✅ Existing queries by `participant_match.participant_id` work unchanged.
- ✅ Pydantic `ParticipantMatch` validates with or without the new field.
- ⚠ The legacy `scripts/ingest_*` family does not populate the new field on inserts — re-run the populate tool after any ingest if needed (idempotent).

**Consumer impact:**
- **oc-empower tool:** no impact (zero references; generic explorer).
- **Octopus Pydantic models:** `src/models/application.py:79` updated.
- **Octopus readers/scripts:** no required changes; field is opt-in.

**Orphan follow-up flagged for later:**
The 3 orphan phone numbers (`6142823217`, `6143683479`, `6143736621`) represent applications where the matcher captured a phone but no `participants` row exists. Two options to address: (a) create participant records for them post-hoc, or (b) drop the `participant_match` reference. Out of scope for this change.

**Verification:**
- 3/3 random spot-checks resolved correctly to the right `participants._id` (including one phone-keyed match for an IMPACT-leads application).
- `db.applications.count_documents({'participant_match.participant_oid': {'$exists': True}})` → 590.
- Remaining 25 = 22 null-match + 3 orphan-phone (matches plan).
- Index `participant_match.participant_oid_1` present in `db.applications.list_indexes()`.

---

### 2026-05-13 17:15 — index-exposures-participant-oid

**Type:** index (added)

**Collection(s):** `exposures` (new index `participant_oid_1`)

**Summary:** Added a single-key ascending index on `exposures.participant_oid` so that queries by the new surrogate FK are O(log n) like queries by the natural key.

**Detail:**
- `db.exposures.create_index([('participant_oid', ASCENDING)])` — completed in 0.35s on 337,912 docs.
- Final exposures index set (8 total):
  - `_id_`
  - `participant_id_1_campaign_id_1` (compound)
  - `campaign_id_1`
  - `unified_status_1`
  - `sent_at_1`
  - `channel_1`
  - `participant_id_1`
  - `participant_oid_1`   ← new

**Rationale:** The 17:05 backfill made `participant_oid` available on every exposure but left queries by it unindexed — a `find({participant_oid: oid})` would have full-scanned. Adding the index unblocks any FK-based query (e.g. participant-merge tooling, `$lookup` joins keyed by OID).

**Migration:** single `create_index` call.

**Reversibility:** `db.exposures.drop_index('participant_oid_1')`.

**Backwards compatibility:** purely additive; no query behavior changes for callers that don't use the field.

**Consumer impact:**
- **oc-empower tool:** no impact.
- **Octopus**: no readers query by `participant_oid` yet. The index is on standby for future use (e.g., the upcoming new ingestion path, identity-merge tooling).

**Verification:** `db.exposures.list_indexes()` post-create shows `participant_oid_1` with `keys={'participant_oid': 1}`. Index build time (0.35s) is consistent with a single pass over the collection.

---

### 2026-05-13 17:05 — add-exposures-participant-oid

**Type:** schema (field added) + data (337,912 docs updated)

**Collection(s):** `exposures` (337,912 docs touched; new field `participant_oid`)

**Summary:** Added `participant_oid` (ObjectId reference to `participants._id`) to every exposure document as a denormalized surrogate FK alongside the existing `participant_id` natural key. The natural key remains canonical and is unchanged; the new field gives us future flexibility for identity merges, email mutation, and `$lookup`/`$graphLookup`-based queries without paying the cost of rewriting the natural key.

**Detail:**
- New backfill script: `scripts/populate_participant_oid_tool.py` (default dry-run; `--apply` to write). Idempotent — re-runs are no-ops thanks to the `participant_oid: {$exists: False}` filter on the UpdateMany predicate.
- Approach: build an in-memory `{participant_id → _id}` map (14,364 entries), then issue one `UpdateMany` per distinct participant_id in batches of 500 via `bulk_write`. 29 batches total, completed in 2.4 seconds.
- Pre-run dry-run confirmed: 14,342 distinct participant_ids in exposures, 100% matched to a participant, **0 orphans**.

**Apply-run result:**
```
Total exposures:                        337,912
Already have participant_oid (before):        0
UpdateMany ops issued:                   14,342  (29 batches × 500)
Total matched:                          337,912
Total modified:                         337,912
Remaining without participant_oid:            0
Elapsed:                                  2.4s
```

- Pydantic update: added `participant_oid: Optional[PyObjectId] = None` to `Exposure` (`src/models/campaign_data.py:478`). Marked optional so existing readers and any pre-populate documents (none currently) continue to validate.

**Rationale:**
- Resolves the "what if email changes" / identity-merge concerns we discussed earlier — *without* the high-blast-radius cost of switching the canonical key on 337K docs and updating every query in two codebases.
- Implements Option 1 of the natural-key vs surrogate-key trade-off: keep the natural key as canonical, add the surrogate side-by-side, defer any switch of "which key is canonical" to a future decision (or never).

**Migration:**
- Executed via `scripts/populate_participant_oid_tool.py --apply` after dry-run review.
- Reversible: `db.exposures.updateMany({}, {$unset: {participant_oid: ""}})` would remove the field with no other side-effects (`participant_id` is untouched and still indexed). Full backup at `/home/yersinia/devel/octopus/backups/empower_development_20260513_142238/` also covers the pre-add state.

**Backwards compatibility:**
- ✅ Existing queries by `participant_id` work identically (the field is additive).
- ✅ Pydantic `Exposure` validates with the field present or absent.
- ✅ Helper `src.utils.engagement.*` and all 9 migrated readers from the earlier change continue to function — they don't touch `participant_oid`.
- ⚠ Any new code that ASSUMES `participant_oid` is present must be aware the legacy ingest scripts (still in `scripts/ingest_impact_*.py`, `scripts/ingest_text_exposures.py`) do **not** populate it. If those scripts are re-run before being replaced, the new exposures they create will be missing the FK. Easy remedy: re-run the backfill tool, which is idempotent.

**Consumer impact:**
- **oc-empower tool**: no impact (zero references; tool is generic).
- **Octopus Pydantic models**: updated (`src/models/campaign_data.py:478`).
- **Octopus readers**: no changes required. Field is opt-in.
- **Octopus ingest scripts**: not updated per prior direction. New ingestion path (when written) should `$set` `participant_oid` at exposure-creation time; otherwise the backfill tool can patch in afterward.

**Index plan (deferred):**
- No index on `participant_oid` was added in this change. Worth adding only when/if we start querying by it. Single-key ascending would be the obvious shape; cheap to add later via `db.exposures.create_index('participant_oid')`.

**Verification:**
- Spot-checked 5 random exposures: 5/5 had `participant_oid` set and the referenced `participants._id` document matched the existing `participant_id` natural key.
- `db.exposures.count_documents({'participant_oid': {'$exists': False}})` → 0.
- `db.exposures.count_documents({'participant_id': {'$exists': False}})` → 0 (confirming the natural key was never touched).

---

### 2026-05-13 16:30 — drop-engagement-summary

**Type:** schema (field removed) + data ($unset on 14,364 docs) + index removal + code refactor

**Collection(s):** `participants` (14,364 docs touched, 1 index dropped)

**Summary:** Removed the denormalized `engagement_summary` field from all `participants` documents and dropped its index. Engagement values are now computed on demand from `exposures` via a new helper `src/utils/engagement.py`. All 9 readers (4 Bayesian models + 5 feature extractors) migrated to the helper.

**Detail:**
- New helper: `src/utils/engagement.py` exposing:
  - `attach_engagement_summaries(db, docs)` — in-place enrichment of a list of participant dicts (drop-in replacement for the projected field)
  - `build_engagement_summaries(db, participant_ids=None)` — batch dict result
  - `get_engagement_summary(db, participant_id)` — single-participant
  - All three produce the legacy `engagement_summary` shape via a single server-side `$group` aggregation on `exposures`.
- Migrated readers (one-line `attach_engagement_summaries(db, records)` after each `.find().list()`):
  - `src/bayesian_models/model_01_baseline/model.py`
  - `src/bayesian_models/model_02_energy_burden/model.py`
  - `src/bayesian_models/model_03_demographics/model.py`
  - `src/bayesian_models/model_05_rate_energy_income/model.py`
  - `src/analysis/extract_participant_features.py`
  - `src/analysis/analysis-02/extract_participant_features.py`
  - `src/analysis/analysis-03/extract_participant_features.py`
  - `src/analysis/analysis-04/extract_applicant_features.py`
  - `src/analysis/analysis-05/extract_applicant_features.py`
- Pydantic: removed `engagement_summary` field from `Participant` (`src/models/campaign_data.py:349`). Left the `EngagementSummary` class definition in place since legacy ingest scripts still import it; those scripts will be replaced by the upcoming new ingestion path.
- MongoDB ops:
  - Dropped index `engagement_summary.unified_status_1` on `participants` (the other index migrate_to_campaign_data_tool.py:221 attempted to create on `ever_engaged` never actually existed — only the unified_status one was real).
  - `$unset` of `engagement_summary` across all 14,364 participants (matched=14364, modified=14364).

**Rationale:**
- The rollup was a cache that had drifted: spot-check of 50 click-bearing participants showed 100% drift (all stored as `no_engagement`/`received`, helper correctly reports `clicked`). `total_exposures` showed ~2× drift on a 200-participant sample, traceable to the Apr 30 duplicate-exposure migration that doubled the fact table without re-running the rollup.
- Five ingest scripts duplicated the rollup-write logic and would have needed a sixth duplicate for the upcoming click-ingest work. The new ingestion path can skip rollup updates entirely.
- `exposures` already had the right indexes (`participant_id_1`, `unified_status_1`, `channel_1`) for the aggregation to run cheaply.

**Migration:**
- Executed inline via `$unset` + index drop.
- Reversible: yes via `mongorestore` from the 2026-05-13 14:22 backup. The helper does NOT write back to participants — re-deriving the rollup is a one-line aggregation if ever needed.

**Backwards compatibility:**
- ✅ Every migrated reader's inner-loop code is unchanged (e.g., `doc.get('engagement_summary', {}).get('by_channel', {}).get('email', {}).get('engaged', 0)` works as before because the helper attaches a same-shape dict).
- ✅ `EngagementSummary` Pydantic class still exists, so any module that imports it directly still works.
- ⚠ Legacy ingest scripts (`scripts/ingest_impact_*.py`, `scripts/ingest_text_exposures.py`, `scripts/migrate_to_campaign_data_tool.py`) write `engagement_summary.*` paths via `$inc` / `$set`. If re-run on the current DB, MongoDB will silently *recreate* the field on touched participants. Per user direction these scripts are being replaced by a new ingestion path and were intentionally not updated.
- ⚠ Any external tool that hardcoded a query like `{"engagement_summary.unified_status": "engaged"}` against the `participants` collection will return zero results. None known.

**Consumer impact:**
- **oc-empower tool:** no impact. `grep -rn engagement_summary /home/yersinia/devel/oc-empower` → zero matches.
- **Octopus Pydantic models:** updated (`src/models/campaign_data.py:349` field removed; `EngagementSummary` class retained).
- **Octopus readers:** 9 files updated as listed above.
- **Octopus ingest scripts:** NOT updated per user direction (being replaced).

**Verification:**
- Helper output validated against stored rollup on 200 random participants (pre-drop): `unified_status` match 96% (192/200), `ever_engaged` match 100%, structural drift on counts attributable to known data issues — confirming the *helper* is more accurate than the dropped field.
- Smoke test: all 4 Bayesian model modules import without error; 10-participant end-to-end run of `attach_engagement_summaries` produces well-formed summaries.
- Post-drop: `db.participants.count_documents({'engagement_summary': {'$exists': True}})` → 0 (was 14,364). `db.participants.list_indexes()` no longer contains `engagement_summary.unified_status_1`.

---

### 2026-05-13 16:10 — drop-applicationlists

**Type:** schema (collection dropped)

**Collection(s):** `ApplicationLists` (dropped)

**Summary:** Removed the `ApplicationLists` collection. It contained only 2 stub documents from 2024-06 that referenced 1–2 parcels each, was disconnected from any active code path, and its `parcel_ids` array was misnamed (held `<County>CountyResidential._id` hex strings, not `parcel_id` field values).

**Detail:**
- Pre-drop count: 2 documents.
- Both documents captured for audit (in case we ever want to recreate similar targeting lists with a corrected schema):
  ```json
  {"_id": "666a6f128890902def131b8b", "name": "LMI zipcodes, Cuyahoga, OH",
   "county_id": "6657abcf9a44425388c6e479",
   "parcel_ids": ["6657b1869a44425388d33cae"]}
  {"_id": "666a6f3c8890902def131b8c", "name": "LMI Energy Burden, Cuyahoga, OH",
   "county_id": "6657abcf9a44425388c6e479",
   "parcel_ids": ["6657b1869a44425388d33cae", "6657b1869a44425388d33cce"]}
  ```
  Those `parcel_ids` resolve to two Cuyahoga residential records (`parcel_id` 36101001 – BERGSTROM, JAMES I., 662 BARRETT RD; and `parcel_id` 36101067 – VECCHIONE, PAUL A., 454 HOLLY DR).
- Drop executed via `db.ApplicationLists.drop()`.

**Rationale:** Abandoned seed data. Misnamed field schema. No code references it. Removing eliminates a misleading collection that would otherwise confuse future readers about what "application lists" mean (the term sounds related to `applications`/`applicants` but is unrelated targeting tooling).

**Migration:**
- Executed inline (single `drop()` call).
- Reversible: yes — the two documents are captured verbatim in this log entry, and the full backup at `/home/yersinia/devel/octopus/backups/empower_development_20260513_142238/` contains the pre-drop state.

**Backwards compatibility:**
- ✅ No code in either octopus or oc-empower references this collection (`grep -rni ApplicationList` returns zero matches in both trees).
- ⚠ Nothing else known.

**Consumer impact:**
- **oc-empower tool:** no impact. `grep -rni ApplicationList /home/yersinia/devel/oc-empower` returned zero matches.
- **Octopus Pydantic models:** no model existed for `ApplicationLists`. No change required.
- **Octopus scripts:** zero references.
- **Other:** none discovered.

**Verification:**
- `"ApplicationLists" in db.list_collection_names()` → False post-drop.
- Pre-drop snapshot of both documents preserved above for forensics.

---

### 2026-05-13 15:58 — rename-ottawa-residential

**Type:** schema (collection rename) + data (CountyKeys row updated)

**Collection(s):** `OttawaResidential` → `OttawaCountyResidential`; `CountyKeys` (1 row updated)

**Summary:** Renamed `OttawaResidential` to `OttawaCountyResidential` so Ottawa follows the same `<County>CountyResidential` naming pattern used by every other county. Updated the `CountyKeys` entry for Ottawa to point at the new name.

**Detail:**
- Collection rename via `db.adminCommand({ renameCollection: "empower_development.OttawaResidential", to: "empower_development.OttawaCountyResidential" })`. 18,440 docs migrated atomically. Sole pre-existing index `_id_` preserved.
- `CountyKeys.find({county:"Ottawa"})` had `residential_data: "OttawaResidential"` → now `"OttawaCountyResidential"`.

**Rationale:** Ottawa was the only county where the residential collection lacked the `County` infix. The inconsistency previously forced consumers to look up collection names through `CountyKeys` rather than constructing them. With this rename, all counties follow `<County>CountyResidential` uniformly (though `CountyKeys` remains the authoritative lookup — see "Backwards compatibility" below).

**Migration:**
- Executed inline (single `renameCollection` admin command + one `update_one` on `CountyKeys`).
- Reversible: yes — rename back via the same admin command and restore the `CountyKeys` value. Backup at `/home/yersinia/devel/octopus/backups/empower_development_20260513_142238/` also includes the pre-rename state.

**Backwards compatibility:**
- ✅ Any consumer that resolves residential collection names through `CountyKeys.residential_data` works without code changes.
- ⚠ Any consumer hardcoding the literal string `"OttawaResidential"` breaks. Audited results below.

**Consumer impact:**
- **oc-empower tool** (`/home/yersinia/devel/oc-empower/workspace-campaign-participants/db/`): no impact. `grep -r OttawaResidential` over the tool returned zero matches. The tool's `get_counties()` derives county lists from `<County>CountyDemographic` collections (unchanged), and `search_by_name()` scans demographic collections only — neither touches residential.
- **Octopus Pydantic models:** no change required (models don't reference collection names).
- **Octopus scripts — fixed in this change:**
  - `scripts/find_matching_counties.py:20` — hardcoded list element `('OttawaResidential', 'zip_code')` → `('OttawaCountyResidential', 'zip_code')`. (This script also still references the deprecated `emailoctopus_db` and is likely unused.)
  - `scripts/zipcode_to_county_mapper.py:48-49` — docstring example updated for clarity. The mapper's actual logic strips suffixes generically and is unaffected by the rename.
- **Other:** none discovered. `grep -r OttawaResidential` across both `/home/yersinia/devel/octopus` and `/home/yersinia/devel/oc-empower` returned only the two files above.

**Verification:**
- Pre/post counts both 18,440 docs.
- `OttawaResidential` no longer in `db.list_collection_names()`.
- `CountyKeys.find_one({"county":"Ottawa"}).residential_data == "OttawaCountyResidential"`.
- Indexes preserved (sole `_id_` index intact).

---

### 2026-05-13 14:22 — initial-backup

**Type:** data (snapshot, no schema change)

**Collection(s):** all of `empower_development`

**Summary:** Full `mongodump --gzip` of the database, taken before any of the upcoming changes.

**Detail:**
- Path: `/home/yersinia/devel/octopus/backups/empower_development_20260513_142238/`
- Size: 322 MB
- Format: gzipped BSON, restorable with `mongorestore --gzip --db empower_development <path>/empower_development`

**Rationale:** Restore point for all subsequent edits in the Text75–84 click-ingestion work and any related schema additions.

**Migration:** N/A — read-only snapshot.

**Backwards compatibility:** N/A.

**Consumer impact:** none.

**Verification:** `ls -la backups/empower_development_20260513_142238/empower_development/` shows BSON files for every collection.

---

*(no further entries yet — first real change pending)*
