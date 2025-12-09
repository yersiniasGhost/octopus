"""
Phase 1: Demographics-only Clustering

This implements the first phase of progressive clustering analysis:
1. FAMD for mixed-data dimensionality reduction
2. K-prototypes for mixed continuous/categorical clustering
3. Cluster validation with silhouette scores
4. Outcome analysis (click rates by cluster - NOT used for clustering)

Per CLUSTERING_PROJECT.md: "Cluster on pre-treatment features, then characterize by outcomes"
"""
import logging
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from scipy.stats import chi2_contingency
import prince
from kmodes.kprototypes import KPrototypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Output directory
OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results-03')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_data(path: str = '/home/yersinia/devel/octopus/data/clustering_results-03/participant_features.parquet') -> pd.DataFrame:
    """Load participant features dataset."""
    df = pd.read_parquet(path)
    logger.info(f"Loaded {len(df)} participants")
    return df


def prepare_phase1_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Prepare Phase 1 features (demographics only).

    Returns:
        df_features: DataFrame with features
        continuous_cols: List of continuous column names
        categorical_cols: List of categorical column names
    """
    # Based on actual data availability from extraction
    continuous_cols = [
        'estimated_income',
        'household_size',
        'total_energy_burden',
        'living_area_sqft',
        'house_age'
    ]

    categorical_cols = [
        'home_owner',
        'dwelling_type',
        'presence_of_children'
    ]

    # Select features that exist and have reasonable coverage
    available_continuous = [c for c in continuous_cols if c in df.columns]
    available_categorical = [c for c in categorical_cols if c in df.columns]

    # Create feature subset
    all_cols = available_continuous + available_categorical + ['participant_id', 'ever_engaged', 'ever_clicked']
    df_features = df[all_cols].copy()

    # Handle missing values in continuous features
    for col in available_continuous:
        # Fill with median for now
        if df_features[col].isna().any():
            median_val = df_features[col].median()
            df_features[col] = df_features[col].fillna(median_val)
            logger.info(f"Filled {col} NaN with median: {median_val:.2f}")

    # Handle categorical features
    for col in available_categorical:
        if df_features[col].isna().any():
            df_features[col] = df_features[col].fillna('Unknown')
        # Convert boolean to string for FAMD/K-prototypes
        if df_features[col].dtype == 'bool':
            df_features[col] = df_features[col].map({True: 'Yes', False: 'No', None: 'Unknown'})
        else:
            df_features[col] = df_features[col].astype(str)

    logger.info(f"Prepared {len(available_continuous)} continuous, {len(available_categorical)} categorical features")
    return df_features, available_continuous, available_categorical


def run_famd(df_features: pd.DataFrame, continuous_cols: List[str],
             categorical_cols: List[str], n_components: int = 5) -> Tuple[pd.DataFrame, prince.FAMD]:
    """
    Run Factor Analysis of Mixed Data (FAMD) for dimensionality reduction.

    FAMD correctly handles both continuous and categorical variables.
    """
    logger.info(f"Running FAMD with {n_components} components...")

    feature_cols = continuous_cols + categorical_cols
    X = df_features[feature_cols].copy()

    # Initialize and fit FAMD
    famd = prince.FAMD(n_components=n_components, n_iter=5, random_state=42)
    famd = famd.fit(X)

    # Get coordinates
    coords = famd.row_coordinates(X)
    coords.index = df_features.index

    # Log variance explained
    eigenvalues = famd.eigenvalues_
    total_var = sum(eigenvalues)
    cumulative_var = np.cumsum(eigenvalues) / total_var * 100

    logger.info("FAMD Variance Explained:")
    for i, (eigen, cum) in enumerate(zip(eigenvalues, cumulative_var)):
        logger.info(f"  Component {i}: {eigen:.3f} ({cum:.1f}% cumulative)")

    # Column contributions (which variables drive each component)
    logger.info("\nColumn Contributions:")
    contributions = famd.column_contributions_
    logger.info(contributions.to_string())

    return coords, famd


def run_kprototypes(df_features: pd.DataFrame, continuous_cols: List[str],
                    categorical_cols: List[str], n_clusters: int = 4,
                    gamma: float = 1.5) -> Tuple[np.ndarray, KPrototypes, float]:
    """
    Run K-prototypes clustering for mixed data.

    K-prototypes combines K-means (numeric) with K-modes (categorical).
    Gamma controls relative weight of categorical vs numeric features.
    """
    logger.info(f"Running K-prototypes with k={n_clusters}, gamma={gamma}...")

    # Standardize continuous features
    scaler = StandardScaler()
    X_continuous = scaler.fit_transform(df_features[continuous_cols])

    # Categorical as string array
    X_categorical = df_features[categorical_cols].values

    # Combine
    X = np.hstack([X_continuous, X_categorical])
    cat_indices = list(range(len(continuous_cols), len(continuous_cols) + len(categorical_cols)))

    # Fit K-prototypes
    kproto = KPrototypes(n_clusters=n_clusters, init='Cao', n_init=10,
                         gamma=gamma, random_state=42, n_jobs=-1)
    labels = kproto.fit_predict(X, categorical=cat_indices)

    # Calculate silhouette score on continuous features only
    silhouette = silhouette_score(X_continuous, labels)
    logger.info(f"Silhouette score: {silhouette:.3f}")

    return labels, kproto, silhouette


def find_optimal_k(df_features: pd.DataFrame, continuous_cols: List[str],
                   categorical_cols: List[str], k_range: range = range(2, 8)) -> pd.DataFrame:
    """
    Evaluate different cluster counts using cost and silhouette metrics.
    """
    logger.info("Finding optimal k...")

    # Prepare data
    scaler = StandardScaler()
    X_continuous = scaler.fit_transform(df_features[continuous_cols])
    X_categorical = df_features[categorical_cols].values
    X = np.hstack([X_continuous, X_categorical])
    cat_indices = list(range(len(continuous_cols), len(continuous_cols) + len(categorical_cols)))

    results = []
    for k in k_range:
        logger.info(f"  Testing k={k}...")
        kproto = KPrototypes(n_clusters=k, init='Cao', n_init=5, gamma=1.5, random_state=42)
        labels = kproto.fit_predict(X, categorical=cat_indices)
        cost = kproto.cost_
        silhouette = silhouette_score(X_continuous, labels)
        results.append({'k': k, 'cost': cost, 'silhouette': silhouette})

    df_results = pd.DataFrame(results)
    logger.info("\nK selection results:")
    logger.info(df_results.to_string(index=False))

    return df_results


def analyze_cluster_outcomes(df_features: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """
    Analyze engagement outcomes by cluster.

    This validates whether clusters have different click rates
    WITHOUT using clicks as a clustering input.
    """
    df_analysis = df_features.copy()
    df_analysis['cluster'] = labels

    # Aggregate by cluster
    cluster_stats = df_analysis.groupby('cluster').agg({
        'ever_engaged': ['sum', 'mean', 'count'],
        'ever_clicked': ['sum', 'mean']
    }).round(4)
    cluster_stats.columns = ['engaged_count', 'engage_rate', 'n_participants',
                            'clicked_count', 'click_rate']

    logger.info("\nCluster Outcome Analysis:")
    logger.info(cluster_stats.to_string())

    # Chi-square test for engagement independence
    contingency = pd.crosstab(df_analysis['cluster'], df_analysis['ever_engaged'])
    chi2, p_value, dof, expected = chi2_contingency(contingency)
    logger.info(f"\nChi-square test (engagement by cluster):")
    logger.info(f"  Chi2: {chi2:.2f}, p-value: {p_value:.4f}, df: {dof}")

    if p_value < 0.05:
        logger.info("  => Clusters show SIGNIFICANTLY different engagement rates!")
    else:
        logger.info("  => No significant difference in engagement across clusters")

    return cluster_stats


def profile_clusters(df_features: pd.DataFrame, labels: np.ndarray,
                     continuous_cols: List[str], categorical_cols: List[str]) -> pd.DataFrame:
    """
    Create cluster profiles showing mean/mode of features.
    """
    df_profile = df_features.copy()
    df_profile['cluster'] = labels

    # Continuous feature profiles
    continuous_profiles = df_profile.groupby('cluster')[continuous_cols].mean()

    # Categorical feature profiles (mode)
    categorical_profiles = df_profile.groupby('cluster')[categorical_cols].agg(
        lambda x: x.value_counts().index[0] if len(x) > 0 else 'Unknown'
    )

    # Combine
    profiles = pd.concat([continuous_profiles, categorical_profiles], axis=1)

    logger.info("\nCluster Profiles:")
    logger.info(profiles.to_string())

    return profiles


def plot_cluster_analysis(df_features: pd.DataFrame, labels: np.ndarray, famd_coords: pd.DataFrame,
                          cluster_stats: pd.DataFrame, profiles: pd.DataFrame,
                          continuous_cols: List[str]):
    """Generate visualization plots for cluster analysis."""

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # 1. FAMD scatter plot colored by cluster
    ax1 = axes[0, 0]
    scatter = ax1.scatter(famd_coords[0], famd_coords[1], c=labels, cmap='viridis',
                         s=10, alpha=0.5)
    ax1.set_xlabel('FAMD Component 1')
    ax1.set_ylabel('FAMD Component 2')
    ax1.set_title('FAMD: Participants Colored by Cluster')
    plt.colorbar(scatter, ax=ax1, label='Cluster')

    # 2. FAMD scatter with engagement overlay
    ax2 = axes[0, 1]
    non_engaged = ~df_features['ever_engaged'].astype(bool)
    engaged = df_features['ever_engaged'].astype(bool)

    ax2.scatter(famd_coords.loc[non_engaged, 0], famd_coords.loc[non_engaged, 1],
               c='lightgray', s=5, alpha=0.3, label=f'Non-engaged (n={non_engaged.sum():,})')
    ax2.scatter(famd_coords.loc[engaged, 0], famd_coords.loc[engaged, 1],
               c='red', s=40, alpha=0.9, label=f'Engaged (n={engaged.sum():,})')
    ax2.set_xlabel('FAMD Component 1')
    ax2.set_ylabel('FAMD Component 2')
    ax2.set_title('FAMD: Engaged Participants Highlighted')
    ax2.legend()

    # 3. Engagement rate by cluster
    ax3 = axes[1, 0]
    x = range(len(cluster_stats))
    bars = ax3.bar(x, cluster_stats['engage_rate'] * 100, color='steelblue')
    ax3.axhline(y=df_features['ever_engaged'].mean() * 100, color='red',
               linestyle='--', label='Overall rate')
    ax3.set_xlabel('Cluster')
    ax3.set_ylabel('Engagement Rate (%)')
    ax3.set_title('Engagement Rate by Cluster')
    ax3.legend()

    # Add count labels on bars
    for i, (bar, count) in enumerate(zip(bars, cluster_stats['n_participants'])):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f'n={count:,}', ha='center', va='bottom', fontsize=8)

    # 4. Cluster profile heatmap (normalized)
    ax4 = axes[1, 1]
    profile_normalized = profiles[continuous_cols].apply(
        lambda x: (x - x.mean()) / x.std(), axis=0
    )
    sns.heatmap(profile_normalized.T, annot=True, fmt='.2f', cmap='RdYlBu_r',
               ax=ax4, center=0)
    ax4.set_title('Cluster Feature Profiles (Standardized)')
    ax4.set_xlabel('Cluster')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'phase1_cluster_analysis.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved plot to {OUTPUT_DIR / 'phase1_cluster_analysis.png'}")
    plt.close()


def main():
    """Run Phase 1 demographics clustering analysis."""
    logger.info("="*60)
    logger.info("PHASE 1: DEMOGRAPHICS-ONLY CLUSTERING")
    logger.info("="*60)

    # Load data
    df = load_data()

    # Prepare features
    df_features, continuous_cols, categorical_cols = prepare_phase1_features(df)
    logger.info(f"Continuous features: {continuous_cols}")
    logger.info(f"Categorical features: {categorical_cols}")

    # Run FAMD
    famd_coords, famd_model = run_famd(df_features, continuous_cols, categorical_cols)

    # Find optimal k
    k_results = find_optimal_k(df_features, continuous_cols, categorical_cols, k_range=range(2, 8))
    k_results.to_csv(OUTPUT_DIR / 'k_selection_results.csv', index=False)

    # Select k based on silhouette (or elbow)
    optimal_k = k_results.loc[k_results['silhouette'].idxmax(), 'k']
    logger.info(f"\nSelected k={optimal_k} based on silhouette score")

    # Final clustering
    labels, kproto, silhouette = run_kprototypes(df_features, continuous_cols, categorical_cols,
                                                   n_clusters=int(optimal_k))

    # Analyze outcomes
    cluster_stats = analyze_cluster_outcomes(df_features, labels)
    cluster_stats.to_csv(OUTPUT_DIR / 'phase1_cluster_outcomes.csv')

    # Profile clusters
    profiles = profile_clusters(df_features, labels, continuous_cols, categorical_cols)
    profiles.to_csv(OUTPUT_DIR / 'phase1_cluster_profiles.csv')

    # Visualize
    plot_cluster_analysis(df_features, labels, famd_coords, cluster_stats, profiles, continuous_cols)

    # Save results
    df_features['cluster'] = labels
    df_features.to_parquet(OUTPUT_DIR / 'phase1_clustered_participants.parquet', index=False)

    # Save FAMD coordinates
    famd_coords_df = famd_coords.copy()
    famd_coords_df['participant_id'] = df_features['participant_id'].values
    famd_coords_df['cluster'] = labels
    famd_coords_df.to_parquet(OUTPUT_DIR / 'phase1_famd_coordinates.parquet', index=False)

    logger.info("\n" + "="*60)
    logger.info("PHASE 1 COMPLETE")
    logger.info(f"Results saved to {OUTPUT_DIR}")
    logger.info("="*60)

    return df_features, labels, famd_coords, famd_model


if __name__ == '__main__':
    main()
