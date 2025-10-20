# Bayesian Model Progression - Quick Reference

**Response Variables:** `opened` (binary), `clicked` (binary, conditional on opened)

---

## Model Progression Summary

| Model | Key Addition | Primary Question | Complexity |
|-------|--------------|------------------|------------|
| **M1** | Baseline | Does energy cost/savings predict opens? | ⭐ |
| **M2** | Energy Burden | Does high energy burden (>6%) drive engagement? | ⭐ |
| **M3** | Demographics | Do demographics explain variance beyond burden? | ⭐⭐ |
| **M4** | Property | Does property type/quality matter? | ⭐⭐ |
| **M5** | Campaign Hierarchy | Do effects vary by campaign? | ⭐⭐⭐ |
| **M6** | Geographic Hierarchy | Do effects vary by ZIP/geography? | ⭐⭐⭐ |
| **M7** | Full Hierarchy | Campaign + Geography crossed effects | ⭐⭐⭐⭐ |
| **M8** | Interactions | Does burden effect vary by income/property? | ⭐⭐⭐⭐ |
| **M9** | Time Series | Do usage patterns predict engagement? | ⭐⭐⭐⭐ |
| **M10** | Spatial | Explicit spatial correlation (CAR model) | ⭐⭐⭐⭐⭐ |

---

## Key Predictor Categories

### 🔥 Energy Economics (Primary Interest)
- `total_energy_burden` - Energy cost / income (hypothesis: high burden → high engagement)
- `annual_kwh_cost`, `annual_gas_cost` - Absolute costs
- `kwh` - Usage intensity
- `annual_savings` - Savings potential

### 👥 Demographics
- `income_level` - Income bracket (0-9 scale)
- `estimated_income` - Dollar amount
- `md_householdsize` - Household size
- `has_mobile` - Tech-savviness proxy

### 🏠 Property Characteristics
- `living_area_total` - Square footage
- `age` - Building age (weatherization potential)
- `heat_type` - Heating system (categorical)
- `story_height` - Property type indicator

### 📍 Geographic
- `zip`, `city` - Location identifiers
- `census_tract` - Fine-grained geography

### 📊 Time Series Features (Engineered)
- `usage_volatility` - Coefficient of variation
- `summer_winter_ratio` - Seasonal usage pattern
- `kwh_hl_slope`, `kwh_cl_slope` - Heating/cooling sensitivity

### 📧 Campaign Context
- `campaign_id` - Campaign identifier
- `campaign_sent_at` - Timing
- Subject line, from name (from campaigns collection)

---

## Recommended Starting Point

### Start with Model 2-3 (Energy Burden + Demographics)

**Why:**
- Tests primary hypothesis (energy burden drives engagement)
- Controls for key confounders (income, household size)
- Interpretable coefficients
- Fast to fit

**Example Research Question:**
> "Do households with high energy burden (>6% of income) have higher email open rates, controlling for income level and household size?"

---

## Progression Logic

```
M1: Baseline (cost, savings)
  ↓
M2: Add ENERGY BURDEN (primary hypothesis)
  ↓
M3: Add DEMOGRAPHICS (confounders)
  ↓
M4: Add PROPERTY (additional confounders)
  ↓
M5-6: Add HIERARCHY (account for clustering)
  ↓
M7: FULL HIERARCHY (crossed random effects)
  ↓
M8: INTERACTIONS (effect modification)
  ↓
M9: TIME SERIES (usage patterns)
  ↓
M10: SPATIAL (geographic correlation)
```

---

## Key Hypotheses to Test

### Energy Burden Hypotheses
1. **H1:** Higher energy burden → higher open rate
2. **H14:** Burden effect stronger for lower-income households (interaction)
3. **H15:** Burden effect stronger for larger homes (interaction)

### Demographic Hypotheses
4. **H2:** Lower income → higher open rate
5. **H3:** Larger households → higher open rate
6. **H4:** Mobile phone availability → higher engagement

### Property Hypotheses
7. **H7:** Larger homes → higher engagement
8. **H8:** Older buildings → higher engagement
9. **H9:** Heat type affects engagement

### Structural Hypotheses
10. **H10:** Campaigns differ in baseline open rates
11. **H11:** Energy burden effect varies by campaign
12. **H12:** Engagement varies by geography
13. **H21:** Spatial correlation exists beyond measured predictors

### Time Series Hypotheses
14. **H17:** Higher usage volatility → higher engagement
15. **H18:** Summer/winter ratio affects engagement

---

## Model Comparison Criteria

### Predictive Performance
- **LOO-CV** (Leave-One-Out Cross-Validation) - Lower is better
- **WAIC** (Widely Applicable Information Criterion) - Lower is better
- **Posterior Predictive Checks** - Calibration plots

### Interpretability
- **Coefficient Clarity** - Credible intervals don't span zero
- **Effect Sizes** - Meaningful on probability scale
- **Domain Knowledge** - Coefficients align with theory

### Practical Considerations
- **Computational Cost** - Time to fit and sample
- **Convergence** - R-hat < 1.01, good ESS
- **Operational Viability** - Can it be deployed?

---

## Quick Implementation Checklist

### Data Preparation
- [ ] Load participant + demographic + property data
- [ ] Match participants to demographics (by email/address)
- [ ] Handle missing data (-1 values, "NA" strings)
- [ ] Scale continuous predictors (z-scores)
- [ ] Encode categorical variables (heat_type, etc.)
- [ ] Create campaign and ZIP indices
- [ ] Engineer time series features

### Model Fitting Workflow
1. **Start Simple** - Fit M1-M2, check convergence
2. **Add Predictors** - Fit M3-M4, compare LOO
3. **Add Hierarchy** - Fit M5-M7, check variance decomposition
4. **Test Interactions** - Fit M8, interpret marginal effects
5. **Advanced Features** - Fit M9-M10 if warranted

### Diagnostics for Each Model
- [ ] Check R-hat < 1.01 for all parameters
- [ ] Check ESS > 400 for all parameters
- [ ] Run posterior predictive checks
- [ ] Plot trace plots (look for good mixing)
- [ ] Calculate LOO-CV (check for influential points)

### Interpretation & Reporting
- [ ] Convert coefficients to probability scale
- [ ] Calculate marginal effects at meaningful values
- [ ] Plot predicted probabilities by key predictors
- [ ] Report credible intervals (2.5%, 97.5%)
- [ ] Interpret hierarchical variance components

---

## Click Model Strategy

### Approach 1: Conditional Model (Recommended First)
**Model:** P(Click | Opened = 1)
- Filter to only participants who opened
- Use same predictor structure as open models
- **Interpretation:** What drives deeper engagement?

### Approach 2: Joint/Hurdle Model
**Model:** P(Click) = P(Open) × P(Click | Open)
- Separate coefficients for opening vs. clicking
- **Interpretation:** Are drivers different for initial vs. deep engagement?

### Approach 3: Ordinal Model
**Model:** 0=Not opened, 1=Opened, 2=Clicked
- Single set of coefficients for ordered engagement
- **Interpretation:** Engagement as progressive stages

---

## Expected Effect Directions

| Predictor | Expected Sign | Reasoning |
|-----------|---------------|-----------|
| `energy_burden` | **+** | High burden → need assistance → higher engagement |
| `income_level` | **−** | Lower income → target population → higher engagement |
| `annual_savings` | **+** | More savings → more motivation → higher engagement |
| `household_size` | **+** | More people → more impacted → higher engagement |
| `living_area` | **+** | Larger home → more savings potential → higher engagement |
| `age` (building) | **+** | Older → less efficient → more need → higher engagement |
| `has_mobile` | **+** | Mobile → tech-savvy → higher engagement |
| `usage_volatility` | **+** | Variable bills → uncertainty → higher engagement |

**Note:** These are hypotheses to test, not assumptions!

---

## Computational Notes

### Sampling Settings (Conservative)
```python
pm.sample(
    draws=2000,        # Posterior samples per chain
    tune=1000,         # Burn-in samples (simple models)
    tune=1500-2000,    # Burn-in (hierarchical models)
    chains=4,          # Parallel chains
    target_accept=0.95 # High acceptance (reduces divergences)
)
```

### Expected Sampling Times (Rough Estimates)
- **M1-M4:** 2-5 minutes (simple logistic regression)
- **M5-M7:** 10-30 minutes (hierarchical models)
- **M8:** 20-40 minutes (interactions + hierarchy)
- **M9:** 30-60 minutes (more predictors)
- **M10:** 60-120 minutes (spatial CAR model)

**Hardware:** Times assume modern multi-core CPU, adjust accordingly

---

## Common Issues & Solutions

### Divergences
**Problem:** Divergent transitions during sampling
**Solutions:**
1. Increase `target_accept` to 0.99
2. Use non-centered parameterization (already in models)
3. Increase `tune` to 2000-3000
4. Check for prior-data conflict (adjust priors)

### Low ESS
**Problem:** Effective Sample Size < 400
**Solutions:**
1. Increase `draws` to 3000-4000
2. Check for high correlation between parameters
3. Center/scale predictors more carefully
4. Consider reparameterization

### Convergence (R-hat > 1.01)
**Problem:** Chains haven't converged
**Solutions:**
1. Increase `tune` and `draws`
2. Check initialization (use `init='adapt_diag'`)
3. Inspect trace plots for stuck chains
4. Consider simpler model structure

---

## Output Interpretation Example

```python
# After fitting Model 7 (Full Hierarchical)
import arviz as az

# Summary statistics
summary = az.summary(trace_7, var_names=["beta_burden", "beta_income"])
print(summary)

# Expected output:
#                mean     sd  hdi_3%  hdi_97%  ess_bulk  ess_tail  r_hat
# beta_burden    0.42   0.08    0.28     0.56    3200      2800    1.00
# beta_income   -0.15   0.06   -0.26    -0.04    3500      3100    1.00

# Interpretation:
# - Energy burden positive effect: OR = exp(0.42) = 1.52
#   (1 SD increase in burden → 52% higher odds of opening)
# - Income negative effect: OR = exp(-0.15) = 0.86
#   (1 SD increase in income → 14% lower odds of opening)
# - Both effects credibly non-zero (95% CI excludes 0)
```

---

## Next Steps Decision Tree

```
Have you fit any models yet?
├─ No → Start with M2 (Energy Burden + Demographics)
└─ Yes → What did you find?
    ├─ Burden effect not significant → Check data quality, try interactions
    ├─ Burden effect significant → Add hierarchy (M5-M7)
    ├─ Models similar → Report simplest model (parsimony)
    └─ Need better predictions → Add complexity (M8-M10)
```

---

**See full details in:** `BAYESIAN_MODELING_PROGRESSION.md`
