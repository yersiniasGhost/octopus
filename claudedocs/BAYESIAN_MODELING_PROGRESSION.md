# Bayesian Modeling Progression for Email Engagement

**Project:** Octopus - Email Campaign Engagement Analysis
**Response Variables:**
1. `opened` - Binary (0/1): Whether participant opened email
2. `clicked` - Binary (0/1): Whether participant opened AND clicked (conditional on opening)

**Generated:** 2025-10-20

---

## Table of Contents

1. [Data Overview](#data-overview)
2. [Model Progression Strategy](#model-progression-strategy)
3. [Model 1: Baseline Logistic Regression](#model-1-baseline-logistic-regression)
4. [Model 2: Energy Burden Focus](#model-2-energy-burden-focus)
5. [Model 3: Demographic Expansion](#model-3-demographic-expansion)
6. [Model 4: Property Characteristics](#model-4-property-characteristics)
7. [Model 5: Hierarchical by Campaign](#model-5-hierarchical-by-campaign)
8. [Model 6: Hierarchical by Geography](#model-6-hierarchical-by-geography)
9. [Model 7: Full Hierarchical Model](#model-7-full-hierarchical-model)
10. [Model 8: Interaction Effects](#model-8-interaction-effects)
11. [Model 9: Time Series Features](#model-9-time-series-features)
12. [Model 10: Advanced Spatial Model](#model-10-advanced-spatial-model)
13. [Click Model Variations](#click-model-variations)
14. [Model Comparison Strategy](#model-comparison-strategy)

---

## Data Overview

### Available Predictors by Category

#### **Energy Economics** (Primary Interest)
- `annual_kwh_cost` - Annual electricity bill ($)
- `annual_gas_cost` - Annual gas bill ($, -1 if no gas)
- `total_energy_burden` - Energy cost / income ratio (decimal)
- `energy_burden_kwh` - Electric cost / income ratio
- `energy_burden_gas` - Gas cost / income ratio
- `kwh` - Annual electricity usage (kWh)
- `annual_savings` - Potential savings from weatherization ($)
- `monthly_cost`, `daily_cost` - Cost breakdowns

#### **Demographics**
- `estimated_income` - Household income ($)
- `income_level` - Income bracket (0-9 scale)
- `md_householdsize` - Number of household members
- `customer_name` - Available (enables deduplication)
- `mobile` - Mobile phone availability (int, -1 if none)
- `email` - Email availability flag

#### **Property Characteristics**
- `living_area_total` - Square footage
- `story_height` - Number of floors
- `age` - Building age (years)
- `construction_quality` - Quality rating
- `heat_type` - Heating system type
- `air_conditioning` - AC system type
- `rooms`, `bedrooms`, `bathrooms` - Room counts
- `garage_size` - Garage capacity
- `gas` - Gas service availability (bool)

#### **Geographic**
- `zip` - Postal code
- `city` - City name
- `census_tract` - Census tract identifier
- `parcel_zip` - Parcel zip (may differ from service zip)

#### **Energy Usage Patterns**
- `time_series_elec` - Monthly electricity consumption history
- `monthly_averages` - Average kWh by calendar month
- `kwh_hl_slope` - Heating load sensitivity (kWh/degree-day)
- `kwh_cl_slope` - Cooling load sensitivity (kWh/degree-day)
- `kwh_hl_r2`, `kwh_cl_r2` - Model fit quality
- `gas_hl_slope`, `gas_cl_slope` - Gas load sensitivities

#### **Campaign Context**
- `campaign_name` - Campaign identifier
- `campaign_sent_at` - Send date
- Campaign subject, from_name (from campaigns collection)
- Campaign statistics (aggregate metrics)

#### **Engagement** (Outcomes)
- `opened` - Email opened (binary)
- `clicked` - Link clicked (binary, conditional on opened)
- `bounced`, `complained`, `unsubscribed` - Other engagement

---

## Model Progression Strategy

### Philosophy
1. **Start Simple** - Establish baseline performance
2. **Add Domain Knowledge** - Incorporate energy burden (primary hypothesis)
3. **Expand Predictors** - Add demographics, property, geography
4. **Introduce Hierarchy** - Model campaign and geographic structure
5. **Capture Interactions** - Test effect modification
6. **Add Complexity** - Spatial, temporal, nonlinear effects

### Evaluation Metrics
- **Predictive:** LOO-CV, WAIC, posterior predictive checks
- **Interpretability:** Coefficient credible intervals, effect sizes
- **Practical:** Classification accuracy, AUC-ROC, calibration

### Notation
- `y_open` - Binary opening outcome
- `y_click` - Binary clicking outcome (given opened)
- `X` - Predictor matrix
- Greek letters - Parameters to estimate

---

## Model 1: Baseline Logistic Regression

**Purpose:** Establish baseline with minimal predictors
**Key Question:** What's the baseline open rate? Does it vary by basic energy metrics?

### Model Specification

```python
import pymc as pm
import numpy as np

# Simple logistic regression: Open ~ Energy Cost + Savings
with pm.Model() as model_1_open:
    # Data
    annual_cost = pm.Data("annual_cost", X_annual_cost_scaled)
    annual_savings = pm.Data("annual_savings", X_annual_savings_scaled)

    # Priors
    α = pm.Normal("intercept", mu=0, sigma=2)  # Baseline log-odds
    β_cost = pm.Normal("beta_cost", mu=0, sigma=1)  # Effect of cost
    β_savings = pm.Normal("beta_savings", mu=0, sigma=1)  # Effect of savings

    # Linear model
    logit_p = α + β_cost * annual_cost + β_savings * annual_savings

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_1 = pm.sample(2000, tune=1000, target_accept=0.95)
```

### Predictors
1. `annual_cost` (scaled) - Total annual energy cost
2. `annual_savings` (scaled) - Potential savings

### Hypotheses
- **H1:** Higher energy costs → higher open rate (salience)
- **H2:** Higher savings potential → higher open rate (motivation)

### Prior Justification
- `α ~ Normal(0, 2)`: On logit scale, allows baseline open rates from 2% to 98%
- `β ~ Normal(0, 1)`: On scaled predictors, allows moderate effect sizes

### Interpretation
```python
# Convert log-odds to odds ratios
import arviz as az

# Posterior probability that β_cost > 0
prob_cost_positive = (trace_1.posterior["beta_cost"] > 0).mean()

# Odds ratio for 1 SD increase in cost
or_cost = np.exp(trace_1.posterior["beta_cost"].mean())
```

---

## Model 2: Energy Burden Focus

**Purpose:** Test primary hypothesis about energy burden driving engagement
**Key Question:** Does high energy burden (>6%) predict higher engagement?

### Model Specification

```python
with pm.Model() as model_2_open:
    # Data
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)
    household_size = pm.Data("household_size", X_household_size_scaled)

    # Priors
    α = pm.Normal("intercept", mu=0, sigma=2)
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)  # Expect positive effect
    β_income = pm.Normal("beta_income", mu=0, sigma=1)
    β_hhsize = pm.Normal("beta_hhsize", mu=0, sigma=1)

    # Linear model
    logit_p = (α +
               β_burden * energy_burden +
               β_income * income_level +
               β_hhsize * household_size)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_2 = pm.sample(2000, tune=1000, target_accept=0.95)
```

### Predictors
1. `total_energy_burden` (scaled) - Energy cost as % of income
2. `income_level` (scaled) - Income bracket (0-9)
3. `md_householdsize` (scaled) - Household size

### Hypotheses
- **H1:** Higher energy burden → higher open rate (need for assistance)
- **H2:** Lower income → higher open rate (target population)
- **H3:** Larger households → higher open rate (more impacted by costs)

### Confounders Addressed
- Income effects separated from energy burden
- Household size controls for per-capita energy use

### Prior Justification
- `β_burden ~ Normal(0.5, 1)`: Weakly informative prior favoring positive effect
  - Based on program logic: high-burden households are target audience

---

## Model 3: Demographic Expansion

**Purpose:** Add demographic predictors as potential confounders
**Key Question:** Do demographics explain variance beyond energy burden?

### Model Specification

```python
with pm.Model() as model_3_open:
    # Data (energy + demographics)
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)
    household_size = pm.Data("household_size", X_household_size_scaled)
    has_mobile = pm.Data("has_mobile", X_has_mobile)  # Binary: mobile != -1
    kwh_usage = pm.Data("kwh_usage", X_kwh_scaled)
    has_gas = pm.Data("has_gas", X_has_gas)  # Binary

    # Priors
    α = pm.Normal("intercept", mu=0, sigma=2)
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)
    β_hhsize = pm.Normal("beta_hhsize", mu=0, sigma=1)
    β_mobile = pm.Normal("beta_mobile", mu=0, sigma=1)  # Mobile phone availability
    β_kwh = pm.Normal("beta_kwh", mu=0, sigma=1)  # Usage level
    β_gas = pm.Normal("beta_gas", mu=0, sigma=1)  # Gas service

    # Linear model
    logit_p = (α +
               β_burden * energy_burden +
               β_income * income_level +
               β_hhsize * household_size +
               β_mobile * has_mobile +
               β_kwh * kwh_usage +
               β_gas * has_gas)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_3 = pm.sample(2000, tune=1000, target_accept=0.95)
```

### Predictors Added
4. `has_mobile` - Mobile phone on file (proxy for reachability)
5. `kwh` - Annual electricity usage (size/usage intensity)
6. `gas` - Natural gas service availability

### Hypotheses
- **H4:** Mobile availability → higher engagement (modern communication)
- **H5:** Higher kWh usage → higher engagement (salience)
- **H6:** Gas service → different engagement (dual fuel burden)

### Confounders Addressed
- Mobile availability as proxy for tech-savviness
- Energy usage intensity vs. cost (usage could indicate property size)
- Gas availability controls for heating fuel type

---

## Model 4: Property Characteristics

**Purpose:** Control for property-level confounders
**Key Question:** Does property type/quality affect engagement beyond energy metrics?

### Model Specification

```python
with pm.Model() as model_4_open:
    # Previous predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)
    household_size = pm.Data("household_size", X_household_size_scaled)

    # Property characteristics
    living_area = pm.Data("living_area", X_living_area_scaled)
    building_age = pm.Data("building_age", X_age_scaled)
    story_height = pm.Data("story_height", X_story_scaled)
    heat_type_idx = pm.Data("heat_type_idx", X_heat_type)  # Categorical index

    # Priors
    α = pm.Normal("intercept", mu=0, sigma=2)
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)
    β_hhsize = pm.Normal("beta_hhsize", mu=0, sigma=1)
    β_area = pm.Normal("beta_area", mu=0, sigma=1)
    β_age = pm.Normal("beta_age", mu=0, sigma=1)
    β_story = pm.Normal("beta_story", mu=0, sigma=1)

    # Categorical effects for heat type
    β_heat = pm.Normal("beta_heat", mu=0, sigma=1, shape=n_heat_types)

    # Linear model
    logit_p = (α +
               β_burden * energy_burden +
               β_income * income_level +
               β_hhsize * household_size +
               β_area * living_area +
               β_age * building_age +
               β_story * story_height +
               β_heat[heat_type_idx])

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_4 = pm.sample(2000, tune=1000, target_accept=0.95)
```

### Predictors Added
7. `living_area_total` - Square footage (property size)
8. `age` - Building age (weatherization potential)
9. `story_height` - Number of floors (property type)
10. `heat_type` - Heating system (categorical: forced air, heat pump, electric, etc.)

### Hypotheses
- **H7:** Larger homes → higher engagement (more savings potential)
- **H8:** Older buildings → higher engagement (more weatherization need)
- **H9:** Heat type affects engagement (electric heat more expensive)

### Confounders Addressed
- Property size separates fixed costs from per-unit costs
- Building age proxy for weatherization state
- Heating system type controls for fuel efficiency

---

## Model 5: Hierarchical by Campaign

**Purpose:** Account for campaign-level variation
**Key Question:** Do open rates vary systematically by campaign? Are effects consistent?

### Model Specification

```python
with pm.Model() as model_5_open:
    # Campaign index
    campaign_idx = pm.Data("campaign_idx", X_campaign_idx)  # Integer index 0 to n_campaigns-1

    # Individual-level predictors (centered within campaigns)
    energy_burden = pm.Data("energy_burden", X_energy_burden_centered)
    income_level = pm.Data("income_level", X_income_level_centered)

    # Hyperpriors for campaign-level effects
    μ_α = pm.Normal("mu_alpha", mu=0, sigma=2)  # Global mean log-odds
    σ_α = pm.HalfNormal("sigma_alpha", sigma=1)  # Between-campaign SD

    μ_burden = pm.Normal("mu_beta_burden", mu=0.5, sigma=1)  # Global energy burden effect
    σ_burden = pm.HalfNormal("sigma_beta_burden", sigma=0.5)  # Campaign variation in effect

    # Campaign-specific parameters (non-centered parameterization)
    α_offset = pm.Normal("alpha_offset", mu=0, sigma=1, shape=n_campaigns)
    α = pm.Deterministic("alpha", μ_α + σ_α * α_offset)

    β_burden_offset = pm.Normal("beta_burden_offset", mu=0, sigma=1, shape=n_campaigns)
    β_burden = pm.Deterministic("beta_burden", μ_burden + σ_burden * β_burden_offset)

    # Fixed effects (same across campaigns)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)

    # Linear model with varying intercepts and slopes
    logit_p = (α[campaign_idx] +
               β_burden[campaign_idx] * energy_burden +
               β_income * income_level)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_5 = pm.sample(2000, tune=1000, target_accept=0.95)
```

### Hierarchical Structure
- **Level 1:** Individual participants
- **Level 2:** Campaigns (varying intercepts and energy burden slopes)

### Key Features
- **Varying Intercepts:** Campaigns differ in baseline open rates
- **Varying Slopes:** Energy burden effect differs by campaign
- **Partial Pooling:** Campaigns borrow strength from each other

### Hypotheses
- **H10:** Campaigns have different baseline open rates (subject line, timing effects)
- **H11:** Energy burden effect varies by campaign (messaging effectiveness)

### Benefits
- Accounts for non-independence (participants in same campaign)
- Separates campaign-level from individual-level variation
- Better uncertainty quantification

---

## Model 6: Hierarchical by Geography

**Purpose:** Account for spatial clustering
**Key Question:** Do open rates vary by ZIP code or census tract?

### Model Specification

```python
with pm.Model() as model_6_open:
    # Geographic index
    zip_idx = pm.Data("zip_idx", X_zip_idx)  # Integer index for ZIP codes

    # Individual-level predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)

    # Hyperpriors for ZIP-level effects
    μ_α = pm.Normal("mu_alpha", mu=0, sigma=2)
    σ_α = pm.HalfNormal("sigma_alpha", sigma=1)

    # ZIP-specific intercepts (non-centered)
    α_offset = pm.Normal("alpha_offset", mu=0, sigma=1, shape=n_zips)
    α = pm.Deterministic("alpha", μ_α + σ_α * α_offset)

    # Fixed effects
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)

    # Linear model with ZIP-level intercepts
    logit_p = (α[zip_idx] +
               β_burden * energy_burden +
               β_income * income_level)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_6 = pm.sample(2000, tune=1000, target_accept=0.95)
```

### Hierarchical Structure
- **Level 1:** Individual participants
- **Level 2:** ZIP codes (varying intercepts)

### Key Features
- Geographic clustering accounted for
- Partial pooling across ZIP codes
- Can substitute census tract for finer resolution

### Hypotheses
- **H12:** Engagement varies by geography (local factors, community effects)
- **H13:** Geographic variation not fully explained by demographics

### Extensions
- Add ZIP-level predictors (median income, urbanicity)
- Model spatial correlation between adjacent ZIPs (CAR/SAR models)

---

## Model 7: Full Hierarchical Model

**Purpose:** Combine campaign and geographic hierarchies
**Key Question:** How much variance is campaign vs. geographic vs. individual?

### Model Specification

```python
with pm.Model() as model_7_open:
    # Indices
    campaign_idx = pm.Data("campaign_idx", X_campaign_idx)
    zip_idx = pm.Data("zip_idx", X_zip_idx)

    # Individual-level predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)
    household_size = pm.Data("household_size", X_household_size_scaled)
    living_area = pm.Data("living_area", X_living_area_scaled)

    # Campaign-level hyperpriors
    μ_α_campaign = pm.Normal("mu_alpha_campaign", mu=0, sigma=2)
    σ_α_campaign = pm.HalfNormal("sigma_alpha_campaign", sigma=1)

    α_campaign_offset = pm.Normal("alpha_campaign_offset", mu=0, sigma=1, shape=n_campaigns)
    α_campaign = pm.Deterministic("alpha_campaign", μ_α_campaign + σ_α_campaign * α_campaign_offset)

    # ZIP-level hyperpriors
    μ_α_zip = pm.Normal("mu_alpha_zip", mu=0, sigma=2)
    σ_α_zip = pm.HalfNormal("sigma_alpha_zip", sigma=1)

    α_zip_offset = pm.Normal("alpha_zip_offset", mu=0, sigma=1, shape=n_zips)
    α_zip = pm.Deterministic("alpha_zip", μ_α_zip + σ_α_zip * α_zip_offset)

    # Fixed effects (individual-level)
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)
    β_hhsize = pm.Normal("beta_hhsize", mu=0, sigma=1)
    β_area = pm.Normal("beta_area", mu=0, sigma=1)

    # Linear model with crossed random effects
    logit_p = (α_campaign[campaign_idx] + α_zip[zip_idx] +
               β_burden * energy_burden +
               β_income * income_level +
               β_hhsize * household_size +
               β_area * living_area)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample (may need more tuning)
    trace_7 = pm.sample(2000, tune=1500, target_accept=0.95)
```

### Hierarchical Structure
- **Level 1:** Individual participants
- **Level 2:** Campaigns (varying intercepts) × ZIP codes (varying intercepts)
- **Crossed random effects:** Participants nested within both campaign and ZIP

### Key Features
- Decomposes variance into campaign, geographic, and individual components
- Accounts for multiple sources of non-independence
- Estimates relative importance of clustering factors

### Variance Partition
```python
# Calculate intraclass correlation coefficients
var_campaign = σ_α_campaign**2
var_zip = σ_α_zip**2
var_individual = np.pi**2 / 3  # Logistic distribution variance

icc_campaign = var_campaign / (var_campaign + var_zip + var_individual)
icc_zip = var_zip / (var_campaign + var_zip + var_individual)
```

---

## Model 8: Interaction Effects

**Purpose:** Test effect modification
**Key Question:** Does energy burden effect vary by income level or property type?

### Model Specification

```python
with pm.Model() as model_8_open:
    # Individual-level predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)
    living_area = pm.Data("living_area", X_living_area_scaled)
    building_age = pm.Data("building_age", X_age_scaled)

    # Campaign and ZIP indices
    campaign_idx = pm.Data("campaign_idx", X_campaign_idx)
    zip_idx = pm.Data("zip_idx", X_zip_idx)

    # Hierarchical structure (from Model 7)
    μ_α_campaign = pm.Normal("mu_alpha_campaign", mu=0, sigma=2)
    σ_α_campaign = pm.HalfNormal("sigma_alpha_campaign", sigma=1)
    α_campaign_offset = pm.Normal("alpha_campaign_offset", mu=0, sigma=1, shape=n_campaigns)
    α_campaign = pm.Deterministic("alpha_campaign", μ_α_campaign + σ_α_campaign * α_campaign_offset)

    μ_α_zip = pm.Normal("mu_alpha_zip", mu=0, sigma=2)
    σ_α_zip = pm.HalfNormal("sigma_alpha_zip", sigma=1)
    α_zip_offset = pm.Normal("alpha_zip_offset", mu=0, sigma=1, shape=n_zips)
    α_zip = pm.Deterministic("alpha_zip", μ_α_zip + σ_α_zip * α_zip_offset)

    # Main effects
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)
    β_area = pm.Normal("beta_area", mu=0, sigma=1)
    β_age = pm.Normal("beta_age", mu=0, sigma=1)

    # Interaction terms
    β_burden_income = pm.Normal("beta_burden_income", mu=0, sigma=0.5)  # Burden × Income
    β_burden_area = pm.Normal("beta_burden_area", mu=0, sigma=0.5)  # Burden × Property size
    β_burden_age = pm.Normal("beta_burden_age", mu=0, sigma=0.5)  # Burden × Building age

    # Linear model with interactions
    logit_p = (α_campaign[campaign_idx] + α_zip[zip_idx] +
               β_burden * energy_burden +
               β_income * income_level +
               β_area * living_area +
               β_age * building_age +
               β_burden_income * energy_burden * income_level +
               β_burden_area * energy_burden * living_area +
               β_burden_age * energy_burden * building_age)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_8 = pm.sample(2000, tune=1500, target_accept=0.95)
```

### Interaction Hypotheses
- **H14:** Energy burden effect stronger for lower-income households
  - Low income + high burden = highest engagement
- **H15:** Energy burden effect stronger for larger homes
  - More savings potential from weatherization
- **H16:** Energy burden effect stronger for older buildings
  - More inefficient, more room for improvement

### Interpretation
```python
# Marginal effect of energy burden at different income levels
income_levels = np.linspace(-2, 2, 5)  # Scaled income
for inc in income_levels:
    marginal_effect = β_burden + β_burden_income * inc
    print(f"Income level {inc:.1f}: Burden effect = {marginal_effect.mean():.3f}")
```

---

## Model 9: Time Series Features

**Purpose:** Incorporate seasonal and usage pattern information
**Key Question:** Do heating/cooling sensitivities or usage volatility predict engagement?

### Model Specification

```python
with pm.Model() as model_9_open:
    # Standard predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)

    # Time series features (engineered from monthly data)
    usage_volatility = pm.Data("usage_volatility", X_volatility_scaled)  # CV of monthly kWh
    summer_winter_ratio = pm.Data("sw_ratio", X_sw_ratio_scaled)  # Summer/winter usage
    heating_sensitivity = pm.Data("hl_slope", X_hl_slope_scaled)  # kwh_hl_slope
    cooling_sensitivity = pm.Data("cl_slope", X_cl_slope_scaled)  # kwh_cl_slope
    heating_r2 = pm.Data("hl_r2", X_hl_r2)  # Heating model fit

    # Campaign and ZIP
    campaign_idx = pm.Data("campaign_idx", X_campaign_idx)
    zip_idx = pm.Data("zip_idx", X_zip_idx)

    # Hierarchical structure
    μ_α_campaign = pm.Normal("mu_alpha_campaign", mu=0, sigma=2)
    σ_α_campaign = pm.HalfNormal("sigma_alpha_campaign", sigma=1)
    α_campaign_offset = pm.Normal("alpha_campaign_offset", mu=0, sigma=1, shape=n_campaigns)
    α_campaign = pm.Deterministic("alpha_campaign", μ_α_campaign + σ_α_campaign * α_campaign_offset)

    μ_α_zip = pm.Normal("mu_alpha_zip", mu=0, sigma=2)
    σ_α_zip = pm.HalfNormal("sigma_alpha_zip", sigma=1)
    α_zip_offset = pm.Normal("alpha_zip_offset", mu=0, sigma=1, shape=n_zips)
    α_zip = pm.Deterministic("alpha_zip", μ_α_zip + σ_α_zip * α_zip_offset)

    # Fixed effects
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)
    β_volatility = pm.Normal("beta_volatility", mu=0, sigma=1)
    β_sw_ratio = pm.Normal("beta_sw_ratio", mu=0, sigma=1)
    β_hl_slope = pm.Normal("beta_hl_slope", mu=0, sigma=1)
    β_cl_slope = pm.Normal("beta_cl_slope", mu=0, sigma=1)
    β_hl_r2 = pm.Normal("beta_hl_r2", mu=0, sigma=1)

    # Linear model
    logit_p = (α_campaign[campaign_idx] + α_zip[zip_idx] +
               β_burden * energy_burden +
               β_income * income_level +
               β_volatility * usage_volatility +
               β_sw_ratio * summer_winter_ratio +
               β_hl_slope * heating_sensitivity +
               β_cl_slope * cooling_sensitivity +
               β_hl_r2 * heating_r2)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_9 = pm.sample(2000, tune=1500, target_accept=0.95)
```

### Time Series Features (Feature Engineering Required)

```python
# Calculate from time_series_elec and monthly_averages
def engineer_time_features(time_series_dict, monthly_stats_dict):
    """
    Extract features from electricity time series
    """
    # Usage volatility (coefficient of variation)
    monthly_values = list(time_series_dict.values())
    usage_volatility = np.std(monthly_values) / np.mean(monthly_values)

    # Summer vs winter ratio
    summer_months = [6, 7, 8]  # Keys "6", "7", "8" in monthly_averages
    winter_months = [12, 1, 2]  # Keys "12", "1", "2"
    summer_avg = np.mean([monthly_stats_dict[str(m)] for m in summer_months])
    winter_avg = np.mean([monthly_stats_dict[str(m)] for m in winter_months])
    sw_ratio = summer_avg / winter_avg if winter_avg > 0 else 1.0

    return {
        'usage_volatility': usage_volatility,
        'summer_winter_ratio': sw_ratio
    }
```

### Hypotheses
- **H17:** Higher usage volatility → higher engagement (variable bills, uncertainty)
- **H18:** High summer/winter ratio → cooling-focused messaging resonates
- **H19:** High heating sensitivity → heating-focused messaging resonates
- **H20:** Better model fit (R²) → more confident predictions, targeted messaging

---

## Model 10: Advanced Spatial Model

**Purpose:** Model spatial correlation explicitly
**Key Question:** Are nearby households more similar in engagement than distant ones?

### Model Specification

```python
with pm.Model() as model_10_open:
    # Standard predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)

    # Campaign index
    campaign_idx = pm.Data("campaign_idx", X_campaign_idx)

    # ZIP index for spatial effects
    zip_idx = pm.Data("zip_idx", X_zip_idx)

    # Campaign-level effects
    μ_α_campaign = pm.Normal("mu_alpha_campaign", mu=0, sigma=2)
    σ_α_campaign = pm.HalfNormal("sigma_alpha_campaign", sigma=1)
    α_campaign_offset = pm.Normal("alpha_campaign_offset", mu=0, sigma=1, shape=n_zips)
    α_campaign = pm.Deterministic("alpha_campaign", μ_α_campaign + σ_α_campaign * α_campaign_offset)

    # Spatial random effects (CAR model)
    # W = adjacency matrix for ZIP codes (0/1 for neighbors)
    W = pm.Data("W", adjacency_matrix)

    # CAR prior for spatial correlation
    τ = pm.Gamma("tau", alpha=2, beta=2)  # Precision parameter
    ρ = pm.Uniform("rho", lower=0, upper=1)  # Spatial correlation parameter

    # Spatial random effects (Conditional Autoregressive)
    α_spatial = pm.CAR("alpha_spatial",
                       W=W,
                       alpha=ρ,
                       tau=τ,
                       shape=n_zips)

    # Fixed effects
    β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)

    # Linear model with spatial effects
    logit_p = (α_campaign[campaign_idx] + α_spatial[zip_idx] +
               β_burden * energy_burden +
               β_income * income_level)

    # Likelihood
    y = pm.Bernoulli("y_open", logit_p=logit_p, observed=y_observed)

    # Sample
    trace_10 = pm.sample(2000, tune=2000, target_accept=0.95)
```

### Spatial Features
- **CAR Prior:** Conditional Autoregressive model
  - Nearby ZIPs have correlated random effects
  - `ρ` controls strength of spatial correlation
- **Adjacency Matrix:** Define neighbors (e.g., contiguous ZIPs)

### Hypotheses
- **H21:** Spatial correlation exists beyond measured predictors
- **H22:** Local community effects (word of mouth, local programs)

### Extensions
- Distance-based correlation (decay with distance)
- Spatial interaction with energy burden (effect varies spatially)

---

## Click Model Variations

### Approach 1: Conditional Model (Given Opened)

**Model:** P(Click | Open = 1)

```python
# Filter to only participants who opened
y_click_given_open = y_click[y_open == 1]
X_given_open = X[y_open == 1]

with pm.Model() as model_click_conditional:
    # Same structure as open models, but on filtered data
    energy_burden = pm.Data("energy_burden", X_given_open_burden_scaled)
    # ... other predictors

    # Priors (may differ from open model)
    α = pm.Normal("intercept", mu=0, sigma=2)
    β_burden = pm.Normal("beta_burden", mu=0, sigma=1)  # No directional prior

    # Linear model
    logit_p_click = α + β_burden * energy_burden

    # Likelihood
    y = pm.Bernoulli("y_click", logit_p=logit_p_click, observed=y_click_given_open)

    # Sample
    trace_click = pm.sample(2000, tune=1000, target_accept=0.95)
```

**Interpretation:** What drives clicking among those who opened?

---

### Approach 2: Joint Model (Hurdle/Two-Part)

**Model:** P(Click) = P(Open) × P(Click | Open)

```python
with pm.Model() as model_click_joint:
    # Shared predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)

    # --- Open model ---
    α_open = pm.Normal("alpha_open", mu=0, sigma=2)
    β_burden_open = pm.Normal("beta_burden_open", mu=0.5, sigma=1)
    β_income_open = pm.Normal("beta_income_open", mu=0, sigma=1)

    logit_p_open = α_open + β_burden_open * energy_burden + β_income_open * income_level

    # --- Click model (conditional on opening) ---
    α_click = pm.Normal("alpha_click", mu=0, sigma=2)
    β_burden_click = pm.Normal("beta_burden_click", mu=0, sigma=1)
    β_income_click = pm.Normal("beta_income_click", mu=0, sigma=1)

    logit_p_click = α_click + β_burden_click * energy_burden + β_income_click * income_level

    # --- Likelihoods ---
    # Open outcome
    y_open_obs = pm.Bernoulli("y_open", logit_p=logit_p_open, observed=y_open)

    # Click outcome (only for those who opened)
    # Use pm.math.switch to handle non-openers
    p_click_final = pm.math.switch(
        y_open == 1,
        pm.math.invlogit(logit_p_click),
        0.0  # If didn't open, can't click
    )
    y_click_obs = pm.Bernoulli("y_click", p=p_click_final, observed=y_click)

    # Sample
    trace_joint = pm.sample(2000, tune=1500, target_accept=0.95)
```

**Interpretation:**
- Separate effects for opening vs. clicking
- Test if energy burden matters more for initial interest (open) or deep engagement (click)

---

### Approach 3: Sequential/Ordinal Model

**Model:** Ordered outcomes: 0=Not opened, 1=Opened only, 2=Opened and clicked

```python
with pm.Model() as model_click_ordinal:
    # Predictors
    energy_burden = pm.Data("energy_burden", X_energy_burden_scaled)
    income_level = pm.Data("income_level", X_income_level_scaled)

    # Create ordinal outcome
    # y_ordinal = 0 (not opened), 1 (opened, not clicked), 2 (clicked)

    # Ordered logit cutpoints
    cutpoints = pm.Normal("cutpoints", mu=[0, 2], sigma=1, shape=2,
                         transform=pm.distributions.transforms.ordered)

    # Linear predictor
    β_burden = pm.Normal("beta_burden", mu=0, sigma=1)
    β_income = pm.Normal("beta_income", mu=0, sigma=1)

    η = β_burden * energy_burden + β_income * income_level

    # Ordered logit likelihood
    y = pm.OrderedLogistic("y_ordinal", eta=η, cutpoints=cutpoints, observed=y_ordinal)

    # Sample
    trace_ordinal = pm.sample(2000, tune=1500, target_accept=0.95)
```

**Interpretation:**
- Treats engagement as ordered progression
- Single set of coefficients describes movement through engagement stages

---

## Model Comparison Strategy

### 1. Predictive Performance

```python
import arviz as az

# Fit all models
models = {
    'M1_baseline': model_1_open,
    'M2_burden': model_2_open,
    'M3_demographics': model_3_open,
    'M4_property': model_4_open,
    'M5_campaign_hier': model_5_open,
    'M6_geography_hier': model_6_open,
    'M7_full_hier': model_7_open,
    'M8_interactions': model_8_open,
    'M9_timeseries': model_9_open,
    'M10_spatial': model_10_open
}

traces = {name: pm.sample(model=m, ...) for name, m in models.items()}

# Compare using LOO-CV
comparison = az.compare({name: trace for name, trace in traces.items()})
print(comparison)
```

**Metrics:**
- **LOO:** Leave-One-Out Cross-Validation (lower is better)
- **WAIC:** Widely Applicable Information Criterion (lower is better)
- **ΔWeight:** Model weight in ensemble

---

### 2. Posterior Predictive Checks

```python
with model_7_open:
    ppc = pm.sample_posterior_predictive(trace_7)

# Check calibration
y_pred = ppc.posterior_predictive['y_open'].mean(dim=['chain', 'draw'])
calibration_bins = pd.cut(y_pred, bins=10)
observed_rate = y_observed.groupby(calibration_bins).mean()
predicted_rate = y_pred.groupby(calibration_bins).mean()

# Plot calibration curve
import matplotlib.pyplot as plt
plt.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
plt.scatter(predicted_rate, observed_rate, label='Model')
plt.xlabel('Predicted open rate')
plt.ylabel('Observed open rate')
plt.legend()
```

---

### 3. Effect Size Interpretation

```python
# Convert log-odds to probability scale
def logit_to_prob(logit):
    return 1 / (1 + np.exp(-logit))

# Example: Energy burden effect
β_burden_samples = trace_7.posterior['beta_burden'].values.flatten()

# Marginal effect (low to high burden)
low_burden = -1  # 1 SD below mean
high_burden = 1  # 1 SD above mean

# Holding other predictors at mean (0 on scaled)
α_mean = trace_7.posterior['alpha_campaign'].mean()

p_low = logit_to_prob(α_mean + β_burden_samples * low_burden)
p_high = logit_to_prob(α_mean + β_burden_samples * high_burden)

effect_size = p_high - p_low
print(f"Increase in open prob: {effect_size.mean():.3f} [{np.percentile(effect_size, 2.5):.3f}, {np.percentile(effect_size, 97.5):.3f}]")
```

---

### 4. Model Selection Criteria

**Choose based on:**

1. **Predictive accuracy** (LOO/WAIC)
   - Best for forecasting new campaigns

2. **Interpretability** (coefficient clarity)
   - Best for understanding mechanisms

3. **Domain knowledge** (theoretical support)
   - Best for policy recommendations

4. **Practical constraints** (computational cost)
   - Best for operational deployment

**Recommendation:**
- **Exploratory phase:** Fit all models, compare
- **Inference phase:** Choose best-supported by theory + data
- **Deployment phase:** Balance accuracy vs. simplicity

---

## Next Steps

### Phase 1: Data Preparation
1. Load participant + demographic + property data
2. Engineer time series features
3. Handle missing data (multiple imputation if needed)
4. Create train/test splits (by campaign or time)

### Phase 2: Model Fitting
1. Fit Models 1-4 sequentially (increasing predictors)
2. Compare performance, identify best predictor set
3. Fit Models 5-7 (hierarchical structures)
4. Compare variance decomposition

### Phase 3: Advanced Modeling
1. Test interactions (Model 8)
2. Add time series features (Model 9)
3. Explore spatial correlation (Model 10)

### Phase 4: Inference & Reporting
1. Posterior predictive checks for best model(s)
2. Effect size calculations and interpretation
3. Sensitivity analysis (prior robustness)
4. Generate predictions for new campaigns

### Phase 5: Deployment
1. Retrain on full dataset
2. Create scoring function for new participants
3. Validate on holdout campaign
4. Document for operational use

---

## References

- **PyMC Documentation:** https://docs.pymc.io/
- **Bayesian Data Analysis (Gelman et al.):** Hierarchical modeling theory
- **Statistical Rethinking (McElreath):** Model building philosophy
- **Applied Regression Modeling (Gelman & Hill):** Multilevel/hierarchical models

---

**Document Version:** 1.0
**Author:** Claude Code Analysis
**Last Updated:** 2025-10-20
