# Campaign Data Sync Tool - Implementation Summary

## Overview

Implemented a complete standalone tool to download all EmailOctopus campaign data, store in MongoDB, and export to CSV files with incremental sync support.

## What Was Built

### 1. Infrastructure ✅
Moved and adapted MongoDB utilities from `empower_analytics` project:
- **`src/utils/singleton.py`** - Singleton metaclass for single instance classes
- **`src/utils/pyobject_id.py`** - Pydantic-compatible MongoDB ObjectId wrapper
- **`src/tools/mongo.py`** - MongoDB connection singleton with auto-indexing

### 2. Data Models ✅
Created Pydantic models for type-safe data handling:
- **`src/models/campaign.py`** - Campaign model with statistics
  - Converts EmailOctopus API responses to MongoDB documents
  - Handles nested statistics (sent, opened, clicked, etc.)
  - Parses ISO 8601 datetime formats

- **`src/models/participant.py`** - Participant model with engagement
  - 13 custom fields (email, name, city, ZIP, kWh, energy costs, etc.)
  - Engagement tracking (opened, clicked, bounced, complained, unsubscribed)
  - CSV export method with flattened structure

### 3. Sync Components ✅

**`src/sync/emailoctopus_fetcher.py`**
- Fetches all campaigns with pagination (100 per page)
- Fetches all participants from multiple report endpoints
- Generator-based iteration for memory efficiency
- Handles wrapped vs direct API response structures
- Deduplicates contacts across report types

**`src/sync/mongodb_writer.py`**
- Upsert operations for idempotent syncing
- Bulk participant insertion (batches of 100)
- Query methods for campaigns and participants
- Sync statistics and campaign tracking
- Incremental sync support (find campaigns needing update)

**`src/sync/csv_writer.py`**
- One CSV file per campaign
- Sanitized filenames (removes invalid characters)
- 20 columns including all participant fields and engagement
- Can export from Pydantic models or MongoDB documents

**`src/sync/campaign_sync.py`** - Main orchestrator
- Coordinates all sync operations
- Supports multiple sync modes:
  - Full sync (all campaigns)
  - Specific campaign sync
  - Incremental sync (by timestamp)
  - MongoDB-to-CSV export
- Comprehensive logging and statistics tracking
- Error handling with rollback safety

### 4. CLI Interface ✅

**`scripts/sync_campaigns.py`** - Standalone command-line tool

**Commands:**
```bash
--all                  # Sync all campaigns
--campaign <id>        # Sync specific campaign
--incremental          # Incremental sync (default: 24h)
--export-csv           # Export MongoDB to CSV
--stats                # Show statistics

--hours <n>            # Incremental threshold
--export-dir <path>    # CSV output directory
--verbose              # Debug logging
--mongo-url <url>      # Override env var
```

**Features:**
- Argparse-based CLI with helpful error messages
- Pretty-printed statistics output
- Verbose logging mode for debugging
- Environment variable support with override options

### 5. MongoDB Schema ✅

**Normalized structure (Option B):**

**campaigns** collection:
- `campaign_id` (unique index) - EmailOctopus UUID
- Campaign metadata (name, subject, from, dates, status)
- Statistics with unique/total counts
- `synced_at` timestamp for incremental sync

**participants** collection:
- `{campaign_id, contact_id}` (compound unique index)
- Contact information and custom fields
- Engagement tracking object
- `synced_at` timestamp

**Indexes:**
- `campaigns.campaign_id` (unique)
- `campaigns.status`
- `campaigns.synced_at`
- `participants.{campaign_id, contact_id}` (unique compound)
- `participants.campaign_id`
- `participants.email_address`

### 6. Documentation ✅

**`SYNC_TOOL.md`** (comprehensive guide):
- Architecture overview with component diagram
- Complete MongoDB schema documentation
- Installation and configuration steps
- Usage examples for all CLI commands
- CSV output format specification
- Cron scheduling examples
- Programmatic API usage
- Performance considerations
- Troubleshooting guide
- Future enhancements roadmap

**`README.md`** (updated):
- New "Campaign Data Sync Tool" section
- Quick start examples
- Feature highlights
- Updated project structure
- MongoDB environment variable documentation

**`.env.example`** (updated):
- Added `MONGO_CONNECTION_URL` with format example

**`requirements.txt`** (updated):
- Added `pymongo==4.6.1`
- Added `pydantic==2.5.3`

## Key Features

### Incremental Sync ✅
- Upsert operations prevent duplicates
- Timestamp tracking for efficient syncing
- Configurable time threshold (default: 24 hours)
- Safe to run multiple times (idempotent)

### Memory Efficiency ✅
- Generator-based participant iteration
- Bulk operations in batches of 100
- Pagination handling for large datasets
- Streaming CSV writes

### Data Integrity ✅
- Pydantic validation for all data
- MongoDB unique indexes prevent duplicates
- Engagement data from multiple report types
- Comprehensive error handling

### Flexibility ✅
- Multiple sync modes (full, incremental, specific)
- MongoDB-only or MongoDB + CSV
- Configurable export directories
- Environment variable overrides

## File Structure Created

```
src/
├── models/
│   ├── __init__.py
│   ├── campaign.py (221 lines)
│   └── participant.py (156 lines)
├── tools/
│   └── mongo.py (105 lines)
├── sync/
│   ├── __init__.py
│   ├── emailoctopus_fetcher.py (195 lines)
│   ├── mongodb_writer.py (167 lines)
│   ├── csv_writer.py (147 lines)
│   └── campaign_sync.py (232 lines)
└── utils/
    ├── singleton.py (14 lines)
    └── pyobject_id.py (35 lines)

scripts/
└── sync_campaigns.py (227 lines)

data/
└── exports/  (directory for CSV output)

Documentation:
├── SYNC_TOOL.md (500+ lines)
└── SYNC_TOOL_SUMMARY.md (this file)
```

**Total Lines of Code:** ~1,500 lines
**Total Files Created:** 14 files

## Usage Examples

### First-Time Sync
```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: Add MONGO_CONNECTION_URL and EMAILOCTOPUS_API_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Sync all campaigns
python scripts/sync_campaigns.py --all --verbose

# Output:
# - MongoDB collections: campaigns, participants
# - CSV files: data/exports/campaign_*.csv
# - Statistics: campaigns processed, participants inserted
```

### Daily Incremental Sync
```bash
# Run via cron daily at 2 AM
0 2 * * * cd /path/to/octopus && python scripts/sync_campaigns.py --incremental >> logs/sync.log 2>&1
```

### Export Only
```bash
# Export MongoDB data to CSV without fetching from API
python scripts/sync_campaigns.py --export-csv
```

## MongoDB Connection

**Format:**
```
mongodb+srv://username:password@cluster.mongodb.net/database
```

**Environment Variable:**
```bash
MONGO_CONNECTION_URL=mongodb+srv://user:pass@cluster.mongodb.net/empower
```

## CSV Output Example

**Filename:** `campaign_abc123_November_Newsletter.csv`

**Content:**
```csv
campaign_name,campaign_sent_at,email,first_name,last_name,city,zip,kwh,cell,address,annual_cost,annual_savings,monthly_cost,monthly_saving,daily_cost,opened,clicked,bounced,complained,unsubscribed,status
November Newsletter,2024-11-15,john@example.com,John,Doe,Columbus,43215,12000,6145551234,123 Main St,$6674.70,$2002.41,$556.23,$166.87,$18.29,Yes,No,No,No,No,SUBSCRIBED
```

## Performance Metrics

**API Efficiency:**
- Pagination: 100 records per request
- Parallel report endpoint fetching
- Deduplication to avoid redundant processing

**MongoDB Efficiency:**
- Bulk operations (100 records per batch)
- Indexed queries for fast lookups
- Upsert operations for minimal writes

**Memory Usage:**
- Generator-based iteration (constant memory)
- Streaming CSV writes
- No full dataset loading required

## Error Handling

**API Errors:**
- Graceful handling of rate limits
- Retry logic for temporary failures
- Detailed error logging

**MongoDB Errors:**
- Connection validation
- Duplicate key handling
- Transaction safety

**File System Errors:**
- Directory creation with permissions
- Filename sanitization
- Write error handling

## Testing Recommendations

1. **Test MongoDB Connection:**
```bash
python -c "from src.tools.mongo import Mongo; m = Mongo(); m.set_connection_url('your-url'); print('OK')"
```

2. **Test Single Campaign Sync:**
```bash
python scripts/sync_campaigns.py --campaign <campaign-id> --verbose
```

3. **Verify CSV Output:**
```bash
ls -lh data/exports/
head -n 3 data/exports/campaign_*.csv
```

4. **Check MongoDB Data:**
```python
from src.tools.mongo import Mongo
mongo = Mongo()
mongo.set_connection_url("your-url")

print("Campaigns:", mongo.database.campaigns.count_documents({}))
print("Participants:", mongo.database.participants.count_documents({}))
```

## Future Enhancements

Potential additions discussed in SYNC_TOOL.md:
- Real-time sync via EmailOctopus webhooks
- Advanced duplicate detection across campaigns
- Multi-campaign CSV exports (combined file)
- Data visualization integration
- Conflict resolution strategies
- Soft delete support
- Audit logging

## Migration Notes

Successfully migrated MongoDB infrastructure from `empower_analytics` project:
- ✅ Mongo singleton pattern (adapted for octopus project)
- ✅ PyObjectId Pydantic compatibility
- ✅ Singleton metaclass
- ✅ Compatible with existing empower_analytics database structure

**Note:** This octopus project is now considered the main project going forward.
