# Text Campaign Name Fix - 2025-11-05

## Issue
The "Recent Text Campaigns" table in the Text Campaign Dashboard showed incorrect campaign names. Names displayed only the campaign_id and message_key, but should include the organization (agency) and message type.

## Root Cause

The `get_text_campaigns()` method was constructing campaign names using `campaign_id` instead of `agency`.

### Problem Code
**File**: `app/services/campaign_data_service.py:94-96`

```python
# Map campaign_id to name if name doesn't exist
if 'name' not in campaign:
    campaign['name'] = f"{campaign.get('campaign_id', 'Unknown')} - {campaign.get('message_key', '')}"
```

**Result**: Names like `"COP90PK - Prequalified"` (campaign ID - message)

### Expected Format
Names should use `agency` (organization) and `message_key` (message type):
- `"Impact - Prequalified"`
- `"OHCAC - Money"`
- `"Day - Final"`

## Text Campaign Data Structure

### Available Fields
```python
{
  'campaign_id': 'COP90PK',         # Campaign identifier (not descriptive)
  'agency': 'Impact',               # Organization name ✅
  'message_key': 'Prequalified',    # Message type ✅
  'text_number': 1,
  'sent_count': 562,
  'delivered_count': 411,
  # ... other fields
}
```

### Name Construction
- **Before**: `campaign_id - message_key` → `"COP90PK - Prequalified"`
- **After**: `agency - message_key` → `"Impact - Prequalified"`

## Solution

Changed the name construction to use `agency` and `message_key` instead of `campaign_id`.

### Fixed Code
**File**: `app/services/campaign_data_service.py:94-98`

```python
# Map agency and message_key to name if name doesn't exist
if 'name' not in campaign:
    agency = campaign.get('agency', 'Unknown')
    message_key = campaign.get('message_key', 'Unknown')
    campaign['name'] = f"{agency} - {message_key}"
```

## Test Results

### Before Fix
```
Campaign Names:
  1. COP90PK - Prequalified
  2. COP90PK - Money
  3. COP90PK - Struggling
```

### After Fix
```
Campaign Names:
  1. Day - Final            (Sent: 760, Delivered: 753)
  2. Day - Final            (Sent: 471, Delivered: 465)
  3. Running - Time         (Sent: 432, Delivered: 419)
  4. Running - Time         (Sent: 386, Delivered: 380)
```

### Verification
```
✅ All campaign names follow "Agency - Message_Key" format

Expected format examples:
  - Impact - Prequalified
  - OHCAC - Money
  - Impact - Struggling
  - Day - Final
  - Running - Time
```

## Impact

### Text Campaign Dashboard
- **Table Column**: "Campaign Name" now displays meaningful organization and message information
- **User Experience**: Users can now identify which organization and message type at a glance
- **Clarity**: "Impact - Prequalified" is more descriptive than "COP90PK - Prequalified"

### Data Meaning
- **Agency**: Organization running the campaign (Impact, OHCAC, Day, Running, etc.)
- **Message_Key**: Type/category of message (Prequalified, Money, Struggling, Final, Time, etc.)

## Related Information

### Campaign Name Pattern
All text campaigns follow this pattern:
```
{organization} - {message_type}
```

### Example Organizations (Agencies)
- Impact
- OHCAC
- Day
- Running

### Example Message Types (Message Keys)
- Prequalified
- Money
- Struggling
- Final
- Time

## Files Modified
- `app/services/campaign_data_service.py:94-98` - Changed name construction from campaign_id to agency

## Code Location
The fix is in the `get_text_campaigns()` method which is called by:
- Text dashboard route: `app/routes/main.py:297`
- Template: `app/templates/dashboards/text.html` (displays campaign names in table)

## Testing
```bash
python3 -c "
from app.services.campaign_data_service import CampaignDataService
service = CampaignDataService()
campaigns = service.get_text_campaigns(limit=5)
for c in campaigns:
    print(f\"{c['name']}\")
"
# Output:
# Day - Final
# Day - Final
# Running - Time
# Running - Time
# Running - Time
```

## Future Considerations

### Name Uniqueness
- Multiple campaigns may have the same agency-message combination
- Consider adding text_number or date to make names unique if needed
- Current format is descriptive and meets display requirements

### Additional Context
If more detail is needed in the future, could enhance to:
```python
campaign['name'] = f"{agency} - {message_key} #{text_number}"
# Example: "Impact - Prequalified #1"
```

Or include campaign_id:
```python
campaign['name'] = f"{agency} - {message_key} ({campaign_id})"
# Example: "Impact - Prequalified (COP90PK)"
```
