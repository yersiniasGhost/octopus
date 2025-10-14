# EmailOctopus Campaign Dashboard - Project Specification

## Executive Summary

**Project Name**: EmailOctopus Campaign Analytics & Reporting Dashboard
**Technology Stack**: Python 3.x + Flask + MongoDB + EmailOctopus API v2
**Primary Goal**: Simplify partner campaign report generation through automated data extraction and visualization
**Users**: 2 internal super users
**Deployment**: Local development → Manual AWS deployment

---

## Problem Statement

**Current Pain Point**: Generating campaign reports for partners is onerous and time-consuming
**Solution**: Automated Flask web application that extracts EmailOctopus campaign data and generates comprehensive reports with visualizations

---

## Core Requirements

### 1. Functional Requirements

#### MVP Scope (Phase 1)
- ✅ **User Authentication**: Login system for 2 super users with session management
- ✅ **API Integration**: Connect to EmailOctopus API v2 using single API key
- ✅ **Data Extraction**: Pull all campaign data (opens, clicks, bounces, unsubscribes, conversions)
- ✅ **MongoDB Storage**: Store EmailOctopus data in dedicated MongoDB collections with append-only strategy
- ✅ **Data Display**: Present campaign metrics in tables and charts
- ✅ **Dashboard**: Single-page overview of all campaigns with key metrics (login required)
- ✅ **Historical Data**: Focus on historical campaign performance analysis

#### Core Features (Phase 1)
- **User Authentication & Authorization**
  - Login page with username/password
  - Session-based authentication (Flask-Login)
  - Password hashing with Werkzeug
  - Login required decorator for all routes
  - Logout functionality
  - Optional: "Remember me" feature

- **Campaign Management**
  - List all campaigns with status and basic metrics
  - View detailed campaign reports (contact status, link performance)
  - Filter campaigns by date range, status, or custom criteria

- **List Management**
  - Display all subscriber lists
  - Show list growth and engagement metrics
  - View list field configurations

- **Contact Data**
  - View contact lists with segmentation
  - Display contact engagement history
  - Filter by tags, status, creation date

- **Visualization**
  - Dashboard with aggregate metrics (total campaigns, avg open rate, click rate)
  - Campaign performance charts (time series, comparison bars)
  - List growth visualizations
  - Engagement heatmaps

- **Report Generation**
  - Custom report builder for partner-specific data
  - Export reports to PDF format
  - Predefined report templates (campaign summary, list performance, engagement analysis)

#### Future Scope (Phase 2+)
- 🔮 **Data Linking**: Connect EmailOctopus contacts to existing customer records (energy + demographics)
- 🔮 **Campaign-Project Association**: Link campaigns to energy consumption analysis projects
- 🔮 **Cross-Domain Analytics**: Campaign effectiveness by energy usage segments, demographic targeting analysis
- 🔮 Real-time data sync and monitoring
- 🔮 Advanced analytics (cohort analysis, predictive modeling)
- 🔮 Automated report scheduling and delivery
- 🔮 Custom dashboard widgets and layouts

### 2. Technical Requirements

#### Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                    Flask Web Application                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Routes     │  │  Services    │  │   Models     │          │
│  │  (Views)     │  │  (Business)  │  │  (MongoDB)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│              EmailOctopus API Client Layer                      │
│           (Rate limiting, pagination, error handling)           │
├─────────────────────────────────────────────────────────────────┤
│                        MongoDB Database                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  EmailOctopus Collections:                               │  │
│  │  - campaigns (append-only with metrics history)          │  │
│  │  - lists (subscriber list data)                          │  │
│  │  - contacts (contact records with engagement)            │  │
│  │  - campaign_metrics_snapshots (time-series metrics)      │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  Existing Collections (Future Phase 2):                  │  │
│  │  - customers (energy + demographic data)                 │  │
│  │  - energy_analyses (consumption projects)                │  │
│  │  - [other existing collections from your system]         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↕
                  EmailOctopus API v2 (REST)
```

#### Technology Stack
- **Backend**: Python 3.9+ with Flask 3.x
- **Database**: MongoDB 6.x (local for dev, Atlas or self-hosted for production)
- **ODM**: PyMongo or MongoEngine for MongoDB integration
- **API Client**: `requests` library for HTTP calls
- **Data Processing**: `numpy` for high-performance numerical operations (avoiding pandas for speed)
- **Visualization**: `plotly` or `Chart.js` for interactive charts
- **PDF Generation**: `ReportLab` or `WeasyPrint` for PDF exports
- **Frontend**: Jinja2 templates + Bootstrap 5 for responsive UI
- **Authentication**: Flask-Login + Werkzeug for password hashing, session-based auth (2 super users)

#### MongoDB Collections & Data Models

**Phase 1: EmailOctopus Data (New Collections)**

```python
# Collection: users
{
    "_id": ObjectId,
    "username": str,  # Unique username
    "email": str,  # Email address
    "password_hash": str,  # Werkzeug hashed password
    "full_name": str,
    "role": str,  # "super_user" for both users
    "is_active": bool,
    "last_login": datetime,
    "created_at": datetime,
    "created_by": str  # Admin who created the account
}

# Collection: campaigns
{
    "_id": ObjectId,
    "emailoctopus_id": str,  # Original EmailOctopus campaign ID
    "name": str,
    "subject": str,
    "status": str,  # draft, sending, sent
    "created_at": datetime,
    "sent_at": datetime,
    "from_name": str,
    "from_email": str,
    "list_id": str,
    "current_metrics": {
        "sent": int,
        "opened": int,
        "clicked": int,
        "bounced": int,
        "unsubscribed": int,
        "spam_complaints": int,
        "last_updated": datetime
    },
    "project_id": str,  # Future: Link to energy analysis project
    "synced_at": datetime,
    "created_by": str  # User who synced the data
}

# Collection: campaign_metrics_snapshots (time-series)
# Append-only collection for tracking metric changes over time
{
    "_id": ObjectId,
    "campaign_id": str,  # References campaigns.emailoctopus_id
    "snapshot_time": datetime,
    "metrics": {
        "sent": int,
        "opened": int,
        "clicked": int,
        "bounced": int,
        "unsubscribed": int,
        "spam_complaints": int
    },
    "rates": {
        "open_rate": float,
        "click_rate": float,
        "bounce_rate": float
    }
}

# Collection: lists
{
    "_id": ObjectId,
    "emailoctopus_id": str,
    "name": str,
    "double_opt_in": bool,
    "fields": [
        {
            "tag": str,
            "type": str,
            "label": str,
            "fallback": str
        }
    ],
    "counts": {
        "subscribed": int,
        "unsubscribed": int,
        "pending": int
    },
    "created_at": datetime,
    "synced_at": datetime
}

# Collection: contacts
{
    "_id": ObjectId,
    "emailoctopus_id": str,
    "email": str,
    "status": str,  # subscribed, unsubscribed, pending
    "fields": dict,  # Custom fields from EmailOctopus
    "tags": [str],
    "list_id": str,
    "created_at": datetime,
    "engagement_history": [
        {
            "campaign_id": str,
            "event_type": str,  # sent, opened, clicked, bounced
            "event_time": datetime
        }
    ],
    "customer_id": str,  # Future: Link to existing customer record
    "synced_at": datetime
}
```

**Phase 2: Data Linking (Future)**
```python
# Your existing collections structure will be integrated here
# Collections: customers, energy_analyses, demographics, etc.
# Linking strategy: Hybrid approach
#   - Contact level: contacts.customer_id → customers._id
#   - Campaign level: campaigns.project_id → energy_analyses._id
```

### 3. API Integration Specifications

#### Authentication
- **Method**: Bearer token (single API key)
- **Storage**: Environment variable or config file (`.env`)
- **Base URL**: `https://api.emailoctopus.com`

#### Rate Limiting Strategy
- **API Limits**: 10 requests/second, 100 token bucket
- **Implementation**:
  - Request throttling with exponential backoff
  - Queue system for batch operations
  - Cache responses to minimize API calls

#### Data Sync Strategy
- **Mode**: Periodic sync (hourly/daily configurable)
- **Storage**: MongoDB with append-only pattern for metrics history
- **Refresh**: Manual refresh button + scheduled background jobs
- **Pagination**: Handle cursor-based pagination for large datasets
- **Sync Logic**:
  - **Initial Sync**: Pull all campaigns, lists, contacts → insert into MongoDB
  - **Incremental Updates**:
    - Check for new campaigns/contacts → insert new documents
    - Update existing campaigns → append metrics snapshot if changed
    - Store engagement events → append to contact.engagement_history
  - **Deduplication**: Use `emailoctopus_id` as unique identifier to prevent duplicates

#### Key Endpoints to Implement
```python
# Campaigns
GET /campaigns                    # List all campaigns
GET /campaigns/{id}               # Campaign details
GET /campaigns/{id}/reports/summary    # Campaign metrics
GET /campaigns/{id}/reports/links      # Link click data

# Lists
GET /lists                        # All lists
GET /lists/{id}                   # List details
GET /lists/{id}/contacts          # Contacts in list

# Contacts
GET /lists/{id}/contacts          # Paginated contacts
GET /lists/{id}/contacts/{id}     # Individual contact
```

### 4. Security & Deployment

#### Security Considerations
- **API Key Protection**: Never commit API keys to version control, use environment variables
- **Password Security**:
  - Werkzeug password hashing (pbkdf2:sha256)
  - No plain text passwords stored
  - Minimum password complexity requirements
- **Session Management**:
  - Flask session with secure cookies
  - Session timeout after inactivity (30 minutes default)
  - CSRF protection with Flask-WTF
- **Access Control**:
  - Login required for all application routes
  - Public routes: /login, /static only
  - No user registration endpoint (admin creates accounts manually)
- **HTTPS**: Required for AWS deployment
- **Input Validation**: Sanitize all user inputs, prevent SQL/NoSQL injection

#### Deployment Strategy
- **Development**:
  - Local Flask development server
  - Local MongoDB instance or MongoDB Atlas free tier
- **Production**: AWS deployment options:
  - **Option A**: EC2 instance + Nginx + Gunicorn + MongoDB on same instance
  - **Option B**: AWS Elastic Beanstalk + MongoDB Atlas (recommended for simplicity)
  - **Option C**: EC2 + Separate MongoDB instance (better scalability)
- **Database**:
  - **Development**: Local MongoDB or MongoDB Atlas free tier
  - **Production**: MongoDB Atlas or self-hosted on EC2
- **Static Files**: Serve from Flask or S3 bucket
- **Environment Config**: AWS Systems Manager Parameter Store or `.env` file

---

## Implementation Roadmap

### Phase 1: MVP (Weeks 1-3)

#### Week 1: Foundation & Authentication
- [ ] Project setup (virtual environment, dependencies)
- [ ] MongoDB setup (local or Atlas)
- [ ] Flask application structure with MongoDB integration
- [ ] User authentication system:
  - [ ] User model with password hashing
  - [ ] Login/logout routes and forms
  - [ ] Flask-Login integration
  - [ ] Session management
  - [ ] Login required decorators
- [ ] Create initial user accounts (script)
- [ ] MongoDB models and collections setup (PyMongo/MongoEngine)
- [ ] EmailOctopus API client implementation
- [ ] API authentication wrapper and rate limiting
- [ ] Basic sync service (API → MongoDB)

#### Week 2: Core Features & Visualization
- [ ] Campaign data extraction and MongoDB storage
- [ ] List and contact data extraction
- [ ] Append-only metrics snapshot logic
- [ ] Dashboard page with aggregate metrics from MongoDB
- [ ] Campaign list view with filtering
- [ ] Campaign detail view with charts
- [ ] Time-series visualization for metric trends

#### Week 3: Reporting & Polish
- [ ] Report builder interface (query MongoDB)
- [ ] PDF export functionality
- [ ] Predefined report templates
- [ ] Manual sync button + sync status display
- [ ] UI/UX polish and responsive design
- [ ] Testing and bug fixes

### Phase 2: Data Linking & Cross-Domain Analytics (Future)
- [ ] Integrate existing MongoDB collections (customers, energy_analyses, demographics)
- [ ] Implement contact → customer linking (by email or custom ID)
- [ ] Implement campaign → energy project association
- [ ] Cross-domain analytics (campaign effectiveness by energy segments)
- [ ] Advanced demographic targeting and segmentation
- [ ] Real-time data sync capabilities
- [ ] Automated report scheduling
- [ ] Custom dashboard layouts

---

## Success Metrics

### MVP Success Criteria
1. ✅ User login system works with secure password hashing
2. ✅ Successfully authenticate with EmailOctopus API
3. ✅ Display all campaigns with key metrics in dashboard (login protected)
4. ✅ Generate partner report in <5 minutes (vs current manual process)
5. ✅ Export report to PDF with visualizations
6. ✅ Support 2 concurrent super users without performance issues
7. ✅ Data processing with numpy performs faster than pandas baseline

### Performance Targets
- **Page Load**: <2 seconds for dashboard
- **Login Time**: <1 second authentication check
- **API Response**: <5 seconds for full campaign sync
- **Report Generation**: <30 seconds for PDF export
- **Data Processing**: NumPy operations >2x faster than pandas equivalent
- **Session Timeout**: 30 minutes inactivity
- **Uptime**: 99% availability (AWS deployment)

---

## Technical Constraints & Assumptions

### Constraints
- Single EmailOctopus account (no multi-account support needed)
- Small number of campaigns to track
- 2 user limit (no complex role management)
- Local development priority (AWS deployment is manual)

### Assumptions
- EmailOctopus API v2 remains stable and backward-compatible
- API rate limits (10 req/sec) are sufficient for use case
- Partners require historical data, not real-time monitoring
- PDF format is acceptable for report delivery
- MongoDB is available (local or Atlas) for development and production
- Existing MongoDB collections will be provided in Phase 2
- Email address is sufficient identifier for linking contacts to customers (Phase 2)

### Risk Mitigation
- **API Changes**: Version API client, monitor EmailOctopus changelog
- **Rate Limiting**: Implement request queuing and caching
- **Data Loss**: MongoDB regular backups (mongodump), export to CSV capability
- **AWS Costs**: Start with smallest instance, monitor usage, MongoDB Atlas free tier for dev
- **MongoDB Performance**: Index on emailoctopus_id, campaign_id for fast lookups
- **Data Growth**: Time-series snapshots may grow large → implement data retention policies if needed

---

## File Structure (Proposed)

```
octopus/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Configuration management
│   ├── models/                  # MongoDB models
│   │   ├── __init__.py
│   │   ├── user.py              # User model with auth methods
│   │   ├── campaign.py          # Campaign model
│   │   ├── contact.py           # Contact model
│   │   ├── list.py              # List model
│   │   └── metrics_snapshot.py  # Metrics snapshot model
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py              # Login/logout routes
│   │   ├── dashboard.py         # Dashboard routes (login required)
│   │   ├── campaigns.py         # Campaign routes (login required)
│   │   ├── reports.py           # Report routes (login required)
│   │   └── sync.py              # Manual sync routes (login required)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py      # Authentication helper functions
│   │   ├── api_client.py        # EmailOctopus API wrapper
│   │   ├── sync_service.py      # Sync logic (API → MongoDB)
│   │   ├── data_service.py      # Data processing logic (numpy-based)
│   │   ├── report_service.py    # Report generation
│   │   └── mongo_service.py     # MongoDB helper functions
│   ├── forms/                   # WTForms for CSRF protection
│   │   ├── __init__.py
│   │   └── auth_forms.py        # Login form
│   ├── templates/               # Jinja2 templates
│   │   ├── base.html
│   │   ├── login.html           # Login page
│   │   ├── dashboard.html
│   │   ├── campaigns.html
│   │   ├── campaign_detail.html
│   │   ├── sync_status.html
│   │   └── report_builder.html
│   └── static/                  # CSS, JS, images
│       ├── css/
│       │   └── style.css
│       ├── js/
│       │   └── main.js
│       └── img/
│           └── logo.png
├── tests/                       # Unit and integration tests
│   ├── test_auth.py
│   ├── test_api_client.py
│   ├── test_sync_service.py
│   └── test_models.py
├── scripts/                     # Utility scripts
│   ├── create_user.py          # Create user accounts
│   ├── init_db.py              # Initialize MongoDB collections
│   ├── manual_sync.py          # Manual sync script
│   └── backup_db.py            # MongoDB backup script
├── .env                        # Environment variables (not in git)
├── .env.example                # Example env file
├── .gitignore
├── requirements.txt            # Python dependencies
├── README.md
└── run.py                      # Application entry point
```

---

## Next Steps

### Immediate Actions
1. **Confirm Specification**: Review and approve this specification
2. **API Key Setup**: Generate EmailOctopus API key and test access
3. **Development Environment**: Set up Python virtual environment
4. **Project Initialization**: Create Flask project structure

### Decision Points
- **Chart Library**: Plotly (interactive) vs Chart.js (lightweight)?
- **PDF Library**: ReportLab (code-based) vs WeasyPrint (HTML-to-PDF)?
- **AWS Deployment**: EC2, Elastic Beanstalk, or Lambda?
- **Report Templates**: What specific metrics do partners need?

---

## Appendix

### EmailOctopus API Reference
- **Documentation**: https://emailoctopus.com/api-documentation/v2
- **Rate Limits**: 10 requests/second, 100 token bucket
- **Authentication**: Bearer token in `Authorization` header
- **Pagination**: Cursor-based for large result sets

### Useful Libraries
```
Flask==3.0.0
pymongo==4.6.1
mongoengine==0.27.0  # Optional: ODM for easier model management
requests==2.31.0
numpy==1.26.3  # High-performance data processing (replacing pandas)
plotly==5.18.0
ReportLab==4.0.7  # or WeasyPrint==60.2
Flask-Login==0.6.3
Flask-WTF==1.2.1  # CSRF protection and forms
email-validator==2.1.0  # For email validation
python-dotenv==1.0.0
APScheduler==3.10.4  # For scheduled sync jobs
```

### Sample Code Snippets

**User Authentication Example**:
```python
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']
        self.is_active = user_data.get('is_active', True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def create_user(username, email, password):
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        user_doc = {
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "role": "super_user",
            "is_active": True,
            "created_at": datetime.utcnow()
        }
        return user_doc

# Login route example
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user_data = db.users.find_one({"username": form.username.data})
        if user_data and User(user_data).check_password(form.password.data):
            user = User(user_data)
            login_user(user, remember=form.remember.data)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html', form=form)
```

**API Request Example**:
```python
import requests

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

response = requests.get(
    "https://api.emailoctopus.com/campaigns",
    headers=headers
)

campaigns = response.json()
```

**MongoDB Storage Example**:
```python
from pymongo import MongoClient
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/")
db = client["emailoctopus_db"]

# Insert campaign data
campaign_doc = {
    "emailoctopus_id": campaign_data["id"],
    "name": campaign_data["name"],
    "subject": campaign_data["subject"],
    "status": campaign_data["status"],
    "current_metrics": {
        "sent": campaign_data["sent"],
        "opened": campaign_data["opened"],
        "clicked": campaign_data["clicked"],
        "last_updated": datetime.utcnow()
    },
    "synced_at": datetime.utcnow()
}

db.campaigns.update_one(
    {"emailoctopus_id": campaign_doc["emailoctopus_id"]},
    {"$set": campaign_doc},
    upsert=True
)

# Append metrics snapshot if changed
snapshot = {
    "campaign_id": campaign_data["id"],
    "snapshot_time": datetime.utcnow(),
    "metrics": {
        "sent": campaign_data["sent"],
        "opened": campaign_data["opened"],
        "clicked": campaign_data["clicked"]
    }
}
db.campaign_metrics_snapshots.insert_one(snapshot)
```

**NumPy Data Processing Example** (replacing pandas):
```python
import numpy as np
from datetime import datetime

# Process campaign metrics using numpy for performance
def calculate_campaign_stats(campaigns):
    """Calculate aggregate stats using numpy arrays instead of pandas"""

    # Extract metrics into numpy arrays
    sent = np.array([c['current_metrics']['sent'] for c in campaigns])
    opened = np.array([c['current_metrics']['opened'] for c in campaigns])
    clicked = np.array([c['current_metrics']['clicked'] for c in campaigns])

    # Calculate rates efficiently
    open_rates = np.divide(opened, sent, where=sent!=0, out=np.zeros_like(opened, dtype=float))
    click_rates = np.divide(clicked, sent, where=sent!=0, out=np.zeros_like(clicked, dtype=float))

    # Aggregate statistics
    stats = {
        'total_campaigns': len(campaigns),
        'total_sent': int(np.sum(sent)),
        'total_opened': int(np.sum(opened)),
        'total_clicked': int(np.sum(clicked)),
        'avg_open_rate': float(np.mean(open_rates)),
        'avg_click_rate': float(np.mean(click_rates)),
        'median_open_rate': float(np.median(open_rates)),
        'std_open_rate': float(np.std(open_rates))
    }

    return stats

# Time-series processing with numpy
def process_metrics_timeseries(snapshots):
    """Process time-series data efficiently with numpy"""

    # Convert to structured numpy array
    timestamps = np.array([s['snapshot_time'] for s in snapshots])
    opens = np.array([s['metrics']['opened'] for s in snapshots])

    # Calculate moving average (7-day window)
    window_size = 7
    moving_avg = np.convolve(opens, np.ones(window_size)/window_size, mode='valid')

    return {
        'timestamps': timestamps.tolist(),
        'values': opens.tolist(),
        'moving_average': moving_avg.tolist()
    }
```
