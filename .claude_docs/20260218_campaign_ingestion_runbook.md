# Campaign Ingestion Runbook: Color-Coded Text Campaigns

**Date**: 2026-02-18
**Reference Campaign**: IMPACT Winter 2026-01
**Database**: `campaign_data` (MongoDB)

---

## 1. Pipeline Overview

```
  AGENCY DELIVERS                    YOU PREPARE                     YOU RUN
  color-coded Excel(s)               data directory                  scripts
  ─────────────────                  ──────────────                  ───────

  ┌──────────────┐    ┌───────────────────────────┐    ┌─────────────────────────┐
  │  Excel files  │───▶│  data/campaign-{NAME}/    │───▶│  STEP A: Ingest         │
  │  (1+ .xlsx)   │    │  ├─ File1_COLORCODED.xlsx │    │  ingest_{name}_tool.py  │
  │  with color   │    │  └─ File2_COLORCODED.xlsx │    │  --dry-run → live       │
  └──────────────┘    └───────────────────────────┘    └──────────┬──────────────┘
                                                                  │
                              Creates in MongoDB:                 │
                              • campaigns (1 per xlsx)            │
                              • participants (new or matched)     ▼
                              • campaign_exposures (1 per row)
                                                       ┌─────────────────────────┐
                                                       │  STEP B: Export CSVs    │
                                                       │  export_{name}_tool.py  │
                                                       │  --dry-run → live       │
                                                       └──────────┬──────────────┘
                                                                  │
                              Creates on disk:                    │
                              • 6 CSVs (one per color)            │
                              Fixes in MongoDB:                   ▼
                              • application→campaign linkage
                              • do_not_contact flags
                                                       ┌─────────────────────────┐
                                                       │  STEP C (optional):     │
                                                       │  ingest_applications.py │
                                                       │  (already parameterized)│
                                                       └──────────┬──────────────┘
                                                                  │
                                                                  ▼
                                                       ┌─────────────────────────┐
                                                       │  STEP D (optional):     │
                                                       │  attribute_applications │
                                                       │  _to_campaigns.py       │
                                                       └─────────────────────────┘
```

**Script dependency chain**: A must complete before B. C and D are independent of A/B but should run after if you have new application CSVs.

---

## 2. Prerequisites

### What you need from the agency

| Item | Format | Example |
|------|--------|---------|
| Color-coded Excel file(s) | `.xlsx` with row-level cell fills | `EmpowerSaves_OH_Text75_Winter_Section1_COLORCODED.xlsx` |
| Campaign name / section info | Text | "Text75 Section 1", "Text76 Section 2" |
| Agency name | Text | "IMPACT Community Action" |
| Approximate send date | Date | January 2026 |
| County served | Text | "FranklinCounty" |

### Expected Excel format

- **Row 1**: Column headers (variable names differ per agency)
- **Rows 2+**: One row per contact, with cell fill color indicating engagement status
- **Color is read from column A** (first cell in each row)
- Common columns: `Cell` (phone), `Email`, `ServiceAddress1`, `ServiceCity`, `ServicePostalCode`, `parcel_id`, `CustomerName`, `FIRST`, `LAST`, energy fields (`annual_consumption`, `annual cost`, `monthly cost`, etc.)

### Color coding convention

The agency applies these fill colors to each row in the Excel file. The color is extracted from the **first cell (column A)** of each data row. See Section 4 for full color mapping.

### Environment

```bash
# Activate virtualenv before running any script
source venv/bin/activate

# Verify MongoDB is running
mongosh --eval "db.adminCommand('ping')"

# Verify openpyxl is available (reads Excel colors)
python -c "import openpyxl; print('OK')"
```

---

## 3. Step-by-Step Instructions

### Step 0: Prepare the data directory

```bash
# Create a directory for this campaign's data
# Convention: data/campaign-{AGENCY}-{YYYYMM}
mkdir -p data/campaign-IMPACT-202601

# Copy the Excel file(s) from the agency into this directory
cp /path/to/agency/files/*.xlsx data/campaign-IMPACT-202601/
```

Verify the files are present and openable:
```bash
ls -la data/campaign-IMPACT-202601/*.xlsx
```

---

### Step A: Copy & Configure the Ingestion Script

**Template**: `scripts/ingest_impact_winter_campaign_tool.py`

Copy the template and rename for this campaign:
```bash
cp scripts/ingest_impact_winter_campaign_tool.py scripts/ingest_{new_name}_campaign_tool.py
```

#### Hardcoded values to change in the ingestion script

| Line(s) | Variable | Current Value | What to Change |
|---------|----------|---------------|----------------|
| 33-44 | `CAMPAIGN_CONFIG` keys | `'EmpowerSaves_OH_Text75_...'` | Excel filename(s) for this campaign |
| 35 | `campaign_id` | `'text_impact_winter_75'` | Unique ID for this campaign section |
| 36 | `name` | `'EmpowerSaves OH Text75 Winter...'` | Human-readable campaign name |
| 37 | `description` | `'Winter 2026 IMPACT campaign...'` | Campaign description |
| 158 | `agency` | `'IMPACT Community Action'` | Agency running this campaign |
| 160 | `target_audience` | `'IMPACT'` | Target audience label |
| 161 | `campaign_group` | `'IMPACT-Winter-202601'` | Grouping key for related campaigns |
| 163 | `sent_at` | `datetime(2026, 1, 1)` | Approximate send date |
| 192 | `county` (address) | `'FranklinCounty'` | Default county for participants |
| 197 | `county_key` (linkage) | `'FranklinCounty'` | County key for linkage |
| 198 | `method` (linkage) | `'impact_winter_import'` | Import method identifier |
| 239 | `agency` (exposure) | `'IMPACT Community Action'` | Agency in exposure records |
| 241 | `sent_at` (exposure) | `datetime(2026, 1, 1)` | Send date in exposure records |
| 288 | `data_dir` | `Path('/home/yersinia/devel/octopus/data/campaign-IMPACT-202601')` | **Absolute path** to data directory (note: unlike the export script, this is NOT relative — change the full path) |
| 285 | print banner | `'IMPACT WINTER 2026-01...'` | Banner text (cosmetic) |

**Tip**: Search for `IMPACT` and `202601` in the copied script to find most values needing change.

#### Run ingestion

```bash
# ALWAYS dry-run first
source venv/bin/activate
python scripts/ingest_{new_name}_campaign_tool.py --dry-run

# Review output:
#   - Verify file paths resolve
#   - Check color distribution looks reasonable
#   - Confirm row counts match expectations

# If dry-run looks good, run live
python scripts/ingest_{new_name}_campaign_tool.py
```

**What dry-run shows**: Row counts per file, color distribution per file, but does NOT write to the database.

**What live run does**:
1. Creates campaign documents in `campaigns` collection
2. Matches contacts to existing participants (phone → email → parcel_id)
3. Creates new participant records for unmatched contacts
4. Inserts `campaign_exposures` records (one per row)
5. Updates participant engagement summaries
6. Flags opted-out participants (`do_not_contact: true`)

---

### Step B: Copy & Configure the Export Script

**Template**: `scripts/export_campaign_color_csvs_tool.py`

Copy and rename:
```bash
cp scripts/export_campaign_color_csvs_tool.py scripts/export_{new_name}_csvs_tool.py
```

#### Hardcoded values to change in the export script

| Line(s) | Variable | Current Value | What to Change |
|---------|----------|---------------|----------------|
| 36 | `DATA_DIR` | `'data' / 'campaign-IMPACT-202601'` | Path suffix for this campaign's data directory |
| 38-41 | `CAMPAIGN_FILES` keys | Excel filenames | Filenames for this campaign's Excel files |
| 38-41 | `CAMPAIGN_FILES` values | `'text_impact_winter_75'` etc. | campaign_id values (must match ingestion script) |
| 52-59 | `CSV_FILES` values | `'impact_winter_blank_received.csv'` etc. | Output CSV filenames (change prefix) |
| 250 | expected count comment | `'expected ~63'` | Hardcoded GREEN row count in print statement (update or remove) |
| 264 | campaign_id `startswith` | `'text_impact_winter'` | Prefix used to check if applications are already linked |
| 370 | campaign_id regex | `'text_impact_winter'` | Regex used in verification query for linked applications |
| 376 | source_campaigns list | `['text_impact_winter_75', 'text_impact_winter_76']` | Campaign IDs for do_not_contact verification query |
| 342 | print banner | `'IMPACT WINTER 2026-01...'` | Banner text (cosmetic) |

#### Run export

```bash
# Dry-run first
source venv/bin/activate
python scripts/export_{new_name}_csvs_tool.py --dry-run

# Review output:
#   - Color distribution table (per-file and totals)
#   - CSV file sizes and row counts

# CSV export only (skip DB verification)
python scripts/export_{new_name}_csvs_tool.py --skip-db

# Full run: export CSVs + fix application linkage + verify do_not_contact
python scripts/export_{new_name}_csvs_tool.py
```

**What the export script does** (3 steps):
1. **Export CSVs**: Reads Excel files, classifies by color, writes 6 CSVs
2. **Fix application linkage**: Updates `applications.attribution.likely_campaigns` for GREEN (converted) rows
3. **Verify do_not_contact**: Ensures RED (opted-out) participants have `do_not_contact: true`

---

### Step C (Optional): Ingest Applications

If you have a new GravityForms CSV with program applications:

```bash
# This script is already parameterized — no copying needed
python scripts/ingest_applications.py data/applications/APPLICANTS_new_file.csv

# Skip participant matching
python scripts/ingest_applications.py data/applications/APPLICANTS_new_file.csv --no-match

# View collection summary only
python scripts/ingest_applications.py data/applications/APPLICANTS_new_file.csv --summary-only
```

---

### Step D (Optional): Attribute Applications to Campaigns

After ingesting new applications, link them to the campaigns that likely influenced them:

```bash
# Dry run
python scripts/attribute_applications_to_campaigns.py --dry-run

# Run with default 14-day attribution window
python scripts/attribute_applications_to_campaigns.py

# Shorter attribution window
python scripts/attribute_applications_to_campaigns.py --window-days 7
```

---

## 4. Color Mapping Reference

The 6-color engagement schema used by agency staff when color-coding Excel files.

| Color | Hex Code | Theme Code | Meaning | `unified_status` |
|-------|----------|------------|---------|-------------------|
| **Blank** | — | — | Received, no action | `received` |
| **Yellow** | `FFFFFF00` | — | Clicked link, no form completed | `clicked` |
| **Green** | `FF92D050` | — | Completed the signup form | `converted` |
| **Orange** | `FFFFC000` | — | Negative/uninterested reply (not STOP) | `negative_response` |
| **Red** | `FFFF0000` | — | Replied STOP (opted out) | `opted_out` |
| **Blue** | — | `theme_4` | Bad number / undeliverable | `undeliverable` |

### Engagement boolean fields per color

| Color | `text_delivered` | `text_clicked` | `text_form_completed` | `text_replied` | `text_opted_out` |
|-------|:---:|:---:|:---:|:---:|:---:|
| Blank | T | F | F | F | F |
| Yellow | T | T | F | F | F |
| Green | T | T | T | F | F |
| Orange | T | F | F | T | F |
| Red | T | F | F | T | T |
| Blue | F | F | F | F | F |

### How colors are detected in code

The `get_cell_color()` function reads from `cell.fill.fgColor`:
- **RGB colors** (Yellow, Green, Orange, Red): `color.type == 'rgb'` → returns hex string like `'FFFFFF00'`
- **Theme colors** (Blue): `color.type == 'theme'` → returns `'theme_4'`
- **No fill** (Blank): Returns `None`

**Important**: Blue uses a theme color, not an explicit RGB hex. If the agency uses a different Excel theme, `theme_4` may map to a different color. Always verify with `--dry-run` and check the color distribution output.

---

## 5. Verification Checklist

### After Step A (Ingestion)

Run these MongoDB queries to verify the ingestion:

```javascript
// Connect to database
use campaign_data

// 1. Verify campaigns were created
db.campaigns.find({ campaign_group: 'IMPACT-Winter-202601' }).pretty()
// Expected: 1 document per Excel file

// 2. Check campaign statistics
db.campaigns.find(
  { campaign_id: /text_impact_winter/ },
  { campaign_id: 1, 'statistics.total_sent': 1, 'statistics.clicked': 1, 'statistics.converted': 1 }
)

// 3. Count exposures per campaign
db.campaign_exposures.aggregate([
  { $match: { campaign_id: /text_impact_winter/ } },
  { $group: { _id: '$campaign_id', count: { $sum: 1 } } }
])
// Expected: total count should match Excel row counts

// 4. Verify exposure status distribution
db.campaign_exposures.aggregate([
  { $match: { campaign_id: /text_impact_winter/ } },
  { $group: { _id: '$unified_status', count: { $sum: 1 } } },
  { $sort: { count: -1 } }
])
// Should match the color distribution from dry-run

// 5. Check opted-out participants are flagged
db.participants.countDocuments({
  source_campaigns: { $in: ['text_impact_winter_75', 'text_impact_winter_76'] },
  do_not_contact: true
})
// Should match RED row count
```

### After Step B (Export)

```bash
# 1. Verify CSV files exist and have correct row counts
wc -l data/campaign-IMPACT-202601/impact_winter_*.csv
# Subtract 1 from each for the header row

# 2. Cross-check: total CSV rows should equal total Excel data rows
# blank + yellow + green + orange + red + blue = total contacts
```

```javascript
// 3. Verify application linkage (only if applications exist)
db.applications.countDocuments({
  'attribution.likely_campaigns.campaign_id': { $regex: /text_impact_winter/ }
})

// 4. Verify do_not_contact integrity
db.participants.countDocuments({
  do_not_contact: true,
  source_campaigns: { $in: ['text_impact_winter_75', 'text_impact_winter_76'] }
})
```

### Quick sanity check (run after both steps)

```javascript
// All three collections should have related counts
var campaigns = db.campaigns.countDocuments({ campaign_id: /text_impact_winter/ });
var exposures = db.campaign_exposures.countDocuments({ campaign_id: /text_impact_winter/ });
var participants = db.participants.countDocuments({
  source_campaigns: { $elemMatch: { $regex: /text_impact_winter/ } }
});

print(`Campaigns: ${campaigns}`);
print(`Exposures: ${exposures}`);
print(`Participants touched: ${participants}`);
```

---

## 6. Troubleshooting

### Theme colors not matching

**Symptom**: `--dry-run` shows unexpected color codes like `theme_0`, `theme_2`, etc.

**Cause**: The Excel file uses a non-default theme. `theme_4` is blue in the default Office theme, but agencies may use custom themes.

**Fix**:
1. Open the Excel file in a spreadsheet app and visually confirm what color `theme_4` represents
2. If the agency used different theme indices, update the `COLOR_MAPPING` dict to map the correct `theme_N` value
3. You may also see hex codes you don't recognize — add them to `COLOR_MAPPING` with the appropriate engagement fields

### Missing phone numbers (skipped rows)

**Symptom**: Ingestion reports `skipped_no_phone: N` with a significant count.

**Cause**: The `Cell` column is empty or contains non-parseable phone numbers for some rows.

**Fix**:
1. Check if the phone column has a different name (e.g., `Phone`, `Mobile`, `CellPhone`)
2. If the column name differs, update `row.get('Cell')` calls in the ingestion script
3. Verify the phone format — the normalizer expects 10 digits (strips `+1` prefix, non-digit characters)

### Duplicate exposures

**Symptom**: Running ingestion twice creates duplicate `campaign_exposures` records.

**Cause**: The ingestion script uses `insert_many` without a unique constraint on (participant_id, campaign_id).

**Prevention**:
- Always verify you haven't already run the ingestion for this campaign
- If you need to re-run, first delete existing exposures:
  ```javascript
  // CAUTION: only do this if re-ingesting from scratch
  db.campaign_exposures.deleteMany({ campaign_id: 'text_impact_winter_75' })
  db.campaign_exposures.deleteMany({ campaign_id: 'text_impact_winter_76' })
  db.campaigns.deleteMany({ campaign_id: /text_impact_winter/ })
  ```

### Participant matching is too low

**Symptom**: Most contacts are created as new participants instead of matching existing ones.

**Cause**: The matching cascade (phone → email → parcel_id) depends on having normalized values in existing participant records.

**Investigation**:
```javascript
// Check how many existing participants have phone numbers
db.participants.countDocuments({ phone: { $ne: null } })

// Check if phones are in the expected 10-digit format
db.participants.findOne({ phone: { $ne: null } }, { phone: 1 })
```

### Export CSV has 0 rows for a color

**Symptom**: One of the 6 CSVs has only a header row.

**Cause**: Either no rows had that color, or the color was detected as an unexpected hex code.

**Fix**: Check the `--dry-run` color distribution. If you see an "Unknown" color entry, that's a hex code not in `COLOR_MAPPING`. Add it to the mapping dict.

### Column name mismatches

**Symptom**: CSV fields are empty despite data being present in Excel.

**Cause**: The export script's `row_to_csv_dict()` maps specific Excel column names. If the agency uses different headers, the mapping won't find the data.

**Common column name variations**:

| Expected | Possible Alternatives |
|----------|----------------------|
| `Cell` | `Phone`, `Mobile`, `CellPhone` |
| `Email` | `email`, `E-mail`, `EmailAddress` |
| `ServiceAddress1` | `Address`, `Street`, `Service Address` |
| `ServiceCity` | `City`, `Service City` |
| `ServicePostalCode` | `Zip`, `Zipcode`, `Postal Code` |
| `CustomerName` | `Name`, `Full Name`, `Customer` |
| `<VD_FirstName>` | `First Name`, `FirstName`, `FIRST` |

**Fix**: Update `row_to_csv_dict()` in the export script and equivalent `row.get()` calls in the ingestion script.

---

## Appendix: Script Locations

| Script | Path | Parameterized? |
|--------|------|:---:|
| Ingestion template | `scripts/ingest_impact_winter_campaign_tool.py` | No (copy & edit) |
| Export template | `scripts/export_campaign_color_csvs_tool.py` | No (copy & edit) |
| Application ingestion | `scripts/ingest_applications.py` | Yes (CLI args) |
| Campaign attribution | `scripts/attribute_applications_to_campaigns.py` | Yes (CLI args) |

## Appendix: IMPACT Winter 2026-01 Reference Values

These are the actual values used for the first campaign processed through this pipeline, preserved as a reference for future campaigns.

| Setting | Value |
|---------|-------|
| Data directory | `data/campaign-IMPACT-202601/` |
| Excel file 1 | `EmpowerSaves_OH_Text75_Winter_Section1_COLORCODED.xlsx` |
| Excel file 2 | `EmpowerSaves_OH_Text76_Winter_Section2_COLOR CODED.xlsx` |
| Campaign ID 1 | `text_impact_winter_75` |
| Campaign ID 2 | `text_impact_winter_76` |
| Campaign group | `IMPACT-Winter-202601` |
| Agency | `IMPACT Community Action` |
| County | `FranklinCounty` |
| Send date | `2026-01-01` (approximate) |
| Total contacts | ~7,642 across both files |
| Engagement breakdown | 4,363 blank / 2,005 yellow / 1,038 blue / 154 red / 63 green / 19 orange |
