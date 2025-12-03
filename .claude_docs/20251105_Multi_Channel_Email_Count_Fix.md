# Multi-Channel Dashboard Email Count Fix - 2025-11-05

## Issue
The EMAIL card on the multi-channel dashboard was showing 72 campaigns instead of 69, including non-email campaigns in the count.

## Root Cause

The `CampaignDataService.get_email_stats()` method had the same issue as the email dashboard route - it wasn't filtering by `campaign_type: 'email'`.

### Problem Code
**File**: `app/services/campaign_data_service.py:46-61`

```python
def get_email_stats(self) -> Dict[str, Any]:
    """Aggregate email campaign statistics"""
    try:
        # Get total campaign count
        total_campaigns = self.email_db.campaigns.count_documents({})  # ❌ No filter

        # Get aggregate statistics
        pipeline = [
            # ❌ No $match stage to filter by campaign_type
            {'$group': {
                '_id': None,
                'total_sent': {'$sum': '$statistics.sent.unique'},
                'total_opened': {'$sum': '$statistics.opened.unique'},
                'total_clicked': {'$sum': '$statistics.clicked.unique'}
            }}
        ]
```

### Impact
- Multi-channel dashboard EMAIL card showed: **72 campaigns**
- Should show: **69 campaigns**
- Difference: **3 non-email campaigns** (1 text, 1 mailer, 1 letter)

## Solution

Added `campaign_type: 'email'` filter to both the count query and aggregation pipeline.

### Fixed Code
**File**: `app/services/campaign_data_service.py:46-62`

```python
def get_email_stats(self) -> Dict[str, Any]:
    """Aggregate email campaign statistics - ONLY email campaigns"""
    try:
        # Get total EMAIL campaign count (filter by campaign_type)
        total_campaigns = self.email_db.campaigns.count_documents({'campaign_type': 'email'})  # ✅ Filtered

        # Get aggregate statistics - ONLY for email campaigns
        pipeline = [
            {'$match': {'campaign_type': 'email'}},  # ✅ Filter added
            {'$group': {
                '_id': None,
                'total_sent': {'$sum': '$statistics.sent.unique'},
                'total_opened': {'$sum': '$statistics.opened.unique'},
                'total_clicked': {'$sum': '$statistics.clicked.unique'}
            }}
        ]
```

## Changes Made

### 1. Campaign Count Filter (Line 50)
**Before:**
```python
total_campaigns = self.email_db.campaigns.count_documents({})
```

**After:**
```python
total_campaigns = self.email_db.campaigns.count_documents({'campaign_type': 'email'})
```

### 2. Aggregation Pipeline Filter (Line 54)
**Before:**
```python
pipeline = [
    {'$group': {
        '_id': None,
        # ...
    }}
]
```

**After:**
```python
pipeline = [
    {'$match': {'campaign_type': 'email'}},  # New filter stage
    {'$group': {
        '_id': None,
        # ...
    }}
]
```

## Test Results

### Before Fix
```
EMAIL: 72 campaigns (includes 1 text, 1 mailer, 1 letter)
TEXT: 74 campaigns
MAILER: 0 campaigns
LETTER: 0 campaigns
```

### After Fix
```
EMAIL: 69 campaigns ✅ (email only)
TEXT: 74 campaigns ✅
MAILER: 0 campaigns ✅
LETTER: 0 campaigns ✅
```

### Verification
```
EMAIL CAMPAIGN STATS:
  total_campaigns: 69
  total_sent: 0
  total_opened: 4,974
  total_clicked: 280

✅ Email campaign count is correct: 69
```

## Related Fixes

This is part of a series of fixes to ensure campaign type filtering consistency:

1. **Email Dashboard Route** (main.py:164-167)
   - Fixed campaign query to filter by `campaign_type: 'email'`
   - Fixed zipcode participant aggregation to only include email campaigns

2. **CampaignDataService.get_email_stats()** (This fix)
   - Fixed campaign count query
   - Fixed statistics aggregation pipeline

3. **CampaignDataService.get_email_campaigns()** (Already correct)
   - Already had `campaign_type: 'email'` filter

## Impact

### Multi-Channel Dashboard
- EMAIL card now shows accurate count: **69 campaigns**
- All statistics (sent, opened, clicked) now aggregate only email campaigns
- No cross-contamination from text/mailer/letter campaigns

### Data Consistency
- All email-related queries now consistently filter by `campaign_type: 'email'`
- Dashboard displays match actual email campaign data
- Clear separation between campaign types

## Files Modified
- `app/services/campaign_data_service.py:50` - Added campaign_type filter to count
- `app/services/campaign_data_service.py:54` - Added $match stage to aggregation pipeline

## Testing
```bash
python3 -c "
from app.services.campaign_data_service import CampaignDataService
service = CampaignDataService()
stats = service.get_email_stats()
print(f\"Email campaigns: {stats['total_campaigns']}\")
"
# Output: Email campaigns: 69
```

## Future Considerations

### Consistency Validation
- All campaign queries should explicitly filter by campaign_type
- Consider adding validation tests to ensure no cross-type contamination
- Document convention: Always filter by campaign_type when querying campaigns

### Code Pattern
Standard pattern for email queries:
```python
# Count
count = db.campaigns.count_documents({'campaign_type': 'email'})

# Find
campaigns = db.campaigns.find({'campaign_type': 'email'})

# Aggregate
pipeline = [
    {'$match': {'campaign_type': 'email'}},
    # ... rest of pipeline
]
```
