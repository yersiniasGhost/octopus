# Multi-Channel Dashboard Design - Executive Summary
**Date**: November 5, 2025
**Status**: ✅ Design Complete - Ready for Review

## Overview

Comprehensive redesign of the campaign dashboard system to support 4 campaign types (Email, Text, Mailer, Letter) with data from multiple databases.

---

## Architecture at a Glance

```
                    NEW MAIN DASHBOARD
                    ==================
        ┌────────────────────────────────────────┐
        │  🏠 Multi-Channel Campaign Overview    │
        │                                        │
        │  [Email: 69]  [Text: TBD]             │
        │  [Mailer: TBD] [Letter: TBD]          │
        │                                        │
        │  Cross-Channel Performance Charts      │
        │  Recent Activity Timeline              │
        └────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┬────────┐
        │               │               │        │
        ▼               ▼               ▼        ▼
    ┌───────┐      ┌───────┐      ┌───────┐  ┌───────┐
    │ EMAIL │      │ TEXT  │      │MAILER │  │LETTER │
    │       │      │       │      │       │  │       │
    │ACTIVE │      │ NEW   │      │  TBD  │  │  TBD  │
    └───────┘      └───────┘      └───────┘  └───────┘
```

---

## Key Design Decisions

### 1. **Unified Main Dashboard**
- **Purpose**: Single overview showing all 4 campaign types
- **Features**:
  - Campaign type cards with quick stats
  - Cross-channel performance comparison
  - Recent activity timeline (all types)
  - Navigation to type-specific dashboards

### 2. **Multi-Database Architecture**
- **Current State**:
  - Email campaigns → `emailoctopus_db`
  - Text/Mailer/Letter → `empowersaves_development_db`
- **Data Service Layer**: Unified `CampaignDataService` class
- **Future-Proof**: Supports migration to single database

### 3. **Campaign Type Dashboards**

#### ✅ Email Dashboard (Existing - Minimal Changes)
- Route: `/dashboard/email` (renamed from `/dashboard`)
- Keep all existing charts and functionality
- Add breadcrumb and campaign type badge

#### 🆕 Text/SMS Dashboard (New Implementation)
- Route: `/dashboard/text`
- Database: `empowersaves_development_db`
- Participant Model: Uses `applicants` collection (different from email)
- Charts:
  - Messages sent by campaign
  - Delivery success vs failed
  - Engagement metrics (clicked/delivered)
  - Opt-out trends over time

#### 🔜 Mailer Dashboard (TBD Placeholder)
- Route: `/dashboard/mailer`
- "Coming Soon" placeholder template
- Will track: printed, mailed, delivered, returned, costs

#### 🔜 Letter Dashboard (TBD Placeholder)
- Route: `/dashboard/letter`
- "Coming Soon" placeholder template
- Will track: printed, mailed, delivered, certified mail, costs

---

## Database Architecture

### Current Structure

```yaml
emailoctopus_db:
  campaigns:
    - campaign_type: "email"
    - count: 69
    - participants: linked via campaign_id

empowersaves_development_db:
  campaigns:
    - campaign_type: "text" | "mailer" | "letter"
    - count: 3 (samples)
  applicants:
    - text campaign participants
    - DIFFERENT MODEL than email participants
```

### Data Service Pattern

```python
class CampaignDataService:
    """Unified access to campaigns across databases"""

    def __init__(self):
        self.email_db = MongoClient(...)['emailoctopus_db']
        self.empower_db = MongoClient(...)['empowersaves_development_db']

    def get_email_campaigns(self, limit=20):
        """Email campaigns from emailoctopus_db"""

    def get_text_campaigns(self, limit=20):
        """Text campaigns from empowersaves_development_db"""

    def get_all_campaign_stats(self):
        """Aggregate stats for all types"""
```

---

## Implementation Phases

### Phase 1: Main Dashboard (Week 1)
**Tasks**:
- Rename `/dashboard` → `/dashboard/email`
- Create new main dashboard at `/`
- Implement `CampaignDataService` for multi-database access
- Create campaign type overview cards
- Add cross-channel performance charts
- Update navigation and breadcrumbs

**Files**:
- `app/services/campaign_data_service.py` (new)
- `app/templates/dashboard.html` (new main dashboard)
- `app/templates/dashboards/email.html` (renamed from dashboard.html)
- `app/routes/main.py` (modified)

### Phase 2: Text Dashboard (Week 2)
**Tasks**:
- Create text dashboard route
- Implement text campaign queries
- Design text dashboard template
- Create text campaign list/detail views
- Map applicant model to participant interface
- Add text-specific charts

**Files**:
- `app/templates/dashboards/text.html` (new)
- `app/templates/campaigns/text_list.html` (new)
- `app/templates/campaigns/text_detail.html` (new)
- `app/routes/dashboards.py` (new)

### Phase 3: TBD Stubs (Week 2)
**Tasks**:
- Create mailer/letter placeholder routes
- Design "Coming Soon" templates
- Add navigation links

**Files**:
- `app/templates/dashboards/mailer_tbd.html` (new)
- `app/templates/dashboards/letter_tbd.html` (new)

---

## Visual Design

### Campaign Type Colors

| Type   | Color          | Icon              |
|--------|----------------|-------------------|
| Email  | Blue (#0d6efd) | 📧 bi-envelope    |
| Text   | Green (#198754)| 📱 bi-phone       |
| Mailer | Orange (#fd7e14)| 📬 bi-mailbox    |
| Letter | Purple (#6f42c1)| 📄 bi-file-text  |

### Navigation Flow

```
Main Dashboard (/)
├── Email Dashboard (/dashboard/email)
│   ├── Campaign List (/campaigns)
│   └── Campaign Detail (/campaigns/<id>)
│
├── Text Dashboard (/dashboard/text)
│   ├── Campaign List (/campaigns/text)
│   └── Campaign Detail (/campaigns/text/<id>)
│
├── Mailer Dashboard (/dashboard/mailer) [TBD]
└── Letter Dashboard (/dashboard/letter) [TBD]
```

---

## Key Features

### Main Dashboard Features
1. **Campaign Type Cards**: Quick overview with counts, status, navigation
2. **Cross-Channel Charts**:
   - Campaign volume by type (bar chart)
   - Engagement rates by type (line chart)
   - Cost efficiency by type (bar chart)
3. **Recent Activity Timeline**: All campaign types, sorted by date
4. **Quick Actions**: Links to each dashboard type

### Text Dashboard Features
1. **Statistics Cards**:
   - Total campaigns
   - Messages sent
   - Delivered count
   - Click-through rate
   - Opt-out rate
   - Failed delivery rate

2. **Charts**:
   - Messages sent by campaign (bar)
   - Delivery success vs failed (stacked bar)
   - Engagement metrics (bar)
   - Opt-out trends (line)

3. **Campaign Table**: Recent text campaigns with key metrics

---

## Important Notes

### Different Participant Models
⚠️ **Critical**: Text campaigns use `applicants` model, NOT `participants` model
- Email: Uses `participants` collection
- Text: Uses `applicants` collection
- Different field structures
- Requires mapping layer

### Database Separation
📊 **Current State**: Two separate databases
- `emailoctopus_db` → Email campaigns only
- `empowersaves_development_db` → Text, Mailer, Letter campaigns

🔮 **Future State**: Plan to migrate email data to `empowersaves_development_db`
- Design supports this migration
- Data service layer abstracts database access
- No template changes required after migration

---

## Success Criteria

### Phase 1 Complete ✅
- [ ] Main dashboard displays with 4 campaign type cards
- [ ] Email dashboard accessible and functional
- [ ] Cross-channel comparison charts working
- [ ] Navigation and breadcrumbs correct

### Phase 2 Complete ✅
- [ ] Text dashboard displays text campaign data
- [ ] Text campaign statistics accurate
- [ ] Text campaign charts rendering
- [ ] Applicant data properly mapped

### Phase 3 Complete ✅
- [ ] Mailer TBD stub page created
- [ ] Letter TBD stub page created
- [ ] All navigation links functional

### Overall Success ✅
- [ ] All 4 campaign types visible
- [ ] User can navigate to type-specific dashboards
- [ ] Data displays correctly from both databases
- [ ] System is extensible for new types

---

## Next Steps

### Immediate Actions
1. **Review Design**: Approve overall architecture and approach
2. **Confirm Data Models**: Verify applicant vs participant model differences
3. **Start Phase 1**: Begin main dashboard implementation
4. **Setup Development**: Create feature branch for dashboard redesign

### Questions to Resolve
1. ✅ Text campaign participant data location? → `applicants` collection
2. ✅ Database names confirmed? → Yes
3. ✅ Keep email in separate DB for now? → Yes, migrate later
4. 📋 Timeline for Mailer/Letter implementation? → TBD

---

## Documentation

**Complete Design Document**:
`.claude_docs/20251105_Multi-Channel_Dashboard_Design.md`

**Contents**:
- Detailed architecture diagrams
- Complete code examples for data service
- Database schema reference
- UI/UX design guidelines
- Migration considerations
- Testing strategy
- Implementation checklist

---

## Timeline Estimate

- **Phase 1** (Main Dashboard): 3-5 days
- **Phase 2** (Text Dashboard): 5-7 days
- **Phase 3** (TBD Stubs): 1-2 days
- **Testing & Polish**: 2-3 days

**Total**: 2-3 weeks for complete implementation

---

## Approval Required

**Design Ready**: ✅ Complete and documented
**Next Step**: Review and approve to begin implementation

**Reviewer**: Frank Rich
**Design Date**: November 5, 2025
**Designer**: Claude Code with /sc:design
