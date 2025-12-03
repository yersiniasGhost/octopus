# Email Dashboard Filter Fix - 2025-11-05

## Issue
Email Campaign Dashboard charts were including text, mailer, and letter campaigns in the data, not just email campaigns.

## Root Cause Analysis

### Investigation
The `emailoctopus_db.campaigns` collection contains campaigns of multiple types:
- 69 email campaigns
- 1 text campaign
- 1 mailer campaign
- 1 letter campaign
- **Total: 72 campaigns**

### Problem Locations
1. **Campaign Query** (main.py:164)
   - Used empty filter: `db.campaigns.find({})`
   - Returned ALL 72 campaigns regardless of type

2. **Zipcode Participant Aggregation** (main.py:245)
   - Queried all participants without filtering by campaign type
   - Included participants from text/mailer/letter campaigns in email dashboard analytics

### Impact
- Email dashboard charts showed inflated numbers including non-email campaign data
- Zipcode engagement data mixed email and non-email campaign participants
- Dashboard metrics were inaccurate for email-only analysis

## Solution Implemented

### File Modified
`app/routes/main.py` - Email dashboard route function

### Changes Made

#### 1. Campaign Query Filter (Line 164-167)
**Before:**
```python
campaigns = list(db.campaigns.find(
    {},  # Empty filter - returns ALL campaigns
    {'name': 1, 'campaign_id': 1, 'statistics': 1, '_id': 0}
).sort('sent_at', -1).limit(20))
```

**After:**
```python
campaigns = list(db.campaigns.find(
    {'campaign_type': 'email'},  # Filter to only email campaigns
    {'name': 1, 'campaign_id': 1, 'statistics': 1, '_id': 0}
).sort('sent_at', -1).limit(20))
```

#### 2. Zipcode Participant Filter (Line 245-262)
**Before:**
```python
zipcode_pipeline = [
    {'$match': {'fields.ZIP': {'$exists': True, '$ne': None, '$ne': ''}}},
    # ... rest of pipeline
]
```

**After:**
```python
zipcode_pipeline = [
    {'$match': {
        'campaign_id': {'$in': list(campaign_id_to_name.keys())},  # Only email campaigns
        'fields.ZIP': {'$exists': True, '$ne': None, '$ne': ''}
    }},
    # ... rest of pipeline
]
```

### How the Filter Works

1. **Campaign Type Field**: All campaigns in the collection have a `campaign_type` field
   - Email campaigns: `campaign_type: 'email'`
   - Text campaigns: `campaign_type: 'text'`
   - Mailer campaigns: `campaign_type: 'mailer'`
   - Letter campaigns: `campaign_type: 'letter'`

2. **Campaign ID Filtering**:
   - First query gets only email campaign IDs
   - Participant queries use these IDs to filter participants
   - Ensures all downstream analytics only include email campaign data

## Test Results

### Before Fix
- Campaigns returned: 72 (includes 1 text, 1 mailer, 1 letter)
- Charts showed mixed campaign type data
- Zipcode engagement included non-email participants

### After Fix
- Campaigns returned: 69 (email only)
- Charts show only email campaign data
- Zipcode engagement filtered to email campaigns only
- **3 non-email campaigns excluded** ✅

### Verification
```
BEFORE:
  Total campaigns: 72 (includes text/mailer/letter)

AFTER:
  Total email campaigns: 69 (email only)
  Non-email campaigns excluded: 3

VERIFICATION:
  Non-email campaigns in filtered results: 0
  ✅ Filter working correctly!
```

## Impact

### Email Dashboard Accuracy
- All 4 charts now show email-only data:
  1. **Sent Chart**: Email campaigns only
  2. **Engagement Chart**: Email opens/clicks only
  3. **Click-Through Rate Chart**: Email CTR only
  4. **Zipcode Chart**: Email participant engagement only

### Data Integrity
- Email dashboard metrics are now accurate for email-specific analysis
- No cross-contamination from other campaign types
- Consistent filtering across all dashboard queries

## Related Files
- `app/routes/main.py:163-167` - Campaign query with email filter
- `app/routes/main.py:245-262` - Zipcode participant filter

## Database Structure
- **Collection**: `emailoctopus_db.campaigns`
- **Filter Field**: `campaign_type`
- **Email Campaigns**: 69 documents
- **Non-Email Campaigns**: 3 documents (1 text, 1 mailer, 1 letter)

## Future Considerations

### Data Import
- New campaigns should always have `campaign_type` field set
- Email campaigns: `campaign_type: 'email'`
- Other types should be stored in appropriate collections or clearly marked

### Validation
- Consider adding index on `campaign_type` for query performance
- Validate all campaign import scripts set `campaign_type` correctly
- Monitor for campaigns without `campaign_type` field

### Consistency
- All dashboard routes should filter by campaign type
- Email dashboard: `{'campaign_type': 'email'}`
- Text dashboard: Uses separate `text_campaigns` collection
- Ensure no cross-type data pollution in analytics
