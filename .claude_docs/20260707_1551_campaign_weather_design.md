# Campaign Weather Enrichment — Design

**Date:** 2026-07-07
**Status:** Approved
**Author:** brainstorming session (Loran + Claude)

## Goal

Add local weather context to each campaign in the `campaigns` collection
(`empower_development` MongoDB). Weatherization and energy-usage campaigns are
centered around Ohio counties; attaching the weather recipients had just
experienced makes campaign performance interpretable against real heating/cooling
conditions.

## Context (data model findings)

- **Campaigns have no county field.** Geography is a derived, recipient-weighted
  property: `exposures.campaign_id` → `exposures.participant_oid` →
  `participants.linkage.county_key`.
- **Campaigns are mostly multi-county.** Only 20/163 hit a single county; COAD
  agency campaigns spread across 9 counties with the top county at ~27%.
- **Campaigns are point-in-time** (`sent_at`, single timestamp), spanning
  2025-03-25 → 2026-03-31. All dates are historical relative to today
  (2026-07-07), so archive weather is fully available.
- `CountyKeys` enumerates 25 Ohio counties but has **no lat/lon**.

## Decisions

| Decision | Choice |
|----------|--------|
| Storage | **Embedded on campaign only** — no new collection |
| Time window | **5 days prior through send** → `[sent_at − 5d, sent_at]` inclusive = 6 daily records |
| County scope | **Dominant county only** (top recipient county), with recipient share recorded |
| Metrics | temp mean/min/max, HDD/CDD (base 65°F), extreme-day counts |

## Design

### 1. Dominant county resolution

For each campaign: join `exposures` (by `campaign_id`) to `participants`
(by `participant_oid`), tally `linkage.county_key` across recipients, select the
county with the most recipients. Record `county_recipient_share` (top count /
total resolved) so the multi-county spread stays transparent.

### 2. Weather window

`window = [sent_at − 5 days, sent_at]` inclusive → 6 daily records.

Edge cases:
- Campaign missing `sent_at` (6 of 163) → `weather: { status: "no_send_date" }`.
- Campaign with no resolvable recipient county (4 of 163) →
  `weather: { status: "no_county" }`.

### 3. Data source

Open-Meteo **Historical Archive** API (`https://archive-api.open-meteo.com/v1/archive`),
free, no API key. Requested with `temperature_unit=fahrenheit` and
`daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean`. County centroid
lat/lon comes from a static 25-county Ohio lookup embedded in the script.

### 4. Metrics (computed over the 6-day window)

- `temp_f`: mean (of daily means), min (of daily mins), max (of daily maxes)
- `degree_days`:
  - `hdd_base65 = Σ max(0, 65 − Tmean_day)`
  - `cdd_base65 = Σ max(0, Tmean_day − 65)`
- `extremes`:
  - `freezing_days` = count of days with daily min < 32°F
  - `hot_days` = count of days with daily max > 90°F
  - `freezing_hours` = count of hourly temps < 32°F (from hourly archive data)
  - `hot_hours` = count of hourly temps > 90°F
  - `window_hours` = total hours in the window (144 for a full 6-day window)

  Day counts flag *whether* an extreme occurred; hour counts measure its
  *duration* (a day can read as "freezing" from a single pre-dawn hour).

### 5. Embedded schema

```jsonc
weather: {
  status: "ok",                       // or "no_send_date" | "no_county" | "fetch_failed"
  county: "Franklin",
  county_recipient_share: 0.82,
  window: { start: <date>, end: <date>, days: 6 },
  source: "open-meteo-archive",
  latitude: 39.97, longitude: -83.00,
  fetched_at: <datetime>,
  temp_f: { mean, min, max },
  degree_days: { hdd_base65, cdd_base65 },
  extremes: { freezing_days, hot_days, freeze_threshold_f: 32, hot_threshold_f: 90 },
  daily: [ { date, tmin_f, tmax_f, tmean_f }, ... ]  // 6 records
}
```

### 6. Deliverables

- `scripts/backfill_campaign_weather_tool.py`
  - Resolves dominant county per campaign.
  - Fetches archive weather for `(county_centroid, window)`.
  - Computes metrics, writes the embedded `weather` field via `update_one`.
  - **Idempotent**: skips campaigns that already have `weather` unless `--force`.
  - **Cached**: memoizes `(county, start, end)` → weather so campaigns sharing a
    county+window reuse one API call.
  - `--dry-run` prints intended writes without mutating the DB.
- New entry in `.claude_docs/script_descriptions.md`.

## Trade-offs

- **Dominant-county-only** characterizes ~27% of recipients for the widest COAD
  campaigns. Accepted; `county_recipient_share` makes the limitation visible.
- **Embedded-only** duplicates weather across campaigns sharing a county+window.
  Mitigated by the in-run cache; footprint is small (6 daily records each).

## Out of scope (YAGNI)

- Shared `county_weather` collection.
- Precipitation / snowfall metrics.
- Recipient-weighted multi-county aggregation.
- Live/forecast weather (all campaign dates are historical).
