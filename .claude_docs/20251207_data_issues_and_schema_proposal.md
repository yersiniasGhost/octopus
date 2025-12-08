# Data Issues Analysis and Schema Proposal

**Date**: 2025-12-07
**Context**: Preparing for clustering analysis per `docs/CLUSTERING_PROJECT.md`

---

## Executive Summary

The current database schema has structural issues that prevent effective clustering analysis:

1. **Disconnected data populations**: Participants with demographic data have no engagement; participants with engagement have no demographic data
2. **Denormalized participant records**: One record per participant×campaign instead of normalized structure
3. **Low match rates**: Only 3.1% of participant records linked to demographics (11.3% of engaged participants)
4. **Missing participant-level aggregation**: No pre-computed behavioral summaries

---

## Current State Analysis

### Collection Inventory

| Category | Collections | Total Documents |
|----------|-------------|-----------------|
| Core | participants, campaigns | 133,838 |
| Demographic | 21 county collections | 64,143 |
| Residential | 25 county collections | 1,128,213 |
| Other (Electrical, Thermal, etc.) | 61 collections | ~2.5M |

### Participant Data Structure

**Current**: Denormalized (one record per campaign exposure)
```
participants: 133,764 records
├── 12,321 unique contact_ids
├── Structure: one document per (contact_id × campaign)
├── engagement: singular dict (not list)
└── Links: residence_ref, demographic_ref (sparse)
```

**Key Finding**: The `engagements` list in the Pydantic model is not reflected in actual data—each participant document represents a single campaign exposure.

### Reference Linkage Crisis

| Metric | Value |
|--------|-------|
| Total participant records | 133,764 |
| Unique participants | 12,321 |
| With residence_ref | 4,090 records (4,090 unique) |
| Coverage | **3.1% of records, 33.2% of unique participants** |

### The Critical Disconnect

| Population | Participants | Campaigns/Person | Total Clicks | Click Rate |
|------------|--------------|------------------|--------------|------------|
| WITH demographics | 4,090 | 1.0 | **0** | 0.00% |
| WITHOUT demographics | 8,231 | 15.7 | 272 | 0.21% |

**All behavioral signal is in the unlinked population.**

### Root Causes

1. **Zipcode-to-County Mapping Errors** (documented in `data/exports/SUMMARY.txt`)
   - 44903, 44904 → AthensCounty (should be RichlandCounty)
   - 43302, 43315 → AthensCounty (should be MarionCounty)
   - Impact: 2,755 participants incorrectly mapped, 0% match rate

2. **Different Data Pipelines**
   - Linked participants: Likely from a different import process (single campaign, no engagement)
   - Unlinked participants: Email campaigns with full engagement tracking

3. **Missing Address Normalization**
   - CSV addresses not matching county database formats
   - No fuzzy matching or standardization

---

## Campaign Data Analysis

### Campaign Types in Database
```
text: 74 campaigns (100%)
email: 0 campaigns
```

Despite file names suggesting email campaigns (EmailOctopus exports), all 74 campaigns in MongoDB are typed as "text".

### CSV Export Structure
```csv
campaign_name,campaign_sent_at,email,first_name,last_name,city,zip,kwh,cell,
address,annual_cost,annual_savings,monthly_cost,monthly_saving,daily_cost,
opened,clicked,bounced,complained,unsubscribed,status
```

**Available but not in MongoDB**:
- `kwh` (energy usage)
- `annual_cost`, `monthly_cost`, `daily_cost`
- `annual_savings`, `monthly_saving`

These fields from EmailOctopus could enrich demographic data but are stored in CSV only.

---

## Proposed Database Schema

### Design Principles

1. **Normalize participants**: One document per unique person
2. **Separate concerns**: Engagement events as subdocuments or separate collection
3. **Pre-compute aggregations**: Store participant-level behavioral summaries
4. **Explicit linkage**: Clear foreign keys to demographic/residential data
5. **Support clustering workflow**: Schema optimized for the analysis pipeline

### Proposed Collections

#### 1. `persons` (Master Entity)

```javascript
{
  _id: ObjectId,
  person_id: String,              // Canonical identifier (email or phone)

  // Contact methods
  email: String,
  phone: String,

  // Address (normalized)
  address: {
    street: String,               // Normalized street address
    city: String,
    zip: String,
    county: String,               // Resolved county name
    raw_address: String           // Original address for debugging
  },

  // Linkage to county data
  parcel_id: String,              // Foreign key to Residential/Demographic
  county_key: String,             // e.g., "Franklin" for collection lookup
  linkage_method: String,         // "email", "address", "phone", "fuzzy"
  linkage_confidence: Float,      // 0.0-1.0

  // Demographics (denormalized from county collections for query efficiency)
  demographics: {
    estimated_income: Float,
    income_level: Int,            // 0-9
    household_size: Float,
    total_energy_burden: Float,
    annual_kwh_cost: Float,
    participant_age: Int,         // If available
    home_owner: Boolean
  },

  // Residence (denormalized from county collections)
  residence: {
    living_area_sqft: Float,
    year_built: Int,
    house_age: Int,               // Computed: current_year - year_built
    bedrooms: Float,
    bathrooms: Float,
    heat_type: String,
    construction_quality: String
  },

  // Behavioral aggregates (pre-computed)
  engagement_summary: {
    total_campaigns: Int,
    total_opens: Int,
    total_clicks: Int,
    open_rate: Float,
    click_rate: Float,
    ever_opened: Boolean,
    ever_clicked: Boolean,
    first_campaign_date: Date,
    last_campaign_date: Date,
    campaign_types: [String]      // ["email", "text"]
  },

  // Metadata
  created_at: Date,
  updated_at: Date,
  data_quality: {
    has_demographics: Boolean,
    has_residence: Boolean,
    has_engagement: Boolean,
    completeness_score: Float     // 0.0-1.0
  }
}
```

#### 2. `campaign_exposures` (Event Log)

```javascript
{
  _id: ObjectId,
  person_id: String,              // Foreign key to persons
  campaign_id: String,            // Foreign key to campaigns

  // Engagement
  sent_at: Date,
  opened: Boolean,
  opened_at: Date,
  clicked: Boolean,
  clicked_at: Date,
  bounced: Boolean,
  unsubscribed: Boolean,

  // For text campaigns
  messages_sent: Int,
  messages_delivered: Int,
  messages_read: Int,
  replied: Boolean
}
```

#### 3. `campaigns` (Unchanged, but with corrections)

```javascript
{
  _id: ObjectId,
  campaign_id: String,
  name: String,
  campaign_type: String,          // "email" | "text" | "mailer" | "letter"
  target_audience: String,        // "OHCAC", "IMPACT", "MVCAP", "COAD"
  sent_at: Date,

  // Aggregate statistics
  statistics: {
    total_sent: Int,
    total_opened: Int,
    total_clicked: Int,
    open_rate: Float,
    click_rate: Float
  }
}
```

#### 4. County Collections (Keep As-Is)

The `{County}Demographic` and `{County}Residential` collections are well-structured. Keep them but ensure:
- Consistent field naming across counties
- Add indexes on `parcel_id` and `address`

### Indexes

```javascript
// persons collection
db.persons.createIndex({ "person_id": 1 }, { unique: true })
db.persons.createIndex({ "email": 1 })
db.persons.createIndex({ "phone": 1 })
db.persons.createIndex({ "address.zip": 1 })
db.persons.createIndex({ "parcel_id": 1 })
db.persons.createIndex({ "engagement_summary.ever_clicked": 1 })
db.persons.createIndex({ "data_quality.completeness_score": 1 })

// campaign_exposures collection
db.campaign_exposures.createIndex({ "person_id": 1 })
db.campaign_exposures.createIndex({ "campaign_id": 1 })
db.campaign_exposures.createIndex({ "person_id": 1, "campaign_id": 1 }, { unique: true })
db.campaign_exposures.createIndex({ "clicked": 1 })
```

---

## Migration Strategy

### Phase 1: Fix Zipcode Mapping
```
1. Correct zipcode_to_county_cache.json
2. Re-run participant matching
3. Expected improvement: 11% → 60%+ match rate
```

### Phase 2: Create Persons Collection
```
1. Group existing participant records by contact_id
2. Aggregate engagement metrics
3. Attempt demographic linkage for each person
4. Compute data quality scores
```

### Phase 3: Backfill Demographics
```
1. For persons without parcel_id, attempt fuzzy address matching
2. For persons with email, search county demographics for email matches
3. For remaining, use zipcode-based imputation (county averages)
```

### Phase 4: Create Clustering Export View
```javascript
// MongoDB aggregation for clustering-ready data
db.persons.aggregate([
  { $match: {
    "data_quality.has_demographics": true,
    "data_quality.has_engagement": true
  }},
  { $project: {
    person_id: 1,
    county: "$address.county",

    // Clustering features (continuous)
    living_area_sqft: "$residence.living_area_sqft",
    house_age: "$residence.house_age",
    estimated_income: "$demographics.estimated_income",
    total_energy_burden: "$demographics.total_energy_burden",
    household_size: "$demographics.household_size",

    // Clustering features (categorical)
    heat_type: "$residence.heat_type",
    campaign_type_email: { $in: ["email", "$engagement_summary.campaign_types"] },
    campaign_type_text: { $in: ["text", "$engagement_summary.campaign_types"] },

    // Outcome variables (for validation, not clustering)
    total_campaigns: "$engagement_summary.total_campaigns",
    click_rate: "$engagement_summary.click_rate",
    ever_clicked: "$engagement_summary.ever_clicked"
  }}
])
```

---

## Immediate Actions Required

### High Priority (Blocking Clustering)

1. **Fix zipcode mapping** in `data/zipcode_to_county_cache.json`
   - Correct 44903, 44904 → RichlandCounty
   - Correct 43302, 43315 → MarionCounty

2. **Re-run participant matching** to link engaged participants to demographics

3. **Create aggregation script** to produce participant-level CSV with:
   - Demographics from county collections
   - Aggregated engagement metrics
   - Data quality flags

### Medium Priority (Schema Improvement)

4. **Create `persons` collection** with normalized structure
5. **Migrate engagement data** to event log pattern
6. **Add fuzzy address matching** for unlinked participants

### Low Priority (Future Enhancement)

7. **Import CSV fields** (kwh, costs) into demographics
8. **Add participant age** where available in county data
9. **Build real-time aggregation pipeline** for ongoing campaigns

---

## Appendix: Data Quality Metrics

### Current State
| Metric | Value |
|--------|-------|
| Unique participants | 12,321 |
| With any demographic linkage | 4,090 (33.2%) |
| With engagement data | 8,231 (66.8%) |
| With BOTH demographics AND engagement | **~0** |
| Clustering-ready records | **0** |

### Target State (After Fixes)
| Metric | Target |
|--------|--------|
| Demographic linkage | >60% |
| With BOTH demographics AND engagement | >50% |
| Clustering-ready records | >5,000 |

---

## Files Referenced

- `src/models/participant.py` - Current Pydantic model
- `src/models/campaign.py` - Campaign model
- `src/models/county_demographic_data.py` - Demographic schema
- `src/models/county_residential_data.py` - Residential schema
- `src/tools/csv_consolidator.py` - Existing matching logic
- `data/exports/SUMMARY.txt` - Match rate analysis
- `data/zipcode_to_county_cache.json` - Zipcode mapping (contains errors)
