# Data Catalog for Causal/Bayesian Modeling

**Generated:** 2025-12-05
**Purpose:** Comprehensive inventory of all data features available for causal model development
**Database:** MongoDB (empower_development)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Data Sources Overview](#data-sources-overview)
3. [Participant & Campaign Data](#participant--campaign-data)
4. [Demographic Data](#demographic-data)
5. [Residential/Property Data](#residentialproperty-data)
6. [Energy Consumption Data](#energy-consumption-data)
7. [Thermal Load Analysis Data](#thermal-load-analysis-data)
8. [Data Quality & Coverage](#data-quality--coverage)
9. [Available Features for Modeling](#available-features-for-modeling)
10. [Recommended Model Features](#recommended-model-features)

---

## Executive Summary

### Data Volume Summary

| Data Category | Collections | Total Records | Key Join Field |
|---------------|-------------|---------------|----------------|
| Campaigns | 1 | 74 | campaign_id |
| Participants | 1 | 133,764 | email_address, campaign_id |
| Demographics | 21 counties | 63,143 | email, parcel_id |
| Residential | 25 counties | 1,106,735 | parcel_id |
| Electrical | 25 counties | 795,991 | parcel_id |
| ThermalLoads | 25 counties | 750,312 | parcel_id |
| Gas | 1 county | 166,846 | parcel_id |

### Join Coverage for Modeling

| Join Path | Records | Coverage |
|-----------|---------|----------|
| Participants (unique emails) | 7,078 | 100% baseline |
| + Demographics (matched) | 7,078 | 100% |
| + Residential (has property data) | 6,981 | 98.6% |
| + ThermalLoads (has energy profile) | 3,078 | 43.5% |

### Outcome Variables (Click Behavior)

| Metric | Total | Rate |
|--------|-------|------|
| Total participant records | 4,778 (enriched CSVs) | - |
| Total clicks | 272 | 5.7% CTR |
| Total campaigns | 68 | - |
| Average open rate | 100% (enriched = openers only) | - |

---

## Data Sources Overview

### Primary Data Flow

```
EmailOctopus API
       ↓
┌─────────────────────────────────────┐
│  campaigns (74 campaigns)           │
│  participants (133,764 records)     │
└─────────────────────────────────────┘
       ↓ match by email
┌─────────────────────────────────────┐
│  {County}Demographic (21 counties)  │
│  - income, energy burden, owner age │
│  - parcel_id for property join      │
└─────────────────────────────────────┘
       ↓ match by parcel_id
┌─────────────────────────────────────┐
│  {County}Residential (25 counties)  │
│  - house age, size, heating type    │
│  - property characteristics         │
└─────────────────────────────────────┘
       ↓ match by parcel_id
┌─────────────────────────────────────┐
│  {County}Electrical/Gas/Thermal     │
│  - consumption time series          │
│  - heating/cooling sensitivity      │
└─────────────────────────────────────┘
```

---

## Participant & Campaign Data

### campaigns Collection

**Records:** 74 campaigns
**Purpose:** Email campaign metadata and aggregate engagement statistics

| Field | Type | Description | Coverage | Sample |
|-------|------|-------------|----------|--------|
| campaign_id | string | EmailOctopus UUID | 100% | `297b7b28-9742-11f0-ae1b...` |
| name | string | Campaign name | 100% | `OHCAC_Webinar_20250921` |
| subject | string | Email subject line | 100% | `Your energy savings...` |
| from_name | string | Sender display name | 100% | `Ohio CAC` |
| status | string | Campaign status | 100% | `SENT` |
| sent_at | datetime | Send timestamp | 100% | `2025-09-21T14:30:00Z` |
| created_at | datetime | Creation timestamp | 100% | `2025-09-20T10:00:00Z` |
| statistics.sent.unique | int | Recipients sent | 100% | `1,200` |
| statistics.opened.unique | int | Unique opens | 100% | `150` |
| statistics.clicked.unique | int | Unique clicks | 100% | `25` |
| statistics.bounced.unique | int | Bounces | 100% | `12` |

**Campaign Naming Convention:** `{ORGANIZATION}_{CAMPAIGN_TYPE}_{DATE}`
- Organizations: OHCAC, MVCAP, IMPACT, COAD
- Types: Webinar, FinalDays, SummerCrisis, Would_$_Per_Month, etc.

### participants Collection

**Records:** 133,764 total (7,078 unique contacts across campaigns)
**Purpose:** Individual recipient engagement tracking per campaign

| Field | Type | Description | Coverage | Sample |
|-------|------|-------------|----------|--------|
| contact_id | string | EmailOctopus contact UUID | 100% | `abc123...` |
| campaign_id | string | FK to campaigns | 100% | `297b7b28...` |
| email_address | string | Recipient email | 100% | `user@example.com` |
| status | string | Contact status | 100% | `SUBSCRIBED` |
| **engagement.opened** | bool | **OUTCOME: Email opened** | 100% | `true` |
| **engagement.clicked** | bool | **OUTCOME: Link clicked** | 100% | `false` |
| engagement.bounced | bool | Email bounced | 100% | `false` |
| engagement.complained | bool | Spam complaint | 100% | `false` |
| engagement.unsubscribed | bool | Unsubscribed | 100% | `false` |
| fields.kWh | string | Annual kWh (from mail merge) | 31% | `44498` |
| fields.annualcost | string | Annual cost (formatted) | 58% | `$6,674.70` |
| fields.AnnualSavings | string | Potential savings | 58% | `$2,002.41` |
| fields.Address | string | Street address | 58% | `221 KENMORE AVE` |
| fields.City | string | City | 77% | `MARION` |
| fields.ZIP | string | Postal code | 81% | `43302` |
| fields.Cell | string | Mobile phone | 48% | `7402255725` |

**Key Modeling Insight:** The `clicked` field is the primary outcome variable for causal models predicting engagement behavior.

---

## Demographic Data

### {County}Demographic Collections (21 counties)

**Total Records:** 63,143 across all counties
**Largest County:** Franklin (27,380)
**Purpose:** Customer demographics, income, and energy burden metrics

| Field | Type | Description | Coverage | Range/Sample |
|-------|------|-------------|----------|--------------|
| parcel_id | string | Property parcel ID | 100% | `30324051` |
| email | string | Customer email | 100% | `user@example.com` |
| customer_name | string | Account holder name | 100% | `SEAN D CONWAY` |
| address | string | Street address | 100% | `10 ABERDEEN CT` |
| parcel_zip | int | Postal code | 100% | `44022` |
| service_city | string | Service area | 100% | `ROCKY RIVER` |
| **estimated_income** | float | **Annual income estimate** | 100% | varies by county |
| **total_energy_burden** | float | **Energy cost / income ratio** | 100% | `0.02 - 0.25` |
| **energy_burden_kwh** | float | **Electric burden component** | 100% | `0.01 - 0.15` |
| **energy_burden_gas** | float | **Gas burden component** | varies | `-1` if no gas |
| **annual_kwh_cost** | float | **Annual electric bill** | 100% | `$0 - $3,065` |
| **annual_gas_cost** | float | **Annual gas bill** | 100% | `$0 - $4,285` |
| **owner_age** | int | **Owner age in years** | **varies** | `18 - 99` |
| md_householdsize | float | Household member count | 100% | `1.0 - 6.0` |
| mobile | int | Phone number | 54% | `2165551234` |
| children_present | string | Children in household | 93% | `Y/N` |
| poverty_level_percent | float | Poverty level % | 93% | varies |
| income_level | float | Income bracket (0-9) | 0% | Not populated |

**Energy Burden Interpretation:**
- Low: < 3% (manageable)
- Moderate: 3-6% (approaching threshold)
- High: 6-10% (eligible for assistance)
- Severe: > 10% (critical need)

**Data Quality Note:** `owner_age` is available in Cuyahoga County but NOT in other counties (0% coverage in match analysis).

---

## Residential/Property Data

### {County}Residential Collections (25 counties)

**Total Records:** 1,106,735
**Largest County:** CuyahogaCountyResidential (353,962)
**Purpose:** Property characteristics and building information

| Field | Type | Description | Coverage | Range/Sample |
|-------|------|-------------|----------|--------------|
| parcel_id | string | Property parcel ID | 100% | `00101001` |
| address | string | Street address | 99% | `11600 HARBORVIEW DR` |
| parcel_city | string | City | 100% | `CLEVELAND` |
| parcel_owner | string | Owner name | 100% | `SMITH, JOHN` |
| parcel_zip | int | Postal code | 99% | `44101` |
| **age** | int | **Year built (or building age)** | 100% | `1900 - 2024` |
| **living_area_total** | float | **Total sq ft** | varies | `800 - 5000` |
| story_height | float | Number of floors | varies | `1.0 - 3.0` |
| **heat_type** | string | **Heating system type** | 100% | `FHA, HWB, EBB, HP` |
| **air_conditioning** | string | **AC present** | 100% | `Y/N/C` |
| construction_quality | string | Build quality | 100% | `A, B, C, D` |
| condition | string | Current condition | 100% | `EXC, GD, AVG, FR, PR` |
| rooms | float | Total rooms | varies | `3 - 15` |
| bedrooms | float | Bedroom count | varies | `1 - 6` |
| bathrooms | float | Full bath count | varies | `1 - 4` |
| half_baths | float | Half bath count | varies | `0 - 2` |
| garage_size | float | Garage capacity | varies | `0 - 3` |
| rcn | float | Replacement cost new | varies | `$50K - $500K` |

**Heat Type Codes:**
- `FHA`: Forced Hot Air
- `HWB`: Hot Water Boiler
- `EBB`: Electric Baseboard
- `HP`: Heat Pump
- `GEO`: Geothermal
- `N/A`: Unknown

**Air Conditioning Codes:**
- `Y`: Yes (any type)
- `N`: No AC
- `C`: Central AC

---

## Energy Consumption Data

### {County}ElectricalDB Collections (25 counties)

**Total Records:** 795,991
**Purpose:** Electricity consumption time series and statistical aggregates

| Field | Type | Description | Coverage | Range/Sample |
|-------|------|-------------|----------|--------------|
| parcel_id | string | Property parcel ID | 100% | `30324051` |
| **time_series_elec** | dict | Monthly kWh by date | 100% | `{"2024-01": 1250.5, ...}` |
| **monthly_averages** | dict | Avg kWh by month (1-12) | 100% | `{"1": 1320, "7": 980}` |
| monthly_minimums | dict | Min kWh by month | 100% | `{"1": 1100, ...}` |
| monthly_maximums | dict | Max kWh by month | 100% | `{"1": 1500, ...}` |

**Derived Features Available:**
- Annual kWh consumption (sum of time_series_elec)
- Seasonal patterns (monthly_averages by season)
- Consumption variability (max - min by month)
- Peak month identification

### {County}GasDB Collections (limited)

**Available:** CuyahogaGasDB (166,846 records)
**Purpose:** Natural gas consumption time series

| Field | Type | Description | Coverage | Range/Sample |
|-------|------|-------------|----------|--------------|
| parcel_id | string | Property parcel ID | 100% | `30324051` |
| time_series_gas | dict | Monthly therms by date | 100% | `{"2024-01": 125.5, ...}` |

---

## Thermal Load Analysis Data

### {County}ThermalLoads Collections (25 counties)

**Total Records:** 750,312
**Purpose:** Heating/cooling load regression analysis for each property

| Field | Type | Description | Coverage | Range/Sample |
|-------|------|-------------|----------|--------------|
| parcel_id | string | Property parcel ID | 100% | `30324051` |
| **kwh_hl_slope** | float | **Electric heating sensitivity** | 99% | `0 - 0.67 kWh/degree-day` |
| **kwh_hl_intercept** | float | **Baseload electric** | 99% | `0 - 4,073 kWh` |
| **kwh_hl_r2** | float | **Heating model fit (R²)** | 99% | `0 - 1.0` |
| **kwh_cl_slope** | float | **Electric cooling sensitivity** | 99% | `0 - 127 kWh/CDD` |
| **kwh_cl_intercept** | float | **Baseload (cooling model)** | 99% | `0 - 3,382 kWh` |
| **kwh_cl_r2** | float | **Cooling model fit (R²)** | 99% | `0 - 1.0` |
| gas_hl_slope | float | Gas heating sensitivity | varies | `-1` if no gas |
| gas_hl_intercept | float | Gas baseload | varies | `0 - 22 therms` |
| gas_hl_r2 | float | Gas heating model fit | varies | `0 - 1.0` |
| gas_cl_slope | float | Gas cooling sensitivity | varies | `0 - 0.005` |
| kwh_hl_cl_loads | list | Load data array (22 points) | 100% | `[...]` |
| gas_hl_cl_loads | list | Load data array (11 points) | 100% | `[...]` |

**Interpretation:**
- **Slope**: Energy sensitivity to temperature (kWh or therms per degree-day)
- **Intercept**: Base energy consumption independent of weather
- **R²**: Model fit quality (>0.7 = good fit)
- High slope + high R² = weather-sensitive building
- High intercept = high baseload (appliances, always-on loads)

---

## Data Quality & Coverage

### Coverage by County (Matched Participants)

| County | Matched | Income | Energy Burden | Owner Age | Notes |
|--------|---------|--------|---------------|-----------|-------|
| Franklin | 1,864 | 100% | 100% | 0% | Largest county |
| Richland | 962 | 100% | 100% | 0% | Good coverage |
| Marion | 941 | 100% | 100% | 0% | Good coverage |
| Lawrence | 648 | 100% | 100% | 0% | Good coverage |
| Allen | 625 | 100% | 100% | 0% | Good coverage |
| Muskingum | 569 | 100% | 100% | 0% | Good coverage |
| Guernsey | 270 | 100% | 100% | 0% | Moderate |
| Belmont | 261 | 100% | 100% | 0% | Moderate |
| Coshocton | 214 | 100% | 100% | 0% | Moderate |
| Athens | 196 | 100% | 100% | 0% | Moderate |
| Fayette | 195 | 100% | 100% | 0% | Moderate |
| Morrow | 152 | 100% | 100% | 0% | Small |
| Harrison | 114 | 100% | 100% | 0% | Small |
| Morgan | 52 | 100% | 100% | 0% | Small |
| Holmes | 14 | 100% | 100% | 0% | Very small |
| Ottawa | 1 | 100% | 0% | 0% | Minimal |

### Feature Availability Summary

| Feature Category | Feature | Availability | Quality |
|-----------------|---------|--------------|---------|
| **Outcome** | clicked (binary) | 100% | Excellent |
| **Outcome** | opened (binary) | 100% | Excellent |
| **Demographics** | income | 100% matched | Good |
| **Demographics** | energy_burden | 100% matched | Good |
| **Demographics** | owner_age | Cuyahoga only | Limited |
| **Demographics** | household_size | 100% matched | Good |
| **Demographics** | children_present | 93% | Good |
| **Property** | house_age (year built) | 98.6% | Excellent |
| **Property** | living_area_total | varies | Moderate |
| **Property** | heat_type | 100% | Excellent |
| **Property** | air_conditioning | 100% | Excellent |
| **Energy** | annual_kwh_cost | 100% | Excellent |
| **Energy** | annual_gas_cost | varies | Moderate |
| **Thermal** | kwh_hl_slope | 43.5% matched | Moderate |
| **Thermal** | kwh_hl_r2 | 43.5% matched | Moderate |
| **Thermal** | kwh_cl_slope | 43.5% matched | Moderate |

---

## Available Features for Modeling

### Predictor Variables (X)

#### Tier 1: High Quality (100% coverage, validated)

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `income` | continuous | $15K - $500K | Estimated annual household income |
| `energy_burden` | continuous | 0.01 - 0.25 | Total energy cost / income |
| `energy_burden_kwh` | continuous | 0.01 - 0.15 | Electric cost / income |
| `annual_kwh_cost` | continuous | $0 - $8,000 | Annual electricity bill |
| `house_age` | continuous | 0 - 200 years | Age of home (current_year - year_built) |

#### Tier 2: Good Coverage (>90%, some missing)

| Variable | Type | Values/Range | Description |
|----------|------|--------------|-------------|
| `household_size` | continuous | 1 - 6 | Number of household members |
| `heat_type` | categorical | FHA, HWB, EBB, HP, etc. | Primary heating system |
| `air_conditioning` | binary | Y/N/C | AC presence |
| `children_present` | binary | Y/N | Children in household |
| `living_area_total` | continuous | 500 - 5,000 sq ft | Home square footage |

#### Tier 3: Limited Coverage (40-90%)

| Variable | Type | Values/Range | Description |
|----------|------|--------------|-------------|
| `kwh_hl_slope` | continuous | 0 - 0.7 | Electric heating sensitivity |
| `kwh_hl_r2` | continuous | 0 - 1.0 | Heating model quality |
| `kwh_cl_slope` | continuous | 0 - 127 | Electric cooling sensitivity |
| `annual_gas_cost` | continuous | $0 - $4,000 | Annual gas bill |
| `mobile` | indicator | present/missing | Has mobile phone |

#### Tier 4: Limited Availability

| Variable | Type | Notes |
|----------|------|-------|
| `owner_age` | continuous | Cuyahoga County only |
| `gas_hl_slope` | continuous | Gas customers only |

### Outcome Variables (Y)

| Variable | Type | Base Rate | Description |
|----------|------|-----------|-------------|
| `clicked` | binary | 5.7% | Clicked link in email |
| `opened` | binary | 100%* | Opened email (*enriched CSVs pre-filtered) |

### Treatment Variables (for future A/B testing)

| Variable | Type | Description |
|----------|------|-------------|
| `campaign_type` | categorical | Webinar, FinalDays, SummerCrisis, etc. |
| `organization` | categorical | OHCAC, MVCAP, IMPACT, COAD |
| `message_framing` | categorical | Cost-focused, savings-focused, urgency |
| `timing` | datetime | Send date/time |

---

## Recommended Model Features

### Model 1: Basic Click Prediction (Current)

**Variables:**
- `income` (standardized)
- `energy_burden` (standardized)
- `house_age` (standardized)

**Coverage:** 98.6% of matched participants
**Status:** Implemented in `click_model_02`

### Model 2: Enhanced Demographics

**Additional Variables:**
- `household_size`
- `children_present`
- `heat_type` (encoded)
- `air_conditioning`
- `living_area_total`

**Coverage:** ~90% of matched participants
**Benefit:** Captures lifestyle and home characteristic effects

### Model 3: Energy Profile Model

**Additional Variables:**
- `kwh_hl_slope` (heating sensitivity)
- `kwh_cl_slope` (cooling sensitivity)
- `kwh_hl_r2` (model quality filter)
- `annual_kwh_cost` / `annual_gas_cost`

**Coverage:** ~43% of matched participants
**Benefit:** Captures energy-conscious behavior indicators

### Model 4: Hierarchical by County

**Structure:**
- County-level random effects
- Pool information across counties
- Estimate county-specific engagement patterns

**Coverage:** 100% of matched participants
**Benefit:** Account for regional variations

### Model 5: Campaign Effect Model

**Additional Variables:**
- `campaign_type` (treatment)
- `organization` (stratification)
- `message_framing` (treatment)
- `timing` (control)

**Coverage:** 100% of participant records
**Benefit:** Estimate causal effects of messaging strategies

---

## Data Access Patterns

### Loading Matched Data

```python
# Python example for loading matched participant data
from pymongo import MongoClient

client = MongoClient('localhost', 27017)
db = client['empower_development']

# Build demographic index by email
demo_by_email = {}
for coll in [c for c in db.list_collection_names() if 'Demographic' in c]:
    for doc in db[coll].find({'email': {'$exists': True}}):
        email = doc.get('email', '').lower().strip()
        if '@' in email:
            demo_by_email[email] = doc

# Build residential index by parcel_id
res_by_parcel = {}
for coll in [c for c in db.list_collection_names() if 'Residential' in c]:
    for doc in db[coll].find({'age': {'$exists': True}}):
        res_by_parcel[doc.get('parcel_id')] = doc

# Match participants
for participant in db.participants.find({'campaign_id': {'$exists': True}}):
    email = participant.get('email_address', '').lower().strip()
    if email in demo_by_email:
        demo = demo_by_email[email]
        parcel_id = demo.get('parcel_id')
        residential = res_by_parcel.get(parcel_id, {})

        # Now have: participant + demo + residential
        # Can build model-ready features
```

### CSV Export Structure

Enriched CSVs in `data/enriched/` contain:
- Campaign metadata: `campaign_name`, `campaign_sent_at`
- Contact info: `email`, `customer_name`, `city`, `zip`
- Energy data: `kwh`, `annual_savings`, `monthly_cost`, etc.
- Engagement: `opened`, `clicked`, `bounced`, etc. (binary 0/1)

---

## Next Steps for Model Development

1. **Data Pipeline Enhancement**
   - Add thermal loads to enriched exports
   - Include residential features (heat_type, AC, living_area)
   - Standardize county name normalization

2. **Feature Engineering**
   - Create `energy_burden_category` (low/moderate/high/severe)
   - Create `house_age_category` (new/mid/old/historic)
   - Create `income_quintile` for stratified analysis

3. **Model Development Priority**
   - Model 2 (Enhanced Demographics): High value, good coverage
   - Model 4 (Hierarchical): Address county heterogeneity
   - Model 5 (Campaign Effects): Requires A/B test data

4. **Data Quality Improvements**
   - Investigate missing owner_age in non-Cuyahoga counties
   - Improve thermal loads match rate (currently 43%)
   - Add gas data for more counties

---

**Document Maintained By:** Claude Code
**Related Documentation:**
- `.claude_docs/DATA_SCHEMA_DOCUMENTATION.md` - Original schema docs
- `.claude_docs/bayesian_model_system.md` - Model architecture
- `src/bayesian_models/click_model_02/` - Current model implementation
