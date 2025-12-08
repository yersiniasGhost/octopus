# Progressive Causal Models for Energy Campaign Click Prediction

**Generated:** 2025-12-06
**Purpose:** Five causal models of increasing complexity for understanding campaign engagement
**Reference:** [Data Catalog for Causal Modeling](20251205_2010_data_catalog_for_causal_modeling.md)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Variable Definitions](#variable-definitions)
3. [Model 1: Baseline Association Model](#model-1-baseline-association-model)
4. [Model 2: Energy Burden Mediation Model](#model-2-energy-burden-mediation-model)
5. [Model 3: Household Characteristics Model](#model-3-household-characteristics-model)
6. [Model 4: Campaign Treatment Effects Model](#model-4-campaign-treatment-effects-model)
7. [Model 5: Full Hierarchical Causal Model](#model-5-full-hierarchical-causal-model)
8. [Backdoor Paths and Identification](#backdoor-paths-and-identification)
9. [Multi-Campaign Participation Handling](#multi-campaign-participation-handling)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

### Modeling Strategy

We present five causal models of increasing complexity designed to build confidence progressively:

| Model | Name | Purpose | Causal Claims |
|-------|------|---------|---------------|
| 1 | Baseline Association | Validate data pipeline, establish associations | None |
| 2 | Mediation | Test energy burden mediation hypothesis | Mediation only |
| 3 | Household Characteristics | Richer confounding control | Partial adjustment |
| 4 | Campaign Treatment | Estimate campaign effects | Conditional on adjustment |
| 5 | Full Hierarchical | Production model with repeated measures | Maximum adjustment |

### Critical Selection Mechanism

**Important Context**: Campaigns target pre-selected households with significant energy burden via:
- Low income threshold
- High energy use

This creates **selection bias** that must be modeled. The population is enriched for high-burden households, affecting causal interpretation.

### Key Changes from Original Data Catalog

**Added Variables:**
- `house_age` (years since built)
- `sqft` (living_area_total from Residential)
- `kwh_hl_slope` (heating load sensitivity)
- `kwh_cl_slope` (cooling load sensitivity)
- `campaign_classification` (6 categories, new)
- `campaign_type` (5 types: email, text-morning, text-evening, letter, mailer)

**Removed Variables:**
- Local climate variables (all participants share same regional climate - Ohio)

**New Structural Considerations:**
- Multi-campaign participation handling
- Campaign classification taxonomy
- Backdoor path analysis

---

## Variable Definitions

### Outcome Variable

| Variable | Type | Role | Description | Coverage |
|----------|------|------|-------------|----------|
| `clicked` | Binary | **Outcome (Y)** | Participant clicked link in campaign | 100% |

Base rate: 5.7% CTR (see [Data Catalog](20251205_2010_data_catalog_for_causal_modeling.md), Section: Outcome Variables)

### Treatment Variables (New)

#### Campaign Classification (6 Categories)

| Classification | Description | Example Subject Lines |
|----------------|-------------|----------------------|
| **Urgency and Deadline Framing** | Time-sensitive messaging emphasizing deadlines | "Final Days to Apply!", "Deadline Tomorrow" |
| **Savings & Financial Empowerment** | Focus on cost reduction and financial benefits | "Save $X Per Month", "Reduce Your Bill" |
| **Relief and Reassurance** | Emotional comfort and assistance messaging | "Help is Available", "We're Here for You" |
| **Informational and Contextual** | Educational content about programs | "About HEAP Benefits", "How to Qualify" |
| **Personalized and Qualified Outreach** | Individual qualification-based messaging | "You Pre-Qualify for...", "Your Savings Estimate" |
| **Motivational / Struggle-Based Appeal** | Empathy for energy burden challenges | "We Know Bills Are High", "Winter Relief" |

*Note: Classification not yet in database; will be added based on campaign content analysis.*

#### Campaign Type (5 Categories)

| Type | Description | Expected Effect |
|------|-------------|-----------------|
| `email` | Standard email campaign | Reference category |
| `text-morning` | SMS sent in morning hours | Higher immediacy |
| `text-evening` | SMS sent in evening hours | Higher response when home |
| `letter` | Physical postal letter | Lower response, higher trust |
| `mailer` | Marketing mailer/flyer | Lowest response |

### Household Demographic Variables

| Variable | Type | Role | Description | Coverage |
|----------|------|------|-------------|----------|
| `income` | Continuous | **Confounder** | Estimated annual household income | 100% |
| `energy_burden` | Continuous | **Confounder/Mediator** | Total energy cost / income ratio | 100% |
| `household_size` | Continuous | Covariate | Number of household members | 100% |
| `children_present` | Binary | Covariate | Children in household | 93% |

See [Data Catalog](20251205_2010_data_catalog_for_causal_modeling.md), Section 4: Demographic Data for full field descriptions.

### Household Property Variables

| Variable | Type | Role | Description | Coverage |
|----------|------|------|-------------|----------|
| `house_age` | Continuous | **Confounder** | Years since construction (current_year - year_built) | 98.6% |
| `sqft` | Continuous | **Confounder** | Total living area in square feet | ~85% |
| `heat_type` | Categorical | Covariate | Heating system (FHA, HWB, EBB, HP, etc.) | 100% |
| `air_conditioning` | Categorical | Covariate | AC presence (Y/N/C) | 100% |

See [Data Catalog](20251205_2010_data_catalog_for_causal_modeling.md), Section 5: Residential/Property Data for heat type codes.

### Thermal Load Variables

| Variable | Type | Role | Description | Coverage |
|----------|------|------|-------------|----------|
| `kwh_hl_slope` | Continuous | **Effect Modifier** | Electric heating sensitivity (kWh/HDD) | 43.5% |
| `kwh_cl_slope` | Continuous | **Effect Modifier** | Electric cooling sensitivity (kWh/CDD) | 43.5% |
| `kwh_hl_r2` | Continuous | Quality Filter | Heating model fit (R-squared) | 43.5% |
| `kwh_cl_r2` | Continuous | Quality Filter | Cooling model fit (R-squared) | 43.5% |

**Interpretation of Thermal Load Slopes:**
- High slope + high R-squared = weather-sensitive building (poor envelope)
- High slope indicates high energy cost volatility with weather
- May indicate greater awareness of energy costs and higher engagement motivation

See [Data Catalog](20251205_2010_data_catalog_for_causal_modeling.md), Section 7: Thermal Load Analysis Data for full interpretation.

### Hierarchical Structure Variables

| Variable | Type | Role | Description |
|----------|------|------|-------------|
| `county` | Categorical | **Random Effect** | Geographic county (16 counties with participants) |
| `campaign_id` | Categorical | **Random Effect** | Specific campaign identifier |
| `participant_id` | Categorical | **Random Effect** | Unique participant (email-based) |
| `campaign_sequence` | Ordinal | **Time-Varying** | Which campaign number for this participant (1st, 2nd, 3rd...) |

---

## Model 1: Baseline Association Model

### Purpose

Establish baseline associations without causal claims. Validate data pipeline and understand marginal relationships.

### DAG (Directed Acyclic Graph)

```
Income ─────────────────────┐
                            ▼
House_Age ──────────────→ CLICKED
                            ▲
Energy_Burden ──────────────┘
```

**Note:** Arrows represent associations only, not causal claims.

### Mathematical Specification

```
clicked_i ~ Bernoulli(p_i)

logit(p_i) = beta_0 + beta_1 * income_i + beta_2 * energy_burden_i + beta_3 * house_age_i
```

Where all predictors are standardized (mean=0, sd=1).

### Prior Distributions

| Parameter | Prior | Rationale |
|-----------|-------|-----------|
| beta_0 (intercept) | Normal(-2.5, 1.0) | Low base click rate (~5-7%), logit(-2.5) approx 0.07 |
| beta_1 (income) | Normal(0, 1.0) | Weakly informative, standardized effect |
| beta_2 (energy_burden) | Normal(0, 1.0) | Weakly informative, standardized effect |
| beta_3 (house_age) | Normal(0, 1.0) | Weakly informative, standardized effect |

### Causal Analysis

**Backdoor Paths:** Not applicable (no causal claims)

**Confounders:** Not adjusted

**Interpretation:** Coefficients represent marginal associations only. Cannot distinguish direct from indirect effects.

### Expected Insights

- Direction of income-click association (positive or negative?)
- Energy burden association strength
- Data quality validation

### Limitations

- No causal interpretation
- Ignores campaign-level variation
- Ignores selection mechanism
- Ignores multi-campaign participation

---

## Model 2: Energy Burden Mediation Model

### Purpose

Test whether energy burden mediates the effect of income on clicking behavior. Establish causal mechanism hypothesis.

### DAG

```
                    ┌────────── Energy_Burden ──────────┐
                    │              (M)                  │
                    │                                   ▼
Income ─────────────┴───────────────────────────────→ CLICKED
   (X)              Direct Effect                       (Y)
                                                        ▲
House_Age ──────────────────────────────────────────────┘
   (C)
```

**Causal Paths:**
1. **Direct Effect:** Income → Clicked
2. **Indirect Effect:** Income → Energy_Burden → Clicked

### Mathematical Specification (Two-Equation System)

**Equation 1: Mediator Model**
```
energy_burden_i ~ Normal(mu_M_i, sigma_M)

mu_M_i = alpha_0 + alpha_1 * income_i + alpha_2 * house_age_i
```

**Equation 2: Outcome Model**
```
clicked_i ~ Bernoulli(p_i)

logit(p_i) = beta_0 + beta_1 * income_i + beta_2 * energy_burden_i + beta_3 * house_age_i
```

### Prior Distributions

| Parameter | Prior | Rationale |
|-----------|-------|-----------|
| alpha_0 | Normal(0, 0.5) | Centered at mean burden (standardized) |
| alpha_1 | Normal(-0.5, 0.3) | **Expected negative**: higher income reduces burden |
| alpha_2 | Normal(0.2, 0.3) | **Expected positive**: older homes have higher burden |
| beta_0 | Normal(-2.5, 1.0) | Low base rate |
| beta_1 | Normal(0, 0.5) | Direct income effect (sign ambiguous) |
| beta_2 | Normal(0.3, 0.3) | **Expected positive**: higher burden increases motivation |
| beta_3 | Normal(0, 0.5) | House age direct effect |
| sigma_M | HalfNormal(0.5) | Residual variance in burden |

### Effect Decomposition

**Total Effect of Income:**
```
Total = Direct + Indirect
Total = beta_1 + (alpha_1 * beta_2)
```

**Proportion Mediated:**
```
PM = (alpha_1 * beta_2) / Total
```

### Causal Analysis

**Assumptions for Mediation:**
1. No unmeasured confounding of Income → Clicked
2. No unmeasured confounding of Income → Energy_Burden
3. No unmeasured confounding of Energy_Burden → Clicked
4. No post-treatment confounding of mediator-outcome relationship

**Potential Violations:**
- County-level economic factors may confound all relationships
- Digital literacy (unmeasured) affects both burden awareness and clicking

### Expected Insights

- Is the income effect primarily direct or mediated through burden?
- Do high-burden households click more (motivation hypothesis)?
- What proportion of income effect operates through energy costs?

### Hypothesis

```
H1: alpha_1 < 0 (higher income reduces burden)
H2: beta_2 > 0 (higher burden increases clicking motivation)
H3: Indirect effect (alpha_1 * beta_2) < 0 (high income reduces clicks via lower burden)
```

---

## Model 3: Household Characteristics Model

### Purpose

Add building envelope and thermal performance indicators for richer confounding control. Test whether thermal sensitivity affects engagement.

### DAG

```
           ┌──────────────────────────────────────────────────────┐
           │                                                      │
Income ────┼──→ Energy_Burden ─────────────────────────┐          │
           │         ▲                                 │          │
           │         │                                 ▼          │
House_Age ─┼─────────┼────────────────────────────→ CLICKED ←─────┘
           │         │                                 ▲
           │         │                                 │
Sqft ──────┼─────────┴─────────────────────────────────┤
           │                                           │
Heat_Type ─┴───────────────────────────────────────────┤
                                                       │
kwh_hl_slope ──────────────────────────────────────────┤
                                                       │
kwh_cl_slope ──────────────────────────────────────────┘
```

### Confounding Relationships Modeled

| Relationship | Mechanism | Expected Direction |
|--------------|-----------|-------------------|
| House_Age → Energy_Burden | Older homes less efficient | Positive |
| Sqft → Energy_Burden | Larger homes cost more | Positive |
| Heat_Type → Energy_Burden | Electric heating expensive | Electric > Gas |
| kwh_hl_slope → Energy_Burden | Weather-sensitive = variable bills | Positive |
| House_Age → Sqft | Older homes often smaller | Negative |
| Sqft → kwh_hl_slope | Larger homes harder to heat | Positive |

### Mathematical Specification

```
clicked_i ~ Bernoulli(p_i)

logit(p_i) = beta_0 +
             beta_inc * income_i +
             beta_bur * energy_burden_i +
             beta_age * house_age_i +
             beta_sqft * sqft_i +
             beta_heat * heat_type_i +  # Categorical (dummy coded)
             beta_hl * kwh_hl_slope_i +
             beta_cl * kwh_cl_slope_i
```

### Prior Distributions

| Parameter | Prior | Rationale |
|-----------|-------|-----------|
| beta_0 | Normal(-2.5, 1.0) | Low base rate |
| beta_inc | Normal(0, 0.5) | Income effect after controlling for burden |
| beta_bur | Normal(0.3, 0.3) | Higher burden → more motivated |
| beta_age | Normal(0, 0.3) | Age effect after controlling for burden |
| beta_sqft | Normal(0, 0.3) | Larger homes - ambiguous effect |
| beta_heat[k] | Normal(0, 0.5) | Categorical effects (reference: FHA) |
| beta_hl | Normal(0.2, 0.3) | **Hypothesis**: weather-sensitive homes more motivated |
| beta_cl | Normal(0.2, 0.3) | Same reasoning for cooling |

### Key Insights Expected

**Thermal Load Slopes as Engagement Predictors:**

Households with high thermal sensitivity (high kwh_hl_slope, kwh_cl_slope) may:
1. Be more aware of energy costs (feel the impact of weather)
2. Have higher energy burden variability
3. Be more motivated to seek assistance

If beta_hl > 0 and beta_cl > 0, this supports the "cost awareness drives engagement" hypothesis.

### Variable Interactions to Consider

```
# Potential interaction: thermal sensitivity amplifies burden effect
beta_bur_hl * energy_burden_i * kwh_hl_slope_i
```

High burden + high thermal sensitivity = maximum engagement?

### Coverage Note

**Thermal load data has 43.5% coverage** among matched participants. Model will require:
- Missing data imputation, OR
- Complete case analysis with selection model, OR
- Two-stage estimation

---

## Model 4: Campaign Treatment Effects Model

### Purpose

Estimate causal effects of campaign characteristics (classification and type) on clicking behavior. This model attempts causal identification through adjustment.

### DAG with Campaign as Treatment

```
                        CAMPAIGN SELECTION MECHANISM
                                    │
        ┌───────────────────────────┴────────────────────────────┐
        │                                                        │
        ▼                                                        ▼
Campaign_Classification ──────────────────────────────────→ CLICKED
   (T1)     │                                                  (Y)
            │                                                   ▲
Campaign_Type ─────────────────────────────────────────────────┤
   (T2)                                                         │
                                                                │
                    ┌── HOUSEHOLD CONFOUNDERS ──────────────────┤
                    │                                           │
Income ─────────────┼───────────────────────────────────────────┤
                    │                                           │
Energy_Burden ──────┼───────────────────────────────────────────┤
                    │                                           │
House_Age ──────────┼───────────────────────────────────────────┤
                    │                                           │
Sqft ───────────────┼───────────────────────────────────────────┤
                    │                                           │
kwh_hl_slope ───────┘                                           │
                                                                │
County ─────────────────────────────────────────────────────────┘
```

### The Selection Problem

**Critical Issue**: Campaigns are NOT randomly assigned.

Selection mechanism:
1. Participants selected based on high energy burden + low income
2. Different organizations may use different campaign types
3. Campaign classification may vary by organization/county

This creates **BACKDOOR PATHS** that must be blocked.

### Backdoor Paths Analysis

**Path 1: Campaign ← Energy_Burden → Click**
- Selection is based on energy burden
- Energy burden affects clicking motivation
- **Solution:** Condition on energy_burden

**Path 2: Campaign ← Income → Click**
- Selection is based on income
- Income may affect digital engagement
- **Solution:** Condition on income

**Path 3: Campaign_Type ← Organization ← County ← Economics → Click**
- Organizations serve different regions
- Regions have different economic conditions
- **Solution:** Condition on county

### Mathematical Specification

```
clicked_ik ~ Bernoulli(p_ik)

logit(p_ik) = beta_0 +
              # Treatment effects (vs reference categories)
              sum(beta_class[j] * classification_jk) +  # j = 1..5 (6th is reference)
              sum(beta_type[m] * type_mk) +             # m = 1..4 (email is reference)

              # Confounding control
              beta_inc * income_i +
              beta_bur * energy_burden_i +
              beta_age * house_age_i +
              beta_sqft * sqft_i +
              beta_hl * kwh_hl_slope_i +

              # County fixed/random effect
              gamma_county[county_i]
```

### Prior Distributions for Treatment Effects

**Campaign Classification Priors** (relative to reference: "Informational and Contextual"):

| Parameter | Prior | Expected Direction | Rationale |
|-----------|-------|-------------------|-----------|
| beta_class[Urgency] | Normal(0.3, 0.3) | Positive | Deadline pressure increases action |
| beta_class[Savings] | Normal(0.2, 0.3) | Positive | Financial motivation |
| beta_class[Relief] | Normal(0.1, 0.3) | Slight positive | Emotional reassurance |
| beta_class[Personalized] | Normal(0.4, 0.3) | Positive | Personalization most effective |
| beta_class[Motivational] | Normal(0.2, 0.3) | Positive | Emotional appeal |

**Campaign Type Priors** (relative to reference: "email"):

| Parameter | Prior | Expected Direction | Rationale |
|-----------|-------|-------------------|-----------|
| beta_type[text-morning] | Normal(0.1, 0.3) | Slight positive | Immediate, may catch before work |
| beta_type[text-evening] | Normal(0.2, 0.3) | Positive | Home, more attention |
| beta_type[letter] | Normal(-0.2, 0.4) | Negative | Slower, less immediate action |
| beta_type[mailer] | Normal(-0.3, 0.4) | More negative | Lowest response expected |

### Adjustment Set for Causal Identification

**Minimal Sufficient Adjustment Set:**
```
{Income, Energy_Burden, County}
```

**Extended Adjustment Set (recommended):**
```
{Income, Energy_Burden, County, House_Age, Sqft, kwh_hl_slope}
```

### Identification Assumptions

1. **Positivity:** All combinations of confounders have some probability of receiving each campaign type
   - *Potential violation:* Some campaign types may only go to certain organizations

2. **Consistency:** Well-defined treatment
   - *Satisfied:* Clear campaign classification

3. **No Unmeasured Confounding:** All common causes measured
   - *Potential violations:*
     - Engagement history (prior clicking)
     - Digital literacy
     - Time-varying confounders (job loss, illness)

4. **No Measurement Error:**
   - *Concern:* Income is estimated, not observed

### Sensitivity Analysis Recommended

For unmeasured confounding, use:
- E-values for effect estimates
- Bayesian sensitivity parameters
- Comparison with propensity score methods

---

## Model 5: Full Hierarchical Causal Model

### Purpose

Production-ready model handling multi-campaign participation, county variation, and campaign-level random effects. Maximum information extraction with proper uncertainty quantification.

### Hierarchical Structure

```
Level 3: County (j = 1..16)
    │
    └──→ Level 2: Campaign (k = 1..74, nested in j)
              │
              └──→ Level 1: Participant-Campaign observation (i,k)
                        │
                        └──→ Outcome: clicked_ijk

Cross-classification:
    Participant (i) can appear in multiple campaigns (k)
```

### DAG with Full Structure

```
    COUNTY_j ──────────────────────────────────────────────────┐
        │                                                      │
        └──→ Regional_Economic_Context                         │
                    │                                          ▼
                    └──→ Income_Distribution ──→ Income_i ─────┴──→ CLICKED
                                                    │              ▲    ▲
                                                    ▼              │    │
                                          Energy_Burden_i ─────────┘    │
                                                    ▲                   │
Campaign_Classification_k ──────────────────────────┼───────────────────┤
                                                    │                   │
Campaign_Type_k ────────────────────────────────────┼───────────────────┤
                                                    │                   │
Campaign_Sequence_ik (1st, 2nd, 3rd...) ────────────┼───────────────────┤
                                                    │                   │
House_Characteristics_i ────────────────────────────┘                   │
                                                                        │
Participant_Random_Effect_i ────────────────────────────────────────────┘
```

### Multi-Campaign Participation Handling

**The Challenge:**
Participants appear in multiple campaigns (average 19 campaigns per unique participant).
This creates:
1. Non-independence of observations within participant
2. Possible fatigue effects across campaigns
3. Prior engagement affecting subsequent engagement

**Three Modeling Strategies:**

#### Strategy A: Participant Random Intercept
```
gamma_participant[i] ~ Normal(0, sigma_participant)
```
- Captures individual "clicker propensity"
- Some people are more likely to click regardless of campaign
- Accounts for unmeasured individual characteristics

#### Strategy B: Campaign Sequence Effect
```
beta_sequence * campaign_number_ik
```
- First campaign vs subsequent campaigns
- Expected: Fatigue effect (beta_sequence < 0)
- Each additional campaign reduces probability

#### Strategy C: Prior Engagement Predictor
```
beta_prior * prior_clicked_ik
```
- Binary: Did participant click any previous campaign?
- Engagement history predicts future engagement

**Recommended:** Combine A + B for production model.

### Mathematical Specification

```
clicked_ijk ~ Bernoulli(p_ijk)

logit(p_ijk) = beta_0 +

               # Treatment effects
               sum(beta_class[c] * classification_ck) +
               sum(beta_type[t] * type_tk) +

               # Household predictors
               beta_inc * income_i +
               beta_bur * energy_burden_i +
               beta_age * house_age_i +
               beta_sqft * sqft_i +
               beta_hl * kwh_hl_slope_i +
               beta_cl * kwh_cl_slope_i +

               # Campaign sequence (fatigue)
               beta_seq * campaign_sequence_ik +

               # Random effects
               gamma_county[j] +           # County intercept
               gamma_campaign[k] +         # Campaign intercept
               gamma_participant[i]        # Participant intercept
```

### Hierarchical Prior Distributions

**Fixed Effects:**
| Parameter | Prior | Rationale |
|-----------|-------|-----------|
| beta_0 | Normal(-2.5, 1.0) | Low base rate |
| beta_class[c] | Normal(0, 0.5) | Treatment effects |
| beta_type[t] | Normal(0, 0.5) | Channel effects |
| beta_seq | Normal(-0.1, 0.1) | Expected fatigue |
| beta_* (household) | Normal(0, 0.5) | Confounder control |

**Random Effect Variances:**
| Parameter | Prior | Interpretation |
|-----------|-------|----------------|
| sigma_county | HalfNormal(0.5) | Between-county variation |
| sigma_campaign | HalfNormal(0.3) | Between-campaign variation (after adjusting for type) |
| sigma_participant | HalfNormal(0.5) | Between-participant variation ("clicker propensity") |

**Random Effects:**
```
gamma_county[j] ~ Normal(0, sigma_county)         # j = 1..16
gamma_campaign[k] ~ Normal(0, sigma_campaign)     # k = 1..74
gamma_participant[i] ~ Normal(0, sigma_participant)  # i = 1..7078
```

### Intraclass Correlation Coefficients (ICC)

The ICC tells us what proportion of variance is explained at each level:

```
ICC_county = sigma_county^2 / (sigma_county^2 + sigma_campaign^2 + sigma_participant^2 + pi^2/3)
ICC_campaign = sigma_campaign^2 / (sigma_county^2 + sigma_campaign^2 + sigma_participant^2 + pi^2/3)
ICC_participant = sigma_participant^2 / (sigma_county^2 + sigma_campaign^2 + sigma_participant^2 + pi^2/3)
```

Where pi^2/3 is the residual variance for logistic distribution.

### Shrinkage and Partial Pooling

The hierarchical model provides **partial pooling**:
- Small campaigns borrow strength from larger campaigns
- Small counties borrow from state-level estimate
- Participants with few observations shrink toward population mean

This is especially valuable for:
- Low-observation campaigns
- Counties with few participants
- New participants (prediction)

---

## Backdoor Paths and Identification

### Summary of All Backdoor Paths

| Path | Description | Blocked By |
|------|-------------|------------|
| Campaign ← Energy_Burden → Click | Selection based on burden | Condition on energy_burden |
| Campaign ← Income → Click | Selection based on income | Condition on income |
| Campaign_Type ← Organization ← County → Click | Org/region confounding | Condition on county |
| Campaign ← House_Age → Energy_Burden → Click | Indirect selection | Condition on house_age |
| Campaign ← Prior_Engagement → Click | Engagement history | Participant random effect |

### D-Separation Analysis

For identifying Campaign → Click effect:

**Open Paths (must block):**
1. Campaign ← Selection ← Energy_Burden → Click
2. Campaign ← Selection ← Income → Click

**Adjustment Strategy:**
- Minimum adjustment set: {Income, Energy_Burden}
- Recommended adjustment set: {Income, Energy_Burden, County, House_Age, Sqft}

### Collider Warning

**Potential Collider:** Campaign_Sent

If we condition on "received campaign" (which we implicitly do), we may open paths through selection criteria.

```
Income → Campaign_Sent ← Energy_Burden
```

Conditioning on Campaign_Sent (being in the sample) creates association between Income and Energy_Burden even if none exists in the population.

**Mitigation:** This is unavoidable in observational data. Document as limitation.

### Unmeasured Confounding Concerns

| Potential Confounder | Affects Treatment? | Affects Outcome? | Available? |
|---------------------|-------------------|------------------|------------|
| Digital literacy | Maybe (tech comfort) | Yes (clicking ability) | No |
| Prior HEAP enrollment | No | Yes (familiarity) | Partially |
| Time-varying income | Yes (eligibility) | Yes (motivation) | No |
| Life events (illness, job loss) | Maybe | Yes (urgency) | No |
| Email frequency preference | Maybe (unsubscribe) | Yes (attention) | No |

### Sensitivity Analysis Recommendations

1. **E-values:** Calculate for all treatment effects
2. **Prior sensitivity:** Vary priors on treatment effects
3. **Subset analysis:** Compare effects across counties
4. **Propensity weighting:** As robustness check

---

## Multi-Campaign Participation Handling

### Descriptive Statistics

From [Data Catalog](20251205_2010_data_catalog_for_causal_modeling.md):
- Total participant records: 133,764
- Unique participants: 7,078
- Average campaigns per participant: 18.9
- Range: 1 to 74 campaigns

### Participation Patterns

| Campaign Count | Participants | Percentage | Analysis Approach |
|----------------|--------------|------------|-------------------|
| 1 campaign | ~500 | 7% | Simple analysis OK |
| 2-10 campaigns | ~2,000 | 28% | Random effects important |
| 11-30 campaigns | ~3,000 | 42% | Fatigue effects likely |
| 31+ campaigns | ~1,500 | 21% | Maximum fatigue |

### Recommended Handling by Model

| Model | Multi-Campaign Strategy |
|-------|------------------------|
| Model 1 | Ignore (simple associations) |
| Model 2 | Cluster-robust standard errors |
| Model 3 | Cluster-robust standard errors |
| Model 4 | County + campaign random effects |
| Model 5 | Full participant random effects + sequence |

### Campaign Sequence Variable Construction

```python
# Pseudocode for sequence variable
def compute_campaign_sequence(participant_campaigns):
    """
    For each participant, order their campaigns by send date
    and assign sequence number 1, 2, 3, ...
    """
    sorted_campaigns = sort_by(participant_campaigns, 'sent_at')
    for i, campaign in enumerate(sorted_campaigns):
        campaign['sequence_number'] = i + 1
    return sorted_campaigns
```

### Prior Click History Variable

```python
def compute_prior_clicked(participant_campaigns):
    """
    For each campaign, check if participant clicked any PRIOR campaign
    """
    sorted_campaigns = sort_by(participant_campaigns, 'sent_at')
    prior_clicked = False
    for campaign in sorted_campaigns:
        campaign['had_prior_click'] = prior_clicked
        if campaign['clicked']:
            prior_clicked = True
    return sorted_campaigns
```

### Expected Fatigue Effect

Based on marketing literature:
- First 5 campaigns: Full engagement potential
- Campaigns 6-15: ~20-30% reduction in baseline
- Campaigns 16-30: ~40-50% reduction
- Campaigns 31+: ~60%+ reduction

Prior for sequence effect:
```
beta_sequence ~ Normal(-0.05, 0.03)  # ~5% decrease in log-odds per campaign
```

---

## Implementation Roadmap

### Phase 1: Model 1 and 2 (Weeks 1-2)

**Objective:** Validate data pipeline and establish baseline

**Tasks:**
1. Implement standardization pipeline for predictors
2. Build Model 1 in NumPyro
3. Validate convergence and diagnostics
4. Build Model 2 mediation model
5. Estimate mediation effects
6. Document findings

**Success Criteria:**
- R-hat < 1.01 for all parameters
- ESS > 1000 for all parameters
- Posterior predictive check passes

### Phase 2: Model 3 (Weeks 3-4)

**Objective:** Add household characteristics

**Tasks:**
1. Merge thermal load data (handle 43.5% coverage)
2. Implement heat_type categorical encoding
3. Build Model 3
4. Compare to Models 1-2
5. Assess thermal load predictive value

**Success Criteria:**
- ELPD improvement over Model 2
- Meaningful thermal load coefficients
- No multicollinearity issues

### Phase 3: Model 4 (Weeks 5-6)

**Objective:** Estimate campaign treatment effects

**Tasks:**
1. Implement campaign classification (manual coding or NLP)
2. Add campaign type variable
3. Build Model 4 with county effects
4. Estimate treatment effects
5. Conduct sensitivity analysis

**Success Criteria:**
- Credible treatment effect estimates
- E-values calculated
- Comparison across organizations

### Phase 4: Model 5 (Weeks 7-8)

**Objective:** Production hierarchical model

**Tasks:**
1. Compute campaign sequence variables
2. Add participant random effects
3. Implement full hierarchical structure
4. Validate on held-out data
5. Document production deployment

**Success Criteria:**
- Proper convergence with 7,078 participant effects
- ICC estimates make sense
- Out-of-sample prediction accuracy

### Data Pipeline Requirements

```python
# Required preprocessing functions
def prepare_model_data():
    """
    Returns:
        - participant_data: DataFrame with household characteristics
        - campaign_data: DataFrame with campaign characteristics
        - observation_data: DataFrame with clicked outcomes
        - design_matrices: Ready for NumPyro
    """
    pass

# Required feature engineering
def compute_derived_features():
    """
    - standardized predictors
    - campaign_sequence
    - prior_clicked
    - heat_type dummies
    - interaction terms
    """
    pass
```

---

## Appendix A: Variable Quick Reference

### Variables by Role

**Outcome:**
- `clicked` (binary)

**Treatments:**
- `campaign_classification` (categorical, 6 levels)
- `campaign_type` (categorical, 5 levels)

**Confounders (must adjust):**
- `income`
- `energy_burden`
- `county`

**Additional Covariates:**
- `house_age`
- `sqft`
- `heat_type`
- `kwh_hl_slope`
- `kwh_cl_slope`
- `household_size`
- `children_present`

**Random Effects:**
- `county` (Level 3)
- `campaign_id` (Level 2)
- `participant_id` (Level 1, cross-classified)

**Time-Varying:**
- `campaign_sequence`
- `prior_clicked`

---

## Appendix B: Prior Sensitivity Recommendations

### Conservative vs Informative Priors

| Parameter | Conservative | Informative | Rationale for Choice |
|-----------|--------------|-------------|---------------------|
| beta_class | Normal(0, 1) | Normal(0.2, 0.3) | Use informative if prior research exists |
| sigma_county | HalfNormal(1) | HalfNormal(0.5) | Conservative avoids overfitting |
| sigma_participant | HalfNormal(1) | HalfNormal(0.5) | Conservative for many participants |

### Recommended Prior Sensitivity Checks

1. Double prior standard deviations
2. Use Student-t(3) instead of Normal
3. Use informative priors from similar studies
4. Compare posterior to prior (learning check)

---

**Document Maintained By:** Claude Code
**Related Documentation:**
- [Data Catalog for Causal Modeling](20251205_2010_data_catalog_for_causal_modeling.md) - Original data catalog
- `.claude_docs/bayesian_model_system.md` - Model architecture
- `src/bayesian_models/click_model_02/` - Current model implementation
