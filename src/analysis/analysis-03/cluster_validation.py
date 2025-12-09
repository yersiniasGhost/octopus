"""
Cluster Validation and Stability Analysis

Validates clustering results using:
1. Silhouette analysis
2. Bootstrap stability testing
3. Outcome predictive power comparison
4. Cross-phase agreement analysis
"""
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, silhouette_samples, adjusted_rand_score
from sklearn.cluster import KMeans
from sklearn.utils import resample
from scipy.stats import chi2_contingency, ttest_ind

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results-03')


def load_results() -> pd.DataFrame:
    """Load Phase 3 clustering results."""
    df = pd.read_parquet(OUTPUT_DIR / 'phase3_clustered_participants.parquet')
    logger.info(f"Loaded {len(df)} participants with {df['cluster_stepmix'].nunique()} clusters")
    return df


def silhouette_analysis(df: pd.DataFrame, feature_cols: list) -> dict:
    """
    Detailed silhouette analysis by cluster.

    Silhouette score ranges -1 to 1:
    > 0.7: Strong structure
    0.5-0.7: Reasonable structure
    0.25-0.5: Weak structure
    < 0.25: Little meaningful structure
    """
    logger.info("Running silhouette analysis...")

    scaler = StandardScaler()
    X = scaler.fit_transform(df[feature_cols].fillna(df[feature_cols].median()))
    labels = df['cluster_stepmix'].values

    # Overall silhouette
    overall_score = silhouette_score(X, labels)
    logger.info(f"Overall silhouette score: {overall_score:.3f}")

    # Per-sample silhouette
    sample_scores = silhouette_samples(X, labels)

    # Per-cluster statistics
    cluster_stats = []
    for cluster in sorted(df['cluster_stepmix'].unique()):
        mask = labels == cluster
        cluster_scores = sample_scores[mask]
        cluster_stats.append({
            'cluster': cluster,
            'n': mask.sum(),
            'mean_silhouette': cluster_scores.mean(),
            'std_silhouette': cluster_scores.std(),
            'min_silhouette': cluster_scores.min(),
            'pct_negative': (cluster_scores < 0).mean() * 100
        })

    df_stats = pd.DataFrame(cluster_stats)
    logger.info("\nSilhouette by Cluster:")
    logger.info(df_stats.to_string(index=False))

    # Interpretation
    if overall_score > 0.7:
        quality = "Strong"
    elif overall_score > 0.5:
        quality = "Reasonable"
    elif overall_score > 0.25:
        quality = "Weak"
    else:
        quality = "Poor"
    logger.info(f"\nCluster quality: {quality}")

    return {
        'overall_score': overall_score,
        'cluster_stats': df_stats,
        'sample_scores': sample_scores,
        'quality': quality
    }


def bootstrap_stability(df: pd.DataFrame, feature_cols: list, n_bootstrap: int = 50) -> dict:
    """
    Test cluster stability via bootstrap resampling.

    Target: Adjusted Rand Index > 0.85 for stable clusters.
    """
    logger.info(f"Running bootstrap stability analysis ({n_bootstrap} iterations)...")

    scaler = StandardScaler()
    X = scaler.fit_transform(df[feature_cols].fillna(df[feature_cols].median()))
    original_labels = df['cluster_stepmix'].values
    n_clusters = len(np.unique(original_labels))

    # Reference: fit on full data
    reference_model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    reference_labels = reference_model.fit_predict(X)

    # Bootstrap
    ari_scores = []
    for i in range(n_bootstrap):
        # Resample
        X_boot, y_boot = resample(X, reference_labels, random_state=i)

        # Fit on bootstrap sample
        boot_model = KMeans(n_clusters=n_clusters, n_init=5, random_state=i)
        boot_labels = boot_model.fit_predict(X_boot)

        # Compare to reference (on bootstrap sample)
        ari = adjusted_rand_score(y_boot, boot_labels)
        ari_scores.append(ari)

    ari_mean = np.mean(ari_scores)
    ari_std = np.std(ari_scores)

    logger.info(f"Bootstrap ARI: {ari_mean:.3f} +/- {ari_std:.3f}")

    if ari_mean > 0.85:
        stability = "Highly Stable"
    elif ari_mean > 0.70:
        stability = "Stable"
    elif ari_mean > 0.50:
        stability = "Moderately Stable"
    else:
        stability = "Unstable"

    logger.info(f"Stability assessment: {stability}")

    return {
        'mean_ari': ari_mean,
        'std_ari': ari_std,
        'stability': stability,
        'ari_scores': ari_scores
    }


def outcome_predictive_power(df: pd.DataFrame) -> dict:
    """
    Compare how well each phase's clustering predicts engagement.
    """
    logger.info("\nComparing predictive power across phases...")

    results = []

    # Phase 1
    try:
        df_p1 = pd.read_parquet(OUTPUT_DIR / 'phase1_clustered_participants.parquet')
        cont = pd.crosstab(df_p1['cluster'], df_p1['ever_engaged'])
        chi2, p_value, dof, _ = chi2_contingency(cont)
        rate_range = df_p1.groupby('cluster')['ever_engaged'].mean()
        results.append({
            'phase': 'Phase 1 (Demographics)',
            'chi2': chi2,
            'p_value': p_value,
            'min_rate': rate_range.min() * 100,
            'max_rate': rate_range.max() * 100,
            'rate_spread': (rate_range.max() - rate_range.min()) * 100
        })
    except FileNotFoundError:
        pass

    # Phase 2
    try:
        df_p2 = pd.read_parquet(OUTPUT_DIR / 'phase2_clustered_participants.parquet')
        cont = pd.crosstab(df_p2['cluster_phase2'], df_p2['ever_engaged'])
        chi2, p_value, dof, _ = chi2_contingency(cont)
        rate_range = df_p2.groupby('cluster_phase2')['ever_engaged'].mean()
        results.append({
            'phase': 'Phase 2 (Demo + Exposure)',
            'chi2': chi2,
            'p_value': p_value,
            'min_rate': rate_range.min() * 100,
            'max_rate': rate_range.max() * 100,
            'rate_spread': (rate_range.max() - rate_range.min()) * 100
        })
    except FileNotFoundError:
        pass

    # Phase 3
    cont = pd.crosstab(df['cluster_stepmix'], df['ever_engaged'])
    chi2, p_value, dof, _ = chi2_contingency(cont)
    rate_range = df.groupby('cluster_stepmix')['ever_engaged'].mean()
    results.append({
        'phase': 'Phase 3 (Bayesian GMM)',
        'chi2': chi2,
        'p_value': p_value,
        'min_rate': rate_range.min() * 100,
        'max_rate': rate_range.max() * 100,
        'rate_spread': (rate_range.max() - rate_range.min()) * 100
    })

    df_results = pd.DataFrame(results)
    logger.info("\nPredictive Power Comparison:")
    logger.info(df_results.to_string(index=False))

    # Best phase
    best = df_results.loc[df_results['p_value'].idxmin()]
    logger.info(f"\nBest predictive clustering: {best['phase']} (p={best['p_value']:.4f})")

    return {'comparison': df_results, 'best_phase': best['phase']}


def engagement_pattern_analysis(df: pd.DataFrame) -> dict:
    """
    Detailed analysis of what distinguishes high vs low engagement clusters.
    """
    logger.info("\nAnalyzing engagement patterns...")

    feature_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age', 'campaign_count', 'email_count', 'exposure_days'
    ]
    # Add message type features if present
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
    feature_cols.extend(msgtype_cols)

    # Get engagement rate by cluster
    cluster_rates = df.groupby('cluster_stepmix')['ever_engaged'].mean()

    # Identify high and low engagement clusters
    high_clusters = cluster_rates[cluster_rates > cluster_rates.median()].index.tolist()
    low_clusters = cluster_rates[cluster_rates <= cluster_rates.median()].index.tolist()

    logger.info(f"High engagement clusters: {high_clusters} (rates: {cluster_rates[high_clusters].values.round(3)})")
    logger.info(f"Low engagement clusters: {low_clusters} (rates: {cluster_rates[low_clusters].values.round(3)})")

    # Compare features between high and low engagement clusters
    high_mask = df['cluster_stepmix'].isin(high_clusters)
    low_mask = df['cluster_stepmix'].isin(low_clusters)

    comparisons = []
    for col in feature_cols:
        if col in df.columns:
            high_vals = df.loc[high_mask, col].dropna()
            low_vals = df.loc[low_mask, col].dropna()

            # T-test
            t_stat, p_value = ttest_ind(high_vals, low_vals)

            comparisons.append({
                'feature': col,
                'high_mean': high_vals.mean(),
                'low_mean': low_vals.mean(),
                'difference': high_vals.mean() - low_vals.mean(),
                'pct_diff': (high_vals.mean() - low_vals.mean()) / low_vals.mean() * 100,
                'p_value': p_value
            })

    df_comp = pd.DataFrame(comparisons)
    df_comp = df_comp.sort_values('p_value')

    logger.info("\nFeature Differences (High vs Low Engagement Clusters):")
    logger.info(df_comp.to_string(index=False))

    # Key differentiators
    significant = df_comp[df_comp['p_value'] < 0.05]
    if len(significant) > 0:
        logger.info(f"\nKey differentiators (p<0.05): {significant['feature'].tolist()}")

    return {
        'high_clusters': high_clusters,
        'low_clusters': low_clusters,
        'feature_comparisons': df_comp
    }


def create_validation_report(df: pd.DataFrame, feature_cols: list):
    """Generate comprehensive validation report with visualizations."""

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))

    # 1. Silhouette by cluster
    ax1 = axes[0, 0]
    scaler = StandardScaler()
    X = scaler.fit_transform(df[feature_cols].fillna(df[feature_cols].median()))
    labels = df['cluster_stepmix'].values
    sample_scores = silhouette_samples(X, labels)

    # Sort by cluster for visualization
    sorted_indices = np.argsort(labels)
    sorted_labels = labels[sorted_indices]
    sorted_scores = sample_scores[sorted_indices]

    colors = plt.cm.tab10(np.linspace(0, 1, len(np.unique(labels))))
    y_lower = 0
    for i, cluster in enumerate(sorted(np.unique(labels))):
        cluster_scores = sorted_scores[sorted_labels == cluster]
        cluster_scores.sort()
        y_upper = y_lower + len(cluster_scores)
        ax1.fill_betweenx(np.arange(y_lower, y_upper), 0, cluster_scores,
                          facecolor=colors[i % len(colors)], alpha=0.7)
        y_lower = y_upper

    ax1.axvline(x=sample_scores.mean(), color='red', linestyle='--',
               label=f'Mean: {sample_scores.mean():.2f}')
    ax1.set_xlabel('Silhouette Score')
    ax1.set_ylabel('Samples (sorted by cluster)')
    ax1.set_title('Silhouette Analysis by Cluster')
    ax1.legend()

    # 2. Engagement rate by cluster
    ax2 = axes[0, 1]
    cluster_stats = df.groupby('cluster_stepmix').agg({
        'ever_engaged': ['sum', 'mean', 'count']
    })
    cluster_stats.columns = ['engaged', 'rate', 'n']
    cluster_stats = cluster_stats.sort_values('rate', ascending=False)

    bars = ax2.bar(range(len(cluster_stats)), cluster_stats['rate'] * 100, color='steelblue')
    ax2.axhline(y=df['ever_engaged'].mean() * 100, color='red', linestyle='--', label='Overall')
    ax2.set_xlabel('Cluster (sorted by rate)')
    ax2.set_ylabel('Engagement Rate (%)')
    ax2.set_title('Engagement Rate by Cluster')
    ax2.legend()

    # Annotate with counts
    for i, (bar, (_, row)) in enumerate(zip(bars, cluster_stats.iterrows())):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f'n={row["n"]:,}', ha='center', va='bottom', fontsize=7, rotation=45)

    # 3. Cluster size distribution
    ax3 = axes[0, 2]
    sizes = df['cluster_stepmix'].value_counts().sort_index()
    ax3.bar(range(len(sizes)), sizes.values, color='teal')
    ax3.set_xlabel('Cluster')
    ax3.set_ylabel('N Participants')
    ax3.set_title('Cluster Size Distribution')
    ax3.axhline(y=len(df) / len(sizes), color='red', linestyle='--', label='Uniform')
    ax3.legend()

    # 4. Phase comparison
    ax4 = axes[1, 0]
    phases = ['Phase 1\n(Demographics)', 'Phase 2\n(+Exposure)', 'Phase 3\n(Bayesian)']
    p_values = []

    try:
        df_p1 = pd.read_parquet(OUTPUT_DIR / 'phase1_clustered_participants.parquet')
        _, p1, _, _ = chi2_contingency(pd.crosstab(df_p1['cluster'], df_p1['ever_engaged']))
        p_values.append(p1)
    except:
        p_values.append(1.0)

    try:
        df_p2 = pd.read_parquet(OUTPUT_DIR / 'phase2_clustered_participants.parquet')
        _, p2, _, _ = chi2_contingency(pd.crosstab(df_p2['cluster_phase2'], df_p2['ever_engaged']))
        p_values.append(p2)
    except:
        p_values.append(1.0)

    _, p3, _, _ = chi2_contingency(pd.crosstab(df['cluster_stepmix'], df['ever_engaged']))
    p_values.append(p3)

    bars = ax4.bar(phases, [-np.log10(p) for p in p_values], color=['gray', 'orange', 'green'])
    ax4.axhline(y=-np.log10(0.05), color='red', linestyle='--', label='p=0.05')
    ax4.set_ylabel('-log10(p-value)')
    ax4.set_title('Predictive Power Comparison\n(higher = better)')
    ax4.legend()

    # 5. Feature importance for engagement
    ax5 = axes[1, 1]
    cluster_rates = df.groupby('cluster_stepmix')['ever_engaged'].mean()
    high_clusters = cluster_rates[cluster_rates > cluster_rates.median()].index
    high_mask = df['cluster_stepmix'].isin(high_clusters)

    pct_diffs = []
    for col in feature_cols:
        high_mean = df.loc[high_mask, col].mean()
        low_mean = df.loc[~high_mask, col].mean()
        pct_diff = (high_mean - low_mean) / (low_mean + 1e-10) * 100
        pct_diffs.append(pct_diff)

    colors = ['green' if x > 0 else 'red' for x in pct_diffs]
    ax5.barh(feature_cols, pct_diffs, color=colors)
    ax5.set_xlabel('% Difference (High vs Low Engagement)')
    ax5.set_title('Feature Differences by Engagement')
    ax5.axvline(x=0, color='black', linewidth=0.5)

    # 6. Summary statistics
    ax6 = axes[1, 2]
    ax6.axis('off')

    summary_text = f"""
    CLUSTERING VALIDATION SUMMARY
    ============================

    Overall Silhouette Score: {sample_scores.mean():.3f}
    Number of Clusters: {len(np.unique(labels))}

    Engagement Rate Range:
      Min: {cluster_stats['rate'].min()*100:.2f}%
      Max: {cluster_stats['rate'].max()*100:.2f}%
      Spread: {(cluster_stats['rate'].max()-cluster_stats['rate'].min())*100:.2f}%

    Chi-Square Test (Phase 3):
      Chi2: {p3:.4f}
      p-value: {p3:.4f}
      {'SIGNIFICANT!' if p3 < 0.05 else 'Not significant'}

    Best Predictive Phase: Phase 3 (Bayesian GMM)
    """
    ax6.text(0.1, 0.9, summary_text, transform=ax6.transAxes,
            fontsize=10, verticalalignment='top', fontfamily='monospace')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'cluster_validation_report.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved: {OUTPUT_DIR / 'cluster_validation_report.png'}")
    plt.close()


def main():
    """Run all validation analyses."""
    logger.info("="*60)
    logger.info("CLUSTER VALIDATION AND STABILITY ANALYSIS")
    logger.info("="*60)

    # Load data
    df = load_results()

    feature_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age', 'campaign_count', 'email_count', 'exposure_days'
    ]
    # Add message type features if present
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
    feature_cols.extend(msgtype_cols)

    # Silhouette analysis
    silhouette_results = silhouette_analysis(df, feature_cols)

    # Bootstrap stability
    stability_results = bootstrap_stability(df, feature_cols, n_bootstrap=30)

    # Predictive power comparison
    predictive_results = outcome_predictive_power(df)

    # Engagement pattern analysis
    pattern_results = engagement_pattern_analysis(df)

    # Create visualization report
    create_validation_report(df, feature_cols)

    # Save summary
    summary = {
        'silhouette_score': silhouette_results['overall_score'],
        'silhouette_quality': silhouette_results['quality'],
        'stability_ari': stability_results['mean_ari'],
        'stability_assessment': stability_results['stability'],
        'best_predictive_phase': predictive_results['best_phase']
    }
    pd.Series(summary).to_csv(OUTPUT_DIR / 'validation_summary.csv')

    logger.info("\n" + "="*60)
    logger.info("VALIDATION COMPLETE")
    logger.info("="*60)

    return summary


if __name__ == '__main__':
    main()
