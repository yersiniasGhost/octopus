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
