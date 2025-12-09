"""
Phase 2: Demographics + Campaign Exposure Clustering

Adds campaign exposure patterns to clustering:
- Number of campaigns received
- Channel distribution (email, text, postal)
- Exposure duration
- Channel diversity

This tests whether campaign-level factors predict engagement better than demographics alone.
"""
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from scipy.stats import chi2_contingency
import prince
from sklearn.cluster import KMeans

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results-02')


def load_data() -> pd.DataFrame:
    """Load participant features with campaign exposure data."""
    df = pd.read_parquet('/home/yersinia/devel/octopus/data/clustering_results-02/participant_features.parquet')
    logger.info(f"Loaded {len(df)} participants")
    return df


def prepare_phase2_features(df: pd.DataFrame) -> tuple:
    """
    Prepare Phase 2 features: Demographics + Campaign Exposure + Message Types.
    """
    # Demographics (same as Phase 1)
    demo_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age'
    ]

    # Campaign exposure features
    exposure_cols = [
        'campaign_count', 'email_count', 'text_count', 'postal_count',
        'channel_diversity', 'exposure_days'
    ]

    # Message type exposure features (NEW)
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]

    # Outcome columns (NOT for clustering)
    outcome_cols = ['ever_engaged', 'ever_clicked', 'engage_rate', 'email_click_rate']

    # Select available columns
    available_demo = [c for c in demo_cols if c in df.columns]
    available_exposure = [c for c in exposure_cols if c in df.columns]
    available_msgtype = [c for c in msgtype_cols if c in df.columns]
    continuous_cols = available_demo + available_exposure + available_msgtype

    all_cols = ['participant_id'] + continuous_cols + outcome_cols
    df_features = df[[c for c in all_cols if c in df.columns]].copy()

    # Fill missing values
    for col in continuous_cols:
        if df_features[col].isna().any():
            median_val = df_features[col].median()
            df_features[col] = df_features[col].fillna(median_val)
            logger.info(f"Filled {col} NaN with median: {median_val:.2f}")

    logger.info(f"Phase 2 features: {len(available_demo)} demographics + {len(available_exposure)} exposure + {len(available_msgtype)} message types")
    return df_features, available_demo, available_exposure + available_msgtype


def run_famd_phase2(df_features: pd.DataFrame, demo_cols: list, exposure_cols: list,
                     n_components: int = 5) -> tuple:
    """Run FAMD on combined demographics + exposure features."""
    logger.info(f"Running FAMD on combined features...")

    all_cols = demo_cols + exposure_cols
    X = df_features[all_cols].copy()

    famd = prince.FAMD(n_components=n_components, n_iter=5, random_state=42)
    famd = famd.fit(X)

    coords = famd.row_coordinates(X)
    coords.index = df_features.index

    # Log variance and contributions
    eigenvalues = famd.eigenvalues_
    total_var = sum(eigenvalues)
    cumulative_var = np.cumsum(eigenvalues) / total_var * 100

    logger.info("FAMD Variance Explained:")
    for i, (eigen, cum) in enumerate(zip(eigenvalues, cumulative_var)):
        logger.info(f"  Component {i}: {eigen:.3f} ({cum:.1f}% cumulative)")

    logger.info("\nColumn Contributions (which features drive each component):")
    contributions = famd.column_contributions_
    logger.info(contributions.to_string())

    return coords, famd


def run_kmeans_phase2(df_features: pd.DataFrame, continuous_cols: list,
                      n_clusters: int = 4) -> tuple:
    """Run KMeans on Phase 2 features (continuous only)."""
    logger.info(f"Running KMeans with k={n_clusters}...")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[continuous_cols])

    kmeans = KMeans(n_clusters=n_clusters, init='k-means++', n_init=10, random_state=42)
    labels = kmeans.fit_predict(X_scaled)

    silhouette = silhouette_score(X_scaled, labels)
    logger.info(f"Silhouette score: {silhouette:.3f}")

    return labels, kmeans, silhouette, scaler


def find_optimal_k_phase2(df_features: pd.DataFrame, continuous_cols: list,
                           k_range: range = range(2, 10)) -> pd.DataFrame:
    """Find optimal k for Phase 2 features."""
    logger.info("Finding optimal k for Phase 2...")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[continuous_cols])

    results = []
    for k in k_range:
        kmeans = KMeans(n_clusters=k, init='k-means++', n_init=5, random_state=42)
        labels = kmeans.fit_predict(X_scaled)
        inertia = kmeans.inertia_
        silhouette = silhouette_score(X_scaled, labels)
        results.append({'k': k, 'inertia': inertia, 'silhouette': silhouette})

    df_results = pd.DataFrame(results)
    logger.info("\nK selection results:")
    logger.info(df_results.to_string(index=False))

    return df_results


def analyze_cluster_outcomes(df_features: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """Analyze engagement by cluster - this is the key test."""
    df_analysis = df_features.copy()
    df_analysis['cluster'] = labels

    # Base aggregations
    agg_dict = {
        'ever_engaged': ['sum', 'mean', 'count'],
        'campaign_count': 'mean',
        'email_count': 'mean',
        'channel_diversity': 'mean'
    }

    # Add message type columns if present
    msgtype_cols = [c for c in df_analysis.columns if c.startswith('msgtype_') and c.endswith('_count')]
    for col in msgtype_cols:
        agg_dict[col] = 'mean'

    cluster_stats = df_analysis.groupby('cluster').agg(agg_dict).round(4)

    # Flatten column names
    new_cols = ['engaged_count', 'engage_rate', 'n_participants',
                'avg_campaigns', 'avg_emails', 'avg_channel_diversity']
    for col in msgtype_cols:
        new_cols.append(f'avg_{col}')
    cluster_stats.columns = new_cols

    logger.info("\nPhase 2 Cluster Outcome Analysis:")
    logger.info(cluster_stats.to_string())

    # Chi-square test
    contingency = pd.crosstab(df_analysis['cluster'], df_analysis['ever_engaged'])
    chi2, p_value, dof, expected = chi2_contingency(contingency)
    logger.info(f"\nChi-square test (engagement by cluster):")
    logger.info(f"  Chi2: {chi2:.2f}, p-value: {p_value:.4f}")

    if p_value < 0.05:
        logger.info("  => SIGNIFICANT! Campaign exposure patterns predict engagement!")
    else:
        logger.info("  => No significant difference (campaign exposure doesn't help)")

    return cluster_stats


def profile_clusters(df_features: pd.DataFrame, labels: np.ndarray,
                     demo_cols: list, exposure_cols: list) -> pd.DataFrame:
    """Profile clusters by demographics AND exposure."""
    df_profile = df_features.copy()
    df_profile['cluster'] = labels

    all_cols = demo_cols + exposure_cols
    profiles = df_profile.groupby('cluster')[all_cols].mean()

    logger.info("\nCluster Profiles:")
    logger.info(profiles.to_string())

    return profiles


def compare_phase1_vs_phase2(df_features: pd.DataFrame,
                              labels_phase2: np.ndarray) -> None:
    """Compare Phase 2 results to Phase 1."""
    # Load Phase 1 results
    try:
        df_phase1 = pd.read_parquet(OUTPUT_DIR / 'phase1_clustered_participants.parquet')
        labels_phase1 = df_phase1['cluster'].values

        logger.info("\n" + "="*50)
        logger.info("COMPARISON: Phase 1 (Demographics) vs Phase 2 (+Exposure)")
        logger.info("="*50)

        # Phase 1 engagement rates
        df_features['cluster_p1'] = labels_phase1[:len(df_features)]
        df_features['cluster_p2'] = labels_phase2

        p1_rates = df_features.groupby('cluster_p1')['ever_engaged'].mean()
        p2_rates = df_features.groupby('cluster_p2')['ever_engaged'].mean()

        logger.info(f"\nPhase 1 engagement rate range: {p1_rates.min():.3f} - {p1_rates.max():.3f}")
        logger.info(f"Phase 2 engagement rate range: {p2_rates.min():.3f} - {p2_rates.max():.3f}")

        # Chi-square for both
        cont_p1 = pd.crosstab(df_features['cluster_p1'], df_features['ever_engaged'])
        cont_p2 = pd.crosstab(df_features['cluster_p2'], df_features['ever_engaged'])

        _, p1_pval, _, _ = chi2_contingency(cont_p1)
        _, p2_pval, _, _ = chi2_contingency(cont_p2)

        logger.info(f"\nPhase 1 chi-square p-value: {p1_pval:.4f}")
        logger.info(f"Phase 2 chi-square p-value: {p2_pval:.4f}")

        if p2_pval < p1_pval:
            logger.info("\n=> Phase 2 (with exposure) better predicts engagement!")
        else:
            logger.info("\n=> Phase 1 (demographics only) is sufficient")

    except FileNotFoundError:
        logger.warning("Phase 1 results not found, skipping comparison")


def plot_phase2_analysis(df_features: pd.DataFrame, labels: np.ndarray,
                         famd_coords: pd.DataFrame, cluster_stats: pd.DataFrame,
                         profiles: pd.DataFrame, demo_cols: list, exposure_cols: list):
    """Generate Phase 2 visualizations."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))

    # 1. FAMD scatter colored by cluster
    ax1 = axes[0, 0]
    scatter = ax1.scatter(famd_coords[0], famd_coords[1], c=labels, cmap='viridis', s=10, alpha=0.5)
    ax1.set_xlabel('FAMD Component 1')
    ax1.set_ylabel('FAMD Component 2')
    ax1.set_title('Phase 2 FAMD: Clusters')
    plt.colorbar(scatter, ax=ax1, label='Cluster')

    # 2. FAMD with engagement
    ax2 = axes[0, 1]
    engaged = df_features['ever_engaged'].astype(bool)
    ax2.scatter(famd_coords.loc[~engaged, 0], famd_coords.loc[~engaged, 1],
               c='lightgray', s=5, alpha=0.3, label=f'Non-engaged')
    ax2.scatter(famd_coords.loc[engaged, 0], famd_coords.loc[engaged, 1],
               c='red', s=40, alpha=0.9, label=f'Engaged (n={engaged.sum()})')
    ax2.set_xlabel('FAMD Component 1')
    ax2.set_ylabel('FAMD Component 2')
    ax2.set_title('Phase 2 FAMD: Engaged Highlighted')
    ax2.legend()

    # 3. Engagement rate by cluster
    ax3 = axes[0, 2]
    x = range(len(cluster_stats))
    bars = ax3.bar(x, cluster_stats['engage_rate'] * 100, color='steelblue')
    ax3.axhline(y=df_features['ever_engaged'].mean() * 100, color='red', linestyle='--', label='Overall')
    ax3.set_xlabel('Cluster')
    ax3.set_ylabel('Engagement Rate (%)')
    ax3.set_title('Engagement Rate by Cluster')
    ax3.legend()
    for bar, count in zip(bars, cluster_stats['n_participants']):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f'n={count:,}', ha='center', va='bottom', fontsize=8)

    # 4. Demographics profile heatmap
    ax4 = axes[1, 0]
    demo_profile = profiles[demo_cols].apply(lambda x: (x - x.mean()) / x.std(), axis=0)
    sns.heatmap(demo_profile.T, annot=True, fmt='.2f', cmap='RdYlBu_r', ax=ax4, center=0)
    ax4.set_title('Demographics Profile (Standardized)')
    ax4.set_xlabel('Cluster')

    # 5. Exposure profile heatmap
    ax5 = axes[1, 1]
    exp_profile = profiles[exposure_cols].apply(lambda x: (x - x.mean()) / x.std(), axis=0)
    sns.heatmap(exp_profile.T, annot=True, fmt='.2f', cmap='RdYlBu_r', ax=ax5, center=0)
    ax5.set_title('Campaign Exposure Profile (Standardized)')
    ax5.set_xlabel('Cluster')

    # 6. Campaign count vs engagement rate
    ax6 = axes[1, 2]
    ax6.scatter(cluster_stats['avg_campaigns'], cluster_stats['engage_rate'] * 100,
               s=cluster_stats['n_participants'] / 10, alpha=0.7)
    for i, row in cluster_stats.iterrows():
        ax6.annotate(f'C{i}', (row['avg_campaigns'], row['engage_rate'] * 100))
    ax6.set_xlabel('Avg Campaigns per Participant')
    ax6.set_ylabel('Engagement Rate (%)')
    ax6.set_title('Campaigns vs Engagement by Cluster')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'phase2_cluster_analysis.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved plot to {OUTPUT_DIR / 'phase2_cluster_analysis.png'}")
    plt.close()


def main():
    """Run Phase 2 clustering analysis."""
    logger.info("="*60)
    logger.info("PHASE 2: DEMOGRAPHICS + CAMPAIGN EXPOSURE CLUSTERING")
    logger.info("="*60)

    # Load and prepare data
    df = load_data()
    df_features, demo_cols, exposure_cols = prepare_phase2_features(df)
    continuous_cols = demo_cols + exposure_cols

    logger.info(f"Demographics: {demo_cols}")
    logger.info(f"Exposure: {exposure_cols}")

    # Run FAMD
    famd_coords, famd_model = run_famd_phase2(df_features, demo_cols, exposure_cols)

    # Find optimal k
    k_results = find_optimal_k_phase2(df_features, continuous_cols)
    k_results.to_csv(OUTPUT_DIR / 'phase2_k_selection.csv', index=False)

    optimal_k = k_results.loc[k_results['silhouette'].idxmax(), 'k']
    logger.info(f"\nSelected k={optimal_k} based on silhouette")

    # Final clustering
    labels, kmeans, silhouette, scaler = run_kmeans_phase2(
        df_features, continuous_cols, n_clusters=int(optimal_k)
    )

    # Analyze outcomes (KEY TEST)
    cluster_stats = analyze_cluster_outcomes(df_features, labels)
    cluster_stats.to_csv(OUTPUT_DIR / 'phase2_cluster_outcomes.csv')

    # Profile clusters
    profiles = profile_clusters(df_features, labels, demo_cols, exposure_cols)
    profiles.to_csv(OUTPUT_DIR / 'phase2_cluster_profiles.csv')

    # Compare to Phase 1
    compare_phase1_vs_phase2(df_features, labels)

    # Visualize
    plot_phase2_analysis(df_features, labels, famd_coords, cluster_stats, profiles,
                         demo_cols, exposure_cols)

    # Save results
    df_features['cluster_phase2'] = labels
    df_features.to_parquet(OUTPUT_DIR / 'phase2_clustered_participants.parquet', index=False)

    logger.info("\n" + "="*60)
    logger.info("PHASE 2 COMPLETE")
    logger.info("="*60)

    return df_features, labels, famd_coords


if __name__ == '__main__':
    main()
