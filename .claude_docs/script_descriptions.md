# Script Descriptions

Brief descriptions of utility scripts in the `scripts/` directory.

## Campaign Management

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
