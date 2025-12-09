# Bayesian Causal Model Preparation Guide

**Purpose**: Technical guide for building PyMC causal models from Analysis-04 outputs

---

## Overview

This document provides specifications for implementing Bayesian causal models to estimate the **treatment effect of text messaging campaigns** on program application rates.

### Research Question

> What is the causal effect of receiving text message campaigns on the probability of submitting a program application, after adjusting for demographic confounders and campaign exposure patterns?

---

## Data Files

### Primary Input Files

| File | Description | Key Columns |
|------|-------------|-------------|
| `phase3_bayesian_integration.parquet` | Main analysis dataset | All features + treatment indicators |
| `phase3_cluster_probs.npy` | Soft cluster assignments | K-1 probability columns |
| `phase3_pymc_summary.json` | Model metadata | n_clusters, feature_names |

### Loading Data

```python
import pandas as pd
import numpy as np
import json

# Load main dataset
df = pd.read_parquet('data/clustering_results-04/phase3_bayesian_integration.parquet')

# Load cluster probabilities (K-1 columns for identifiability)
cluster_probs = np.load('data/clustering_results-04/phase3_cluster_probs.npy')

# Load metadata
with open('data/clustering_results-04/phase3_pymc_summary.json', 'r') as f:
    meta = json.load(f)
```

---

## Variable Definitions

### Outcome Variable

| Variable | Type | Description |
|----------|------|-------------|
| `is_applicant` | Binary (0/1) | Applied to program (1) or not (0) |

**Distribution**: 240 applicants / 7,473 participants = 3.21% base rate

### Treatment Variables

| Variable | Type | Description | Coverage |
|----------|------|-------------|----------|
| `has_text_treatment` | Binary | Received any text campaign | 57.5% |
| `has_email_treatment` | Binary | Received any email campaign | 95.0% |
| `total_text_count` | Count | Number of text campaigns received | 0-74 |
| `email_count` | Count | Number of email campaigns received | 0-68 |

**Primary Treatment**: `has_text_treatment` (binary indicator)

**Note**: Letters/mailers were sent to everyone (baseline), so they are not treatment variables.

### Channel Combinations

| `channel_combo` | Description | N | App Rate |
|-----------------|-------------|---|----------|
| `letter_only` | No digital campaigns | 22 | 0.00% |
| `letter+email` | Email only | 3,170 | 1.67% |
| `letter+text` | Text only | 373 | 4.29% |
| `letter+email+text` | Both channels | 3,908 | 3.81% |

---

## Confounders (Adjustment Variables)

### Demographic Confounders

| Variable | Type | Rationale |
|----------|------|-----------|
| `household_income` | Continuous | Affects both channel assignment and application likelihood |
| `household_size` | Continuous | Larger households may have different needs/exposure |
| `house_age` | Continuous | Older homes may have different program eligibility |
| `total_energy_burden` | Continuous | Program targeting may prioritize high-burden households |
| `living_area_sqft` | Continuous | Home size affects eligibility and targeting |
| `dwelling_type` | Categorical | Housing type affects program fit |
| `presence_of_children` | Binary | Family status may affect targeting |

### Exposure Confounders

| Variable | Type | Rationale |
|----------|------|-----------|
| `campaign_count` | Count | More exposure = more chances to apply |
| `exposure_days` | Count | Duration in campaign system |
| `channel_diversity` | Count | Number of unique channels received |

### Message Type Exposures

| Variable | Type | Description |
|----------|------|-------------|
| `msg_informational` | Count | Educational messages about program |
| `msg_motivational_struggle` | Count | Empathy-based messaging |
| `msg_personalized_qualified` | Count | Pre-qualification messaging |
| `msg_relief_reassurance` | Count | Anxiety-reducing messaging |
| `msg_savings_financial` | Count | Financial benefit emphasis |
| `msg_urgency_deadline` | Count | Time-limited offers |

---

## Cluster Probabilities for Hierarchical Modeling

### Why Use Cluster Probabilities?

1. **Soft Assignment**: Avoid hard clustering artifacts
2. **Heterogeneity Control**: Account for unobserved participant types
3. **Dimension Reduction**: Summarize demographic patterns efficiently
4. **Identifiability**: K-1 columns prevent multicollinearity

### Usage in PyMC

```python
# cluster_probs shape: (7473, 9) for 10 clusters
# Reference cluster (highest app rate) excluded for identifiability

# Add cluster effects to linear predictor
cluster_effect = pm.Normal('cluster_effect', mu=0, sigma=1, shape=9)
cluster_contribution = cluster_probs @ cluster_effect
```

---

## Recommended Model Structures

### Model 1: Simple Treatment Effect

**Purpose**: Estimate average treatment effect (ATE) of text messaging

```python
import pymc as pm
import pytensor.tensor as pt

with pm.Model() as simple_ate:
    # Priors
    intercept = pm.Normal('intercept', mu=-3, sigma=1)  # Low base rate
    text_effect = pm.Normal('text_effect', mu=0, sigma=1)

    # Linear predictor
    eta = intercept + text_effect * df['has_text_treatment'].values

    # Likelihood
    p = pm.math.sigmoid(eta)
    y = pm.Bernoulli('y', p=p, observed=df['is_applicant'].values)

    # Sample
    trace = pm.sample(2000, tune=1000, cores=4)
```

**Expected Output**: Posterior distribution of `text_effect` on log-odds scale

### Model 2: Adjusted Treatment Effect

**Purpose**: Control for demographic and exposure confounders

```python
with pm.Model() as adjusted_ate:
    # Standardize continuous confounders
    X_demo = df[['household_income', 'household_size', 'house_age',
                 'total_energy_burden', 'living_area_sqft']].values
    X_demo_std = (X_demo - X_demo.mean(0)) / X_demo.std(0)

    X_exposure = df[['campaign_count', 'exposure_days']].values
    X_exposure_std = (X_exposure - X_exposure.mean(0)) / X_exposure.std(0)

    # Priors
    intercept = pm.Normal('intercept', mu=-3, sigma=1)
    text_effect = pm.Normal('text_effect', mu=0, sigma=1)

    beta_demo = pm.Normal('beta_demo', mu=0, sigma=0.5, shape=5)
    beta_exposure = pm.Normal('beta_exposure', mu=0, sigma=0.5, shape=2)

    # Linear predictor
    eta = (intercept +
           text_effect * df['has_text_treatment'].values +
           X_demo_std @ beta_demo +
           X_exposure_std @ beta_exposure)

    # Likelihood
    p = pm.math.sigmoid(eta)
    y = pm.Bernoulli('y', p=p, observed=df['is_applicant'].values)

    trace = pm.sample(2000, tune=1000, cores=4)
```

### Model 3: Hierarchical with Cluster Effects

**Purpose**: Account for unobserved heterogeneity via cluster membership

```python
with pm.Model() as hierarchical_model:
    # Load cluster probabilities
    cluster_probs = np.load('data/clustering_results-04/phase3_cluster_probs.npy')

    # Priors
    intercept = pm.Normal('intercept', mu=-3, sigma=1)
    text_effect = pm.Normal('text_effect', mu=0, sigma=1)

    # Cluster effects (K-1 for identifiability)
    cluster_effect = pm.Normal('cluster_effect', mu=0, sigma=1, shape=9)

    # Demographic effects
    beta_demo = pm.Normal('beta_demo', mu=0, sigma=0.5, shape=5)

    # Linear predictor
    eta = (intercept +
           text_effect * df['has_text_treatment'].values +
           cluster_probs @ cluster_effect +
           X_demo_std @ beta_demo)

    # Likelihood
    p = pm.math.sigmoid(eta)
    y = pm.Bernoulli('y', p=p, observed=df['is_applicant'].values)

    trace = pm.sample(2000, tune=1000, cores=4)
```

### Model 4: Propensity Score Adjustment (Doubly Robust)

**Purpose**: Address selection bias in treatment assignment

```python
with pm.Model() as propensity_model:
    # Stage 1: Propensity score model
    # P(text | demographics, prior exposure)

    # Confounders that predict treatment assignment
    X_confounders = df[['household_income', 'household_size', 'house_age',
                        'email_count', 'exposure_days']].values
    X_conf_std = (X_confounders - X_confounders.mean(0)) / X_confounders.std(0)

    # Propensity model parameters
    alpha_ps = pm.Normal('alpha_ps', mu=0, sigma=1)
    beta_ps = pm.Normal('beta_ps', mu=0, sigma=0.5, shape=5)

    # Propensity scores
    ps_eta = alpha_ps + X_conf_std @ beta_ps
    propensity = pm.math.sigmoid(ps_eta)

    # Treatment likelihood (for propensity estimation)
    treatment = pm.Bernoulli('treatment', p=propensity,
                              observed=df['has_text_treatment'].values)

    # Stage 2: Outcome model with propensity adjustment
    intercept = pm.Normal('intercept', mu=-3, sigma=1)
    text_effect = pm.Normal('text_effect', mu=0, sigma=1)

    # Inverse probability weights
    ipw = pm.Deterministic('ipw',
        df['has_text_treatment'].values / propensity +
        (1 - df['has_text_treatment'].values) / (1 - propensity))

    # Weighted outcome model
    eta_outcome = intercept + text_effect * df['has_text_treatment'].values
    p_outcome = pm.math.sigmoid(eta_outcome)

    # Weighted likelihood (approximation)
    y = pm.Bernoulli('y', p=p_outcome, observed=df['is_applicant'].values)

    trace = pm.sample(2000, tune=1000, cores=4)
```

---

## Heterogeneous Treatment Effects

### By Cluster

Estimate separate treatment effects for each cluster:

```python
with pm.Model() as het_by_cluster:
    # Cluster-specific treatment effects
    text_effect_cluster = pm.Normal('text_effect_cluster', mu=0, sigma=1, shape=10)

    # Assign effects by hard cluster (or use soft assignment)
    cluster_idx = df['phase3_cluster'].values
    text_effect_i = text_effect_cluster[cluster_idx]

    # ... rest of model
```

### By Channel Combination

```python
# Create interaction terms
df['text_x_email'] = df['has_text_treatment'] * df['has_email_treatment']

with pm.Model() as interaction_model:
    text_main = pm.Normal('text_main', mu=0, sigma=1)
    email_main = pm.Normal('email_main', mu=0, sigma=1)
    text_email_interaction = pm.Normal('text_email_interaction', mu=0, sigma=1)

    eta = (intercept +
           text_main * df['has_text_treatment'].values +
           email_main * df['has_email_treatment'].values +
           text_email_interaction * df['text_x_email'].values)
```

---

## Model Diagnostics

### Convergence Checks

```python
import arviz as az

# R-hat should be < 1.01
az.rhat(trace)

# ESS should be > 400
az.ess(trace)

# Visual diagnostics
az.plot_trace(trace, var_names=['text_effect'])
az.plot_posterior(trace, var_names=['text_effect'])
```

### Posterior Predictive Checks

```python
with model:
    ppc = pm.sample_posterior_predictive(trace)

# Check if observed base rate is plausible under posterior
az.plot_ppc(ppc)
```

### Model Comparison

```python
# Compare models using LOO-CV
az.compare({
    'simple': trace_simple,
    'adjusted': trace_adjusted,
    'hierarchical': trace_hierarchical
})
```

---

## Expected Results

### Treatment Effect Interpretation

| Metric | Formula | Naive Estimate |
|--------|---------|----------------|
| Log-odds ratio | `text_effect` posterior mean | ~0.95 |
| Odds ratio | `exp(text_effect)` | ~2.6 |
| Risk difference | P(apply\|text) - P(apply\|no text) | +2.62 pp |
| Relative risk | P(apply\|text) / P(apply\|no text) | ~2.6x |

### Credible Intervals

Report 89% HDI (Highest Density Interval) following Bayesian best practices:

```python
az.hdi(trace, hdi_prob=0.89, var_names=['text_effect'])
```

---

## Causal Assumptions

### Required Assumptions for Causal Interpretation

1. **SUTVA (Stable Unit Treatment Value Assumption)**
   - One participant's treatment doesn't affect another's outcome
   - *Plausible*: Applications are individual decisions

2. **Positivity**
   - All confounder combinations have non-zero probability of treatment
   - *Check*: Verify overlap in propensity score distributions

3. **Ignorability (No Unmeasured Confounding)**
   - All confounders affecting both treatment and outcome are measured
   - *Limitation*: Phone number availability may predict text receipt AND application propensity

4. **Correct Model Specification**
   - Functional form is correct
   - *Mitigation*: Compare multiple model specifications

### Sensitivity Analysis

Test robustness to unmeasured confounding:

```python
# Vary assumed correlation between unmeasured confounder and outcome
for gamma in [0.1, 0.2, 0.3]:
    # Re-run model with simulated confounder
    pass
```

---

## Implementation Checklist

### Data Preparation
- [ ] Load `phase3_bayesian_integration.parquet`
- [ ] Load `phase3_cluster_probs.npy`
- [ ] Standardize continuous variables
- [ ] Create dummy variables for categoricals
- [ ] Verify no missing values in model variables

### Model Building
- [ ] Start with simple treatment effect model
- [ ] Add demographic confounders
- [ ] Add cluster probabilities
- [ ] Test heterogeneous effects by cluster

### Diagnostics
- [ ] Check R-hat < 1.01 for all parameters
- [ ] Verify ESS > 400
- [ ] Run posterior predictive checks
- [ ] Compare models with LOO-CV

### Reporting
- [ ] Report posterior mean and 89% HDI for treatment effect
- [ ] Convert to interpretable scale (odds ratio, risk difference)
- [ ] Discuss causal assumptions and limitations
- [ ] Sensitivity analysis for unmeasured confounding

---

## References

- Gelman, A. et al. (2013). Bayesian Data Analysis, 3rd ed.
- McElreath, R. (2020). Statistical Rethinking, 2nd ed.
- Pearl, J. (2009). Causality: Models, Reasoning, and Inference.
- PyMC Documentation: https://www.pymc.io/

---

*Generated from Analysis-04 Pipeline*
