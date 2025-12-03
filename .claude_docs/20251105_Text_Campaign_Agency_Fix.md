# Text Campaign Agency Fix - 2025-11-05

## Issue Summary

Text campaign `agency` and `message_key` fields were incorrectly parsed from Excel data during import, causing wrong agency names and truncated message keys in the database and dashboard.

**Example Problem:**
- **Excel**: `Text35_Energy_Assistance_MVCAP`
- **Database (WRONG)**: agency="Assistance", message_key="Energy"
- **Expected**: agency="MVCAP", message_key="Energy_Assistance"

**Dashboard Impact:**
- Agency badges showed incorrect names: "Assistance", "Day", "Running", "Costs", "Savings", "Today"
- Should show actual organizations: "MVCAP", "OHCAC", "IMPACT", "COAD"

## Root Cause

### Regex Pattern Bug

**File**: `scripts/extract_text_campaigns.py:53`

**Problematic Pattern:**
```python
pattern = r'Text(\d+)_([^_]+)_([^_]+)(?:_(.+))?'
```

**Why It Failed:**

The pattern `([^_]+)` means "match one or more characters that are NOT underscores". This works for simple cases like `Text1_Prequalified_Impact`, but breaks when the MessageKey contains underscores.

**Parsing Breakdown:**
```
Input: Text35_Energy_Assistance_MVCAP
Pattern matches:
  Group 1 (text_num): 35 ✅
  Group 2 (message_key): "Energy" ❌ (should be "Energy_Assistance")
  Group 3 (agency): "Assistance" ❌ (should be "MVCAP")
  Group 4 (time_variant): "MVCAP" ❌ (should be None)
```

The regex stops at the first underscore after `Text#_`, treating:
- `Energy` as the message key (wrong - should include `_Assistance`)
- `Assistance` as the agency (wrong - should be `MVCAP`)
- `MVCAP` as the time variant (wrong - should be the agency)

## Affected Campaigns

**40 out of 74 campaigns** had incorrect data:

### Multi-Word Message Key Campaigns
```
Text35-38: Energy_Assistance → parsed as "Energy" + agency="Assistance"
Text39-42: Monthly_Savings → parsed as "Monthly" + agency="Savings"
Text43-50: Act_Today → parsed as "Act" + agency="Today"
Text51-58: Fight_Costs → parsed as "Fight" + agency="Costs"
Text59-62: Final_Day → parsed as "Final" + agency="Day" (some variants)
Text63-70: Time_Running_Out → parsed as "Time" + agency="Running"
Text71-74: Final_Day → parsed as "Final" + agency="Day"
```

### Unaffected Campaigns
34 campaigns with single-word message keys were parsed correctly:
- Prequalified, Money, Struggling, Savings, Relief, Improvements, Improved, StayCool

## Solution Implemented

### 1. Fixed Regex Pattern

**File**: `scripts/extract_text_campaigns.py:53-57`

**New Pattern:**
```python
# Use non-greedy (.+?) for message_key and explicitly match known agencies
pattern = r'Text(\d+)_(.+?)_(IMPACT|Impact|OHCAC|MVCAP|COAD|NA)(?:_(.+))?$'
```

**How It Works:**
- `.+?` = Non-greedy match for message_key (captures all underscores until agency match)
- `(IMPACT|Impact|OHCAC|MVCAP|COAD|NA)` = Explicit agency list ensures correct boundary
- `(?:_(.+))?$` = Optional time variant at end

**Parsing Example:**
```
Input: Text35_Energy_Assistance_MVCAP
New pattern matches:
  Group 1: 35 ✅
  Group 2: "Energy_Assistance" ✅ (non-greedy stops at agency match)
  Group 3: "MVCAP" ✅ (explicit agency match)
  Group 4: None ✅ (no time variant)
```

### 2. Created Update Script

**File**: `scripts/fix_text_campaign_agencies.py`

**Purpose**: Update existing campaign records in place without breaking foreign key relationships

**Key Features:**
- Reads Excel data and re-parses with fixed regex
- Matches campaigns by `text_number` (unique identifier)
- Updates `agency` and `message_key` fields in place
- Preserves `_id`, `campaignId`, and all statistics
- Dry-run mode for safe testing

**Why Update In Place:**
- `empower.participants` collection has foreign key: `engagements[].campaign_id`
- Deleting and re-importing would orphan participant engagement records
- In-place update preserves all relationships and IDs

### 3. Database Structure Note

All 74 campaigns share the same `campaign_id`: **"COP90PK"**

The unique identifier is `text_number` (1-74), NOT `campaign_id`.

This is why our update script matches by `text_number`:
```python
# Excel data dictionary uses text_number as key
campaigns_data[text_num] = {...}

# Database lookup by text_number
correct_data = excel_data[text_number]
```

## Execution Results

### Script Execution
```bash
python scripts/fix_text_campaign_agencies.py
```

**Output:**
```
Text Campaign Agency Fix Tool
============================================================
Fix Summary:
  Total campaigns: 74
  Already correct: 34
  Updated: 40
  Errors/Skipped: 0
============================================================
✓ Successfully updated 40 campaigns
```

### Sample Corrections Verified

```
✅ Text35: agency="MVCAP", message_key="Energy_Assistance"
✅ Text51: agency="OHCAC", message_key="Fight_Costs"
✅ Text63: agency="IMPACT", message_key="Time_Running_Out"
✅ Text71: agency="COAD", message_key="Final_Day"
✅ Text39: agency="OHCAC", message_key="Monthly_Savings"
✅ Text43: agency="MVCAP", message_key="Act_Today"
```

### Dashboard Display Test

**Before Fix:**
```
Agency      Campaign Name
Assistance  Energy         ❌
Day         Final          ❌
Running     Time           ❌
Costs       Fight          ❌
```

**After Fix:**
```
Agency      Campaign Name
MVCAP       Energy_Assistance     ✅
COAD        Final_Day             ✅
IMPACT      Time_Running_Out      ✅
OHCAC       Fight_Costs           ✅
```

## Files Modified

### 1. Import Script (Future Imports)
**File**: `scripts/extract_text_campaigns.py`
- **Line 53-57**: Fixed regex pattern in `parse_shortened_name()` function
- **Line 39-44**: Updated docstring with multi-word examples

### 2. Update Script (Database Fix)
**File**: `scripts/fix_text_campaign_agencies.py` (NEW)
- Complete script to fix existing database records
- Includes dry-run mode and verbose logging
- Matches by `text_number` instead of `campaign_id`

### 3. Template (Already Correct)
**File**: `app/templates/dashboards/text.html`
- No changes needed - template displays `campaign.agency` and `campaign.message_key` correctly
- Previously modified to show Agency column with badges and separate Campaign Name column

### 4. Service Layer (Already Correct)
**File**: `app/services/campaign_data_service.py`
- `get_text_campaigns()` method reads data from database correctly
- No changes needed - it just returns what's in the database

## Testing Commands

### Test Fixed Regex Pattern
```bash
python3 -c "
import re
def parse(name):
    pattern = r'Text(\d+)_(.+?)_(IMPACT|Impact|OHCAC|MVCAP|COAD|NA)(?:_(.+))?\$'
    match = re.match(pattern, name)
    if match:
        return match.group(1), match.group(2), match.group(3), match.group(4)
    return None

# Test cases
test_cases = [
    'Text35_Energy_Assistance_MVCAP',
    'Text63_Time_Running_Out_IMPACT_morning',
    'Text71_Final_Day_COAD',
    'Text1_Prequalified_Impact'
]

for test in test_cases:
    result = parse(test)
    print(f'{test} → {result}')
"
```

### Verify Database Corrections
```bash
python3 -c "
from pymongo import MongoClient
from src.utils.envvars import EnvVars

env = EnvVars()
client = MongoClient(env.get_env('MONGO_URI'))
db = client['emailoctopus_db']

# Check sample campaigns
for text_num in [35, 51, 63, 71]:
    campaign = db.text_campaigns.find_one({'text_number': text_num})
    print(f\"Text{text_num}: {campaign['agency']} - {campaign['message_key']}\")
"
```

### Test Dashboard Display
```bash
python3 -c "
from app.services.campaign_data_service import CampaignDataService

service = CampaignDataService()
campaigns = service.get_text_campaigns(limit=5)

for c in campaigns:
    print(f\"{c['agency']:<10} {c['message_key']}\")
"
```

## Prevention

### For Future Imports

Always use the fixed regex pattern when parsing `Text#_MessageKey_Agency[_TimeVariant]` format:

```python
pattern = r'Text(\d+)_(.+?)_(IMPACT|Impact|OHCAC|MVCAP|COAD|NA)(?:_(.+))?$'
```

### Known Agency List

Valid agencies in the system:
- **IMPACT** (or Impact)
- **OHCAC**
- **MVCAP**
- **COAD**
- **NA** (for campaigns without agency)

### Common Multi-Word Message Keys

Be aware of these multi-word patterns:
- `Energy_Assistance`
- `Monthly_Savings`
- `Act_Today`
- `Fight_Costs`
- `Final_Day`
- `Time_Running_Out`

## Related Documentation

- `.claude_docs/20251105_Text_Campaign_Name_Fix.md` - Previous fix for campaign name display format
- `.claude_docs/20251105_Text_Campaign_Fix.md` - Initial text campaign import setup
- `scripts/extract_text_campaigns.py` - Import script with fixed regex
- `scripts/fix_text_campaign_agencies.py` - Database correction script

## Summary

**Problem**: Regex pattern used `[^_]+` which stopped at first underscore, breaking multi-word message keys

**Solution**: Use non-greedy `.+?` with explicit agency matching to correctly parse full message keys

**Result**: 40 campaigns corrected, all 74 campaigns now display accurate agency and message key data

**Impact**: Dashboard now shows correct organization names (MVCAP, OHCAC, IMPACT, COAD) and complete message types (Energy_Assistance, Final_Day, Time_Running_Out, etc.)
