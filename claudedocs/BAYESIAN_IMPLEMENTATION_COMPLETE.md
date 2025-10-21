# Bayesian Models Implementation - Complete

Implementation of hierarchical Bayesian models for email engagement prediction based on energy burden hypothesis.

---

## ✅ Implementation Status

### Models Implemented (2/10)
- ✅ **Model 1: Baseline** - Cost + savings predictors
- ✅ **Model 2: Energy Burden** - Primary hypothesis (energy burden → engagement)
- ⏳ **Model 3-10** - Available in progression documentation, ready to implement

### Core Infrastructure
- ✅ Data preparation pipeline with MongoDB integration
- ✅ Diagnostic utilities (R-hat, ESS, LOO-CV, WAIC, PPC)
- ✅ Model fitting scripts with automated outputs
- ✅ GPU verification and benchmarking
- ✅ Comprehensive documentation

---

## 📁 File Structure

```
src/bayesian_models/          # Model implementations
├── __init__.py               # Package exports
├── model_01_baseline.py      # Baseline cost + savings model
└── model_02_energy_burden.py # Energy burden hypothesis model

src/bayesian_scripts/         # Executable scripts
├── bayes_verify_gpu.py       # GPU setup verification ⭐ RUN THIS FIRST
├── bayes_debug_data.py       # MongoDB data inspection ⭐ TROUBLESHOOTING
├── bayes_fit_model_01.py     # Fit Model 1
├── bayes_fit_model_02.py     # Fit Model 2
└── __init__.py

src/bayesian_tools/           # Utilities
├── data_preparation.py       # MongoDB data loading & preprocessing
├── diagnostics.py            # Model diagnostics & validation
└── __init__.py

claudedocs/                   # Documentation
├── BAYESIAN_MODELING_PROGRESSION.md  # Full 10-model progression
├── DATA_SCHEMA_DOCUMENTATION.md      # Data schema reference
├── MODEL_PROGRESSION_SUMMARY.md      # Quick reference guide
└── BAYESIAN_IMPLEMENTATION_COMPLETE.md  # This file
```

---

## 🔧 Configuration

### Environment Variables (via `.env` file)

The implementation uses TWO MongoDB databases and reads configuration from `src/utils/envvars.py`:

```bash
# MongoDB Connection
MONGODB_HOST=localhost                    # MongoDB host (default: localhost)
MONGODB_PORT=27017                       # MongoDB port (default: 27017)

# Database Names (BOTH REQUIRED)
MONGODB_OCTOPUS=your_octopus_db_name    # Participant & campaign data
MONGODB_DATABASE=your_county_db_name    # Demographic & property data
```

**Two-Database Architecture:**
- **MONGODB_OCTOPUS**: Contains `participants` and `campaigns` collections
- **MONGODB_DATABASE**: Contains `*CountyDemographic`, `*CountyResidential`, `*CountyElectrical`, etc.

**Location:** Place `.env` file in:
- Project root directory, OR
- Home directory (`~/.env`)

### Dependencies

Install required packages:
```bash
pip install -r requirements_bayesian_gpu.txt
```

Key dependencies:
- `pymc` - Bayesian modeling framework
- `arviz` - Diagnostics and visualization
- `jax` - GPU-accelerated computation (optional but recommended)
- `pymongo` - MongoDB connection
- `scikit-learn` - Data preprocessing
- `pandas`, `numpy` - Data manipulation

---

## 🚀 Quick Start

### 1. Verify GPU Setup (Optional but Recommended)
```bash
python src/bayesian_scripts/bayes_verify_gpu.py
```

**Expected output:**
- ✅ JAX installed and GPU detected
- ✅ PyMC and ArviZ available
- ✅ Simple benchmark completes successfully

### 2. Debug Data Availability
```bash
python src/bayesian_scripts/bayes_debug_data.py
```

**What it checks:**
- MongoDB connection successful
- Participants collection exists and has data
- Campaigns collection populated
- Demographic and property collections available
- Sample engagement statistics

**If you see "No participants found":**
- Verify `MONGODB_OCTOPUS` environment variable is correct (participant data)
- Verify `MONGODB_DATABASE` environment variable is correct (demographic data)
- Check that data has been synced to MongoDB
- Run sync: `python -m src.sync.campaign_sync`

### 3. Fit Model 1 (Baseline)
```bash
python src/bayesian_scripts/bayes_fit_model_01.py
```

**Options:**
```bash
--campaign-ids ID1,ID2,ID3    # Filter to specific campaigns
--draws 2000                  # Posterior samples per chain (default: 2000)
--tune 1000                   # Burn-in samples (default: 1000)
--chains 4                    # Number of chains (default: 4)
--output-dir reports/bayes    # Output directory (default: reports/bayesian_models)
```

**Outputs:**
- `model_01_trace.nc` - Full trace (InferenceData)
- `model_01_summary.csv` - Coefficient summary
- `model_01_metadata.json` - Data metadata
- `model_01_trace.png` - Trace plots
- `model_01_posterior.png` - Posterior distributions
- `model_01_forest.png` - Forest plot
- `model_01_ppc.png` - Posterior predictive check

### 4. Fit Model 2 (Energy Burden)
```bash
python src/bayesian_scripts/bayes_fit_model_02.py
```

**Same options as Model 1, plus:**
- `model_02_marginal_effects.png` - Energy burden marginal effects plot

---

## 📊 Understanding the Output

### Convergence Diagnostics

**R-hat (Gelman-Rubin statistic):**
- ✅ < 1.01 = Converged
- ⚠️ > 1.01 = Potential convergence issues

**ESS (Effective Sample Size):**
- ✅ > 400 = Sufficient
- ⚠️ < 400 = May need more samples

### Coefficient Interpretation

**Logit scale coefficients:**
- β = 0.42 means a 1 SD increase in predictor → 0.42 increase in log-odds

**Odds Ratio (OR):**
- OR = exp(0.42) = 1.52
- Interpretation: 52% higher odds of opening email per 1 SD increase

**Credible intervals:**
- 95% HDI excludes zero → Effect is credibly non-zero
- 95% HDI includes zero → Effect inconclusive

### Model Comparison

**LOO-CV (Leave-One-Out Cross-Validation):**
- Lower is better
- Compare relative values between models
- LOO difference > 2×SE suggests meaningful improvement

**WAIC (Widely Applicable Information Criterion):**
- Lower is better
- Alternative to LOO for model comparison

---

## 🧪 Testing Hypotheses

### Primary Hypothesis (Model 2)

**H1: High energy burden (>6% of income) predicts higher email open rates**

**Check in output:**
```
HYPOTHESIS TEST RESULTS
======================
✅ PRIMARY HYPOTHESIS SUPPORTED:
   High energy burden predicts higher open rates
   Effect is credibly positive: [0.15, 0.68]
```

**If supported:**
- β_burden > 0 and 95% CI excludes zero
- Odds ratio > 1.0
- Can conclude: Energy burden drives engagement

**If not supported:**
- Either negative effect or CI includes zero
- May need to explore interactions or hierarchical structure

---

## 🔍 Troubleshooting

### "No participants found"

**Problem:** `load_participants()` returns empty DataFrame

**Solutions:**
1. Run debug script: `python src/bayesian_scripts/bayes_debug_data.py`
2. Check environment variables:
   - `echo $MONGODB_OCTOPUS` (should have participant/campaign data)
   - `echo $MONGODB_DATABASE` (should have demographic/property data)
3. Verify data synced: Count documents in `participants` collection
4. Sync data if needed: `python -m src.sync.campaign_sync`

### "Divergent transitions"

**Problem:** Warning about divergent transitions during sampling

**Solutions:**
1. Increase `target_accept`: Change from 0.95 to 0.99
2. Increase `tune`: Change from 1000 to 2000
3. Check for multicollinearity in predictors
4. Consider reparameterization (already using non-centered)

### "Low ESS"

**Problem:** Effective sample size < 400

**Solutions:**
1. Increase `draws`: Change from 2000 to 3000-4000
2. Check trace plots for mixing issues
3. Increase `tune` for better adaptation
4. Check for high parameter correlation

### "Model won't converge"

**Problem:** R-hat > 1.01 persists

**Solutions:**
1. Increase both `tune` and `draws`
2. Check data quality (missing values, outliers)
3. Try different initialization: `init='adapt_diag'`
4. Simplify model structure temporarily
5. Inspect trace plots for stuck chains

### GPU not detected

**Problem:** JAX uses CPU instead of GPU

**Solutions:**
1. Install GPU-enabled JAX:
   ```bash
   pip install --upgrade jax[cuda12]
   ```
2. Verify CUDA installation: `nvidia-smi`
3. Check CUDA version compatibility with JAX
4. CPU fallback is fine but slower

---

## 📈 Next Steps

### Implement Additional Models

**Model 3: Demographics** (Next recommended)
- Add has_mobile predictor
- ~10 minutes additional implementation
- Tests hypothesis about tech-savviness

**Model 4: Property Characteristics**
- Add living_area, age, heat_type
- Tests physical property impacts
- ~15 minutes implementation

**Model 5-7: Hierarchical Models**
- Campaign-level random effects
- Geographic clustering
- ~30-60 minutes each
- Requires understanding of hierarchical modeling

### Model Comparison Workflow

1. Fit Model 1 (baseline)
2. Fit Model 2 (energy burden)
3. Compare using LOO-CV
4. If Model 2 significantly better → energy burden matters
5. Proceed to Model 3 to check demographic confounding
6. Continue progression based on LOO improvements

### Reporting Results

**For each model, report:**
- Convergence diagnostics (R-hat, ESS)
- Coefficient estimates with 95% CI
- Odds ratios with interpretation
- Model comparison metrics (LOO, WAIC)
- Posterior predictive check results

**Final analysis should include:**
- Best model based on LOO-CV
- Effect sizes on probability scale
- Marginal effects plots
- Predictions for key subgroups
- Practical implications for targeting

---

## 📚 Documentation References

- **Model Progression:** `claudedocs/BAYESIAN_MODELING_PROGRESSION.md`
- **Data Schema:** `claudedocs/DATA_SCHEMA_DOCUMENTATION.md`
- **Quick Reference:** `claudedocs/MODEL_PROGRESSION_SUMMARY.md`
- **PyMC Docs:** https://www.pymc.io/
- **ArviZ Docs:** https://arviz-devs.github.io/arviz/

---

## 🤝 Support

**Issues with implementation:**
1. Check troubleshooting section above
2. Run debug script to verify data
3. Review documentation for model details
4. Check convergence diagnostics output

**Model interpretation questions:**
- See Quick Reference guide for hypothesis list
- Check coefficient interpretation examples
- Review expected effect directions table

---

**Implementation Status:** ✅ Ready for production use
**Last Updated:** 2025-10-20
**Version:** 1.0.0
