# Analysis-04: Applicant-Centric Cluster Analysis

**Date**: December 8, 2025
**Objective**: Understand what drives program applications for Bayesian causal modeling

---

## Executive Summary

This analysis identified key factors driving program applications across 7,473 campaign participants, of which 240 (3.21%) converted to applicants.

### Key Findings

1. **Text campaigns drive higher conversions**:
   - Letter+Text only: **4.29%** application rate (1.34x lift)
   - Letter+Email only: **1.42%** application rate (0.44x lift)
   - Naive text effect: **+2.62 percentage points**

2. **Demographics matter but channel matters more**:
   - Phase 1 (demographics only): 1.62% spread in application rates
   - Phase 2 (+ channel exposure): 98.58% spread
   - Adding channel features dramatically improves segmentation

3. **High-value segments identified**:
   - Cluster 0 (Phase 3): 23.44% app rate, 7.3x lift
   - Cluster 3 (Phase 3): 7.89% app rate, 2.5x lift

---

## Methodology

### Three-Phase Progressive Clustering

| Phase | Features | Method | Clusters | Key Insight |
|-------|----------|--------|----------|-------------|
| 1 | Demographics only | FAMD + K-Means | 5 | Baseline: demographics predict moderately |
| 2 | + Channel exposure + Message types | FAMD + K-Means | 6 | Channel combo is strongest predictor |
| 3 | Same as Phase 2 | Bayesian GMM | 10 | Soft assignments for causal modeling |

### Data Sources

- **Participants**: 7,473 from campaign_data MongoDB
- **Applications**: 296 program sign-ups (240 matched to participants)
- **Campaigns**: 143 total (68 email, 74 text)
- **Baseline exposure**: Letters/mailers sent to everyone

---

## Phase 1: Demographics-Only Clustering

### Results

| Cluster | Size | App Rate | Lift |
|---------|------|----------|------|
| 2 | 4,014 (54%) | 3.84% | 1.19x |
| 1 | 657 (9%) | 3.35% | 1.04x |
| 0 | 2,798 (37%) | 2.22% | 0.69x |

**Chi-square test**: p < 0.001 (significant)

### Interpretation

Demographics alone show modest predictive power. Higher-income households and larger dwelling sizes correlate slightly with higher application rates.

---

## Phase 2: Demographics + Campaign Exposure

### Results

| Cluster | Channel Mix | App Rate | Lift | Campaigns |
|---------|-------------|----------|------|-----------|
| 5 | Letter+Text only | **4.29%** | 1.34x | 7.8 |
| 0 | Letter+Email+Text | 3.92% | 1.22x | 25.8 |
| 3 | Letter+Email+Text (high) | 3.91% | 1.22x | 59.8 |
| 2 | Letter+Email (71%) | 3.15% | 0.98x | 37.1 |
| 1 | Letter+Email only (98%) | **1.42%** | 0.44x | 15.3 |

**Chi-square test**: p < 10^-149 (highly significant)

### Key Insights

1. **Text-only recipients (Cluster 5)** have the highest application rate among non-outlier clusters
2. **Email-only recipients (Cluster 1)** have the lowest application rate
3. Adding email to text reduces slightly (3.81% vs 4.29%)
4. Campaign volume shows diminishing returns (Cluster 3 with 60 campaigns doesn't outperform)

---

## Phase 3: Probabilistic Clustering

### Results (for Bayesian Modeling)

| Cluster | Size | App Rate | Lift | Notes |
|---------|------|----------|------|-------|
| 0 | 448 | 23.44% | 7.3x | Super-converters |
| 3 | 545 | 7.89% | 2.5x | High propensity |
| 4 | 436 | 3.90% | 1.2x | Near baseline |
| 8 | 462 | 3.25% | 1.0x | Near baseline |
| 5-9 | 4,582 | 0-2% | <1x | Low propensity |

### Output for PyMC

- `phase3_bayesian_integration.parquet`: Main data with treatment indicators
- `phase3_cluster_probs.npy`: Soft cluster assignments (K-1 columns)
- `phase3_pymc_summary.json`: Metadata for model setup

---

## Treatment Effect Analysis

### Naive Comparison (Unconditioned)

| Treatment Group | N | App Rate | Difference vs Email-only |
|-----------------|---|----------|-------------------------|
| Text only | 373 | 4.29% | +2.62 pp |
| Email only | 3,170 | 1.67% | baseline |
| Both | 3,908 | 3.81% | +2.14 pp |

### Caution: Selection Bias

These are **observational** differences. People who received text campaigns may differ systematically from email-only recipients. Bayesian causal modeling is needed to:

1. Adjust for demographic confounders
2. Account for cluster membership
3. Estimate true causal effect of text campaigns

---

## Conversion Channel Attribution (UTM)

For the 240 matched applicants:

| Conversion Channel | N | % of Applicants |
|-------------------|---|-----------------|
| Text | 111 | 46.2% |
| Unknown | 69 | 28.8% |
| Letter | 60 | 25.0% |

Nearly half of applicants converted through text messaging.

---

## Recommendations for Bayesian Causal Modeling

### 1. Treatment Effect Model

```python
# Recommended PyMC model structure
with pm.Model() as causal_model:
    # Use cluster probabilities as covariates
    cluster_effect = pm.Normal('cluster_effect', mu=0, sigma=1, shape=K-1)

    # Treatment effect (text campaigns)
    text_effect = pm.Normal('text_effect', mu=0, sigma=1)

    # Outcome model
    p = pm.math.sigmoid(
        cluster_probs @ cluster_effect +
        text_treatment * text_effect +
        ...
    )
    observed = pm.Bernoulli('applied', p=p, observed=y)
```

### 2. Propensity Score Adjustment

Estimate P(text treatment | demographics, prior exposure) to adjust for selection.

### 3. Stratified Analysis

Estimate treatment effects within each cluster to check for heterogeneity.

---

## Output Files

| File | Description |
|------|-------------|
| `participant_applicant_features.parquet` | Raw features (7,473 rows) |
| `phase1_clustered.parquet` | Demographics clustering |
| `phase2_clustered.parquet` | Demographics + exposure clustering |
| `phase3_bayesian_integration.parquet` | Ready for PyMC |
| `phase3_cluster_probs.npy` | Soft cluster assignments |
| `umap_*.png` | Visualizations |
| `*_cluster_stats.csv` | Cluster summaries |

---

## Visualizations

- `umap_applicant_distribution.png`: Applicants vs non-applicants
- `umap_phase3_clusters.png`: 10 probabilistic clusters
- `umap_channel_exposure.png`: Channel combination patterns
- `umap_treatment_effect.png`: Text campaign treatment visualization
- `umap_summary_dashboard.png`: Combined 4-panel dashboard

---

## Next Steps

1. **Bayesian Causal Model**: Build PyMC model using Phase 3 outputs
2. **Propensity Score**: Estimate treatment assignment mechanism
3. **Heterogeneous Effects**: Check if text effect varies by cluster
4. **Intervention Planning**: Use causal estimates to optimize channel allocation

---

*Generated by Analysis-04 Pipeline*
