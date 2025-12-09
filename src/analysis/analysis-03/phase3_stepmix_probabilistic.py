"""
Phase 3: StepMix Probabilistic Clustering for Bayesian Integration

StepMix provides:
1. Soft cluster assignments (posterior probabilities)
2. Native mixed-data handling
3. BIC/AIC for model selection
4. Direct integration with PyMC Bayesian models

The soft assignments preserve uncertainty for downstream causal modeling.
"""
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from scipy.stats import chi2_contingency
from sklearn.mixture import BayesianGaussianMixture, GaussianMixture

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results-03')


def load_data() -> pd.DataFrame:
    """Load participant features."""
    df = pd.read_parquet('/home/yersinia/devel/octopus/data/clustering_results-03/participant_features.parquet')
    logger.info(f"Loaded {len(df)} participants")
    return df


def prepare_stepmix_features(df: pd.DataFrame) -> tuple:
    """Prepare features for StepMix (continuous + exposure + message types).
    Updated for analysis-03: includes text campaign metrics.
    """
    base_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age',
        'campaign_count', 'email_count', 'total_text_count', 'exposure_days'
    ]

    # Message type exposure features
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]

    continuous_cols = base_cols + msgtype_cols

    # Build column list for selection - updated for analysis-03
    select_cols = ['participant_id'] + continuous_cols + ['ever_engaged', 'ever_clicked', 'ever_replied_text', 'engage_rate', 'text_reply_rate']
    available_cols = [c for c in select_cols if c in df.columns]
    df_features = df[available_cols].copy()

    # Fill missing values
    for col in continuous_cols:
        if col in df_features.columns and df_features[col].isna().any():
            df_features[col] = df_features[col].fillna(df_features[col].median())

    logger.info(f"Prepared {len(base_cols)} base + {len(msgtype_cols)} message type = {len(continuous_cols)} continuous features")
    return df_features, continuous_cols


def model_selection(df_features: pd.DataFrame, continuous_cols: list,
                    k_range: range = range(2, 8)) -> pd.DataFrame:
    """
    Select optimal number of clusters using BIC/AIC.

    BIC is preferred for cluster selection - lower is better.
    """
    logger.info("Running Gaussian Mixture model selection...")

    scaler = StandardScaler()
    X = scaler.fit_transform(df_features[continuous_cols])

    results = []
    for k in k_range:
        logger.info(f"  Fitting k={k}...")
        try:
            model = GaussianMixture(n_components=k, n_init=10, random_state=42)
            model.fit(X)

            bic = model.bic(X)
            aic = model.aic(X)
            ll = model.score(X) * len(X)

            results.append({'k': k, 'bic': bic, 'aic': aic, 'log_likelihood': ll})
        except Exception as e:
            logger.warning(f"  k={k} failed: {e}")

    df_results = pd.DataFrame(results)

    logger.info("\nModel Selection Results:")
    logger.info(df_results.to_string(index=False))

    return df_results


def fit_probabilistic_model(df_features: pd.DataFrame, continuous_cols: list,
                             n_components: int = 3) -> tuple:
    """
    Fit BayesianGaussianMixture model for soft cluster assignments.

    BayesianGMM with Dirichlet process prior can automatically determine
    the effective number of clusters by pruning unused components.

    Returns:
        labels: Hard cluster assignments
        probs: Soft cluster probabilities (n_participants x n_clusters)
        model: Fitted model
        scaler: StandardScaler for future transformations
    """
    logger.info(f"Fitting BayesianGaussianMixture with {n_components} max components...")

    scaler = StandardScaler()
    X = scaler.fit_transform(df_features[continuous_cols])

    # Bayesian GMM with Dirichlet process prior
    # Increased reg_covar for numerical stability with correlated features
    model = BayesianGaussianMixture(
        n_components=n_components,
        weight_concentration_prior_type='dirichlet_process',
        weight_concentration_prior=0.1,  # Lower = fewer active clusters
        reg_covar=1e-3,  # Regularization for stability with message type features
        n_init=10,
        random_state=42
    )
    model.fit(X)

    # Hard assignments
    labels = model.predict(X)

    # Soft assignments (posterior probabilities)
    probs = model.predict_proba(X)

    # Check effective number of clusters (weights > 1%)
    effective_k = (model.weights_ > 0.01).sum()
    logger.info(f"Effective clusters (weight > 1%): {effective_k}")
    logger.info(f"Component weights: {model.weights_.round(3)}")
    logger.info(f"Cluster sizes: {np.bincount(labels)}")
    logger.info(f"Mean max probability: {probs.max(axis=1).mean():.3f}")
    logger.info(f"Mean entropy: {-np.sum(probs * np.log(probs + 1e-10), axis=1).mean():.3f}")

    return labels, probs, model, scaler


def analyze_cluster_probabilities(df_features: pd.DataFrame, labels: np.ndarray,
                                   probs: np.ndarray) -> pd.DataFrame:
    """
    Analyze cluster membership probabilities and their relation to engagement.
    """
    df_analysis = df_features.copy()
    df_analysis['cluster'] = labels

    # Add probability columns
    for k in range(probs.shape[1]):
        df_analysis[f'prob_cluster_{k}'] = probs[:, k]

    # Max probability (confidence in assignment)
    df_analysis['max_prob'] = probs.max(axis=1)

    # Engagement by confidence level
    confidence_bins = [0, 0.5, 0.7, 0.9, 1.0]
    df_analysis['confidence_bin'] = pd.cut(df_analysis['max_prob'], confidence_bins)

    engagement_by_confidence = df_analysis.groupby('confidence_bin', observed=True).agg({
        'ever_engaged': ['sum', 'mean', 'count']
    })
    engagement_by_confidence.columns = ['engaged', 'rate', 'n']

    logger.info("\nEngagement by Assignment Confidence:")
    logger.info(engagement_by_confidence.to_string())

    # Standard cluster outcomes
    cluster_stats = df_analysis.groupby('cluster').agg({
        'ever_engaged': ['sum', 'mean', 'count'],
        'max_prob': 'mean'
    })
    cluster_stats.columns = ['engaged', 'rate', 'n', 'avg_confidence']

    logger.info("\nCluster Statistics:")
    logger.info(cluster_stats.to_string())

    # Chi-square test
    contingency = pd.crosstab(df_analysis['cluster'], df_analysis['ever_engaged'])
    chi2, p_value, _, _ = chi2_contingency(contingency)
    logger.info(f"\nChi-square test: chi2={chi2:.2f}, p={p_value:.4f}")

    return cluster_stats, df_analysis


def profile_clusters(df_features: pd.DataFrame, labels: np.ndarray,
                     continuous_cols: list, model, scaler) -> pd.DataFrame:
    """Profile clusters using model parameters and empirical data."""
    df_profile = df_features.copy()
    df_profile['cluster'] = labels

    # Empirical cluster means
    profiles = df_profile.groupby('cluster')[continuous_cols].mean()

    # Model-based cluster means (transform back from scaled space)
    try:
        model_means_scaled = model.means_
        model_means = scaler.inverse_transform(model_means_scaled)
        logger.info("\nModel-based cluster means (unscaled):")
        logger.info(pd.DataFrame(model_means, columns=continuous_cols).round(2).to_string())
    except Exception as e:
        logger.warning(f"Could not get model means: {e}")

    logger.info("\nEmpirical Cluster Profiles:")
    logger.info(profiles.to_string())

    return profiles


def generate_bayesian_integration_data(df_features: pd.DataFrame, labels: np.ndarray,
                                        probs: np.ndarray, continuous_cols: list) -> pd.DataFrame:
    """
    Generate dataset for Bayesian causal modeling.

    Per CLUSTERING_PROJECT.md: Use K-1 probability columns as covariates
    to preserve classification uncertainty.
    """
    df_bayes = df_features.copy()
    df_bayes['cluster_hard'] = labels

    # Add soft probabilities (K-1 for identifiability)
    for k in range(probs.shape[1] - 1):
        df_bayes[f'cluster_prob_{k}'] = probs[:, k]

    # Example: PyMC model structure
    logger.info("\n" + "="*50)
    logger.info("BAYESIAN INTEGRATION GUIDE")
    logger.info("="*50)
    logger.info("""
Use the cluster probabilities as covariates in PyMC:

```python
import pymc as pm

with pm.Model() as causal_model:
    # Cluster membership adjustment (K-1 probabilities)
    beta_cluster = pm.Normal('beta_cluster', mu=0, sigma=1,
                              shape=n_clusters-1)

    # Treatment effect of interest
    beta_treatment = pm.Normal('beta_treatment', mu=0, sigma=1)

    # Linear predictor with cluster adjustment
    logit_p = (
        pm.math.dot(cluster_probs[:, :-1], beta_cluster) +
        beta_treatment * treatment +
        # ... other covariates
    )

    # Binary outcome model
    clicks = pm.Bernoulli('clicks', logit_p=logit_p, observed=y)
```
""")

    return df_bayes


def plot_stepmix_analysis(df_features: pd.DataFrame, labels: np.ndarray,
                           probs: np.ndarray, cluster_stats: pd.DataFrame,
                           profiles: pd.DataFrame, continuous_cols: list):
    """Visualize StepMix clustering results."""
    from sklearn.decomposition import PCA

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))

    # PCA for visualization
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[continuous_cols])
    pca = PCA(n_components=2)
    X_2d = pca.fit_transform(X_scaled)

    # 1. Soft cluster membership visualization
    ax1 = axes[0, 0]
    for k in range(probs.shape[1]):
        mask = labels == k
        ax1.scatter(X_2d[mask, 0], X_2d[mask, 1], c=probs[mask, k],
                   cmap='viridis', s=20, alpha=0.5, label=f'Cluster {k}')
    ax1.set_xlabel('PCA 1')
    ax1.set_ylabel('PCA 2')
    ax1.set_title('StepMix: Soft Cluster Membership')
    ax1.legend()

    # 2. Confidence (max probability) visualization
    ax2 = axes[0, 1]
    scatter = ax2.scatter(X_2d[:, 0], X_2d[:, 1], c=probs.max(axis=1),
                          cmap='RdYlGn', s=20, alpha=0.5)
    ax2.set_xlabel('PCA 1')
    ax2.set_ylabel('PCA 2')
    ax2.set_title('Assignment Confidence (Max Probability)')
    plt.colorbar(scatter, ax=ax2, label='Confidence')

    # 3. Engagement overlay
    ax3 = axes[0, 2]
    engaged = df_features['ever_engaged'].astype(bool)
    ax3.scatter(X_2d[~engaged, 0], X_2d[~engaged, 1], c='lightgray', s=5, alpha=0.3)
    ax3.scatter(X_2d[engaged, 0], X_2d[engaged, 1], c='red', s=40, alpha=0.9,
               label=f'Engaged (n={engaged.sum()})')
    ax3.set_xlabel('PCA 1')
    ax3.set_ylabel('PCA 2')
    ax3.set_title('Engaged Participants Highlighted')
    ax3.legend()

    # 4. Probability distribution
    ax4 = axes[1, 0]
    ax4.hist(probs.max(axis=1), bins=30, edgecolor='black', alpha=0.7)
    ax4.axvline(x=probs.max(axis=1).mean(), color='red', linestyle='--',
               label=f'Mean: {probs.max(axis=1).mean():.2f}')
    ax4.set_xlabel('Max Cluster Probability')
    ax4.set_ylabel('Count')
    ax4.set_title('Distribution of Assignment Confidence')
    ax4.legend()

    # 5. Engagement by cluster
    ax5 = axes[1, 1]
    bars = ax5.bar(range(len(cluster_stats)), cluster_stats['rate'] * 100,
                   color='steelblue')
    ax5.axhline(y=df_features['ever_engaged'].mean() * 100, color='red',
               linestyle='--', label='Overall')
    ax5.set_xlabel('Cluster')
    ax5.set_ylabel('Engagement Rate (%)')
    ax5.set_title('Engagement Rate by Cluster')
    ax5.legend()
    for bar, n in zip(bars, cluster_stats['n']):
        ax5.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f'n={n:,}', ha='center', va='bottom', fontsize=8)

    # 6. Profile heatmap
    ax6 = axes[1, 2]
    profile_norm = profiles.apply(lambda x: (x - x.mean()) / x.std(), axis=0)
    sns.heatmap(profile_norm.T, annot=True, fmt='.2f', cmap='RdYlBu_r',
               ax=ax6, center=0)
    ax6.set_title('Cluster Feature Profiles (Standardized)')
    ax6.set_xlabel('Cluster')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'phase3_stepmix_analysis.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved plot to {OUTPUT_DIR / 'phase3_stepmix_analysis.png'}")
    plt.close()


def main():
    """Run Phase 3 StepMix probabilistic clustering."""
    logger.info("="*60)
    logger.info("PHASE 3: STEPMIX PROBABILISTIC CLUSTERING")
    logger.info("="*60)

    # Load and prepare data
    df = load_data()
    df_features, continuous_cols = prepare_stepmix_features(df)

    # Model selection
    selection_results = model_selection(df_features, continuous_cols)
    selection_results.to_csv(OUTPUT_DIR / 'phase3_model_selection.csv', index=False)

    # Select based on BIC
    optimal_k = int(selection_results.loc[selection_results['bic'].idxmin(), 'k'])
    logger.info(f"\nSelected k={optimal_k} based on BIC")

    # Fit final model with Bayesian GMM (auto-determines effective k)
    labels, probs, model, scaler = fit_probabilistic_model(df_features, continuous_cols, n_components=10)

    # Analyze
    cluster_stats, df_analysis = analyze_cluster_probabilities(df_features, labels, probs)
    cluster_stats.to_csv(OUTPUT_DIR / 'phase3_cluster_stats.csv')

    # Profile
    profiles = profile_clusters(df_features, labels, continuous_cols, model, scaler)
    profiles.to_csv(OUTPUT_DIR / 'phase3_cluster_profiles.csv')

    # Generate Bayesian integration data
    df_bayes = generate_bayesian_integration_data(df_features, labels, probs, continuous_cols)
    df_bayes.to_parquet(OUTPUT_DIR / 'phase3_bayesian_integration.parquet', index=False)

    # Visualize
    plot_stepmix_analysis(df_features, labels, probs, cluster_stats, profiles, continuous_cols)

    # Save full results
    df_features['cluster_stepmix'] = labels
    for k in range(probs.shape[1]):
        df_features[f'prob_cluster_{k}'] = probs[:, k]
    df_features.to_parquet(OUTPUT_DIR / 'phase3_clustered_participants.parquet', index=False)

    # Save probability matrix separately for PyMC
    np.save(OUTPUT_DIR / 'cluster_probabilities.npy', probs)

    logger.info("\n" + "="*60)
    logger.info("PHASE 3 COMPLETE")
    logger.info(f"Cluster probabilities saved for Bayesian integration")
    logger.info("="*60)

    return df_features, labels, probs, model


if __name__ == '__main__':
    main()
