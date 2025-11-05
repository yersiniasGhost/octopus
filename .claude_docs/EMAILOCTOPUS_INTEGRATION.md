# EmailOctopus API Integration

Complete guide to the EmailOctopus API integration in the Octopus application.

## Overview

The Octopus application integrates with the EmailOctopus API v1.6 to retrieve campaign, list, and contact data for analysis and reporting.

**API Documentation**: https://emailoctopus.com/api-documentation/v2

## Features Implemented

✅ **EmailOctopus API Client** (`app/services/emailoctopus_client.py`)
- Full API client with authentication and error handling
- Campaign retrieval (list and individual)
- Campaign statistics and reports
- List and contact management
- Connection testing

✅ **Campaign Routes** (`app/routes/campaigns.py`)
- Web UI routes for viewing campaigns
- RESTful API endpoints for JSON data
- Pagination support
- Error handling with user-friendly messages

✅ **Templates**
- Campaign list view with pagination
- Campaign detail view with statistics
- Error handling page with configuration help

## Configuration

### 1. API Key Setup

Get your EmailOctopus API key from: https://emailoctopus.com/api-documentation

Add to `.env` file:
```bash
EMAILOCTOPUS_API_KEY=your-api-key-here
EMAILOCTOPUS_API_BASE_URL=https://emailoctopus.com/api/1.6
```

### 2. Environment Variables

Required variables in `.env`:
```bash
# EmailOctopus API Configuration
EMAILOCTOPUS_API_KEY=your-emailoctopus-api-key-here
EMAILOCTOPUS_API_BASE_URL=https://emailoctopus.com/api/1.6
```

The API client will automatically use these environment variables via the `EnvVars` singleton.

## Usage

### Web Interface

#### View All Campaigns
```
URL: http://localhost:5000/campaigns
Method: GET
Authentication: Required (login)
```

Features:
- Displays all campaigns in a paginated table
- Shows campaign name, subject, status, sender, dates
- Click "View Details" to see individual campaign

#### View Campaign Details
```
URL: http://localhost:5000/campaigns/<campaign_id>
Method: GET
Authentication: Required (login)
```

Features:
- Campaign information (name, subject, sender, dates)
- Campaign statistics (sent, opened, clicked, bounced)
- Visual progress bars for open and click rates
- Content preview (HTML and plain text)

### API Endpoints

#### Get Campaigns (JSON)
```
URL: /api/campaigns
Method: GET
Authentication: Required
Parameters:
  - page (optional): Page number (default 1)
  - limit (optional): Items per page (default 100, max 100)

Response:
{
  "success": true,
  "data": [...],
  "paging": {...},
  "count": 10
}
```

#### Get Campaign Details (JSON)
```
URL: /api/campaigns/<campaign_id>
Method: GET
Authentication: Required

Response:
{
  "success": true,
  "data": {...},
  "reports": {...}
}
```

#### Test API Connection
```
URL: /api/test-connection
Method: GET
Authentication: Required

Response:
{
  "success": true,
  "connected": true
}
```

### Programmatic Usage

#### Basic Usage

```python
from app.services import EmailOctopusClient

# Initialize client (uses environment variables)
client = EmailOctopusClient()

# Test connection
if client.test_connection():
    print("Connected to EmailOctopus API")

# Get campaigns
campaigns = client.get_campaigns(limit=10, page=1)
for campaign in campaigns['data']:
    print(f"Campaign: {campaign['name']}")
    print(f"Status: {campaign['status']}")
    print(f"Subject: {campaign['subject']}")
```

#### Get Campaign Details

```python
# Get specific campaign
campaign_id = "00000000-0000-0000-0000-000000000000"
campaign = client.get_campaign(campaign_id)

print(f"Name: {campaign['name']}")
print(f"From: {campaign['from']['name']} <{campaign['from']['email_address']}>")
print(f"Created: {campaign['created_at']}")
```

#### Get Campaign Statistics

```python
# Get campaign reports
reports = client.get_campaign_reports(campaign_id)

print(f"Sent: {reports['sent']}")
print(f"Opened: {reports['opened']}")
print(f"Clicked: {reports['clicked']}")
print(f"Bounced: {reports['bounced']}")

# Calculate rates
if reports['sent'] > 0:
    open_rate = (reports['opened'] / reports['sent']) * 100
    click_rate = (reports['clicked'] / reports['sent']) * 100
    print(f"Open Rate: {open_rate:.1f}%")
    print(f"Click Rate: {click_rate:.1f}%")
```

#### Get Lists and Contacts

```python
# Get all lists
lists = client.get_lists(limit=100, page=1)
for lst in lists['data']:
    print(f"List: {lst['name']}")

# Get specific list
list_id = "00000000-0000-0000-0000-000000000000"
lst = client.get_list(list_id)

# Get contacts from list
contacts = client.get_contacts(list_id, limit=100, page=1)
for contact in contacts['data']:
    print(f"Email: {contact['email_address']}")
```

## Error Handling

The API client provides custom exceptions for different error scenarios:

### Exception Types

```python
from app.services.emailoctopus_client import (
    EmailOctopusAPIError,           # Base exception
    EmailOctopusAuthenticationError, # Invalid API key
    EmailOctopusRateLimitError      # Rate limit exceeded
)
```

### Example Error Handling

```python
try:
    campaigns = client.get_campaigns()
except EmailOctopusAuthenticationError:
    print("Invalid API key. Check your .env configuration.")
except EmailOctopusRateLimitError:
    print("API rate limit exceeded. Please wait before retrying.")
except EmailOctopusAPIError as e:
    print(f"API error: {str(e)}")
except Exception as e:
    print(f"Unexpected error: {str(e)}")
```

## API Client Methods

### Campaign Methods

#### `get_campaigns(limit=100, page=1)`
Retrieve list of campaigns with pagination.

**Parameters**:
- `limit`: Number of campaigns (default 100, max 100)
- `page`: Page number (default 1)

**Returns**: Dictionary with `data` (list of campaigns) and `paging` info

#### `get_campaign(campaign_id)`
Retrieve single campaign by ID.

**Parameters**:
- `campaign_id`: UUID of the campaign

**Returns**: Campaign object dictionary

#### `get_campaign_reports(campaign_id)`
Retrieve campaign statistics and reports.

**Parameters**:
- `campaign_id`: UUID of the campaign

**Returns**: Dictionary with sent, opened, clicked, bounced counts

### List Methods

#### `get_lists(limit=100, page=1)`
Retrieve list of contact lists.

**Parameters**:
- `limit`: Number of lists (default 100, max 100)
- `page`: Page number (default 1)

**Returns**: Dictionary with `data` (list of lists) and `paging` info

#### `get_list(list_id)`
Retrieve single list by ID.

**Parameters**:
- `list_id`: UUID of the list

**Returns**: List object dictionary

#### `get_contacts(list_id, limit=100, page=1)`
Retrieve contacts from a list.

**Parameters**:
- `list_id`: UUID of the list
- `limit`: Number of contacts (default 100, max 100)
- `page`: Page number (default 1)

**Returns**: Dictionary with `data` (list of contacts) and `paging` info

### Utility Methods

#### `test_connection()`
Test API connection and authentication.

**Returns**: `True` if connection successful, `False` otherwise

## API Response Examples

### Campaign Object
```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "status": "SENT",
  "name": "Campaign name",
  "subject": "Email subject",
  "from": {
    "name": "Sender name",
    "email_address": "sender@example.com"
  },
  "content": {
    "html": "<html>...",
    "plain_text": "..."
  },
  "created_at": "2024-01-01T12:00:00+00:00",
  "sent_at": "2024-01-01T13:00:00+00:00"
}
```

### Campaign Reports
```json
{
  "sent": 1000,
  "bounced": 10,
  "opened": 350,
  "clicked": 120,
  "complained": 2,
  "unsubscribed": 5
}
```

### Pagination Response
```json
{
  "data": [...],
  "paging": {
    "next": "https://emailoctopus.com/api/1.6/campaigns?api_key=...&page=2",
    "previous": null
  }
}
```

## Logging

The API client uses Python's built-in logging module.

**Configure logging** (optional):
```python
import logging

# Set log level
logging.basicConfig(level=logging.INFO)

# Get logger
logger = logging.getLogger('app.services.emailoctopus_client')
logger.setLevel(logging.DEBUG)
```

**Log messages**:
- `INFO`: API requests and responses
- `ERROR`: API errors and failures
- `DEBUG`: Detailed request information

## Testing

### Manual Testing

1. **Test API connection**:
```bash
source venv/bin/activate
octopus shell
```

```python
from app.services import EmailOctopusClient

client = EmailOctopusClient()
print(client.test_connection())
```

2. **Test campaign retrieval**:
```python
campaigns = client.get_campaigns(limit=5)
print(f"Found {len(campaigns['data'])} campaigns")
for c in campaigns['data']:
    print(f"- {c['name']} ({c['status']})")
```

### Web Interface Testing

1. Start application:
```bash
source venv/bin/activate
octopus run
```

2. Navigate to http://localhost:5000/campaigns

3. Test features:
   - Campaign list displays correctly
   - Pagination works
   - Campaign details page loads
   - Statistics display correctly
   - Error handling shows helpful messages

## Troubleshooting

### Issue: "Invalid API key or unauthorized access"

**Solution**:
1. Verify API key in `.env` is correct
2. Check API key has not expired
3. Ensure no extra spaces in `.env` file
4. Restart application after changing `.env`

### Issue: "API rate limit exceeded"

**Solution**:
1. Wait before making more requests
2. Reduce frequency of API calls
3. Implement caching (future enhancement)

### Issue: "Connection error"

**Solution**:
1. Check internet connection
2. Verify API base URL is correct
3. Check firewall settings
4. Ensure EmailOctopus API is operational

### Issue: "No campaigns displayed"

**Possible causes**:
1. No campaigns exist in EmailOctopus account
2. API authentication issue
3. API key lacks permissions

**Solution**:
1. Create test campaign in EmailOctopus
2. Verify API key permissions
3. Check browser console for errors

## Security Best Practices

1. **Never commit `.env` file**: Already in `.gitignore`
2. **Use environment variables**: API key stored in `.env`, not code
3. **Validate user input**: All route parameters validated
4. **Require authentication**: All routes protected with `@login_required`
5. **Handle errors gracefully**: No sensitive information in error messages

## Future Enhancements

Planned improvements for Phase 2:

- [ ] MongoDB storage for campaign data
- [ ] Automatic data synchronization
- [ ] Campaign data caching
- [ ] Advanced filtering and search
- [ ] Bulk campaign operations
- [ ] Contact and list management UI
- [ ] Campaign comparison features
- [ ] Export to CSV/Excel
- [ ] Scheduled report generation

## Architecture

```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Flask Routes   │  app/routes/campaigns.py
│  (campaigns_bp) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ EmailOctopus    │  app/services/emailoctopus_client.py
│     Client      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  EmailOctopus   │  https://emailoctopus.com/api/1.6
│      API        │
└─────────────────┘
```

## Files Modified/Created

### Created Files
- `app/services/__init__.py` - Services package
- `app/services/emailoctopus_client.py` - API client implementation
- `app/routes/campaigns.py` - Campaign routes (web + API)
- `app/templates/campaigns/list.html` - Campaign list view
- `app/templates/campaigns/detail.html` - Campaign detail view
- `app/templates/campaigns/error.html` - Error handling page
- `EMAILOCTOPUS_INTEGRATION.md` - This documentation

### Modified Files
- `app/__init__.py` - Registered campaigns blueprint
- `app/templates/dashboard.html` - Added campaigns link and feature status
- `.env.example` - Already contained EmailOctopus configuration

## Quick Start

1. **Configure API key**:
```bash
# Edit .env
echo "EMAILOCTOPUS_API_KEY=your-key-here" >> .env
```

2. **Start application**:
```bash
source venv/bin/activate
octopus run
```

3. **Access campaigns**:
- Login at http://localhost:5000/login
- Click "View Campaigns" on dashboard
- Or navigate to http://localhost:5000/campaigns

## Support

For issues or questions:
1. Check this documentation
2. Review EmailOctopus API documentation
3. Check application logs
4. Test API connection using `/api/test-connection`

---

**Integration completed**: October 7, 2025
**API Version**: EmailOctopus API v1.6
**Status**: ✅ Ready for use
