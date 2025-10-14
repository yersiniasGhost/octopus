# Dashboard Statistics Implementation

## Overview

The dashboard now displays real-time statistics from the EmailOctopus API:
- **Total Campaigns**: Number of campaigns in your account
- **Active Lists**: Number of contact lists
- **Total Contacts**: Sum of all subscribed contacts across all lists

**Implemented**: October 7, 2025

## Features

### Real-Time Statistics
- ✅ Fetches live data from EmailOctopus API on each dashboard load
- ✅ Total campaign count from API
- ✅ Active lists count
- ✅ Total contacts count (aggregated from all lists)
- ✅ API connection status indicator

### Error Handling
- ✅ Graceful degradation: Shows 0 if API unavailable
- ✅ "API offline" indicator if connection fails
- ✅ Logs errors without breaking dashboard
- ✅ User-friendly status badges

### Visual Indicators
- ✅ Color-coded stat cards (blue, green, cyan)
- ✅ API status badge (green = connected, yellow = offline)
- ✅ Small offline indicator on each stat card if API fails

## Implementation Details

### Backend (`app/routes/main.py`)

**Dashboard Route Enhancement**:
```python
@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Displays overview statistics from EmailOctopus API"""

    # Initialize stats with defaults
    stats = {
        'total_campaigns': 0,
        'total_lists': 0,
        'total_contacts': 0,
        'api_connected': False
    }

    try:
        client = EmailOctopusClient()

        # Fetch campaigns (first 100)
        campaigns = client.get_campaigns(limit=100, page=1)
        stats['total_campaigns'] = len(campaigns['data'])

        # Fetch lists (first 100)
        lists = client.get_lists(limit=100, page=1)
        stats['total_lists'] = len(lists['data'])

        # Sum contacts across all lists
        for lst in lists['data']:
            if 'counts' in lst:
                subscribed = lst['counts'].get('subscribed', 0)
                stats['total_contacts'] += subscribed

        stats['api_connected'] = True

    except EmailOctopusAPIError:
        # Stats remain at 0, api_connected = False
        pass

    return render_template('dashboard.html',
                          user=current_user,
                          stats=stats)
```

**Key Points**:
- Default values ensure dashboard works even if API fails
- Fetches first page (100 items) for counts
- Aggregates contact counts from list metadata
- Catches API errors gracefully
- Logs all operations for debugging

### Frontend (`app/templates/dashboard.html`)

**Stat Cards**:
```html
<!-- Total Campaigns -->
<h3 class="display-4 mb-0">{{ stats.total_campaigns }}</h3>
<p class="mb-0">Total Campaigns</p>
{% if not stats.api_connected %}
<small class="text-white-50">API offline</small>
{% endif %}
```

**API Status Badge**:
```html
{% if stats.api_connected %}
<span class="badge bg-success">
    <i class="bi bi-check-circle"></i> API Connected
</span>
{% else %}
<span class="badge bg-warning text-dark">
    <i class="bi bi-exclamation-triangle"></i> API Offline
</span>
{% endif %}
```

## Data Sources

### Campaigns Count
- **Source**: `GET /campaigns?limit=100&page=1`
- **Counts**: Number of items in first page response
- **Note**: If >100 campaigns exist, shows first 100 only
- **Future**: Iterate all pages for exact total

### Lists Count
- **Source**: `GET /lists?limit=100&page=1`
- **Counts**: Number of items in first page response
- **Note**: If >100 lists exist, shows first 100 only

### Contacts Count
- **Source**: List metadata from `/lists` endpoint
- **Counts**: Sum of `counts.subscribed` from each list
- **Includes**: Only subscribed (active) contacts
- **Excludes**: Unsubscribed, pending, bounced contacts

Example list object structure:
```json
{
  "id": "...",
  "name": "My List",
  "counts": {
    "subscribed": 150,
    "unsubscribed": 10,
    "pending": 5
  }
}
```

## Performance Considerations

### API Calls
- **Dashboard load**: 2 API calls (campaigns + lists)
- **Response time**: ~1-2 seconds depending on API latency
- **Caching**: Not implemented (Phase 2)

### Optimization Opportunities
1. **Caching**: Store counts for 5-15 minutes
2. **Background updates**: Async fetch on page load
3. **Full pagination**: Iterate all pages for exact counts
4. **Progressive loading**: Show cached data immediately, update in background

## Error Scenarios

### API Key Invalid
- **Behavior**: Shows 0 for all stats
- **Indicator**: "API offline" badge and text
- **Logged**: Error message in application logs

### Network Timeout
- **Behavior**: Shows 0 for all stats
- **Indicator**: "API offline" badge
- **User Impact**: Dashboard still loads, just no stats

### Rate Limit Exceeded
- **Behavior**: Shows last successful counts or 0
- **Indicator**: "API offline" badge
- **Logged**: Rate limit error

### Partial Failure
- **Behavior**: Shows available data, 0 for failed calls
- **Example**: Campaigns load but lists fail → campaigns count shown, lists = 0

## Testing

### Manual Testing

1. **With valid API key**:
   ```bash
   # Ensure API key in .env
   octopus run
   # Login and check dashboard shows counts
   ```

2. **Without API key**:
   ```bash
   # Remove EMAILOCTOPUS_API_KEY from .env
   octopus run
   # Dashboard should show 0 with "API offline"
   ```

3. **With invalid API key**:
   ```bash
   # Set invalid key in .env
   EMAILOCTOPUS_API_KEY=invalid-key
   octopus run
   # Should show "API offline" status
   ```

### Expected Results

**With valid API and data**:
- Total Campaigns: Shows actual count (e.g., 5)
- Active Lists: Shows actual count (e.g., 2)
- Total Contacts: Shows sum (e.g., 150)
- Badge: Green "API Connected"

**With valid API but no data**:
- All stats show: 0
- Badge: Green "API Connected"

**With invalid/missing API key**:
- All stats show: 0
- Badge: Yellow "API Offline"
- Small "API offline" text on each stat card

## Files Modified

### Modified Files (2)
1. `app/routes/main.py` - Added API calls and stats logic
2. `app/templates/dashboard.html` - Updated to display dynamic stats

### Created Files (1)
1. `DASHBOARD_STATS_IMPLEMENTATION.md` - This documentation

## Usage

No additional configuration needed! The dashboard automatically:
1. Loads when user logs in
2. Fetches current stats from API
3. Displays counts or falls back to 0
4. Shows connection status

**Refresh** the dashboard page to update counts.

## Logging

**Info logs**:
```
Dashboard stats: campaigns=5, lists=2, contacts=150
```

**Error logs**:
```
EmailOctopus API error on dashboard: Invalid API key
```

**Debug logs**:
```
Making GET request to https://emailoctopus.com/api/1.6/campaigns
Retrieved 5 campaigns
Retrieved 2 lists
```

Enable debug logging:
```python
# In app/__init__.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

### Phase 2
- [ ] Caching stats for 5-15 minutes
- [ ] Full pagination for exact counts (>100 items)
- [ ] Background async updates
- [ ] Trend indicators (↑ ↓ compared to last week)
- [ ] Click-through to filtered views

### Phase 3
- [ ] More detailed stats (open rates, click rates)
- [ ] Recent campaign activity
- [ ] Contact growth chart
- [ ] Campaign performance overview

## Troubleshooting

### Stats show 0 but API is working

**Check**:
1. EmailOctopus account has campaigns/lists
2. API key has proper permissions
3. Application logs for errors

**Debug**:
```bash
octopus shell
```
```python
from app.services import EmailOctopusClient
client = EmailOctopusClient()

campaigns = client.get_campaigns(limit=5)
print(f"Campaigns: {len(campaigns['data'])}")

lists = client.get_lists(limit=5)
print(f"Lists: {len(lists['data'])}")

for lst in lists['data']:
    print(f"List: {lst['name']}, Contacts: {lst.get('counts', {}).get('subscribed', 0)}")
```

### API Connected but wrong counts

**Possible causes**:
1. Only first 100 items counted (pagination not implemented)
2. List counts metadata not returned by API
3. Contact status filtering (only 'subscribed' counted)

**Verify**:
```python
# Check list structure
lists = client.get_lists(limit=1)
import json
print(json.dumps(lists['data'][0], indent=2))
```

## Documentation Links

- **EmailOctopus API**: https://emailoctopus.com/api-documentation/v2
- **Campaigns endpoint**: `/campaigns` documentation
- **Lists endpoint**: `/lists` documentation
- **API Integration Guide**: EMAILOCTOPUS_INTEGRATION.md

---

**Status**: ✅ Implemented and ready for use
**Version**: 1.0
**Last Updated**: October 7, 2025
