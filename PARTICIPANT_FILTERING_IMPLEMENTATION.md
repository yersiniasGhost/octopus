# Participant Filtering Implementation

## Overview

Advanced filtering system for campaign participants based on email engagement metrics.

**Implemented**: January 2025

## Features

### Filter Types
- ✅ **All Subscribed**: All active subscribers in campaign list
- ✅ **Opened**: Contacts who opened the email
- ✅ **Clicked**: Contacts who clicked a link in the email
- ✅ **Bounced**: Contacts whose emails bounced
- ✅ **Complained**: Contacts who marked email as spam
- ✅ **Unsubscribed**: Contacts who unsubscribed from campaign

### UI Components
- ✅ Visual filter button group with icons
- ✅ Active filter highlighting
- ✅ Filter description text
- ✅ Color-coded filter buttons
- ✅ Pagination preserves filter selection
- ✅ Reusable filter component in macro

## Implementation Details

### Backend Components

#### 1. API Client Method (`app/services/emailoctopus_client.py:218-251`)

**New Method**: `get_campaign_report_contacts()`

```python
def get_campaign_report_contacts(
    self,
    campaign_id: str,
    report_type: str,
    limit: int = 100,
    page: int = 1
) -> Dict[str, Any]:
    """
    Retrieve contacts from a specific campaign report

    Args:
        campaign_id: UUID of the campaign
        report_type: Type of report (sent, opened, clicked, bounced, complained, unsubscribed)
        limit: Number of contacts to retrieve (default 100, max 100)
        page: Page number for pagination

    Returns:
        Dictionary with data (list of contacts with engagement info) and paging info
    """
```

**API Endpoints**:
- `/campaigns/{id}/reports/sent` - All sent contacts
- `/campaigns/{id}/reports/opened` - Contacts who opened
- `/campaigns/{id}/reports/clicked` - Contacts who clicked
- `/campaigns/{id}/reports/bounced` - Bounced emails
- `/campaigns/{id}/reports/complained` - Spam complaints
- `/campaigns/{id}/reports/unsubscribed` - Unsubscribed contacts

**Response Structure**:
```json
{
  "data": [
    {
      "contact": {
        "id": "contact-uuid",
        "email_address": "user@example.com",
        "fields": {
          "FirstName": "John",
          "LastName": "Doe",
          ...
        }
      }
    }
  ],
  "paging": {
    "previous": "url or null",
    "next": "url or null"
  }
}
```

#### 2. Route Handler (`app/routes/campaigns.py:88-154`)

**Filter Logic**:

```python
# Get filter parameter from URL
filter_type = request.args.get('filter', 'all', type=str)

if filter_type == 'all' or filter_type == 'subscribed':
    # Fetch from campaign list, filter by SUBSCRIBED status
    participants_result = client.get_campaign_contacts(campaign_id, limit=100, page=page)
    participants_raw = participants_result.get('data', [])
    participants = [p for p in participants_raw if p.get('status') == 'SUBSCRIBED']

elif filter_type in ['opened', 'clicked', 'bounced', 'complained', 'unsubscribed']:
    # Fetch from specific campaign report endpoint
    participants_result = client.get_campaign_report_contacts(
        campaign_id, filter_type, limit=100, page=page
    )
    # Extract contact data from report structure
    participants = [item.get('contact', {}) for item in participants_result.get('data', [])]
```

**URL Parameters**:
- `?filter=all` - All subscribed contacts (default)
- `?filter=opened` - Contacts who opened
- `?filter=clicked` - Contacts who clicked
- `?filter=bounced` - Bounced emails
- `?filter=complained` - Spam complaints
- `?filter=unsubscribed` - Unsubscribed contacts
- `?page=N` - Page number (combines with filter)

**Example URLs**:
```
/campaigns/abc123?filter=opened
/campaigns/abc123?filter=clicked&page=2
/campaigns/abc123?filter=bounced
```

### Frontend Components

#### 1. Filter Controls (`app/templates/campaigns/detail.html:255-298`)

**Button Group**:
```html
<div class="btn-group" role="group">
    <a href="?filter=all" class="btn btn-sm btn-primary">
        <i class="bi bi-people"></i> All Subscribed
    </a>
    <a href="?filter=opened" class="btn btn-sm btn-success">
        <i class="bi bi-envelope-open"></i> Opened
    </a>
    <!-- More filter buttons -->
</div>
```

**Visual Design**:
- Primary (blue): All Subscribed
- Success (green): Opened
- Info (cyan): Clicked
- Warning (yellow): Bounced
- Danger (red): Complained
- Secondary (gray): Unsubscribed

**Active State**:
- Active filter has solid color: `btn-primary`
- Inactive filters have outline: `btn-outline-primary`

**Filter Description**:
```html
<small class="text-muted">
    {% if filter_type == 'opened' %}
    Showing contacts who opened this email
    {% endif %}
</small>
```

#### 2. Updated Pagination (`app/templates/campaigns/detail.html:346-373`)

**Preserves Filter**:
```html
<a href="{{ url_for('campaigns.campaign_detail',
                    campaign_id=campaign.id,
                    page=current_page+1,
                    filter=filter_type) }}">
    Next
</a>
```

**Behavior**:
- Clicking Next/Previous maintains current filter
- Page number resets to 1 when changing filters
- Pagination only shows when results exist

#### 3. Reusable Macro (`app/templates/macros/participant_table.html:1-67`)

**Enhanced Macro**:
```jinja2
{% macro participant_table(
    participants,
    show_filters=True,
    filter_type='all',
    campaign_id=None
) %}
```

**Usage in Future Reports**:
```jinja2
{% from 'macros/participant_table.html' import participant_table %}
{{ participant_table(
    participants,
    show_filters=True,
    filter_type=filter_type,
    campaign_id=campaign.id
) }}
```

## Filter Behavior

### All Subscribed (Default)
**Data Source**: Campaign's contact list (`/lists/{id}/contacts`)

**Filter Logic**:
- Fetches all contacts from campaign list
- Filters client-side for `status == 'SUBSCRIBED'`
- Excludes UNSUBSCRIBED, PENDING, BOUNCED contacts

**Use Case**: See all current active subscribers

### Opened
**Data Source**: Campaign report (`/campaigns/{id}/reports/opened`)

**Returns**: Contacts who opened the email at least once

**Notes**:
- Includes multiple opens from same contact
- Shows all contacts who engaged with email

### Clicked
**Data Source**: Campaign report (`/campaigns/{id}/reports/clicked`)

**Returns**: Contacts who clicked any link in the email

**Notes**:
- Includes multiple clicks from same contact
- Indicates high engagement level

### Bounced
**Data Source**: Campaign report (`/campaigns/{id}/reports/bounced`)

**Returns**: Contacts whose emails bounced

**Use Case**:
- Identify invalid email addresses
- Clean up email list
- Investigate delivery issues

### Complained
**Data Source**: Campaign report (`/campaigns/{id}/reports/complained`)

**Returns**: Contacts who marked email as spam

**Use Case**:
- Identify unhappy subscribers
- Review email content/frequency
- Compliance monitoring

### Unsubscribed
**Data Source**: Campaign report (`/campaigns/{id}/reports/unsubscribed`)

**Returns**: Contacts who unsubscribed from this campaign

**Use Case**:
- Track campaign-specific unsubscribes
- Analyze content that caused unsubscribes

## Data Structure Differences

### List Contacts (All Subscribed)
```json
{
  "data": [
    {
      "id": "contact-uuid",
      "email_address": "user@example.com",
      "status": "SUBSCRIBED",
      "fields": { ... }
    }
  ]
}
```

### Report Contacts (Opened, Clicked, etc.)
```json
{
  "data": [
    {
      "contact": {
        "id": "contact-uuid",
        "email_address": "user@example.com",
        "fields": { ... }
      }
    }
  ]
}
```

**Note**: Report endpoints wrap contacts in a `contact` object. The route handler extracts this automatically.

## Error Handling

### No Results for Filter
**Scenario**: Filter has no matching contacts (e.g., no one complained)

**Behavior**:
```html
<div class="alert alert-info">
    No participants found for this filter.
</div>
```

**User Experience**: Clear message, filter buttons remain visible

### Invalid Filter Type
**Scenario**: URL has invalid filter parameter

**Behavior**:
- Defaults to 'all' filter
- Logs warning
- Displays all subscribed contacts

### API Error
**Scenario**: EmailOctopus API unavailable

**Behavior**:
- Empty participant list
- Warning logged
- No filter results shown

## Performance Considerations

### API Calls per Page Load
- Base: 2 calls (campaign details + reports)
- With participants: +1 call (filtered contacts)
- **Total**: 3 API calls per page

### Caching Opportunities
1. **Campaign details**: Cache for 15 minutes
2. **Report statistics**: Cache for 5 minutes
3. **Participant lists**: Cache for 2-5 minutes per filter
4. **Pagination**: Cache individual pages

### Filter Performance
- **All Subscribed**: Client-side filtering on 100 contacts (fast)
- **Report Filters**: Direct API endpoint (optimized by EmailOctopus)

## Future Enhancements

### Phase 2: Advanced Filtering
- [ ] Combine filters (opened AND clicked)
- [ ] Date range filtering (opened last 7 days)
- [ ] Custom field filtering (City = "Columbus")
- [ ] Search by name/email within filter

### Phase 3: Analytics
- [ ] Filter conversion metrics (opened → clicked rate)
- [ ] Filter comparison charts
- [ ] Time-based filter analysis (when did they open?)
- [ ] Export filtered results to CSV/PDF

### Phase 4: Automation
- [ ] Create segments from filters
- [ ] Automated follow-up campaigns to filtered groups
- [ ] A/B test different filter groups

## Usage Examples

### View All Engaged Contacts
```
1. Navigate to campaign details
2. Click "Opened" filter
3. See all contacts who opened the email
4. Click "Clicked" to see who took action
```

### Identify Problem Emails
```
1. Click "Bounced" filter
2. Review invalid email addresses
3. Click "Complained" filter
4. Identify spam complaints
5. Review email content for issues
```

### Measure Campaign Success
```
1. Start with "All Subscribed" (total audience)
2. Check "Opened" (interest level)
3. Check "Clicked" (engagement level)
4. Compare counts for conversion rate
```

### Clean Email List
```
1. Click "Bounced" filter
2. Export list (future feature)
3. Remove or update invalid emails
4. Click "Unsubscribed" filter
5. Respect unsubscribe preferences
```

## Testing

### Manual Testing

**Test All Filters**:
```bash
octopus run
# Login and navigate to campaign
# Click each filter button
# Verify correct data displays
# Check pagination works with filters
```

**Test Edge Cases**:
1. Campaign with no opens → Opened filter shows "No participants"
2. Campaign with no bounces → Bounced filter shows "No participants"
3. Large filtered list (>100) → Pagination works correctly

### Expected Results

**Filter: All Subscribed**
- Shows all SUBSCRIBED contacts from list
- Excludes UNSUBSCRIBED, PENDING
- Default view on page load

**Filter: Opened**
- Shows only contacts who opened email
- Count matches "opened unique" from statistics
- May be less than total sent

**Filter: Clicked**
- Shows only contacts who clicked links
- Count matches "clicked unique" from statistics
- Typically less than opened count

**Filter: Bounced**
- Shows contacts with delivery failures
- Useful for list cleanup
- May be empty for healthy lists

**Filter: Complained**
- Shows spam complaint contacts
- Should be very low count
- Important for compliance

**Filter: Unsubscribed**
- Shows campaign-specific unsubscribes
- May differ from global unsubscribe list

## Files Modified

### Modified Files (3)
1. `app/services/emailoctopus_client.py` - Added `get_campaign_report_contacts()` method
2. `app/routes/campaigns.py` - Added filter logic to campaign detail route
3. `app/templates/campaigns/detail.html` - Added filter UI controls

### Enhanced Files (1)
1. `app/templates/macros/participant_table.html` - Added filter support to reusable macro

### Created Files (1)
1. `PARTICIPANT_FILTERING_IMPLEMENTATION.md` - This documentation

## Troubleshooting

### Filter shows no results but statistics show data

**Possible Cause**: API pagination limit

**Check**:
```python
# In Python shell
from app.services import EmailOctopusClient
client = EmailOctopusClient()
result = client.get_campaign_report_contacts('campaign-id', 'opened', limit=100)
print(f"Found {len(result['data'])} opened contacts")
print(f"Paging: {result.get('paging')}")
```

**Solution**: Results may be on subsequent pages, use pagination

### Filter button not highlighting

**Check**:
1. URL contains correct `?filter=type` parameter
2. Template receives `filter_type` variable
3. Filter type matches exactly (lowercase)

### Pagination loses filter

**Check**: Pagination links include `filter=filter_type` parameter

**Fix**: Ensure all pagination URLs preserve filter:
```jinja2
url_for('campaigns.campaign_detail',
        campaign_id=campaign.id,
        page=N,
        filter=filter_type)
```

## Documentation Links

- **EmailOctopus API**: https://emailoctopus.com/api-documentation
- **Campaign Reports**: `/campaigns/{id}/reports/{type}`
- **Participant Data**: See `PARTICIPANT_DATA_IMPLEMENTATION.md`

---

**Status**: ✅ Implemented and ready for use
**Version**: 1.0
**Last Updated**: January 2025
