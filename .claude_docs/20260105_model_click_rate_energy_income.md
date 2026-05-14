# Click Rate Model: Energy Cost × Income Category

**Created**: 2026-01-05
**Status**: Implemented
**Model ID**: `model_05_rate_energy_income`

---

## Purpose

Model click-rate probability using energy cost and income category as separate predictors, avoiding the information loss from discretizing a derived energy burden ratio.

## Key Design Decision

**Why not use energy burden directly?**

```
energy_burden = energy_cost($) / income(categorical)
                     ↑                    ↑
                continuous         already discretized (10 categories)
```

Discretizing energy burden into categories would compound information loss. Instead, we model the components separately with an interaction term that captures the burden relationship implicitly.

---

## Data Characteristics

| Variable | Type | Details |
|----------|------|---------|
| `click` | Binary | Target variable (clicked = 1, not clicked = 0) |
| `energy_cost` | Continuous | Average monthly energy cost in dollars |
| `income_category` | Categorical | 10 ordered categories |
| **Base click rate** | — | ~2.5% (rare event) |

---

## Model Structure

### Mathematical Specification

```
Likelihood:
    click_i ~ Bernoulli(p_i)

Link Function:
    logit(p_i) = η_i

Linear Predictor:
    η_i = α                                    # baseline (reflects 2.5% rate)
        + β_energy · energy_cost_scaled_i      # continuous effect
        + γ[income_cat_i]                      # categorical effect (10 levels)
        + δ[income_cat_i] · energy_cost_scaled_i   # varying slopes (interaction)
```

### Parameter Interpretation

| Parameter | Meaning |
|-----------|---------|
| `α` | Baseline log-odds at mean energy cost, reference income category |
| `β_energy` | Average effect of energy cost on log-odds of clicking |
| `γ[k]` | Shift in log-odds for income category k vs reference |
| `δ[k]` | How energy cost effect differs for income category k |

### Prior Specification

```python
# Baseline - centered on observed click rate
# logit(0.025) ≈ -3.66
α ~ Normal(-3.7, 0.5)

# Energy cost effect (per 1 SD of energy_cost)
# Weakly informative, allows for moderate effects
β_energy ~ Normal(0, 0.5)

# Income category effects - hierarchical for partial pooling
γ[k] ~ Normal(0, σ_γ)        for k = 1, ..., 10
σ_γ ~ HalfNormal(0.5)

# Varying slopes by income - hierarchical
δ[k] ~ Normal(μ_δ, σ_δ)      for k = 1, ..., 10
μ_δ ~ Normal(0, 0.25)         # population mean slope modifier
σ_δ ~ HalfNormal(0.25)        # between-category slope variation
```

### Prior Justification

| Prior | Rationale |
|-------|-----------|
| `α ~ Normal(-3.7, 0.5)` | Centers on 2.5% base rate, allows range ~1-6% |
| `σ_γ ~ HalfNormal(0.5)` | Regularizes category effects, prevents overfitting with 10 levels |
| `σ_δ ~ HalfNormal(0.25)` | Tighter prior on slope variation — interactions harder to estimate |

---

## Preprocessing Requirements

```python
# 1. Scale energy cost for numerical stability
energy_cost_scaled = (energy_cost - energy_cost.mean()) / energy_cost.std()

# 2. Income category encoding
#    Option A: Treatment coding (first category = reference, γ[0] = 0)
#    Option B: Sum-to-zero coding (Σγ = 0) — often better for interactions
#    Recommendation: Sum-to-zero for interpretability

# 3. Handle missing values before modeling
```

---

## Visual Interpretation

```
Click Probability vs Energy Cost, by Income Category

     p(click)
        │
   0.06 ┤         ╱ Lowest Income (steepest positive slope)
        │       ╱
   0.04 ┤     ╱    ╱ Lower-Middle Income
        │   ╱    ╱
   0.02 ┤ ╱    ╱   ── Higher Income (flatter/negative slope)
        │╱   ╱  ──────
   0.00 ┼──────────────────
        $50  $100  $150  $200  $250
              Monthly Energy Cost

The interaction (δ[k]) allows each income category to have a different
slope — this IS the energy burden effect modeled flexibly.
```

---

## Model Outputs

### Primary Quantities of Interest

1. **Posterior predicted click probabilities** by income × energy cost combinations
2. **Marginal effects** of energy cost within each income category
3. **Contrast comparisons** between income categories at fixed energy costs

### Diagnostics to Check

- [ ] R-hat < 1.01 for all parameters
- [ ] ESS > 400 for all parameters
- [ ] No divergences
- [ ] Posterior predictive check: does model recover ~2.5% overall click rate?
- [ ] LOO-CV for model comparison (when adding predictors)

---

## Extension Roadmap

This model serves as a foundation. Planned extensions:

| Extension | Description |
|-----------|-------------|
| Campaign effects | Add campaign ID as group-level predictor |
| Demographics | Add demographic covariates |
| Temporal effects | Day-of-week, seasonality |
| Geographic | Region/zip-level effects |
| Message content | Text features from message |

Each extension should be added incrementally with model comparison (LOO-CV).

---

## Implementation Notes

### Recommended Framework
- **NumPyro/JAX** for GPU acceleration (if available)
- **PyMC** as alternative

### Sampling Recommendations
```python
# For rare events with hierarchical structure
num_warmup = 1000
num_samples = 2000
num_chains = 4
target_accept = 0.9  # slightly higher for hierarchical models
```

### File Locations
```
src/bayesian_models/model_05_rate_energy_income/
├── config.yaml          # model configuration
├── model.py             # model definition (ClickRateEnergyIncomeModel)
└── __init__.py

src/bayesian_scripts/
└── train_model_05_rate_energy_income.py

data/inference/model_05_rate_energy_income/  # (created during training)
├── traces/              # MCMC trace files (.nc)
├── reports/             # training results, category effects
├── diagrams/            # DAG, interaction plots, forest plots
└── checkpoints/         # scaler params for inference
```

---

## References

- Gelman et al. (2013) - Bayesian Data Analysis, Ch. 5 (Hierarchical Models)
- McElreath (2020) - Statistical Rethinking, Ch. 13 (Varying Slopes)
- Vehtari et al. (2017) - Practical Bayesian model evaluation using LOO-CV
