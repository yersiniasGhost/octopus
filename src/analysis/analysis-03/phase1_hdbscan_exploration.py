"""
Phase 1b: HDBSCAN Exploratory Clustering

Density-based clustering that:
1. Automatically determines cluster count
2. Identifies outliers/noise points
3. Reveals natural groupings without pre-specifying k

This complements K-prototypes by discovering structure without assumptions.
"""
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
import hdbscan
import gower

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results')


def load_and_prepare_data() -> pd.DataFrame:
    """Load and prepare data for HDBSCAN clustering."""
    df = pd.read_parquet('/home/yersinia/devel/octopus/data/participant_features.parquet')

    # Select continuous features with good coverage
    continuous_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age'
    ]

    df_features = df[['participant_id'] + continuous_cols + ['ever_engaged', 'ever_clicked']].copy()

    # Fill missing values
    for col in continuous_cols:
        df_features[col] = df_features[col].fillna(df_features[col].median())

    logger.info(f"Prepared {len(df_features)} participants with {len(continuous_cols)} features")
    return df_features, continuous_cols


def run_hdbscan_euclidean(df_features: pd.DataFrame, continuous_cols: list,
                          min_cluster_size: int = 100) -> tuple:
    """
    Run HDBSCAN with standardized Euclidean distance.

    min_cluster_size controls granularity - larger = fewer, more robust clusters.
    """
    logger.info(f"Running HDBSCAN (Euclidean) with min_cluster_size={min_cluster_size}...")

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[continuous_cols])

    # Fit HDBSCAN
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=10,
        metric='euclidean',
        cluster_selection_method='eom',  # excess of mass
        prediction_data=True
    )
    labels = clusterer.fit_predict(X_scaled)

    # Analyze results
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()

    logger.info(f"Found {n_clusters} clusters, {n_noise} noise points ({100*n_noise/len(labels):.1f}%)")

    # Silhouette score (excluding noise)
    if n_clusters > 1:
        mask = labels != -1
        if mask.sum() > n_clusters:
            silhouette = silhouette_score(X_scaled[mask], labels[mask])
            logger.info(f"Silhouette score (non-noise): {silhouette:.3f}")
        else:
            silhouette = None
    else:
        silhouette = None

    return labels, clusterer, silhouette


def run_hdbscan_gower(df_features: pd.DataFrame, continuous_cols: list,
                       min_cluster_size: int = 80) -> tuple:
    """
    Run HDBSCAN with Gower distance matrix.

    Gower distance handles mixed data naturally, normalizing each feature.
    Note: Requires O(n²) memory for distance matrix.
    """
    logger.info(f"Computing Gower distance matrix for {len(df_features)} participants...")

    X = df_features[continuous_cols]

    # Compute Gower distance matrix
    dist_matrix = gower.gower_matrix(X).astype(np.float64)
    logger.info(f"Distance matrix shape: {dist_matrix.shape}")

    # Fit HDBSCAN with precomputed distances
    logger.info(f"Running HDBSCAN (Gower) with min_cluster_size={min_cluster_size}...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=10,
        metric='precomputed',
        cluster_selection_method='eom'
    )
    labels = clusterer.fit_predict(dist_matrix)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    logger.info(f"Found {n_clusters} clusters, {n_noise} noise points ({100*n_noise/len(labels):.1f}%)")

    return labels, clusterer, None


def analyze_cluster_structure(df_features: pd.DataFrame, labels: np.ndarray,
                               continuous_cols: list, method_name: str) -> pd.DataFrame:
    """Analyze cluster structure and outcomes."""
    df_analysis = df_features.copy()
    df_analysis['cluster'] = labels

    # Cluster statistics
    stats = []
    for cluster in sorted(df_analysis['cluster'].unique()):
        cluster_data = df_analysis[df_analysis['cluster'] == cluster]
        stat = {
            'cluster': cluster,
            'n': len(cluster_data),
            'pct': 100 * len(cluster_data) / len(df_analysis),
            'engage_rate': cluster_data['ever_engaged'].mean() * 100 if cluster_data['ever_engaged'].dtype == bool else 0,
            'engaged_count': cluster_data['ever_engaged'].sum()
        }
        for col in continuous_cols:
            stat[f'{col}_mean'] = cluster_data[col].mean()
        stats.append(stat)

    df_stats = pd.DataFrame(stats)
    logger.info(f"\n{method_name} Cluster Statistics:")
    logger.info(df_stats.to_string(index=False))

    return df_stats


def compare_min_cluster_sizes(df_features: pd.DataFrame, continuous_cols: list) -> pd.DataFrame:
    """Explore effect of min_cluster_size parameter."""
    logger.info("\nExploring min_cluster_size parameter...")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[continuous_cols])

    results = []
    for mcs in [50, 100, 200, 300, 500]:
        clusterer = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=10, metric='euclidean')
        labels = clusterer.fit_predict(X_scaled)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = (labels == -1).sum()

        # Check if engaged participants are in noise
        df_temp = df_features.copy()
        df_temp['cluster'] = labels
        engaged_in_noise = df_temp[(df_temp['cluster'] == -1) & (df_temp['ever_engaged'] == True)].shape[0]

        results.append({
            'min_cluster_size': mcs,
            'n_clusters': n_clusters,
            'n_noise': n_noise,
            'pct_noise': 100 * n_noise / len(labels),
            'engaged_in_noise': engaged_in_noise
        })

    df_results = pd.DataFrame(results)
    logger.info("\nParameter exploration results:")
    logger.info(df_results.to_string(index=False))

    return df_results


def plot_hdbscan_analysis(df_features: pd.DataFrame, labels: np.ndarray,
                          continuous_cols: list, method_name: str):
    """Visualize HDBSCAN clustering results."""
    from sklearn.decomposition import PCA

    # PCA for visualization
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[continuous_cols])
    pca = PCA(n_components=2)
    X_2d = pca.fit_transform(X_scaled)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # 1. Clusters
    ax1 = axes[0]
    unique_labels = sorted(set(labels))
    colors = plt.cm.viridis(np.linspace(0, 1, len(unique_labels)))

    for label, color in zip(unique_labels, colors):
        mask = labels == label
        if label == -1:
            ax1.scatter(X_2d[mask, 0], X_2d[mask, 1], c='lightgray', s=5, alpha=0.3, label='Noise')
        else:
            ax1.scatter(X_2d[mask, 0], X_2d[mask, 1], c=[color], s=20, alpha=0.5, label=f'Cluster {label}')

    ax1.set_title(f'{method_name}: Cluster Assignments')
    ax1.set_xlabel('PCA 1')
    ax1.set_ylabel('PCA 2')
    ax1.legend(loc='best', fontsize=8)

    # 2. Engagement overlay
    ax2 = axes[1]
    non_engaged = ~df_features['ever_engaged'].astype(bool)
    engaged = df_features['ever_engaged'].astype(bool)

    ax2.scatter(X_2d[non_engaged, 0], X_2d[non_engaged, 1], c='lightgray', s=5, alpha=0.2)
    ax2.scatter(X_2d[engaged, 0], X_2d[engaged, 1], c='red', s=40, alpha=0.8, label=f'Engaged (n={engaged.sum()})')
    ax2.set_title(f'{method_name}: Engaged Highlighted')
    ax2.set_xlabel('PCA 1')
    ax2.set_ylabel('PCA 2')
    ax2.legend()

    # 3. Engagement rate by cluster
    ax3 = axes[2]
    df_temp = df_features.copy()
    df_temp['cluster'] = labels

    cluster_rates = df_temp.groupby('cluster')['ever_engaged'].mean() * 100
    cluster_counts = df_temp.groupby('cluster').size()

    bars = ax3.bar(range(len(cluster_rates)), cluster_rates.values, color='steelblue')
    ax3.axhline(y=df_features['ever_engaged'].mean() * 100, color='red', linestyle='--', label='Overall')
    ax3.set_xticks(range(len(cluster_rates)))
    ax3.set_xticklabels([f'{c}\n(n={cluster_counts[c]:,})' for c in cluster_rates.index], fontsize=8)
    ax3.set_xlabel('Cluster (-1 = Noise)')
    ax3.set_ylabel('Engagement Rate (%)')
    ax3.set_title(f'{method_name}: Engagement by Cluster')
    ax3.legend()

    plt.tight_layout()
    filename = f'hdbscan_{method_name.lower().replace(" ", "_")}.png'
    plt.savefig(OUTPUT_DIR / filename, dpi=150, bbox_inches='tight')
    logger.info(f"Saved plot to {OUTPUT_DIR / filename}")
    plt.close()


def main():
    """Run HDBSCAN exploratory clustering."""
    logger.info("="*60)
    logger.info("PHASE 1b: HDBSCAN EXPLORATORY CLUSTERING")
    logger.info("="*60)

    # Load data
    df_features, continuous_cols = load_and_prepare_data()

    # Parameter exploration
    param_results = compare_min_cluster_sizes(df_features, continuous_cols)
    param_results.to_csv(OUTPUT_DIR / 'hdbscan_parameter_exploration.csv', index=False)

    # Run HDBSCAN with Euclidean distance
    labels_euclidean, clusterer_euclidean, silhouette = run_hdbscan_euclidean(
        df_features, continuous_cols, min_cluster_size=100
    )
    stats_euclidean = analyze_cluster_structure(df_features, labels_euclidean, continuous_cols, 'HDBSCAN Euclidean')
    plot_hdbscan_analysis(df_features, labels_euclidean, continuous_cols, 'HDBSCAN Euclidean')

    # Save Euclidean results
    df_result = df_features.copy()
    df_result['hdbscan_cluster'] = labels_euclidean
    df_result.to_parquet(OUTPUT_DIR / 'hdbscan_clustered_participants.parquet', index=False)

    # Run HDBSCAN with Gower distance (takes longer due to distance matrix)
    logger.info("\n" + "-"*40)
    labels_gower, clusterer_gower, _ = run_hdbscan_gower(df_features, continuous_cols, min_cluster_size=80)
    stats_gower = analyze_cluster_structure(df_features, labels_gower, continuous_cols, 'HDBSCAN Gower')
    plot_hdbscan_analysis(df_features, labels_gower, continuous_cols, 'HDBSCAN Gower')

    logger.info("\n" + "="*60)
    logger.info("HDBSCAN EXPLORATION COMPLETE")
    logger.info("="*60)

    return df_result, labels_euclidean, labels_gower


if __name__ == '__main__':
    main()
