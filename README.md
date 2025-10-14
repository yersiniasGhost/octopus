# EmailOctopus Campaign Dashboard

Flask-based web application for EmailOctopus campaign analytics and partner report generation.

## Features

### Phase 1 Complete ✅
- **User Authentication**: Secure login system with password hashing (Werkzeug pbkdf2:sha256)
- **Landing Page**: Professional landing page with feature highlights
- **Dashboard**: Protected dashboard for authenticated users with real-time statistics
  - Total campaigns count from EmailOctopus API
  - Active lists count
  - Total contacts across all lists
  - API connection status indicator
- **SQLite Database**: Local user management with SQLite
- **Session Management**: Flask-Login with 30-minute session timeout
- **CSRF Protection**: Flask-WTF form protection
- **EmailOctopus API Integration**: Full API client for campaign data retrieval
- **Campaign Management**: View campaigns, details, and statistics
  - Campaign list with status badges and pagination
  - Campaign details with open/click statistics
  - Content preview (HTML and plain text)
- **Participant Data Display**: View campaign participants with full contact details
  - Email address, First name, Last name
  - City, ZIP code, kWh usage
  - Cell phone, Address
  - Subscription status indicators
  - Pagination for large contact lists
  - Reusable template macros for future reporting
- **Participant Filtering**: Filter participants by engagement metrics
  - All Subscribed (active subscribers)
  - Opened (contacts who opened the email)
  - Clicked (contacts who clicked a link)
  - Bounced (delivery failures)
  - Complained (spam complaints)
  - Unsubscribed (campaign-specific unsubscribes)
  - Visual filter controls with color coding
  - Pagination preserves filter selection
- **API Error Handling**: Comprehensive error handling with user-friendly messages

### Campaign Data Sync Tool ✅
- **Standalone Sync Tool**: Download all campaign data from EmailOctopus
  - MongoDB storage with incremental sync support
  - CSV export (one file per campaign)
  - Pagination handling for large datasets
  - Engagement tracking (opened, clicked, bounced, etc.)
  - Idempotent operations (safe to run multiple times)
  - CLI interface with multiple sync modes
  - See [SYNC_TOOL.md](SYNC_TOOL.md) for complete documentation

### Phase 2 Planned 🚀
- Interactive charts and visualizations (Plotly)
- PDF report generation
- Contact and list management
- Advanced analytics
- Real-time sync via webhooks

## Project Structure

```
octopus/
├── app/                         # Flask web application
│   ├── __init__.py              # Flask app factory
│   ├── models/
│   │   └── user.py              # User model with authentication
│   ├── routes/
│   │   ├── auth.py              # Login/logout routes
│   │   ├── main.py              # Landing page and dashboard
│   │   └── campaigns.py         # Campaign routes
│   ├── services/
│   │   └── emailoctopus_client.py  # EmailOctopus API client
│   ├── forms/
│   │   └── auth_forms.py        # Login form with CSRF
│   ├── templates/
│   │   ├── base.html            # Base template
│   │   ├── index.html           # Landing page
│   │   ├── login.html           # Login page
│   │   ├── dashboard.html       # Dashboard page
│   │   ├── campaigns/           # Campaign templates
│   │   │   ├── list.html        # Campaign list view
│   │   │   └── detail.html      # Campaign details
│   │   └── macros/              # Reusable template components
│   │       └── participant_table.html  # Participant table macro
│   └── static/
│       └── css/
│           └── style.css        # Custom styles
├── src/                         # Sync tool and utilities
│   ├── models/                  # Pydantic data models
│   │   ├── campaign.py          # Campaign model
│   │   └── participant.py       # Participant model
│   ├── tools/                   # Utilities
│   │   └── mongo.py             # MongoDB singleton
│   ├── sync/                    # Data sync logic
│   │   ├── emailoctopus_fetcher.py  # API fetching
│   │   ├── mongodb_writer.py    # MongoDB operations
│   │   ├── csv_writer.py        # CSV export
│   │   └── campaign_sync.py     # Main orchestrator
│   └── utils/                   # Helper utilities
│       ├── envvars.py           # Environment variables
│       ├── singleton.py         # Singleton metaclass
│       └── pyobject_id.py       # MongoDB ObjectId support
├── scripts/
│   ├── create_user.py           # User creation script
│   ├── test_emailoctopus.py     # API integration test
│   └── sync_campaigns.py        # Campaign sync CLI ⭐ NEW
├── data/
│   └── exports/                 # CSV export output
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
├── requirements.txt             # Python dependencies
├── run.py                       # Flask app entry point
├── README.md                    # This file
├── SYNC_TOOL.md                 # Sync tool documentation ⭐ NEW
├── EMAILOCTOPUS_INTEGRATION.md  # API integration docs
├── PARTICIPANT_DATA_IMPLEMENTATION.md  # Participant data docs
└── PARTICIPANT_FILTERING_IMPLEMENTATION.md  # Filtering docs
```

## Installation

### Quick Install (Recommended)

```bash
# Install as editable package
pip install -e .

# Or install with all features
pip install -e ".[dev,mongodb,reporting]"
```

**After installation, you get:**
- `octopus` - Main CLI command
- `octopus-create-user` - User management
- Full package functionality

See [PACKAGE_INSTALL.md](PACKAGE_INSTALL.md) for detailed installation options.

## Setup Instructions

### 1. Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### 2. Installation

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and set your SECRET_KEY
# Generate a secure secret key with:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Required environment variables in `.env`:
- `SECRET_KEY`: Flask secret key (generate a secure random string)
- `DATABASE_URI`: SQLite database path (default: `sqlite:///octopus.db`)
- `FLASK_ENV`: Environment mode (`development` or `production`)
- `EMAILOCTOPUS_API_KEY`: Your EmailOctopus API key
- `MONGODB_HOST`: MongoDB host (default: localhost)
- `MONGODB_PORT`: MongoDB port (default: 27017)
- `MONGODB_DATABASE`: MongoDB database name (required for sync tool)

### 4. Initialize Database

```bash
# If installed as package
octopus init-db

# Or automatically on first run
python3 run.py  # Creates database automatically
```

### 5. Create Users

```bash
# If installed as package
octopus-create-user

# Or directly
python3 scripts/create_user.py

# Follow the prompts to create user accounts
```

### 6. Run Application

**If installed as package:**
```bash
octopus run

# Custom host/port
octopus run --host 0.0.0.0 --port 8000
```

**Or run directly:**
```bash
python3 run.py
```

The application will be available at: **http://localhost:5000**

## Usage

### Accessing the Application

1. **Landing Page**: Navigate to `http://localhost:5000/`
   - Public page showcasing features
   - "Get Started" button redirects to login

2. **Login**: Navigate to `http://localhost:5000/login`
   - Enter username and password
   - Optional "Remember Me" checkbox
   - Redirects to dashboard on successful login

3. **Dashboard**: `http://localhost:5000/dashboard` (requires authentication)
   - Shows user information
   - Displays placeholder stats (EmailOctopus integration coming in Phase 2)

4. **Logout**: Click username dropdown → Logout

### Creating Users

Run the interactive user creation script:

```bash
python3 scripts/create_user.py
```

Options:
1. Create new user (interactive prompts)
2. List all users
3. Exit

## Campaign Data Sync Tool

The standalone sync tool downloads all campaign data from EmailOctopus and stores it in MongoDB with CSV exports.

### Quick Start

```bash
# Sync all campaigns
python scripts/sync_campaigns.py --all

# Incremental sync (only campaigns older than 24h)
python scripts/sync_campaigns.py --incremental

# Sync specific campaign
python scripts/sync_campaigns.py --campaign abc-123-def

# Export MongoDB data to CSV
python scripts/sync_campaigns.py --export-csv

# Show statistics
python scripts/sync_campaigns.py --stats
```

### Features

- ✅ Downloads all campaign data with pagination support
- ✅ Stores in MongoDB with normalized schema (campaigns + participants collections)
- ✅ Exports one CSV file per campaign to `data/exports/`
- ✅ Tracks engagement (opened, clicked, bounced, complained, unsubscribed)
- ✅ Incremental sync (only updates changed data)
- ✅ Idempotent operations (safe to run multiple times)

**Complete documentation:** [SYNC_TOOL.md](SYNC_TOOL.md)

### MongoDB Schema

**campaigns** collection:
- Campaign metadata (name, subject, from, dates, status)
- Statistics (sent, opened, clicked, bounced, complained, unsubscribed)
- Unique index on `campaign_id`

**participants** collection:
- Contact information (email, name, city, ZIP, etc.)
- Custom fields (kWh, cell, address, energy costs)
- Engagement tracking (opened, clicked, etc.)
- Compound unique index on `{campaign_id, contact_id}`

### Scheduling with Cron

```bash
# Daily incremental sync at 2 AM
0 2 * * * cd /path/to/octopus && python scripts/sync_campaigns.py --incremental >> logs/sync.log 2>&1

# Weekly full sync on Sunday at 3 AM
0 3 * * 0 cd /path/to/octopus && python scripts/sync_campaigns.py --all >> logs/sync.log 2>&1
```

### Security Features

- **Password Hashing**: Werkzeug pbkdf2:sha256
- **Session Management**: 30-minute timeout
- **CSRF Protection**: Flask-WTF tokens on all forms
- **Login Required**: All protected routes use `@login_required` decorator
- **Secure Cookies**: Flask session with SECRET_KEY

## Development

### Project Phases

**Phase 1 (Current)**: ✅ Authentication & Landing Page
- User login system with secure password hashing
- Landing page with feature highlights
- Dashboard skeleton

**Phase 2 (Next)**: EmailOctopus Integration
- API client for EmailOctopus
- Campaign data extraction
- MongoDB integration
- Data synchronization

**Phase 3 (Future)**: Analytics & Reporting
- Interactive charts and visualizations
- PDF report generation
- Advanced filtering and search

### Tech Stack

- **Backend**: Flask 3.0.0
- **Database**: SQLite (users), MongoDB (campaigns - Phase 2)
- **Authentication**: Flask-Login + Werkzeug password hashing
- **Forms**: Flask-WTF with CSRF protection
- **Frontend**: Bootstrap 5 + Jinja2 templates
- **Data Processing**: NumPy (Phase 2)

## Troubleshooting

### Database Issues

If you encounter database errors:

```bash
# Remove existing database
rm octopus.db

# Run application to recreate
python3 run.py
```

### Import Errors

Make sure virtual environment is activated and dependencies are installed:

```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Environment Variable Issues

Ensure `.env` file exists and contains required variables:

```bash
# Check .env file
cat .env

# Should contain at minimum:
# SECRET_KEY=your-secret-key-here
# FLASK_ENV=development
```

## EmailOctopus Integration

### Quick Start

1. **Get API Key**: https://emailoctopus.com/api-documentation
2. **Configure**: Add `EMAILOCTOPUS_API_KEY=your-key` to `.env`
3. **Test**: Run `python3 scripts/test_emailoctopus.py`
4. **Use**: Navigate to http://localhost:5000/campaigns

### Features

- ✅ View all campaigns with pagination
- ✅ Campaign details with statistics
- ✅ Open and click rate visualization
- ✅ Content preview (HTML and plain text)
- ✅ Error handling with helpful messages
- ✅ API endpoints for JSON data

### Documentation

- **EMAILOCTOPUS_INTEGRATION.md** - Complete API integration guide
- **API_IMPLEMENTATION_SUMMARY.md** - Quick implementation reference
- **Test Script**: `scripts/test_emailoctopus.py`

### API Endpoints

Web routes:
- `/campaigns` - Campaign list
- `/campaigns/<id>` - Campaign details

API routes (JSON):
- `/api/campaigns` - Get campaigns
- `/api/campaigns/<id>` - Get campaign details
- `/api/test-connection` - Test API

## Contributing

This is an internal application. Contact the development team for contribution guidelines.

## License

Internal use only - EmpowerSaves

## Support

For issues or questions, contact the development team.

## Documentation

- **README.md** - Main documentation (this file)
- **GETTING_STARTED.md** - Complete getting started guide
- **QUICK_REFERENCE.md** - Quick command reference
- **EMAILOCTOPUS_INTEGRATION.md** - EmailOctopus API integration
- **API_IMPLEMENTATION_SUMMARY.md** - Implementation summary
- **DASHBOARD_STATS_IMPLEMENTATION.md** - Dashboard statistics feature
- **PARTICIPANT_DATA_IMPLEMENTATION.md** - Participant data display feature
- **PARTICIPANT_FILTERING_IMPLEMENTATION.md** - Participant filtering feature
- **PACKAGE_INSTALL.md** - Package installation guide
- **INSTALLATION_SUCCESS.md** - Installation verification
