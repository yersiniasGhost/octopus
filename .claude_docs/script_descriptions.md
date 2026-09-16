# Script Descriptions

Brief descriptions of utility scripts in the `scripts/` directory.

> See also: [`20260513_1508_database_schema.md`](20260513_1508_database_schema.md) — current MongoDB schema reference for `empower_development`.

## Campaign Management

### backfill_text_campaign_message_body_tool.py
**One-shot tool** (2026-05-13). Populates `campaigns.message_body` with the actual SMS template per text campaign so detail pages can show what was sent. Two sources:
1. **Primary** — `data/campaign_texting/Empower_Saves_Texts_All.csv` (per-send rendered bodies). Joins stats CSV's `action` → contacts CSV's `Contacted in Project`, normalizes per-recipient tokens (address, first name, dollar amounts) to placeholders, picks the modal form per campaign. Covers Text1-Text74 (74 updated).
2. **Fallback** — `data/campaign_texting/text_content.txt` (campaign-brief templates). Applied to Text75-84 + WCP IMPACT campaigns by mapping slot keywords (`LastDay`→Final Day, `EndsSoon`→Time running out, etc.). Covers 12 campaigns.

Only overwrites null/empty values or the legacy `"<slot> message campaign"` placeholder; pass `--force` to overwrite real content. Idempotent. Default dry-run; `--apply` to write.

**Usage:**
```bash
source venv/bin/activate
python scripts/backfill_text_campaign_message_body_tool.py
python scripts/backfill_text_campaign_message_body_tool.py --apply
python scripts/backfill_text_campaign_message_body_tool.py --verbose
```

### apply_cross_file_text_clicks_tool.py
**One-shot Fix #4 tool** (ran 2026-05-13). Aggregates cross-file `click_<slug>` evidence from all 10 Text75-84 vendor xlsx files and applies it to the corresponding owning campaign's exposures. Reverses the Stage-4 "stay in lane" policy for remediation, after the Stage 4b audit revealed ~0.5% of cross-file click signals were being lost. Same per-doc precedence as Stage 4 (received→clicked, engaged/opted_out→audit-only, undeliverable→skip). Idempotent. Default dry-run; `--apply` to write.

**Usage:**
```bash
source venv/bin/activate
python scripts/apply_cross_file_text_clicks_tool.py
python scripts/apply_cross_file_text_clicks_tool.py --apply
```

### backfill_wcp_text2_clicked_flag_tool.py
**One-shot Fix #1 tool** (ran 2026-05-13). Backfills `text_engagement.clicked=true` on the 2,111 docs in older WCP Text2 Section 1/2 campaigns (Jan 2026) that had `unified_status: "clicked"` without the underlying nested-field flag. `clicked_at` left as-is (original timestamps unknown). Idempotent. Default dry-run; `--apply`.

**Usage:**
```bash
source venv/bin/activate
python scripts/backfill_wcp_text2_clicked_flag_tool.py
python scripts/backfill_wcp_text2_clicked_flag_tool.py --apply
```

### audit_text75_84_cross_file_clicks_tool.py
**Read-only audit** (Stage 4b of Text75-84 ingest). For each of the 10 RumbleUp xlsx files, scans the Conversations Tags column for `click_<slug>` tokens belonging to OTHER campaigns and verifies the owning campaign has matching `text_engagement.clicked=true` exposures. Reports phones present in the owning campaign but NOT marked as clicked there — discrepancies are flagged but not auto-fixed (per Decision 3). Useful for sanity-checking cross-file corroboration of click data.

**Usage:**
```bash
source venv/bin/activate
python scripts/audit_text75_84_cross_file_clicks_tool.py
python scripts/audit_text75_84_cross_file_clicks_tool.py --verbose-missing  # show all flagged phones
```

### apply_text75_84_clicks_tool.py
**One-shot Stage 4 tool** for the Text75-84 ingest. Applies `click_<slug>` matches from each of the 10 RumbleUp xlsx files at `data/campaign-updated-20260512/` to corresponding exposures in `empower_development`. Strictly stays-in-lane (only this file's own slug is processed; cross-contamination tokens ignored per Decision 3). Per-doc precedence: received/no_engagement → promote to `unified_status: clicked` + set `text_engagement.clicked/clicked_at`; engaged/opted_out → audit-only (set click flag but keep status); undeliverable → skip. Matches by `contact_snapshot.phone` (dual-phone-safe). Idempotent. Default dry-run; `--apply` to write; `--files key1,key2` filter.

**Usage:**
```bash
source venv/bin/activate
python scripts/apply_text75_84_clicks_tool.py
python scripts/apply_text75_84_clicks_tool.py --apply
python scripts/apply_text75_84_clicks_tool.py --files text79,text80 --apply
```

### ingest_text75_84_exposures_tool.py
**One-shot Stage 3 ingestor** of Text75-84 RumbleUp xlsx files from `data/campaign-updated-20260512/`. Per-file actions via `FILE_PLAN` table: `wipe` (delete old UUID-keyed campaign + exposures, then re-create from xlsx — used for Text75/76), `create` (insert new campaign + exposures — used for Text77/78), `reset_clicks` (downgrade unified_status: clicked → received and clear text_engagement.clicked — used for Text83). No exposure changes for Text79-82/Text84 (Stage 4 only). Reads the third tag column ('Tags') that the existing impact-cold helper misses. Writes both participant_id and participant_oid at insert time. Does NOT write engagement_summary (removed 2026-05-13). Default dry-run; `--apply` to write; `--files key1,key2` filters scope.

**NOT idempotent for create/wipe actions** (re-running --apply on Text77/78 would duplicate exposures because no pre-insert dedup). reset_clicks is idempotent (second run finds 0 docs with unified_status=clicked).

**Usage:**
```bash
source venv/bin/activate
python scripts/ingest_text75_84_exposures_tool.py
python scripts/ingest_text75_84_exposures_tool.py --apply
python scripts/ingest_text75_84_exposures_tool.py --files text75,text83 --apply
```

### cleanup_duplicate_text_exposures_tool.py
**One-shot diagnostic** (Stage 2 of Text75-84 ingest work, ran 2026-05-13 — NOT applied; tool kept for future use). Scans `db.exposures` for `(campaign_id, participant_id)` duplicate pairs in text-channel campaigns. For each duplicate group, reports KEEP/DROP candidates (by earliest `created_at`) with field-level diff hints. Default dry-run; `--apply` would delete dropped candidates; `--campaigns id1,id2` limits scope.

**Important caveat:** the May 2026 run on Text79-84 surfaced 3 "duplicates" that turned out to be legitimate dual-phone sends (same contact, two phones, both folded under one participant by the matcher). The tool's keep-earliest heuristic is correct for true vendor-retry duplicates but wrong for dual-phone-send cases. Always inspect the `contact_snapshot` diff before applying.

**Usage:**
```bash
source venv/bin/activate
python scripts/cleanup_duplicate_text_exposures_tool.py
python scripts/cleanup_duplicate_text_exposures_tool.py --campaigns text_impact_cold_79
python scripts/cleanup_duplicate_text_exposures_tool.py --apply
```

### migrate_text_engagement_clicked_tool.py
**One-shot migration** (Stage 0 of Text75-84 ingest work, completed 2026-05-13). Folds the legacy top-level `text_clicked` / `text_clicked_at` fields on `db.exposures` into the proper nested path `text_engagement.clicked` / `text_engagement.clicked_at`. Two passes: (A) 1,134 True docs migrate value + preserve clicked_at, (B) 16,767 False docs (junk default from impact-cold tool family) just `$unset` the legacy fields. Idempotent — re-runs after success move zero docs. Default dry-run; `--apply` to write. See `.claude_docs/20260513_1530_database_changes_log.md` entry `migrate-text-engagement-clicked` for the full migration record.

**Usage:**
```bash
source venv/bin/activate
python scripts/migrate_text_engagement_clicked_tool.py            # dry-run
python scripts/migrate_text_engagement_clicked_tool.py --apply
```

### investigate_text75_84_state_tool.py
**One-shot investigation** (Stage 1 of the Text75-84 click-ingestion workflow). Surveys the 10 EmpowerSaves_OH_Text{75..84} workbooks at `data/campaign-updated-20260512/` against the live `empower_development` DB and emits a per-file markdown report. For each file: extracts Stats-sheet source-of-truth (sent count, slug, action #, reply tag), counts `click_<slug>` tokens (including cross-contamination from other campaigns), finds candidate campaign docs in DB, profiles existing exposures (status distribution, sent_at range, duplicates, orphan FKs, legacy off-model `text_clicked` count, dual-keyed participants), and computes file-vs-DB phone deltas. Pure reads; no DB writes. Reads all three tag columns from the Conversations sheet ('Msg Tags', 'Contact Tags', and the contact-aggregated 'Tags' column the existing impact-cold helper misses). Report path: `.claude_docs/<ts>_text75_84_state_investigation.md`.

**Usage:**
```bash
source venv/bin/activate
python scripts/investigate_text75_84_state_tool.py
python scripts/investigate_text75_84_state_tool.py --report-path /tmp/x.md
```

### populate_participant_oid_tool.py
**Reusable Tool**: Backfills `exposures.participant_oid` (ObjectId reference to `participants._id`) from the existing `participant_id` natural key. Adds a denormalized FK alongside the natural key — does NOT modify `participant_id`. Idempotent: re-runs only touch exposures missing the field. Default is dry-run; pass `--apply` to write. Reports orphan participant_ids (exposures whose participant_id doesn't match any participant) so referential integrity issues surface before writes.

**Usage:**
```bash
source venv/bin/activate
python scripts/populate_participant_oid_tool.py --dry-run                # default
python scripts/populate_participant_oid_tool.py --apply
python scripts/populate_participant_oid_tool.py --apply --batch-size 500
```

### extract_text_campaigns.py
Extracts text/SMS campaign data from Excel file (`Empower_Saves_Texts_All.xlsx`) and imports into MongoDB `text_campaigns` collection. Parses campaign metadata from shortened names (format: `Text#_MessageKey_Agency_Time`), validates data, and provides options for dry-run mode, JSON export, or direct MongoDB insertion. Supports verbose logging for debugging and data validation.

**Usage:**
```bash
# Dry run (validation only)
python scripts/extract_text_campaigns.py --dry-run --verbose

# Import to MongoDB
python scripts/extract_text_campaigns.py --output mongo --verbose

# Export to JSON
python scripts/extract_text_campaigns.py --output json --json-file campaigns.json

# Both MongoDB and JSON
python scripts/extract_text_campaigns.py --output both
```

### create_text_campaign_tool.py
**Reusable Tool**: Creates text/SMS campaign records in MongoDB campaigns collection. Use this to set up new text campaigns before importing conversation data. Generates UUID campaign IDs and initializes TextStatistics structure.

**Usage:**
```bash
# Create a new text campaign
python scripts/create_text_campaign_tool.py --name "Text1_Prequalified_Impact" --agency "IMPACT"

# With description
python scripts/create_text_campaign_tool.py --name "Text2_FollowUp" --agency "OHCAC" --description "Follow-up outreach campaign"
```

### import_text_conversations_tool.py
**Reusable Tool**: Imports text conversation data from Excel (Conversations worksheet) into MongoDB participants collection with enhanced 8-strategy residence/demographic matching. Groups messages by phone number, performs comprehensive matching using src/tools/residence_matcher.py, creates Participant records with TextEngagement tracking, and updates campaign statistics. Supports dry-run mode for validation before import.

**Features:**
- Loads 47K+ conversation records from Excel
- Groups conversations by phone number (creates one Participant per contact)
- Enhanced 8-strategy matching via ResidenceMatcher:
  1. Email (fastest, most reliable)
  2. Name (fuzzy matching with normalization)
  3. Phone (normalized comparison)
  4. Exact address
  5. Normalized address (street/directional abbreviations)
  6. State route variations (OH-314, US-40 patterns)
  7. Hyphenated roads ("Cadiz-New Athens Rd")
  8. Fuzzy address (similarity scoring)
- Creates TextEngagement with message counts, timestamps, reply/opt-out tracking
- Updates Campaign statistics (sent, delivered, failed, opt-outs)
- Supports update-existing for re-imports
- --limit flag for testing with subset of data

**Usage:**
```bash
# Dry run (validation only)
python scripts/import_text_conversations_tool.py \
    --campaign-id 690b0058eadaad6f0e0dbfb3 \
    --dry-run --verbose

# Full import
python scripts/import_text_conversations_tool.py \
    --campaign-id 690b0058eadaad6f0e0dbfb3

# Custom Excel file
python scripts/import_text_conversations_tool.py \
    --excel data/campaign_texting/custom.xlsx \
    --sheet Conversations \
    --campaign-id <campaign_id>
```

### extract_campaign_emails.py
Extracts email campaign participant data from EmailOctopus campaign exports and processes for analysis.

## Residence Matching & Applicant Import

### match_csv_to_residence.py
**Enhanced with 8-Strategy Comprehensive Matching**: Matches CSV applicant data to residence/demographic records using the reusable ResidenceMatcher tool from `src/tools/residence_matcher.py`. Achieves 93.6% match rate (277/296 applicants) using 8 strategies: email matching (fastest, most reliable), name matching (fuzzy logic), phone matching, exact address, normalized address, state route variations (OH-314, US-40), hyphenated roads, and fuzzy address scoring. Provides detailed match statistics and quality reporting.

**Usage:**
```bash
source venv/bin/activate
python scripts/match_csv_to_residence.py
```

**Output:** Detailed match results showing exact/good/fuzzy/demographic matches with statistics breakdown.

### populate_applicants_db_v3.py
**Reusable Tool**: Populates the `empower.applicants` MongoDB collection from CSV applicant data using comprehensive 8-strategy matching via ResidenceMatcher. Clears existing applicants collection and imports fresh data with match quality scoring (exact/high/medium/no_match). Creates Applicant models with ResidenceReference and DemographicReference links. Provides detailed import statistics showing match method distribution.

**Features:**
- Uses same 8-strategy matching as match_csv_to_residence.py
- 93.6% match rate achievement (277/296 applicants)
- Email matches: 47.3%, Name matches: 28.4%, Phone: 8.4%
- Address matches: 8.5% combined (normalized/fuzzy/state route)
- Only 6.4% unmatched (19 applicants)
- Bulk insert optimization for performance
- Comprehensive error handling and statistics

**Usage:**
```bash
source venv/bin/activate
python scripts/populate_applicants_db_v3.py
```

**Output:** Import statistics with match method breakdown and total matched percentage.

### debug_residence_match.py
Debugging tool for investigating residence matching issues. Provides detailed logging of match attempts, scores, and candidate selection.

## Data Analysis

### analyze_unmatched.py
Analyzes applicant records that failed to match to residences. Generates reports on common failure patterns and data quality issues.

### check_engagement.py
Analyzes campaign engagement metrics across different data sources and validates engagement tracking accuracy.

### count_csv_engagement.py
Counts engagement events (opens, clicks) from CSV campaign exports for statistical analysis.

## User & Database Management

### create_user.py
Creates new user accounts in the system with proper authentication setup.

### list_mongo_databases.py
Lists all available MongoDB databases and collections for database exploration and verification.

### find_demographic_collections.py
Searches for demographic data collections across MongoDB databases and reports their structure and availability.

## Database Migration

### migrate_to_campaign_data_tool.py
**Reusable Tool**: Comprehensive migration tool that creates and populates the new `campaign_data` database from CSV exports and county data. Replaces the poorly-structured `emailoctopus_db` with a well-designed schema featuring normalized participants, denormalized demographics/residence data, and unified engagement status (no_engagement/received/engaged).

**Features:**
- Phase 1 (setup): Creates database, collections, and indexes
- Phase 2 (import): Imports CSV files, deduplicates participants, creates campaign exposures
- Phase 3 (match): Matches participants to county demographic/residential data using 8-strategy ResidenceMatcher
- Phase 4 (summarize): Computes pre-aggregated engagement summaries per participant
- Phase 5 (stats): Updates campaign-level aggregate statistics
- Supports multi-channel campaigns (email, text_morning, text_evening, mailer, letter)
- Creates `analysis_ready` flag for clustering-ready data export

**Usage:**
```bash
# Dry run - analyze what would be migrated
python scripts/migrate_to_campaign_data_tool.py --dry-run

# Full live migration
python scripts/migrate_to_campaign_data_tool.py --live

# Run specific phase only
python scripts/migrate_to_campaign_data_tool.py --live --phase setup
python scripts/migrate_to_campaign_data_tool.py --live --phase import
python scripts/migrate_to_campaign_data_tool.py --live --phase match
python scripts/migrate_to_campaign_data_tool.py --live --phase summarize

# Limit records for testing
python scripts/migrate_to_campaign_data_tool.py --live --limit 1000
```

**Output:** Migration statistics including CSV processing counts, participant deduplication, match rates by method, and engagement distribution.

### rematch_participants_tool.py
**Reusable Tool**: Re-runs residence/demographic matching for participants lacking references using the corrected zipcode-to-county cache and 8-strategy ResidenceMatcher.

**Usage:**
```bash
# Dry run
python scripts/rematch_participants_tool.py --dry-run

# Live update
python scripts/rematch_participants_tool.py --live

# Limit for testing
python scripts/rematch_participants_tool.py --dry-run --limit 100 --verbose
```

### rematch_campaign_data_tool.py
**Reusable Tool**: Re-runs residence/demographic matching for unmatched participants in the `campaign_data` database. Key features:
- Pulls phone/address data from `campaign_exposures.contact_snapshot` (data stored at campaign send time)
- Builds ZIP-to-counties map supporting multi-county ZIP codes (e.g., ZIP 44813 spans RichlandCounty and HuronCounty)
- Tries matching across ALL counties for a given ZIP, ordered by data volume
- Uses 8-strategy ResidenceMatcher (email, name, phone, address variations)

**Usage:**
```bash
# Dry run - see what would change
python scripts/rematch_campaign_data_tool.py --dry-run

# Live update
python scripts/rematch_campaign_data_tool.py --live

# With verbose output
python scripts/rematch_campaign_data_tool.py --live --verbose

# Limit for testing
python scripts/rematch_campaign_data_tool.py --dry-run --limit 100
```

**Output:** Statistics showing newly matched participants, match methods used, and by-county breakdown.

## Data Enrichment

### enrich_participants.py
Enriches campaign participant records with additional demographic and engagement data from multiple sources.

### export_matched_data.py
Exports matched residence and applicant data to CSV format for external analysis and reporting.

## Clustering Analysis (src/analysis/)

Analysis scripts implementing the progressive clustering strategy from CLUSTERING_PROJECT.md.

### extract_participant_features.py
Extracts and aggregates participant-level features from `campaign_data` database for clustering analysis. Aggregates from observation level (129K exposures) to participant level (7K participants), separates pre-treatment features from behavioral outcomes, and handles missing values appropriately.

**Output:**
- `data/participant_features.parquet` - Full dataset
- `data/participant_features_analysis.parquet` - Filtered for analysis

**Usage:**
```bash
python -m src.analysis.extract_participant_features
```

### phase1_demographics_clustering.py
Phase 1 of progressive clustering: Demographics-only analysis using FAMD for dimensionality reduction and K-prototypes for mixed-data clustering. Clusters on pre-treatment features only, then validates clusters by analyzing engagement rates.

**Key Finding:** Demographics alone don't predict engagement (chi-square p=0.85).

**Output:**
- `data/clustering_results/phase1_cluster_analysis.png`
- `data/clustering_results/phase1_clustered_participants.parquet`

**Usage:**
```bash
python -m src.analysis.phase1_demographics_clustering
```

### phase1_hdbscan_exploration.py
Exploratory density-based clustering with HDBSCAN. Automatically determines cluster count and identifies outliers/noise points. Complements K-prototypes by discovering structure without assumptions.

**Output:**
- `data/clustering_results/hdbscan_clustered_participants.parquet`
- `data/clustering_results/hdbscan_*.png`

**Usage:**
```bash
python -m src.analysis.phase1_hdbscan_exploration
```

### phase2_campaign_exposure_clustering.py
Phase 2: Adds campaign exposure patterns to demographics. Tests whether campaign-level factors (number of campaigns, channel distribution, exposure duration) predict engagement better than demographics alone.

**Key Finding:** Adding exposure improves prediction slightly (p=0.18) but not significantly.

**Output:**
- `data/clustering_results/phase2_cluster_analysis.png`
- `data/clustering_results/phase2_clustered_participants.parquet`

**Usage:**
```bash
python -m src.analysis.phase2_campaign_exposure_clustering
```

### phase3_stepmix_probabilistic.py
Phase 3: BayesianGaussianMixture clustering for Bayesian model integration. Provides soft cluster assignments (posterior probabilities) that can be used as covariates in PyMC causal models. Auto-determines effective cluster count using Dirichlet process prior.

**Key Finding:** SIGNIFICANT (p=0.0007)! Engagement rates range 0.4% to 7.7% across clusters.

**Output:**
- `data/clustering_results/phase3_bayesian_integration.parquet` - For PyMC
- `data/clustering_results/cluster_probabilities.npy` - Probability matrix

**Usage:**
```bash
python -m src.analysis.phase3_stepmix_probabilistic
```

### umap_visualization.py
UMAP 2D visualizations with rare outcome emphasis. Plots non-engaged participants as small transparent points, engaged as large opaque - revealing patterns in sparse engagement data.

**Output:**
- `data/clustering_results/umap_comprehensive_dashboard.png`
- `data/clustering_results/umap_parameter_comparison.png`
- `data/clustering_results/umap_coordinates.parquet`

**Usage:**
```bash
python -m src.analysis.umap_visualization
```

### cluster_validation.py
Comprehensive validation including silhouette analysis, bootstrap stability testing, and predictive power comparison across all phases.

**Key Findings:**
- Silhouette: 0.161 (weak structure)
- Stability ARI: 0.80 (stable)
- Phase 3 best predictor (p=0.0007)
- Key differentiators: campaign_count (+103%), income (+38%), energy_burden (-17%)

**Output:**
- `data/clustering_results/cluster_validation_report.png`
- `data/clustering_results/validation_summary.csv`

**Usage:**
```bash
python -m src.analysis.cluster_validation
```

---

*Last updated: 2025-12-08*

## Application (Conversion) Ingestion

### scripts/ingest_applications.py
**Purpose**: Ingest program applications (conversions) from CSV into MongoDB `applications` collection.

Applications represent the ultimate outcome in the campaign funnel - people who completed the sign-up form. This data is used to:
- Validate clustering effectiveness (which clusters convert?)
- Attribution analysis (which campaigns drove conversions?)
- Compare self-reported vs modeled demographics

Features:
- Parses GravityForms CSV exports with 50+ columns
- Normalizes messy data formats (income: "$100,000", "1850mo", "40,000"; phone: "(614)499-2431")
- Extracts UTM attribution from source URLs (utm_source, utm_medium, utm_campaign, utm_content)
- Matches to existing participants by email → phone
- Creates indexes for efficient querying

Usage:
```bash
# Ingest applications with participant matching
python scripts/ingest_applications.py data/applications/APPLICANTS_sign-up-today-2025-09-03.csv

# Skip participant matching
python scripts/ingest_applications.py data/applications/APPLICANTS.csv --no-match

# View collection summary only
python scripts/ingest_applications.py --summary-only
```

Output: Applications collection with 296 records, 71% matched to participants, 65% with UTM attribution.

### scripts/attribute_applications_to_campaigns.py
**Purpose**: Attribute applications to likely influential campaigns using UTM data and date-based inference.

Attribution methods (in priority order):
1. **UTM Direct**: Parse utm_medium, utm_campaign, utm_content to match campaigns
2. **Date Window**: Find campaigns sent to applicant's county within N days before application

For matched participants, uses their actual campaign_exposures for higher-confidence attribution.

Usage:
```bash
# Run attribution with default 14-day window
python scripts/attribute_applications_to_campaigns.py

# Use 7-day window
python scripts/attribute_applications_to_campaigns.py --window-days 7

# Dry run (no database updates)
python scripts/attribute_applications_to_campaigns.py --dry-run

# View attribution summary only
python scripts/attribute_applications_to_campaigns.py --summary-only
```

Output: 85.8% of applications attributed to campaigns. Top campaigns and confidence distributions reported.

## scripts/dryrun_text_participant_matching.py
**Purpose**: Dry-run script to analyze participant matching for text campaign ingestion.

Analyzes unique contacts from text campaign data against existing participants in campaign_data database. Reports match rates by method (email, phone, address), identifies new participants that need creation, and analyzes county distribution for residential/demographic data lookup.

Key outputs:
- Match statistics by method (email/phone/address)
- List of unmatched contacts needing new participant records
- County distribution for demographic lookup planning
- Exports unmatched contacts to `data/campaign_texting/compact/unmatched_contacts.csv`

## scripts/ingest_text_campaigns.py
**Purpose**: Ingest text campaigns from RumbleUp/texting platform into campaign_data database.

Reads `data/campaign_texting/compact/campaigns.csv` and creates Campaign documents in the `campaigns` collection with:
- `campaign_id`: `text_{action}` format
- `channel`: "text"
- `source_system`: "rumbleup"
- Statistics: sent, delivered, replies, etc.

Usage:
```bash
python scripts/ingest_text_campaigns.py [--dry-run]
```

## scripts/ingest_text_exposures.py
**Purpose**: Ingest text campaign exposures and participants into campaign_data database.

Handles:
1. Matching contacts to existing participants (by email → phone → address)
2. Creating new participants for unmatched contacts (using phone as participant_id)
3. Creating CampaignExposure records for each outbound message
4. Updating participant engagement summaries

Key features:
- Zip code to county inference for new participants
- Reply detection from inbound messages
- Batch processing with configurable batch size
- Engagement summary updates (by_channel.text)

Usage:
```bash
python scripts/ingest_text_exposures.py [--dry-run] [--batch-size N]
```

## Analysis-04: Applicant-Centric Cluster Analysis (src/analysis/analysis-04/)

Analysis-04 focuses on understanding what drives program applications (conversions) across all campaign channels. Key difference from Analysis-03: outcome is `is_applicant` (binary) instead of engagement metrics.

### extract_applicant_features.py
**Purpose**: Extract unified participant features with applicant outcome flag for clustering.

Key features:
- Merges participants, campaign exposures, and applications
- Self-reported demographics for applicants → participant fallback for non-applicants
- Channel combo features: letter_only, letter+email, letter+text, letter+email+text
- UTM attribution: channel_of_conversion for applicants
- Creates demographics discrepancy report

Output:
- `data/clustering_results-04/participant_applicant_features.parquet`
- `data/clustering_results-04/demographics_discrepancy_report.csv`

Usage:
```bash
python -m src.analysis.analysis-04.extract_applicant_features
```

### phase1_demographics_clustering.py
**Purpose**: Phase 1 demographics-only clustering to establish baseline.

Uses FAMD + K-Means on demographic features. Tests whether demographics alone predict application rates.

Key findings:
- 5 clusters identified
- Chi-square p < 0.001 (significant)
- Modest predictive power (1.62% spread)

Output: `phase1_clustered.parquet`, `phase1_cluster_stats.csv`

### phase2_campaign_exposure_clustering.py
**Purpose**: Phase 2 adds campaign channel and message type features.

Key findings:
- 6 clusters identified
- Letter+Text only: 4.29% app rate (1.34x lift)
- Letter+Email only: 1.42% app rate (0.44x lift)
- Text campaigns drive higher conversions!

Output: `phase2_clustered.parquet`, `phase2_cluster_stats.csv`

### phase3_probabilistic_clustering.py
**Purpose**: Bayesian Gaussian Mixture for soft cluster assignments.

Creates outputs ready for PyMC causal modeling:
- Soft cluster probabilities (K-1 columns)
- Treatment indicators (has_text_treatment, has_email_treatment)
- Standardized features for modeling

Key findings:
- Cluster 0: 23.44% app rate (7.3x lift) - super-converters
- Naive text effect: +2.62 percentage points vs email-only

Output:
- `phase3_bayesian_integration.parquet` (main PyMC data)
- `phase3_cluster_probs.npy` (soft assignments)
- `phase3_pymc_summary.json` (metadata)

### umap_visualization.py
**Purpose**: UMAP visualizations for applicant analysis.

Generates:
- `umap_applicant_distribution.png`: Applicants vs non-applicants
- `umap_phase3_clusters.png`: 10 probabilistic clusters
- `umap_channel_exposure.png`: Channel patterns
- `umap_treatment_effect.png`: Text campaign visualization
- `umap_summary_dashboard.png`: Combined 4-panel dashboard

Usage:
```bash
python -m src.analysis.analysis-04.umap_visualization
```

### ANALYSIS_REPORT.md
Full analysis report with key findings, methodology, and Bayesian modeling recommendations located at `data/clustering_results-04/ANALYSIS_REPORT.md`.

## Demographic Enrichment

### enrich_demographics_from_bolt.py
**Purpose**: Enrich existing county demographic documents with additional fields from BOLT analysis Excel files.

Reads BOLT analysis files (from data enrichment vendor with MD_ prefixed fields) and updates existing demographic documents in `empower_development` database with:
- `owner_age`: Age in 2-year increments
- `number_of_adults`: Household adult count
- `marital_status`: Single/Married
- `presence_of_children`: Yes/No
- `estimated_home_value`: Dollar amount
- Additional fields where available: gender, dwelling_type, home_owner, presence_of_senior, education, etc.

Key features:
- Only updates EXISTING documents (no new inserts)
- Matches by parcel_id (primary) or address (fallback)
- Tracks and reports unmatched records to CSV
- Supports multi-county files via county column detection
- Dry-run mode for validation before updates

Files processed:
- `allen__EmpowerSaves_BOLT Analysis_20250310.xlsx` → AllenCountyDemographic
- `fayette_EmpowerSaves_BOLT Analysis_20250310.xlsx` → FayetteCountyDemographic
- `Richland_EmpowerSaves_BOL Analysis_20250317.xlsx` → RichlandCountyDemographic
- `HHWP_EmpowerSaves_BOLT Analysis_20250220.xlsx` → Hancock, Putnam, Wyandot
- `EmpowerSaves-OHCAC_BOLT ANALYSIS_2050228.xlsx` → Marion, Morrow, Richland
- `EmpowerSaves_COAD_BOLT Analysis_with costs_20250507.xlsx` → COAD counties
- `IMPACT_EmpowerSaves_BOLT ANALYSIS_with costs_for texting_20250509.xlsx` → Franklin

Usage:
```bash
# Dry run - show what would be updated
python scripts/enrich_demographics_from_bolt.py --dry-run

# Update all files
python scripts/enrich_demographics_from_bolt.py

# Update specific file only
python scripts/enrich_demographics_from_bolt.py --file Fayette
python scripts/enrich_demographics_from_bolt.py --file Allen --dry-run
```

Output: Updates 7,197 documents across 8+ collections with demographic enrichment fields.

## Bayesian-Fable Model Series (src/bayesian-fable/)

### run_fable.py
**Purpose**: CLI for the third-generation (McElreath-style) model series — f01 campaign pooling ladder, f02 weather→text engagement, f03 cooling-dose salience (flagship), f04 Text75–84 vs EGE-control ITT, f05 ordered engagement ladder. Design doc: [`20260709_1745_bayesian_fable_model_series.md`](20260709_1745_bayesian_fable_model_series.md).

Modes per model: `simulate` (fit on generative synthetic data, report parameter recovery — no MongoDB needed), `prior` (prior predictive check only), `fit` (full workflow: prior predictive → NUTS with log-likelihood → convergence gate via `src.bayesian_models.validation` → posterior predictive → persist to `data/inference/fable/<model_id>/`), plus `balance` (f04 covariate-balance table, run before fitting).

Usage:
```bash
source venv/bin/activate
python src/bayesian-fable/run_fable.py f01 simulate
python src/bayesian-fable/run_fable.py f01 fit --variant all --channel text   # pooling ladder + LOO
python src/bayesian-fable/run_fable.py f03 fit --variant reliable             # kwh_cl_r2 >= 0.5 subset
python src/bayesian-fable/run_fable.py f04 balance --csv <combined-export.csv>
```

## Bayesian Model Training (src/bayesian_scripts/)

### train_model_01_baseline.py
**Purpose**: Train the Baseline Email Open Model (Model 01) using the registry-based architecture.

Trains a simple logistic regression model predicting email opens based on energy cost and savings potential. This establishes baseline predictive performance before adding energy burden and demographic confounders.

Features:
- Uses `BaseBayesianModel` base class with standard interface
- Outputs saved to `data/inference/model_01_baseline/`:
  - `traces/`: MCMC trace files (.nc NetCDF format)
  - `reports/`: Training results, coefficients, odds ratios
  - `diagrams/`: DAG visualization, trace plots, posterior plots
  - `checkpoints/`: Scaler parameters for inference
- Generates diagnostic plots (trace, posterior, forest)
- Computes odds ratios with credibility assessments
- Supports dry-run mode for data validation

Usage:
```bash
# Train with defaults (2000 draws, 4 chains)
python src/bayesian_scripts/train_model_01_baseline.py

# Custom sampling parameters
python src/bayesian_scripts/train_model_01_baseline.py --draws 3000 --chains 4 --tune 1500

# Dry run - load data only, no training
python src/bayesian_scripts/train_model_01_baseline.py --dry-run

# View all options
python src/bayesian_scripts/train_model_01_baseline.py --help
```

Output: Model artifacts in `data/inference/model_01_baseline/` ready for UI visualization and inference.

### train_model_02_energy_burden.py
**Purpose**: Train the Energy Burden Email Open Model (Model 02) using the registry-based architecture.

Tests the hypothesis: households with high energy burden (>6% of income) have higher email open rates, controlling for income level and household size.

Features:
- Extends `BaseBayesianModel` with standard interface
- Three predictors with confounders:
  - `beta_burden`: Energy burden (primary hypothesis - expected positive)
  - `beta_income`: Income level (confounder - expected negative)
  - `beta_hhsize`: Household size (confounder - expected positive)
- Outputs saved to `data/inference/model_02_energy_burden/`:
  - `traces/`: MCMC trace files (.nc NetCDF format)
  - `reports/`: Training results with hypothesis test outcomes
  - `diagrams/`: DAG visualization, trace plots, posterior plots, forest plots
  - `checkpoints/`: Scaler parameters for inference
- Hypothesis test result reported (SUPPORTED/REJECTED/INCONCLUSIVE)
- Supports dry-run mode for data validation

Usage:
```bash
# Train with defaults (2000 draws, 4 chains)
python src/bayesian_scripts/train_model_02_energy_burden.py

# Custom sampling parameters
python src/bayesian_scripts/train_model_02_energy_burden.py --draws 3000 --chains 4 --tune 1500

# Dry run - load data only, no training
python src/bayesian_scripts/train_model_02_energy_burden.py --dry-run

# View all options
python src/bayesian_scripts/train_model_02_energy_burden.py --help
```

Output: Model artifacts in `data/inference/model_02_energy_burden/` ready for UI visualization and inference.

### train_model_03_demographics.py
**Purpose**: Train the Demographics Email Open Model (Model 03) using the registry-based architecture.

Tests the hypothesis: does electricity usage (kWh) predict email open rates, controlling for energy burden, income level, and household size?

Features:
- Extends `BaseBayesianModel` with standard interface
- Four predictors including new kWh usage:
  - `beta_burden`: Energy burden (expected positive)
  - `beta_income`: Income level (confounder - expected negative)
  - `beta_hhsize`: Household size (confounder - expected positive)
  - `beta_kwh`: Annual kWh usage (NEW hypothesis - expected positive, higher usage → higher salience)
- Outputs saved to `data/inference/model_03_demographics/`:
  - `traces/`: MCMC trace files (.nc NetCDF format)
  - `reports/`: Training results with kWh hypothesis test outcomes
  - `diagrams/`: DAG visualization, trace plots, posterior plots, forest plots
  - `checkpoints/`: Scaler parameters for inference
- Hypothesis test result reported (SUPPORTED/REJECTED/INCONCLUSIVE) for kWh usage effect
- Supports dry-run mode for data validation

Usage:
```bash
# Train with defaults (2000 draws, 4 chains)
python src/bayesian_scripts/train_model_03_demographics.py

# Custom sampling parameters
python src/bayesian_scripts/train_model_03_demographics.py --draws 3000 --chains 4 --tune 1500

# Dry run - load data only, no training
python src/bayesian_scripts/train_model_03_demographics.py --dry-run

# View all options
python src/bayesian_scripts/train_model_03_demographics.py --help
```

Output: Model artifacts in `data/inference/model_03_demographics/` ready for UI visualization and inference.

### train_messaging_effectiveness.py
**Purpose**: Train the 2-Stage Messaging Effectiveness Model using the registry-based architecture.

Analyzes the email campaign funnel with hierarchical Bayesian modeling:
- Stage 1: P(Open | features) - What drives email opens?
- Stage 2: P(Click | Open, features) - What drives clicks among openers?

Features:
- 2-stage hierarchical model with campaign random effects
- Non-centered parameterization for stable MCMC sampling
- Multiple effect types:
  - Campaign random effects (partial pooling across campaigns)
  - Message type effects (cost_framing, savings_framing, urgency, personalization, etc.)
  - Location effects (city/zip geographic variation)
  - Monthly seasonal effects (12 month indicators)
  - Offer characteristics (savings, cost, kWh as continuous predictors)
- Outputs saved to `data/inference/messaging_effectiveness/`:
  - `traces/`: MCMC trace files (.nc NetCDF format)
  - `reports/`: Effect summaries, diagnostics, campaign rankings
  - `diagrams/`: Trace plots, forest plots for message types and campaigns
  - `checkpoints/`: Model state for inference

Prerequisites:
```bash
# Prepare data first (creates pickle files from CSV exports)
python src/bayesian_scripts_orig/prepare_messaging_data.py
```

Usage:
```bash
# Train with defaults (POC subset, 2000 draws, 4 chains)
python src/bayesian_scripts/train_messaging_effectiveness.py

# Use full dataset
python src/bayesian_scripts/train_messaging_effectiveness.py --full-data

# Custom sampling parameters
python src/bayesian_scripts/train_messaging_effectiveness.py --draws 3000 --chains 4 --tune 1500

# Show campaign rankings after training
python src/bayesian_scripts/train_messaging_effectiveness.py --show-rankings

# Dry run - load data only, validate model structure
python src/bayesian_scripts/train_messaging_effectiveness.py --dry-run

# View all options
python src/bayesian_scripts/train_messaging_effectiveness.py --help
```

Output: Model artifacts in `data/inference/messaging_effectiveness/` including campaign performance rankings with credible intervals.

**Results Interpretation**: See `.claude_docs/20260101_1545_messaging_effectiveness_results.md` for detailed analysis of model findings, strategic recommendations, and campaign rankings.

### train_model_04_campaign_effects.py
**Purpose**: Train the Campaign Treatment Effects Model (Model 04) for causal estimation of message type effects.

This is a Level 4 model in the causal progression, designed for campaign optimization. It estimates causal effects of campaign message types on click behavior with proper confounding control.

Features:
- Treatment variable: message_types (6 categories, multi-label)
- Confounding control: income, energy_burden, county
- County random effects for geographic variation
- Multi-label treatment handling (campaigns can have multiple message types)
- E-value sensitivity analysis for unmeasured confounding
- Comprehensive validation and diagnostic output

Research Questions Addressed:
1. Which message types drive highest click-through rates?
2. What are the relative effect sizes of different messaging strategies?
3. How robust are treatment effects to unmeasured confounding?

Causal Identification:
- Adjustment set: {income, energy_burden, county}
- Blocks backdoor paths from selection mechanism

Usage:
```bash
# Train with defaults (2000 draws, 4 chains)
python src/bayesian_scripts/train_model_04_campaign_effects.py

# Quick test run (500 draws, 2 chains)
python src/bayesian_scripts/train_model_04_campaign_effects.py --quick

# With post-training validation
python src/bayesian_scripts/train_model_04_campaign_effects.py --validate

# View all options
python src/bayesian_scripts/train_model_04_campaign_effects.py --help
```

Output: Model artifacts in `data/inference/model_04_campaign_effects/` including treatment effect estimates with E-values, county effects, and validation diagnostics.

## Bayesian Model Validation (scripts/ and src/bayesian_models/validation/)

### validate_bayesian_model.py
**Purpose**: Run comprehensive validation on any trained Bayesian model.

Performs McElreath's Statistical Rethinking validation methodology:
- Convergence diagnostics (R-hat < 1.01, ESS > 400, no divergences)
- Posterior predictive checks for calibration
- PSIS-LOO cross-validation for model comparison
- E-values for causal sensitivity analysis
- Generates diagnostic plots for UI display

Usage:
```bash
# Validate a trained model
python scripts/validate_bayesian_model.py model_04_campaign_effects

# With diagnostic plots
python scripts/validate_bayesian_model.py model_03_demographics --plots

# Export JSON report
python scripts/validate_bayesian_model.py model_04_campaign_effects --output-json report.json

# Skip LOO for faster validation
python scripts/validate_bayesian_model.py model_04_campaign_effects --no-loo
```

Output: Detailed validation report with pass/fail status, recommendations, and optional plots.

### train_model_05_rate_energy_income.py
**Purpose**: Train the Click Rate by Energy Cost × Income Category Model (Model 05).

A hierarchical Bayesian model using energy cost and income category as separate predictors with varying slopes. This design avoids information loss from discretizing the derived energy burden ratio.

Model Structure:
- `logit(p) = α + β·energy_cost + γ[income_cat] + δ[income_cat]·energy_cost`
- 10 income categories with hierarchical partial pooling
- Varying slopes δ[k] capture how energy cost effect differs by income
- Implicitly models energy burden without discretization

Key Features:
- Base rate centered at 2.5% click rate (α ~ Normal(-3.7, 0.5))
- Non-centered parameterization for stable sampling
- GPU acceleration via NumPyro backend
- Comprehensive diagnostic and visualization outputs

Outputs saved to `data/inference/model_05_rate_energy_income/`:
- `traces/`: MCMC trace files (.nc NetCDF format)
- `reports/`: Category effects, varying slopes, diagnostics
- `diagrams/`: DAG, interaction plots, forest plots for γ and δ
- `checkpoints/`: Scaler parameters for inference

Usage:
```bash
# Train with defaults (2000 draws, 4 chains, GPU)
python src/bayesian_scripts/train_model_05_rate_energy_income.py

# Custom sampling parameters
python src/bayesian_scripts/train_model_05_rate_energy_income.py --draws 3000 --chains 4

# Disable GPU (use CPU only)
python src/bayesian_scripts/train_model_05_rate_energy_income.py --no-gpu

# Dry run - load data only, validate structure
python src/bayesian_scripts/train_model_05_rate_energy_income.py --dry-run

# View all options
python src/bayesian_scripts/train_model_05_rate_energy_income.py --help
```

Output: Model artifacts ready for UI visualization. Includes income category comparison table and slope variation analysis.

### generate_data_summary.py
**Purpose**: Generate data ingestion summaries for trained Bayesian models.

Creates detailed JSON summary files documenting what data was used to train each model:
- Total participants, observations, campaigns, counties
- Click/engagement rates
- Per-county breakdown with participant counts and click rates
- Per-campaign breakdown with exposure counts and message types
- Missing data statistics (no demographics, no county, excluded records)
- Treatment variable summaries for causal models

The summaries are displayed in the Inference Models UI under the "Data Summary" tab.

Usage:
```bash
# Generate for specific model
python scripts/generate_data_summary.py --model model_04_campaign_effects

# Generate for all models with registered generators
python scripts/generate_data_summary.py --all

# List available models
python scripts/generate_data_summary.py --list
```

Output: `data/inference/{model_id}/reports/data_summary.json`

### Validation Framework (src/bayesian_models/validation/)
Reusable validation module for programmatic and UI integration:
- `ModelValidator`: Main validation class
- `diagnostics.py`: Convergence checks, E-values, LOO, PPC
- `visualizations.py`: Forest plots, calibration plots, E-value charts

Usage in code:
```python
from src.bayesian_models.validation import ModelValidator

validator = ModelValidator(trace, treatment_effects=effects)
report = validator.full_validation()
ui_summary = validator.get_summary_for_ui()  # For dashboard display
validator.generate_all_plots(output_dir, return_base64=True)  # For web
```

## Data Enrichment

### enrich_thermal_loads.py
**Purpose**: Enrich participants with thermal load data from county-specific collections.

Joins participant data (via parcel_id) with thermal load regression analysis:
- Reads from `campaign_data.participants` (with `linkage.parcel_id`)
- Matches to `empower_development.{County}ThermalLoads` collections
- Adds heating/cooling load regression coefficients to participant records

Fields added to participants:
- `thermal.kwh_hl_slope`: Heating load slope (kWh/HDD)
- `thermal.kwh_hl_intercept`: Heating load intercept
- `thermal.kwh_hl_r2`: Heating load R² fit quality
- `thermal.kwh_cl_slope`: Cooling load slope (kWh/CDD)
- `thermal.kwh_cl_intercept`: Cooling load intercept
- `thermal.kwh_cl_r2`: Cooling load R² fit quality
- `thermal.enriched_at`: Timestamp of enrichment
- `thermal.source_collection`: Source collection name
- `thermal.county`: Normalized county name

Coverage Notes (as of 2026-01-04):
- 43.8% overall coverage (3,265 / 7,446 participants with parcel_id)
- 100% coverage in: Allen, Athens, Fayette, Marion, Morrow, Richland
- 0% coverage in: Belmont, Coshocton, Guernsey, Harrison, Holmes, Morgan, Muskingum
- The 0% counties have no overlapping parcels between participant data and thermal analysis

Usage:
```bash
# Dry run (preview changes)
python scripts/enrich_thermal_loads.py --dry-run

# Run enrichment
python scripts/enrich_thermal_loads.py

# Specific county only
python scripts/enrich_thermal_loads.py --county "Hennepin"

# Re-enrich already enriched participants
python scripts/enrich_thermal_loads.py --force

# Verbose output
python scripts/enrich_thermal_loads.py --verbose
```

## Data Quality

### fix_income_mismatches_tool.py
**Purpose**: Identify and fix mismatches between `income_level` and `estimated_income` in demographic data.

Analyzes the relationship between the categorical `income_level` (1-9 scale) and the dollar-based `estimated_income` field. Records where these don't align (e.g., income_level=6 but estimated_income=$7,500) are flagged and can be corrected.

The script:
1. Calculates median income for each income_level from the data
2. Flags records where estimated_income is outside the expected IQR range
3. Exports mismatches to CSV for review
4. Fixes by setting estimated_income to the median for that income_level
5. Recalculates total_energy_burden based on corrected income
6. Preserves original values in `*_original` fields for audit trail

Fields added during fix:
- `estimated_income_original`: Original income value before fix
- `total_energy_burden_original`: Original burden value before fix
- `income_fix_date`: ISO timestamp of when fix was applied
- `income_fix_reason`: Reason for the fix

Usage:
```bash
# Analyze data and show statistics
python scripts/fix_income_mismatches_tool.py --analyze

# Export mismatches to CSV
python scripts/fix_income_mismatches_tool.py --export --output data/exports/income_mismatches.csv

# Preview what would be fixed (dry run)
python scripts/fix_income_mismatches_tool.py --fix --dry-run

# Apply fixes to database
python scripts/fix_income_mismatches_tool.py --fix
```

Results (2026-01-14): Fixed 4,378 records in FranklinCountyDemographic. Eliminated all records with >100% energy burden.

## Comparable Residence Finder (src/tools/comparables/)

A reusable tool for finding comparable residences based on property characteristics, demographics, and energy consumption patterns.

### Purpose
When analyzing energy usage or targeting campaign outreach, we need to compare "apples to apples" - a 5000 sqft mansion's energy costs shouldn't be compared directly to a 1500 sqft ranch. The ComparableFinder locates similar homes within the same geographic area to enable fair comparisons.

### Core Classes

**ComparableFinder**: Main finder class that combines data from multiple collections:
- `{County}Residential`: Physical property data (sqft, stories, age, rooms)
- `{County}Demographic`: Occupant data (household size, income, energy costs)
- `{County}ThermalLoads`: Energy consumption patterns (heating/cooling loads)

**ComparableFilters**: Optional filter configuration with all fields optional:
- Geographic: `same_zip`, `same_city`, `zip_codes`, `census_tract`
- Physical: `sqft_tolerance`, `story_height_tolerance/exact`, `age_tolerance`
- Rooms: `bedrooms_tolerance/exact`, `bathrooms_tolerance`
- Construction: `construction_quality`, `heat_type`, `air_conditioning`
- Demographic: `household_size_tolerance/exact`, `income_tolerance/pct`
- Energy: `energy_burden_max`, `annual_kwh_cost_max`
- Exclusions: `exclude_parcel_ids`

**ScoringWeights**: Configurable weights for similarity scoring:
- Default weights prioritize physical characteristics (sqft=3.0, story=2.0, age=2.0)
- Configurable reference ranges for normalization

### Usage Examples

```python
from src.tools.comparables import ComparableFinder, ComparableFilters
from src.tools.mongo import get_empower_db

db = get_empower_db()
finder = ComparableFinder(db, county='FranklinCounty')

# Basic: Find 10 most similar homes
results = finder.find_comparables('21425802C', n_results=10)
for comp in results.comparables:
    print(f"{comp.address}: {comp.score.overall_score:.2f} similarity")

# With filters: Same ZIP, similar size, exact story match
filters = ComparableFilters(
    same_zip=True,
    sqft_tolerance=500,  # +/- 500 sqft
    story_height_exact=True,
    age_tolerance=10,  # +/- 10 years
    household_size_tolerance=1  # +/- 1 person
)
results = finder.find_comparables('21425802C', n_results=10, filters=filters)

# By address lookup
results = finder.find_comparables_for_address(
    '1050 STONEWOOD CT',
    zip_code=44145,
    n_results=5
)
```

### Return Values

**ComparableSearchResult** contains:
- `target_parcel_id`, `target_address`, `county`: Target property info
- `target_sqft`, `target_stories`, `target_age`, `target_household_size`: Target characteristics
- `comparables`: List of `ComparableResult` objects ranked by similarity
- `total_candidates`: Count of candidates before final ranking
- `avg_sqft_diff`, `avg_age_diff`, `avg_energy_cost`: Result statistics

**ComparableResult** contains:
- Property info: `parcel_id`, `address`, `city`, `zip_code`
- Characteristics: `living_area_sqft`, `story_height`, `age`, `bedrooms`, `bathrooms`
- Demographics: `household_size`, `estimated_income`
- Energy: `annual_kwh_cost`, `annual_gas_cost`, `total_energy_burden`
- Scoring: `score` (ComparableScore with overall and per-feature scores)

### EnergyPercentileCalculator

Calculates energy consumption percentile for properties relative to comparable homes using scipy.stats.percentileofscore.

```python
from src.tools.comparables import EnergyPercentileCalculator, TieredFilterConfig

db = get_empower_db()

# Basic usage
calculator = EnergyPercentileCalculator(db, county='Franklin')
result = calculator.calculate_percentile(parcel_id='010-000002-00')

if result.is_valid:
    print(f"{result.annual_kwh:.0f} kWh/year")
    print(f"{result.percentile_rank:.1f}th percentile")
    print(f"Compared to {result.comparable_count} similar homes")

# Custom configuration
config = TieredFilterConfig(
    sqft_pct=0.25,        # ±25% sqft range
    age_tolerance=15,      # ±15 years
    min_comparables=50     # Require 50 comparables before relaxing
)
calculator = EnergyPercentileCalculator(db, 'Franklin', config)

# Batch processing with DB updates
results = calculator.batch_calculate(parcel_ids, update_db=True)

# Update single property
result = calculator.update_property_percentile('010-000002-00')
```

**Interpretation**: Higher percentile = higher consumption. A home at the 65th percentile uses MORE electricity than 65% of comparable homes.

### Similarity Scoring Algorithm

Weighted similarity calculation across features:
1. Each feature converted to 0-1 score using reference ranges
2. Features combined using configurable weights
3. Missing data gracefully excluded from scoring

Default weights (adjustable via ScoringWeights):
- sqft_weight=3.0, story_weight=2.0, age_weight=2.0
- bedrooms_weight=1.5, bathrooms_weight=1.0
- household_weight=1.5, income_weight=1.0

### Tests

Comprehensive test suite at `tests/test_comparable_finder.py`:
- Scoring tests: identical/similar/different property comparisons
- Filter tests: ZIP, sqft tolerance, story height, age tolerance
- Integration tests: full search pipeline, result ranking
- Edge cases: missing data, sentinel values, strict filters

Run tests:
```bash
source venv/bin/activate && python -m pytest tests/test_comparable_finder.py -v --override-ini="addopts="
```

### calculate_energy_percentiles_tool.py
**Purpose**: Calculate energy consumption percentile rank for residential properties relative to comparable homes.

Uses scipy.stats.percentileofscore for robust percentile calculation that handles ties and edge cases. Higher percentile = higher consumption relative to peers (e.g., 65th percentile means uses more electricity than 65% of comparable homes).

**Comparable Criteria (Tiered Relaxation)**:
- Tier 1 (Core): sqft ±20%, age ±20 years, same story height
- Tier 2 (Location): same ZIP code
- Progressive relaxation: If <30 comparables found, constraints are relaxed step-by-step:
  1. Expand sqft to ±30%
  2. Remove ZIP constraint
  3. Expand age to ±30 years
  4. Remove story constraint
  5. Expand sqft to ±50%

**Features**:
- Batch-optimized queries (300x faster than naive N+1 approach)
- Annualized kWh calculation from monthly time series (requires 6+ months data)
- Stores results to MongoDB with full criteria transparency
- Progress reporting and CSV export

**Database Storage Schema**:
```python
{
    "energy_percentile": {
        "annual_kwh": 8500,
        "percentile_rank": 65.0,
        "comparable_count": 127,
        "comparable_criteria": {
            "sqft_range": [1100, 1650],
            "age_range": [1990, 2010],
            "zip": 43204,
            "story_height": 2.0,
            "relaxations_applied": []
        },
        "calculated_at": "2025-01-15T20:38:00Z"
    }
}
```

**Usage**:
```bash
# Test on single parcel
python scripts/calculate_energy_percentiles_tool.py --parcel 010-000002-00 --verbose

# Process 100 properties (dry run - no DB updates)
python scripts/calculate_energy_percentiles_tool.py --county Franklin --limit 100

# Process all and save to database
python scripts/calculate_energy_percentiles_tool.py --county Franklin --update-db

# Export results to CSV
python scripts/calculate_energy_percentiles_tool.py --county Franklin --limit 1000 -o results.csv

# Process from file of parcel IDs
python scripts/calculate_energy_percentiles_tool.py --parcel-file parcels.txt --update-db
```

**Output**: Percentile distribution summary and optional CSV with parcel_id, annual_kwh, percentile_rank, comparable_count.

### generate_campaign_list_by_energy_percentile_tool.py
**Purpose**: Generate campaign target lists sorted by highest energy consumption percentile or heating load, organized by zipcode and bucketed by square footage.

Creates CSV files for targeted outreach campaigns focusing on households with the highest energy usage relative to comparable homes. Useful for identifying homes that could benefit most from energy efficiency programs.

**Features**:
- Filters by county and specific zip codes
- Joins Residential and Demographic data for complete household info
- **Standard mode**: Sorts by highest energy percentile (100th = highest usage)
- **Heating load mode** (`--heating-load`): Joins with ThermalLoads collection, sorts by `kwh_hl_slope` (highest heating load first - best weatherization targets)
- Organizes output by zipcode folders
- Buckets within each zipcode by sqft ranges:
  - under_1000_sqft, 1000_to_1500_sqft, 1500_to_2000_sqft
  - 2000_to_2500_sqft, 2500_to_3000_sqft, over_3000_sqft
- Includes phone numbers where available
- Indicates demographic database match status
- **No-overwrite protection**: Creates unique directory names if output exists

**CSV Columns**:
- Standard: Name, Address, City, Zipcode, Phone, Sqft, Year_Built, Energy_Percentile, In_Demographic_DB
- Heating load mode adds: Heating_Load_Slope, Heating_Load_R2

**Usage**:
```bash
# Generate for Franklin County with default zip codes
python scripts/generate_campaign_list_by_energy_percentile_tool.py

# Specify custom zip codes
python scripts/generate_campaign_list_by_energy_percentile_tool.py --zips 43210,43222,43211

# Custom output folder
python scripts/generate_campaign_list_by_energy_percentile_tool.py --output-dir data/my-campaign

# Minimum percentile threshold (only 70th percentile and above)
python scripts/generate_campaign_list_by_energy_percentile_tool.py --min-percentile 70

# Heating load mode (for weatherization targeting)
python scripts/generate_campaign_list_by_energy_percentile_tool.py --heating-load

# Heating load with R² quality filter
python scripts/generate_campaign_list_by_energy_percentile_tool.py --heating-load --min-r2 0.5
```

**Output Structure**:
```
data/campaign-list-YYYYMMDD-county/           # Standard mode
data/campaign-list-YYYYMMDD-county-heating-load/  # Heating load mode
├── 43201/
│   ├── under_1000_sqft.csv
│   ├── 1000_to_1500_sqft.csv
│   ├── ...
│   └── all_households.csv
├── 43203/
│   └── ...
└── ...
```

### calculate_missing_thermal_loads_tool.py
**Purpose**: Calculate thermal load coefficients for parcels that are in the electrical database but missing from the thermal loads database.

Implements the same ASHRAE energy signature methodology used in the original Franklin thermal load calculation:
1. **Degree-Hour Integration**: Calculates Heating Degree-Hours (HDH) and Cooling Degree-Hours (CDH) using trapezoidal integration on hourly weather data
2. **Linear Regression**: Fits kWh consumption against degree-hours to extract thermal load slope and R² fit quality

**Thresholds**:
- Heating: 62°F (below this, heating degree-hours accumulate)
- Cooling: 72°F (above this, cooling degree-hours accumulate)

**Weather Data**: Reads NOAA weather data from John Glenn Columbus International Airport (station 72428014821) with hourly temperature observations.

**Features**:
- Identifies parcels missing from thermal loads collection
- Processes weather data in NOAA raw format or pre-processed CSV
- Calculates billing-period-aligned HDH/CDH values
- Performs sklearn LinearRegression for each parcel
- Dry-run mode for validation before database insertion
- Verbose logging with detailed progress information
- Configurable county and parcel limits

**Database Collections**:
- Source: `{County}ElectricalDB` - Monthly kWh billing data
- Existing: `{County}ThermalLoads` - Already-calculated thermal records
- Target: `{County}ThermalLoads` - Insert new thermal calculations

**Usage**:
```bash
# Dry run - show what would be calculated (no DB writes)
python scripts/calculate_missing_thermal_loads_tool.py --county Franklin --dry-run

# Test with limit
python scripts/calculate_missing_thermal_loads_tool.py --county Franklin --dry-run --limit 10 --verbose

# Full calculation (inserts to MongoDB)
python scripts/calculate_missing_thermal_loads_tool.py --county Franklin

# With custom weather file
python scripts/calculate_missing_thermal_loads_tool.py --county Franklin --weather-file /path/to/weather.csv
```

**Output**:
- Thermal load records with: kwh_hl_slope, kwh_hl_intercept, kwh_hl_r2, kwh_cl_slope, kwh_cl_intercept, kwh_cl_r2
- Processing statistics: parcels found, successfully processed, failed, inserted

**Dependencies**: sklearn, pandas, pymongo, numpy

### ingest_franklin_demographics_tool.py
**Purpose**: Ingest Franklin County demographic data from Melissa Data enriched CSV into the `empower_development.FranklinCountyDemographic` MongoDB collection.

Converts string-based income brackets (e.g., "$30,001-$40,000") to numeric values and maps CSV fields to the existing demographic schema. Preserves additional Melissa Data (MD_) enrichment fields.

**Income Conversion**:
| CSV Bracket | estimated_income | income_level |
|-------------|------------------|--------------|
| $0-$15,000 | 10,000 | 1 |
| $15,001-$20,000 | 17,500 | 2 |
| $20,001-$30,000 | 25,000 | 3 |
| $30,001-$40,000 | 35,000 | 4 |
| $40,001-$50,000 | 45,000 | 5 |
| $50,001-$60,000 | 55,000 | 5 |
| $60,001-$75,000 | 62,500 | 6 |
| $75,001-$100,000 | 87,500 | 7 |
| $100,001-$125,000 | 112,500 | 8 |
| $125,001+ | 150,000 | 9 |

**Field Mappings**:
- `First Name` + `Last Name` → `customer_name`
- `Address` → `address` (normalized uppercase)
- `City` → `service_city`
- `Zipcode` → `parcel_zip` (5-digit extracted)
- `MD_EMAIL` → `email`
- `MD_MOBILE` → `mobile`
- `MD_HouseholdIncome` → `estimated_income`, `income_level`
- `MD_HouseholdSize` → `md_householdsize`
- Additional MD_ fields preserved: own_rent, education, marital_status, gender, occupation, etc.

**Features**:
- Duplicate detection by address + zipcode (skips existing records)
- Dry-run mode for validation before insertion
- Preserves source metadata (`source`, `ingested_at`)
- Progress reporting every 5,000 records
- Handles missing/null values gracefully with -1 sentinel

**Usage**:
```bash
# Dry run - preview without inserting
python scripts/ingest_franklin_demographics_tool.py --dry-run

# Test with limit
python scripts/ingest_franklin_demographics_tool.py --dry-run --limit 100 --verbose

# Full ingestion
python scripts/ingest_franklin_demographics_tool.py

# Custom CSV file
python scripts/ingest_franklin_demographics_tool.py --csv /path/to/data.csv
```

**Output**: Inserts ~20,785 new records into FranklinCountyDemographic collection (after duplicate detection).

### enrich_franklin_age_data_tool.py
**Purpose**: Enrich existing FranklinCountyDemographic records with age data calculated from Melissa Data `MD_DateOfBirth` field.

Updates existing demographic records (no new inserts) by matching on normalized address. Calculates `owner_age` from YYYYMM birth date format and enriches with additional demographic fields.

**Age Calculation**:
- Input: `MD_DateOfBirth` in YYYYMM format (e.g., 197607 = July 1976)
- Output: `owner_age` calculated as current_year - birth_year, adjusted for month
- Validation: Years must be 1900-2020, months 1-12

**Fields Enriched**:
- `owner_age`: Calculated from MD_DateOfBirth
- `date_of_birth`: YYYYMM string for storage
- `presence_of_senior`: Normalized Yes/No
- `children_age_range`: MD_ChildrenAgeRange value
- `marital_status`: Normalized Single/Married
- `number_of_adults`: Estimated from household size and children presence
- `length_of_residence`: MD_LengthOfResidence value
- `estimated_home_value`: Parsed numeric from dollar string
- `enriched_at`: Timestamp of enrichment
- `enriched_from`: Source CSV filename

**Matching Strategy** (consistent with existing scripts):
- Primary: Normalized address + parcel_zip
- Fallback: Normalized address only (if ZIP doesn't match)
- Uses same `normalize_address()` function as other ingestion scripts

**Features**:
- Only updates EXISTING documents (no new inserts)
- Skips records already enriched with owner_age (unless --force)
- Dry-run mode for validation before updates
- Age distribution preview in dry-run output
- Progress reporting every 5,000 records

**Usage**:
```bash
# Dry run - preview without updating
python scripts/enrich_franklin_age_data_tool.py --dry-run

# Test with limit
python scripts/enrich_franklin_age_data_tool.py --dry-run --limit 500 --verbose

# Full enrichment
python scripts/enrich_franklin_age_data_tool.py

# Force update (re-enrich even if owner_age exists)
python scripts/enrich_franklin_age_data_tool.py --force

# Custom CSV file
python scripts/enrich_franklin_age_data_tool.py --csv /path/to/data.csv
```

**Output**: Updates ~13,000 records with owner_age data (mean age ~49, 16% seniors 65+).

### backfill_demographic_parcel_ids_tool.py
**Purpose**: Backfill missing `parcel_id` values in FranklinCountyDemographic by matching addresses to FranklinCountyResidential.

The `ingest_franklin_demographics_tool.py` script creates records without parcel_id (the Melissa Data CSV doesn't include it). This script fills in the missing parcel_ids by address matching, enabling parcel_id-based joins.

**Address Normalization**:
- Handles suffix variations: AV→AVE, ST→ST, DR→DR, etc.
- Uppercase, whitespace normalization
- Same algorithm used across all demographic scripts

**Fields Updated**:
- `parcel_id`: The matched parcel ID from Residential
- `parcel_id_source`: 'backfill_from_residential'
- `parcel_id_backfilled_at`: Timestamp of backfill

**Features**:
- Only updates records with empty/missing parcel_id
- Dry-run mode for validation
- Progress reporting every 5,000 records
- Reports match statistics and remaining gaps

**Usage**:
```bash
# Dry run - preview without updating
python scripts/backfill_demographic_parcel_ids_tool.py --dry-run

# Test with limit
python scripts/backfill_demographic_parcel_ids_tool.py --dry-run --limit 500 --verbose

# Full backfill
python scripts/backfill_demographic_parcel_ids_tool.py
```

**Output**: Updates ~20,750 records (99.8% match rate). Enables parcel_id joins from 56% to 100% coverage.

## ingest_impact_winter_campaign_tool.py
**Purpose**: Ingest IMPACT Winter 2026-01 text campaign data from color-coded Excel files into campaign_data database.

Creates campaigns, matches/creates participants, and records engagement data with rich tracking (clicked, form_completed, opted_out).

**Color Code Mapping**:
| Color | Hex Code | Meaning | unified_status |
|-------|----------|---------|----------------|
| Blank | - | Received, no action | `received` |
| Yellow | FFFFFF00 | Clicked link, no form | `clicked` |
| Green | FF92D050 | Completed form | `converted` |
| Orange | FFFFC000 | Negative reply (no stop) | `negative_response` |
| Red | FFFF0000 | Replied STOP | `opted_out` |
| Blue | theme_4 | Bad number/undeliverable | `undeliverable` |

**Extended Schema Fields** (beyond standard text exposure):
- `text_clicked`: Boolean - did they click the link?
- `text_form_completed`: Boolean - did they complete the signup form?
- `text_opted_out`: Boolean - did they reply STOP?
- `do_not_contact`: Global participant flag for TCPA compliance

**Participant Matching**: Phone → Email → Parcel ID cascade

**Campaigns Created**:
- `text_impact_winter_75`: Section 1 (~3,800 contacts)
- `text_impact_winter_76`: Section 2 (~3,800 contacts)

**Usage**:
```bash
# Dry run - preview changes
python scripts/ingest_impact_winter_campaign_tool.py --dry-run

# Full ingestion
python scripts/ingest_impact_winter_campaign_tool.py
```

**Output**: Campaign records with rich statistics (clicked, converted, opted_out counts), participant records with engagement tracking, exposure records with color-based status.

## ingest_impact_20260110_campaign_tool.py
**Purpose**: Ingest IMPACT 2026-01-10 text campaign data from color-coded Excel files into campaign_data database.

Same pipeline as `ingest_impact_winter_campaign_tool.py` but for the January 10, 2026 campaign send. Key difference: undeliverable rows use `theme_3` (blue/gray) instead of `theme_4`.

**Color Code Mapping**:
| Color | Hex Code | Meaning | unified_status |
|-------|----------|---------|----------------|
| Blank | - | Received, no action | `received` |
| Yellow | FFFFFF00 | Clicked link, no form | `clicked` |
| Green | FF92D050 | Completed form | `converted` |
| Orange | FFFFC000 | Negative reply (no stop) | `negative_response` |
| Red | FFFF0000 | Replied STOP | `opted_out` |
| Blue/Gray | theme_3 | Bad number/undeliverable | `undeliverable` |

**Campaigns Created**:
- `text_impact_20260110_s1`: Section 1 (~3,701 contacts)
- `text_impact_20260110_s2`: Section 2 (~3,700 contacts)

**Usage**:
```bash
# Dry run - preview changes
python scripts/ingest_impact_20260110_campaign_tool.py --dry-run

# Full ingestion
python scripts/ingest_impact_20260110_campaign_tool.py
```

**Output**: 7,401 total records. 29.4% click rate, 0.73% conversion, 1.6% opt-out, 0.4% undeliverable.

## export_impact_20260110_csvs_tool.py
**Purpose**: Export IMPACT 2026-01-10 campaign data as 6 color-coded CSV files and verify database linkage.

Same pipeline as `export_campaign_color_csvs_tool.py` but for the January 10, 2026 campaign. Uses `theme_3` for undeliverable color detection.

**Output CSVs** (in `data/campaign-IMPACT-20260110/`):
| File | Color | Meaning |
|------|-------|---------|
| `impact_20260110_blank_received.csv` | Blank | Received, no click |
| `impact_20260110_yellow_clicked.csv` | Yellow | Clicked link, no form |
| `impact_20260110_green_converted.csv` | Green | Filled out form |
| `impact_20260110_orange_negative.csv` | Orange | Nasty/uninterested |
| `impact_20260110_red_opted_out.csv` | Red | Opted out (STOP) |
| `impact_20260110_blue_undeliverable.csv` | Blue/Gray | Bad number/undeliverable |

**Usage**:
```bash
# Dry run - preview without changes
python scripts/export_impact_20260110_csvs_tool.py --dry-run

# Full run - export CSVs + fix DB
python scripts/export_impact_20260110_csvs_tool.py

# CSV export only, skip DB operations
python scripts/export_impact_20260110_csvs_tool.py --skip-db
```

## export_campaign_color_csvs_tool.py
**Purpose**: Export IMPACT Winter 2026-01 campaign data as 6 color-coded CSV files and verify database linkage.

Reads both color-coded Excel files (Text75 + Text76, 7,642 records), classifies each row by cell background color, and writes separate CSVs. Also fixes Application → Campaign linkage for GREEN (converted) rows and verifies `do_not_contact` flags for RED (opted-out) participants.

**Output CSVs** (in `data/campaign-IMPACT-202601/`):
| File | Rows | Color | Meaning |
|------|------|-------|---------|
| `impact_winter_blank_received.csv` | 4,363 | Blank | Received, no click |
| `impact_winter_yellow_clicked.csv` | 2,005 | Yellow | Clicked link, no form |
| `impact_winter_blue_undeliverable.csv` | 1,038 | Blue | Bad number/undeliverable |
| `impact_winter_red_opted_out.csv` | 154 | Red | Opted out (STOP) |
| `impact_winter_green_converted.csv` | 63 | Green | Filled out form |
| `impact_winter_orange_negative.csv` | 19 | Orange | Nasty/uninterested |

**DB Operations**:
- Updates `applications.attribution.likely_campaigns` for GREEN rows (confidence: 1.0, method: `excel_color_verified`)
- Verifies `participants.do_not_contact` is True for RED rows

**Usage**:
```bash
# Dry run - preview without changes
python scripts/export_campaign_color_csvs_tool.py --dry-run

# Full run - export CSVs + fix DB
python scripts/export_campaign_color_csvs_tool.py

# CSV export only, skip DB operations
python scripts/export_campaign_color_csvs_tool.py --skip-db
```

## reformat_campaign_list_tool.py
**Purpose**: Reformat campaign_list.csv to match BOLT analysis format with 53 columns.
**Location**: `scripts/reformat_campaign_list_tool.py`
**Data Sources**:
- FranklinCountyResidential: property data (year built, sqft, stories)
- FranklinCountyDemographic: contact info (cell, email) and demographics
- FranklinElectricalDB: monthly energy readings (time_series_elec)
**Usage**:
```bash
python scripts/reformat_campaign_list_tool.py --dry-run     # Preview
python scripts/reformat_campaign_list_tool.py --limit 100   # Test with subset
python scripts/reformat_campaign_list_tool.py               # Full run
```

## ingest_green_applications_tool.py
**Purpose**: Ingest GREEN (converted) rows from IMPACT 20260110 campaign as Application documents in the `applications` collection.

The text_impact_20260110 campaign has 54 GREEN rows (form completed) but only 4 matched existing application records. This script creates Application documents for the remaining unmatched conversions with pre-linked campaign attribution.

**Key Features**:
- Reads `data/campaign-IMPACT-20260110/impact_20260110_green_converted.csv` (54 rows)
- Deterministic `application_id`: `green_{campaign_id}_{phone}` for idempotent re-runs
- Participant matching: parcel_id first (confidence 0.90), phone fallback (0.85)
- Phone-level duplicate detection against existing applications
- Pre-linked attribution: `likely_campaigns` with confidence 1.0, method `excel_color_verified`
- Handles bracket income format (e.g. "$15,001-$20,000") and numeric format
- Dry-run mode for validation

**Usage**:
```bash
# Dry run - preview without inserting
python scripts/ingest_green_applications_tool.py --dry-run

# Full ingestion
python scripts/ingest_green_applications_tool.py
```

**Output**: ~50 new Application documents (54 total minus ~4 already existing by phone match).

## Energy Conservation Client Portal (client/)

### client/app.py
**Purpose**: Standalone Flask application serving the Energy Conservation Client Portal - a single-page demo app for viewing energy profiles and chatting with an AI advisor.

**Features**:
- Separate Flask app on port 5001 (independent from main `app/`)
- User search by name with county and participant filters
- Energy profile display with comparables analysis
- AI chat interface (Phase 3: Claude API integration)
- Opportunities checklist sidebar
- Dark theme Bootstrap 5 UI with Chart.js visualizations

**Architecture**:
- `app.py`: Flask routes and entry point
- `config.py`: Configuration using shared `src/utils/EnvVars`
- `services/mongo_service.py`: MongoDB data access layer
- `services/programs.py`: Hardcoded Ohio energy programs and savings estimates
- `templates/index.html`: Single-page template
- `static/css/style.css`: Dark theme styles
- `static/js/main.js`: Frontend logic

**API Endpoints**:
- `GET /`: Serve main page
- `GET /api/counties`: List available counties
- `POST /api/search`: Search users by name
- `GET /api/user/<parcel_id>`: Get full profile with comparables
- `POST /api/programs`: Look up eligible programs by income
- `POST /api/savings`: Calculate savings for improvements
- `POST /api/chat`: Chat with AI advisor (Phase 3)

**Usage**:
```bash
# Activate venv and run
source venv/bin/activate
python client/app.py

# Access at http://localhost:5001
```

**Implementation Phases**:
- Phase 1 (Complete): Flask structure, MongoDB service, base UI
- Phase 2: Search & profile display with charts
- Phase 3: AI advisor with Claude API tools
- Phase 4: Opportunities sidebar
- Phase 5: Polish and testing

## ingest_impact_leads_20260414_tool.py
**Purpose**: Ingest the hand-tracked `data/EMPOWER-IMPACT LEADS_20260414.xlsx` lead sheet (209 rows) into the `applications` collection.

Differs from `ingest_applications.py` (GravityForms CSV): no Entry Id, no UTM, no Date column. Generates a deterministic `application_id = "impact_lead_20260414_<email|phone>"` for safe re-runs (upsert), stamps synthetic IMPACT attribution, and stores IMPACT-specific extras (`fpl_percent`, `impact_zip`, `called`, `notes`) under a `lead_tracking` sub-document. Reuses participant matching from `ApplicationIngester`. Subclasses the parent ingester to skip the unique-index recreation that conflicts with the existing non-unique `application_id` index.

**Usage**:
```bash
source venv/bin/activate
python scripts/ingest_impact_leads_20260414_tool.py --dry-run    # parse + report only
python scripts/ingest_impact_leads_20260414_tool.py              # live ingest
python scripts/ingest_impact_leads_20260414_tool.py --no-match   # skip participant matching
```

**Output (initial run)**: 207 inserted, 2 updated (two duplicate-email rows collide on the deterministic id), 0 errors, 193/209 (92%) matched to existing participants (93 email, 35 phone, 65 address+zip). CSV mirror written to `data/applications/EMPOWER-IMPACT_LEADS_20260414.csv`.

## ingest_impact_endssoon_lastday_20260406_campaign_tool.py
**Purpose**: Ingest the IMPACT EndsSoon/LastDay text-campaign batch (Text81-84) from `data/campaign-IMPACT-20260406/*.xlsx` into `empower_development` (campaigns, participants, exposures).

DRY: imports all conversation-format helpers (`read_stats_sheet`, `read_conversations`, `aggregate_contacts`, `classify_engagement`, `build_*_doc`, `parse_sent_date`, `normalize_*`) from `ingest_impact_cold_20260310_campaign_tool.py` and only supplies a new `CAMPAIGN_CONFIG`, `DATA_DIR`, and `CAMPAIGN_GROUP='IMPACT-EndsSoon-LastDay-202604'`. Same tag-based engagement classification (STOP/dnd → opted_out, bad/err → undeliverable, inbound reply → negative_response, default → received). Surfaces existing-campaign warnings before re-ingesting.

**Usage**:
```bash
source venv/bin/activate
PYTHONPATH=scripts python scripts/ingest_impact_endssoon_lastday_20260406_campaign_tool.py --dry-run
PYTHONPATH=scripts python scripts/ingest_impact_endssoon_lastday_20260406_campaign_tool.py
```

**Output (initial run, 2026-04-27)**: 4 campaigns created (`text_impact_endssoon_81`, `_82`, `text_impact_lastday_83`, `_84`), 11,765 exposures inserted, 0 new participants (all 11,765 contacts matched existing — same audience as Cold/Winter waves), 107 opt-outs flagged, 14 testers skipped. Per-campaign exposures: 2977 / 2974 / 2908 / 2906.

## backfill_participant_customer_name_tool.py
**Purpose**: Backfill `participants.demographics.customer_name` from the per-county `<County>CountyDemographic` source-of-truth collections, using `linkage.parcel_id` + `linkage.county_key` as the join key.

The participants collection is a denormalized snapshot of county demographics, but the original import left `demographics.customer_name` null for ~50% of records system-wide and ~92% within Franklin County. The county collections themselves DO have the names — this tool copies them across. Resolves the demographic collection name via `CountyKeys` (the authoritative registry), so it works uniformly across all 25 counties. Idempotent: only touches participants whose `customer_name` is null/empty.

**Usage**:
```bash
source venv/bin/activate
python scripts/backfill_participant_customer_name_tool.py              # dry-run
python scripts/backfill_participant_customer_name_tool.py --county Franklin  # one county
python scripts/backfill_participant_customer_name_tool.py --apply      # write
```

**Output (initial run, 2026-05-13)**: 6,872 / 6,890 nameless-but-parcel-linked participants matched a `customer_name` in `FranklinCountyDemographic` and were updated. The 18 unmatched parcels either don't exist in the county collection or have county_key values that don't normalize cleanly. Effect on Text81 detail page: from 1/25 names visible per page → 25/25.

## attribute_winter_sameday_conversions_tool.py
**Purpose**: Backfill `attribution.likely_campaigns` (a `CampaignLink`) for the four 2026-01-23 Winter same-day conversions that the UTM-based pipeline missed.

Four IMPACT participants submitted GravityForms applications on the EmpowerSaves landing page (`reduceenergyburdenohio.com`) on the same day they received the Winter text blast (Text75 Section1 / Text76 Section2), but the form carried no UTM so attribution stayed empty. This tool writes the missing link per application, calibrated by evidence strength: recorded Text76 *click* → confidence 0.95, method `click_same_day_landing`; same-day Text75 *receipt* only → confidence 0.70, method `receipt_same_day_landing`. Hardcoded `TARGETS` table (app_id → campaign slug). Idempotent (skips an app already linked to the target campaign, mirroring `export_campaign_color_csvs_tool.py`); safety-guards on campaign existence and on `entry_date` falling on the 2026-01-23 send day before writing.

**Note**: `application_id` is stored as a **string** in `applications` (e.g. `"437"`), and the `campaign_id` written into the link is the campaign *slug* (`text_impact_winter_76`), not the ObjectId.

**Usage**:
```bash
source venv/bin/activate
python scripts/attribute_winter_sameday_conversions_tool.py            # dry-run (default)
python scripts/attribute_winter_sameday_conversions_tool.py --apply    # write
```

**Output (initial run, 2026-06-02)**: 4 applications updated (#437/#440/#412 → `text_impact_winter_76`; #408 → `text_impact_winter_75`). These were the first 4 applications in the collection to carry a populated `likely_campaigns`. Re-run skips all 4 as already-linked.

## attribute_click_conversions_tool.py
**Purpose**: Generalized, query-driven behavioral attribution. Backfills `attribution.likely_campaigns` on converted applications by inferring the driving campaign from the matched participant's *click* behavior, aligned to the application's `entry_date`. Supersedes the hardcoded `attribute_winter_sameday_conversions_tool.py`.

**Attribution priority** (first match wins; confidence by evidence strength):
1. same-day CLICK → conf 0.95, method `click_same_day_landing`
2. windowed CLICK (clicked ≤ `--lag-days` before applying, most recent wins) → conf 0.85, method `click_window_landing`
3. same-day RECEIPT, no click → conf 0.70, method `receipt_same_day_landing` (only with `--include-receipt`)

**Scope/safety**: only touches applications with EMPTY `likely_campaigns` (idempotent); SKIPS apps that already carry a real UTM (`utm_source`/`utm_campaign`/`utm_id` — reserved for a future `utm_direct` rule, not overwritten); SKIPS apps with no `participant_match.participant_oid`. Writes the campaign *slug* (`campaigns.campaign_id`, e.g. `text_impact_winter_75`); `application_id` is a STRING in this collection.

**Usage**:
```bash
source venv/bin/activate
python scripts/attribute_click_conversions_tool.py                                   # dry-run report
python scripts/attribute_click_conversions_tool.py --csv data/attribution/status.csv # per-app status CSV (no writes)
python scripts/attribute_click_conversions_tool.py --lag-days 7 --apply              # write
```
`--csv PATH` classifies EVERY application into one status (same-day / windowed / utm-deferred / no-match / no-signal / already-attributed) and exits without writing.

**Output (initial run, 2026-06-02, lag 7d, click-only)**: of 299 empty-attribution applications, **224 attributed** (164 same-day @0.95, 60 windowed @0.85) across the full Text75–84 / WCP / Cold / EndsSoon / LastDay text family + 2 EGE email clicks. Skipped: 25 has-UTM, 15 no-match, 35 no-signal. Collection-wide after run: 228 attributed, 75 empty. Outliers (no-signal/no-match/receipt) catalogued in `.claude_docs/20260602_1232_attribution_outliers.md` for a later click-ingestion audit.

## attribute_utm_direct_tool.py
**Purpose**: UTM-direct attribution for direct-mail conversions deferred by the behavioral tool. Maps the landing-page UTM (`utm_source=mail&utm_campaign=<Test|Control>-<Click|View>`) to the real `dm_impact_*` letter campaign.

**Verified mapping** (March 2026 IMPACT direct-mail A/B drop): `Test→new` (NEW copy), `Control→old` (OLD copy); `Click→clickers`, `View→non_clickers` → `dm_impact_{audience}_{copy}`. e.g. `Test-Click → dm_impact_clickers_new`. Mapping confirmed independently: 20/21 matched converters also appear in the mapped campaign's letter exposures.

**Confidence (double-keyed)**: 0.99 `utm_direct_verified` when the UTM maps AND the participant is in that campaign's letter exposures; 0.90 `utm_direct` when mapped by label only (no `participant_oid` or not in audience). Idempotent; skips already-attributed apps; reports unmappable UTMs (e.g. `utm_source=Majority`) rather than guessing.

**Usage**:
```bash
source venv/bin/activate
python scripts/attribute_utm_direct_tool.py            # dry-run
python scripts/attribute_utm_direct_tool.py --apply    # write
```

**Output (initial run, 2026-06-02)**: 24 of 25 UTM-deferred applications attributed (22 verified @0.99, 2 label-only @0.90) → `clickers_old` 9, `non_clickers_new` 8, `clickers_new` 4, `non_clickers_old` 3. 1 unmapped (#695, `utm_source=Majority` — needs a campaign record). Collection-wide after run: 252 attributed, 51 empty.

## fix_dm_campaign_sent_date_tool.py
**Purpose**: Correct the placeholder `sent_at` on the four `dm_impact_*` direct-mail campaigns. They were ingested from RumbleUp audience CSVs (no send date), so `sent_at` defaulted to the ingest timestamp 2026-05-14 — but the real drop was ~March 2026 (every attributable conversion landed 2026-03-13 → 03-31). Repoints `sent_at` on the 4 campaigns AND their 1,000 letter exposures, preserving provenance: original kept in `sent_at_ingest`, plus `sent_at_estimated` flag and `sent_at_source` note when inferred.

**Date**: defaults to the earliest dm_impact-attributed conversion (a "delivered no later than" floor, flagged estimated). Pass `--date YYYY-MM-DD` once the true vendor drop date is known (clears the estimated flag).

**Usage**:
```bash
source venv/bin/activate
python scripts/fix_dm_campaign_sent_date_tool.py                   # dry-run, inferred date
python scripts/fix_dm_campaign_sent_date_tool.py --date 2026-03-10 --apply   # known date
```

**Output (initial run, 2026-06-02)**: 4 campaigns + 1,000 exposures repointed 2026-05-14 → **2026-03-13 (ESTIMATED**, source "earliest dm_impact-attributed conversion"). Original ingest date preserved in `sent_at_ingest` on all 1,004 docs. **Action needed**: re-run with `--date` when the real RumbleUp/vendor drop date is confirmed.

## export_text7x_8x_participant_csv_tool.py
**Purpose**: Read-only export of the Text7X/8X (Text75-84) campaign cohort to a single 24-column CSV — one row per participant targeted by at least one selected Text campaign. Combines LOCATE-appended demographics (Melissa Data), self-reported applicant data, and engagement across text (Text75-84), direct mail (DM IMPACT), and email (EGE WinterCrisis 2026). Adapts `export_participant_master_csv_tool.py` (from the original checkout) with a cohort filter + Melissa LOCATE join. Makes no DB writes.

**Cohort filter**: `--campaigns` selects which Text campaigns define the population (accepts `75`, `text75`, or full slugs; default all ten). The filter changes *which participants* appear, not which columns — all ten Text columns are always emitted (stable schema).

**Text cell code** (kept from the master export, reviewed 2026-06-02): `received=1, clicked=2, opted_out=3, undeliverable=4, negative_response=5`, blank = not targeted. SMS has no open event, so the literal `2=opened` from the column note cannot occur; the richer 1-5 code is used.

**(locate) demographics**: phone-matched to the Melissa Data LOCATE CSV (`--locate-csv`, default `/home/yersinia/devel/oc-orig/octopus/data/demographic/20260121-frankline/all_not_in_demographic_db_FINAL.csv`; warns + leaves columns blank if absent). Fills Age (from MD_DateOfBirth), Children/Senior (MD_PresenceOf*), Income Append (MD_HouseholdIncome bracket → midpoint), Household size. An applicant's self-reported value overrides the appended value where present. **Number of Adults stays blank** — no source has an adult-count field. Email columns use the EGE_WinterCrisis_2026 campaign (only 2026 email; ~89% cohort coverage).

**Intake likely campaign** (`infer_intake_campaign`): priority = (1) application UTM source/medium → (2) a same-day exposure, preferring `clicked` over `received`, then latest by send time → (3) most recent exposure on/before entry_date → (4) `N/A`. The same-day rule (added 2026-06-03) corrects a timezone bug: exposure `sent_at` is UTC while application `entry_date` is local Eastern, so a strict `sent_at<=entry_date` test dropped same-day text clicks (which blast ~21:00 UTC ≈ 16:00 ET) and produced `N/A` (no prior exposure) or a stale months-old campaign (older exposure survived). On current data the fix cleared all 43 `N/A`s to 0 and reattributed 111 stale rows; 150/154 changed rows now resolve to a same-day *clicked* exposure, 4 to same-day *received*. Requires `load_intake_exposures` to project `unified_status` (so the same-day branch can prefer clicks).

**Usage**:
```bash
source venv/bin/activate
python scripts/export_text7x_8x_participant_csv_tool.py                 # all 75-84 → exports/
python scripts/export_text7x_8x_participant_csv_tool.py --campaigns 75,76,83
python scripts/export_text7x_8x_participant_csv_tool.py --output /tmp/out.csv
```

**Output (full run, 2026-06-03)**: 7,417 cohort rows; LOCATE phone-matched 5,877 (79%); filled age 4,968 / children 5,520 / senior 5,657 / household 6,333 / income-append 6,418; 249 applicant matches; income-reported 234; intake likely campaign `N/A` count 0 (was 41 before the same-day fix).

---

## backfill_franklin_impact_demographics_tool.py

Backfills missing demographic fields into the `FranklinCountyDemographic`
collection (`empower_development`) from the IMPACT Franklin 2,500-row source file
(`~/devel/oc-orig/octopus/data/demographic/20260121-frankline/IMPACT_franklin_2500_final.xlxs`,
converted to CSV alongside it).

**Non-destructive**: writes a field only when the DB value is missing/sentinel
(`-1`, `''`, `nan`) AND the source carries a real value — existing good values are
preserved. Matched on `parcel_id`. Idempotent.

**Fields backfilled** (source → DB, format-matched to existing docs):
- `MD_PresenceOfSenior` → `presence_of_senior` (`Yes`/`No`)
- `Age in Two-Year Increments - 1st Individual` → `owner_age` (int)
- `Number of Adults` → `number_of_adults` (int)
- `Marital Status` → `marital_status` (`S`→Single, `M`→Married, A/B passthrough)
- `MD_EstimatedHomeValue` → `estimated_home_value` (int)
- `MD_PresenceOfChildren` (fallback `Presence of Children` Y/N) → **new** `presence_of_children` (`Yes`/`No`)

Stamps provenance on every modified doc: `backfill_at`, `backfill_from`, `backfill_fields`.

```bash
python scripts/backfill_franklin_impact_demographics_tool.py            # dry run
python scripts/backfill_franklin_impact_demographics_tool.py --apply    # write
```

**Output (2026-06-03)**: 2,500/2,500 rows matched; 2,472 docs modified.
Fills: presence_of_senior +859, owner_age +1,182, number_of_adults +1,224,
marital_status +1,177, estimated_home_value +1,379, presence_of_children +2,375
(new field). Post-backfill DB coverage now equals source-file coverage for all
fields of interest (income, children, senior, age, adults, marital, home value).

---

## enrich_participants_franklin_demographics_tool.py

Enriches `participants.demographics` from the (backfilled) `FranklinCountyDemographic`
collection. Joins on `linkage.parcel_id` (direct, falling back to digits-only
normalization). The cohort participants are ~100% Franklin and the parcel match
rate is 99.9% — far better than the phone-keyed LOCATE join (79%).

**Non-destructive**: a demographics sub-field is written only where the participant
slot is null/absent AND the Franklin doc has a value. Idempotent. Stamps
`demographics_enriched_at/from/fields` provenance on each modified participant.

Fills: `demographics.owner_age`, `presence_of_children`, `presence_of_senior`
(new slots), `number_of_adults`, `marital_status`, `estimated_income`,
`household_size` (FCD `md_householdsize`).

```bash
python scripts/enrich_participants_franklin_demographics_tool.py            # dry run
python scripts/enrich_participants_franklin_demographics_tool.py --apply    # write
```

**Output (2026-06-03)**: 8,823 Franklin participants updated (3 unmatched).
Fills: owner_age +6,772, presence_of_children +1,881 (limited to the IMPACT-2500
subset where FCD carries children), presence_of_senior +5,282, number_of_adults
+6,703, marital_status +6,755, estimated_income +6,888, household_size +6,727.

### export_text7x_8x_participant_csv_tool.py — demographics fallback added (2026-06-03)
build_row() now reads `participant.demographics` as a fallback after the LOCATE
CSV for age (`owner_age`), children (`presence_of_children`), senior
(`presence_of_senior`), and Number of Adults (`number_of_adults`, previously
always blank). New helper `yn_from_yesno()` maps the 'Yes'/'No' presence flags to
'Y'/'N'. Post-enrichment coverage (7,417-row cohort): age 4,968→5,476,
children 5,520→6,043, senior 5,657→6,170, household 6,333→7,260,
income 6,418→7,414, Number of Adults 0→5,315.

### backfill_campaign_weather_tool.py — embed local weather on each campaign (2026-07-07)
Adds an embedded `weather` sub-document to every doc in `campaigns`
(`empower_development`). Resolves each campaign's **dominant county** from its
recipients (`exposures.campaign_id` → `exposures.participant_oid` →
`participants.linkage.county_key`), then fetches daily historical weather for that
county's centroid over the window `[sent_at − 5d, sent_at]` (6 inclusive days)
from the Open-Meteo archive API (free, no key, Fahrenheit). Computes temp
mean/min/max, HDD/CDD (base 65°F), and extreme-day counts (freezing <32°F,
hot >90°F). Idempotent (skips campaigns already having `weather` unless `--force`);
memoizes `(county, window)` fetches. County centroids for the 25 Ohio counties
are a static table in the script (CountyKeys has no lat/lon).
Design: `.claude_docs/20260707_1551_campaign_weather_design.md`.
Tests: `tests/test_campaign_weather.py` (11 unit tests on the pure logic).

```bash
python scripts/backfill_campaign_weather_tool.py --dry-run --limit 12   # preview
python scripts/backfill_campaign_weather_tool.py                        # write all
python scripts/backfill_campaign_weather_tool.py --force                # recompute
```

**Result (2026-07-07)**: 163 campaigns tagged — 153 `ok`, 6 `no_send_date`,
4 `no_county`; 107 unique (county, window) API fetches. Winter Crisis text
campaigns correctly show mean ~11°F, HDD ~322, 6 freezing days.

### backfill_campaign_weather_tool.py — added threshold HOURS (2026-07-07, update)
Extended to also request **hourly** temperature from the Open-Meteo archive and
count `freezing_hours` (hourly temp < 32°F), `hot_hours` (> 90°F), and
`window_hours` (144 for a full window) into `weather.extremes`. Hours measure the
*duration* of extremes that the day counts only flag. Re-run with `--force` to
update existing docs. New pure fn `threshold_hours()`; tests extended to 12.
Notable: the Feb-4-2026 Winter Crisis send read 144/144 freezing hours.

### analyze_bayesian_model_inputs_tool.py — live model-input coverage report (2026-07-08)
Reusable EDA companion to `.claude_docs/20260708_0940_bayesian_model_inputs_catalog.md`.
One pass over `empower_development` printing: campaign weather coverage and
collinearity (incl. within-month HDD spread — the identification currency for
weather effects), exposure outcome rates by channel + duplicate-pair count,
participant covariate coverage (exposed the `income_level` 13% trap and county-key
drift), the joined effective-N funnel for the weather→engagement models (base
frame + `kwh_cl_slope` dose subset with seasonal support), and Text75-84 cohort
conversion counts. Findings feed `20260708_1635_bayesian_model_proposals.md`.

```bash
source venv/bin/activate
python scripts/analyze_bayesian_model_inputs_tool.py
```

### export_application_exposure_dataset_tool.py — F6 application-conversion dataset (2026-07-13)
Materializes the exposure-grain frame behind the f06 Bayesian model
(`src/bayesian-fable/core/frames.load_application_frame`) as a shareable CSV in
`exports/`. One row per deduped (participant, campaign) send: `applied` outcome
(best-confidence attributed trigger of the participant's earliest application,
post-application sends censored), channel/agency, message-theme one-hots,
window weather (HDD/CDD, temp, freezing/hot hours), communication-sequence
features (prior-send count, receipt-lag-adjusted recency with letters +6 days,
first/last-in-wave and last-week flags), and demographics incl. the sparse
Franklin fields (owner_age, children, senior, adults). Prints event counts by
attribution method, channel mix, and coverage. First run (2026-07-13): 210,831
rows, 227 events.

```bash
source venv/bin/activate
python scripts/export_application_exposure_dataset_tool.py
```

### compute_f06_scenario_contrasts_tool.py — f06 posterior contrasts on outcome scale (2026-07-14)
Loads the latest f06 (impact2026) trace and reports population-average
applications per 10,000 sends under counterfactual factor settings (last-week /
first-in-wave / first-contact flags flipped, HDD at mean vs +1SD, income at
$25k vs $60k). Feeds the scenario table in
`.claude_docs/20260713_1030_f06_application_hazard_results.md` and the lay
summary `.claude_docs/20260714_0910_f06_results_plain_language.md`.

```bash
source venv/bin/activate
python scripts/compute_f06_scenario_contrasts_tool.py
```

### backfill_impact2026_message_types_tool.py — code message_types on IMPACT-2026 text campaigns (2026-07-15)
Backfills the six-code `message_types` theme labels onto the 12 IMPACT-2026
text campaigns (Jan–Mar 2026) that were sent uncoded. The 12 campaigns reuse
only 4 distinct message bodies, each verbatim-identical to an already-coded
2025 campaign (Text31–34, Text19–22, Text63–68, Text71–74), so codes are
inherited from those twins for coder consistency. Idempotent; skips campaigns
whose existing codes conflict. `--dry-run` reports without writing. Unlocks
the message-theme question in the f06 application-hazard analysis.

```bash
source venv/bin/activate
python scripts/backfill_impact2026_message_types_tool.py [--dry-run]
```

### get_participant_profile_tool.py — full participant profile by _id / phone / name (2026-07-16)
**Reusable Tool**. Resolves an identifier (24-hex ObjectId, phone number, or
case-insensitive name substring, tried in that order) to one or more
participants and prints everything known about each: the participant
document, campaign exposures, application match (both the modern
`applications` collection and the legacy `applicants` collection), and
county-specific enrichment — demographic, residential, electrical, thermal
load, gas, and multi-tenant data joined via `linkage.parcel_id` — plus a
Melissa LOCATE CSV phone match and an energy-burden verdict (flags
`total_energy_burden > 6%` as high burden per the Model 02 hypothesis
threshold). Generalizes `investigate_participant_debug.py` (which is
Franklin-only and ID-only) to all ~30 ingested counties and to phone/name
lookups. Read-only. Name searches matching >5 participants print a
disambiguation list (capped at 30 rows) instead of dumping every profile.
Backs the `participant-profile` skill — see
`.claude/skills/participant-profile/SKILL.md` for the county-collection
naming quirks and field-meaning notes this tool encodes.

**Usage:**
```bash
source venv/bin/activate
python scripts/get_participant_profile_tool.py 69a61c0f9595ac4823aeb4b4
python scripts/get_participant_profile_tool.py 6142640950
python scripts/get_participant_profile_tool.py "Tuan Nguyen"
```

## gpu_env_tool.sh (2026-07-16)

Sourceable environment setup for GPU-accelerated PyMC/JAX runs. Activates the
repo venv and prepends the venv's pip-installed `nvidia/*/lib` CUDA 12.9
libraries to `LD_LIBRARY_PATH` so the system CUDA 12.4 toolkit in
`/usr/local/cuda` cannot shadow them (that shadowing breaks
`libcublasLt`/`cuSPARSE` loading and silently drops JAX to CPU). Also disables
XLA GPU memory preallocation. Usage: `source scripts/gpu_env_tool.sh`.

## run_bayesian_campaign_models_tool.sh (2026-07-16)

Sequential GPU sweep of every bayesian-fable campaign-model configuration for
the clicks + applications goal: F1 pooling ladders for `text_clicked` and
`email_clicked`, the F7 (text click, IMPACT winter cohort) and F8 (email
click, summer collection) predictor ladders with PSIS-LOO comparison, F2
replied models pooled/summer/winter, and F6 application-hazard refits with
message themes (post 2026-07-15 backfill), with and without campaign REs.
Logs per step to `data/inference/fable/logs/`; failures don't stop the sweep.

## summarize_fable_results_tool.py (2026-07-16)

Consolidates bayesian-fable fit outputs (`data/inference/fable/`) into one
markdown summary: convergence overview from the latest `report_*.json` per
model directory, coefficient tables (with odds ratios for `b_*` terms, RE
scales, ICC) from the latest `summary_*.csv`, and all persisted PSIS-LOO
ladder comparison CSVs. `--filter` restricts by directory-name substring;
`--out` writes to a file.

## render_claude_docs_html_tool.py (2026-07-16)

Renders `.claude_docs` markdown artifacts to standalone styled HTML (same
basename, `.html` extension) with inline CSS readable in light and dark
themes; tables and fenced code supported. Used to publish the Bayesian
modeling artifacts as .md + .html pairs.

## run_bayesian_reruns_tool.sh (2026-07-17)

Follow-up fits after the 2026-07-16 sweep, covering the steps that needed
code fixes: F2 summer with the season-appropriate hot_hours weather axis, F5
opt-out with the variant-aware outcome name, the F8 email-click ladder in its
memory-safe campaign-grain Binomial form, and the F7 text-click ladder at 500
draws (pointwise log-likelihood fits in ~0.6 GB). Same logging convention as
the main sweep driver.

## ingest_electric_bills_tool.py
**Purpose**: Ingest utility pre-enrollment electric usage lists (AEP, AES, Duke, FirstEnergy) from `data/electric-bills/` zips into `{County}ElectricalDB` collections. Dry-run by default (`--execute` to write); dry run prints/writes a per-county refresh summary (docs updated/created, readings added, match rates). Streams nested zips without full extraction; matches service addresses to parcels via shared `src/tools/address_normalization.py`; unmatched accounts stored with deterministic surrogate `_id` (parcel_id=null). Supporting package: `src/tools/utility_bills/` (record, parsers, sources registry, ingest engine). NOTE: kW peak demand, KVAR/on-peak splits (AES), and read-vs-estimated flags (Duke) exist in the raw files but are deliberately NOT stored (decision 2026-08-19). Known-bad archives are documented in `src/tools/utility_bills/sources.py` (Jan 2026 AEP zip corrupt; "AEP August 2026.zip" is a mislabeled AES duplicate).

## audit_thermal_load_coverage_tool.py
**Purpose**: Read-only audit of `*ThermalLoads` coverage and integrity against `*ElectricalDB` across all 25 thermal counties. Six named checks via `--check`: `coverage` (parcels eligible for slopes vs parcels that have them, plus no-parcel_id and below-minimum-period populations), `types` (parcel_id BSON type mismatches — Thermal stores int/Int64 where Electrical stores str), `duplicates` (duplicate parcel_id within each collection), `joinkey` (parcel_id vs the indexed parcel_key as join field, reporting phantom gaps), `staleness` (electrical delivery tags vs thermal provenance stamps), `slopes` (null/zero/absent `kwh_hl_slope` and surviving real gas regressions). `--check all` runs everything; `--county` restricts; `--json` writes results. Never writes. Baseline measured 2026-09-16: 60,733 genuinely missing, 1,622 phantom, 67,307 non-string parcel_id, 875 thermal duplicates, 16,419 electrical duplicates, 126,987 real gas slopes. Companion to `.claude_docs/20260916_1300_thermal_slope_remediation_runbook.md`.
