# Applicant Visualization Page — Design Spec

**Date:** 2026-04-27
**Author:** Loran Friedrich (with Claude)
**Status:** Approved, ready for implementation plan

## Summary

A new authenticated page at `/dashboard/applicants` that visualizes applicant
data across three tabs: **Overview**, **Demographics**, and **Attribution**.
Follows the existing per-channel dashboard pattern (email, text) and reuses the
Flask + Bootstrap + Chart.js + `CampaignDataService` stack already in place.

Geography (county heat map / choropleth) is explicitly **out of scope** for
this iteration but the architecture leaves room to add a fourth tab later.

## Goals

- Give operators a single page to answer: who is applying, what do they look
  like, and where did they come from?
- Reuse existing patterns; no new frameworks, no new env vars, no new
  third-party dependencies.
- Stay honest about data coverage — show "n=X" captions whenever a chart is
  computed from a subset.

## Non-Goals

- Geographic / map visualization (deferred)
- A/B test or experiment tooling
- Editing or admin actions on applicants (read-only page)
- Real-time updates / streaming

## Data Sources

Two MongoDB collections in `empower_development`:

| Collection     | Records | Role                                                                     |
| -------------- | ------- | ------------------------------------------------------------------------ |
| `applications` | 616     | Primary source — newer schema, has UTM attribution + self-reported demos |
| `applicants`   | 296     | Supplementary — older schema, has `demographic_ref.total_energy_burden`  |

**Join key for the energy-burden chart:** `applications.applicant.email` ↔
`applicants.email`. The energy-burden chart explicitly labels its sample size
since coverage is partial.

### Key fields used

From `applications`:

- `_id`, `application_id`, `entry_date`, `created_at`, `import_batch`
- `address.county`, `address.zip`, `address.city`
- `applicant.first_name`, `applicant.last_name`, `applicant.email`
- `attribution.utm.utm_source`, `attribution.utm.utm_medium`,
  `attribution.utm.utm_campaign`
- `self_reported.age`, `self_reported.household_income`,
  `self_reported.household_members`
- `participant_match.match_method`, `participant_match.match_confidence`

From `applicants`:

- `email`, `demographic_ref.total_energy_burden`,
  `demographic_ref.annual_kwh_cost`

## Architecture

### Routing

- New view function `applicants_dashboard()` in `app/routes/main.py`
- URL: `GET /dashboard/applicants`
- Decorator: `@login_required`
- Follows the same pattern as `email_dashboard()` (try/except, default-empty
  fallback on error)

### Template

- New file: `app/templates/dashboards/applicants.html`
- Extends `base.html`
- Uses Bootstrap nav-tabs for the three tabs
- Embeds chart data as JSON in `<script>` blocks for Chart.js to read
- Each chart lives in a Bootstrap card with a title + "n=X" caption

### Service Layer

Extend `app/services/campaign_data_service.py` with one orchestrating method
plus three private builders, one per tab:

```python
def get_applicant_dashboard_data(self) -> Dict[str, Any]:
    return {
        'overview': self._build_applicant_overview(),
        'demographics': self._build_applicant_demographics(),
        'attribution': self._build_applicant_attribution(),
    }
```

Each builder runs a small number of MongoDB aggregations (binning, grouping,
sorting done in the database) and returns a plain dict the template can
serialize to JSON without touching ObjectIds or `datetime` objects.

### Navigation

Add an "Applicants" link to the dashboard nav alongside Email / Text / Mailer /
Letter / Modeling. The exact location depends on the current nav markup in
`base.html`; the implementation plan will surface this.

## Tab Contents

### Overview tab

- **KPI strip** (5 cards): total applicants · this-month count · match rate
  (% with successful `participant_match`) · top county · top channel
- **Time series**: applications per week, last 6 months, line chart, bucketed
  on `entry_date`
- **Match quality donut**: counts grouped by `participant_match.match_method`
  (or "unmatched" when null)
- **Recent applicants table**: 25 rows — name, county, zip, channel
  (`utm_medium`), entry date, match badge

### Demographics tab

- **Age histogram**: bins `<30`, `30–44`, `45–59`, `60–74`, `75+`, from
  `self_reported.age`. Excludes nulls; "n=X" caption.
- **Household income histogram**: bins `<20k`, `20–40k`, `40–60k`, `60–80k`,
  `80k+`, from `self_reported.household_income`. Excludes nulls; "n=X" caption.
- **Household size bar**: bins `1`, `2`, `3`, `4`, `5+`, from
  `self_reported.household_members`.
- **Energy burden histogram**: bins `<6%`, `6–10%`, `10–15%`, `15%+`, from
  `applicants.demographic_ref.total_energy_burden` joined by email. Caption
  reads "based on n=X demographic-matched records (out of 616)".
- **Scatter**: income (y) vs. age (x), color-coded by top-3 counties + "other".

### Attribution tab

- **UTM medium bar**: counts grouped by `attribution.utm.utm_medium`. Null
  values bucketed as "Direct/Unknown".
- **UTM source bar**: top 10 by application count.
- **UTM campaign bar**: top 10 by application count.
- **Channel conversion table**: per channel (text / email / letter / mailer),
  show exposures count, applications count, conversion rate (%). Exposures
  come from the `exposures` collection grouped by `channel`/`campaign_type`;
  applications come from `applications` grouped by `utm.utm_medium`. The
  caption explains the mapping (utm_medium "Letter" → letter channel, etc.).

## Data Flow

1. `GET /dashboard/applicants` → `applicants_dashboard()`
2. View calls `service.get_applicant_dashboard_data()`
3. Service runs three aggregations (one per tab) plus the supplementary
   energy-burden join
4. Service returns plain dict; view passes it to `render_template`
5. Template emits JSON `<script>` blocks for Chart.js to read on page load
6. Charts render client-side; no AJAX, no follow-up requests

## Error Handling

- Service catches exceptions per-builder and returns empty/zero defaults so
  one failing chart never breaks the whole page. Logs via `LogManager`.
- View has an outer try/except that returns the template with a fully-empty
  data dict if the service itself fails (parallels the existing
  `email_dashboard()` fallback at `app/routes/main.py:70-91`).
- Template uses `{% if data %}` guards on each chart card; empty state shows a
  muted "No data" placeholder instead of an empty chart canvas.
- Aggregations exclude null fields with `$match: {field: {$ne: null}}` so the
  "n=X" caption reflects the actual non-null sample.

## Testing

- **Unit tests** for the three builder methods in `tests/test_applicant_dashboard.py`
  (or matching the existing naming convention — to be confirmed in the plan).
  Each test uses an in-memory or mocked Mongo with 5–10 application docs
  covering: missing `self_reported`, missing `utm`, different counties, null
  `participant_match`. Asserts on the structure and counts of the returned
  dict.
- **Manual verification**: hit `/dashboard/applicants` against the live
  `empower_development` DB. Cross-check that:
  - total applicants on Overview matches `db.applications.countDocuments({})` (= 616)
  - top county on Overview matches a direct aggregation
  - n=X captions match `db.applications.countDocuments({field: {$ne: null}})`
- **No browser / E2E tests** — existing dashboards don't have any and adding
  them is out of scope for this feature.

## Out of Scope (Deferred)

- Geographic / county-choropleth tab
- Filter bar (date range, county, channel) that re-filters all charts
- Export-to-CSV button
- Drill-down from a chart bar into a filtered applicant list
- Real-time refresh / WebSocket push

## Open Questions

None blocking. The implementation plan can flag any nav-placement or naming
choices that surface during the build.

## Affected Files

- `app/routes/main.py` — new view function
- `app/services/campaign_data_service.py` — new service methods
- `app/templates/dashboards/applicants.html` — new template
- `app/templates/base.html` (or wherever the nav lives) — add menu link
- `tests/test_applicant_dashboard.py` — new unit tests

## Dependencies

None new. Uses existing Flask, Flask-Login, PyMongo, Bootstrap, Chart.js.
