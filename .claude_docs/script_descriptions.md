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
