# EmailOctopus Campaign Sync Tool

Standalone tool to download all campaign data from EmailOctopus, store in MongoDB, and export to CSV files.

## Overview

The sync tool provides:
- ✅ Complete data download from EmailOctopus API
- ✅ MongoDB storage with incremental sync support
- ✅ CSV export (one file per campaign)
- ✅ Pagination handling for large datasets
- ✅ Engagement tracking (opened, clicked, bounced, etc.)
- ✅ Idempotent operations (safe to run multiple times)

## Architecture

### Components

```
src/
├── models/              # Pydantic data models
│   ├── campaign.py      # Campaign model with statistics
│   └── participant.py   # Participant model with engagement
├── tools/               # Utilities
│   └── mongo.py         # MongoDB singleton connection
├── sync/                # Sync logic
│   ├── emailoctopus_fetcher.py    # API data fetching
│   ├── mongodb_writer.py          # MongoDB operations
│   ├── csv_writer.py              # CSV export
│   └── campaign_sync.py           # Main orchestrator
└── utils/               # Helper utilities
    ├── singleton.py     # Singleton metaclass
    └── pyobject_id.py   # MongoDB ObjectId support

scripts/
└── sync_campaigns.py    # CLI entry point

data/
└── exports/             # CSV output directory
```

### Data Flow

```
EmailOctopus API → Fetcher → Models → MongoDB
                                    ↓
                                  CSV Files
```

## MongoDB Schema

### Collections

**campaigns** collection:
```python
{
  "_id": ObjectId("..."),
  "campaign_id": "uuid",           # EmailOctopus UUID (unique index)
  "name": "November Newsletter",
  "subject": "Your Energy Savings",
  "from_name": "EmpowerSaves",
  "from_email": "info@empowersaves.com",
  "created_at": ISODate("2024-11-01"),
  "sent_at": ISODate("2024-11-15"),
  "status": "SENT",
  "to_lists": ["list-id-1"],
  "statistics": {
    "sent": {"unique": 1000, "total": 1000},
    "opened": {"unique": 450, "total": 520},
    "clicked": {"unique": 120, "total": 145},
    "bounced": {"unique": 12, "total": 12},
    "complained": {"unique": 2, "total": 2},
    "unsubscribed": {"unique": 8, "total": 8}
  },
  "synced_at": ISODate("2024-11-20")
}
```

**participants** collection:
```python
{
  "_id": ObjectId("..."),
  "contact_id": "uuid",            # EmailOctopus contact UUID
  "campaign_id": "uuid",           # Foreign key to campaigns
  "email_address": "john@example.com",
  "status": "SUBSCRIBED",
  "fields": {
    "FirstName": "John",
    "LastName": "Doe",
    "City": "Columbus",
    "ZIP": "43215",
    "kWh": "12000",
    "Cell": "6145551234",
    "Address": "123 Main St",
    "annualcost": "$6,674.70",
    "AnnualSavings": "$2,002.41",
    "MonthlyCost": "$556.23",
    "MonthlySaving": "$166.87",
    "DailyCost": "$18.29"
  },
  "engagement": {
    "opened": true,
    "clicked": false,
    "bounced": false,
    "complained": false,
    "unsubscribed": false
  },
  "synced_at": ISODate("2024-11-20")
}
```

### Indexes

```python
# campaigns
campaigns.campaign_id (unique)
campaigns.status
campaigns.synced_at

# participants
participants.{campaign_id, contact_id} (unique compound)
participants.campaign_id
participants.email_address
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `pymongo==4.6.1` - MongoDB driver
- `pydantic==2.5.3` - Data validation and models

### 2. Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and add:
```bash
# EmailOctopus API
EMAILOCTOPUS_API_KEY=your_api_key_here

# MongoDB Connection
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=emailoctopus_db
```

## Usage

### Sync All Campaigns

Download all campaigns and participants:

```bash
python scripts/sync_campaigns.py --all
```

**What it does:**
1. Fetches all campaigns from EmailOctopus API
2. For each campaign:
   - Fetches campaign details and statistics
   - Saves campaign to MongoDB
   - Fetches all participants with engagement data
   - Saves participants to MongoDB
   - Exports to CSV file

**Output:**
- MongoDB collections: `campaigns`, `participants`
- CSV files: `data/exports/campaign_{id}_{name}.csv`

### Sync Specific Campaign

Sync a single campaign by ID:

```bash
python scripts/sync_campaigns.py --campaign abc-123-def-456
```

### Incremental Sync

Sync only campaigns that haven't been updated recently:

```bash
# Sync campaigns older than 24 hours (default)
python scripts/sync_campaigns.py --incremental

# Sync campaigns older than 6 hours
python scripts/sync_campaigns.py --incremental --hours 6
```

**How it works:**
- Checks `synced_at` timestamp in MongoDB
- Only syncs campaigns older than threshold
- Skips recently synced campaigns (efficient!)

### Export MongoDB to CSV

Export all campaigns from MongoDB without re-fetching from API:

```bash
python scripts/sync_campaigns.py --export-csv
```

**Use case:** Regenerate CSV files after data correction or format changes.

### Show Statistics

View sync statistics:

```bash
python scripts/sync_campaigns.py --stats
```

**Output:**
```
Total campaigns:        45
Total participants:     12,345
Avg participants/campaign: 274.3

CSV exports: 45 files in data/exports
```

### Command-Line Options

```bash
usage: sync_campaigns.py [-h]
       (--all | --campaign ID | --incremental | --export-csv | --stats)
       [--hours HOURS] [--export-dir DIR] [--verbose] [--mongo-url URL]

Options:
  --all                 Sync all campaigns
  --campaign ID         Sync specific campaign
  --incremental         Incremental sync (only old campaigns)
  --export-csv          Export MongoDB to CSV
  --stats               Show statistics

  --hours HOURS         Hours threshold for incremental (default: 24)
  --export-dir DIR      CSV export directory (default: data/exports)
  --verbose, -v         Verbose logging
  --mongo-url URL       MongoDB URL (overrides env var)
```

## CSV Output Format

Each campaign creates one CSV file: `campaign_{id}_{name}.csv`

**Columns:**
```csv
campaign_name,campaign_sent_at,email,first_name,last_name,city,zip,kwh,cell,address,annual_cost,annual_savings,monthly_cost,monthly_saving,daily_cost,opened,clicked,bounced,complained,unsubscribed,status
```

**Example:**
```csv
November Newsletter,2024-11-15,john@example.com,John,Doe,Columbus,43215,12000,6145551234,123 Main St,$6674.70,$2002.41,$556.23,$166.87,$18.29,Yes,No,No,No,No,SUBSCRIBED
```

## Scheduling with Cron

Run automatic syncs with cron:

```bash
# Edit crontab
crontab -e

# Add daily sync at 2 AM
0 2 * * * cd /path/to/octopus && python scripts/sync_campaigns.py --incremental --hours 24 >> logs/sync.log 2>&1

# Add weekly full sync on Sunday at 3 AM
0 3 * * 0 cd /path/to/octopus && python scripts/sync_campaigns.py --all >> logs/sync.log 2>&1
```

## Programmatic Usage

### Python API

```python
from src.sync.campaign_sync import CampaignSync

# Initialize
sync = CampaignSync(
    mongo_connection_url="mongodb+srv://...",
    export_dir="data/exports"
)

# Sync all campaigns
stats = sync.sync_all_campaigns()
print(f"Synced {stats['campaigns_processed']} campaigns")

# Sync specific campaign
sync.sync_campaign("campaign-uuid")

# Incremental sync
stats = sync.sync_incremental(hours=24)

# Export to CSV
count = sync.export_all_to_csv()
```

### Custom Integration

```python
from src.sync.emailoctopus_fetcher import EmailOctopusFetcher
from src.sync.mongodb_writer import MongoDBWriter
from src.tools.mongo import Mongo

# Initialize components
mongo = Mongo()
mongo.set_connection_url("mongodb+srv://...")

fetcher = EmailOctopusFetcher()
writer = MongoDBWriter(mongo)

# Fetch campaigns
campaigns = fetcher.fetch_all_campaigns()

# Process each campaign
for campaign_data in campaigns:
    campaign_id = campaign_data['id']

    # Fetch participants
    for contact_data in fetcher.fetch_all_participants(campaign_id):
        # Process contact...
        pass
```

## Data Models

### Campaign Model

```python
from src.models.campaign import Campaign

# Create from EmailOctopus data
campaign = Campaign.from_emailoctopus(
    campaign_data=api_response,
    statistics=statistics_data
)

# Convert to MongoDB document
doc = campaign.to_mongo_dict()
```

### Participant Model

```python
from src.models.participant import Participant

# Create from EmailOctopus data
participant = Participant.from_emailoctopus(
    contact_data=api_response,
    campaign_id="campaign-uuid",
    report_type="opened"  # Tracks engagement
)

# Convert to CSV row
row = participant.to_csv_row(
    campaign_name="Newsletter",
    campaign_sent_at="2024-11-15"
)
```

## Incremental Sync Strategy

The tool uses **upsert operations** for idempotent syncing:

```python
# MongoDB upsert logic
db.campaigns.update_one(
    {'campaign_id': campaign_id},     # Match criteria
    {'$set': campaign_data},          # Update data
    upsert=True                       # Insert if not exists
)

db.participants.update_one(
    {'campaign_id': campaign_id, 'contact_id': contact_id},
    {'$set': participant_data},
    upsert=True
)
```

**Benefits:**
- ✅ Safe to run multiple times (no duplicates)
- ✅ Updates changed data automatically
- ✅ Tracks sync timestamps
- ✅ Efficient for large datasets

## Performance Considerations

### Pagination

EmailOctopus API limits responses to 100 records per page. The fetcher automatically handles pagination:

```python
# Generator-based iteration (memory efficient)
for contact in fetcher.fetch_all_participants(campaign_id):
    # Process one contact at a time
    # Memory usage stays constant
    pass
```

### Bulk Operations

Participants are inserted in batches of 100 for efficiency:

```python
# Bulk upsert
stats = writer.upsert_participants_bulk(participants)
# {'inserted': 150, 'updated': 25, 'failed': 0}
```

### API Rate Limits

EmailOctopus API has rate limits. The tool handles this gracefully:
- Use `--incremental` to avoid re-fetching unchanged data
- Run during off-peak hours for large datasets
- Monitor API usage in EmailOctopus dashboard

## Troubleshooting

### MongoDB Connection Issues

```bash
# Test connection
python -c "from src.tools.mongo import Mongo; m = Mongo(); m.set_connection_url('your-url'); print('Connected!')"
```

**Common issues:**
- ❌ Firewall blocking MongoDB port (allow IP in MongoDB Atlas)
- ❌ Invalid connection string format
- ❌ Wrong database name in URL

### Missing Environment Variables

```bash
# Check .env file
cat .env | grep MONGO_CONNECTION_URL
cat .env | grep EMAILOCTOPUS_API_KEY
```

### API Errors

Enable verbose logging:
```bash
python scripts/sync_campaigns.py --all --verbose
```

### CSV Export Errors

Check export directory permissions:
```bash
ls -la data/exports
mkdir -p data/exports
chmod 755 data/exports
```

## Migration from empower_analytics

The sync tool reuses MongoDB infrastructure from the `empower_analytics` project:

**Moved files:**
- ✅ `mongo_tools/mongo.py` → `src/tools/mongo.py`
- ✅ `config/singleton.py` → `src/utils/singleton.py`
- ✅ `config/pyobject_id.py` → `src/utils/pyobject_id.py`

**New models:**
- ✅ `src/models/campaign.py` (new)
- ✅ `src/models/participant.py` (new)

**Integration:**
- Same MongoDB singleton pattern
- Same Pydantic model approach
- Compatible with existing tools

## Future Enhancements

Potential additions:
- [ ] Real-time sync via webhooks
- [ ] Duplicate detection across campaigns
- [ ] Advanced analytics queries
- [ ] Multi-campaign CSV exports
- [ ] Data visualization integration
- [ ] Conflict resolution strategies
- [ ] Soft delete support
- [ ] Audit logging

## Support

For issues or questions:
1. Check this documentation
2. Review logs with `--verbose` flag
3. Verify environment configuration
4. Check MongoDB connection and permissions
