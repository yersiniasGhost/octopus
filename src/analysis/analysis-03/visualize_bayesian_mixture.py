"""
Bayesian Gaussian Mixture Model Visualizations

Comprehensive visualizations for Phase 3 clustering results including:
1. Cluster size and engagement comparison
2. Soft probability distributions (assignment uncertainty)
3. Component weights from Dirichlet process
4. Feature profiles heatmap
5. PCA projection with cluster assignments
6. Probability distribution per participant
7. Engagement vs confidence relationship
"""
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

OUTPUT_DIR = Path('/home/yersinia/devel/octopus/data/clustering_results-03')

# Cluster names for readability
CLUSTER_NAMES = {
    0: 'Multi-Channel Active',
    1: 'Email Baseline',
    2: 'Standard Participants',
    3: 'Super Performers',
    4: 'New/Minimal Exposure',
    5: 'Low-Exposure Email Only',
    6: 'Moderate Responders',
    7: 'High-Burden Engagers',
    8: 'High-Frequency Responders',
    9: 'Moderate Text Users'
}


def load_data():
    """Load all Phase 3 clustering outputs."""
    df = pd.read_parquet(OUTPUT_DIR / 'phase3_clustered_participants.parquet')
    probs = np.load(OUTPUT_DIR / 'cluster_probabilities.npy')
    stats = pd.read_csv(OUTPUT_DIR / 'phase3_cluster_stats.csv', index_col='cluster')
    profiles = pd.read_csv(OUTPUT_DIR / 'phase3_cluster_profiles.csv', index_col='cluster')

    logger.info(f"Loaded {len(df)} participants, {probs.shape[1]} clusters")
    return df, probs, stats, profiles


def plot_cluster_overview(stats: pd.DataFrame, figsize=(14, 5)):
    """Plot cluster sizes and engagement rates side by side."""
    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Sort by engagement rate for better visualization
    stats_sorted = stats.sort_values('rate', ascending=True)
    clusters = stats_sorted.index
    names = [CLUSTER_NAMES.get(c, f'Cluster {c}') for c in clusters]

    # Color by engagement (green = high, red = low)
    colors = plt.cm.RdYlGn(stats_sorted['rate'] / stats_sorted['rate'].max())

    # 1. Cluster sizes
    ax1 = axes[0]
    bars1 = ax1.barh(names, stats_sorted['n'], color=colors)
    ax1.set_xlabel('Number of Participants')
    ax1.set_title('Cluster Sizes', fontsize=12, fontweight='bold')
    for i, (bar, n) in enumerate(zip(bars1, stats_sorted['n'])):
        ax1.text(bar.get_width() + 20, bar.get_y() + bar.get_height()/2,
                f'{n:,}', va='center', fontsize=9)

    # 2. Engagement rates
    ax2 = axes[1]
    bars2 = ax2.barh(names, stats_sorted['rate'] * 100, color=colors)
    ax2.axvline(x=stats['rate'].mean() * 100, color='black', linestyle='--',
               linewidth=2, label=f'Overall: {stats["rate"].mean()*100:.1f}%')
    ax2.set_xlabel('Engagement Rate (%)')
    ax2.set_title('Engagement Rate by Cluster', fontsize=12, fontweight='bold')
    ax2.legend(loc='lower right')
    for bar, rate in zip(bars2, stats_sorted['rate']):
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'{rate*100:.1f}%', va='center', fontsize=9)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_cluster_overview.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved cluster overview plot")
    plt.close()


def plot_probability_distributions(probs: np.ndarray, df: pd.DataFrame, figsize=(16, 10)):
    """Visualize soft probability distributions."""
    fig, axes = plt.subplots(2, 2, figsize=figsize)

    # 1. Max probability histogram (assignment confidence)
    ax1 = axes[0, 0]
    max_probs = probs.max(axis=1)
    ax1.hist(max_probs, bins=50, edgecolor='black', alpha=0.7, color='steelblue')
    ax1.axvline(x=max_probs.mean(), color='red', linestyle='--', linewidth=2,
               label=f'Mean: {max_probs.mean():.3f}')
    ax1.axvline(x=np.median(max_probs), color='orange', linestyle='--', linewidth=2,
               label=f'Median: {np.median(max_probs):.3f}')
    ax1.set_xlabel('Maximum Cluster Probability')
    ax1.set_ylabel('Count')
    ax1.set_title('Assignment Confidence Distribution', fontsize=12, fontweight='bold')
    ax1.legend()

    # 2. Entropy distribution (uncertainty measure)
    ax2 = axes[0, 1]
    entropy = -np.sum(probs * np.log(probs + 1e-10), axis=1)
    ax2.hist(entropy, bins=50, edgecolor='black', alpha=0.7, color='coral')
    ax2.axvline(x=entropy.mean(), color='red', linestyle='--', linewidth=2,
               label=f'Mean: {entropy.mean():.3f}')
    ax2.set_xlabel('Entropy (Higher = More Uncertain)')
    ax2.set_ylabel('Count')
    ax2.set_title('Cluster Assignment Entropy', fontsize=12, fontweight='bold')
    ax2.legend()

    # 3. Second-best probability (ambiguity)
    ax3 = axes[1, 0]
    sorted_probs = np.sort(probs, axis=1)[:, ::-1]
    second_best = sorted_probs[:, 1]
    ax3.hist(second_best, bins=50, edgecolor='black', alpha=0.7, color='mediumpurple')
    ax3.set_xlabel('Second-Best Cluster Probability')
    ax3.set_ylabel('Count')
    ax3.set_title('Assignment Ambiguity (2nd Best Prob)', fontsize=12, fontweight='bold')

    # 4. Confidence vs Engagement
    ax4 = axes[1, 1]
    engaged = df['ever_engaged'].values
    ax4.scatter(max_probs[~engaged], entropy[~engaged], alpha=0.3, s=10,
               c='lightgray', label='Not Engaged')
    ax4.scatter(max_probs[engaged], entropy[engaged], alpha=0.7, s=30,
               c='red', label='Engaged')
    ax4.set_xlabel('Assignment Confidence (Max Prob)')
    ax4.set_ylabel('Entropy')
    ax4.set_title('Confidence vs Uncertainty by Engagement', fontsize=12, fontweight='bold')
    ax4.legend()

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_probability_distributions.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved probability distributions plot")
    plt.close()


def plot_component_weights(probs: np.ndarray, figsize=(12, 5)):
    """Visualize Dirichlet process component weights."""
    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Effective weight = proportion of participants primarily assigned
    hard_assignments = probs.argmax(axis=1)
    cluster_counts = np.bincount(hard_assignments, minlength=probs.shape[1])
    effective_weights = cluster_counts / len(probs)

    # Also compute mean probability per cluster (soft weight)
    soft_weights = probs.mean(axis=0)

    clusters = range(probs.shape[1])
    names = [CLUSTER_NAMES.get(c, f'C{c}')[:15] for c in clusters]

    # 1. Effective weights (hard assignment proportions)
    ax1 = axes[0]
    colors = plt.cm.tab10(np.arange(len(clusters)))
    bars1 = ax1.bar(names, effective_weights * 100, color=colors, edgecolor='black')
    ax1.set_ylabel('Proportion (%)')
    ax1.set_xlabel('Cluster')
    ax1.set_title('Component Weights (Hard Assignments)', fontsize=12, fontweight='bold')
    ax1.tick_params(axis='x', rotation=45)
    for bar, w in zip(bars1, effective_weights):
        if w > 0.02:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{w*100:.1f}%', ha='center', fontsize=8)

    # 2. Soft weights (mean probabilities)
    ax2 = axes[1]
    bars2 = ax2.bar(names, soft_weights * 100, color=colors, edgecolor='black', alpha=0.7)
    ax2.set_ylabel('Mean Probability (%)')
    ax2.set_xlabel('Cluster')
    ax2.set_title('Component Weights (Soft Probabilities)', fontsize=12, fontweight='bold')
    ax2.tick_params(axis='x', rotation=45)
    for bar, w in zip(bars2, soft_weights):
        if w > 0.02:
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{w*100:.1f}%', ha='center', fontsize=8)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_component_weights.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved component weights plot")
    plt.close()


def plot_feature_profiles_heatmap(profiles: pd.DataFrame, stats: pd.DataFrame, figsize=(14, 10)):
    """Create heatmap of standardized feature profiles by cluster."""
    # Standardize profiles for comparison
    profiles_norm = profiles.apply(lambda x: (x - x.mean()) / x.std(), axis=0)

    # Sort clusters by engagement rate
    sorted_clusters = stats.sort_values('rate', ascending=False).index
    profiles_norm = profiles_norm.loc[sorted_clusters]

    # Create readable names
    cluster_labels = [f"{CLUSTER_NAMES.get(c, f'C{c}')} ({stats.loc[c, 'rate']*100:.1f}%)"
                     for c in sorted_clusters]

    # Rename features for readability
    feature_names = {
        'estimated_income': 'Income',
        'household_size': 'HH Size',
        'total_energy_burden': 'Energy Burden',
        'living_area_sqft': 'Living Area',
        'house_age': 'House Age',
        'campaign_count': 'Total Campaigns',
        'email_count': 'Email Count',
        'total_text_count': 'Text Count',
        'exposure_days': 'Exposure Days',
        'msgtype_informational_count': 'Informational',
        'msgtype_motivational_struggle_count': 'Motivational',
        'msgtype_personalized_qualified_count': 'Personalized',
        'msgtype_relief_reassurance_count': 'Relief',
        'msgtype_savings_financial_count': 'Savings',
        'msgtype_urgency_deadline_count': 'Urgency'
    }
    profiles_norm.columns = [feature_names.get(c, c) for c in profiles_norm.columns]

    # Create figure with better proportions
    fig, ax = plt.subplots(figsize=figsize)

    sns.heatmap(profiles_norm.T, annot=True, fmt='.2f', cmap='RdBu_r',
               center=0, ax=ax, cbar_kws={'label': 'Standardized Value'},
               xticklabels=cluster_labels, yticklabels=profiles_norm.columns)

    ax.set_title('Cluster Feature Profiles\n(Sorted by Engagement Rate, High→Low)',
                fontsize=14, fontweight='bold')
    ax.set_xlabel('Cluster (Engagement Rate)')
    ax.set_ylabel('Feature')

    # Group feature labels
    ax.axhline(y=5, color='white', linewidth=3)  # After demographics
    ax.axhline(y=9, color='white', linewidth=3)  # After exposure

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_feature_profiles_heatmap.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved feature profiles heatmap")
    plt.close()


def plot_pca_projection(df: pd.DataFrame, probs: np.ndarray, stats: pd.DataFrame, figsize=(16, 6)):
    """PCA projection colored by cluster and engagement."""
    # Get feature columns
    feature_cols = [
        'estimated_income', 'household_size', 'total_energy_burden',
        'living_area_sqft', 'house_age', 'campaign_count', 'email_count',
        'total_text_count', 'exposure_days'
    ]
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
    all_features = feature_cols + msgtype_cols

    # Prepare data
    X = df[all_features].fillna(df[all_features].median())
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # PCA
    pca = PCA(n_components=2)
    X_2d = pca.fit_transform(X_scaled)

    fig, axes = plt.subplots(1, 3, figsize=figsize)

    # 1. Colored by cluster (hard assignment)
    ax1 = axes[0]
    clusters = df['cluster_stepmix'].values
    scatter1 = ax1.scatter(X_2d[:, 0], X_2d[:, 1], c=clusters, cmap='tab10',
                          s=15, alpha=0.6)
    ax1.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
    ax1.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
    ax1.set_title('Colored by Cluster Assignment', fontsize=12, fontweight='bold')

    # Add cluster labels at centroids
    for c in range(probs.shape[1]):
        mask = clusters == c
        if mask.sum() > 0:
            cx, cy = X_2d[mask, 0].mean(), X_2d[mask, 1].mean()
            ax1.annotate(CLUSTER_NAMES.get(c, f'C{c}')[:10], (cx, cy),
                        fontsize=8, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

    # 2. Colored by assignment confidence
    ax2 = axes[1]
    max_prob = probs.max(axis=1)
    scatter2 = ax2.scatter(X_2d[:, 0], X_2d[:, 1], c=max_prob, cmap='RdYlGn',
                          s=15, alpha=0.6)
    ax2.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
    ax2.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
    ax2.set_title('Colored by Assignment Confidence', fontsize=12, fontweight='bold')
    plt.colorbar(scatter2, ax=ax2, label='Max Probability')

    # 3. Engagement highlighted
    ax3 = axes[2]
    engaged = df['ever_engaged'].values.astype(bool)
    ax3.scatter(X_2d[~engaged, 0], X_2d[~engaged, 1], c='lightgray', s=5, alpha=0.3,
               label=f'Not Engaged ({(~engaged).sum():,})')
    ax3.scatter(X_2d[engaged, 0], X_2d[engaged, 1], c='red', s=40, alpha=0.8,
               label=f'Engaged ({engaged.sum():,})')
    ax3.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
    ax3.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
    ax3.set_title('Engagement Highlighted', fontsize=12, fontweight='bold')
    ax3.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_pca_projection.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved PCA projection plot")
    plt.close()


def plot_probability_heatmap_sample(probs: np.ndarray, df: pd.DataFrame, n_sample=100, figsize=(14, 8)):
    """Show probability distribution across clusters for sample participants."""
    # Sample engaged and non-engaged participants
    engaged_idx = df[df['ever_engaged'] == True].index[:n_sample//2].tolist()
    not_engaged_idx = df[df['ever_engaged'] == False].index[:n_sample//2].tolist()

    # Get numeric positions
    engaged_pos = [df.index.get_loc(i) for i in engaged_idx]
    not_engaged_pos = [df.index.get_loc(i) for i in not_engaged_idx]
    sample_idx = engaged_pos + not_engaged_pos

    sample_probs = probs[sample_idx]
    sample_engaged = [True] * len(engaged_pos) + [False] * len(not_engaged_pos)

    # Sort by max probability for visualization
    sorted_order = np.argsort(-sample_probs.max(axis=1))
    sample_probs = sample_probs[sorted_order]
    sample_engaged = [sample_engaged[i] for i in sorted_order]

    fig, ax = plt.subplots(figsize=figsize)

    # Create heatmap
    cluster_names_short = [CLUSTER_NAMES.get(i, f'C{i}')[:12] for i in range(probs.shape[1])]
    sns.heatmap(sample_probs, cmap='YlOrRd', ax=ax,
               xticklabels=cluster_names_short,
               yticklabels=False,
               cbar_kws={'label': 'Cluster Probability'})

    # Add engagement indicator on the side
    for i, eng in enumerate(sample_engaged):
        color = 'green' if eng else 'lightgray'
        ax.add_patch(plt.Rectangle((-0.8, i), 0.5, 1, color=color, clip_on=False))

    ax.set_title(f'Soft Cluster Assignments (n={n_sample} sample)\nGreen bar = Engaged',
                fontsize=12, fontweight='bold')
    ax.set_xlabel('Cluster')
    ax.set_ylabel('Participants (sorted by confidence)')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_probability_heatmap_sample.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved probability heatmap sample")
    plt.close()


def plot_engagement_by_confidence(df: pd.DataFrame, probs: np.ndarray, figsize=(12, 5)):
    """Analyze relationship between assignment confidence and engagement."""
    max_prob = probs.max(axis=1)
    engaged = df['ever_engaged'].values
    clusters = df['cluster_stepmix'].values

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # 1. Engagement rate by confidence bin
    ax1 = axes[0]
    confidence_bins = pd.cut(max_prob, bins=[0, 0.8, 0.9, 0.95, 0.99, 1.0],
                            labels=['<80%', '80-90%', '90-95%', '95-99%', '>99%'])

    engagement_by_conf = pd.DataFrame({'confidence': confidence_bins, 'engaged': engaged})
    rates = engagement_by_conf.groupby('confidence', observed=True)['engaged'].agg(['mean', 'count'])

    bars = ax1.bar(range(len(rates)), rates['mean'] * 100,
                  color='steelblue', edgecolor='black')
    ax1.set_xticks(range(len(rates)))
    ax1.set_xticklabels(rates.index)
    ax1.set_xlabel('Assignment Confidence')
    ax1.set_ylabel('Engagement Rate (%)')
    ax1.set_title('Engagement vs Assignment Confidence', fontsize=12, fontweight='bold')

    for bar, (_, row) in zip(bars, rates.iterrows()):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f'n={int(row["count"]):,}', ha='center', fontsize=9)

    # 2. Confidence distribution by cluster
    ax2 = axes[1]
    cluster_conf = pd.DataFrame({
        'cluster': clusters,
        'confidence': max_prob,
        'name': [CLUSTER_NAMES.get(c, f'C{c}')[:15] for c in clusters]
    })

    # Sort by median confidence
    order = cluster_conf.groupby('name')['confidence'].median().sort_values().index

    sns.boxplot(data=cluster_conf, x='name', y='confidence', order=order, ax=ax2,
               palette='viridis')
    ax2.set_xlabel('Cluster')
    ax2.set_ylabel('Assignment Confidence')
    ax2.set_title('Confidence Distribution by Cluster', fontsize=12, fontweight='bold')
    ax2.tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'bayesian_engagement_confidence.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved engagement by confidence plot")
    plt.close()


def plot_summary_dashboard(df: pd.DataFrame, probs: np.ndarray, stats: pd.DataFrame, figsize=(18, 14)):
    """Create comprehensive summary dashboard."""
    fig = plt.figure(figsize=figsize)

    # Create grid
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

    # 1. Cluster sizes (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    stats_sorted = stats.sort_values('n', ascending=True)
    names = [CLUSTER_NAMES.get(c, f'C{c}')[:15] for c in stats_sorted.index]
    colors = plt.cm.tab10(stats_sorted.index / 10)
    ax1.barh(names, stats_sorted['n'], color=colors)
    ax1.set_xlabel('Participants')
    ax1.set_title('Cluster Sizes', fontweight='bold')

    # 2. Engagement rates (top middle)
    ax2 = fig.add_subplot(gs[0, 1])
    stats_sorted = stats.sort_values('rate', ascending=True)
    names = [CLUSTER_NAMES.get(c, f'C{c}')[:15] for c in stats_sorted.index]
    colors = plt.cm.RdYlGn(stats_sorted['rate'] / stats_sorted['rate'].max())
    ax2.barh(names, stats_sorted['rate'] * 100, color=colors)
    ax2.axvline(x=stats['rate'].mean() * 100, color='black', linestyle='--', linewidth=2)
    ax2.set_xlabel('Engagement Rate (%)')
    ax2.set_title('Engagement by Cluster', fontweight='bold')

    # 3. Confidence distribution (top right)
    ax3 = fig.add_subplot(gs[0, 2])
    max_prob = probs.max(axis=1)
    ax3.hist(max_prob, bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    ax3.axvline(x=max_prob.mean(), color='red', linestyle='--', linewidth=2)
    ax3.set_xlabel('Max Probability')
    ax3.set_ylabel('Count')
    ax3.set_title(f'Assignment Confidence\n(Mean: {max_prob.mean():.3f})', fontweight='bold')

    # 4. PCA with clusters (middle row, spans 2 columns)
    ax4 = fig.add_subplot(gs[1, :2])
    feature_cols = ['estimated_income', 'household_size', 'total_energy_burden',
                   'living_area_sqft', 'house_age', 'campaign_count', 'email_count',
                   'total_text_count', 'exposure_days']
    msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
    X = df[feature_cols + msgtype_cols].fillna(df[feature_cols + msgtype_cols].median())
    X_scaled = StandardScaler().fit_transform(X)
    X_2d = PCA(n_components=2).fit_transform(X_scaled)

    clusters = df['cluster_stepmix'].values
    scatter = ax4.scatter(X_2d[:, 0], X_2d[:, 1], c=clusters, cmap='tab10', s=10, alpha=0.5)
    ax4.set_xlabel('PC1')
    ax4.set_ylabel('PC2')
    ax4.set_title('PCA Projection by Cluster', fontweight='bold')

    # Add cluster centroids
    for c in range(probs.shape[1]):
        mask = clusters == c
        if mask.sum() > 0:
            cx, cy = X_2d[mask, 0].mean(), X_2d[mask, 1].mean()
            ax4.annotate(str(c), (cx, cy), fontsize=12, fontweight='bold',
                        color='black', ha='center', va='center',
                        bbox=dict(boxstyle='circle', facecolor='white', edgecolor='black'))

    # 5. Engagement overlay (middle right)
    ax5 = fig.add_subplot(gs[1, 2])
    engaged = df['ever_engaged'].values.astype(bool)
    ax5.scatter(X_2d[~engaged, 0], X_2d[~engaged, 1], c='lightgray', s=5, alpha=0.3)
    ax5.scatter(X_2d[engaged, 0], X_2d[engaged, 1], c='red', s=30, alpha=0.7)
    ax5.set_xlabel('PC1')
    ax5.set_ylabel('PC2')
    ax5.set_title(f'Engaged Highlighted (n={engaged.sum()})', fontweight='bold')

    # 6. Key metrics summary (bottom left)
    ax6 = fig.add_subplot(gs[2, 0])
    ax6.axis('off')
    metrics_text = f"""
    KEY METRICS
    ───────────────────
    Total Participants: {len(df):,}
    Total Clusters: {probs.shape[1]}

    Engagement:
      Overall Rate: {df['ever_engaged'].mean()*100:.1f}%
      Top Cluster: {stats['rate'].max()*100:.1f}%
      Bottom Cluster: {stats['rate'].min()*100:.1f}%

    Assignment Quality:
      Mean Confidence: {max_prob.mean():.3f}
      >95% Confident: {(max_prob > 0.95).mean()*100:.1f}%
    """
    ax6.text(0.1, 0.9, metrics_text, transform=ax6.transAxes, fontsize=11,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # 7. Component weights (bottom middle)
    ax7 = fig.add_subplot(gs[2, 1])
    hard_assignments = probs.argmax(axis=1)
    cluster_counts = np.bincount(hard_assignments, minlength=probs.shape[1])
    effective_weights = cluster_counts / len(probs)
    ax7.bar(range(len(effective_weights)), effective_weights * 100,
           color=plt.cm.tab10(np.arange(len(effective_weights)) / 10), edgecolor='black')
    ax7.set_xlabel('Cluster')
    ax7.set_ylabel('Weight (%)')
    ax7.set_title('Dirichlet Process Weights', fontweight='bold')

    # 8. Engagement vs Confidence (bottom right)
    ax8 = fig.add_subplot(gs[2, 2])
    confidence_bins = pd.cut(max_prob, bins=[0, 0.9, 0.95, 0.99, 1.0],
                            labels=['<90%', '90-95%', '95-99%', '>99%'])
    engagement_by_conf = pd.DataFrame({'conf': confidence_bins, 'eng': df['ever_engaged']})
    rates = engagement_by_conf.groupby('conf', observed=True)['eng'].mean() * 100
    ax8.bar(range(len(rates)), rates.values, color='coral', edgecolor='black')
    ax8.set_xticks(range(len(rates)))
    ax8.set_xticklabels(rates.index)
    ax8.set_xlabel('Confidence Level')
    ax8.set_ylabel('Engagement Rate (%)')
    ax8.set_title('Engagement by Confidence', fontweight='bold')

    plt.suptitle('Bayesian Gaussian Mixture Model - Summary Dashboard',
                fontsize=16, fontweight='bold', y=1.02)

    plt.savefig(OUTPUT_DIR / 'bayesian_summary_dashboard.png', dpi=150, bbox_inches='tight')
    logger.info(f"Saved summary dashboard")
    plt.close()


def main():
    """Generate all Bayesian mixture model visualizations."""
    logger.info("="*60)
    logger.info("BAYESIAN GAUSSIAN MIXTURE MODEL VISUALIZATIONS")
    logger.info("="*60)

    # Load data
    df, probs, stats, profiles = load_data()

    # Generate all plots
    logger.info("\n1. Generating cluster overview...")
    plot_cluster_overview(stats)

    logger.info("2. Generating probability distributions...")
    plot_probability_distributions(probs, df)

    logger.info("3. Generating component weights...")
    plot_component_weights(probs)

    logger.info("4. Generating feature profiles heatmap...")
    plot_feature_profiles_heatmap(profiles, stats)

    logger.info("5. Generating PCA projections...")
    plot_pca_projection(df, probs, stats)

    logger.info("6. Generating probability heatmap sample...")
    plot_probability_heatmap_sample(probs, df)

    logger.info("7. Generating engagement by confidence...")
    plot_engagement_by_confidence(df, probs)

    logger.info("8. Generating summary dashboard...")
    plot_summary_dashboard(df, probs, stats)

    logger.info("\n" + "="*60)
    logger.info("VISUALIZATION COMPLETE")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info("Generated files:")
    for f in sorted(OUTPUT_DIR.glob('bayesian_*.png')):
        logger.info(f"  - {f.name}")
    logger.info("="*60)


if __name__ == '__main__':
    main()
