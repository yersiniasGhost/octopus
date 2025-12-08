# Campaign Data Database Schema Proposal

**Date**: 2025-12-07
**Database Name**: `campaign_data`
**Purpose**: Replace poorly-constructed `emailoctopus_db` with a well-designed schema supporting multi-channel campaign analytics

---

## Design Principles

1. **Normalized participants**: One document per unique person (not per campaign exposure)
2. **Denormalized demographics**: Copy all demographic/residential data for each participant (no joins needed)
3. **Unified engagement model**: Standardize engagement across channels as `no_engagement` → `received` → `engaged`
4. **Multi-channel support**: email, text-morning, text-evening, mailers, letters (separate channels)
5. **Analysis-ready**: Schema optimized for the clustering and behavioral analysis pipeline

---

## Engagement Status Mapping

| Channel | Raw Status | Unified Status |
|---------|------------|----------------|
| **Email** | not opened | `no_engagement` |
| **Email** | opened (not clicked) | `received` |
| **Email** | clicked | `engaged` |
| **Text** | sent (not delivered) | `no_engagement` |
| **Text** | delivered/read | `received` |
| **Text** | replied/clicked link | `engaged` |
| **Mailer** | sent | `no_engagement` |
| **Mailer** | delivered (confirmed) | `received` |
| **Mailer** | response received | `engaged` |
| **Letter** | sent | `no_engagement` |
| **Letter** | delivered | `received` |
| **Letter** | response received | `engaged` |

---

## Collections

### 1. `participants` (Master Entity)

One document per unique person, identified by canonical ID (email or phone).

```javascript
{
  _id: ObjectId,

  // === IDENTITY ===
  participant_id: String,           // Canonical: email if available, else phone

  // Contact methods
  email: String,                    // Primary email (nullable)
  phone: String,                    // Primary phone (normalized 10-digit)

  // Normalized address
  address: {
    street: String,                 // Normalized: "123 main st"
    city: String,
    zip: String,                    // 5-digit
    county: String,                 // Resolved: "FranklinCounty"
    raw: String                     // Original for debugging
  },

  // === LINKAGE TO COUNTY DATA ===
  linkage: {
    parcel_id: String,              // FK to county collections (nullable if unmatched)
    county_key: String,             // e.g., "Franklin" for collection lookup
    method: String,                 // "email", "phone", "address_phone", "address_exact", "address_fuzzy", "name_address"
    confidence: Float,              // 0.0-1.0
    matched_at: Date
  },

  // === DEMOGRAPHICS (denormalized from {County}Demographic) ===
  demographics: {
    customer_name: String,
    estimated_income: Float,
    income_level: Int,              // 0-9 scale
    household_size: Float,

    // Energy metrics
    annual_kwh_cost: Float,
    annual_gas_cost: Float,         // -1 if no gas
    total_energy_burden: Float,     // Energy cost / income ratio
    energy_burden_kwh: Float,
    energy_burden_gas: Float,

    // Personal (if available)
    age_bracket: String,            // "25-34", "35-44", etc.
    home_owner: Boolean,            // O=Owner, R=Renter
    dwelling_type: String,          // S=Single family, etc.
    marital_status: String,
    presence_of_children: Boolean,
    number_of_adults: Float
  },

  // === RESIDENCE (denormalized from {County}Residential) ===
  residence: {
    living_area_sqft: Float,
    story_height: Float,
    year_built: Int,                // Actual year (e.g., 1985)
    house_age: Int,                 // Computed: current_year - year_built
    bedrooms: Float,
    bathrooms: Float,
    half_baths: Float,
    rooms_total: Float,

    // Building characteristics
    heat_type: String,              // "FORCED AIR", "HEAT PUMP", etc.
    air_conditioning: String,       // "CENTRAL", "NONE", etc.
    construction_quality: String,   // "AVERAGE", "GOOD", "EXCELLENT"
    garage_size: Float,

    // Property info
    parcel_owner: String,
    census_tract: String,
    rcn: Float                      // Replacement cost new
  },

  // === ENERGY SNAPSHOT (from campaign CSV at time of import) ===
  energy_snapshot: {
    kwh_annual: Float,              // Annual kWh usage
    annual_cost: Float,             // $ - parsed from "$6,674.70"
    annual_savings: Float,          // $ - potential savings
    monthly_cost: Float,
    monthly_saving: Float,
    daily_cost: Float,
    snapshot_date: Date             // When this was captured
  },

  // === ENGAGEMENT SUMMARY (pre-computed aggregations) ===
  engagement_summary: {
    // Totals
    total_campaigns: Int,
    total_exposures: Int,           // Sum across all channels

    // By channel
    by_channel: {
      email: {
        exposures: Int,
        received: Int,              // opened
        engaged: Int                // clicked
      },
      text_morning: {
        exposures: Int,
        received: Int,
        engaged: Int
      },
      text_evening: {
        exposures: Int,
        received: Int,
        engaged: Int
      },
      mailer: {
        exposures: Int,
        received: Int,
        engaged: Int
      },
      letter: {
        exposures: Int,
        received: Int,
        engaged: Int
      }
    },

    // Unified status (highest achieved across all channels)
    unified_status: String,         // "no_engagement", "received", "engaged"

    // Convenience flags
    ever_received: Boolean,         // Any channel: received or engaged
    ever_engaged: Boolean,          // Any channel: engaged

    // Timing
    first_campaign_date: Date,
    last_campaign_date: Date,

    // Rates (computed)
    overall_receive_rate: Float,    // received / total_exposures
    overall_engage_rate: Float      // engaged / total_exposures
  },

  // === DATA QUALITY ===
  data_quality: {
    has_demographics: Boolean,
    has_residence: Boolean,
    has_energy_snapshot: Boolean,
    has_engagement: Boolean,
    completeness_score: Float,      // 0.0-1.0 (% of fields populated)

    // For analysis filtering
    analysis_ready: Boolean         // Has both demographics AND engagement
  },

  // === METADATA ===
  created_at: Date,
  updated_at: Date,
  source_campaigns: [String]        // List of campaign_ids this participant appeared in
}
```

### 2. `campaigns` (Campaign Metadata)

```javascript
{
  _id: ObjectId,
  campaign_id: String,              // UUID from source system

  // Identity
  name: String,                     // "OHCAC_Webinar_20250921"
  agency: String,                   // "OHCAC", "MVCAP", "IMPACT", "COAD"
  channel: String,                  // "email", "text_morning", "text_evening", "mailer", "letter"

  // Content
  subject: String,                  // Email subject line (nullable for non-email)
  message_type: String,             // "webinar", "crisis", "savings", "daily_cost", etc.

  // Timing
  sent_at: Date,

  // Source tracking
  source_system: String,            // "emailoctopus", "text_platform", "mailer_vendor"
  source_file: String,              // CSV filename if imported from file

  // Aggregate statistics
  statistics: {
    total_sent: Int,

    // Raw counts
    opened: Int,                    // Email: opened
    clicked: Int,                   // Email: clicked
    bounced: Int,
    unsubscribed: Int,
    complained: Int,

    // Unified counts
    received: Int,                  // Normalized "received" count
    engaged: Int,                   // Normalized "engaged" count

    // Rates
    receive_rate: Float,            // received / total_sent
    engage_rate: Float              // engaged / total_sent
  },

  created_at: Date,
  synced_at: Date                   // Last sync from source
}
```

### 3. `campaign_exposures` (Event Log)

One document per participant × campaign combination.

```javascript
{
  _id: ObjectId,

  // Foreign keys
  participant_id: String,           // FK to participants.participant_id
  campaign_id: String,              // FK to campaigns.campaign_id

  // Denormalized for query convenience
  agency: String,
  channel: String,
  sent_at: Date,

  // === RAW ENGAGEMENT (channel-specific) ===

  // Email fields
  email_opened: Boolean,
  email_opened_at: Date,
  email_clicked: Boolean,
  email_clicked_at: Date,
  email_bounced: Boolean,
  email_complained: Boolean,
  email_unsubscribed: Boolean,

  // Text fields (nullable for email campaigns)
  text_delivered: Boolean,
  text_read: Boolean,
  text_replied: Boolean,

  // Mailer/Letter fields (nullable for digital campaigns)
  postal_delivered: Boolean,
  postal_response: Boolean,

  // === UNIFIED ENGAGEMENT ===
  unified_status: String,           // "no_engagement", "received", "engaged"

  // === CONTACT INFO AT TIME OF SEND ===
  // (Captures state when campaign was sent, may differ from current participant record)
  contact_snapshot: {
    email: String,
    phone: String,
    address: String,
    city: String,
    zip: String
  },

  // === ENERGY DATA AT TIME OF SEND ===
  // (From CSV import - preserves historical values)
  energy_at_send: {
    kwh: Float,
    annual_cost: Float,
    annual_savings: Float,
    monthly_cost: Float,
    daily_cost: Float
  },

  created_at: Date
}
```

---

## Indexes

```javascript
// === participants ===
db.participants.createIndex({ "participant_id": 1 }, { unique: true })
db.participants.createIndex({ "email": 1 }, { sparse: true })
db.participants.createIndex({ "phone": 1 }, { sparse: true })
db.participants.createIndex({ "address.zip": 1 })
db.participants.createIndex({ "address.county": 1 })
db.participants.createIndex({ "linkage.parcel_id": 1 }, { sparse: true })

// Engagement queries
db.participants.createIndex({ "engagement_summary.unified_status": 1 })
db.participants.createIndex({ "engagement_summary.ever_engaged": 1 })
db.participants.createIndex({ "data_quality.analysis_ready": 1 })

// Demographics queries
db.participants.createIndex({ "demographics.income_level": 1 })
db.participants.createIndex({ "demographics.total_energy_burden": 1 })

// Compound for filtering
db.participants.createIndex({
  "data_quality.analysis_ready": 1,
  "engagement_summary.unified_status": 1
})

// === campaigns ===
db.campaigns.createIndex({ "campaign_id": 1 }, { unique: true })
db.campaigns.createIndex({ "agency": 1 })
db.campaigns.createIndex({ "channel": 1 })
db.campaigns.createIndex({ "sent_at": -1 })
db.campaigns.createIndex({ "agency": 1, "channel": 1, "sent_at": -1 })

// === campaign_exposures ===
db.campaign_exposures.createIndex({ "participant_id": 1 })
db.campaign_exposures.createIndex({ "campaign_id": 1 })
db.campaign_exposures.createIndex(
  { "participant_id": 1, "campaign_id": 1 },
  { unique: true }
)
db.campaign_exposures.createIndex({ "unified_status": 1 })
db.campaign_exposures.createIndex({ "channel": 1, "unified_status": 1 })
db.campaign_exposures.createIndex({ "sent_at": -1 })
```

---

## Migration Strategy

### Phase 1: Create Database and Collections

```javascript
use campaign_data

// Create collections with validation
db.createCollection("participants")
db.createCollection("campaigns")
db.createCollection("campaign_exposures")

// Apply indexes (see above)
```

### Phase 2: Import Campaigns from CSV Files

For each CSV file in `data/exports/`:

1. Parse campaign metadata from filename: `campaign_{uuid}_{name}.csv`
2. Extract agency from name prefix (OHCAC, MVCAP, IMPACT, COAD)
3. Create campaign document
4. Process each row as participant exposure

### Phase 3: Deduplicate Participants

1. Group CSV rows by canonical identifier (email → phone → address)
2. Create one `participants` document per unique person
3. Aggregate engagement across all their campaign exposures
4. Compute `engagement_summary` fields

### Phase 4: Match to County Data

Using existing `ResidenceMatcher` pattern:

1. For each participant with zipcode:
   - Map zipcode → county using `zipcode_to_county_cache.json`
   - Apply 8 matching strategies in priority order
   - On match: copy demographics + residence data

2. Update `data_quality` flags:
   - `has_demographics`: matched to county demographic
   - `has_residence`: matched to county residential
   - `analysis_ready`: has_demographics AND has_engagement

### Phase 5: Compute Engagement Summaries

For each participant:

```javascript
db.campaign_exposures.aggregate([
  { $match: { participant_id: "..." } },
  { $group: {
    _id: "$channel",
    exposures: { $sum: 1 },
    received: { $sum: { $cond: [{ $in: ["$unified_status", ["received", "engaged"]] }, 1, 0] } },
    engaged: { $sum: { $cond: [{ $eq: ["$unified_status", "engaged"] }, 1, 0] } }
  }}
])
```

---

## Analysis Queries

### Query 1: Clustering-Ready Export

```javascript
db.participants.aggregate([
  { $match: { "data_quality.analysis_ready": true } },
  { $project: {
    participant_id: 1,
    county: "$address.county",

    // Demographics (continuous)
    estimated_income: "$demographics.estimated_income",
    income_level: "$demographics.income_level",
    household_size: "$demographics.household_size",
    total_energy_burden: "$demographics.total_energy_burden",

    // Residence (continuous)
    living_area_sqft: "$residence.living_area_sqft",
    house_age: "$residence.house_age",

    // Residence (categorical)
    heat_type: "$residence.heat_type",

    // Engagement (outcome variable)
    unified_status: "$engagement_summary.unified_status",
    ever_engaged: "$engagement_summary.ever_engaged",
    overall_engage_rate: "$engagement_summary.overall_engage_rate"
  }}
])
```

### Query 2: Campaign Performance by Agency

```javascript
db.campaigns.aggregate([
  { $group: {
    _id: { agency: "$agency", channel: "$channel" },
    campaigns: { $sum: 1 },
    total_sent: { $sum: "$statistics.total_sent" },
    total_engaged: { $sum: "$statistics.engaged" },
    avg_engage_rate: { $avg: "$statistics.engage_rate" }
  }},
  { $sort: { "_id.agency": 1, "_id.channel": 1 } }
])
```

### Query 3: Engagement by Demographics

```javascript
db.participants.aggregate([
  { $match: { "data_quality.has_demographics": true } },
  { $bucket: {
    groupBy: "$demographics.income_level",
    boundaries: [0, 3, 6, 9, 10],
    output: {
      count: { $sum: 1 },
      engaged_count: { $sum: { $cond: ["$engagement_summary.ever_engaged", 1, 0] } },
      avg_energy_burden: { $avg: "$demographics.total_energy_burden" }
    }
  }}
])
```

### Query 4: Match Rate by County

```javascript
db.participants.aggregate([
  { $group: {
    _id: "$address.county",
    total: { $sum: 1 },
    matched: { $sum: { $cond: ["$data_quality.has_demographics", 1, 0] } },
    with_engagement: { $sum: { $cond: ["$data_quality.has_engagement", 1, 0] } },
    analysis_ready: { $sum: { $cond: ["$data_quality.analysis_ready", 1, 0] } }
  }},
  { $addFields: {
    match_rate: { $divide: ["$matched", "$total"] },
    analysis_ready_rate: { $divide: ["$analysis_ready", "$total"] }
  }},
  { $sort: { total: -1 } }
])
```

---

## Comparison: Old vs. New

| Aspect | `emailoctopus_db` (Old) | `campaign_data` (New) |
|--------|-------------------------|----------------------|
| **Participant structure** | One doc per campaign×participant | One doc per unique person |
| **Demographics** | Sparse `residence_ref`/`demographic_ref` links | Denormalized, copied in full |
| **Engagement** | Channel-specific only | Unified `no_engagement`/`received`/`engaged` |
| **Analysis readiness** | ~0 records with both demographics + engagement | `analysis_ready` flag, expected >50% |
| **Energy data** | Lost after CSV import | Preserved in `energy_snapshot` and `energy_at_send` |
| **Multi-channel** | Email only (plus text labeled as "text") | Explicit: email, text_morning, text_evening, mailer, letter |
| **Aggregations** | None pre-computed | `engagement_summary` with rates, flags |

---

## Files Referenced

- Existing matching code: `scripts/match_participants_optimized.py`
- Rematch tool: `scripts/rematch_participants_tool.py`
- Residence matcher: `src/tools/residence_matcher.py`
- Zipcode cache: `data/zipcode_to_county_cache.json`
- CSV exports: `data/exports/campaign_*.csv`

---

## Next Steps

1. **Review and approve** this schema
2. **Create migration script** to populate `campaign_data` from:
   - CSV files in `data/exports/`
   - Existing `emailoctopus_db` participants
   - `empower_development` county collections
3. **Validate** match rates and `analysis_ready` counts
4. **Export** clustering-ready data for analysis
