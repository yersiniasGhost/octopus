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

---

*Last updated: 2025-12-07*
