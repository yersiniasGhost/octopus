"""
Phase 1: Demographics-Only Clustering for Applicant Analysis
ANALYSIS-04: Applicant-Centric Clustering

This phase clusters participants using ONLY demographic features to establish
a baseline understanding of how demographics relate to application rates.

Methodology:
1. Use FAMD (Factor Analysis of Mixed Data) for dimensionality reduction
2. Apply K-Means clustering on FAMD components
3. Evaluate clusters by application rate (is_applicant outcome)
4. Compare to baseline application rate of ~3.2%

Features used:
- Continuous: household_income, household_size, house_age, total_energy_burden,
              living_area_sqft, bedrooms, bathrooms
- Categorical: dwelling_type, presence_of_children

Output: Cluster assignments with application rate analysis per cluster.
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
import prince  # For FAMD

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Phase1DemographicsClustering:
    """Demographics-only clustering with applicant outcome analysis."""

    def __init__(self, data_path: str = '/home/yersinia/devel/octopus/data/clustering_results-04'):
        self.data_path = Path(data_path)
        self.df: Optional[pd.DataFrame] = None
        self.feature_sets: Optional[Dict] = None

        # Feature definitions (excluding low-coverage features like bedrooms, bathrooms)
        self.continuous_features = [
            'household_income', 'household_size', 'house_age',
            'total_energy_burden', 'living_area_sqft'
        ]
        self.categorical_features = ['dwelling_type', 'presence_of_children']
        self.outcome_var = 'is_applicant'

    def load_data(self) -> pd.DataFrame:
        """Load the participant-applicant feature dataset."""
        logger.info("Loading data...")
        parquet_path = self.data_path / 'participant_applicant_features.parquet'
        self.df = pd.read_parquet(parquet_path)

        # Load feature set definitions
        with open(self.data_path / 'feature_sets.json', 'r') as f:
            self.feature_sets = json.load(f)

        logger.info(f"Loaded {len(self.df)} participants, {self.df['is_applicant'].sum()} applicants")
        return self.df

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """
        Prepare features for clustering.

        Returns:
            Tuple of (continuous_df, categorical_df, outcome_series)
        """
        logger.info("Preparing features...")

        # Filter to available features
        available_cont = [f for f in self.continuous_features if f in df.columns]
        available_cat = [f for f in self.categorical_features if f in df.columns]

        logger.info(f"Continuous features: {available_cont}")
        logger.info(f"Categorical features: {available_cat}")

        # Extract feature matrices
        cont_df = df[available_cont].copy()
        cat_df = df[available_cat].copy()
        outcome = df[self.outcome_var].copy()

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
            # Convert to string for FAMD
            cat_df[col] = cat_df[col].astype(str)

        # Log feature coverage
        for col in available_cont:
            coverage = df[col].notna().mean() * 100
            logger.info(f"  {col}: {coverage:.1f}% coverage")

        return cont_imputed, cat_df, outcome

    def run_famd(self, cont_df: pd.DataFrame, cat_df: pd.DataFrame,
                 n_components: int = 5) -> np.ndarray:
        """
        Run Factor Analysis of Mixed Data (FAMD) for dimensionality reduction.

        Args:
            cont_df: Continuous features DataFrame
            cat_df: Categorical features DataFrame
            n_components: Number of FAMD components to keep

        Returns:
            FAMD-transformed feature matrix
        """
        logger.info(f"Running FAMD with {n_components} components...")

        # Combine features for FAMD
        combined_df = pd.concat([cont_df, cat_df], axis=1)

        # Initialize and fit FAMD
        famd = prince.FAMD(
            n_components=n_components,
            n_iter=5,
            random_state=42
        )
        famd.fit(combined_df)

        # Get transformed coordinates
        coords = famd.row_coordinates(combined_df)

        # Log explained variance (handle different prince versions)
        try:
            explained_var = famd.explained_inertia_
        except AttributeError:
            try:
                explained_var = famd.percentage_of_variance_
            except AttributeError:
                explained_var = None

        if explained_var is not None:
            logger.info(f"FAMD explained variance: {explained_var}")
            logger.info(f"Total explained: {sum(explained_var):.1%}")
        else:
            logger.info("FAMD completed (variance info not available in this prince version)")

        return coords.values

    def find_optimal_k(self, X: np.ndarray, k_range: range = range(2, 11)) -> Tuple[int, pd.DataFrame]:
        """
        Find optimal number of clusters using silhouette score and elbow method.

        Returns:
            Tuple of (optimal_k, evaluation_dataframe)
        """
        logger.info("Finding optimal k...")

        results = []
        for k in k_range:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X)

            silhouette = silhouette_score(X, labels)
            inertia = kmeans.inertia_

            results.append({
                'k': k,
                'silhouette': silhouette,
                'inertia': inertia
            })
            logger.info(f"  k={k}: silhouette={silhouette:.3f}, inertia={inertia:.0f}")

        results_df = pd.DataFrame(results)

        # Find optimal k (highest silhouette)
        optimal_k = results_df.loc[results_df['silhouette'].idxmax(), 'k']
        logger.info(f"Optimal k by silhouette: {optimal_k}")

        return int(optimal_k), results_df

    def cluster_and_analyze(self, X: np.ndarray, df: pd.DataFrame, k: int) -> pd.DataFrame:
        """
        Perform clustering and analyze application rates per cluster.

        Returns:
            DataFrame with cluster assignments and analysis
        """
        logger.info(f"Clustering with k={k}...")

        # Fit K-Means
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        # Add cluster labels to dataframe
        result_df = df.copy()
        result_df['phase1_cluster'] = labels

        # Analyze each cluster
        baseline_rate = df['is_applicant'].mean()
        logger.info(f"\nBaseline application rate: {baseline_rate:.2%}")
        logger.info("\nCluster Analysis:")

        cluster_stats = []
        for cluster_id in range(k):
            cluster_mask = result_df['phase1_cluster'] == cluster_id
            cluster_df = result_df[cluster_mask]

            n_participants = len(cluster_df)
            n_applicants = cluster_df['is_applicant'].sum()
            app_rate = cluster_df['is_applicant'].mean()
            lift = app_rate / baseline_rate if baseline_rate > 0 else 0

            # Demographic profile
            profile = {}
            for col in self.continuous_features:
                if col in cluster_df.columns:
                    profile[f'{col}_mean'] = cluster_df[col].mean()
                    profile[f'{col}_median'] = cluster_df[col].median()

            cluster_stats.append({
                'cluster': cluster_id,
                'n_participants': n_participants,
                'n_applicants': n_applicants,
                'pct_of_total': n_participants / len(df) * 100,
                'application_rate': app_rate * 100,
                'lift_vs_baseline': lift,
                **profile
            })

            logger.info(f"  Cluster {cluster_id}: {n_participants:,} participants, "
                       f"{n_applicants} applicants ({app_rate:.2%}), lift={lift:.2f}x")

        cluster_stats_df = pd.DataFrame(cluster_stats)

        # Statistical significance test
        self._test_cluster_significance(result_df, k)

        return result_df, cluster_stats_df

    def _test_cluster_significance(self, df: pd.DataFrame, k: int):
        """Test if cluster differences in application rate are statistically significant."""
        # Chi-square test for independence
        contingency = pd.crosstab(df['phase1_cluster'], df['is_applicant'])
        chi2, p_value, dof, expected = stats.chi2_contingency(contingency)

        logger.info(f"\nChi-square test for cluster independence:")
        logger.info(f"  Chi2 = {chi2:.2f}, p-value = {p_value:.4e}, dof = {dof}")

        if p_value < 0.05:
            logger.info("  ✓ Clusters show SIGNIFICANT differences in application rates (p < 0.05)")
        else:
            logger.info("  ✗ No significant difference between clusters (p >= 0.05)")

    def run_phase1(self, n_components: int = 5, k: Optional[int] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Run complete Phase 1 clustering pipeline.

        Args:
            n_components: Number of FAMD components
            k: Number of clusters (if None, will find optimal)

        Returns:
            Tuple of (clustered_df, cluster_stats_df)
        """
        # Load data
        if self.df is None:
            self.load_data()

        # Prepare features
        cont_df, cat_df, outcome = self.prepare_features(self.df)

        # Run FAMD
        X_famd = self.run_famd(cont_df, cat_df, n_components=n_components)

        # Find optimal k or use provided
        if k is None:
            k, k_selection_df = self.find_optimal_k(X_famd)
            # Save k selection results
            k_selection_df.to_csv(self.data_path / 'phase1_k_selection.csv', index=False)
        else:
            logger.info(f"Using provided k={k}")

        # Cluster and analyze
        result_df, cluster_stats_df = self.cluster_and_analyze(X_famd, self.df, k)

        # Save results
        self._save_results(result_df, cluster_stats_df, X_famd)

        return result_df, cluster_stats_df

    def _save_results(self, result_df: pd.DataFrame, cluster_stats_df: pd.DataFrame,
                      X_famd: np.ndarray):
        """Save clustering results."""
        # Save clustered data
        result_df.to_parquet(self.data_path / 'phase1_clustered.parquet', index=False)
        logger.info(f"Saved clustered data to {self.data_path / 'phase1_clustered.parquet'}")

        # Save cluster stats
        cluster_stats_df.to_csv(self.data_path / 'phase1_cluster_stats.csv', index=False)
        logger.info(f"Saved cluster stats to {self.data_path / 'phase1_cluster_stats.csv'}")

        # Save FAMD coordinates for visualization
        np.save(self.data_path / 'phase1_famd_coords.npy', X_famd)
        logger.info(f"Saved FAMD coordinates")

    def print_summary(self, cluster_stats_df: pd.DataFrame):
        """Print formatted summary of clustering results."""
        print("\n" + "=" * 70)
        print("PHASE 1: DEMOGRAPHICS-ONLY CLUSTERING SUMMARY")
        print("=" * 70)

        print(f"\nNumber of clusters: {len(cluster_stats_df)}")

        # Sort by application rate
        sorted_stats = cluster_stats_df.sort_values('application_rate', ascending=False)

        print("\nCluster Performance (sorted by application rate):")
        print("-" * 70)
        print(f"{'Cluster':<10} {'Size':<12} {'% Total':<10} {'App Rate':<12} {'Lift':<8}")
        print("-" * 70)

        for _, row in sorted_stats.iterrows():
            print(f"{int(row['cluster']):<10} {int(row['n_participants']):,<12} "
                  f"{row['pct_of_total']:.1f}%{'':<5} "
                  f"{row['application_rate']:.2f}%{'':<6} "
                  f"{row['lift_vs_baseline']:.2f}x")

        print("-" * 70)

        # Top cluster profile
        top_cluster = sorted_stats.iloc[0]
        print(f"\nTop Performing Cluster ({int(top_cluster['cluster'])}) Profile:")
        for col in self.continuous_features:
            mean_col = f'{col}_mean'
            if mean_col in top_cluster:
                print(f"  {col}: {top_cluster[mean_col]:.1f}")

        print("=" * 70)


def main():
    """Run Phase 1 demographics clustering."""
    clusterer = Phase1DemographicsClustering()
    result_df, cluster_stats_df = clusterer.run_phase1(n_components=5, k=None)
    clusterer.print_summary(cluster_stats_df)
    return result_df, cluster_stats_df


if __name__ == '__main__':
    main()
