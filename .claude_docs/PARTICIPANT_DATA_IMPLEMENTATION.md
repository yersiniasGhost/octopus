# Participant Data Implementation

## Overview

Campaign participant data display with full contact details from EmailOctopus API.

**Implemented**: January 2025

## Features

### Participant Table Display
- ✅ Email address, First name, Last name
- ✅ City, ZIP code, kWh usage
- ✅ Cell phone, Address
- ✅ Subscription status badges
- ✅ Pagination for large contact lists (100 per page)
- ✅ Reusable template macros for future reporting

### Data Access
- ✅ Fetches contacts from campaign's associated lists
- ✅ Handles custom fields from EmailOctopus
- ✅ Safe fallback for missing fields (displays "N/A")
- ✅ Color-coded status indicators

## Implementation Details

### Backend Components

#### 1. API Client Method (`app/services/emailoctopus_client.py`)

**New Method**: `get_campaign_contacts()`

```python
def get_campaign_contacts(
    self,
    campaign_id: str,
    limit: int = 100,
    page: int = 1
) -> Dict[str, Any]:
    """
    Retrieve contacts from a campaign's associated lists

    Args:
        campaign_id: UUID of the campaign
        limit: Number of contacts to retrieve per list (default 100, max 100)
        page: Page number for pagination

    Returns:
        Dictionary with data (list of contacts) and paging info
    """
```

**Process**:
1. Fetches campaign details to get associated list IDs
2. Retrieves contacts from campaign's list using EmailOctopus `/lists/{list_id}/contacts` endpoint
3. Returns paginated contact data with custom fields

**Future Enhancement**: Combine contacts from multiple lists when campaign has multiple recipients

#### 2. Route Handler (`app/routes/campaigns.py`)

**Updated Route**: `/campaigns/<campaign_id>`

**Additions**:
```python
# Get page number for participant pagination
page = request.args.get('page', 1, type=int)

# Fetch campaign participants (contacts)
try:
    participants_result = client.get_campaign_contacts(campaign_id, limit=100, page=page)
    participants = participants_result.get('data', [])
    participants_paging = participants_result.get('paging', {})
except EmailOctopusAPIError as e:
    participants = []
    participants_paging = {}
```

**Template Variables**:
- `participants`: List of contact dictionaries
- `participants_paging`: Pagination metadata
- `current_page`: Current page number

### Frontend Components

#### 1. Campaign Detail Template (`app/templates/campaigns/detail.html`)

**New Section**: Participant Table Card

**Features**:
- Responsive Bootstrap table with striped rows
- Badge showing participant count
- Color-coded status indicators (green=SUBSCRIBED, gray=UNSUBSCRIBED)
- Pagination controls when multiple pages exist
- Handles missing custom fields gracefully

**Template Structure**:
```jinja2
{% if participants %}
<div class="card">
    <div class="card-header">
        <h5>Campaign Participants</h5>
        <span class="badge">{{ participants|length }} contacts</span>
    </div>
    <div class="card-body">
        <table class="table table-striped">
            <!-- Participant rows -->
        </table>
        <!-- Pagination -->
    </div>
</div>
{% endif %}
```

#### 2. Reusable Macro (`app/templates/macros/participant_table.html`)

**Purpose**: Template macro for consistent participant display across future reporting features

**Macro**: `participant_table()`

**Usage**:
```jinja2
{% from 'macros/participant_table.html' import participant_table %}
{{ participant_table(participants, show_pagination=True, paging=participants_paging,
                   current_page=page, base_url=url_for('reports.some_report')) }}
```

**Benefits**:
- Consistent table structure across application
- Easy to maintain and update styling
- Reusable in reports, exports, and other views
- Built-in pagination support

**Export Placeholder**: `participant_export_buttons()` macro ready for future CSV/PDF/Excel export functionality

## Data Structure

### EmailOctopus Contact Object

```json
{
  "id": "contact-uuid",
  "email_address": "user@example.com",
  "status": "SUBSCRIBED",
  "fields": {
    "FirstName": "John",
    "LastName": "Doe",
    "City": "Columbus",
    "ZIP": "43215",
    "kWh": "12000",
    "Cell": "6145551234",
    "Address": "123 Main St"
  },
  "created_at": "2025-01-15T10:30:00+00:00",
  "tags": []
}
```

### Custom Fields

**Required Fields** (requested by user):
- `FirstName` - Contact's first name
- `LastName` - Contact's last name
- `City` - City name
- `ZIP` - Postal code
- `kWh` - Energy usage in kilowatt-hours
- `Cell` - Cell phone number
- `Address` - Street address

**Additional Fields** (available in data):
- `AnnualSavings` - Calculated annual savings
- `MonthlyCost` - Monthly energy cost
- `MonthlySaving` - Monthly savings estimate
- `DailyCost` - Daily energy cost
- `annualcost` - Annual energy cost

### Status Values

- `SUBSCRIBED` - Active subscriber (green badge)
- `UNSUBSCRIBED` - Opted out (gray badge)
- `PENDING` - Awaiting confirmation (yellow badge)
- Other statuses - Info badge (blue)

## Pagination

**Implementation**:
- Default limit: 100 contacts per page (EmailOctopus API maximum)
- Query parameter: `?page=N` for page navigation
- Previous/Next buttons with Bootstrap styling
- Disabled state when no more pages

**Example URLs**:
```
/campaigns/abc123                    # Page 1
/campaigns/abc123?page=2             # Page 2
/campaigns/abc123?page=3             # Page 3
```

**Paging Metadata**:
```json
{
  "previous": "url-to-previous-page or null",
  "next": "url-to-next-page or null"
}
```

## Error Handling

### Missing Participants
**Scenario**: Campaign has no associated lists or contacts unavailable

**Behavior**:
- Table section not displayed
- Warning logged to application logs
- No error shown to user (graceful degradation)

### Missing Custom Fields
**Scenario**: Contact missing one or more custom fields

**Behavior**:
- Display "N/A" for missing fields
- Template uses `|default('N/A', true)` filter
- No errors or broken layout

### API Errors
**Scenario**: EmailOctopus API unavailable or returns error

**Behavior**:
- Participants set to empty list
- Table section not displayed
- Error logged for debugging
- Campaign details still displayed (statistics, content)

## Future Enhancements

### Phase 2: Export Functionality
- [ ] CSV export with all participant data
- [ ] PDF report generation with formatting
- [ ] Excel export with formulas and formatting
- [ ] Filter exports by status (subscribed only, etc.)

### Phase 3: Advanced Features
- [ ] Search and filter participants in table
- [ ] Sort by column (name, city, ZIP, kWh)
- [ ] Combine contacts from multiple campaign lists
- [ ] Calculate aggregate statistics (average kWh, total contacts by city)
- [ ] Contact detail view with full history

### Phase 4: Reporting
- [ ] Custom report builder using participant macro
- [ ] Scheduled report generation
- [ ] Email report delivery
- [ ] Data visualization (charts, graphs)

## Files Modified

### Modified Files (2)
1. `app/services/emailoctopus_client.py` - Added `get_campaign_contacts()` method
2. `app/routes/campaigns.py` - Added participant data fetching to campaign detail route
3. `app/templates/campaigns/detail.html` - Added participant table section

### Created Files (2)
1. `app/templates/macros/participant_table.html` - Reusable participant table macro
2. `PARTICIPANT_DATA_IMPLEMENTATION.md` - This documentation

## Usage

### Viewing Participants

1. Navigate to campaign list: `http://localhost:5000/campaigns`
2. Click "View Details" on any campaign
3. Scroll to "Campaign Participants" section
4. Use Previous/Next buttons to navigate pages

### Using in Reports

```python
# In route handler
from app.services import EmailOctopusClient

client = EmailOctopusClient()
participants_result = client.get_campaign_contacts(campaign_id, limit=100, page=1)
participants = participants_result['data']

# In template
{% from 'macros/participant_table.html' import participant_table %}
{{ participant_table(participants) }}
```

## Testing

### Manual Testing

1. **With participants**:
   ```bash
   octopus run
   # Login and navigate to campaign with contacts
   # Verify table displays all 8 required fields
   ```

2. **Pagination**:
   ```bash
   # Navigate to campaign with >100 contacts
   # Verify Previous/Next buttons work correctly
   # Check page number updates in URL and display
   ```

3. **Missing fields**:
   ```bash
   # View campaign with contacts missing custom fields
   # Verify "N/A" displays for missing data
   # No errors or broken layout
   ```

### Expected Results

**With valid data**:
- Table displays all 8 columns (Email, First Name, Last Name, City, ZIP, kWh, Cell, Address)
- Status badge shows subscription state
- Pagination works for large lists
- Badge shows correct contact count

**With missing fields**:
- "N/A" displays for missing custom fields
- Table structure maintained
- No layout issues

**With no participants**:
- Participant section not displayed
- No errors or warnings visible to user

## API Endpoints

**No new public endpoints created**

The participant data is integrated into existing campaign detail view:
- Route: `/campaigns/<campaign_id>`
- Method: GET
- Authentication: Required (`@login_required`)

## Performance Considerations

### API Calls
- Campaign detail page: 3 API calls total
  1. Get campaign details
  2. Get campaign reports
  3. Get campaign contacts (new)

### Optimization Opportunities
1. **Caching**: Cache contact data for 5-15 minutes
2. **Lazy Loading**: Load participants on demand (separate tab or expand section)
3. **Background Fetch**: Async load participant data after page renders
4. **Data Aggregation**: Store frequently accessed participant lists in database

## Troubleshooting

### No participants showing

**Check**:
1. Campaign has associated list (check `campaign.to` field)
2. List contains contacts
3. API key has proper permissions
4. Application logs for errors

**Debug**:
```python
from app.services import EmailOctopusClient
client = EmailOctopusClient()

# Check campaign structure
campaign = client.get_campaign('campaign-id')
print(f"Lists: {campaign.get('to', [])}")

# Check contacts
if campaign.get('to'):
    list_id = campaign['to'][0]
    contacts = client.get_contacts(list_id, limit=5)
    print(f"Contact count: {len(contacts['data'])}")
```

### Fields showing "N/A"

**Possible causes**:
1. Custom fields not set in EmailOctopus list
2. Field names case-sensitive (must match exactly)
3. Contact imported without custom fields

**Verify**:
- Check EmailOctopus dashboard for list's custom fields
- Ensure field names match exactly: `FirstName`, `LastName`, `City`, `ZIP`, `kWh`, `Cell`, `Address`

### Pagination not working

**Check**:
1. URL includes `?page=N` parameter
2. EmailOctopus API returning paging metadata
3. Template receiving `participants_paging` variable

**Debug**:
```python
# Check paging structure
participants_result = client.get_campaign_contacts(campaign_id)
print(f"Paging: {participants_result.get('paging')}")
```

## Documentation Links

- **EmailOctopus API**: https://emailoctopus.com/api-documentation
- **Lists endpoint**: `/lists/{list_id}/contacts`
- **Custom fields**: EmailOctopus dashboard → Lists → Custom Fields

---

**Status**: ✅ Implemented and ready for use
**Version**: 1.0
**Last Updated**: January 2025
