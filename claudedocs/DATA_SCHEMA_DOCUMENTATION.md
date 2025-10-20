# Data Schema Documentation

**Project:** Octopus - Energy Campaign Analytics Platform
**Generated:** 2025-10-20
**Purpose:** Comprehensive documentation of MongoDB models and CSV export data structures

---

## Table of Contents

1. [Overview](#overview)
2. [MongoDB Collections](#mongodb-collections)
   - [Campaigns](#campaigns-collection)
   - [Participants](#participants-collection)
   - [Parcels](#parcels-collection)
   - [Meter Data](#meter-data-collection)
   - [County Residential Data](#county-residential-data-collection)
   - [County Thermal Loads](#county-thermal-loads-collection)
   - [County Gas Data](#county-gas-data-collection)
   - [County Electrical Data](#county-electrical-data-collection)
   - [County Demographic Data](#county-demographic-data-collection)
3. [CSV Export Formats](#csv-export-formats)
4. [Data Relationships](#data-relationships)
5. [Field Definitions](#field-definitions)

---

## Overview

The Octopus platform integrates energy usage data with email campaign analytics to track engagement and measure savings potential for energy assistance programs. Data is stored in MongoDB and exported to CSV for analysis.

**Primary Data Sources:**
- EmailOctopus API (campaigns and participant engagement)
- County energy usage databases (residential, electrical, gas)
- Parcel data (property information)
- Demographic data (income, household information)

**Key Workflows:**
1. Campaign data synced from EmailOctopus
2. Participant engagement tracked (opens, clicks, bounces)
3. Energy usage data matched to participants by address/parcel
4. Enriched data exported for analysis

---

## MongoDB Collections

### Campaigns Collection

**Collection Name:** `campaigns`
**Purpose:** Store email campaign metadata and aggregated statistics
**Model:** `src/models/campaign.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "campaign_id": str,                 # EmailOctopus campaign UUID
  "name": str,                        # Campaign name (e.g., "OHCAC_Webinar_20250921")
  "subject": str,                     # Email subject line
  "from_name": str,                   # Sender display name
  "from_email_address": str,          # Sender email address
  "created_at": datetime,             # Campaign creation timestamp
  "sent_at": datetime,                # Campaign sent timestamp
  "status": str,                      # Campaign status: DRAFT, SENT, etc.
  "to_lists": [str],                  # List of EmailOctopus list IDs
  "statistics": {
    "sent": {"unique": int, "total": int},
    "opened": {"unique": int, "total": int},
    "clicked": {"unique": int, "total": int},
    "bounced": {"unique": int, "total": int},
    "complained": {"unique": int, "total": int},
    "unsubscribed": {"unique": int, "total": int}
  },
  "synced_at": datetime               # Last sync with EmailOctopus
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `campaign_id` | str | Unique UUID from EmailOctopus | `"297b7b28-9742-11f0-ae1b-d73f90836e3d"` |
| `name` | str | Human-readable campaign name | `"OHCAC_Webinar_20250921"` |
| `status` | str | Campaign state | `"SENT"`, `"DRAFT"` |
| `statistics.opened.unique` | int | Unique recipients who opened | `150` |
| `sent_at` | datetime | When campaign was sent | `2025-09-21T14:30:00Z` |

---

### Participants Collection

**Collection Name:** `participants`
**Purpose:** Store individual campaign recipient data and engagement tracking
**Model:** `src/models/participant.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "contact_id": str,                  # EmailOctopus contact UUID
  "campaign_id": str,                 # Reference to campaigns collection
  "email_address": str,               # Participant email
  "status": str,                      # SUBSCRIBED, UNSUBSCRIBED, etc.
  "fields": {                         # Custom contact fields
    "FirstName": str,                 # Optional first name
    "LastName": str,                  # Optional last name
    "City": str,                      # City name
    "ZIP": str,                       # Postal code
    "kWh": str,                       # Annual kWh usage
    "Cell": str,                      # Mobile phone number
    "Address": str,                   # Street address
    "annualcost": str,                # Annual energy cost (formatted with $)
    "AnnualSavings": str,             # Potential annual savings (formatted)
    "MonthlyCost": str,               # Monthly energy cost
    "MonthlySaving": str,             # Monthly savings potential
    "DailyCost": str                  # Daily energy cost
  },
  "engagement": {                     # Engagement tracking
    "opened": bool,                   # Email was opened
    "clicked": bool,                  # Link was clicked
    "bounced": bool,                  # Email bounced
    "complained": bool,               # Spam complaint filed
    "unsubscribed": bool              # Recipient unsubscribed
  },
  "synced_at": datetime               # Last sync timestamp
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `email_address` | str | Recipient email address | `"taylor@example.com"` |
| `fields.kWh` | str | Annual electricity usage | `"44498"` |
| `fields.annualcost` | str | Annual energy cost | `"$6,674.70"` |
| `fields.AnnualSavings` | str | Potential savings | `"$2,002.41"` |
| `engagement.opened` | bool | Email opened status | `true` |
| `engagement.clicked` | bool | Link clicked status | `false` |

**Notes:**
- `fields` supports additional custom properties via `extra='allow'`
- Cost/savings fields are formatted strings with currency symbols
- Engagement booleans track cumulative actions (clicked implies opened)

---

### Parcels Collection

**Collection Name:** `parcels`
**Purpose:** Property parcel records for address matching
**Model:** `src/models/parcel.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "parcel_id": int,                   # County parcel identifier
  "street_number": str,               # Street number
  "street_name": str,                 # Street name
  "street_suffix": str,               # Street suffix (ST, AVE, RD, etc.)
  "city": str,                        # City name
  "zip": str,                         # Postal code
  "gas": bool                         # Natural gas service available
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `parcel_id` | int | Unique parcel identifier | `21425802` |
| `street_number` | str | Property street number | `"3244"` |
| `street_name` | str | Street name only | `"MARION MOUNT GILEAD"` |
| `street_suffix` | str | Suffix abbreviation | `"RD"`, `"AVE"`, `"CT"` |
| `gas` | bool | Gas service availability | `true` |

---

### Meter Data Collection

**Collection Name:** `meter_data`
**Purpose:** Raw meter reading data by meter ID
**Model:** `src/models/meter_data.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "meter_id": str,                    # Utility meter identifier
  "meter_data": {                     # Time series meter readings
    "YYYY-MM-DD": float,              # Date: kWh or therms reading
    # ... additional date entries
  }
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `meter_id` | str | Unique meter identifier | `"MTR-123456"` |
| `meter_data` | dict | Date → reading mapping | `{"2024-01-15": 1250.5}` |

**Notes:**
- Dictionary keys are ISO date strings (YYYY-MM-DD)
- Values represent energy consumption for that billing period
- Units vary by meter type (kWh for electric, therms for gas)

---

### County Residential Data Collection

**Collection Name:** `{County}Residential` (e.g., `OttawaResidential`)
**Purpose:** Property characteristics and building information
**Model:** `src/models/county_residential_data.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "parcel_id": str,                   # Reference to parcel
  "parcel_zip": int,                  # Postal code (-1 if unknown)
  "parcel_owner": str,                # Property owner name
  "parcel_city": str,                 # City name
  "address": str,                     # Full street address
  "story_height": float,              # Number of stories
  "construction_quality": str,        # Quality rating
  "age": int,                         # Building age in years (-1 if unknown)
  "heat_type": str,                   # Heating system type
  "air_conditioning": str,            # AC type/presence
  "rooms": float,                     # Total room count (-1 if unknown)
  "bedrooms": float,                  # Bedroom count (-1 if unknown)
  "bathrooms": float,                 # Full bathroom count (-1 if unknown)
  "half_baths": float,                # Half bathroom count (-1 if unknown)
  "garage_size": float,               # Garage capacity (-1 if unknown)
  "living_area_total": float,         # Total square footage
  "rcn": float,                       # Replacement cost new (-1 if unknown)
  "census_tract": str                 # Census tract identifier
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `parcel_id` | str | Links to parcel record | `"21425802C"` |
| `address` | str | Full street address | `"3244 MARION MOUNT GILEAD RD"` |
| `living_area_total` | float | Square footage | `2450.0` |
| `story_height` | float | Number of floors | `2.0` |
| `heat_type` | str | Heating system | `"FORCED AIR"`, `"HEAT PUMP"` |
| `air_conditioning` | str | AC system | `"CENTRAL"`, `"NONE"` |
| `age` | int | Building age in years | `45` |

**Notes:**
- Default value `-1` indicates missing/unknown data
- Default string `"NA"` indicates not available
- `rcn` is Replacement Cost New (insurance/valuation metric)

---

### County Thermal Loads Collection

**Collection Name:** `{County}ThermalLoads` (e.g., `OttawaThermalLoads`)
**Purpose:** Heating/cooling load calculations and regression analysis
**Model:** `src/models/county_loads_data.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "parcel_id": str,                   # Reference to parcel
  "gas_hl_cl_loads": [float],         # Gas heating/cooling load pairs
  "kwh_hl_cl_loads": [float],         # Electric heating/cooling load pairs
  "gas_hl_slope": float,              # Gas heating load slope (-1 if no gas)
  "gas_hl_intercept": float,          # Gas heating load intercept
  "gas_hl_r2": float,                 # Gas heating regression R²
  "kwh_hl_slope": float,              # Electric heating load slope
  "kwh_hl_intercept": float,          # Electric heating load intercept
  "kwh_hl_r2": float,                 # Electric heating regression R²
  "gas_cl_slope": float,              # Gas cooling load slope (-1 if no gas)
  "gas_cl_intercept": float,          # Gas cooling load intercept
  "gas_cl_r2": float,                 # Gas cooling regression R²
  "kwh_cl_slope": float,              # Electric cooling load slope
  "kwh_cl_intercept": float,          # Electric cooling load intercept
  "kwh_cl_r2": float                  # Electric cooling regression R²
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `kwh_hl_slope` | float | Electric heating sensitivity | `15.5` kWh/degree-day |
| `kwh_hl_r2` | float | Heating model fit quality | `0.92` (good fit) |
| `kwh_cl_slope` | float | Electric cooling sensitivity | `22.3` kWh/degree-day |
| `gas_hl_slope` | float | Gas heating sensitivity | `1.8` therms/degree-day |

**Notes:**
- `hl` = heating load, `cl` = cooling load
- Slope represents energy consumption per degree-day
- R² values indicate regression model quality (0-1 scale)
- `-1` values indicate no gas service or insufficient data

---

### County Gas Data Collection

**Collection Name:** `{County}Gas` (e.g., `OttawaGas`)
**Purpose:** Natural gas consumption time series
**Model:** `src/models/county_gas_data.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "parcel_id": str,                   # Reference to parcel
  "time_series_gas": {                # Monthly gas consumption
    "YYYY-MM": float,                 # Month: therms consumed
    # ... additional month entries
  }
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `time_series_gas` | dict | Month → therms mapping | `{"2024-01": 125.5, "2024-02": 108.2}` |

**Notes:**
- Dictionary keys are year-month strings (YYYY-MM)
- Values are natural gas consumption in therms
- Only present for parcels with gas service

---

### County Electrical Data Collection

**Collection Name:** `{County}Electrical` (e.g., `OttawaElectrical`)
**Purpose:** Electricity consumption time series and statistical aggregates
**Model:** `src/models/county_electrical_data.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "parcel_id": str,                   # Reference to parcel
  "time_series_elec": {               # Monthly electricity consumption
    "YYYY-MM": float,                 # Month: kWh consumed
    # ... additional month entries
  },
  "monthly_averages": {               # Average kWh by calendar month
    "1": float,                       # January average
    "2": float,                       # February average
    # ... months 3-12
  },
  "monthly_minimums": {               # Minimum kWh by calendar month
    "1": float,                       # January minimum
    # ... months 2-12
  },
  "monthly_maximums": {               # Maximum kWh by calendar month
    "1": float,                       # January maximum
    # ... months 2-12
  }
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `time_series_elec` | dict | Month → kWh mapping | `{"2024-01": 1250.5}` |
| `monthly_averages` | dict | Calendar month stats | `{"1": 1320.2, "7": 980.5}` |
| `monthly_minimums` | dict | Minimum usage patterns | `{"1": 1100.0, "7": 850.0}` |
| `monthly_maximums` | dict | Maximum usage patterns | `{"1": 1500.0, "7": 1150.0}` |

**Notes:**
- `time_series_elec` keys are YYYY-MM format
- Statistical aggregates use numeric month keys (1-12)
- Aggregates calculated across multiple years of data

---

### County Demographic Data Collection

**Collection Name:** `{County}Demographic` (e.g., `OttawaDemographic`)
**Purpose:** Customer demographics, income data, and energy burden metrics
**Model:** `src/models/county_demographic_data.py`

#### Schema

```python
{
  "_id": ObjectId,                    # MongoDB unique identifier
  "parcel_id": str,                   # Reference to parcel
  "address": str,                     # Street address
  "energy_burden_gas": float,         # Gas cost / income (-1 if no gas)
  "energy_burden_kwh": float,         # Electric cost / income
  "annual_kwh_cost": float,           # Annual electricity cost ($)
  "annual_gas_cost": float,           # Annual gas cost ($, -1 if no gas)
  "total_energy_burden": float,       # Total energy cost / income
  "customer_name": str,               # Customer full name
  "estimated_income": float,          # Midpoint of income range
  "income_level": float,              # Income bracket (0-9 scale, -1 if unknown)
  "md_householdsize": float,          # Household member count
  "email": float,                     # Email availability flag (-1 if none)
  "mobile": int,                      # Mobile phone number (-1 if none)
  "parcel_zip": int,                  # Postal code
  "service_city": str                 # Service area city
}
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `customer_name` | str | Account holder name | `"SEAN D CONWAY"` |
| `estimated_income` | float | Estimated annual income | `45000.0` |
| `income_level` | float | Income bracket rating | `5.0` (middle income) |
| `total_energy_burden` | float | Energy cost as % of income | `0.0642` (6.42%) |
| `annual_kwh_cost` | float | Annual electric bill | `2887.28` |
| `md_householdsize` | float | People in household | `2.0` |
| `mobile` | int | Phone number | `2162253312` |

**Notes:**
- Energy burden calculated as: (annual costs) / (estimated income)
- `income_level` scale: 0=lowest, 9=highest, -1=unknown
- High energy burden (>6%) indicates potential need for assistance
- Mobile phone stored as integer, -1 indicates not available

**Additional Demographic Fields (in raw data, not in model):**
```python
# Fields present in source data but not exposed in Pydantic model:
"age in two-year increments - 1st individual": float  # Primary resident age
"dwelling type": str                                  # S=Single family, etc.
"gender - input individual": str                      # M/F/X
"home length of residence": float                     # Years at address
"home owner / renter": str                            # O=Owner, R=Renter
"marital status": str                                 # S/M/D/W
"number of adults": float                             # Adults in household
"presence of children": str                           # Y/N
```

---

## CSV Export Formats

### Campaign Export Files

**Location:** `data/exports/`
**Naming:** `campaign_{campaign_id}_{campaign_name}.csv`
**Example:** `campaign_297b7b28-9742-11f0-ae1b-d73f90836e3d_OHCAC_Webinar_20250921.csv`

#### Standard Export Schema

```csv
campaign_name,campaign_sent_at,email,first_name,last_name,city,zip,kwh,cell,address,annual_cost,annual_savings,monthly_cost,monthly_saving,daily_cost,opened,clicked,bounced,complained,unsubscribed,status
```

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `campaign_name` | str | Campaign identifier | `"OHCAC_Webinar_20250921"` |
| `campaign_sent_at` | date | Send date | `"2025-09-21"` |
| `email` | str | Recipient email | `"taylor@example.com"` |
| `first_name` | str | First name (often empty) | `""` |
| `last_name` | str | Last name (often empty) | `""` |
| `city` | str | City name | `"MARION"` |
| `zip` | str | Postal code | `"43302"` |
| `kwh` | str | Annual kWh usage | `"44498"` |
| `cell` | str | Mobile phone | `"7402255725"` |
| `address` | str | Street address | `"3244 MARION MOUNT GILEAD RD"` |
| `annual_cost` | str | Annual energy cost | `"$6,674.70"` |
| `annual_savings` | str | Savings potential | `"$2,002.41"` |
| `monthly_cost` | str | Monthly energy cost | `"$556.23"` |
| `monthly_saving` | str | Monthly savings | `"$166.87"` |
| `daily_cost` | str | Daily energy cost | `"$18.29"` |
| `opened` | str | Email opened | `"Yes"` or `"No"` |
| `clicked` | str | Link clicked | `"Yes"` or `"No"` |
| `bounced` | str | Email bounced | `"Yes"` or `"No"` |
| `complained` | str | Spam complaint | `"Yes"` or `"No"` |
| `unsubscribed` | str | Unsubscribed | `"Yes"` or `"No"` |
| `status` | str | Contact status | `"SUBSCRIBED"` |

---

### Enriched Export Files

**Location:** `data/enriched/`
**Naming:** `enriched_campaign_{campaign_id}_{campaign_name}.csv`
**Example:** `enriched_campaign_297b7b28-9742-11f0-ae1b-d73f90836e3d_OHCAC_Webinar_20250921.csv`

#### Enriched Export Schema

```csv
campaign_name,campaign_sent_at,email,first_name,last_name,customer_name,city,zip,kwh,cell,address,annual_savings,monthly_cost,monthly_saving,daily_cost,opened,clicked,bounced,complained,unsubscribed
```

**Differences from Standard Export:**

| Change | Description |
|--------|-------------|
| ➕ `customer_name` | Added from demographic data |
| ➖ `annual_cost` | Removed (only savings retained) |
| ➖ `status` | Removed |
| 🔄 Engagement fields | Changed from "Yes"/"No" to `1`/`0` |

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `customer_name` | str | From demographic collection | `"JUSTIN R MALONE"` |
| `annual_savings` | str | Savings potential | `"$1,890.32"` |
| `opened` | int | Email opened (0/1) | `1` |
| `clicked` | int | Link clicked (0/1) | `0` |

**Notes:**
- Enriched files contain only matched records (participants with demographic data)
- Engagement metrics converted to binary integers for easier analysis
- `customer_name` enables better customer matching and deduplication

---

### Matched/Unmatched Debug Files

**Location:** `data/exports/`
**Naming:** `matched_participants_{timestamp}.csv` or `unmatched_debug_{timestamp}.csv`
**Example:** `matched_participants_20251010_000125.csv`

These files are generated during the enrichment process to track:
- **Matched**: Participants successfully linked to demographic data
- **Unmatched**: Participants without demographic matches (for debugging)

Schema matches enriched export format but includes additional debugging columns.

---

## Data Relationships

### Entity Relationship Diagram

```
Campaigns (1:N) → Participants
                     ↓ (matched by email/address)
                  Demographic Data
                     ↓ (linked by parcel_id)
Parcels (1:1) → Residential Data
            ↓ (1:1 relationships)
            ├─ Thermal Loads
            ├─ Gas Data
            ├─ Electrical Data
            └─ Meter Data (1:N)
```

### Relationship Details

| Parent Collection | Child Collection | Link Field | Cardinality |
|-------------------|------------------|------------|-------------|
| `campaigns` | `participants` | `campaign_id` | 1:N |
| `participants` | `*Demographic` | Email/Address match | N:1 |
| `parcels` | `*Residential` | `parcel_id` | 1:1 |
| `parcels` | `*ThermalLoads` | `parcel_id` | 1:1 |
| `parcels` | `*Gas` | `parcel_id` | 1:1 |
| `parcels` | `*Electrical` | `parcel_id` | 1:1 |
| `*Residential` | `meter_data` | `meter_id` (implicit) | 1:N |

### Matching Logic

**Participant → Demographic Match:**
1. Email address exact match
2. Address fuzzy match (street number + street name)
3. ZIP code validation

**Demographic → Parcel Match:**
1. `parcel_id` field links to `parcels` collection
2. Address fields provide human-readable reference

---

## Field Definitions

### Energy Metrics

| Field | Unit | Description | Typical Range |
|-------|------|-------------|---------------|
| `kWh` | kilowatt-hours | Annual electricity usage | 3,000 - 50,000 |
| `therms` | therms | Natural gas usage | 0 - 2,000 |
| `annual_kwh_cost` | USD | Annual electric bill | $500 - $8,000 |
| `annual_gas_cost` | USD | Annual gas bill | $0 - $2,500 |
| `energy_burden_kwh` | decimal | Electric cost / income | 0.01 - 0.20 |
| `total_energy_burden` | decimal | Total energy cost / income | 0.02 - 0.25 |

**Energy Burden Thresholds:**
- **Low:** < 3% (energy costs manageable)
- **Moderate:** 3-6% (approaching burden threshold)
- **High:** 6-10% (eligible for assistance)
- **Severe:** > 10% (critical need for intervention)

---

### Cost Calculations

**Formulas:**
```python
annual_cost = (annual_kwh * kwh_rate) + (annual_therms * gas_rate)
monthly_cost = annual_cost / 12
daily_cost = annual_cost / 365
annual_savings = annual_cost * efficiency_improvement_pct
monthly_saving = annual_savings / 12
```

**Typical Rates (Ohio):**
- Electricity: $0.12 - $0.15 per kWh
- Natural Gas: $0.60 - $1.20 per therm
- Efficiency Improvement: 25-35% (weatherization programs)

---

### Engagement Metrics

| Metric | Description | Calculation |
|--------|-------------|-------------|
| **Open Rate** | % of recipients who opened email | (unique opens / sent) × 100 |
| **Click Rate** | % of recipients who clicked links | (unique clicks / sent) × 100 |
| **Click-to-Open Rate** | % of opens that resulted in clicks | (unique clicks / unique opens) × 100 |
| **Bounce Rate** | % of undeliverable emails | (bounces / sent) × 100 |
| **Unsubscribe Rate** | % who opted out | (unsubscribes / sent) × 100 |

---

### Property Characteristics

| Field | Description | Common Values |
|-------|-------------|---------------|
| `story_height` | Number of floors | 1.0, 1.5, 2.0, 2.5 |
| `construction_quality` | Build quality rating | "AVERAGE", "GOOD", "EXCELLENT" |
| `heat_type` | Primary heating system | "FORCED AIR", "HEAT PUMP", "ELECTRIC" |
| `air_conditioning` | Cooling system | "CENTRAL", "NONE", "WINDOW UNITS" |
| `living_area_total` | Finished square footage | 800 - 5000 sq ft |

---

### Income Levels

**Income Bracket Scale (0-9):**

| Level | Income Range | Description |
|-------|--------------|-------------|
| 0-1 | < $20,000 | Very low income |
| 2-3 | $20,000 - $35,000 | Low income |
| 4-5 | $35,000 - $50,000 | Lower-middle income |
| 6-7 | $50,000 - $75,000 | Middle income |
| 8-9 | $75,000+ | Upper-middle income |

**Note:** Income levels correlate with energy assistance program eligibility (typically < Level 5)

---

### Status Codes

**Participant Status:**
- `SUBSCRIBED`: Active, can receive emails
- `UNSUBSCRIBED`: Opted out, no emails
- `PENDING`: Confirmation required
- `BOUNCED`: Invalid/inactive address

**Campaign Status:**
- `DRAFT`: Not yet sent
- `SENT`: Delivered to recipients
- `SCHEDULED`: Queued for future send
- `SENDING`: Currently in progress

---

## Data Quality Notes

### Missing Data Conventions

**Numeric Fields:**
- `-1`: Missing/unknown data (default for optional integers/floats)
- `0.0`: Actual zero value (e.g., no gas service)

**String Fields:**
- `"NA"`: Not available
- `""` (empty): Field not populated
- `null`: Explicitly null in database

### Data Validation

**Critical Fields (must be present):**
- Campaign: `campaign_id`, `name`, `status`
- Participant: `contact_id`, `campaign_id`, `email_address`
- Parcel: `parcel_id`, `city`, `zip`

**Calculated Fields (derived):**
- Energy burden metrics (from costs + income)
- Statistical aggregates (from time series)
- Regression parameters (from load analysis)

---

## Usage Examples

### Query Campaign Performance

```python
from pymongo import MongoClient

client = MongoClient()
db = client.octopus

# Get campaign with statistics
campaign = db.campaigns.find_one({"name": "OHCAC_Webinar_20250921"})
print(f"Open rate: {campaign['statistics']['opened']['unique'] / campaign['statistics']['sent']['unique'] * 100:.1f}%")
```

### Find High Energy Burden Participants

```python
# Find participants with >6% energy burden
high_burden = db.OttawaDemographic.find({
    "total_energy_burden": {"$gt": 0.06},
    "email": {"$ne": -1}  # Has email address
})

for customer in high_burden:
    print(f"{customer['customer_name']}: {customer['total_energy_burden']*100:.1f}% burden")
```

### Export Enriched Campaign Data

```python
import csv

campaign = db.campaigns.find_one({"name": "OHCAC_Webinar_20250921"})
participants = db.participants.find({"campaign_id": campaign['campaign_id']})

with open('enriched_export.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[...])
    for p in participants:
        # Match to demographic data
        demo = db.OttawaDemographic.find_one({"email": p['email_address']})
        if demo:
            row = {**p.to_csv_row(), "customer_name": demo['customer_name']}
            writer.writerow(row)
```

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-20 | Initial comprehensive documentation |

---

**Maintained by:** Octopus Development Team
**Contact:** Documentation questions → GitHub Issues
**Related Docs:** See `claudedocs/` for implementation guides
