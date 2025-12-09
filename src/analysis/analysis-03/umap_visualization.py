"""
UMAP Visualization with Rare Outcome Emphasis

Creates 2D visualizations of participant clusters with special handling
for rare binary outcomes (2.18% engagement rate).

Key technique: Plot non-engaged first (small, transparent) then
overlay engaged (large, opaque) to reveal patterns.
"""
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from umap import UMAP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results-03')


def load_all_results() -> dict:
    """Load results from all clustering phases."""
    results = {}

    try:
        results['phase1'] = pd.read_parquet(OUTPUT_DIR / 'phase1_clustered_participants.parquet')
        logger.info(f"Loaded Phase 1: {len(results['phase1'])} participants")
    except FileNotFoundError:
        logger.warning("Phase 1 results not found")

    try:
        results['phase2'] = pd.read_parquet(OUTPUT_DIR / 'phase2_clustered_participants.parquet')
        logger.info(f"Loaded Phase 2: {len(results['phase2'])} participants")
    except FileNotFoundError:
        logger.warning("Phase 2 results not found")

    try:
        results['phase3'] = pd.read_parquet(OUTPUT_DIR / 'phase3_clustered_participants.parquet')
        logger.info(f"Loaded Phase 3: {len(results['phase3'])} participants")
    except FileNotFoundError:
        logger.warning("Phase 3 results not found")

    return results


def fit_umap(df: pd.DataFrame, feature_cols: list,
             n_neighbors: int = 15, min_dist: float = 0.1) -> np.ndarray:
    """
    Fit UMAP for 2D visualization.

    Parameters:
        n_neighbors: Balance local/global structure (10=local, 30=global)
        min_dist: Cluster tightness (0.0=tight, 0.5=spread)
    """
    logger.info(f"Fitting UMAP (n_neighbors={n_neighbors}, min_dist={min_dist})...")

    scaler = StandardScaler()
    X = scaler.fit_transform(df[feature_cols])

    umap_model = UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        n_components=2,
        metric='euclidean',
        random_state=42
    )
    X_2d = umap_model.fit_transform(X)

    logger.info(f"UMAP embedding shape: {X_2d.shape}")
    return X_2d


def plot_rare_outcome_emphasis(X_2d: np.ndarray, engaged: np.ndarray, ax: plt.Axes,
                                title: str = 'Engaged Participants Highlighted'):
    """
    Plot with rare outcome emphasis per CLUSTERING_PROJECT.md.

    Technique: Non-engaged first (small, transparent), then engaged (large, opaque).
    """
    engaged = engaged.astype(bool)

    # Background: non-engaged (97.5%)
    ax.scatter(X_2d[~engaged, 0], X_2d[~engaged, 1],
               c='lightgray', s=5, alpha=0.3,
               label=f'Non-engaged (n={(~engaged).sum():,})')

    # Foreground: engaged (2.5%)
    ax.scatter(X_2d[engaged, 0], X_2d[engaged, 1],
               c='red', s=40, alpha=0.9,
               label=f'Engaged (n={engaged.sum():,})')

    ax.set_xlabel('UMAP 1')
    ax.set_ylabel('UMAP 2')
    ax.set_title(title)
    ax.legend()


def plot_cluster_colored(X_2d: np.ndarray, labels: np.ndarray, ax: plt.Axes,
                          title: str = 'Clusters'):
    """Plot with clusters color-coded."""
    scatter = ax.scatter(X_2d[:, 0], X_2d[:, 1], c=labels, cmap='tab10',
                        s=10, alpha=0.5)
    ax.set_xlabel('UMAP 1')
    ax.set_ylabel('UMAP 2')
    ax.set_title(title)
    plt.colorbar(scatter, ax=ax, label='Cluster')


def plot_feature_gradient(X_2d: np.ndarray, values: np.ndarray, ax: plt.Axes,
                           title: str = 'Feature', cmap: str = 'viridis'):
    """Plot with continuous feature as color gradient."""
    scatter = ax.scatter(X_2d[:, 0], X_2d[:, 1], c=values, cmap=cmap,
                        s=10, alpha=0.5)
    ax.set_xlabel('UMAP 1')
    ax.set_ylabel('UMAP 2')
    ax.set_title(title)
    plt.colorbar(scatter, ax=ax)


def create_comprehensive_visualization(results: dict):
    """Create comprehensive UMAP visualization dashboard."""
    if 'phase3' not in results:
        logger.error("Phase 3 results required for visualization")
        return

    df = results['phase3']

    # Features for UMAP - include message types
    feature_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age',
        'campaign_count', 'email_count', 'exposure_days'
    ]
    # Add message type features if present
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
    feature_cols.extend(msgtype_cols)

    # Fill missing values
    df_clean = df.copy()
    for col in feature_cols:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].fillna(df_clean[col].median())

    # Fit UMAP
    X_2d = fit_umap(df_clean, feature_cols)

    # Create 4x2 dashboard
    fig, axes = plt.subplots(3, 3, figsize=(18, 16))

    # Row 1: Core views
    plot_rare_outcome_emphasis(X_2d, df_clean['ever_engaged'].values, axes[0, 0],
                               'UMAP: Engaged Highlighted (Rare Outcome)')

    plot_cluster_colored(X_2d, df_clean['cluster_stepmix'].values, axes[0, 1],
                        'UMAP: Phase 3 Clusters')

    # Engagement rate by region (binned)
    ax_eng = axes[0, 2]
    # Create local engagement density
    from scipy.ndimage import gaussian_filter
    h, xedges, yedges = np.histogram2d(X_2d[df_clean['ever_engaged'], 0],
                                        X_2d[df_clean['ever_engaged'], 1],
                                        bins=30)
    h_smooth = gaussian_filter(h, sigma=1)
    ax_eng.imshow(h_smooth.T, extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]],
                  origin='lower', cmap='hot', aspect='auto')
    ax_eng.set_xlabel('UMAP 1')
    ax_eng.set_ylabel('UMAP 2')
    ax_eng.set_title('Engagement Density Heatmap')

    # Row 2: Feature gradients
    plot_feature_gradient(X_2d, df_clean['estimated_income'].values, axes[1, 0],
                          'Income Gradient')

    plot_feature_gradient(X_2d, df_clean['total_energy_burden'].values, axes[1, 1],
                          'Energy Burden Gradient', cmap='RdYlGn_r')

    plot_feature_gradient(X_2d, df_clean['campaign_count'].values, axes[1, 2],
                          'Campaign Count Gradient')

    # Row 3: More features and cluster quality
    plot_feature_gradient(X_2d, df_clean['house_age'].values, axes[2, 0],
                          'House Age Gradient')

    # Assignment confidence
    prob_cols = [c for c in df_clean.columns if c.startswith('prob_cluster_')]
    if prob_cols:
        max_probs = df_clean[prob_cols].max(axis=1).values
        plot_feature_gradient(X_2d, max_probs, axes[2, 1],
                              'Assignment Confidence', cmap='RdYlGn')

    # Cluster profile summary
    ax_summary = axes[2, 2]
    cluster_rates = df_clean.groupby('cluster_stepmix')['ever_engaged'].mean() * 100
    cluster_counts = df_clean.groupby('cluster_stepmix').size()
    x = range(len(cluster_rates))
    bars = ax_summary.bar(x, cluster_rates.values, color='steelblue')
    ax_summary.axhline(y=df_clean['ever_engaged'].mean() * 100, color='red',
                       linestyle='--', label='Overall')
    ax_summary.set_xlabel('Cluster')
    ax_summary.set_ylabel('Engagement Rate (%)')
    ax_summary.set_title('Engagement by Cluster')
    ax_summary.legend()

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'umap_comprehensive_dashboard.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved: {OUTPUT_DIR / 'umap_comprehensive_dashboard.png'}")
    plt.close()

    # Save UMAP coordinates
    df_umap = pd.DataFrame({
        'participant_id': df_clean['participant_id'].values,
        'umap_1': X_2d[:, 0],
        'umap_2': X_2d[:, 1],
        'cluster': df_clean['cluster_stepmix'].values,
        'engaged': df_clean['ever_engaged'].values
    })
    df_umap.to_parquet(OUTPUT_DIR / 'umap_coordinates.parquet', index=False)
    logger.info(f"Saved UMAP coordinates")

    return X_2d


def create_umap_parameter_comparison(results: dict):
    """Compare UMAP with different parameters to show sensitivity."""
    if 'phase3' not in results:
        return

    df = results['phase3']
    feature_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age',
        'campaign_count', 'email_count', 'exposure_days'
    ]
    # Add message type features if present
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
    feature_cols.extend(msgtype_cols)

    df_clean = df.copy()
    for col in feature_cols:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].fillna(df_clean[col].median())

    scaler = StandardScaler()
    X = scaler.fit_transform(df_clean[feature_cols])

    # Different parameter combinations
    params = [
        {'n_neighbors': 5, 'min_dist': 0.0, 'name': 'Local (n=5, d=0)'},
        {'n_neighbors': 15, 'min_dist': 0.1, 'name': 'Default (n=15, d=0.1)'},
        {'n_neighbors': 30, 'min_dist': 0.1, 'name': 'Global (n=30, d=0.1)'},
        {'n_neighbors': 15, 'min_dist': 0.5, 'name': 'Spread (n=15, d=0.5)'},
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    engaged = df_clean['ever_engaged'].astype(bool).values

    for ax, p in zip(axes.flat, params):
        umap_model = UMAP(n_neighbors=p['n_neighbors'], min_dist=p['min_dist'],
                         n_components=2, random_state=42)
        X_2d = umap_model.fit_transform(X)

        plot_rare_outcome_emphasis(X_2d, engaged, ax, p['name'])

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'umap_parameter_comparison.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved: {OUTPUT_DIR / 'umap_parameter_comparison.png'}")
    plt.close()


def main():
    """Generate all UMAP visualizations."""
    logger.info("="*60)
    logger.info("UMAP VISUALIZATION WITH RARE OUTCOME EMPHASIS")
    logger.info("="*60)

    # Load results
    results = load_all_results()

    if not results:
        logger.error("No clustering results found!")
        return

    # Comprehensive dashboard
    create_comprehensive_visualization(results)

    # Parameter comparison
    create_umap_parameter_comparison(results)

    logger.info("\n" + "="*60)
    logger.info("VISUALIZATION COMPLETE")
    logger.info("="*60)


if __name__ == '__main__':
    main()
