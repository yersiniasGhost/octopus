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

## Residence Matching

### match_csv_to_residence.py
Matches CSV applicant data to residence records in MongoDB by performing fuzzy address matching and residence lookups.

### match_csv_to_residence_enhanced.py
Enhanced version of residence matching with improved matching algorithms, multiple matching strategies (exact, fuzzy, normalized), and detailed match quality scoring.

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

## Data Enrichment

### enrich_participants.py
Enriches campaign participant records with additional demographic and engagement data from multiple sources.

### export_matched_data.py
Exports matched residence and applicant data to CSV format for external analysis and reporting.

---

*Last updated: 2025-11-04*
