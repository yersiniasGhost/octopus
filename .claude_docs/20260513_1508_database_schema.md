# Database Schema — `empower_development`

**Generated:** 2026-05-13 15:08 PDT
**Last updated:** 2026-05-13 17:50 PDT
**MongoDB host:** `localhost:27017`
**Database:** `empower_development` (formerly split across `campaign_data` + `emailoctopus_db`; unified per CLAUDE.md)
**Pydantic models:** `src/models/`
**Change log:** [`20260513_1530_database_changes_log.md`](20260513_1530_database_changes_log.md) — every schema change since this doc was created is appended there in reverse-chronological order.

This document captures the *actual* shape of documents in the live DB at this date, with the Pydantic models as the secondary reference. Anywhere the two disagree, the live DB wins — and those drift points are called out explicitly.

### Recent changes (2026-05-13)

| Time  | Change | Affected |
|---|---|---|
| 18:50 | Fix #4: applied cross-file click evidence to 6 of the 10 Text75-84 owning campaigns. +38 click promotions; cross-file audit now shows 0 discrepancies. | `exposures` (38) |
| 18:45 | Fix #1: backfilled `text_engagement.clicked=true` on 2,111 WCP Text2 Jan-2026 docs that had `unified_status=clicked` without the underlying flag. | `exposures` (2,111) |
| 18:32 | Cross-file click coverage audit (read-only). 21,358 cross-file sightings, 103 discrepancies flagged for future review. | report only |
| 18:25 | Stage 4 of Text75-84: applied click_<slug> matches across all 10 files. 9,851 promoted to clicked, 27 audit-only. | `exposures` (9,878) |
| 18:18 | Stage 3 of Text75-84: wiped Text75/76 (old UUID), created Text77/78 fresh, reset Text83 clicks. -7,641 / +13,798 / 1,134 status resets. | `exposures` (+6,157 net), `campaigns` (-2 +4) |
| 17:52 | Folded legacy `text_clicked`/`text_clicked_at` into `text_engagement.clicked`/`clicked_at` (1,134 True + 16,767 False unset). Rewrote `compute_unified_status` text branch (opted_out > undeliverable > engaged > clicked > received). | `exposures` (17,901), Pydantic model |
| 17:40 | Added `applications.participant_match.participant_oid` (surrogate FK to `participants._id`) + index | `applications` (590/615) |
| 17:15 | Added index on `exposures.participant_oid` | `exposures` |
| 17:05 | Added `exposures.participant_oid` (surrogate FK to `participants._id`) | `exposures` (337,912) |
| 16:30 | Removed `participants.engagement_summary` field + index. Replaced by `src.utils.engagement` on-demand helper | `participants` (14,364) |
| 16:10 | Dropped `ApplicationLists` collection (abandoned 2024 stub data) | (collection removed) |
| 15:58 | Renamed `OttawaResidential` → `OttawaCountyResidential` for consistency | `OttawaCountyResidential`, `CountyKeys` |
| 14:22 | Initial pre-changes mongodump backup | snapshot only |

---

## 1. Collection inventory

Counts as of generation time.

### Operational collections (the ones we read/write)

| Collection | Count | Pydantic model | Role |
|---|---:|---|---|
| `participants` | 14,364 | `models/campaign_data.py :: Participant` | Master person — one doc per canonical contact (email or phone). Denormalized demographics, residence. (Engagement rollup was removed 2026-05-13 — compute from `exposures` via `src.utils.engagement`.) |
| `campaigns` | 160 | `models/campaign_data.py :: Campaign` | Per-send campaign metadata. Email, text, mailer, letter. Includes vendor stats. |
| `exposures` | 344,069 | `models/campaign_data.py :: Exposure` | One row per (participant × campaign). The fact table for engagement. |
| `applications` | 615 | `models/application.py :: Application` | **Canonical** conversion events (submitted forms). |
| `applicants` | 296 | `models/applicant.py :: Applicant` | **Legacy** sign-up records from earlier CSV imports; superseded by `applications` but still queryable. |

### Reference / lookup

| Collection | Count | Role |
|---|---:|---|
| `CountyKeys` | 25 | One doc per Ohio county. Maps county → the names of its five (sometimes six) per-county collections. **Authoritative source-of-truth for "which counties do we have data for."** |
| `CountySummaries` | 25 | Pre-computed aggregate stats per county (parcel counts, income distribution, monthly consumption, LMI counts). |

### County-data collections (per-county pattern, 24 counties)

For each Ohio county we cover, we maintain up to six parallel collections keyed by `parcel_id`. Counties present: Allen, Athens, Belmont, Coshocton, Cuyahoga, Fayette, Franklin, Guernsey, Hancock, Hardin, Harrison, Holmes, Huron, Lawrence, Marion, Montgomery, Morgan, Morrow, Muskingum, Ottawa, Putnam, Richland, Ross, Scioto, Wyandot.

| Pattern | Example | Role | Always present? |
|---|---|---|---|
| `<County>CountyDemographic` | `FranklinCountyDemographic` | Demographics enrichment (income, household size, energy burden, email/mobile, customer_name) | Most counties; missing for a few (Hardin, Ross, Scioto) |
| `<County>CountyResidential` | `FranklinCountyResidential` | Parcel/residence info (address, year built, sqft, owner, RCN) | Yes |
| `<County>ElectricalDB` | `FranklinElectricalDB` | Monthly + time-series electric consumption | Yes |
| `<County>GasDB` | `CuyahogaGasDB` | Monthly + time-series gas consumption | Only Cuyahoga (others gas-less) |
| `<County>ThermalLoads` | `FranklinThermalLoads` | Heating/cooling thermal regression coefficients (kwh_hl, kwh_cl slopes/intercepts/R²) | Yes |
| `<County>MultiTenant` | `CuyahogaMultiTenant`, `OttawaMultiTenant` | Multi-tenant parcel index | Cuyahoga + Ottawa only |

Naming is now uniform across all counties (`<County>CountyResidential`, etc.) as of 2026-05-13 15:58 — see [`20260513_1530_database_changes_log.md`](20260513_1530_database_changes_log.md#2026-05-13-1558---rename-ottawa-residential) for the Ottawa rename. `CountyKeys` remains the authoritative lookup since some counties still lack optional collections (`*GasDB`, `*MultiTenant`).

---

## 2. `participants` — master person

**Index:** unique on `participant_id`. Also indexed on `email`, `address.county`, `address.zip`, `linkage.parcel_id`.

**Identity rule:** `participant_id` is **email if available, else phone (10 digits, no formatting)**.

```jsonc
{
  "_id": ObjectId,
  "participant_id": "ttaylor2tambra51@outlook.com",  // canonical ID — email OR phone
  "email": "ttaylor2tambra51@outlook.com",            // duplicate of participant_id when email-keyed
  "phone": null,                                      // 10-digit string when present

  "address": {
    "street": null,
    "city": null,
    "zip": "43143",
    "county": "FayetteCounty",   // string, sometimes "Fayette", sometimes "FayetteCounty" — inconsistent
    "raw": null
  },

  "linkage": {                       // how we tied this participant to a parcel
    "parcel_id": "10000200202101",
    "county_key": "Fayette",         // matches CountyKeys.county
    "method": "email",               // "email" | "phone" | "address" | "name"
    "confidence": 0.8,               // 0.0–1.0
    "matched_at": ISODate
  },

  "demographics": {                  // DENORMALIZED snapshot from <County>CountyDemographic
    "customer_name": "TAMBRA L TAYLOR",
    "estimated_income": 25000.0,
    "income_level": null,
    "household_size": 4.0,
    "annual_kwh_cost": 7378.02,
    "annual_gas_cost": null,
    "total_energy_burden": 29.51208,
    "energy_burden_kwh": 29.51208,
    "energy_burden_gas": null,
    "age_bracket": null,             // "65-66" format when present
    "home_owner": null,
    "dwelling_type": null,
    "marital_status": null,
    "presence_of_children": null,
    "number_of_adults": null
  },

  "residence": {                     // DENORMALIZED snapshot from <County>CountyResidential
    "living_area_sqft": 2021.0,
    "story_height": 1.5,
    "year_built": 1900,
    "house_age": 125,
    "bedrooms": null, "bathrooms": null, "half_baths": null, "rooms_total": null,
    "heat_type": null, "air_conditioning": null, "construction_quality": null,
    "garage_size": null,
    "parcel_owner": "TAMBRA L TAYLOR",
    "census_tract": null,
    "rcn": null                      // replacement cost new
  },

  "energy_snapshot": {               // captured at first campaign send time
    "kwh_annual": null,
    "annual_cost": 8513.1,
    "annual_savings": null,
    "monthly_cost": null,
    "monthly_saving": null,
    "daily_cost": null,
    "snapshot_date": ISODate
  },

  // engagement_summary: REMOVED 2026-05-13. Compute on demand from `exposures`
  // via src.utils.engagement.attach_engagement_summaries. See change log entry
  // "2026-05-13 16:30 — drop-engagement-summary".

  "data_quality": {                  // flags for analysis filtering
    "has_demographics": true,
    "has_residence": true,
    "has_energy_snapshot": false,
    "has_engagement": true,
    "completeness_score": 0.57,      // 0.0–1.0
    "analysis_ready": true
  },

  "thermal": {                       // OPTIONAL — added by demographic enrichment
    "county": "Fayette",
    "kwh_hl_slope": 0.31, "kwh_hl_intercept": 2240.24, "kwh_hl_r2": 0.69,
    "kwh_cl_slope": -0.53, "kwh_cl_intercept": 6247.63, "kwh_cl_r2": 0.09,
    "source_collection": "FayetteThermalLoads",
    "enriched_at": ISODate
  },

  "source_campaigns": ["MVCAP_...", "text_35", ...],  // list of campaign names/ids touched

  "created_at": ISODate,
  "updated_at": ISODate,

  "_migration": { "source_db": "campaign_data", "migrated_at": ISODate, ... }
}
```

**🚩 Known gotchas:**
- **Engagement is no longer denormalized on the participant.** Use `src.utils.engagement.attach_engagement_summaries(db, docs)` to compute the same shape from `exposures` on demand. Single-participant variant: `get_engagement_summary(db, participant_id)`.
- `address.county` is inconsistent — sometimes `"Fayette"`, sometimes `"FayetteCounty"`. Always compare case-insensitively *and* with/without the `County` suffix.
- `email` is immutable after creation (per obs 1694, Apr 30). If a participant's email is empty/wrong, you can't fix it by updating — you need to create a new participant and migrate exposures.

---

## 3. `campaigns` — per-send metadata

**Index:** unique on `campaign_id` (a UUID). Also indexed on `channel`, `agency`, `sent_at`, and both `source_ids.*` fields.

```jsonc
{
  "_id": ObjectId,
  "campaign_id": "cfbdcaef-30ab-4994-b984-2a488eea266e",   // canonical UUID — referenced by exposures

  "source_ids": {                    // traceability back to original systems
    "campaign_data_id": "00f9aa9a-7a0e-11f0-9ff1-434f69d2f065",
    "empower_dev_id": null
  },

  // Identity
  "name": "MVCAP_Improve_20250815",
  "name_variants": ["MVCAP_Improve_20250815"],
  "agency": "MVCAP",
  "channel": "email",                // "email" | "text" | "mailer" | "letter"  (also legacy "text_morning"/"text_evening")
  "campaign_type": null,
  "message_type": "improve",
  "message_types": ["savings_financial", "motivational_struggle"],
  "message_body": null,              // populated for text campaigns
  "target_audience": null,
  "status": "SENT",

  // Delivery — email-specific
  "subject": null, "from_name": null, "from_email_address": null, "template_id": null,

  // Delivery — text-specific
  "sender_phone": null, "sms_provider": null,    // e.g. "rumbleup"

  // Delivery — postal-specific
  "print_vendor": null, "postage_class": null, "envelope_type": null,
  "color_printing": null, "double_sided": null,

  // Cost
  "cost_per_send": null, "total_cost": null,

  "statistics": {                    // aggregate counters (denormalized — recomputed from exposures)
    "total_sent": 1692,
    "delivered": 51,
    "opened": 51,
    "clicked": 1,
    "bounced": 64,
    "failed": null,
    "unsubscribed": 0,
    "opted_out": null,
    "complained": 1,
    "received": 0,
    "engaged": 0,
    "receive_rate": 0.030,
    "engage_rate": 0.001
  },

  "source_system": "emailoctopus",   // "emailoctopus" | "rumbleup" | "excel_import" | "conversation_import" | null
  "source_file": "campaign_00f9aa9a..._MVCAP_Improve_20250815.csv",

  "sent_at": ISODate,
  "created_at": ISODate,
  "synced_at": ISODate,

  "_migration": { ... }
}
```

**🚩 Gotchas:**
- `channel` has `null` for some legacy docs — defend against it.
- `statistics` is a cache. Don't trust it for live numbers; recompute from `exposures` when accuracy matters.

---

## 4. `exposures` — the fact table

**Indexes:** compound `(participant_id, campaign_id)` (**not unique**, but should be), plus singletons on `participant_id`, `participant_oid`, `campaign_id`, `unified_status`, `sent_at`, `channel`.

**This is the biggest collection (338K docs) and the one the upcoming click-ingestion will write to.**

**Dual-key reference to participants** (since 2026-05-13): every exposure carries both `participant_id` (natural key — email/phone string, canonical for queries today) and `participant_oid` (surrogate FK — `participants._id`, for identity-merge scenarios and `$lookup` joins). Both are indexed.

```jsonc
{
  "_id": ObjectId,

  // Foreign keys
  "participant_id":  "ttaylor2tambra51@outlook.com",          // natural key → participants.participant_id (email or 10-digit phone)
  "participant_oid": ObjectId("69a61c0f9595ac4823ae94c2"),    // surrogate FK → participants._id (added 2026-05-13)
  "campaign_id":     "cfbdcaef-30ab-4994-b984-2a488eea266e",  // → campaigns.campaign_id

  // Denormalized for query convenience
  "agency": "MVCAP",
  "channel": "email",                // "email" | "text"  (mailer/letter exist in model but rare in data)
  "sent_at": ISODate,

  // Channel-specific engagement — exactly one of these is populated based on channel
  "email_engagement": {
    "opened": false, "opened_at": null,
    "clicked": false, "clicked_at": null,
    "bounced": false, "complained": false, "unsubscribed": false
  },
  "text_engagement": {
    "delivered":  null,
    "read":       null,
    "replied":    null,
    "opted_out":  null,
    "failed":     null,
    "clicked":    null,   // added 2026-05-13 17:52 (mirrors email_engagement)
    "clicked_at": null
  },
  "postal_engagement": {
    "delivered": null, "response": null
  },

  // Unified status — distinct values currently in DB:
  //   "no_engagement" | "received" | "clicked" | "engaged" | "converted"
  //   | "opted_out" | "undeliverable" | "negative_response"
  "unified_status": "no_engagement",

  // Contact + energy at send-time (immutable snapshot)
  "contact_snapshot": { "email": "...", "phone": "", "address": "", "city": "", "zip": "43143" },
  "energy_at_send":   { "kwh": null, "annual_cost": 8513.1, "annual_savings": null, ... },

  "created_at": ISODate,
  "_migration": { "source": "campaign_exposures", "source_id": "...", "migrated_at": ISODate },

  // ⚠ OFF-MODEL FIELDS (added imperatively by mark_clicked_from_csv_tool.py — not in Pydantic):
  "text_clicked":    true,           // exists on 1,134 docs as of 2026-05-05
  "text_clicked_at": ISODate
}
```

### `unified_status` hierarchy (text channel — current logic in `Exposure.compute_unified_status`, updated 2026-05-13 17:52)

```
opted_out / undeliverable    (terminal — never overwritten)
engaged    (replied — wins over clicked)
clicked    (link tap — beats received)
received   (delivered / read)
no_engagement
```

`compute_unified_status` now produces all six statuses including `clicked` (previously `clicked` was set imperatively only via `mark_clicked_from_csv_tool.py`). Future ingest code can call `compute_unified_status` after setting `text_engagement.clicked=True` and get the correct status string back.

**🚩 Schema drift (relevant to upcoming work):**
- ✅ `TextEngagement.clicked` + `clicked_at` added to model (2026-05-13 17:52) and 1,134 legacy off-model docs migrated. Field path is `exposures.text_engagement.clicked`.
- ⚠ `unified_status` distinct values include `"converted"` and `"negative_response"` which are not in the `UnifiedEngagement` enum. Something is writing them. Worth grepping before adding new statuses.
- ⚠ Compound index on `(participant_id, campaign_id)` is **not unique** — duplicates are possible and have happened (per obs 1701, Apr 30: "Duplicate exposure migration created 20 real and 20 phantom records"). Always upsert defensively.
- ✅ 2,111 docs in older WCP Text2 campaigns (Jan 2026) had `unified_status: "clicked"` without the nested flag; backfilled 2026-05-13 18:45 (`scripts/backfill_wcp_text2_clicked_flag_tool.py`). `compute_unified_status` now returns the same `clicked` value.

---

## 5. `applications` — canonical conversions

**Index:** non-unique on `application_id`, `applicant.email`, `address.county`, `participant_match.participant_id`, `participant_match.participant_oid`. (Uniqueness is enforced via the ingest pipeline checking `application_id` before insert.)

```jsonc
{
  "_id": ObjectId,
  "application_id": "323",            // "Entry Id" from source form (string)

  "applicant": {
    "first_name": "Zane",
    "middle_name": null,
    "last_name": "Davenport",
    "email": "zanedavenport@hotmail.com",
    "phone": "3302067363",            // 10 digits, no formatting
    "phone_raw": "3302067363"         // as-submitted
  },

  "address": {
    "street": "360 Cadiz-New Athens Rd",
    "city": "Cadiz",
    "state": null,
    "zip": "43907",
    "county": "Harrison"
  },

  "self_reported": {                  // from the application form, normalized
    "age": 72, "age_raw": "72",
    "household_income": 40000.0, "household_income_raw": "40,000",
    "household_members": 2,
    "housing_status": null,           // "rent" | "own" | null
    "needs_housing_help": null,
    "has_dependent_children": null,
    "pre_1978_home": null
  },

  "attribution": {                    // how we credit a campaign for this conversion
    "utm": {                          // parsed from form's source_url
      "utm_source": "Majority",
      "utm_medium": "Letter",
      "utm_campaign": "Letter",
      "utm_id": "Letter",
      "utm_content": null,
      "source_url": "https://www.reduceenergyburdenohio.com/?utm_source=Majority&..."
    },
    "likely_campaigns": [             // populated by attribute_applications_to_campaigns.py
      // { "campaign_id": "...", "confidence": 0.7, "method": "utm_direct" | "date_window" | "county_exposure" }
    ]
  },

  "participant_match": {              // → participants
    "participant_id":  "zanedavenport@hotmail.com",        // natural key (email or 10-digit phone) → participants.participant_id
    "participant_oid": ObjectId("69a61c0f..."),            // surrogate FK → participants._id (added 2026-05-13; absent on null-match and orphan-phone applications)
    "match_method": "email",          // "email" | "phone" | "address"
    "match_confidence": 0.95,
    "matched_at": ISODate
  },

  "cluster_assignment": {             // for outcome analysis vs clustering models
    "phase1_cluster": null,           // demographics clustering
    "phase2_cluster": null,           // campaign exposure clustering
    "phase3_cluster": null,           // probabilistic clustering
    "assigned_at": null
  },

  "entry_date": ISODate,
  "created_at": ISODate,
  "import_batch": "APPLICANTS_sign-up-today-2025-09-03_20251209_054227",
  "_migration": { ... }
}
```

---

## 6. `applicants` — legacy sign-up table

**No declared indexes** (only `_id`). **Superseded by `applications`** but still present (296 docs).

Different shape from `applications`: flat top-level fields, no nested `applicant`/`address`/`attribution`. Uses `demographic_ref` / `residence_ref` sub-docs that point at the matched county records.

```jsonc
{
  "_id": ObjectId,
  "entry_id": "323",
  "first_name": "Zane",
  "last_name":  "Davenport",
  "email":      "zanedavenport@hotmail.com",
  "phone":      "3302067363",
  "address":    "360 Cadiz-New Athens Rd",
  "city":       "Cadiz",
  "zip_code":   "43907",
  "county":     "Harrison",

  "demographic_ref": {                // see ResidenceReference / DemographicReference in models/common.py
    "county": "Harrison",
    "parcel_id": "50000010000",
    "customer_name": "DAVENPORT, ZANE W",
    "email": "zanedavenport@hotmail.com",
    "mobile": null,
    "annual_kwh_cost": 2855.58,
    "total_energy_burden": 11.42232
  },
  "residence_ref": {
    "county": "Harrison",
    "parcel_id": "50000010000",
    "address": "360 OAK PARK RD",
    "parcel_city": "CADIZ",
    "parcel_zip": 43907
  },
  "match_info": {
    "match_quality": "demographic",   // "exact" | "good" | "fuzzy" | "demographic" | "no_match"
    "match_method": "email",
    "match_details": "Email match: ...",
    "matched_at": ISODate
  },

  "created_at": ISODate,
  "updated_at": ISODate
}
```

**🚩** Some of the same entries exist in both `applicants` (legacy) and `applications` (canonical). For any new work, **write only to `applications`**. Querying conversions should hit `applications` unless you specifically need a record that pre-dates the 2025-11 migration.

---

## 7. `ApplicationLists` — *(removed 2026-05-13)*

Dropped. Contained only 2 stub documents from 2024-06 with a misnamed `parcel_ids` field. See [change log entry](20260513_1530_database_changes_log.md#2026-05-13-1610---drop-applicationlists).

---

## 8. `CountyKeys` — county collection lookup (source of truth)

```jsonc
{
  "_id": ObjectId,
  "county": "Cuyahoga",                              // bare name, no "County" suffix
  "state": "OH",
  "demographic_data":  "CuyahogaCountyDemographic",  // exact collection name
  "residential_data":  "CuyahogaCountyResidential",
  "electrical_data":   "CuyahogaElectricalDB",
  "gas_data":          "CuyahogaGasDB",              // present only for counties with gas data
  "thermal_load_data": "CuyahogaThermalLoads",
  "commercial_data":   "CuyahogaMultiTenant"         // present only for counties with multi-tenant index
}
```

**Always resolve county collection names through this collection.** Although naming is now uniform across counties as of 2026-05-13 15:58 (the Ottawa rename), some counties still lack optional collections (`*GasDB` for non-Cuyahoga, `*MultiTenant` for most counties). String-concatenation would silently miss those.

---

## 9. `CountySummaries` — pre-aggregated county stats

```jsonc
{
  "_id": ObjectId,
  "county_id": ObjectId,               // → CountyKeys._id
  "county_name": "Ottawa",
  "state": "OH",
  "calculated_at": ISODate,

  "total_parcels": 18440,
  "parcels_with_demographic_data": 5645,
  "parcels_with_electrical_data": 11399,
  "parcels_with_gas_data": 0,
  "parcels_with_thermal_data": 11399,

  "income_dist_extreme_poverty": 59,
  "income_dist_severe_poverty":  158,
  "income_dist_near_poverty":    263,
  "income_dist_above_poverty":   783,
  "income_dist_unknown":         4382,

  "avg_estimated_income":    0.0,
  "median_estimated_income": 87500.0,
  "min_estimated_income":    0.0,
  "max_estimated_income":    300000.0,

  "avg_energy_burden_kwh":     0.0,
  "avg_energy_burden_gas":    -1.0,    // -1 = no data sentinel
  "avg_total_energy_burden":   0.0,
  "median_total_energy_burden": 0.2,

  "lmi_parcel_count":     1541,
  "non_lmi_parcel_count": 783,
  "monthly_lmi_consumption":     [0.8, 1.9, 1.3, ...],   // 12 months Jan→Dec
  "monthly_non_lmi_consumption": [0.9, 1.8, 1.5, ...]
}
```

---

## 10. County-data document shapes

All keyed by `parcel_id` (string).

### `<County>CountyDemographic`

```jsonc
{
  "_id": ObjectId,
  "parcel_id":            "...",
  "customer_name":        "FELICHA L THOMPKINS",
  "email":                "...",
  "mobile":               "6145553333",
  "address":              "...",
  "service_city":         "...",
  "parcel_zip":           43207,
  "estimated_income":     35000.0,
  "income_level":          2,        // tier code
  "md_householdsize":      3.0,
  "annual_kwh_cost":       2855.58,
  "annual_gas_cost":       null,
  "energy_burden_kwh":     11.42,
  "energy_burden_gas":     null,
  "total_energy_burden":   11.42
  // Some counties also include: age in two-year increments - 1st individual,
  // home owner / renter, presence of children, marital status, number of adults,
  // dwelling type. Field naming is inconsistent — see Demographics.from_county_record.
}
```

### `<County>CountyResidential`

```jsonc
{
  "_id": ObjectId,
  "parcel_id":          "...",
  "address":            "...",
  "parcel_city":        "...",
  "parcel_zip":         43215,
  "parcel_owner":       "...",
  "age":                1970,         // ⚠ can be year_built (>1800) OR age in years (<200)
  "story_height":       1.5,
  "living_area_total":  1820.0,
  "rcn":                145000.0,     // replacement cost new
  "energy_percentile":  72            // optional, set by enrichment
}
```

### `<County>ElectricalDB`

```jsonc
{
  "_id": ObjectId,
  "parcel_id":         "...",
  "time_series_elec":  [ { "date": ISODate, "kwh": ... }, ... ],
  "monthly_averages":  [j,f,m,a,m,j,j,a,s,o,n,d],
  "monthly_maximums":  [...],
  "monthly_minimums":  [...]
}
```

### `<County>GasDB` (Cuyahoga only at present)

Same shape as `ElectricalDB` but `time_series_gas` and adds `annual_average`.

### `<County>ThermalLoads`

```jsonc
{
  "_id": ObjectId,
  "parcel_id":          "...",
  // Heating-load regression (kWh ~ HDD)
  "kwh_hl_slope":       0.31,
  "kwh_hl_intercept":   2240.24,
  "kwh_hl_r2":          0.69,
  // Cooling-load regression (kWh ~ CDD)
  "kwh_cl_slope":       -0.53,
  "kwh_cl_intercept":   6247.63,
  "kwh_cl_r2":          0.09,
  // Per-month deconvolved heating/cooling consumption
  "kwh_hl_cl_loads":    [{ "month": 1, "hl": ..., "cl": ... }, ...],
  "gas_hl_cl_loads":    [...]
}
```

### `<County>MultiTenant`

Multi-tenant parcel index — same shape as Residential but for buildings with multiple units.

---

## 11. Key relationships (diagram)

```
                              ┌──────────────────┐
                              │   CountyKeys     │
                              │   (one per       │
                              │    county)       │
                              └────────┬─────────┘
                                       │  resolves to
                                       ▼
                ┌──────────────────────────────────────────┐
                │  <County>CountyDemographic               │
                │  <County>CountyResidential               │
                │  <County>ElectricalDB                    │   keyed by parcel_id
                │  <County>GasDB             (Cuyahoga)    │
                │  <County>ThermalLoads                    │
                │  <County>MultiTenant       (Cuy + Ottawa)│
                └──────────────────────────────────────────┘
                                       ▲
                                       │ linkage.parcel_id
                                       │ + denormalized snapshots
                                       │
                                ┌──────┴─────────┐
  ┌─────────────────┐           │  participants  │
  │   campaigns     │           │  ._id  (OID)   │
  │   .campaign_id  │           │  .participant_ │
  │   (UUID)        │           │     id (email  │
  └────────┬────────┘           │     or phone)  │
           │                    └───┬────────┬───┘
           │                        │        │
           │       participant_id ──┘        └── participant_oid (OID, since 2026-05-13)
           │       (natural key)                 (surrogate FK)
           ▼                        │             │
     ┌────────────┐                 │             │
     │ exposures  │ ◄───────────────┴─────────────┘   (BOTH keys present on every doc)
     │ (fact)     │
     │            │                ┌──────────────────────┐
     │            │ ◄────likely_   │   applications       │
     │            │   campaigns    │   (conversions)      │
     │            │                │                      │
     │            │                │  participant_match:  │
     │            │                │    .participant_id   │ ─┐
     │            │                │    .participant_oid  │ ─┤
     │            │                │       (since         │  │  both reference
     │            │                │        2026-05-13)   │  │  participants
     │            │                └──────────────────────┘  │
     └────────────┘                                          │
                                                             ▼
                                                      (back to participants)

  applicants (legacy)  ─── superseded by applications, kept for read-only history
```

---

## 12. Things to know before the click-ingestion work

These directly affect the choices on the upcoming Text75–84 click ingestion. Items marked ✅ are now resolved; ⚠ are still live decisions or constraints.

1. ⚠ **`TextEngagement.clicked` does not exist as a model field**, but `text_clicked: true` exists on 1,134 `exposures` docs (added imperatively by `mark_clicked_from_csv_tool.py` on 2026-05-05). Decision still pending: add to model and migrate the 1,134 docs, vs. keep off-model.
2. ⚠ **`unified_status: "clicked"` is set imperatively**, not by `compute_unified_status`. Re-running that method on a "clicked" exposure would *downgrade* it to "received". Any future enrichment must avoid blanket recomputes, or `compute_unified_status` needs updating.
3. ✅ **`participants.engagement_summary` removed 2026-05-13.** Engagement is now derived on demand from `exposures` via `src.utils.engagement`. No stale-rollup risk.
4. ⚠ **`(participant_id, campaign_id)` is not unique on `exposures`** — duplicates have happened during migrations. Always upsert with explicit filters; never bulk-insert without a dedupe check.
5. ⚠ **Campaigns for Text75–84 may or may not already exist.** Text83/84 were partially loaded on May 5 (campaign_ids like `text_impact_lastday_83`); Text75–82 likely aren't ingested at all yet. Confirm before deciding "create new" vs "augment existing."
6. ⚠ **`Tags` column in source Excel is contact-level aggregated** — contains `click_<slug>` tokens from *every* campaign the contact ever touched. Per-file ingestion must filter to only the slugs relevant to that file's campaign.
7. ⚠ **Slug collisions**: Text75/76 both use slug `lmss`; Text83/84 both use slug `pRJQ`. The `Tags` column alone cannot distinguish Section 1 from Section 2 — disambiguation must come from "which file contained this contact's phone."
8. ✅ **Surrogate FK `participant_oid` available on every exposure.** New ingestion should populate it at exposure-creation (do a `participants.find_one({participant_id})._id` lookup and set both keys). If skipped, `scripts/populate_participant_oid_tool.py` can backfill idempotently after the fact.

**Tools available for the new ingestion path:**
- `src.utils.engagement.{attach,build,get}_engagement_summaries` — compute participant rollups from exposures without storing anything
- `scripts/populate_participant_oid_tool.py` — idempotent FK backfill for any collection + field path
- `scripts/mark_clicked_from_csv_tool.py` — promote exposures to `unified_status: clicked` from a phone-list CSV (the existing pattern that wrote the 1,134 docs)
