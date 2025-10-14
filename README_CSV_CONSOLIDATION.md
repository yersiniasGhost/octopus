# CSV Consolidation & MongoDB Enrichment

## Overview

Two-step pipeline to consolidate EmailOctopus campaign CSV files with MongoDB demographic enrichment:

1. **`zipcode_to_county_mapper.py`**: Build cached zipcode-to-county mapping from MongoDB
2. **`csv_consolidator.py`**: Consolidate CSVs with demographic enrichment and county identification

## Quick Start

```bash
# Step 1: Build zipcode-to-county cache (one-time setup)
cd /home/frich/devel/EmpowerSaves/octopus
python zipcode_to_county_mapper.py

# Step 2: Consolidate CSVs with enrichment
python csv_consolidator.py --filter all
# OR for engaged users only
python csv_consolidator.py --filter engaged
```

## Scripts

### 1. `zipcode_to_county_mapper.py`

**Purpose**: Pre-build zipcode-to-county lookup from MongoDB demographic collections.

**How it works**:
- Scans all MongoDB `*Demographic` and `*Residential` collections
- Extracts county names from collection names (e.g., `OttawaDemographic` → `Ottawa`)
- Maps all zipcodes to their counties
- Saves cache to `data/zipcode_to_county_cache.json`

**Usage**:
```bash
python zipcode_to_county_mapper.py
```

**Output**:
- Creates `data/zipcode_to_county_cache.json` with zipcode→county mappings
- Reports multi-county zipcodes (zipcodes spanning multiple counties)

**When to re-run**:
- After adding new county data to MongoDB
- If county boundaries or zipcode assignments change

---

### 2. `csv_consolidator.py`

**Purpose**: Consolidate all EmailOctopus campaign CSVs into single enriched output.

**Matching Strategy** (Hierarchical):
1. **Email exact match** → MongoDB demographic record
2. **Address normalization match** → MongoDB address
3. **Cell phone match** → MongoDB mobile number
4. **Fallback**: Use zipcode→county cache for unmatched records

**Performance Optimization**:
- Pre-loads all MongoDB demographic data into memory (email, address, phone indexes)
- Eliminates repeated database queries (~130K records processed in 5-15 minutes)

**Usage**:
```bash
# Process all records
python csv_consolidator.py \
    --input-dir ./data/exports \
    --output ./data/consolidated_all.csv \
    --filter all

# Process only engaged users (opened OR clicked)
python csv_consolidator.py \
    --input-dir ./data/exports \
    --output ./data/consolidated_engaged.csv \
    --filter engaged
```

**Arguments**:
- `--input-dir`: Directory containing EmailOctopus CSV files (default: `./data/exports`)
- `--output`: Output CSV file path (default: `./data/consolidated_output.csv`)
- `--filter`: Filter mode
  - `all`: Include all records
  - `engaged`: Include only records where `opened=Yes` OR `clicked=Yes`

**Output CSV Columns**:
```
person_id              # Email or name
campaign_name          # Campaign identifier
opened                 # Yes/No
clicked                # Yes/No
applied                # Always 0
county                 # Identified county
zipcode                # From CSV or MongoDB
address                # From CSV
name                   # Customer name
email                  # Email address
cell                   # Cell phone
estimated_income       # From MongoDB (-1 if not matched)
energy_burden_kwh      # From MongoDB (-1 if not matched)
total_energy_burden    # From MongoDB (-1 if not matched)
```

**Statistics Reported**:
- Total input records
- Engaged records (opened or clicked)
- Successfully matched to MongoDB
- Output record count
- Missing county data count
- Match rate percentage

## Example Output

```
============================================================
CSV Consolidation Statistics
============================================================
Total input records:        129,551
Engaged records (O or C):   0
Matched to MongoDB:         0
Output records:             129,551
Missing county data:        45,230
Match rate:                 0.0%
============================================================
```

## Data Flow

```
EmailOctopus CSVs (~/data/exports/*.csv)
    ↓
[Load all CSVs]
    ↓
[Filter by engagement] ← --filter [all|engaged]
    ↓
[Match to MongoDB]
    ├→ Email match (primary)
    ├→ Address match (secondary)
    ├→ Cell match (tertiary)
    └→ Zipcode→County fallback
    ↓
[Enrich with demographics]
    ↓
Consolidated CSV output
```

## Performance Considerations

### Current Dataset
- **~130K records** across all campaign CSVs
- **0 engaged records** (no "Yes" in opened/clicked currently)

### Optimization Strategies
1. **In-memory caching**: Pre-loads all MongoDB demographic data
2. **Indexed lookups**: Email, address, and phone number dictionaries
3. **Batch processing**: Single pass through CSVs
4. **Cached zipcode mapping**: No repeated MongoDB queries for county lookups

### Expected Runtime
- **Zipcode cache build**: 30-60 seconds
- **CSV consolidation (all)**: 5-15 minutes for 130K records
- **CSV consolidation (engaged)**: <1 minute if few engaged records

## Troubleshooting

### Cache file not found
```
Error: Cache file not found: data/zipcode_to_county_cache.json
```
**Solution**: Run `python zipcode_to_county_mapper.py` first

### MongoDB connection error
```
Error: Environment variable is not set: MONGO_CONNECTION_URL
```
**Solution**: Ensure `MONGO_CONNECTION_URL` is set in environment

### Low match rate
- **Check CSV data quality**: Verify email/address/phone fields are populated
- **Verify MongoDB data**: Ensure demographic collections have matching records
- **Review normalization**: Address normalization may need tuning for your data

### Missing county data
- **Zipcode not in MongoDB**: Zipcode doesn't exist in any demographic collection
- **Invalid zipcode**: CSV has empty or invalid zipcode field
- **Solution**: Review zipcode coverage in MongoDB or add external zipcode database

## Future Enhancements

1. **Fuzzy name matching**: Add name similarity scoring for unmatched records
2. **External zipcode database**: Integrate USPS or Census zipcode→county data
3. **Match confidence scoring**: Add confidence levels to matched records
4. **Parallel processing**: Multi-threaded CSV processing for larger datasets
5. **Incremental updates**: Support appending new campaigns to existing output

## Dependencies

- Python 3.7+
- pymongo
- pydantic
- Standard library: csv, json, re, pathlib, argparse

## File Structure

```
octopus/
├── zipcode_to_county_mapper.py   # Cache builder
├── csv_consolidator.py           # Main consolidation script
├── README_CSV_CONSOLIDATION.md   # This file
└── data/
    ├── exports/                  # Input CSVs
    │   └── campaign_*.csv
    ├── zipcode_to_county_cache.json  # Generated cache
    └── consolidated_output.csv   # Output file
```
