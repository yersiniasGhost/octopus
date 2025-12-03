# Data Model Clarification - Participants vs Applicants
**Date**: November 5, 2025
**Status**: ✅ Clarified

## Critical Distinction

### Participants Collection
**Purpose**: People who were **contacted/approached** by campaigns

**Usage**:
- Email campaigns → participants with `email_address` populated
- Text campaigns → participants with `phone_number` populated
- Mailer campaigns → participants with mailing address
- Letter campaigns → participants with mailing address

**What it tracks**:
- Who was contacted
- Engagement metrics (opened, clicked, delivered, bounced, etc.)
- Contact information (email or phone)
- Campaign-specific engagement data

**Key Fields**:
```python
class Participant(BaseModel):
    contact_id: str  # Email or phone number
    email_address: Optional[str]  # For email campaigns
    phone_number: Optional[str]   # For text campaigns
    status: str  # SUBSCRIBED, OPTED_OUT, etc.

    # Multi-campaign engagement tracking
    engagements: List[Union[ParticipantEngagement, TextEngagement]]

    # References to other data
    residence_ref: Optional[ResidenceReference]
    demographic_ref: Optional[DemographicReference]
```

---

### Applicants Collection
**Purpose**: People who actually **signed up/applied** for the program

**Usage**:
- Any campaign can lead to applicants
- Web form submissions
- Program enrollments
- Actual conversions from marketing campaigns

**What it tracks**:
- Who signed up for the program
- Complete application data
- Matching to residence and demographic databases
- Entry/form submission details

**Key Fields**:
```python
class Applicant(BaseModel):
    entry_id: str  # Unique form submission ID
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str]

    # Full address information
    address: str
    city: str
    zip_code: str
    county: Optional[str]

    # Matching information
    match_info: ApplicantMatchInfo
    residence_ref: Optional[ResidenceReference]
    demographic_ref: Optional[DemographicReference]
```

---

## Campaign Conversion Funnel

```
┌─────────────────────────────────────────────────────────────┐
│                    CAMPAIGN CREATED                          │
│              (Email, Text, Mailer, Letter)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  PARTICIPANTS (Contacted)                    │
│  - Email: 10,000 emails sent → 10,000 participants          │
│  - Text: 5,000 texts sent → 5,000 participants              │
│  - Mailer: 3,000 mailers sent → 3,000 participants          │
│  - Letter: 1,000 letters sent → 1,000 participants          │
│                                                              │
│  Total Reach: 19,000 participants                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    (Some people engage)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   APPLICANTS (Converted)                     │
│  - 150 people signed up via web form                        │
│  - Came from any/all campaigns                              │
│  - Actual program enrollments                               │
│                                                              │
│  Conversion Rate: 150/19,000 = 0.79%                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Dashboard Metrics by Collection

### Participants Metrics (Campaign Reach)
**Email Campaign Dashboard**:
- Participants contacted (sent count)
- Engagement: opened, clicked, bounced
- Unsubscribed count
- Click-through rate

**Text Campaign Dashboard**:
- Participants contacted (sent count)
- Engagement: delivered, read, replied
- Opt-outs
- Failed deliveries

**Mailer Campaign Dashboard** (Future):
- Participants contacted (mailed count)
- Delivered estimate
- Returned mail count

**Letter Campaign Dashboard** (Future):
- Participants contacted (mailed count)
- Delivery confirmations
- Returned mail count

### Applicants Metrics (Conversions)
**All Dashboards Should Show**:
- Total applicants (program sign-ups)
- Applicants by campaign source (if trackable)
- Conversion rate (applicants / participants)
- Application completion rate

---

## Key Metrics to Track

### Campaign Performance
```python
# Per campaign
campaign_stats = {
    'participants': {
        'total_contacted': 10000,
        'engaged': 3500,  # opened/read/delivered
        'clicked': 250,
        'bounced': 50,
        'opted_out': 12
    },
    'applicants': {
        'total_signed_up': 15,  # People who converted
        'conversion_rate': 0.15  # 15/10000 = 0.15%
    }
}
```

### Cross-Channel Performance
```python
# Across all campaigns
all_campaigns_stats = {
    'email': {
        'participants': 50000,
        'applicants': 75,
        'conversion_rate': 0.15
    },
    'text': {
        'participants': 25000,
        'applicants': 50,
        'conversion_rate': 0.20
    },
    'mailer': {
        'participants': 10000,
        'applicants': 30,
        'conversion_rate': 0.30
    },
    'letter': {
        'participants': 5000,
        'applicants': 25,
        'conversion_rate': 0.50
    }
}
```

---

## Database Queries for Dashboards

### Get Campaign Participants
```python
# Get all participants for a specific campaign
participants = db.participants.find({
    'engagements.campaign_id': campaign_id
})

# Count participants by campaign type
email_participants = db.participants.count_documents({
    'email_address': {'$ne': None}
})

text_participants = db.participants.count_documents({
    'phone_number': {'$ne': None}
})
```

### Get Campaign Applicants (Conversions)
```python
# Count total applicants (all campaigns)
total_applicants = db.applicants.count_documents({})

# If we track campaign source in applicants (future enhancement):
applicants_from_email = db.applicants.count_documents({
    'source_campaign_type': 'email'
})

# For now, show total applicants as overall conversion metric
```

### Calculate Conversion Rate
```python
# Per campaign
campaign_participants = db.participants.count_documents({
    'engagements.campaign_id': campaign_id
})

# Total applicants (we don't currently track which campaign led to signup)
total_applicants = db.applicants.count_documents({})

# Note: Current limitation - we can't directly attribute applicants to specific campaigns
# This is a future enhancement opportunity
```

---

## Future Enhancement: Campaign Attribution

### Problem
Currently, we can't directly track which campaign caused an applicant to sign up.

### Solution
Add campaign attribution to Applicant model:

```python
class Applicant(BaseModel):
    # ... existing fields ...

    # NEW: Campaign attribution
    source_campaign_id: Optional[str] = None
    source_campaign_type: Optional[str] = None  # email, text, mailer, letter
    referral_code: Optional[str] = None  # If we use unique codes per campaign

    # NEW: Matching to participant record
    participant_ref: Optional[str] = None  # Link to participant.contact_id
```

### Implementation
1. Add unique tracking codes to campaigns (e.g., email links, text messages)
2. Capture tracking code on sign-up form
3. Store campaign attribution in applicant record
4. Enable per-campaign conversion tracking

---

## Updated Dashboard Design Requirements

### All Campaign Dashboards Should Include:

**Participants Section**:
- Total participants contacted
- Engagement metrics (campaign-type specific)
- Reach and engagement rates

**Applicants Section** (NEW):
- Total applicants across all campaigns
- Conversion funnel visualization
- Note: "Currently showing total applicants. Campaign-specific attribution coming soon."

**Conversion Metrics** (NEW):
- Overall conversion rate (total applicants / total participants across all campaigns)
- Best performing campaign types
- Conversion trends over time

---

## Corrected Collections Usage

### emailoctopus_db
```yaml
campaigns:
  - campaign_type: "email"
  - Statistics include participant engagement

participants:
  - People contacted via email campaigns
  - email_address populated
  - Engagement tracking (opened, clicked, etc.)
```

### empowersaves_development_db
```yaml
campaigns:
  - campaign_type: "text" | "mailer" | "letter"
  - Statistics include participant engagement

participants:
  - People contacted via text/mailer/letter campaigns
  - phone_number or address populated
  - Engagement tracking (delivered, read, etc.)

applicants:
  - People who signed up for the program
  - From ANY campaign type
  - Full application data
  - NOT campaign-specific (yet)
```

---

## Impact on Dashboard Design

### Main Dashboard Updates

**Campaign Overview Cards** should show:
```
┌──────────────────────────────────────┐
│  EMAIL CAMPAIGNS                     │
│  69 campaigns                        │
│  50,000 participants contacted       │
│  3,500 opened (7%)                   │
│  View Dashboard →                    │
└──────────────────────────────────────┘
```

**Add New Section: Overall Conversions**
```
┌──────────────────────────────────────┐
│  TOTAL PROGRAM APPLICANTS            │
│  155 applicants signed up            │
│  From all campaign types             │
│  0.17% overall conversion rate       │
│  View Applicants →                   │
└──────────────────────────────────────┘
```

### Individual Campaign Dashboards

**Add Conversion Section**:
```
┌──────────────────────────────────────┐
│  CAMPAIGN CONVERSIONS                │
│  ℹ️ Currently showing total          │
│     applicants across all campaigns  │
│                                      │
│  📊 Total Applicants: 155            │
│  📈 Overall Rate: 0.17%              │
│                                      │
│  Coming Soon: Per-campaign tracking  │
└──────────────────────────────────────┘
```

---

## Terminology Guide

| Term | Meaning | Collection | Example |
|------|---------|------------|---------|
| **Participant** | Person contacted by campaign | `participants` | Email sent to john@example.com |
| **Applicant** | Person who signed up for program | `applicants` | John Doe filled out application form |
| **Engagement** | Interaction with campaign | `participants.engagements` | Email opened, link clicked |
| **Conversion** | Participant → Applicant | Cross-collection | Recipient became applicant |
| **Reach** | Total participants contacted | `participants` count | Sent to 10,000 people |
| **Response Rate** | Engaged / Contacted | Calculated | 35% opened email |
| **Conversion Rate** | Applicants / Participants | Cross-collection calc | 0.15% became applicants |

---

## Summary

✅ **Participants** = People contacted by campaigns (outreach/marketing)
✅ **Applicants** = People who signed up for program (conversions)
✅ **All campaign types** use both collections
✅ **Current limitation**: Can't directly attribute applicants to specific campaigns
🔜 **Future enhancement**: Add campaign attribution to applicant model

This clarification significantly impacts dashboard metrics and design!
