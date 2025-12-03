# Text Campaign Dashboard Fix - 2025-11-05

## Issue
TEXT/SMS campaigns showing 0 in multi-channel dashboard despite campaigns existing in the database.

## Root Cause Analysis

### Investigation Steps
1. Checked `empowersaves_development_db.Campaigns` collection → Empty
2. Listed all databases and collections in MongoDB
3. Found text campaigns in **wrong location** than expected

### Root Causes Identified

1. **Wrong Database**
   - Expected: `empowersaves_development_db.campaigns`
   - Actual: `emailoctopus_db.text_campaigns`
   - Text campaigns are stored in the same database as email campaigns

2. **Wrong Collection Name**
   - Expected: `campaigns` (matching email campaigns)
   - Actual: `text_campaigns` (separate collection)

3. **Wrong Field Structure**
   - Expected fields: `campaign_type`, `statistics.sent.unique`, `statistics.delivered.unique`
   - Actual fields: `campaign_id`, `sent_count`, `delivered_count`, `responses_count`, `error_count`

4. **Wrong Applicant Database**
   - Expected: `empowersaves_development_db.applicants`
   - Actual: `empower.applicants`

## Database Structure Discovery

### emailoctopus_db Collections
- `campaigns`: 72 email campaign documents
- `participants`: 129,483 email participant documents
- **`text_campaigns`: 74 text campaign documents** ← Issue source

### empower Database
- **`applicants`: 296 applicant documents** ← Conversion tracking

### Text Campaign Document Structure
```javascript
{
  campaign_id: "COP90PK",
  text_number: 1,
  message_key: "Prequalified",
  agency: "Impact",
  sent_time: ISODate("2025-05-02T17:16:42.000Z"),
  update_time: ISODate("2025-05-04T23:00:00.000Z"),
  target_size: 505,
  sent_count: 562,
  delivered_count: 411,
  received_count: 6,
  replies_count: 2,
  responses_count: 0,
  segments_sent: 1144,
  dnd_count: 4,
  bad_number_count: 59,
  spam_count: 50,
  landline_count: 1,
  error_count: 151
}
```

## Solution Implemented

### File Modified
`app/services/campaign_data_service.py`

### Changes Made

#### 1. Database Reference Update
```python
# Before
self.empower_db = self.client['empowersaves_development_db']

# After
self.empower_db = self.client['empower']  # Correct database for applicants
```

#### 2. get_text_campaigns() Method Rewrite
```python
def get_text_campaigns(self, limit: int = 20) -> List[Dict]:
    """Get text campaigns from emailoctopus_db.text_campaigns"""
    # Changed from: self.empower_db.campaigns.find({'campaign_type': 'text'})
    # Changed to: self.email_db.text_campaigns.find({})

    campaigns = list(self.email_db.text_campaigns.find({}).sort('sent_time', -1).limit(limit))

    # Transform data to match expected structure
    for campaign in campaigns:
        campaign['name'] = f"{campaign.get('campaign_id', 'Unknown')} - {campaign.get('message_key', '')}"
        campaign['campaign_type'] = 'text'
        campaign['sent_at'] = campaign.get('sent_time')
        campaign['statistics'] = {
            'sent': {'unique': campaign.get('sent_count', 0)},
            'delivered': {'unique': campaign.get('delivered_count', 0)},
            'clicked': {'unique': campaign.get('responses_count', 0)},
            'failed': {'unique': campaign.get('error_count', 0)}
        }

    return campaigns
```

#### 3. get_text_stats() Method Rewrite
```python
def get_text_stats(self) -> Dict[str, Any]:
    """Aggregate text campaign statistics from emailoctopus_db.text_campaigns"""
    # Changed collection: self.empower_db.campaigns → self.email_db.text_campaigns
    # Changed field mapping: 'statistics.sent.unique' → 'sent_count'

    total_campaigns = self.email_db.text_campaigns.count_documents({})

    pipeline = [
        {'$group': {
            '_id': None,
            'total_sent': {'$sum': '$sent_count'},          # Was: '$statistics.sent.unique'
            'total_delivered': {'$sum': '$delivered_count'}, # Was: '$statistics.delivered.unique'
            'total_clicked': {'$sum': '$responses_count'},   # Was: '$statistics.clicked.unique'
            'total_failed': {'$sum': '$error_count'}         # Was: '$statistics.failed.unique'
        }}
    ]

    result = list(self.email_db.text_campaigns.aggregate(pipeline))
    # ... process results
```

## Test Results

### Before Fix
```
TEXT:
  total_campaigns: 0
  total_sent: 0
  total_delivered: 0
  total_clicked: 0
```

### After Fix
```
TEXT:
  total_campaigns: 74
  total_sent: 46,453
  total_delivered: 43,004
  total_clicked: 0
  total_failed: 3,449
```

### Sample Campaign Data Retrieved
```
Campaign 1:
  Name: COP90PK - Final
  Sent: 760
  Delivered: 753
  Clicked: 0

Campaign 2:
  Name: COP90PK - Final
  Sent: 471
  Delivered: 465
  Clicked: 0
```

## Impact

### Dashboard Display
- Multi-channel dashboard now correctly shows **74 TEXT/SMS campaigns**
- Text dashboard shows accurate statistics: 46,453 sent, 43,004 delivered
- Campaign list displays with proper formatting

### Data Integrity
- All 74 text campaigns are now accessible
- Statistics are accurately aggregated
- Field mapping ensures consistency with email campaign structure

## Remaining Considerations

### Mailer and Letter Campaigns
- These remain at 0 as they haven't been imported yet
- The service structure is ready when data becomes available
- Expected location: Would need clarification on actual storage location

### Data Model Consistency
- Text campaigns use different field names than email campaigns
- Transformation layer in service ensures UI consistency
- Consider standardizing field names in future data imports

### Performance
- Direct aggregation on 74 text campaigns is fast
- No indexing concerns at current data volume
- Consider indexing on `sent_time` if collection grows significantly

## Files Modified
- `app/services/campaign_data_service.py` - Fixed text campaign data access

## Testing Performed
- ✅ Text campaign count: 74 (was 0)
- ✅ Statistics aggregation: 46,453 sent, 43,004 delivered
- ✅ Campaign list retrieval: Working with proper field mapping
- ✅ Multi-channel dashboard: All stats display correctly
- ✅ Text dashboard: Campaign table renders properly
