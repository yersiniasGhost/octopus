# Data Access Reference Guide

## Overview

This document provides a comprehensive reference for accessing, matching, and managing data across the Octopus project's database systems and exports.

---

## Database Architecture

### MongoDB Databases

| Database | Environment Variable | Purpose | Host |
|----------|---------------------|---------|------|
| `emailoctopus_db` | `MONGODB_OCTOPUS` | Campaign/participant data synced from EmailOctopus API | localhost |
| `empower_development` | `MONGODB_DATABASE` / `MONGODB_DATABASE_RM` | County demographic and residential data | localhost / 192.168.1.156 |

### Connection Configuration (.env)

```bash
# Local MongoDB (emailoctopus_db)
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=empower_development
MONGODB_OCTOPUS=emailoctopus_db

# Remote MongoDB (county data)
MONGODB_HOST_RM=192.168.1.156
MONGODB_PORT_RM=27017
MONGODB_DATABASE_RM=empower_development
```

---

## Database Collections

### emailoctopus_db (MONGODB_OCTOPUS)

| Collection | Key Fields | Description |
|------------|------------|-------------|
| `campaigns` | `campaign_id` (unique), `name`, `status`, `statistics`, `synced_at` | Email/text campaign metadata |
| `participants` | `campaign_id + contact_id` (compound unique), `email_address`, `engagement`, `fields` | Campaign participants with engagement data |
| `applicants` | `entry_id` (unique) | Matched applicant records from CSV imports |

**Indexes:**
- `campaigns.campaign_id` (unique)
- `campaigns.status`
- `campaigns.synced_at`
- `participants.campaign_id + contact_id` (compound unique)
- `participants.campaign_id`
- `participants.email_address`

### empower_development (MONGODB_DATABASE_RM)

Collections follow naming pattern: `{County}CountyDemographic` and `{County}CountyResidential`

| Collection Pattern | Key Fields | Description |
|-------------------|------------|-------------|
| `{County}CountyDemographic` | `parcel_id`, `parcel_zip`, `customer_name`, `email`, `mobile`, `estimated_income`, `age in two-year increments - 1st individual` | Customer demographic data |
| `{County}CountyResidential` | `parcel_id`, `address`, `parcel_zip`, `age` (year built) | Property/residence data |

**Available Counties** (based on collections):
- AthensCounty, FranklinCounty, RichlandCounty, MarionCounty, MorrowCounty, and others

---

## Data Retrieval

### EmailOctopus Data (src/tools/mongo.py)

```python
from src.tools.mongo import Mongo

# Singleton pattern - auto-connects using env vars
mongo = Mongo()
db = mongo.database  # Access emailoctopus_db

# Query campaigns
campaigns = db.campaigns.find({'status': 'SENT'})

# Query engaged participants
engaged = db.participants.find({
    '$or': [
        {'engagement.opened': True},
        {'engagement.clicked': True}
    ]
})
```

### County Data (Direct Connection)

```python
from pymongo import MongoClient
import os

# Connect to remote county database
client = MongoClient(
    os.getenv('MONGODB_HOST_RM'),
    int(os.getenv('MONGODB_PORT_RM', '27017'))
)
db = client[os.getenv('MONGODB_DATABASE_RM')]

# Query demographic data for a county
county = 'RichlandCounty'
demographics = db[f'{county}Demographic'].find({'parcel_zip': 44903})

# Query residential data
residences = db[f'{county}Residential'].find({'parcel_zip': 44903})
```

---

## Data Matching Strategies

### Matching Priority Order

The system uses multiple matching strategies in priority order:

1. **Email Match** (highest confidence) - Match participant email to demographic.email
2. **Name Match** - Match FirstName + LastName to demographic.customer_name
3. **Phone Match** - Match participant Cell to demographic.mobile
4. **Address + Phone** - Combined match for highest confidence
5. **Address Exact** - Exact normalized address match
6. **Address Fuzzy** - Partial address match with score threshold

### Address Normalization

```python
# src/scripts/match_participants_optimized.py - AddressNormalizer class
# Transforms: "123 Main Street" -> "123 main st"

STREET_ABBREV = {
    'street': 'st', 'avenue': 'ave', 'road': 'rd', 'drive': 'dr',
    'lane': 'ln', 'court': 'ct', 'circle': 'cir', 'boulevard': 'blvd'
}

DIRECTIONAL_ABBREV = {
    'north': 'n', 'south': 's', 'east': 'e', 'west': 'w'
}
```

### Phone Normalization

```python
# Normalize to 10 digits, remove leading 1 if 11 digits
def normalize_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    return digits
```

---

## Data Export Structure

### Campaign CSV Exports (data/exports/)

**File naming:** `campaign_{uuid}_{name}_{date}.csv`

**Columns:**
| Column | Source | Description |
|--------|--------|-------------|
| `campaign_name` | campaigns.name | Campaign name |
| `campaign_sent_at` | campaigns.sent_at | Send date |
| `email` | participants.email_address | Participant email |
| `first_name` | participants.fields.FirstName | First name (often empty) |
| `last_name` | participants.fields.LastName | Last name (often empty) |
| `city` | participants.fields.City | City |
| `zip` | participants.fields.ZIP | ZIP code |
| `address` | participants.fields.Address | Street address |
| `kwh` | participants.fields.kWh | Energy usage |
| `cell` | participants.fields.Cell | Phone number |
| `annual_cost` | participants.fields.annualcost | Annual energy cost |
| `annual_savings` | participants.fields.AnnualSavings | Potential annual savings |
| `monthly_cost` | participants.fields.MonthlyCost | Monthly cost |
| `monthly_saving` | participants.fields.MonthlySaving | Monthly savings |
| `daily_cost` | participants.fields.DailyCost | Daily cost |
| `opened` | participants.engagement.opened | Yes/No |
| `clicked` | participants.engagement.clicked | Yes/No |
| `bounced` | participants.engagement.bounced | Yes/No |
| `complained` | participants.engagement.complained | Yes/No |
| `unsubscribed` | participants.engagement.unsubscribed | Yes/No |
| `status` | participants.status | SUBSCRIBED, etc. |

### Matched Participant Export

**File naming:** `matched_participants_{timestamp}.csv`

**Columns:**
| Column | Source | Description |
|--------|--------|-------------|
| `Name` | demographic.customer_name | Full name from county data |
| `Campaign` | campaigns.name | Campaign name |
| `County` | zipcode_to_county_cache.json | Mapped county |
| `Opened` | engagement.opened | 0/1 |
| `Clicked` | engagement.clicked | 0/1 |
| `Applied` | Always 0 | Application status |
| `Age` | demographic.age in two-year increments | Age bracket |
| `Income` | demographic.estimated_income | Estimated income |
| `YearBuilt` | residential.age | Year home built |

---

## Zipcode to County Mapping

### Cache File

**Location:** `data/zipcode_to_county_cache.json`

**Structure:**
```json
{
  "zipcode_map": {
    "44903": "RichlandCounty",
    "43302": "MarionCounty"
  },
  "multi_county": {
    "44000": ["CountyA", "CountyB"]
  }
}
```

### Cache Maintenance

The zipcode cache was rebuilt on 2025-12-05 using `scripts/fix_zipcode_cache.py` which:
1. Filters to Ohio ZIP codes only (43xxx-45xxx)
2. Uses authoritative county mappings for known ZIP code ranges
3. Preferentially excludes AthensCounty when ZIP appears in multiple counties (due to data quality issues)

**Previously fixed issues:**
- ZIP 44903, 44904 now correctly map to RichlandCounty (was AthensCounty)
- ZIP 43302 now correctly maps to MarionCounty (was AthensCounty)

### Rebuilding the Cache

```bash
# Use the fix script (preferred - includes authoritative mappings)
python scripts/fix_zipcode_cache.py

# Or regenerate from raw collection data (may reintroduce errors)
python scripts/zipcode_to_county_mapper.py
```

**Note:** The original `zipcode_to_county_mapper.py` extracts ZIP codes directly from collections,
which can include bad data. Use `fix_zipcode_cache.py` for cleaner results.

---

## Scripts Reference

### Core Data Pipeline Scripts

| Script | Status | Purpose | Reusable |
|--------|--------|---------|----------|
| `sync_campaigns.py` | VALID | Sync campaigns from EmailOctopus API to MongoDB and CSV | YES |
| `match_participants_optimized.py` | VALID | Match participants to county data using zipcode lookup | YES |
| `export_matched_data.py` | VALID | Export matched participant data to CSV | YES |
| `fix_zipcode_cache.py` | VALID | Rebuild zipcode cache with authoritative Ohio mappings | YES |
| `zipcode_to_county_mapper.py` | SUPERSEDED | Build zipcode cache (use fix_zipcode_cache.py instead) | NO |
| `list_mongo_databases.py` | VALID | Diagnostic - list all MongoDB databases and collections | YES |

### Matching Scripts

| Script | Status | Purpose | Reusable |
|--------|--------|---------|----------|
| `match_participants.py` | SUPERSEDED | Original matching script (slower, searches all counties) | NO - use optimized |
| `match_csv_to_residence.py` | VALID | Match CSV applicants to residence records | YES |
| `match_csv_to_residence_enhanced.py` | VALID | Enhanced matching with 8 strategies | YES |
| `populate_applicants_db.py` | VALID | Import applicants CSV to MongoDB | CONDITIONAL |
| `populate_applicants_db_v2.py` | VALID | Updated applicant import | CONDITIONAL |

### Analysis Scripts

| Script | Status | Purpose | Reusable |
|--------|--------|---------|----------|
| `analyze_export.py` | VALID | Analyze matched export CSV statistics | YES |
| `analyze_final_export.py` | VALID | Final export analysis | YES |
| `analyze_unmatched.py` | VALID | Debug unmatched participants | YES |
| `check_county_fields.py` | VALID | Inspect county collection fields | YES |
| `check_engagement.py` | VALID | Check engagement data | YES |
| `count_csv_engagement.py` | VALID | Count engagement in CSV | YES |

### Testing/Debug Scripts

| Script | Status | Purpose | Reusable |
|--------|--------|---------|----------|
| `test_emailoctopus.py` | VALID | Test EmailOctopus API connection | YES |
| `test_email_matching.py` | VALID | Test email matching logic | CONDITIONAL |
| `test_franklin_matching.py` | VALID | Test Franklin County matching | CONDITIONAL |
| `test_franklin_matching_normalized.py` | VALID | Test normalized matching | CONDITIONAL |
| `test_address_matching.py` | VALID | Test address matching | CONDITIONAL |
| `test_campaign_model.py` | VALID | Test campaign model | YES |

### Data Discovery Scripts

| Script | Status | Purpose | Reusable |
|--------|--------|---------|----------|
| `find_demographic_collections.py` | VALID | Search for demographic collections | YES |
| `find_franklin_county.py` | SPECIFIC | Find Franklin County data | CONDITIONAL |
| `find_matching_counties.py` | VALID | Find counties with data | YES |
| `debug_participant_fetch.py` | DEBUG | Debug participant fetching | CONDITIONAL |

### Deprecated/One-Time Scripts

| Script | Status | Purpose | Reusable |
|--------|--------|---------|----------|
| `enrich_participants.py` | OUTDATED | Email-based enrichment (poor match rate) | NO |
| `migrate_campaigns_add_type.py` | ONE-TIME | Database migration | NO |
| `create_user.py` | UTILITY | Create app user | CONDITIONAL |
| `verify_setup.py` | UTILITY | Verify environment setup | YES |
| `create_text_campaign_tool.py` | UTILITY | Create text campaigns | CONDITIONAL |
| `extract_text_campaigns.py` | UTILITY | Extract text campaign data | CONDITIONAL |
| `import_text_conversations_tool.py` | UTILITY | Import text conversations | CONDITIONAL |

---

## Common Data Operations

### Sync All Campaigns

```bash
source venv/bin/activate
python scripts/sync_campaigns.py --all
```

### Export Specific Campaign

```bash
python scripts/sync_campaigns.py --campaign abc-123-def
```

### Match Participants to County Data

```bash
python scripts/export_matched_data.py
```

### Rebuild Zipcode Cache

```bash
python scripts/zipcode_to_county_mapper.py
```

### View Database Statistics

```bash
python scripts/list_mongo_databases.py
```

---

## Data Model Relationships

```
EmailOctopus API
      │
      ▼
┌─────────────┐    ┌──────────────┐
│  campaigns  │───▶│ participants │
│ (campaign_id)│    │(campaign_id, │
└─────────────┘    │ contact_id)  │
                   └──────────────┘
                          │
                          │ Match via:
                          │ - zipcode → county
                          │ - address/email/phone/name
                          ▼
┌──────────────────────────────────────┐
│     County Data (empower_development)  │
├──────────────────────────────────────┤
│  {County}CountyDemographic           │
│  - parcel_id                         │
│  - customer_name                     │
│  - email                             │
│  - mobile                            │
│  - estimated_income                  │
│  - age                               │
├──────────────────────────────────────┤
│  {County}CountyResidential           │
│  - parcel_id                         │
│  - address                           │
│  - parcel_zip                        │
│  - age (year built)                  │
└──────────────────────────────────────┘
```

---

## API Data Notes

### EmailOctopus Limitations

Per `data/exports/API_REVIEW.md`:

- **FirstName/LastName fields are never populated** in EmailOctopus data
- Names must be sourced from county demographic data (`customer_name`)
- All engagement data (opened, clicked, bounced, complained, unsubscribed) is correctly synced
- Custom fields (Address, City, ZIP, kWh, costs) are properly populated

### Match Rate Statistics (from SUMMARY.txt)

| County | Match Rate | Notes |
|--------|------------|-------|
| MarionCounty | 100% | All matched |
| MorrowCounty | 100% | All matched |
| FranklinCounty | 93.3% | Good |
| RichlandCounty | 54.4% | Moderate |
| AthensCounty | 0.0% | **Zipcode mapping error** |

---

## Troubleshooting

### No Matches Found

1. Check zipcode mapping: `python scripts/list_mongo_databases.py`
2. Verify county collection exists for the zipcode
3. Check if zipcode_to_county_cache.json has correct mappings
4. Run `python scripts/analyze_unmatched.py` for debugging

### Low Match Rate

1. Verify participant data has valid addresses/phones
2. Check address normalization is working
3. Verify county collections have complete data
4. Consider fuzzy matching threshold adjustments

### MongoDB Connection Issues

1. Verify `.env` file has correct host/port settings
2. Test local connection: `mongo localhost:27017`
3. Test remote connection: `mongo 192.168.1.156:27017`
4. Run `python scripts/verify_setup.py`

---

## File Locations Summary

| Type | Location |
|------|----------|
| Environment config | `.env` |
| Campaign CSV exports | `data/exports/campaign_*.csv` |
| Matched exports | `data/exports/matched_participants_*.csv` |
| Zipcode cache | `data/zipcode_to_county_cache.json` |
| Scripts | `scripts/` |
| MongoDB tools | `src/tools/mongo.py` |
| Sync modules | `src/sync/` |
| Data models | `src/models/` |
