# Engagement Data Fix - Opened/Clicked Tracking

## Problem Identified

The EmailOctopus sync script was not properly tracking engagement data (opened/clicked). All 129,483 participants showed `opened=False, clicked=False` despite actual engagement occurring.

### Root Cause

**Two critical bugs** in the sync logic:

1. **mongodb_writer.py** (lines 64-97, 99-142):
   - Used `$set` operator which **overwrites** the entire document
   - When processing multiple report types (`sent` → `opened` → `clicked`), engagement flags were lost
   - Example: Contact in "sent" gets `opened=False`, then "opened" report should set `opened=True`, but `$set` would overwrite with whatever the current report had

2. **emailoctopus_fetcher.py** (lines 111-114):
   - Global `seen_contacts` set prevented same contact from being processed across different report types
   - Contact processed in "sent" report would be **skipped** in "opened" and "clicked" reports
   - This meant engagement data was never even fetched for most contacts

## Solution Implemented

### 1. MongoDB Upsert Logic Fix (`mongodb_writer.py`)

**Changed from:**
```python
{'$set': participant.to_mongo_dict()}
```

**To:**
```python
update_ops = {
    '$set': participant_dict,  # Update all non-engagement fields
    '$max': {  # Keep True values (True > False in MongoDB)
        'engagement.opened': engagement.get('opened', False),
        'engagement.clicked': engagement.get('clicked', False),
        'engagement.bounced': engagement.get('bounced', False),
        'engagement.complained': engagement.get('complained', False),
        'engagement.unsubscribed': engagement.get('unsubscribed', False)
    }
}
```

**Why this works:**
- MongoDB's `$max` operator compares values and keeps the greater one
- `True > False` in MongoDB, so once a flag is set to `True`, it stays `True`
- Allows multiple upserts (one per report type) to accumulate engagement data

### 2. Fetcher Duplicate Detection Fix (`emailoctopus_fetcher.py`)

**Changed from:**
```python
seen_contacts = set()  # Global across all report types
```

**To:**
```python
seen_per_report = {}  # Separate tracking per report type
seen_per_report[report_type] = set()
```

**Why this works:**
- Prevents pagination loops **within** each report type
- **Allows** same contact to be yielded across different report types
- Each report type can update engagement flags via MongoDB `$max` operator

## Files Modified

1. `/home/frich/devel/EmpowerSaves/octopus/src/sync/mongodb_writer.py`
   - `upsert_participant()` method (lines 64-118)
   - `upsert_participants_bulk()` method (lines 120-184)

2. `/home/frich/devel/EmpowerSaves/octopus/src/sync/emailoctopus_fetcher.py`
   - `fetch_all_participants()` method (lines 111-220)

## How to Re-sync Engagement Data

### Option 1: Re-sync All Campaigns (Recommended)

This will fetch fresh data from EmailOctopus and properly populate engagement:

```bash
cd /home/frich/devel/EmpowerSaves/octopus
python scripts/sync_campaigns.py --all
```

**Expected behavior:**
- Processes all 69 campaigns
- Fetches participants from 6 report types per campaign (sent, opened, clicked, bounced, complained, unsubscribed)
- MongoDB `$max` operator accumulates engagement flags correctly
- Exports updated CSV files with proper `opened=Yes, clicked=Yes` values

**Runtime:** ~1-2 hours for 69 campaigns (with API rate limiting delays)

### Option 2: Re-sync Specific Campaign (Testing)

Test the fix on a single campaign first:

```bash
python scripts/sync_campaigns.py --campaign <campaign-id>
```

### Option 3: Export CSV from Fixed MongoDB Data

If you don't want to re-fetch from API, just re-export CSVs from current MongoDB:

```bash
python scripts/sync_campaigns.py --export-csv
```

**Note:** This only works if MongoDB already has engagement data. Since current data is all `False`, you need Option 1 or 2.

## Verification

After re-syncing, verify engagement data is properly populated:

```bash
python -c "
from pymongo import MongoClient

client = MongoClient('localhost', 27017)
db = client['emailoctopus_db']

total = db['participants'].count_documents({})
opened = db['participants'].count_documents({'engagement.opened': True})
clicked = db['participants'].count_documents({'engagement.clicked': True})
engaged = db['participants'].count_documents({'\$or': [{'engagement.opened': True}, {'engagement.clicked': True}]})

print(f'Total participants: {total:,}')
print(f'Opened: {opened:,} ({opened/total*100:.1f}%)')
print(f'Clicked: {clicked:,} ({clicked/total*100:.1f}%)')
print(f'Engaged (opened OR clicked): {engaged:,} ({engaged/total*100:.1f}%)')
"
```

**Expected output** (after re-sync):
```
Total participants: 129,483
Opened: 15,234 (11.8%)     # Example - actual numbers depend on your campaigns
Clicked: 3,421 (2.6%)
Engaged (opened OR clicked): 16,892 (13.0%)
```

## CSV Consolidator Compatibility

The `csv_consolidator.py` script created earlier is **fully compatible** with this fix:

```bash
# Once engagement data is re-synced, use:
python csv_consolidator.py --filter engaged
```

This will correctly extract only participants with `opened=True` OR `clicked=True` from MongoDB.

## Technical Details

### MongoDB $max Operator

The `$max` operator updates a field **only if** the specified value is **greater than** the current value:

```javascript
// MongoDB boolean comparison: true > false
db.participants.update_one(
    {contact_id: "abc-123"},
    {$max: {"engagement.opened": true}}
)
```

**Behavior:**
- If `engagement.opened` is `false` → updates to `true`
- If `engagement.opened` is `true` → **stays** `true` (max of true and true is true)
- If `engagement.opened` is `true` and update value is `false` → **stays** `true` (max of true and false is true)

This ensures engagement flags are **monotonic** (once True, always True).

### Report Type Processing Order

The fetcher processes reports in this order:
1. `sent` - All recipients (engagement likely all False)
2. `opened` - Contacts who opened (sets opened=True)
3. `clicked` - Contacts who clicked (sets opened=True, clicked=True)
4. `bounced` - Bounced emails
5. `complained` - Spam complaints
6. `unsubscribed` - Unsubscribes

With the fix, a contact appearing in multiple reports will have engagement flags **accumulated** correctly.

## Rollback (If Needed)

If the fix causes issues, you can rollback:

```bash
cd /home/frich/devel/EmpowerSaves/octopus
git diff src/sync/mongodb_writer.py src/sync/emailoctopus_fetcher.py > engagement_fix.patch
git checkout src/sync/mongodb_writer.py src/sync/emailoctopus_fetcher.py
```

## Next Steps

1. **Test on single campaign** to verify fix works
2. **Re-sync all campaigns** to populate engagement data
3. **Run csv_consolidator.py** with `--filter engaged` to verify output
4. **Update CSV export processes** to use new consolidated data

## Questions?

- Check sync logs for errors: `python scripts/sync_campaigns.py --all --verbose`
- Verify MongoDB engagement data with query above
- Test CSV consolidator: `python csv_consolidator.py --filter engaged --output test_output.csv`
