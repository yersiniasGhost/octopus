# Multi-Channel Dashboard Design (UPDATED)
**Date**: November 5, 2025
**Status**: ✅ Updated with corrected data model
**See Also**: `20251105_Data_Model_Clarification.md`

## Critical Update: Participants vs Applicants

⚠️ **Important Clarification**:
- **Participants** = People contacted by campaigns (all channels)
- **Applicants** = People who signed up for the program (conversions from any channel)

This creates a **conversion funnel**: Campaign → Participants → Applicants

---

## Architecture Overview (UPDATED)

```
┌─────────────────────────────────────────────────────────────┐
│                      MAIN DASHBOARD                          │
│                                                               │
│  Campaign Overview (All Types)                               │
│  - Email: 69 campaigns, 50K participants                    │
│  - Text: TBD campaigns, TBD participants                    │
│  - Mailer: TBD campaigns, TBD participants                  │
│  - Letter: TBD campaigns, TBD participants                  │
│                                                               │
│  Program Conversions (NEW)                                   │
│  - Total Applicants: 155 sign-ups                           │
│  - Overall Conversion Rate: 0.17%                           │
│  - Conversion by Channel                                     │
│                                                               │
│  Navigation to Type-Specific Dashboards                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Model (CORRECTED)

### Collections Purpose

#### `participants` Collection (All Channels)
**Purpose**: Track people **contacted** by campaigns

**Used By**:
- Email campaigns (email_address populated)
- Text campaigns (phone_number populated)
- Mailer campaigns (mailing address)
- Letter campaigns (mailing address)

**What It Stores**:
```python
{
    "contact_id": "email or phone",
    "email_address": "john@example.com",  # For email campaigns
    "phone_number": "+15551234567",       # For text campaigns
    "status": "SUBSCRIBED | OPTED_OUT",
    "engagements": [
        {
            "campaign_id": "campaign_123",
            "opened": true,
            "clicked": false,
            # Campaign-specific engagement metrics
        }
    ],
    "residence_ref": {...},
    "demographic_ref": {...}
}
```

#### `applicants` Collection (All Channels)
**Purpose**: Track people who **signed up** for the program

**Used By**: All campaign types (conversions)

**What It Stores**:
```python
{
    "entry_id": "form_submission_123",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+15551234567",
    "address": "123 Main St",
    "city": "Columbus",
    "zip_code": "43215",
    "county": "Franklin",
    "match_info": {...},
    "residence_ref": {...},
    "demographic_ref": {...},
    # Future: source_campaign_id, source_campaign_type
}
```

### Current Limitation

🚨 **Cannot directly attribute applicants to specific campaigns**
- We know total applicants across all campaigns
- We don't yet track which campaign led to each sign-up
- **Future Enhancement**: Add campaign attribution tracking

---

## Main Dashboard Design (UPDATED)

### Section 1: Campaign Type Overview

```
┌─────────────────────────────────────────────────────────────┐
│  MULTI-CHANNEL CAMPAIGN OVERVIEW                             │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   📧 EMAIL   │  📱 TEXT     │  📬 MAILER   │  📄 LETTER     │
│              │              │              │                │
│  69 campaigns│  TBD         │  TBD         │  TBD           │
│  50K reached │  TBD reached │  TBD reached │  TBD reached   │
│  3.5K opened │  TBD deliv.  │  TBD deliv.  │  TBD deliv.    │
│              │              │              │                │
│  View → │  View →     │  View →     │  View →        │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

### Section 2: Program Conversions (NEW)

```
┌─────────────────────────────────────────────────────────────┐
│  PROGRAM APPLICANTS & CONVERSIONS                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Total Applicants: 155 sign-ups                             │
│  Overall Conversion Rate: 0.17%                              │
│                                                              │
│  Conversion by Channel:                                      │
│  ├─ Email: 75 applicants (est.)                             │
│  ├─ Text: 50 applicants (est.)                              │
│  ├─ Mailer: 30 applicants (est.)                            │
│  └─ Letter: TBD                                              │
│                                                              │
│  ℹ️ Note: Campaign attribution coming soon                  │
│                                                              │
│  [View All Applicants →]                                     │
└─────────────────────────────────────────────────────────────┘
```

### Section 3: Conversion Funnel (NEW)

```
┌─────────────────────────────────────────────────────────────┐
│  CAMPAIGN TO CONVERSION FUNNEL                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Campaigns Created: 69                                       │
│         ↓                                                    │
│  Participants Reached: 90,000                                │
│         ↓                                                    │
│  Engaged: 15,000 (16.7%)                                     │
│         ↓                                                    │
│  Applicants: 155 (0.17%)                                     │
│                                                              │
│  [Funnel Visualization Chart]                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Email Dashboard (UPDATED)

### Existing Components (Keep)
- Campaign statistics cards
- Sent/Opened/Clicked charts
- CTR by campaign
- Engagement by zipcode

### New Components to Add

#### Conversion Section
```
┌─────────────────────────────────────────────────────────────┐
│  EMAIL CAMPAIGN CONVERSIONS                                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Total Applicants (All Campaigns): 155                       │
│                                                              │
│  Estimated from Email Campaigns: 75                          │
│  Email Conversion Rate: 0.15%                                │
│                                                              │
│  ℹ️ Note: Showing total applicants across all campaign      │
│     types. Per-campaign attribution coming soon.             │
│                                                              │
│  Top Converting Campaigns (by opened count):                 │
│  1. Summer Crisis Email - High engagement                    │
│  2. HEAP Awareness Email - Good reach                        │
│  3. Weatherization Email - Targeted                          │
│                                                              │
│  [View Applicant Details →]                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Text Dashboard (UPDATED)

### Participants Section
```
┌─────────────────────────────────────────────────────────────┐
│  TEXT CAMPAIGN PARTICIPANTS                                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Total Reached: 25,000 phone numbers                         │
│  Delivered: 24,500 (98%)                                     │
│  Read: 12,250 (50% of delivered)                             │
│  Replied: 1,225 (5% of delivered)                            │
│  Opted Out: 125 (0.5%)                                       │
│  Failed: 500 (2%)                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Conversions Section (NEW)
```
┌─────────────────────────────────────────────────────────────┐
│  TEXT CAMPAIGN CONVERSIONS                                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Total Applicants (All Campaigns): 155                       │
│                                                              │
│  Estimated from Text Campaigns: 50                           │
│  Text Conversion Rate: 0.20%                                 │
│                                                              │
│  ℹ️ Note: Showing total applicants. Per-campaign            │
│     attribution will enable precise tracking.                │
│                                                              │
│  Conversion Funnel:                                          │
│  25,000 reached → 12,250 read → 1,225 replied → 50 applied  │
│                                                              │
│  [View Applicant Details →]                                  │
└─────────────────────────────────────────────────────────────┘
```

### Charts
1. Messages sent by campaign (bar chart)
2. Delivery success vs failed (stacked bar)
3. Engagement funnel: delivered → read → replied (funnel chart)
4. Opt-out trends over time (line chart)
5. **NEW**: Conversion funnel visualization

---

## Data Service Updates (CORRECTED)

```python
# app/services/campaign_data_service.py

class CampaignDataService:
    """
    Unified data access for campaigns, participants, and applicants
    """

    def __init__(self):
        env = EnvVars()
        mongo_uri = env.get_env('MONGO_URI', 'mongodb://localhost:27017')
        self.client = MongoClient(mongo_uri)

        # Databases
        self.email_db = self.client['emailoctopus_db']
        self.empower_db = self.client['empowersaves_development_db']

    # ========================================
    # PARTICIPANT METHODS (Campaign Reach)
    # ========================================

    def get_email_participants_count(self) -> int:
        """Count participants contacted via email campaigns"""
        return self.email_db.participants.count_documents({
            'email_address': {'$ne': None}
        })

    def get_text_participants_count(self) -> int:
        """Count participants contacted via text campaigns"""
        return self.empower_db.participants.count_documents({
            'phone_number': {'$ne': None}
        })

    def get_email_participants_stats(self) -> Dict[str, int]:
        """Get email participant engagement statistics"""
        pipeline = [
            {'$match': {'email_address': {'$ne': None}}},
            {'$unwind': '$engagements'},
            {'$group': {
                '_id': None,
                'total': {'$sum': 1},
                'opened': {'$sum': {'$cond': ['$engagements.opened', 1, 0]}},
                'clicked': {'$sum': {'$cond': ['$engagements.clicked', 1, 0]}},
                'bounced': {'$sum': {'$cond': ['$engagements.bounced', 1, 0]}},
            }}
        ]
        result = list(self.email_db.participants.aggregate(pipeline))
        return result[0] if result else {}

    def get_text_participants_stats(self) -> Dict[str, int]:
        """Get text participant engagement statistics"""
        pipeline = [
            {'$match': {'phone_number': {'$ne': None}}},
            {'$unwind': '$engagements'},
            {'$group': {
                '_id': None,
                'total': {'$sum': 1},
                'sent': {'$sum': '$engagements.messages_sent'},
                'delivered': {'$sum': '$engagements.messages_delivered'},
                'read': {'$sum': '$engagements.messages_read'},
                'failed': {'$sum': '$engagements.messages_failed'},
                'opted_out': {'$sum': {'$cond': ['$engagements.opted_out', 1, 0]}},
            }}
        ]
        result = list(self.empower_db.participants.aggregate(pipeline))
        return result[0] if result else {}

    # ========================================
    # APPLICANT METHODS (Conversions)
    # ========================================

    def get_total_applicants_count(self) -> int:
        """Count total applicants across all campaigns"""
        return self.empower_db.applicants.count_documents({})

    def get_applicants_by_county(self) -> List[Dict]:
        """Get applicant counts grouped by county"""
        pipeline = [
            {'$group': {
                '_id': '$county',
                'count': {'$sum': 1}
            }},
            {'$sort': {'count': -1}}
        ]
        return list(self.empower_db.applicants.aggregate(pipeline))

    def get_applicants_by_zip(self, limit: int = 20) -> List[Dict]:
        """Get applicant counts grouped by ZIP code"""
        pipeline = [
            {'$group': {
                '_id': '$zip_code',
                'count': {'$sum': 1}
            }},
            {'$sort': {'count': -1}},
            {'$limit': limit}
        ]
        return list(self.empower_db.applicants.aggregate(pipeline))

    def get_recent_applicants(self, limit: int = 10) -> List[Dict]:
        """Get most recent applicants"""
        return list(self.empower_db.applicants.find(
            {},
            {
                'first_name': 1,
                'last_name': 1,
                'email': 1,
                'city': 1,
                'zip_code': 1,
                'created_at': 1,
                '_id': 0
            }
        ).sort('created_at', -1).limit(limit))

    # ========================================
    # CONVERSION METRICS (Cross-Collection)
    # ========================================

    def get_overall_conversion_stats(self) -> Dict[str, Any]:
        """Calculate overall conversion statistics"""
        # Total participants (all channels)
        email_participants = self.get_email_participants_count()
        text_participants = self.get_text_participants_count()
        total_participants = email_participants + text_participants

        # Total applicants
        total_applicants = self.get_total_applicants_count()

        # Calculate conversion rate
        conversion_rate = 0.0
        if total_participants > 0:
            conversion_rate = (total_applicants / total_participants) * 100

        return {
            'participants': {
                'email': email_participants,
                'text': text_participants,
                'total': total_participants
            },
            'applicants': {
                'total': total_applicants
            },
            'conversion': {
                'rate': round(conversion_rate, 2),
                'ratio': f"{total_applicants}/{total_participants}"
            }
        }

    def get_email_conversion_estimate(self) -> Dict[str, Any]:
        """
        Estimate email campaign conversions
        NOTE: This is an estimate until we add campaign attribution
        """
        email_participants = self.get_email_participants_count()
        total_applicants = self.get_total_applicants_count()
        total_participants = email_participants + self.get_text_participants_count()

        # Proportional estimate
        estimated_email_applicants = 0
        if total_participants > 0:
            proportion = email_participants / total_participants
            estimated_email_applicants = int(total_applicants * proportion)

        conversion_rate = 0.0
        if email_participants > 0:
            conversion_rate = (estimated_email_applicants / email_participants) * 100

        return {
            'participants': email_participants,
            'estimated_applicants': estimated_email_applicants,
            'conversion_rate': round(conversion_rate, 2),
            'note': 'Estimate based on proportional distribution. Add campaign attribution for precise tracking.'
        }

    def get_text_conversion_estimate(self) -> Dict[str, Any]:
        """
        Estimate text campaign conversions
        NOTE: This is an estimate until we add campaign attribution
        """
        text_participants = self.get_text_participants_count()
        total_applicants = self.get_total_applicants_count()
        total_participants = self.get_email_participants_count() + text_participants

        # Proportional estimate
        estimated_text_applicants = 0
        if total_participants > 0:
            proportion = text_participants / total_participants
            estimated_text_applicants = int(total_applicants * proportion)

        conversion_rate = 0.0
        if text_participants > 0:
            conversion_rate = (estimated_text_applicants / text_participants) * 100

        return {
            'participants': text_participants,
            'estimated_applicants': estimated_text_applicants,
            'conversion_rate': round(conversion_rate, 2),
            'note': 'Estimate based on proportional distribution. Add campaign attribution for precise tracking.'
        }
```

---

## Future Enhancement: Campaign Attribution

### Goal
Track which campaign led to each applicant sign-up

### Implementation Plan

**Step 1**: Add fields to Applicant model
```python
class Applicant(BaseModel):
    # ... existing fields ...

    # NEW: Campaign attribution
    source_campaign_id: Optional[str] = None
    source_campaign_type: Optional[Literal["email", "text", "mailer", "letter"]] = None
    referral_code: Optional[str] = None  # Unique tracking code
    participant_ref: Optional[str] = None  # Link to participant.contact_id
```

**Step 2**: Add tracking codes to campaigns
- Email: Unique URLs with tracking parameters
- Text: Unique response codes or links
- Mailer: Unique QR codes or promo codes
- Letter: Unique reference numbers

**Step 3**: Capture attribution on sign-up form
- Add hidden field for tracking code
- Store campaign source when form submitted

**Step 4**: Update analytics
- Precise per-campaign conversion tracking
- Remove "estimated" labels
- Enable A/B testing and optimization

---

## Key Metrics Summary

### Per Campaign Type

**Email Campaigns**:
- Participants reached (sent count)
- Engagement rate (opened/sent)
- Click-through rate (clicked/opened)
- Estimated applicants (until attribution added)

**Text Campaigns**:
- Participants reached (sent count)
- Delivery rate (delivered/sent)
- Read rate (read/delivered)
- Reply rate (replied/delivered)
- Opt-out rate
- Estimated applicants (until attribution added)

**All Campaigns**:
- Total applicants (actual sign-ups)
- Overall conversion rate
- Conversion funnel visualization

---

## Implementation Priority (UPDATED)

### Phase 1: Main Dashboard
1. Campaign type overview cards
2. **NEW**: Program conversions section
3. **NEW**: Conversion funnel visualization
4. Cross-channel comparison charts
5. Navigation to type dashboards

### Phase 2: Text Dashboard
1. Participant metrics (reach, delivery, engagement)
2. **NEW**: Conversion section with estimates
3. **NEW**: Funnel visualization (reached → engaged → applied)
4. Charts and visualizations

### Phase 3: Enhanced Email Dashboard
1. Keep existing functionality
2. **NEW**: Add conversion section
3. **NEW**: Add funnel visualization
4. Link to applicant details

### Phase 4: Future Enhancements
1. Campaign attribution system
2. Precise conversion tracking
3. A/B testing capabilities
4. Mailer/Letter dashboards

---

## Success Criteria (UPDATED)

✅ All dashboards show both participants AND applicants
✅ Conversion funnel visualized clearly
✅ Users understand difference between reach and conversions
✅ Estimated conversions shown with disclaimer
✅ Path forward for campaign attribution documented
✅ System extensible for future attribution tracking

---

**Status**: ✅ Design Updated with Corrected Data Model
**Next Steps**: Review updated design, approve Phase 1 implementation
