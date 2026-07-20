# Octopus — Functional & UI/UX Specification

> **Purpose of this document.** A complete inventory of *what the current "octopus" application does* (functional pieces) and *how users interact with it* (UI/UX pieces), intended as the source-of-truth feature list for rebuilding the application from scratch. It describes the system as it exists today, not how a rebuild should be implemented.

**Generated:** 2026-06-14
**Scope reviewed:** `app/` (main Flask app), `client/` (advisor portal), `src/` (data & modeling pipeline), templates, static assets.

---

## 1. System Overview

Octopus is an internal **multi-channel campaign analytics + energy-data platform** for EmpowerSaves (an Ohio residential energy-savings program). It is two web applications plus an analytical backend that share one MongoDB database (`empower_development`).

| Component | Path | Port | Audience | Role |
|-----------|------|------|----------|------|
| **Main app** | `app/` | 5000 (CLI default 5006) | Internal staff / analysts | Campaign management, analytics dashboards, NL data exploration, Bayesian modeling |
| **Client app** | `client/` | 5001 | Consumer-facing / advisors | Per-household energy profile lookup + savings advisor |
| **Pipeline** | `src/` | n/a (batch) | Engineers / data team | Ingest, sync, clustering, Bayesian inference, enrichment tools |

**Core technology:** Flask (app-factory + blueprints), Flask-Login auth, MongoDB (PyMongo), SQLite/SQLAlchemy (users only), EmailOctopus API, Anthropic Claude API, Chart.js + Bootstrap 5 frontend, PyMC/ArviZ for Bayesian models, FAMD/K-prototypes/StepMix for clustering.

**Key data domains (MongoDB collections):**
- `campaigns` — all campaigns across channels (email/text/mailer/letter)
- `exposures` — per-participant send records (system of record for "reach")
- `participants` — unified person records w/ demographics
- `applications` / `applicants` — conversions (program applications) + energy-burden demographics
- `{County}CountyDemographic` — income, household size, energy costs per parcel
- `{County}CountyResidential` — home characteristics + energy percentile
- `users` — app login accounts (SQLite, not Mongo)

---

## 2. Functional Pieces (Main App)

### 2.1 Authentication & Accounts
- **Username/password login** (`/login`) with Flask-WTF/CSRF, hashed passwords (pbkdf2:sha256), "remember me", `is_active` gate, `last_login` tracking, and `next`-param post-login redirect.
- **Logout** (`/logout`).
- **User model** (`users` table): username, email, password_hash, full_name, role (default `super_user`), is_active, last_login, created_at, created_by.
- **30-minute session timeout**.
- **No public self-registration** — accounts created via CLI (internal-only app).
- **All dashboards/APIs require login** except landing page (`/`) and login.

### 2.2 CLI (`octopus` command)
- `octopus run` — dev server (host/port/debug flags).
- `octopus shell` — REPL w/ `app`, `db`, `User` in context.
- `octopus init-db` — create tables.
- `octopus version` — version + dependency versions.
- (User creation referenced as `octopus-create-user`.)

### 2.3 Main Dashboard (`/dashboard`)
Cross-channel overview aggregating from `CampaignDataService`:
- **Per-channel campaign counts** (email, text, mailer, letter) + key metrics.
- **Overall conversion stats** — participants (email+text), total applicants, conversion rate (`applicants / participants × 100`).
- **Recent applicants** (last 10) w/ name, location, match quality.
- **Applicant summary** — by county (top 10), by match method, top counties.

### 2.4 Email Campaign Analytics (`/dashboard/email`)
Combines **EmailOctopus API** (live campaign/list/contact counts) + **MongoDB** campaign records. Computes & charts:
- Messages **sent** by campaign.
- **Engagement** (opened vs clicked) by campaign.
- **Click-through rate** (clicked/opened %) by campaign.
- **Zip-code engagement** (top 20 zips, opened/clicked, min 10 participants/zip).
- API connection status indicator.

### 2.5 Text/SMS Campaign Analytics
- **List view** (`/dashboard/text`) — paginated (20/page) campaign table; totals for campaigns/sent/delivered/clicked; tolerant of legacy + modern schema shapes.
- **Detail view** (`/dashboard/text/<campaign_id>`) — the richest functional screen:
  - **Live engagement breakdown** computed from `exposures` (not cached stats): counts by `unified_status` (received, clicked, engaged, opted_out, undeliverable, negative_response, converted, no_engagement).
  - **Computed rates** — delivery, click, reply, opt-out.
  - **Message body** (the actual SMS template sent).
  - **Top zip codes** by exposure count.
  - **Related campaigns** in same campaign group (splits/retries).
  - **Attributed applications** count (via `attribution.likely_campaigns`).
  - **Paginated, searchable, status-filterable exposures table** (server-side `$facet` pagination, regex search on name/phone/zip/city, `$lookup` join to participants for names).

### 2.6 Applicants Dashboard (`/dashboard/applicants`)
Three tabs from `get_applicant_dashboard_data()`:
- **Overview** — KPIs (total, this month, match rate %, top county, top channel); applications-per-week time series (last 6 months, weekly buckets); match-quality donut; recent 25 applicants table.
- **Demographics** — histograms for age, household income, household size, and **energy burden** (joined from `applicants` collection on email); income-vs-age scatter colored by top-3 counties.
- **Attribution** — UTM medium/source/campaign bar charts; per-channel conversion table (exposures vs applications vs rate).
- Tolerant of partial failures (one bad tab doesn't crash the page).

### 2.7 Email Campaign Browser (`/campaigns`, EmailOctopus-backed)
- **List** all EmailOctopus campaigns (paginated 100/page) w/ status, subject, from, dates.
- **Detail** (`/campaigns/<id>`) — campaign metadata, statistics (open/click rates w/ progress bars), HTML + plain-text content preview, and a **participant table** filterable by status (all/subscribed/opened/clicked/bounced/complained/unsubscribed).
- **Enriched data** integration: read enriched CSV as JSON (`/api/campaigns/<id>/enriched-data`), **download enriched CSV** (`/campaigns/<id>/download-enriched`).
- **Savings histogram** (`/api/campaigns/<id>/savings-histogram`) — 10 equal-width bins over annual savings, total vs opened counts per bin (powers the savings-distribution chart).
- **JSON API** endpoints: `/api/campaigns`, `/api/campaigns/<id>`, `/api/test-connection`.

### 2.8 County Analysis (`/county-analysis`)
County-level demographic/energy exploration over `{County}CountyDemographic` + `{County}CountyResidential`:
- **Income distribution** (`POST /api/.../income-distribution`) — 8 income brackets, counts + mean/median/min/max.
- **Energy burden by income** (`POST /api/.../energy-burden-by-income`) — burden % histogram (11 bins) for a chosen bracket or all.
- **Energy percentile by income** (`POST /api/.../percentile-distribution-by-income`) — percentile-vs-comparable-homes histogram (10 bins), joining demographics→residential by `parcel_id`.
- Graceful "data unavailable / pending" responses when collections or percentiles aren't ready.

### 2.9 Explore — Natural-Language Data Query (`/explore`)
AI-driven querying of MongoDB in plain English (powered by Claude). Two engines:
- **Tools method** (`ExploreService`, default) — Claude orchestrates 7 read tools: `list_collections`, `get_document_sample`, `count_documents`, `find_documents`, `sample_documents`, `run_aggregation` (auto-limited to 100), `search_by_name` (handles name-order variants across county collections). Agentic loop up to 50 iterations.
- **Python method** (`ClaudeService`) — Claude writes & executes sandboxed Python (pandas/json/datetime/re/ObjectId) against the DB; 30s/script timeout, 100KB output cap, up to 15 iterations.
- Both return: interpretation, step-by-step reasoning trace, natural-language summary, structured result tables, and metadata.
- `POST /api/explore/query` (1000-char query limit), `GET /api/explore/stats`.

### 2.10 Bayesian Inference Models (`/inference-models`, `/dashboard/modeling`)
- **Model registry** lists all models w/ metadata, version, status, trained flag.
- **Per-model tabs:** DAG (image or text from `config.yaml`), description (purpose/features/hypotheses/notes), data summary (participants/observations/campaigns/counties + per-campaign & per-county click rates + missing-data report), model fit (R-hat/ESS/divergences, LOO/WAIC, trace plots), effectiveness (AUC-ROC/accuracy/calibration + coefficient table), validation (convergence/PPC/LOO cards, treatment-effects plot, E-values table).
- **Run inference** (`POST /inference-models/<id>/run`) — dynamic per-model parameter form (text/number/select/multiselect/boolean) → predictions (JSON).
- **Run validation** (`POST /inference-models/<id>/validate`) — full validation w/ optional plots + optional LOO CV; saves timestamped report.
- **Static artifact serving** (`/static/inference/<path>`) for DAGs/trace plots.

### 2.11 Placeholder / "Coming Soon" features
- **Mailer dashboard** (`/dashboard/mailer`) — planned print/mail stats.
- **Letter dashboard** (`/dashboard/letter`) — planned certified-mail/delivery tracking.
- **Participant Analysis** (`/analysis`) — planned geographic/demographic/engagement filtering + list export.
- **Participant export macro** — CSV/PDF/Excel buttons disabled ("coming soon").

---

## 3. Functional Pieces (Client App — Energy Advisor Portal, port 5001)

A separate, consumer-friendly single-page tool:
- **Search residents by name** (`/api/search`) w/ county filter + "participants only" toggle.
- **County list** (`/api/counties`) — currently Franklin, Cuyahoga.
- **Full household profile** (`/api/user/<parcel_id>`) — merges demographics (income, household size, electric/gas annual costs) + residential (sqft, age, beds/baths, stories) + **comparable homes** (±20% sqft, ±10yr age → average energy cost) + **energy percentile** vs similar homes + campaign-participant status.
- **Program eligibility** (`/api/programs`) — Ohio energy-assistance programs (HEAP, WAP, utility rebates, federal tax credits, LED) matched by income/household size vs Federal Poverty Level.
- **Savings estimates** (`/api/savings`) — annual savings + simple-payback years for ~10 improvement types (attic insulation, HVAC, smart thermostat, etc.).
- **AI chat advisor** (`/api/chat`) — conversational energy advisor (placeholder now; designed to call Claude).

---

## 4. Functional Pieces (Backend Pipeline — `src/`)

Not user-facing, but defines the data capabilities the apps depend on:

- **Sync (`src/sync/`)** — EmailOctopus → MongoDB ingest: paginated fetch across report types (sent/opened/clicked/bounced/complained/unsubscribed), idempotent upsert, engagement merge via `$max`, CSV export.
- **Models (`src/models/`)** — Pydantic schemas: Campaign, Participant, Applicant/Application, County demographic/residential/electrical/gas/loads, parcel/meter references, match info.
- **Clustering/Segmentation (`src/analysis/`)** — participant feature extraction (129K exposures → 7K participants); phased clustering (Phase 1 demographics FAMD+K-prototypes, Phase 2 +exposure features, Phase 3 StepMix probabilistic); HDBSCAN + UMAP exploration; silhouette/chi-square validation. Strategy: cluster on pre-treatment features, characterize by outcomes.
- **Bayesian models (`src/bayesian_models/`)** — hierarchical GLMs: baseline open, energy burden, demographics, campaign random effects, rate×energy×income interaction, click models, messaging effectiveness; registry + base class + data-summary.
- **Training (`src/bayesian_scripts/`)** — per-model fit scripts (configurable draws/chains) writing traces/reports/diagrams/checkpoints to `data/inference/{model_id}/`.
- **Modeling tools (`src/bayesian_tools/`)** — data prep/scaling, MCMC diagnostics, architecture/parameter-importance viz, CPU/GPU benchmark.
- **Reusable tools (`src/tools/`)** — Mongo singleton, EmailOctopus client, residence matcher (fuzzy address/name/phone linkage), CSV consolidator (engagement + demographics), schema explorer, comparables utilities.
- **Utilities (`src/utils/`)** — env vars, logging, on-demand engagement rollups (status hierarchy), county lookup, application parsers, ObjectId validator, singleton metaclass.

---

## 5. UI/UX Pieces

### 5.1 Global Shell, Branding & Theme
- **Dark theme** throughout. Backgrounds `#1a1d23` (page) / `#24282f` (cards) / `#2d3139`. Text `#e8eaed`/`#bdc1c6`/`#9aa0a6`.
- **Brand colors:** primary blue `#198fd9` (hover `#1577b5`), secondary green `#65bd7d`; channel accents incl. purple `#6f42c1`.
- **Sticky white navbar** w/ EmpowerSaves logo (40px) + "Campaign Dashboard"; nav links: Dashboard, Explore, County Analysis, user dropdown (logout).
- **Bootstrap 5** grid + components; **Chart.js** for all charts; Bootstrap Icons; breadcrumbs on subpages; sticky footer w/ copyright.
- **Flash messages** (dismissible, category-colored), spinners + full-page loading overlays, inline form validation.

### 5.2 Reusable Interactive Components
- **Sortable tables** (`sortable_table.js`) — click-to-sort headers, type-aware (text/number/date), `data-sort-value` overrides, ⇅/↑/↓ carets.
- **Clickable rows** (`clickable_rows.js`) — whole-row navigation via `data-href`, Cmd/Ctrl/middle-click → new tab, passes through clicks on nested controls.
- **DataTables.js** (campaign enriched-data tab) — search, length menu (10/25/50/100/All), column show/hide selector, CSV download.
- **Participant table macro** — shared contact table w/ status-filter buttons, hide/show "energy cost" columns toggle, status badges, pagination.
- **JSON viewer modal** (Explore) — syntax-highlighted, copy-to-clipboard, click-to-expand nested objects.

### 5.3 Page-by-Page UI Inventory

| Page | Key UI elements |
|------|-----------------|
| **Login** | Centered card; username/password/remember-me; inline validation; "internal app" note. |
| **Index/Landing** | Hero w/ SVG illustration + dual CTAs; 3 feature cards (📈/📊/🔄); primary CTA band (logged-out only). |
| **Main Dashboard** | 5 channel cards (icon, badge, big count, 3 metrics, hover lift); cross-channel summary table; conversions card; recent-applicants list w/ match badges; applicant analytics; inference-models card. |
| **Email Dashboard** | Connection-status badge; 3 stat cards; 4 Chart.js charts (sent, engagement, CTR, zip); quick-action buttons. |
| **Text Dashboard** | 3 stat cards; sortable+clickable campaign table w/ agency badges; Bootstrap pagination. |
| **Text Detail** | 6-card KPI strip w/ %s; Overview/Demographics/Attribution tabs; message-body blockquote; campaign-info grid + unified-status breakdown; top-zip table; related-campaigns table; **searchable/filterable/sortable/paginated exposures table** w/ sticky header. |
| **Applicants** | 5-card KPI strip; 3 tabs; time-series line, match-quality doughnut, recent-25 table; 4 demographic bar charts + income-age scatter; 3 UTM bar charts + channel-conversion table; charts auto-resize on tab show. |
| **Campaigns List** | Campaign table (name/subject/status badges/from/dates/actions); pagination; count alert. |
| **Campaign Detail** | Info + statistics cards w/ gradient progress bars; HTML/plain-text content tabs (sandboxed scroll); 3 data tabs — filterable participants (energy-cost toggle), DataTables enriched data (column selector + CSV), savings-distribution mixed chart (bars + open-rate line, triple axis) + 3 stat cards. |
| **County Analysis** | County dropdown + analyze button; income stats cards; histogram + pie; color-coded income-bracket button group; energy-burden stats + histogram; percentile histogram + coverage stats; async load w/ spinners + error alerts. |
| **Explore** | Large NL query input + "Ask" button; Tools/Python method radios; clickable example-query badges; data-context pills; collapsible agent-reasoning trace (color-coded steps); summary card; dynamic result tables (smart cell formatting, sort, paginate, CSV, expand-nested); JSON modal; metadata footer; loading overlay. |
| **Inference Models** | Model dropdown (reload on change) + info card; 7 tabs (DAG/Description/Data Summary/Model Fit/Effectiveness/Validation/Inference); metric cards w/ status badges; collapsible data tables; dynamic inference param form + side-by-side results; async validation run. |
| **Modeling Dashboard** | Model selector + refresh; model-details card; Train vs Run-Inference action cards (large icons); inference-params preview table; no-model fallback. |
| **Letter / Mailer / Analysis** | "Coming Soon" placeholder cards w/ planned-feature checklists and status badges. |

### 5.4 Client App UI (port 5001)
- **Single-page layout**, 3 panels:
  - **Left — Profile:** name/address/participant badge; **energy-percentile half-doughnut gauge** (green <30 / orange 30–70 / red >70); household info; annual energy costs vs comparables; energy-burden %; potential savings.
  - **Center — Chat:** conversational AI advisor w/ typing indicators + markdown.
  - **Right — Opportunities:** categorized recommendations (weatherization/HVAC/appliances/behavioral/programs), color-coded by category + priority, w/ estimated savings + contractor type.
- Search header w/ name + county filter + participants-only checkbox. Bootstrap 5 + Chart.js + Font Awesome.

### 5.5 Charts & Visualization (Chart.js)
Bar (campaign/demographic/engagement), line (time series), doughnut (match quality, percentile gauge), pie (income breakdown), scatter (income vs age), mixed bar+line (savings histogram w/ open-rate, triple Y-axis). Custom tooltips (%, thousands separators), red→yellow→green gradient palettes for income/burden.

### 5.6 Accessibility & Responsive
- Semantic HTML, ARIA (`aria-current`, tablist/tab roles, progressbar attrs, `role="alert"`), keyboard-navigable controls, focus states.
- Bootstrap responsive grid; `table-responsive` wrappers; stacked layouts + truncated pagination on small screens; charts `responsive: true`.

---

## 6. Cross-Cutting Behaviors to Preserve in a Rebuild

1. **Schema tolerance** — campaign/exposure data exists in *both* legacy (flat) and modern (nested) shapes; services coalesce via `$ifNull` chains. Any rebuild must read mixed shapes or migrate first.
2. **Exposures as system of record** — engagement metrics are computed *live* from `exposures`, not from cached campaign statistics.
3. **Attribution model** — applications link to campaigns via `attribution.likely_campaigns` and `attribution.utm.*`; conversion = applications/exposures per channel.
4. **Parcel-based linkage** — participants ↔ county demographic/residential data join on `parcel_id`; person search must handle multiple name orderings.
5. **AI exploration is agentic** — the Explore feature relies on Claude calling read-only Mongo tools (or sandboxed Python) in a loop and returning a reasoning trace + summary + tables.
6. **Two front-ends, one DB** — internal analytics app and consumer advisor portal are separate Flask apps sharing `empower_development`.
7. **Auth is internal-only** — login-gated, no self-registration, accounts provisioned via CLI.
8. **Modeling artifacts are file-based** — Bayesian model configs/traces/reports/diagrams live under `data/inference/{model_id}/` and are read by the web UI.

---

## 7. Feature Checklist (condensed, for rebuild parity)

**Auth:** login/logout · session timeout · user model · CLI user mgmt
**Dashboards:** main cross-channel · email · text (list + detail) · applicants (3 tabs) · mailer* · letter* (*placeholder)
**Email/EmailOctopus:** campaign list · campaign detail (stats/content/participants) · status filters · enriched CSV view + download · savings histogram · JSON API · connection test
**Text/SMS:** paginated list · live status breakdown · rates · message body · top zips · related campaigns · attributed apps · searchable exposures table
**Applicants:** KPIs · time series · match quality · demographics histograms · energy burden · income-age scatter · UTM attribution · channel conversion
**County analysis:** income distribution · energy burden by income · energy percentile by income
**Explore:** NL query (tools + python engines) · reasoning trace · result tables · CSV export · JSON viewer
**Modeling:** model registry · DAG/description/data-summary/fit/effectiveness/validation tabs · run inference · run validation · training scripts
**Client portal:** resident search · household profile · comparables · percentile gauge · program eligibility · savings estimates · AI chat
**Pipeline:** EmailOctopus sync · clustering (3 phases) · Bayesian models · residence matching · CSV consolidation · enrichment tools
**UI kit:** dark theme + brand · sortable tables · clickable rows · DataTables · participant macro · Chart.js suite · JSON modal · loading/flash/validation states · responsive + a11y
