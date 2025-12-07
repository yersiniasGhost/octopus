# Bayesian and Causal Modeling Research Report

**Date**: 2025-12-05
**Domain**: Energy Utility Marketing - Email Campaign Engagement
**Current Models**: click_model (v0, v02), email open models (01-03)

---

## Executive Summary

This research analyzed the octopus codebase to develop recommendations for Bayesian and causal modeling approaches. Key findings:

1. **Causal Structure**: Identified a DAG with Income and County as key confounders for the Energy Burden → Click relationship
2. **Model Progression**: Recommend hierarchical county-level models as immediate next step
3. **Prior Refinement**: Domain-informed priors can tighten inference
4. **Causal Validity**: Backdoor adjustment is valid with proper conditioning; sensitivity analysis essential
5. **Answerable Questions**: Most questions about EB effects are answerable with current data + proper adjustment

---

## 1. Causal Structure Discovery

### 1.1 Proposed DAG Structure

```
                        County (C)
                       /    |    \
                      ↓     ↓     ↓
               Income(I)   HA   Local_Climate(U1)
                 |    \    |         |
                 |     \   |         |
                 ↓      ↓  ↓         ↓
        Digital_Lit(U2) Energy_Cost(EC)
                 |           |
                 |           ↓
                 |    Energy_Burden (EB = EC/I)
                 |         / |
                 ↓        ↓  |
              Open ←─────────┘
               |
               ↓
            Click

Legend:
- Observed: County, Income, House Age (HA), Energy Burden (EB), Open, Click
- Unobserved: Digital Literacy (U2), Local Climate factors (U1)
```

### 1.2 Variable Classification

| Variable | Role | Rationale |
|----------|------|-----------|
| **Income** | CONFOUNDER | Affects EB (denominator) AND Click (digital literacy path) |
| **County** | CONFOUNDER | Common cause of Income, EB, and engagement patterns |
| **House Age** | CONFOUNDER | Affects energy costs → EB, and may affect engagement directly |
| **Energy Burden** | EXPOSURE | Target causal effect of interest |
| **Open** | MEDIATOR | Intermediate outcome between EB and Click |
| **Click** | OUTCOME | Primary binary outcome |

### 1.3 Backdoor Paths (EB → Click)

1. EB ← Income → Digital_Lit → Click
2. EB ← House_Age ← County → Click
3. EB ← Income ← County → Click

**Minimal Adjustment Set**: {Income, County} blocks all backdoor paths.

**Current Model Gap**: click_model v0/v02 adjusts for Income but NOT County → potential residual confounding.

### 1.4 Unobserved Confounders

| Confounder | Impact | Handling Strategy |
|------------|--------|-------------------|
| Digital Literacy | Biases Income→Click path | Proxy with zip-code education if available |
| Environmental Consciousness | May attenuate EB effect | Sensitivity analysis with E-value |
| Financial Stress/Urgency | May strengthen EB effect | Bounds analysis |
| Prior Program Participation | Time-varying confounder | Future: G-estimation |
| Household Composition | Partially captured by EB | Consider adding if available |

---

## 2. Model Complexity Spectrum

### 2.1 Current Baseline (Level 1)

```python
# click_model v0/v02: Simple Additive Logistic
logit(P(Click=1)) = α + β₁*Income + β₂*EB + β₃*House_Age
```

**Strengths**: Interpretable, fast, good starting point
**Limitations**: Ignores clustering, assumes homogeneous effects, no county adjustment

### 2.2 Recommended: Hierarchical Model (Level 2)

```python
# Proposal: click_model_03 - Hierarchical County Effects
logit(P(Click_ij=1)) = α_j[county] + β₁*Income + β₂*EB + β₃*HA

# Priors
α_j ~ Normal(μ_α, τ_α)         # County random intercepts
μ_α ~ Normal(-3.5, 1.0)        # Grand mean (3% baseline CTR)
τ_α ~ HalfNormal(0.5)          # County variation
```

**Benefits**:
- Addresses county clustering
- Enables valid backdoor adjustment
- Partial pooling borrows strength
- Accounts for unmeasured county-level confounders

### 2.3 Extension: Varying Slopes (Level 2+)

```python
# If county heterogeneity detected
# County-specific EB effects with correlation structure
[α_j, β_EB_j] ~ MVNormal([μ_α, μ_β], Σ)
Σ = LKJ_corr_cholesky(η=2.0) * diag(σ)
```

**When to use**: If posterior σ_β_EB indicates meaningful county-level variation in EB effects.

### 2.4 Non-Linear Extensions (Level 3)

```python
# Spline model for non-linear EB effects
f(EB) = Σ β_k * B_k(EB)  # B-spline basis
β_k ~ Normal(0, τ)       # Smoothness prior
τ ~ HalfNormal(1.0)
```

**When to use**: If residual plots show systematic non-linearity (thresholds, saturation).

### 2.5 Complexity Decision Framework

```
Progression:
1. Fit Level 1 (current baseline)
2. Fit Level 2 (hierarchical) → Compare WAIC
   - ΔWAIC < -4: Level 2 clearly better
   - -4 < ΔWAIC < 4: Prefer simpler (Level 1)

3. Check LOO diagnostics
   - Pareto-k > 0.7 for >5% observations: Model misspecified

4. Residual analysis
   - Systematic patterns vs EB: Consider Level 3 (splines)
```

---

## 3. Bayesian Framework Choices

### 3.1 Prior Recommendations

| Parameter | Current Prior | Recommended Prior | Justification |
|-----------|---------------|-------------------|---------------|
| α (intercept) | N(-3.5, 1.0) | N(-3.5, 0.7) | Industry CTR 2-5%, tighter |
| β_income | N(0, 0.5) | N(0, 0.3) | Skeptical, weak expected effect |
| β_EB | N(0, 0.5) | N(0.2, 0.3) | Weakly positive, domain informed |
| β_house_age | N(0, 0.5) | N(0, 0.3) | Skeptical, uncertain direction |
| τ_county | - | HalfNormal(0.5) | Modest county variation |

### 3.2 Prior Predictive Checks

**Validation Criteria**:
- P(Click) should fall in [0.001, 0.3] across prior draws
- If prior allows P(Click) > 0.5 frequently → priors too diffuse

```python
# Prior predictive check code
with model:
    prior_pred = pm.sample_prior_predictive(500)
    # Check: az.plot_ppc(prior_pred, group='prior')
```

### 3.3 Likelihood Functions

| Outcome Type | Distribution | Link Function |
|--------------|--------------|---------------|
| Binary (Click) | Bernoulli | Logit |
| Binary (Open) | Bernoulli | Logit |
| Count | Poisson/NegBinom | Log |
| Ordinal (engagement level) | OrderedLogistic | Cumulative logit |

**Current**: Bernoulli-Logit is correct for binary outcomes.

### 3.4 Model Comparison Approaches

| Method | Use Case | ArviZ Function |
|--------|----------|----------------|
| WAIC | Nested models, quick comparison | `az.waic(trace)` |
| LOO-CV | Complex/hierarchical models | `az.loo(trace)` |
| Bayes Factors | Specific hypothesis testing | Bridge sampling |

**Decision Rule**:
```
ΔWAIC < -4: Complex model clearly better
-4 ≤ ΔWAIC ≤ 4: Similar fit, prefer simpler
ΔWAIC > 4: Simple model better
```

---

## 4. Causal Inference Methods

### 4.1 Do-Calculus Applicability

**Target**: P(Click | do(EB = eb))

**Backdoor Adjustment Formula**:
```
P(Click | do(EB)) = Σ_{c,i} P(Click | EB, County=c, Income=i) × P(County=c, Income=i)
```

**Status**: ✅ Valid with hierarchical model adjusting for County + Income

### 4.2 Instrumental Variables

**Assessment of Available Data**:

| Candidate IV | Validity | Issue |
|--------------|----------|-------|
| Weather shocks | ❌ Not available | Could instrument EB via heating/cooling costs |
| Utility rate changes | ❌ Not available | Would provide exogenous EB variation |
| County as IV | ❌ Invalid | Has direct effect on Click |
| House Age as IV | ⚠️ Questionable | Exclusion restriction likely violated |

**Recommendation**: No valid IV in current data. Future data collection could include:
- Heating/cooling degree days
- Historical utility rate schedules
- Energy efficiency subsidy timelines

### 4.3 Difference-in-Differences Opportunities

**Potential Design**: Campaign timing as treatment

| Component | Data Availability |
|-----------|-------------------|
| Treatment timing | ✅ campaign_sent_at |
| Geographic variation | ✅ County |
| Pre-campaign baseline | ⚠️ Need to construct |
| Parallel trends | ⚠️ Need to verify |

**Recommendation**: Explore staggered campaign rollout as natural experiment.

### 4.4 Regression Discontinuity Opportunities

**Question**: Are campaigns targeted using explicit income/burden cutoffs?

If yes (e.g., target households with EB > 6%):
- Sharp RD design possible at threshold
- Local average treatment effect at cutoff

**Action Item**: Verify campaign targeting criteria with business team.

### 4.5 Sensitivity Analysis for Unmeasured Confounding

**E-Value Approach**:
```python
# Post-hoc sensitivity analysis
def compute_e_value(odds_ratio):
    return odds_ratio + np.sqrt(odds_ratio * (odds_ratio - 1))

# Interpretation:
# If E-value = 2.5, unmeasured confounder needs RR ≥ 2.5
# with BOTH exposure and outcome to explain away effect
```

**Reporting Standard**: Always report E-value alongside effect estimates.

---

## 5. Model Proposals

### 5.1 Immediate: click_model_03 (Hierarchical)

**File**: `src/bayesian_models/click_model_03/model.py`

```python
with pm.Model() as hierarchical_click:
    # Hyperpriors
    mu_alpha = pm.Normal('mu_alpha', -3.5, 1.0)
    sigma_alpha = pm.HalfNormal('sigma_alpha', 0.5)

    # County random intercepts
    alpha_county = pm.Normal('alpha_county', mu_alpha, sigma_alpha,
                             shape=n_counties)

    # Fixed effects
    beta_income = pm.Normal('beta_income', 0, 0.3)
    beta_eb = pm.Normal('beta_eb', 0.2, 0.3)
    beta_ha = pm.Normal('beta_ha', 0, 0.3)

    # Linear predictor with county indexing
    eta = (alpha_county[county_idx] +
           beta_income * income_std +
           beta_eb * eb_std +
           beta_ha * ha_std)

    # Likelihood
    p = pm.math.sigmoid(eta)
    clicks = pm.Bernoulli('clicks', p=p, observed=y)
```

**DAG Assumption**: County → {Income, EB, HA, Click}; conditioning on County blocks backdoor paths.

### 5.2 Medium-term: click_model_04 (Varying Slopes)

```python
with pm.Model() as varying_slopes:
    # Correlated county effects (intercept + EB slope)
    chol, corr, stds = pm.LKJCholeskyCov(
        'chol', n=2, eta=2.0,
        sd_dist=pm.HalfNormal.dist([0.5, 0.3])
    )

    county_effects = pm.MvNormal(
        'county_effects',
        mu=[pm.Normal('mu_alpha', -3.5, 1.0),
            pm.Normal('mu_beta_eb', 0.2, 0.3)],
        chol=chol,
        shape=(n_counties, 2)
    )

    alpha_county = county_effects[:, 0]
    beta_eb_county = county_effects[:, 1]

    # eta with county-varying EB effect
    eta = alpha_county[c] + beta_eb_county[c] * eb_std + ...
```

### 5.3 Lower Priority: Spline Model

Only pursue if:
1. Hierarchical model shows good fit
2. Residual vs EB plots show systematic non-linearity
3. Domain experts suggest threshold effects

---

## 6. Answerable vs Assumption-Heavy Questions

### ✅ Answerable with Current Data + Proposed Models

| Question | Method | Key Assumption |
|----------|--------|----------------|
| Causal effect of EB on Click, adjusted | Hierarchical backdoor | No unmeasured I,C confounders |
| Does EB effect vary by county? | Varying slopes model | Above + county exchangeability |
| Is EB effect linear? | Spline vs linear WAIC | Model specification |
| Total Income effect on Click | Unadjusted for EB | Standard causal |
| Mediated effect through EB | Total - Direct | No med-outcome confounding |

### ⚠️ Require Stronger Assumptions or Additional Data

| Question | Issue | What's Needed |
|----------|-------|---------------|
| Direct Income effect (not via EB) | Med-outcome confounders | Education/digital literacy data |
| Interventional "if we reduce EB" | Positivity, consistency | Actual intervention data |
| Time-varying campaign effects | Dynamic confounding | Longitudinal structure |
| Effect of digital literacy | Unobserved | Direct measurement |

---

## 7. Implementation Roadmap

### Phase 1: Immediate (1-2 weeks)
1. Implement click_model_03 (hierarchical county effects)
2. Add county to ClickModelData class
3. Compare WAIC to v0/v02
4. Run prior predictive checks

### Phase 2: Validation (2-3 weeks)
1. Posterior predictive checks
2. LOO-CV diagnostics (Pareto-k)
3. Residual analysis for non-linearity
4. E-value sensitivity analysis

### Phase 3: Extensions (if warranted)
1. Varying slopes model (if county heterogeneity)
2. Spline model (if non-linearity detected)
3. DiD analysis (if campaign timing data structured)

### Phase 4: Documentation
1. Update DAG documentation per model
2. Document causal assumptions explicitly
3. Create model comparison report
4. Add sensitivity analysis to standard outputs

---

## 8. Key References

### Causal Inference
- Pearl, J. (2009). Causality: Models, Reasoning, and Inference
- Hernán, M. A. & Robins, J. M. (2020). Causal Inference: What If
- VanderWeele, T. J. & Ding, P. (2017). Sensitivity Analysis in Observational Research

### Bayesian Modeling
- Gelman, A. et al. (2013). Bayesian Data Analysis, 3rd Edition
- McElreath, R. (2020). Statistical Rethinking, 2nd Edition
- Bürkner, P. C. (2017). brms: Bayesian Regression Models

### Hierarchical Models
- Gelman, A. & Hill, J. (2006). Data Analysis Using Regression and Multilevel Models

---

## Appendix: Data Summary

### Available Variables
| Variable | Source | Type | Range |
|----------|--------|------|-------|
| contact_id | participants | String | Unique ID |
| income | Demographic | Float | $15K-500K |
| energy_burden | Demographic | Float | 1-30% |
| house_age | Residential | Integer | 1800-2025 |
| county | Demographic | Categorical | 10 counties |
| click | participants.engagement | Binary | {0, 1} |
| open | participants.engagement | Binary | {0, 1} |

### Match Coverage
- Participant → Demographic: ~65% match rate
- Demographic → Residential: Variable by county

### Current Model Inventory
| Model | Purpose | Variables | Status |
|-------|---------|-----------|--------|
| click_model | CTR from demographics | I, EB | Active |
| click_model_02 | + House age | I, EB, HA | Beta |
| model_01_baseline | Open prediction | Cost, Savings | Active |
| model_02_energy_burden | Open from EB | EB, I, HH_size | Active |
| model_03_demographics | Open from demos | Demographics | Active |
