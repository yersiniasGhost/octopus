---
name: participant-profile
description: "Gather a full profile for one EMPOWER Saves participant by Mongo _id, phone number, or name. Pulls the participant document, campaign exposures, applications, and county-specific demographic/residential/electrical/thermal-load enrichment with energy burden calculations, in one command."
---

# Participant Profile

## Overview

Use this skill whenever asked to look up, dump, extract, or summarize "everything" about a specific EMPOWER Saves participant — by their Mongo `_id`, phone number, or name. It runs `scripts/get_participant_profile_tool.py`, which resolves the identifier and joins across every collection that holds information about that person, instead of re-deriving the query chain by hand each time.

## When to Use This Skill

- "Extract all information on participant ID: ..."
- "Look up participant \<phone number\>" / "\<name\>"
- "Include energy burden calculations" for a participant
- Any request for a participant's full record, engagement history, or demographic/energy profile

## How to Run It

```bash
source venv/bin/activate
python scripts/get_participant_profile_tool.py <identifier>
```

`<identifier>` can be:
- A 24-character hex Mongo `_id` (e.g. `69a61c0f9595ac4823aeb4b4`)
- A phone number, any formatting (e.g. `614-264-0950`, `(614) 264 0950`) — normalized to 10 digits and matched against `phone` or `participant_id`
- A name substring, case-insensitive (e.g. `"Tuan Nguyen"`) — matched against `demographics.customer_name`

Resolution is tried in that order. If a name matches more than 5 participants, the tool prints a disambiguation list (capped at 30 rows) instead of dumping every profile — re-run with a phone number, `_id`, or a fuller name.

## What It Returns

For each resolved participant:
1. **Participant document** — every top-level field (address, linkage, demographics, source_campaigns, do_not_contact, data_quality, etc.)
2. **Exposures** — every campaign send, with `unified_status` and `sent_at`
3. **Application** — match in the modern `applications` collection (`ingest_applications.py` pipeline), keyed by `participant_match.participant_oid`
4. **Applicants** — match in the legacy `applicants` collection (`populate_applicants_db_v3.py` pipeline), keyed by phone. These two collections are populated independently (296 vs 303 docs) and can disagree — check both.
5. **County enrichment** — demographic, residential, electrical, thermal-load, gas, and multi-tenant docs from that participant's county-specific collections, joined on `linkage.parcel_id` (falls back to phone/mobile match for the demographic collection if no parcel_id)
6. **Energy burden verdict** — `total_energy_burden` from the demographic doc, flagged as high burden if `> 6%` (the threshold `src/bayesian_models/model_02_energy_burden` tests against)
7. **Melissa LOCATE CSV match** — raw vendor row by phone, from the same CSV the county Demographic collections were built from

## Schema Gotchas Worth Knowing

`★ Insight ─────────────────────────────────────`
These are non-obvious quirks in `empower_development` that the tool encodes so you don't have to rediscover them per participant:

1. **County collection naming is inconsistent.** `{County}CountyDemographic` and `{County}CountyResidential` keep the "County" suffix, but `{County}ElectricalDB`, `{County}ThermalLoads`, `{County}GasDB`, and `{County}MultiTenant` drop it. `FranklinCountyDemographic` but `FranklinElectricalDB` — not `FranklinCountyElectricalDB`. Guessing collection names by pattern-matching one example will misfire on the other family.

2. **`participant.energy_snapshot` is essentially always empty** (`{}`) for the IMPACT-backfilled cohort, and `data_quality.has_energy_snapshot` is `False` even when real energy data exists. The actual energy data lives one join away in the county collections via `linkage.parcel_id` — don't trust the participant document's own completeness flags as a signal that the data doesn't exist elsewhere.

3. **`total_energy_burden` is `annual_kwh_cost / estimated_income * 100`**, computed at a flat **$0.13/kWh** rate baked into ingestion (not a real utility rate schedule) — verified by back-dividing several records. `-1.0` is a sentinel for "not computable" (usually missing gas data), not a real value — check for negative burden figures before treating them as zero-burden.

4. **`income_level` (on the demographic doc) is a separate raw vendor scale** (values run at least 1–9) and does **not** index into this app's own `INCOME_BRACKETS` array in `app/routes/county_analysis.py` (which only has 8 buckets, indices 0–7). Don't conflate the two.
`─────────────────────────────────────────────────`

## Related

- `scripts/investigate_participant_debug.py` — the original Franklin-only, ID-only version this skill's tool generalizes. Kept for its narrower original use case.
- `.claude_docs/script_descriptions.md` — full tool documentation index (search for `get_participant_profile_tool.py`)
- `src/bayesian_models/model_02_energy_burden/model.py` — the model that motivates the >6% high-burden threshold
