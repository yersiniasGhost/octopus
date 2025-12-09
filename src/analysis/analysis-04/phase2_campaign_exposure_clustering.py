"""
Phase 2: Demographics + Campaign Exposure Clustering for Applicant Analysis
ANALYSIS-04: Applicant-Centric Clustering

This phase adds campaign exposure features to the demographic baseline to test
whether channel exposure and message types improve our ability to identify
high-applicant-rate segments.

Added Features:
- Channel exposure: email_count, total_text_count, channel_diversity, channel_combo
- Message type exposure: 6 message type counts
- Exposure intensity: campaign_count, exposure_days

Key Question: Does campaign exposure help predict who applies, beyond demographics?

Output: Cluster assignments with application rate analysis comparing Phase 1 vs Phase 2.
"""
import logging
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import prince

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Phase2CampaignExposureClustering:
    """Demographics + Campaign exposure clustering with applicant outcome analysis."""

    def __init__(self, data_path: str = '/home/yersinia/devel/octopus/data/clustering_results-04'):
        self.data_path = Path(data_path)
        self.df: Optional[pd.DataFrame] = None

        # Demographics features (same as Phase 1)
        self.demo_continuous = [
            'household_income', 'household_size', 'house_age',
            'total_energy_burden', 'living_area_sqft'
        ]
        self.demo_categorical = ['dwelling_type', 'presence_of_children']

        # Campaign exposure features
        self.exposure_continuous = [
            'campaign_count', 'email_count', 'total_text_count',
            'channel_diversity', 'exposure_days'
        ]

        # Message type features (will be populated from data)
        self.message_type_features: List[str] = []

        # Channel combo is categorical
        self.exposure_categorical = ['channel_combo']

        self.outcome_var = 'is_applicant'

    def load_data(self) -> pd.DataFrame:
        """Load the participant-applicant feature dataset."""
        logger.info("Loading data...")

        # Load Phase 1 clustered data to compare
        phase1_path = self.data_path / 'phase1_clustered.parquet'
        self.df = pd.read_parquet(phase1_path)

        # Get message type columns
        self.message_type_features = [c for c in self.df.columns
                                       if c.startswith('msgtype_') and c.endswith('_count')]
        logger.info(f"Found {len(self.message_type_features)} message type features")

        logger.info(f"Loaded {len(self.df)} participants, {self.df['is_applicant'].sum()} applicants")
        return self.df

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """
        Prepare combined demographics + exposure features for clustering.

        Returns:
            Tuple of (continuous_df, categorical_df, outcome_series)
        """
        logger.info("Preparing features (demographics + campaign exposure)...")

        # Combine continuous features
        all_continuous = (self.demo_continuous + self.exposure_continuous +
                          self.message_type_features)
        available_cont = [f for f in all_continuous if f in df.columns]

        # Combine categorical features
        all_categorical = self.demo_categorical + self.exposure_categorical
        available_cat = [f for f in all_categorical if f in df.columns]

        logger.info(f"Continuous features ({len(available_cont)}): {available_cont}")
        logger.info(f"Categorical features ({len(available_cat)}): {available_cat}")

        # Extract feature matrices
        cont_df = df[available_cont].copy()
        cat_df = df[available_cat].copy()
        outcome = df[self.outcome_var].copy()

        # Cap extreme values in household_income to avoid outlier influence
        income_cap = cont_df['household_income'].quantile(0.99)
        cont_df['household_income'] = cont_df['household_income'].clip(upper=income_cap)

        # Handle missing values in continuous features
        imputer = SimpleImputer(strategy='median')
        cont_imputed = pd.DataFrame(
            imputer.fit_transform(cont_df),
            columns=available_cont,
            index=df.index
        )

        # Handle missing values in categorical features
        for col in available_cat:
            if cat_df[col].isna().any():
                mode_val = cat_df[col].mode().iloc[0] if len(cat_df[col].mode()) > 0 else 'Unknown'
                cat_df[col] = cat_df[col].fillna(mode_val)
            cat_df[col] = cat_df[col].astype(str)

        # Log feature coverage
        logger.info("\nFeature coverage:")
        for col in available_cont[:10]:  # Log first 10
            coverage = df[col].notna().mean() * 100
            logger.info(f"  {col}: {coverage:.1f}%")

        return cont_imputed, cat_df, outcome

    def run_famd(self, cont_df: pd.DataFrame, cat_df: pd.DataFrame,
                 n_components: int = 8) -> np.ndarray:
        """Run FAMD for dimensionality reduction."""
        logger.info(f"Running FAMD with {n_components} components...")

        combined_df = pd.concat([cont_df, cat_df], axis=1)

        famd = prince.FAMD(n_components=n_components, n_iter=5, random_state=42)
        famd.fit(combined_df)
        coords = famd.row_coordinates(combined_df)

        try:
            explained_var = famd.explained_inertia_
            logger.info(f"FAMD explained variance: {explained_var[:5]}...")
        except AttributeError:
            logger.info("FAMD completed")

        return coords.values

    def find_optimal_k(self, X: np.ndarray, k_range: range = range(2, 11)) -> Tuple[int, pd.DataFrame]:
        """Find optimal number of clusters using silhouette score."""
        logger.info("Finding optimal k...")

        results = []
        for k in k_range:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X)
            silhouette = silhouette_score(X, labels)
            inertia = kmeans.inertia_

            results.append({'k': k, 'silhouette': silhouette, 'inertia': inertia})
            logger.info(f"  k={k}: silhouette={silhouette:.3f}")

        results_df = pd.DataFrame(results)
        optimal_k = results_df.loc[results_df['silhouette'].idxmax(), 'k']
        logger.info(f"Optimal k by silhouette: {optimal_k}")

        return int(optimal_k), results_df

    def cluster_and_analyze(self, X: np.ndarray, df: pd.DataFrame, k: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Perform clustering and analyze application rates."""
        logger.info(f"Clustering with k={k}...")

        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        result_df = df.copy()
        result_df['phase2_cluster'] = labels

        baseline_rate = df['is_applicant'].mean()
        logger.info(f"\nBaseline application rate: {baseline_rate:.2%}")

        cluster_stats = []
        for cluster_id in range(k):
            cluster_mask = result_df['phase2_cluster'] == cluster_id
            cluster_df = result_df[cluster_mask]

            n_participants = len(cluster_df)
            n_applicants = cluster_df['is_applicant'].sum()
            app_rate = cluster_df['is_applicant'].mean()
            lift = app_rate / baseline_rate if baseline_rate > 0 else 0

            # Channel profile
            channel_profile = cluster_df['channel_combo'].value_counts(normalize=True).to_dict()

            # Message type profile
            msg_profile = {}
            for col in self.message_type_features:
                msg_profile[col.replace('msgtype_', '').replace('_count', '')] = cluster_df[col].mean()

            cluster_stats.append({
                'cluster': cluster_id,
                'n_participants': n_participants,
                'n_applicants': n_applicants,
                'pct_of_total': n_participants / len(df) * 100,
                'application_rate': app_rate * 100,
                'lift_vs_baseline': lift,
                'avg_campaign_count': cluster_df['campaign_count'].mean(),
                'avg_email_count': cluster_df['email_count'].mean(),
                'avg_text_count': cluster_df['total_text_count'].mean(),
                'pct_letter_only': channel_profile.get('letter_only', 0) * 100,
                'pct_letter_email': channel_profile.get('letter+email', 0) * 100,
                'pct_letter_text': channel_profile.get('letter+text', 0) * 100,
                'pct_letter_email_text': channel_profile.get('letter+email+text', 0) * 100,
                **{f'avg_msg_{k}': v for k, v in msg_profile.items()}
            })

            logger.info(f"  Cluster {cluster_id}: {n_participants:,} participants, "
                       f"{n_applicants} applicants ({app_rate:.2%}), lift={lift:.2f}x")

        cluster_stats_df = pd.DataFrame(cluster_stats)
        self._test_cluster_significance(result_df, k)
        self._compare_to_phase1(result_df)

        return result_df, cluster_stats_df

    def _test_cluster_significance(self, df: pd.DataFrame, k: int):
        """Test statistical significance of cluster differences."""
        contingency = pd.crosstab(df['phase2_cluster'], df['is_applicant'])
        chi2, p_value, dof, _ = stats.chi2_contingency(contingency)

        logger.info(f"\nPhase 2 Chi-square test:")
        logger.info(f"  Chi2 = {chi2:.2f}, p-value = {p_value:.4e}")
        if p_value < 0.05:
            logger.info("  ✓ Clusters show SIGNIFICANT differences in application rates")
        else:
            logger.info("  ✗ No significant difference between clusters")

    def _compare_to_phase1(self, df: pd.DataFrame):
        """Compare Phase 2 clustering to Phase 1."""
        logger.info("\n--- Comparison: Phase 1 vs Phase 2 ---")

        # Calculate spread of application rates
        phase1_rates = df.groupby('phase1_cluster')['is_applicant'].mean()
        phase2_rates = df.groupby('phase2_cluster')['is_applicant'].mean()

        # Filter out tiny clusters (< 10 participants)
        phase1_sizes = df.groupby('phase1_cluster').size()
        phase2_sizes = df.groupby('phase2_cluster').size()

        phase1_rates_filtered = phase1_rates[phase1_sizes >= 10]
        phase2_rates_filtered = phase2_rates[phase2_sizes >= 10]

        p1_spread = phase1_rates_filtered.max() - phase1_rates_filtered.min()
        p2_spread = phase2_rates_filtered.max() - phase2_rates_filtered.min()

        logger.info(f"Phase 1 application rate spread: {p1_spread:.2%}")
        logger.info(f"Phase 2 application rate spread: {p2_spread:.2%}")

        if p2_spread > p1_spread:
            improvement = (p2_spread - p1_spread) / p1_spread * 100
            logger.info(f"✓ Phase 2 improves cluster separation by {improvement:.1f}%")
        else:
            logger.info("✗ Phase 2 does not improve cluster separation")

        # Cross-tabulate Phase 1 vs Phase 2 clusters
        crosstab = pd.crosstab(df['phase1_cluster'], df['phase2_cluster'], normalize='index')
        logger.info("\nPhase 1 → Phase 2 cluster transition (top transitions):")
        for p1_cluster in crosstab.index[:3]:  # Show top 3 Phase 1 clusters
            top_p2 = crosstab.loc[p1_cluster].idxmax()
            pct = crosstab.loc[p1_cluster, top_p2] * 100
            logger.info(f"  Phase1-{p1_cluster} → Phase2-{top_p2}: {pct:.1f}%")

    def run_phase2(self, n_components: int = 8, k: Optional[int] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Run complete Phase 2 clustering pipeline."""
        if self.df is None:
            self.load_data()

        cont_df, cat_df, outcome = self.prepare_features(self.df)
        X_famd = self.run_famd(cont_df, cat_df, n_components=n_components)

        if k is None:
            k, k_selection_df = self.find_optimal_k(X_famd)
            k_selection_df.to_csv(self.data_path / 'phase2_k_selection.csv', index=False)

        result_df, cluster_stats_df = self.cluster_and_analyze(X_famd, self.df, k)
        self._save_results(result_df, cluster_stats_df, X_famd)

        return result_df, cluster_stats_df

    def _save_results(self, result_df: pd.DataFrame, cluster_stats_df: pd.DataFrame,
                      X_famd: np.ndarray):
        """Save clustering results."""
        result_df.to_parquet(self.data_path / 'phase2_clustered.parquet', index=False)
        cluster_stats_df.to_csv(self.data_path / 'phase2_cluster_stats.csv', index=False)
        np.save(self.data_path / 'phase2_famd_coords.npy', X_famd)
        logger.info(f"Saved Phase 2 results to {self.data_path}")

    def print_summary(self, cluster_stats_df: pd.DataFrame):
        """Print formatted summary."""
        print("\n" + "=" * 80)
        print("PHASE 2: DEMOGRAPHICS + CAMPAIGN EXPOSURE CLUSTERING SUMMARY")
        print("=" * 80)

        print(f"\nNumber of clusters: {len(cluster_stats_df)}")

        # Sort by application rate
        sorted_stats = cluster_stats_df.sort_values('application_rate', ascending=False)

        print("\nCluster Performance (sorted by application rate):")
        print("-" * 80)
        print(f"{'Cluster':<8} {'Size':<10} {'App Rate':<10} {'Lift':<8} "
              f"{'Campaigns':<10} {'Emails':<8} {'Texts':<8}")
        print("-" * 80)

        for _, row in sorted_stats.iterrows():
            print(f"{int(row['cluster']):<8} {int(row['n_participants']):,<10} "
                  f"{row['application_rate']:.2f}%{'':<4} "
                  f"{row['lift_vs_baseline']:.2f}x{'':<3} "
                  f"{row['avg_campaign_count']:.1f}{'':<6} "
                  f"{row['avg_email_count']:.1f}{'':<5} "
                  f"{row['avg_text_count']:.1f}")

        print("-" * 80)

        # Channel analysis
        print("\nChannel Mix by Cluster:")
        print("-" * 80)
        for _, row in sorted_stats.iterrows():
            print(f"Cluster {int(row['cluster'])}: "
                  f"L+E: {row['pct_letter_email']:.0f}%, "
                  f"L+T: {row['pct_letter_text']:.0f}%, "
                  f"L+E+T: {row['pct_letter_email_text']:.0f}%, "
                  f"L only: {row['pct_letter_only']:.0f}%")

        print("=" * 80)


def main():
    """Run Phase 2 campaign exposure clustering."""
    clusterer = Phase2CampaignExposureClustering()
    result_df, cluster_stats_df = clusterer.run_phase2(n_components=8, k=None)
    clusterer.print_summary(cluster_stats_df)
    return result_df, cluster_stats_df


if __name__ == '__main__':
    main()
