# Multi-Channel Campaign Dashboard Design
**Date**: November 5, 2025
**Design**: /sc:design multi-channel dashboard system

## Executive Summary

Redesign of the main dashboard and creation of campaign-type-specific dashboards to support Email, Text, Mailer, and Letter campaigns with data from multiple databases.

### Key Design Decisions
1. **Main Dashboard**: Unified overview showing all 4 campaign types with navigation cards
2. **Type-Specific Dashboards**: Separate dashboards for Email, Text, Mailer (TBD), and Letter (TBD)
3. **Data Architecture**: Multi-database access pattern for EmailOctopus (emailoctopus_db) and Text/Mailer/Letter (empowersaves_development_db)
4. **Future-Proofing**: Design accommodates future migration of Email data to empowersaves_development_db

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      MAIN DASHBOARD                          │
│  - Overall campaign statistics (all types)                   │
│  - Navigation cards to type-specific dashboards              │
│  - Cross-channel performance comparison                      │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┬──────────────────┐
        │                   │                   │                  │
        ▼                   ▼                   ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│    EMAIL     │   │   TEXT/SMS   │   │    MAILER    │   │    LETTER    │
│  DASHBOARD   │   │  DASHBOARD   │   │  DASHBOARD   │   │  DASHBOARD   │
│              │   │              │   │              │   │              │
│ (EXISTING)   │   │    (NEW)     │   │   (TBD)      │   │   (TBD)      │
│              │   │              │   │              │   │              │
│ emailoctopus │   │ empowersaves │   │ empowersaves │   │ empowersaves │
│    _db       │   │ _development │   │ _development │   │ _development │
│              │   │     _db      │   │     _db      │   │     _db      │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

---

## Database Architecture

### Current State
```yaml
emailoctopus_db:
  collections:
    - campaigns:
        campaign_type: "email"
        count: 69
        source: EmailOctopus API sync
    - participants:
        linked_to: campaigns via campaign_id
        fields: email, demographics, engagement

empowersaves_development_db:
  collections:
    - campaigns:
        campaign_type: "text" | "mailer" | "letter"
        count: 3 (1 text, 1 mailer, 1 letter sample)
        source: Manual imports/integrations
    - applicants:
        different_model: true
        note: "Text campaign participants use this model"
```

### Future State (Post-Migration)
```yaml
empowersaves_development_db:
  collections:
    - campaigns:
        campaign_type: "email" | "text" | "mailer" | "letter"
        unified: true
    - participants:
        unified: true
        all_campaign_types: true
```

---

## Main Dashboard Design

### Purpose
Unified overview of all campaign activities with quick navigation to type-specific details.

### Components

#### 1. Campaign Type Overview Cards (Top Section)
```
┌────────────────────────────────────────────────────────────────┐
│  CAMPAIGN TYPES OVERVIEW                                       │
├─────────────┬─────────────┬─────────────┬─────────────────────┤
│   EMAIL     │  TEXT/SMS   │   MAILER    │    LETTER           │
│   69 ▲      │    TBD ▲    │   TBD ▲     │    TBD ▲            │
│   View →    │  View →     │  View →     │   View →            │
└─────────────┴─────────────┴─────────────┴─────────────────────┘
```

Each card shows:
- Campaign type icon
- Total campaigns count
- Active campaigns count
- Last campaign date
- Quick "View Dashboard" link
- Status badge (Active/TBD for future types)

#### 2. Cross-Channel Performance (Middle Section)
```
┌────────────────────────────────────────────────────────────────┐
│  CROSS-CHANNEL PERFORMANCE COMPARISON                          │
├────────────────────────────────────────────────────────────────┤
│  Chart: Campaign Volume by Type (Bar Chart)                    │
│  Chart: Engagement Rates by Type (Line Chart)                  │
│  Chart: Cost Efficiency by Type (Bar Chart - $/engagement)     │
└────────────────────────────────────────────────────────────────┘
```

#### 3. Recent Activity Timeline (Bottom Section)
```
┌────────────────────────────────────────────────────────────────┐
│  RECENT CAMPAIGN ACTIVITY (All Types)                          │
├────────────────────────────────────────────────────────────────┤
│  [EMAIL]   Campaign Name 1                Nov 4, 2025          │
│  [TEXT]    Campaign Name 2                Nov 3, 2025          │
│  [EMAIL]   Campaign Name 3                Nov 2, 2025          │
│  [MAILER]  Campaign Name 4                Nov 1, 2025          │
└────────────────────────────────────────────────────────────────┘
```

### Data Sources

```python
# Main dashboard data aggregation
def get_main_dashboard_stats():
    """Aggregate stats from both databases"""

    # Email campaigns (emailoctopus_db)
    email_client = MongoClient(MONGO_URI)
    email_db = email_client['emailoctopus_db']
    email_campaigns = email_db.campaigns.count_documents({'campaign_type': 'email'})

    # Other campaigns (empowersaves_development_db)
    empower_client = MongoClient(MONGO_URI)
    empower_db = empower_client['empowersaves_development_db']
    text_campaigns = empower_db.campaigns.count_documents({'campaign_type': 'text'})
    mailer_campaigns = empower_db.campaigns.count_documents({'campaign_type': 'mailer'})
    letter_campaigns = empower_db.campaigns.count_documents({'campaign_type': 'letter'})

    return {
        'email': {
            'total': email_campaigns,
            'database': 'emailoctopus_db',
            'status': 'active'
        },
        'text': {
            'total': text_campaigns,
            'database': 'empowersaves_development_db',
            'status': 'active' if text_campaigns > 0 else 'tbd'
        },
        'mailer': {
            'total': mailer_campaigns,
            'database': 'empowersaves_development_db',
            'status': 'tbd'
        },
        'letter': {
            'total': letter_campaigns,
            'database': 'empowersaves_development_db',
            'status': 'tbd'
        }
    }
```

---

## Email Dashboard (Existing)

### Current Location
- Route: `/dashboard`
- Database: `emailoctopus_db`
- Status: ✅ **Fully Implemented**

### Design Changes
**Minimal changes required**:
1. Add breadcrumb: `Home > Email Dashboard`
2. Add campaign type badge: `[EMAIL]` on page header
3. Update "Quick Actions" to include "View All Campaigns" link to main dashboard

### Keep As-Is
- All existing charts (sent, opened/clicked, CTR, zipcode)
- All existing statistics cards
- All existing functionality

---

## Text/SMS Dashboard (New)

### Purpose
Display Text/SMS campaign analytics from empowersaves_development_db.

### Route Structure
```python
# New route
@main_bp.route('/dashboard/text')
@login_required
def text_dashboard():
    """Text/SMS campaign dashboard"""
```

### Database
- **Database**: `empowersaves_development_db`
- **Collections**: `campaigns` (campaign_type='text'), `applicants`
- **Note**: Participants for text campaigns use `applicants` model, NOT `participants` model

### Components

#### 1. Statistics Cards (Top Row)
```
┌─────────────┬─────────────┬─────────────┬─────────────────────┐
│  CAMPAIGNS  │   SENT      │  DELIVERED  │   CLICK RATE        │
│     10      │  125,000    │   123,450   │      2.5%           │
└─────────────┴─────────────┴─────────────┴─────────────────────┘
```

Stats to display:
- Total text campaigns
- Total messages sent
- Delivered count (sent - failed)
- Average click-through rate
- Opt-out rate
- Failed delivery rate

#### 2. Charts (Middle Section)

**Chart 1: Messages Sent by Campaign**
- Bar chart showing message volume per campaign
- Sorted by sent count (highest first)
- Similar to existing email dashboard

**Chart 2: Delivery Success vs Failed**
- Stacked bar chart per campaign
- Green: Delivered
- Red: Failed
- Shows delivery reliability

**Chart 3: Engagement Metrics**
- Bar chart showing clicked vs delivered
- Calculate click-through rate per campaign

**Chart 4: Opt-Out Trends**
- Line chart over time
- Track opt-out rate trends
- Alert if rate exceeds threshold (e.g., >2%)

#### 3. Campaign List Table (Bottom Section)
```
┌──────────────────────────────────────────────────────────────┐
│  RECENT TEXT CAMPAIGNS                                        │
├──────────────┬─────────┬──────────┬──────────┬───────────────┤
│ Campaign     │ Sent    │ Delivered│ Clicked  │ Date          │
├──────────────┼─────────┼──────────┼──────────┼───────────────┤
│ Summer Crisis│ 10,000  │ 9,850    │ 245      │ Nov 4, 2025   │
│ HEAP Reminder│ 8,500   │ 8,400    │ 180      │ Nov 1, 2025   │
└──────────────┴─────────┴──────────┴──────────┴───────────────┘
```

### Data Model Mapping

```python
# Text Campaign Statistics from empowersaves_development_db
{
    "campaign_type": "text",
    "statistics": {
        "sent": {"unique": 10000},
        "delivered": {"unique": 9850},
        "clicked": {"unique": 245},
        "failed": {"unique": 150},
        "opt_outs": {"unique": 12}
    }
}

# Applicants collection (text campaign participants)
# NOTE: Different from email participants model
{
    "phone_number": "+15551234567",
    "first_name": "John",
    "last_name": "Doe",
    "city": "Columbus",
    "zip": "43215",
    # ... other applicant fields
}
```

### Implementation Requirements

1. **Data Service Layer** (New)
```python
# app/services/campaign_data_service.py
class CampaignDataService:
    """Unified data access for campaigns across databases"""

    def __init__(self):
        self.email_db = MongoClient(MONGO_URI)['emailoctopus_db']
        self.empower_db = MongoClient(MONGO_URI)['empowersaves_development_db']

    def get_text_campaigns(self, limit=20):
        """Get text campaigns from empowersaves_development_db"""
        return list(self.empower_db.campaigns.find(
            {'campaign_type': 'text'}
        ).sort('sent_at', -1).limit(limit))

    def get_text_campaign_stats(self):
        """Aggregate text campaign statistics"""
        # Implementation
        pass
```

2. **Template** (New)
- `app/templates/dashboards/text.html`
- Follow same design pattern as existing dashboard
- Reuse chart components and styling

3. **Route** (New)
- Add to `app/routes/main.py` or new `app/routes/dashboards.py`

---

## Mailer Dashboard (TBD Stub)

### Purpose
Physical mailer campaign tracking (placeholder for future implementation).

### Route Structure
```python
@main_bp.route('/dashboard/mailer')
@login_required
def mailer_dashboard():
    """Mailer campaign dashboard (TBD)"""
    return render_template('dashboards/mailer_tbd.html')
```

### Database
- **Database**: `empowersaves_development_db`
- **Collections**: `campaigns` (campaign_type='mailer')

### TBD Placeholder Design

```
┌────────────────────────────────────────────────────────────────┐
│  MAILER CAMPAIGNS (Coming Soon)                                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📬 Mailer Campaign Dashboard                                  │
│                                                                 │
│  This dashboard will display:                                  │
│  - Total mailer campaigns                                      │
│  - Print and mail statistics                                   │
│  - Delivery tracking                                           │
│  - Return/undeliverable rates                                  │
│  - Cost per mail piece                                         │
│                                                                 │
│  Status: Coming Soon                                           │
│                                                                 │
│  [Return to Main Dashboard]                                    │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Future Statistics to Track
- Printed count
- Mailed count
- Estimated delivery count
- Returned mail count
- Delivery rate percentage
- Cost per mailer
- Total campaign cost

---

## Letter Dashboard (TBD Stub)

### Purpose
Letter campaign tracking (placeholder for future implementation).

### Route Structure
```python
@main_bp.route('/dashboard/letter')
@login_required
def letter_dashboard():
    """Letter campaign dashboard (TBD)"""
    return render_template('dashboards/letter_tbd.html')
```

### Database
- **Database**: `empowersaves_development_db`
- **Collections**: `campaigns` (campaign_type='letter')

### TBD Placeholder Design

```
┌────────────────────────────────────────────────────────────────┐
│  LETTER CAMPAIGNS (Coming Soon)                                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✉️ Letter Campaign Dashboard                                  │
│                                                                 │
│  This dashboard will display:                                  │
│  - Total letter campaigns                                      │
│  - Print and mail statistics                                   │
│  - Certified mail tracking                                     │
│  - Delivery confirmation rates                                 │
│  - Return/undeliverable rates                                  │
│  - Cost per letter                                             │
│                                                                 │
│  Status: Coming Soon                                           │
│                                                                 │
│  [Return to Main Dashboard]                                    │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Future Statistics to Track
- Printed count
- Mailed count
- Delivered count
- Returned count
- Certified mail count
- Delivery confirmation rate
- Cost per letter
- Total campaign cost

---

## Navigation Structure

### Updated Navigation Flow

```
Main Dashboard (/)
├── Email Dashboard (/dashboard)
│   ├── Campaign List (/campaigns)
│   └── Campaign Detail (/campaigns/<id>)
│
├── Text Dashboard (/dashboard/text)
│   ├── Campaign List (/campaigns/text)
│   └── Campaign Detail (/campaigns/text/<id>)
│
├── Mailer Dashboard (/dashboard/mailer) [TBD]
│   └── Coming Soon Placeholder
│
└── Letter Dashboard (/dashboard/letter) [TBD]
    └── Coming Soon Placeholder
```

### Breadcrumb Pattern
```html
<!-- Main Dashboard -->
Home

<!-- Email Dashboard -->
Home > Email Campaigns

<!-- Email Campaign Detail -->
Home > Email Campaigns > Campaign Name

<!-- Text Dashboard -->
Home > Text Campaigns

<!-- Text Campaign Detail -->
Home > Text Campaigns > Campaign Name
```

---

## Technical Implementation Plan

### Phase 1: Main Dashboard Redesign (Week 1)

**Tasks**:
1. Rename current `/dashboard` to `/dashboard/email`
2. Create new main dashboard at `/`
3. Implement multi-database aggregation service
4. Create campaign type overview cards
5. Add cross-channel performance charts
6. Update navigation and breadcrumbs

**Files to Modify**:
- `app/routes/main.py` - Add new main dashboard route
- `app/templates/index.html` - Rename to `landing.html`
- `app/templates/dashboard.html` - Rename to `dashboards/email.html`
- Create `app/templates/dashboard.html` - New main dashboard

**Files to Create**:
- `app/services/campaign_data_service.py` - Multi-database access
- `app/templates/dashboards/main.html` - Main dashboard template

### Phase 2: Text Dashboard Implementation (Week 2)

**Tasks**:
1. Create text dashboard route and controller
2. Implement text campaign data queries
3. Design and create text dashboard template
4. Create text campaign list and detail views
5. Map applicant model to participant interface
6. Add text-specific charts and visualizations

**Files to Create**:
- `app/routes/dashboards.py` - Dashboard routes module
- `app/templates/dashboards/text.html` - Text dashboard
- `app/templates/campaigns/text_list.html` - Text campaign list
- `app/templates/campaigns/text_detail.html` - Text campaign detail

### Phase 3: Mailer & Letter Stubs (Week 2)

**Tasks**:
1. Create TBD placeholder routes
2. Design coming soon templates
3. Add navigation links
4. Document future implementation requirements

**Files to Create**:
- `app/templates/dashboards/mailer_tbd.html`
- `app/templates/dashboards/letter_tbd.html`

### Phase 4: Testing & Documentation (Week 3)

**Tasks**:
1. Test multi-database access
2. Verify all navigation flows
3. Test with real text campaign data
4. Document new dashboard system
5. Create user guide

---

## Data Service Architecture

### Multi-Database Access Pattern

```python
# app/services/campaign_data_service.py

from pymongo import MongoClient
from typing import Dict, List, Any
from src.utils.envvars import EnvVars

class CampaignDataService:
    """
    Unified data access service for campaigns across multiple databases.

    Handles:
    - Email campaigns (emailoctopus_db)
    - Text/SMS campaigns (empowersaves_development_db)
    - Mailer campaigns (empowersaves_development_db)
    - Letter campaigns (empowersaves_development_db)
    """

    def __init__(self):
        env = EnvVars()
        mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')

        self.client = MongoClient(mongo_uri)
        self.email_db = self.client['emailoctopus_db']
        self.empower_db = self.client['empowersaves_development_db']

    # Email campaign methods (emailoctopus_db)
    def get_email_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get email campaigns from emailoctopus_db"""
        return list(self.email_db.campaigns.find(
            {'campaign_type': 'email'}
        ).sort('sent_at', -1).limit(limit))

    def get_email_stats(self) -> Dict[str, Any]:
        """Aggregate email campaign statistics"""
        pipeline = [
            {'$match': {'campaign_type': 'email'}},
            {'$group': {
                '_id': None,
                'total_campaigns': {'$sum': 1},
                'total_sent': {'$sum': '$statistics.sent.unique'},
                'total_opened': {'$sum': '$statistics.opened.unique'},
                'total_clicked': {'$sum': '$statistics.clicked.unique'}
            }}
        ]
        result = list(self.email_db.campaigns.aggregate(pipeline))
        return result[0] if result else {}

    # Text campaign methods (empowersaves_development_db)
    def get_text_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get text campaigns from empowersaves_development_db"""
        return list(self.empower_db.campaigns.find(
            {'campaign_type': 'text'}
        ).sort('sent_at', -1).limit(limit))

    def get_text_stats(self) -> Dict[str, Any]:
        """Aggregate text campaign statistics"""
        pipeline = [
            {'$match': {'campaign_type': 'text'}},
            {'$group': {
                '_id': None,
                'total_campaigns': {'$sum': 1},
                'total_sent': {'$sum': '$statistics.sent.unique'},
                'total_delivered': {'$sum': '$statistics.delivered.unique'},
                'total_clicked': {'$sum': '$statistics.clicked.unique'},
                'total_failed': {'$sum': '$statistics.failed.unique'},
                'total_opt_outs': {'$sum': '$statistics.opt_outs.unique'}
            }}
        ]
        result = list(self.empower_db.campaigns.aggregate(pipeline))
        return result[0] if result else {}

    # Mailer campaign methods (empowersaves_development_db)
    def get_mailer_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get mailer campaigns from empowersaves_development_db"""
        return list(self.empower_db.campaigns.find(
            {'campaign_type': 'mailer'}
        ).sort('sent_at', -1).limit(limit))

    # Letter campaign methods (empowersaves_development_db)
    def get_letter_campaigns(self, limit: int = 20) -> List[Dict]:
        """Get letter campaigns from empowersaves_development_db"""
        return list(self.empower_db.campaigns.find(
            {'campaign_type': 'letter'}
        ).sort('sent_at', -1).limit(limit))

    # Cross-channel analytics
    def get_all_campaign_stats(self) -> Dict[str, Any]:
        """Get aggregated stats for all campaign types"""
        return {
            'email': self.get_email_stats(),
            'text': self.get_text_stats(),
            'mailer': {
                'total_campaigns': self.empower_db.campaigns.count_documents({'campaign_type': 'mailer'})
            },
            'letter': {
                'total_campaigns': self.empower_db.campaigns.count_documents({'campaign_type': 'letter'})
            }
        }

    def get_recent_campaigns_all_types(self, limit: int = 10) -> List[Dict]:
        """Get most recent campaigns across all types"""
        # Combine campaigns from both databases
        email_campaigns = list(self.email_db.campaigns.find(
            {'campaign_type': 'email'},
            {'name': 1, 'campaign_type': 1, 'sent_at': 1, '_id': 0}
        ).sort('sent_at', -1).limit(limit))

        other_campaigns = list(self.empower_db.campaigns.find(
            {'campaign_type': {'$in': ['text', 'mailer', 'letter']}},
            {'name': 1, 'campaign_type': 1, 'sent_at': 1, '_id': 0}
        ).sort('sent_at', -1).limit(limit))

        # Merge and sort by sent_at
        all_campaigns = email_campaigns + other_campaigns
        all_campaigns.sort(key=lambda x: x.get('sent_at', ''), reverse=True)

        return all_campaigns[:limit]
```

---

## UI/UX Design Guidelines

### Color Scheme by Campaign Type

```css
/* Campaign type colors */
.campaign-type-email {
    background-color: #0d6efd; /* Primary blue */
    color: white;
}

.campaign-type-text {
    background-color: #198754; /* Success green */
    color: white;
}

.campaign-type-mailer {
    background-color: #fd7e14; /* Orange */
    color: white;
}

.campaign-type-letter {
    background-color: #6f42c1; /* Purple */
    color: white;
}

.campaign-type-tbd {
    background-color: #6c757d; /* Gray */
    color: white;
}
```

### Icons by Campaign Type

- **Email**: `<i class="bi bi-envelope-fill"></i>`
- **Text/SMS**: `<i class="bi bi-phone-fill"></i>`
- **Mailer**: `<i class="bi bi-mailbox"></i>`
- **Letter**: `<i class="bi bi-file-text-fill"></i>`

### Badge Component

```html
<span class="badge campaign-type-{{ campaign_type }}">
    <i class="bi bi-{{ icon_name }}"></i> {{ campaign_type|upper }}
</span>
```

---

## Migration Considerations

### Future Email Data Migration

When migrating email campaigns from `emailoctopus_db` to `empowersaves_development_db`:

1. **Data Compatibility**
   - Both databases already use same Campaign model
   - `campaign_type` field ensures proper identification
   - Statistics structure is identical

2. **Migration Script Approach**
```python
# scripts/migrate_email_to_empower_db.py
def migrate_email_campaigns():
    """
    Migrate email campaigns from emailoctopus_db to empowersaves_development_db
    """
    # 1. Copy campaigns collection
    # 2. Copy participants collection
    # 3. Verify data integrity
    # 4. Update application database references
    # 5. Archive emailoctopus_db
```

3. **Application Changes After Migration**
   - Update `CampaignDataService` to use single database
   - Remove `email_db` references
   - Update configuration
   - No template changes needed
   - No route changes needed

---

## Testing Strategy

### Unit Tests
- Test `CampaignDataService` methods
- Mock MongoDB connections
- Verify data aggregation logic

### Integration Tests
- Test multi-database queries
- Verify campaign type filtering
- Test navigation flows

### Manual Testing Checklist
- [ ] Main dashboard displays all 4 campaign types
- [ ] Email dashboard shows existing data
- [ ] Text dashboard shows text campaign data
- [ ] Mailer dashboard shows TBD placeholder
- [ ] Letter dashboard shows TBD placeholder
- [ ] Navigation breadcrumbs work correctly
- [ ] Charts render properly on all dashboards
- [ ] Cross-channel comparison displays correctly
- [ ] Recent activity timeline shows all types

---

## Documentation Requirements

### Files to Create/Update
1. **User Guide**: `DASHBOARD_USER_GUIDE.md`
2. **API Documentation**: `CAMPAIGN_DATA_SERVICE.md`
3. **Migration Guide**: `EMAIL_MIGRATION_PLAN.md`
4. **Design Decisions**: This document

### Screenshots Needed
- Main dashboard overview
- Each campaign type dashboard
- Navigation flow diagram
- Cross-channel comparison charts

---

## Success Criteria

### Phase 1 Complete When:
- ✅ Main dashboard displays with 4 campaign type cards
- ✅ Email dashboard accessible from main dashboard
- ✅ Cross-channel comparison charts functional
- ✅ Navigation and breadcrumbs working

### Phase 2 Complete When:
- ✅ Text dashboard displays text campaign data
- ✅ Text campaign statistics accurate
- ✅ Text campaign charts rendering correctly
- ✅ Applicant data properly mapped

### Phase 3 Complete When:
- ✅ Mailer TBD stub page created
- ✅ Letter TBD stub page created
- ✅ All navigation links functional

### Overall Success:
- ✅ All 4 campaign types visible in main dashboard
- ✅ User can navigate to type-specific dashboards
- ✅ Data displays correctly from both databases
- ✅ Future migration path is clear
- ✅ System is extensible for new campaign types

---

## Appendix

### Database Collections Schema Reference

#### emailoctopus_db.campaigns
```python
{
    "_id": ObjectId,
    "campaign_id": str,
    "campaign_type": "email",
    "name": str,
    "subject": str,
    "statistics": {
        "sent": {"unique": int},
        "opened": {"unique": int},
        "clicked": {"unique": int},
        "bounced": {"unique": int},
        "complained": {"unique": int},
        "unsubscribed": {"unique": int}
    },
    "sent_at": datetime
}
```

#### empowersaves_development_db.campaigns
```python
{
    "_id": ObjectId,
    "campaign_id": str,
    "campaign_type": "text" | "mailer" | "letter",
    "name": str,
    "statistics": {
        # Text campaigns
        "sent": {"unique": int},
        "delivered": {"unique": int},
        "clicked": {"unique": int},
        "failed": {"unique": int},
        "opt_outs": {"unique": int}
    },
    "sent_at": datetime
}
```

### Environment Variables Required

```bash
# .env
MONGO_URI=mongodb://localhost:27017
EMAILOCTOPUS_API_KEY=your-api-key-here
```

### Dependencies

No new dependencies required. Existing stack:
- Flask 3.0.0
- PyMongo 4.6.1
- Chart.js (via CDN)
- Bootstrap 5 (via CDN)

---

**Design Status**: ✅ Complete - Ready for Implementation
**Next Step**: Review and approve design, then begin Phase 1 implementation
