# Clustering and dimensionality reduction for behavioral data with rare outcomes

Understanding population structure in mixed-type data before Bayesian causal modeling requires a carefully sequenced approach: **start with FAMD for interpretable dimensionality reduction, use K-prototypes or StepMix for mixed-data clustering, and treat cluster membership as a confounding adjustment in your causal framework**. For your 8,000 participants with ~2.5% click rates, aggregate to participant-level features and cluster on demographics first—keeping behavioral outcomes separate for validation rather than clustering inputs.

This guide walks through classical and probabilistic clustering methods, dimensionality reduction for visualization, and practical Python implementations tailored to your multi-level data structure with rare binary outcomes.

---

## Why standard K-means fails with mixed data types

K-means fundamentally assumes Euclidean distance and computes centroids as arithmetic means—both operations become meaningless with categorical variables. When campaign type is encoded as integers (1, 2, 3), K-means treats "Campaign A" as mathematically closer to "Campaign B" than to "Campaign C," creating artificial ordinal relationships that don't exist. The algorithm also struggles with scale differences: income ranging from $20K-$200K will completely dominate clustering compared to binary clicks (0/1), regardless of which features actually matter for segmentation.

For your mixed continuous/categorical data, three approaches handle this properly:

**K-prototypes** combines K-means for numeric attributes with K-modes for categorical, using a weighted cost function: `d(x,y) = Σ(x_num - y_num)² + γ × Σ(x_cat ≠ y_cat)`. The gamma parameter balances continuous versus categorical influence—with standardized numerics and only one categorical variable (campaign type), you'll likely need gamma > 1.0 to give campaign type meaningful weight.

```python
from kmodes.kprototypes import KPrototypes
from sklearn.preprocessing import StandardScaler

# Standardize continuous features
scaler = StandardScaler()
continuous_scaled = scaler.fit_transform(df[['house_size', 'house_age', 
    'participant_age', 'income_log', 'energy_burden']])

# Combine with categorical (keep as strings, not encoded)
X = np.hstack([continuous_scaled, df[['campaign_type']].values])
cat_columns = [5]  # Index of campaign_type

kproto = KPrototypes(n_clusters=5, init='Cao', n_init=10, gamma=1.5)
clusters = kproto.fit_predict(X, categorical=cat_columns)
```

**Gower distance** normalizes each feature to [0,1] using range for continuous variables and simple matching (0=same, 1=different) for categorical, then averages across features. This works with hierarchical clustering or HDBSCAN but requires computing an **8,000 × 8,000 distance matrix** (~512MB)—manageable but slow. Use this for exploratory analysis where you want to discover natural groupings without pre-specifying cluster count.

**HDBSCAN with Gower** automatically determines cluster count and identifies outliers, making it excellent for exploratory work:

```python
import hdbscan
import gower

dist_matrix = gower.gower_matrix(df[features])
clusterer = hdbscan.HDBSCAN(metric='precomputed', min_cluster_size=80)
labels = clusterer.fit_predict(dist_matrix)
```

---

## Handling the 2.5% click rate in clustering

With only ~200 clickers among 8,000 participants, standard clustering will create segments dominated by non-clicker patterns—clickers scatter across all clusters rather than forming distinct groups. This isn't necessarily a problem; it's actually the **correct approach for causal inference**.

**Cluster on pre-treatment features, then characterize by outcomes.** This means clustering participants using demographics and campaign exposure *without* including clicks as a clustering variable, then analyzing click rates across the resulting clusters:

```python
# Cluster WITHOUT outcome variables
clustering_features = ['house_size', 'house_age', 'participant_age', 
                       'income', 'energy_burden', 'campaign_type']
df['cluster'] = kproto.fit_predict(X[clustering_features], categorical=[5])

# Then analyze outcomes by cluster
cluster_stats = df.groupby('cluster').agg({
    'clicks': ['sum', 'mean', 'count'],
    'income': 'mean',
    'energy_burden': 'mean'
})

# Test if clusters differ significantly on click rates
from scipy.stats import chi2_contingency
contingency = pd.crosstab(df['cluster'], df['clicks'])
chi2, p_value, _, _ = chi2_contingency(contingency)
```

This approach treats clusters as **pre-treatment heterogeneity strata**—analogous to propensity score subclassification. If clusters show significantly different click rates, you've identified treatment effect heterogeneity worth exploring in your Bayesian model. If click rates are similar across clusters, demographics may not drive response variation, pointing toward campaign-specific factors instead.

---

## FAMD for mixed-data dimensionality reduction

Factor Analysis of Mixed Data (FAMD) is the optimal choice for your data because it correctly handles both continuous and categorical variables in a single framework. FAMD standardizes continuous variables (preventing scale dominance), applies optimal scaling to categorical variables, and finds components that capture variance across both types simultaneously.

```python
import prince

# FAMD handles mixed data automatically
famd = prince.FAMD(n_components=5, n_iter=3, random_state=42)
famd = famd.fit(df[['house_size', 'house_age', 'participant_age', 
                    'income', 'energy_burden', 'campaign_type']])

# Check which variables drive each component
print(famd.column_contributions_.style.format('{:.0%}'))

# Get coordinates for visualization or further analysis
famd_coords = famd.row_coordinates(df)
```

The **column contributions** table reveals which original variables drive each FAMD component—essential for interpretability. If component 1 shows high contributions from income and house_size, that dimension captures socioeconomic status. This interpretability directly supports your causal modeling by identifying which latent dimensions might confound treatment effects.

For **PCA on continuous variables only**, use it when you want maximum interpretability and your categorical variable (campaign_type) represents treatment rather than baseline characteristic:

```python
from sklearn.decomposition import PCA

pca = PCA(n_components=3)
continuous_pca = pca.fit_transform(df[continuous_cols])
print(f"Variance explained: {pca.explained_variance_ratio_.cumsum()}")
```

---

## Visualizing 8,000 participants with UMAP

For final 2D visualization, UMAP outperforms t-SNE for your dataset size: it's faster, better preserves global structure, and produces more reproducible results. The key insight from recent research is that **initialization matters more than algorithm choice**—both UMAP and t-SNE perform similarly with PCA initialization.

```python
from umap import UMAP

# Run UMAP on FAMD coordinates (not raw data)
umap_model = UMAP(
    n_neighbors=15,     # Balance local/global; try 10, 15, 30
    min_dist=0.1,       # 0.0 = tight clusters, 0.5 = spread out
    n_components=2,
    metric='euclidean',
    random_state=42
)
X_2d = umap_model.fit_transform(famd_coords)
```

**Critical visualization technique for rare outcomes**: With 2.5% clickers, default scatter plots will hide them completely. Plot non-clickers first with small, transparent markers, then overlay clickers with large, opaque markers:

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 8))

# Background: non-clickers (97.5%)
non_click = df['clicks'] == 0
ax.scatter(X_2d[non_click, 0], X_2d[non_click, 1],
           c='lightgray', s=5, alpha=0.3, label=f'Non-clickers (n={non_click.sum():,})')

# Foreground: clickers (2.5%)
click = df['clicks'] == 1
ax.scatter(X_2d[click, 0], X_2d[click, 1],
           c='red', s=40, alpha=0.9, label=f'Clickers (n={click.sum():,})')

ax.legend()
ax.set_title('FAMD + UMAP: Clickers Highlighted')
```

This reveals whether clickers concentrate in specific regions (suggesting clusterable engagement patterns) or scatter uniformly (suggesting click behavior is orthogonal to demographic segmentation).

---

## Probabilistic clustering with StepMix connects to Bayesian frameworks

**StepMix** is the recommended probabilistic approach because it natively handles mixed continuous/categorical data and provides soft cluster assignments (posterior probabilities) that integrate directly into Bayesian causal models. Unlike GMM (which assumes Gaussian distributions inappropriate for categorical data) or traditional LCA (designed for categorical-only data), StepMix combines Latent Profile Analysis for continuous variables with Latent Class Analysis for categorical.

```python
from stepmix.stepmix import StepMix

# Model selection: compare BIC across different cluster counts
results = []
for k in range(2, 8):
    model = StepMix(n_components=k, n_init=20, random_state=42)
    model.fit(X)
    results.append({'k': k, 'bic': model.bic(X), 'aic': model.aic(X)})

# Select model with lowest BIC
optimal_k = min(results, key=lambda x: x['bic'])['k']

# Fit final model
final_model = StepMix(n_components=optimal_k, n_init=50, random_state=42)
final_model.fit(X)

# Soft assignments preserve uncertainty
cluster_probs = final_model.predict_proba(X)  # Shape: (8000, K)
```

**Integrating cluster probabilities into Bayesian causal models**: Rather than using hard cluster assignments (which discard uncertainty), include the K-1 probability columns as covariates. This performs dimensionality reduction while preserving classification uncertainty:

```python
import pymc as pm

with pm.Model() as causal_model:
    # Cluster membership adjustment (K-1 probabilities)
    beta_cluster = pm.Normal('beta_cluster', mu=0, sigma=1, shape=optimal_k-1)
    
    # Treatment effect of interest
    beta_treatment = pm.Normal('beta_treatment', mu=0, sigma=1)
    
    # Linear predictor
    logit_p = (
        pm.math.dot(cluster_probs[:, :-1], beta_cluster) +
        beta_treatment * treatment
    )
    
    # Rare binary outcome
    clicks = pm.Bernoulli('clicks', logit_p=logit_p, observed=df['clicks'])
    
    trace = pm.sample(2000, tune=1000)
```

For **automatic cluster number selection**, use sklearn's BayesianGaussianMixture with a Dirichlet process prior—it prunes unused components automatically:

```python
from sklearn.mixture import BayesianGaussianMixture

bgmm = BayesianGaussianMixture(
    n_components=10,  # Upper bound
    weight_concentration_prior_type='dirichlet_process',
    weight_concentration_prior=0.1,  # Lower = fewer active clusters
    random_state=42
)
bgmm.fit(X_continuous)  # GMM only for continuous variables
effective_k = (bgmm.weights_ > 0.01).sum()
```

---

## The multi-level structure requires participant-level aggregation

Your 126,000 observations from 8,000 participants violate the independence assumption underlying standard clustering algorithms. Clustering at the observation level would give disproportionate influence to participants with 50+ campaigns while participants with single campaigns contribute minimally. More fundamentally, observations within a participant are correlated, inflating apparent cluster sizes artificially.

**Aggregate to participant level (N=8,000)** before clustering:

| Feature Category | Aggregated Variables |
|------------------|---------------------|
| Demographics | House size, house age, age, income, energy burden (static) |
| Campaign Exposure | Total campaigns, unique types, date range, type distribution |
| Behavioral Summary | Click rate, ever-clicked binary, click recency |

**Handling click rate with varying exposure**: A participant with 1 campaign and 0 clicks has 0% rate, but so does someone with 50 campaigns and 0 clicks—yet these represent different evidence strengths. Consider variance-weighted estimates or empirical Bayes shrinkage:

```python
# Simple approach: weight by campaign count
df_participant = df.groupby('participant_id').agg({
    'clicks': ['sum', 'count'],
    'house_size': 'first',
    'income': 'first',
    # ... other demographics
})
df_participant['click_rate'] = df_participant[('clicks', 'sum')] / df_participant[('clicks', 'count')]
df_participant['campaign_count'] = df_participant[('clicks', 'count')]

# For clustering, consider binary "ever clicked" for stability
df_participant['ever_clicked'] = (df_participant[('clicks', 'sum')] > 0).astype(int)
```

---

## Progressive analysis strategy builds interpretable understanding

Rather than clustering all variables simultaneously, build understanding progressively:

**Phase 1 (Demographics only)**: Cluster on house_size, house_age, participant_age, income, energy_burden. These are pre-treatment variables that existed before any campaign exposure. Expected outcome: **3-5 interpretable demographic segments** (e.g., "young renters with high energy burden," "established homeowners," "seniors in older housing").

**Phase 2 (Add campaign exposure)**: Include total campaigns received, campaign type mix, exposure duration. This reveals whether certain demographic segments receive systematically different campaign portfolios—a selection effect relevant to causal inference.

**Phase 3 (Overlay behavioral outcomes)**: Now examine click rates *within* the clusters from Phases 1-2. Do demographic segments show different engagement? Does campaign type effectiveness vary by segment?

This progression avoids **outcome contamination**—clustering on clicks first would create circular reasoning where you find "clicker segments" that are tautologically defined by clicking. Instead, finding that demographic cluster 3 has 5% click rate versus 1.5% for cluster 1 represents genuine treatment effect heterogeneity.

---

## Choosing cluster count with multiple validation methods

No single metric definitively selects K—use multiple approaches and prioritize interpretability:

**Elbow method** plots within-cluster cost versus K, looking for diminishing returns:
```python
costs = []
for k in range(2, 10):
    kp = KPrototypes(n_clusters=k, init='Cao', n_init=10)
    kp.fit_predict(X, categorical=cat_columns)
    costs.append(kp.cost_)

plt.plot(range(2, 10), costs, 'bx-')
plt.xlabel('K'); plt.ylabel('Cost')
```

**Silhouette score** measures cluster cohesion versus separation (range -1 to 1):
- \> 0.7: Strong structure
- 0.5-0.7: Reasonable structure  
- 0.25-0.5: Weak structure
- < 0.25: Little meaningful structure

```python
from sklearn.metrics import silhouette_score

for k in range(2, 10):
    labels = KPrototypes(n_clusters=k).fit_predict(X, categorical=cat_columns)
    score = silhouette_score(X_numeric, labels)
    print(f"K={k}: silhouette={score:.3f}")
```

**BIC for probabilistic models** (StepMix, GMM) provides a principled penalized likelihood—lower is better, and the penalty increases with model complexity.

**Stability analysis** tests whether clusters are robust:
```python
# Bootstrap stability
from sklearn.utils import resample
jaccard_scores = []
for _ in range(100):
    X_boot = resample(X, random_state=None)
    labels_boot = KPrototypes(n_clusters=5).fit_predict(X_boot, categorical=cat_columns)
    # Compare to original clustering using Jaccard similarity
```

Target: Jaccard similarity > 0.75 across bootstrap samples; adjusted Rand index > 0.85 across random seeds.

---

## Cluster profiling with radar charts and heatmaps

After clustering, profile each segment to understand what makes them distinct:

```python
# Compute cluster means for continuous variables
cluster_profiles = df.groupby('cluster')[continuous_cols].mean()

# Standardize for radar chart (so all variables comparable)
cluster_profiles_std = (cluster_profiles - cluster_profiles.mean()) / cluster_profiles.std()
```

**Radar chart for multi-variable cluster profiles**:
```python
import numpy as np

def radar_chart(df_profiles, cluster_id):
    categories = df_profiles.columns.tolist()
    values = df_profiles.loc[cluster_id].values.tolist()
    values += values[:1]  # Close the polygon
    
    angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.plot(angles, values, 'o-', linewidth=2)
    ax.fill(angles, values, alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories)
    ax.set_title(f'Cluster {cluster_id} Profile')
    
radar_chart(cluster_profiles_std, cluster_id=0)
```

**Heatmap of cluster characteristics**:
```python
import seaborn as sns

# Include outcome rates for interpretation (not clustering input)
profile_with_outcomes = df.groupby('cluster').agg({
    'clicks': 'mean',
    'income': 'mean',
    'energy_burden': 'mean',
    'house_age': 'mean'
})

sns.heatmap(profile_with_outcomes, annot=True, fmt='.2f', cmap='RdYlBu_r')
```

---

## Connecting clusters to causal inference goals

Your clusters serve two roles in Bayesian causal modeling:

**As confounding adjustment**: If campaign assignment correlates with participant characteristics, cluster membership captures propensity-relevant variation. Including cluster probabilities as covariates in outcome models adjusts for this confounding—similar to propensity score stratification but with interpretable segments.

**For heterogeneous treatment effect detection**: Estimate treatment effects *within* each cluster, then compare:

```python
# Within-cluster treatment effect estimation
for cluster_id in df['cluster'].unique():
    cluster_data = df[df['cluster'] == cluster_id]
    
    # Compare click rates across campaign types within cluster
    effect_by_campaign = cluster_data.groupby('campaign_type')['clicks'].mean()
    print(f"Cluster {cluster_id} (n={len(cluster_data)})")
    print(effect_by_campaign)
    print()
```

If cluster 2 shows 4% click rate for email campaigns versus 1% for SMS, while cluster 4 shows the reverse pattern, you've discovered treatment effect heterogeneity that justifies cluster-specific causal parameters in your Bayesian model.

---

## Complete pipeline summary

```python
# 1. Aggregate to participant level
df_participant = aggregate_to_participant(df)

# 2. Progressive clustering
# Phase 1: Demographics
famd = prince.FAMD(n_components=5).fit(df_participant[demographic_cols])
kproto_demo = KPrototypes(n_clusters=4, gamma=1.5)
df_participant['cluster_demo'] = kproto_demo.fit_predict(X_demo, categorical=cat_idx)

# 3. Validate clusters
silhouette = silhouette_score(X_numeric, df_participant['cluster_demo'])
click_rates_by_cluster = df_participant.groupby('cluster_demo')['click_rate'].mean()

# 4. Probabilistic refinement
stepmix = StepMix(n_components=4, n_init=50).fit(X_all)
cluster_probs = stepmix.predict_proba(X_all)

# 5. Visualization
umap_coords = UMAP(n_neighbors=15).fit_transform(famd.row_coordinates(df_participant))
plot_with_rare_class_emphasis(umap_coords, df_participant['ever_clicked'])

# 6. Integration with Bayesian model
# Use cluster_probs[:, :-1] as covariates for confounding adjustment
```

The key insight: clustering before causal modeling isn't just dimensionality reduction—it's discovering the heterogeneity structure in your population that determines whether treatment effects vary across segments. Start simple with demographics, validate that clusters predict outcomes, then use probabilistic membership to preserve uncertainty in your Bayesian framework.