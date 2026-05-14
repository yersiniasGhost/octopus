"""
UMAP Visualization for Applicant Analysis
ANALYSIS-05: Message Classification Focus

Generate UMAP projections to visualize:
1. Cluster structure in 2D
2. Applicant distribution across clusters
3. Channel exposure patterns
4. Treatment effect visualization
5. MESSAGE TYPE PATTERNS (NEW) - Visualize which message types drive conversions

Output: PNG visualizations in clustering_results-05/
"""
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import umap

from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class UMAPVisualizer:
    """UMAP visualization for applicant clustering analysis."""

    def __init__(self, data_path: str = '/home/yersinia/devel/octopus/data/clustering_results-05'):
        self.data_path = Path(data_path)
        self.df: Optional[pd.DataFrame] = None
        self.embedding: Optional[np.ndarray] = None

    def load_data(self) -> pd.DataFrame:
        """Load Phase 3 Bayesian integration data."""
        logger.info("Loading data...")
        self.df = pd.read_parquet(self.data_path / 'phase3_bayesian_integration.parquet')
        logger.info(f"Loaded {len(self.df)} participants")
        return self.df

    def compute_umap(self, n_neighbors: int = 30, min_dist: float = 0.3,
                     random_state: int = 42) -> np.ndarray:
        """Compute UMAP embedding from features."""
        logger.info("Computing UMAP embedding...")

        # Select features for UMAP
        feature_cols = [
            'household_income', 'household_size', 'house_age',
            'total_energy_burden', 'living_area_sqft',
            'campaign_count', 'email_count', 'total_text_count',
            'channel_diversity', 'exposure_days'
        ]
        # Add message type features
        msg_cols = [c for c in self.df.columns if c.startswith('msgtype_') and c.endswith('_count')]
        feature_cols.extend(msg_cols)

        available_cols = [c for c in feature_cols if c in self.df.columns]
        X = self.df[available_cols].copy()

        # Cap extreme values
        for col in available_cols:
            cap = X[col].quantile(0.99)
            X[col] = X[col].clip(upper=cap)

        # Impute and scale
        imputer = SimpleImputer(strategy='median')
        X_imputed = imputer.fit_transform(X)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_imputed)

        # Fit UMAP
        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            n_components=2,
            metric='euclidean',
            random_state=random_state
        )
        self.embedding = reducer.fit_transform(X_scaled)
        logger.info("UMAP embedding complete")

        return self.embedding

    def plot_applicant_distribution(self, save: bool = True):
        """Plot UMAP colored by applicant status."""
        logger.info("Plotting applicant distribution...")

        fig, ax = plt.subplots(figsize=(12, 10))

        # Non-applicants (gray, smaller, background)
        non_app_mask = ~self.df['is_applicant']
        ax.scatter(
            self.embedding[non_app_mask, 0],
            self.embedding[non_app_mask, 1],
            c='lightgray', s=5, alpha=0.3, label='Non-applicant'
        )

        # Applicants (red, larger, foreground)
        app_mask = self.df['is_applicant']
        ax.scatter(
            self.embedding[app_mask, 0],
            self.embedding[app_mask, 1],
            c='red', s=30, alpha=0.8, label='Applicant', edgecolor='darkred', linewidth=0.5
        )

        ax.set_xlabel('UMAP 1', fontsize=12)
        ax.set_ylabel('UMAP 2', fontsize=12)
        ax.set_title('UMAP: Applicant Distribution\n(Red = Applied, Gray = Did Not Apply)', fontsize=14)
        ax.legend(loc='upper right', fontsize=10)

        plt.tight_layout()
        if save:
            path = self.data_path / 'umap_applicant_distribution.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved to {path}")
        plt.close()

    def plot_phase3_clusters(self, save: bool = True):
        """Plot UMAP colored by Phase 3 probabilistic clusters."""
        logger.info("Plotting Phase 3 clusters...")

        fig, ax = plt.subplots(figsize=(12, 10))

        clusters = self.df['phase3_cluster'].unique()
        n_clusters = len(clusters)
        cmap = plt.cm.get_cmap('tab10', n_clusters)

        for i, cluster in enumerate(sorted(clusters)):
            mask = self.df['phase3_cluster'] == cluster
            n_in_cluster = mask.sum()
            app_rate = self.df[mask]['is_applicant'].mean() * 100

            ax.scatter(
                self.embedding[mask, 0],
                self.embedding[mask, 1],
                c=[cmap(i)], s=10, alpha=0.6,
                label=f'Cluster {cluster} (n={n_in_cluster}, {app_rate:.1f}%)'
            )

        ax.set_xlabel('UMAP 1', fontsize=12)
        ax.set_ylabel('UMAP 2', fontsize=12)
        ax.set_title('UMAP: Phase 3 Probabilistic Clusters\n(with application rates)', fontsize=14)
        ax.legend(loc='upper right', fontsize=8, ncol=2)

        plt.tight_layout()
        if save:
            path = self.data_path / 'umap_phase3_clusters.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved to {path}")
        plt.close()

    def plot_channel_exposure(self, save: bool = True):
        """Plot UMAP colored by channel combination."""
        logger.info("Plotting channel exposure...")

        fig, ax = plt.subplots(figsize=(12, 10))

        channel_colors = {
            'letter_only': 'purple',
            'letter+email': 'blue',
            'letter+text': 'green',
            'letter+email+text': 'orange'
        }

        for channel, color in channel_colors.items():
            mask = self.df['channel_combo'] == channel
            n_in_channel = mask.sum()
            app_rate = self.df[mask]['is_applicant'].mean() * 100 if mask.any() else 0

            ax.scatter(
                self.embedding[mask, 0],
                self.embedding[mask, 1],
                c=color, s=10, alpha=0.5,
                label=f'{channel} (n={n_in_channel}, {app_rate:.1f}%)'
            )

        ax.set_xlabel('UMAP 1', fontsize=12)
        ax.set_ylabel('UMAP 2', fontsize=12)
        ax.set_title('UMAP: Channel Exposure Patterns\n(with application rates)', fontsize=14)
        ax.legend(loc='upper right', fontsize=10)

        plt.tight_layout()
        if save:
            path = self.data_path / 'umap_channel_exposure.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved to {path}")
        plt.close()

    def plot_treatment_effect(self, save: bool = True):
        """Plot UMAP highlighting text treatment effect."""
        logger.info("Plotting treatment effect visualization...")

        fig, axes = plt.subplots(1, 2, figsize=(18, 8))

        # Left: Has text vs no text
        ax1 = axes[0]
        no_text = self.df['total_text_count'] == 0
        has_text = self.df['total_text_count'] > 0

        ax1.scatter(self.embedding[no_text, 0], self.embedding[no_text, 1],
                   c='lightblue', s=8, alpha=0.4, label='No text campaigns')
        ax1.scatter(self.embedding[has_text, 0], self.embedding[has_text, 1],
                   c='darkgreen', s=8, alpha=0.4, label='Has text campaigns')

        # Highlight applicants
        app_no_text = self.df['is_applicant'] & no_text
        app_has_text = self.df['is_applicant'] & has_text

        ax1.scatter(self.embedding[app_no_text, 0], self.embedding[app_no_text, 1],
                   c='blue', s=50, alpha=0.9, marker='*', label='Applied (no text)')
        ax1.scatter(self.embedding[app_has_text, 0], self.embedding[app_has_text, 1],
                   c='red', s=50, alpha=0.9, marker='*', label='Applied (has text)')

        ax1.set_xlabel('UMAP 1', fontsize=12)
        ax1.set_ylabel('UMAP 2', fontsize=12)
        ax1.set_title('Text Campaign Exposure\n(Stars = Applicants)', fontsize=14)
        ax1.legend(loc='upper right', fontsize=9)

        # Right: Application rate by text exposure density
        ax2 = axes[1]
        text_counts = self.df['total_text_count']
        colors = ax2.scatter(
            self.embedding[:, 0], self.embedding[:, 1],
            c=text_counts, cmap='YlOrRd', s=10, alpha=0.6
        )
        plt.colorbar(colors, ax=ax2, label='Text Campaign Count')

        # Overlay applicants
        ax2.scatter(
            self.embedding[self.df['is_applicant'], 0],
            self.embedding[self.df['is_applicant'], 1],
            c='none', edgecolor='black', s=40, linewidth=1.5,
            label='Applicants'
        )

        ax2.set_xlabel('UMAP 1', fontsize=12)
        ax2.set_ylabel('UMAP 2', fontsize=12)
        ax2.set_title('Text Campaign Intensity\n(Circles = Applicants)', fontsize=14)
        ax2.legend(loc='upper right', fontsize=10)

        plt.tight_layout()
        if save:
            path = self.data_path / 'umap_treatment_effect.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved to {path}")
        plt.close()

    def plot_message_type_patterns(self, save: bool = True):
        """Plot UMAP showing message type exposure patterns and their relation to conversion."""
        logger.info("Plotting message type patterns...")

        # Get message type columns
        msg_types = ['informational', 'motivational_struggle', 'personalized_qualified',
                     'relief_reassurance', 'savings_financial', 'urgency_deadline']
        msg_cols = [f'msgtype_{mt}_count' for mt in msg_types if f'msgtype_{mt}_count' in self.df.columns]

        if len(msg_cols) < 4:
            logger.warning("Not enough message type columns for visualization")
            return

        # Create 2x3 grid for message types
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        axes = axes.flatten()

        for i, col in enumerate(msg_cols[:6]):
            ax = axes[i]
            msg_name = col.replace('msgtype_', '').replace('_count', '')

            # Plot message intensity
            scatter = ax.scatter(
                self.embedding[:, 0], self.embedding[:, 1],
                c=self.df[col], cmap='YlOrRd', s=8, alpha=0.6
            )
            plt.colorbar(scatter, ax=ax, label='Count', shrink=0.8)

            # Overlay applicants
            app_mask = self.df['is_applicant']
            ax.scatter(
                self.embedding[app_mask, 0], self.embedding[app_mask, 1],
                c='none', edgecolor='blue', s=30, linewidth=1.5
            )

            # Calculate stats
            exposed = self.df[self.df[col] > 0]
            exposed_rate = exposed['is_applicant'].mean() * 100 if len(exposed) > 0 else 0
            unexposed = self.df[self.df[col] == 0]
            unexposed_rate = unexposed['is_applicant'].mean() * 100 if len(unexposed) > 0 else 0

            ax.set_title(f'{msg_name}\nExposed: {exposed_rate:.2f}% | Unexposed: {unexposed_rate:.2f}%',
                        fontsize=11)
            ax.set_xlabel('UMAP 1')
            ax.set_ylabel('UMAP 2')

        plt.suptitle('Message Type Exposure Patterns\n(Blue circles = Applicants)', fontsize=14, y=1.02)
        plt.tight_layout()

        if save:
            path = self.data_path / 'umap_message_types.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved to {path}")
        plt.close()

    def plot_message_effectiveness_comparison(self, save: bool = True):
        """Plot side-by-side comparison of high vs low message exposure with conversion rates."""
        logger.info("Plotting message effectiveness comparison...")

        msg_types = ['informational', 'motivational_struggle', 'personalized_qualified',
                     'relief_reassurance', 'savings_financial', 'urgency_deadline']
        msg_cols = [f'msgtype_{mt}_count' for mt in msg_types if f'msgtype_{mt}_count' in self.df.columns]

        # Calculate effectiveness for each message type
        effectiveness = []
        for col in msg_cols:
            mt = col.replace('msgtype_', '').replace('_count', '')
            exposed = self.df[self.df[col] > 0]
            unexposed = self.df[self.df[col] == 0]
            exp_rate = exposed['is_applicant'].mean() * 100 if len(exposed) > 0 else 0
            unexp_rate = unexposed['is_applicant'].mean() * 100 if len(unexposed) > 0 else 0
            effectiveness.append({
                'type': mt,
                'col': col,
                'diff': exp_rate - unexp_rate,
                'exp_rate': exp_rate,
                'unexp_rate': unexp_rate
            })

        # Sort by effectiveness
        effectiveness = sorted(effectiveness, key=lambda x: x['diff'], reverse=True)

        fig, axes = plt.subplots(1, 2, figsize=(18, 8))

        # Left: Bar chart of effectiveness
        ax1 = axes[0]
        types = [e['type'] for e in effectiveness]
        diffs = [e['diff'] for e in effectiveness]
        colors = ['green' if d > 0 else 'red' for d in diffs]

        bars = ax1.barh(types, diffs, color=colors, alpha=0.7)
        ax1.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax1.set_xlabel('Conversion Rate Difference (pp)', fontsize=12)
        ax1.set_title('Message Type Effectiveness\n(Exposed - Unexposed Conversion Rate)', fontsize=14)

        # Add value labels
        for bar, diff in zip(bars, diffs):
            width = bar.get_width()
            ax1.annotate(f'{diff:+.2f}pp',
                        xy=(width, bar.get_y() + bar.get_height()/2),
                        xytext=(5 if width >= 0 else -5, 0),
                        textcoords='offset points',
                        ha='left' if width >= 0 else 'right',
                        va='center', fontsize=10)

        # Right: UMAP with most effective message type highlighted
        ax2 = axes[1]
        best_msg = effectiveness[0]
        col = best_msg['col']

        # Background: all points by exposure
        exposed_mask = self.df[col] > 0
        ax2.scatter(self.embedding[~exposed_mask, 0], self.embedding[~exposed_mask, 1],
                   c='lightgray', s=5, alpha=0.3, label='Not exposed')
        ax2.scatter(self.embedding[exposed_mask, 0], self.embedding[exposed_mask, 1],
                   c='lightgreen', s=5, alpha=0.5, label='Exposed')

        # Highlight applicants
        app_exposed = self.df['is_applicant'] & exposed_mask
        app_unexposed = self.df['is_applicant'] & ~exposed_mask
        ax2.scatter(self.embedding[app_unexposed, 0], self.embedding[app_unexposed, 1],
                   c='blue', s=40, alpha=0.8, marker='o', label='Applied (unexposed)')
        ax2.scatter(self.embedding[app_exposed, 0], self.embedding[app_exposed, 1],
                   c='red', s=40, alpha=0.8, marker='*', label='Applied (exposed)')

        ax2.set_xlabel('UMAP 1', fontsize=12)
        ax2.set_ylabel('UMAP 2', fontsize=12)
        ax2.set_title(f'Best Message Type: {best_msg["type"]}\n'
                     f'({best_msg["exp_rate"]:.2f}% vs {best_msg["unexp_rate"]:.2f}%)', fontsize=14)
        ax2.legend(loc='upper right', fontsize=9)

        plt.tight_layout()
        if save:
            path = self.data_path / 'umap_message_effectiveness.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved to {path}")
        plt.close()

    def plot_summary_dashboard(self, save: bool = True):
        """Create a 2x2 summary dashboard."""
        logger.info("Creating summary dashboard...")

        fig, axes = plt.subplots(2, 2, figsize=(16, 14))

        # Top-left: Applicants
        ax = axes[0, 0]
        non_app_mask = ~self.df['is_applicant']
        ax.scatter(self.embedding[non_app_mask, 0], self.embedding[non_app_mask, 1],
                  c='lightgray', s=3, alpha=0.3)
        app_mask = self.df['is_applicant']
        ax.scatter(self.embedding[app_mask, 0], self.embedding[app_mask, 1],
                  c='red', s=20, alpha=0.8)
        ax.set_title(f'Applicants (n={app_mask.sum()}, {app_mask.mean()*100:.1f}%)', fontsize=12)
        ax.set_xlabel('UMAP 1')
        ax.set_ylabel('UMAP 2')

        # Top-right: Phase 3 clusters
        ax = axes[0, 1]
        clusters = sorted(self.df['phase3_cluster'].unique())
        cmap = plt.cm.get_cmap('tab10', len(clusters))
        for i, c in enumerate(clusters):
            mask = self.df['phase3_cluster'] == c
            ax.scatter(self.embedding[mask, 0], self.embedding[mask, 1],
                      c=[cmap(i)], s=5, alpha=0.5, label=f'{c}')
        ax.set_title('Phase 3 Clusters', fontsize=12)
        ax.set_xlabel('UMAP 1')
        ax.set_ylabel('UMAP 2')
        ax.legend(loc='upper right', fontsize=7, ncol=2, title='Cluster')

        # Bottom-left: Channel combo
        ax = axes[1, 0]
        channel_colors = {
            'letter_only': 'purple', 'letter+email': 'blue',
            'letter+text': 'green', 'letter+email+text': 'orange'
        }
        for ch, color in channel_colors.items():
            mask = self.df['channel_combo'] == ch
            if mask.any():
                ax.scatter(self.embedding[mask, 0], self.embedding[mask, 1],
                          c=color, s=5, alpha=0.5, label=ch)
        ax.set_title('Channel Exposure', fontsize=12)
        ax.set_xlabel('UMAP 1')
        ax.set_ylabel('UMAP 2')
        ax.legend(loc='upper right', fontsize=9)

        # Bottom-right: Text campaign intensity
        ax = axes[1, 1]
        scatter = ax.scatter(
            self.embedding[:, 0], self.embedding[:, 1],
            c=self.df['total_text_count'], cmap='YlOrRd', s=5, alpha=0.6
        )
        plt.colorbar(scatter, ax=ax, label='Text Campaigns')
        ax.scatter(
            self.embedding[self.df['is_applicant'], 0],
            self.embedding[self.df['is_applicant'], 1],
            c='none', edgecolor='black', s=30, linewidth=1
        )
        ax.set_title('Text Intensity (circles=applicants)', fontsize=12)
        ax.set_xlabel('UMAP 1')
        ax.set_ylabel('UMAP 2')

        plt.suptitle('Analysis-05: Applicant Clustering Summary', fontsize=16, y=1.02)
        plt.tight_layout()

        if save:
            path = self.data_path / 'umap_summary_dashboard.png'
            plt.savefig(path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved dashboard to {path}")
        plt.close()

    def run_all_visualizations(self):
        """Generate all UMAP visualizations."""
        if self.df is None:
            self.load_data()
        if self.embedding is None:
            self.compute_umap()

        self.plot_applicant_distribution()
        self.plot_phase3_clusters()
        self.plot_channel_exposure()
        self.plot_treatment_effect()
        self.plot_message_type_patterns()  # NEW: Message type exposure patterns
        self.plot_message_effectiveness_comparison()  # NEW: Message effectiveness comparison
        self.plot_summary_dashboard()

        logger.info("\nAll visualizations complete!")
        logger.info(f"Output directory: {self.data_path}")


def main():
    """Generate UMAP visualizations."""
    visualizer = UMAPVisualizer()
    visualizer.run_all_visualizations()


if __name__ == '__main__':
    main()
