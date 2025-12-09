"""
Phase 3: Probabilistic Clustering for Bayesian Causal Modeling
ANALYSIS-04: Applicant-Centric Clustering

This phase uses Bayesian Gaussian Mixture (Dirichlet process prior) to generate
soft cluster assignments that preserve uncertainty for downstream causal modeling.

Key differences from hard clustering:
1. Soft assignments: Each participant has probability of belonging to each cluster
2. Uncertainty preserved: Allows propagation of clustering uncertainty into PyMC models
3. Auto-selection of effective clusters: Dirichlet process prior prunes unused components

Output for Bayesian modeling:
- K-1 cluster probability columns (for identifiability in PyMC)
- Cluster confidence scores
- Ready for use as covariates or group indices in hierarchical models

Causal modeling use case:
"Given cluster membership probability, what's the causal effect of adding text campaigns?"
"""
import logging
import json
from pathlib import Path
from typing import Dict, Tuple, Optional

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.mixture import BayesianGaussianMixture
from sklearn.metrics import silhouette_score
import prince

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Phase3ProbabilisticClustering:
    """Probabilistic clustering with soft assignments for Bayesian causal modeling."""

    def __init__(self, data_path: str = '/home/yersinia/devel/octopus/data/clustering_results-04'):
        self.data_path = Path(data_path)
        self.df: Optional[pd.DataFrame] = None

        # Use same features as Phase 2
        self.continuous_features = [
            'household_income', 'household_size', 'house_age',
            'total_energy_burden', 'living_area_sqft',
            'campaign_count', 'email_count', 'total_text_count',
            'channel_diversity', 'exposure_days'
        ]
        self.categorical_features = ['dwelling_type', 'presence_of_children', 'channel_combo']
        self.message_type_features: list = []
        self.outcome_var = 'is_applicant'

    def load_data(self) -> pd.DataFrame:
        """Load Phase 2 clustered data."""
        logger.info("Loading data...")
        phase2_path = self.data_path / 'phase2_clustered.parquet'
        self.df = pd.read_parquet(phase2_path)

        self.message_type_features = [c for c in self.df.columns
                                       if c.startswith('msgtype_') and c.endswith('_count')]
        logger.info(f"Loaded {len(self.df)} participants")
        return self.df

    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, pd.DataFrame]:
        """Prepare features and return scaled continuous + encoded categorical."""
        logger.info("Preparing features for probabilistic clustering...")

        all_continuous = self.continuous_features + self.message_type_features
        available_cont = [f for f in all_continuous if f in df.columns]

        cont_df = df[available_cont].copy()

        # Cap extreme values
        for col in available_cont:
            cap = cont_df[col].quantile(0.99)
            cont_df[col] = cont_df[col].clip(upper=cap)

        # Impute and scale
        imputer = SimpleImputer(strategy='median')
        cont_imputed = imputer.fit_transform(cont_df)

        scaler = StandardScaler()
        cont_scaled = scaler.fit_transform(cont_imputed)

        # For BGM, we use only continuous features (scaled)
        # Categorical features are harder to incorporate directly
        logger.info(f"Prepared {cont_scaled.shape[1]} continuous features")

        return cont_scaled, df

    def fit_bayesian_gmm(self, X: np.ndarray, max_components: int = 10,
                          weight_concentration_prior: float = 0.1) -> BayesianGaussianMixture:
        """
        Fit Bayesian Gaussian Mixture with Dirichlet process prior.

        Args:
            X: Scaled feature matrix
            max_components: Maximum number of mixture components
            weight_concentration_prior: Lower = sparser (fewer effective clusters)

        Returns:
            Fitted BayesianGaussianMixture model
        """
        logger.info(f"Fitting Bayesian GMM with max {max_components} components...")

        bgm = BayesianGaussianMixture(
            n_components=max_components,
            covariance_type='full',
            weight_concentration_prior_type='dirichlet_process',
            weight_concentration_prior=weight_concentration_prior,
            max_iter=500,
            n_init=5,
            random_state=42,
            verbose=0
        )
        bgm.fit(X)

        # Analyze effective clusters
        weights = bgm.weights_
        effective_clusters = np.sum(weights > 0.01)  # Clusters with >1% weight
        logger.info(f"Converged: {bgm.converged_}")
        logger.info(f"Component weights: {weights.round(3)}")
        logger.info(f"Effective clusters (weight > 1%): {effective_clusters}")

        return bgm

    def extract_soft_assignments(self, bgm: BayesianGaussianMixture, X: np.ndarray,
                                  df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract soft cluster assignments (posterior probabilities).

        Returns DataFrame with:
        - phase3_cluster: Hard assignment (MAP estimate)
        - cluster_prob_0, cluster_prob_1, ...: Soft probabilities (K-1 for identifiability)
        - cluster_confidence: Max probability (uncertainty measure)
        """
        logger.info("Extracting soft cluster assignments...")

        # Get posterior probabilities
        probs = bgm.predict_proba(X)
        labels = bgm.predict(X)

        result_df = df.copy()
        result_df['phase3_cluster'] = labels

        # Add probability columns (K-1 for identifiability in Bayesian models)
        n_components = probs.shape[1]
        for k in range(n_components - 1):  # K-1 columns
            result_df[f'cluster_prob_{k}'] = probs[:, k]

        # Cluster confidence (max probability)
        result_df['cluster_confidence'] = probs.max(axis=1)

        # Store full probability matrix separately for detailed analysis
        self.cluster_probs = probs

        # Summary stats
        mean_confidence = result_df['cluster_confidence'].mean()
        low_confidence = (result_df['cluster_confidence'] < 0.5).sum()
        logger.info(f"Mean cluster confidence: {mean_confidence:.2%}")
        logger.info(f"Low confidence assignments (<50%): {low_confidence} ({low_confidence/len(df):.1%})")

        return result_df

    def analyze_clusters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Analyze application rates by probabilistic cluster."""
        logger.info("\nPhase 3 Cluster Analysis:")

        baseline_rate = df['is_applicant'].mean()
        logger.info(f"Baseline application rate: {baseline_rate:.2%}")

        cluster_stats = []
        for cluster_id in sorted(df['phase3_cluster'].unique()):
            cluster_mask = df['phase3_cluster'] == cluster_id
            cluster_df = df[cluster_mask]

            n_participants = len(cluster_df)
            if n_participants < 5:
                continue  # Skip tiny clusters

            n_applicants = cluster_df['is_applicant'].sum()
            app_rate = cluster_df['is_applicant'].mean()
            lift = app_rate / baseline_rate if baseline_rate > 0 else 0
            avg_confidence = cluster_df['cluster_confidence'].mean()

            cluster_stats.append({
                'cluster': cluster_id,
                'n_participants': n_participants,
                'n_applicants': n_applicants,
                'pct_of_total': n_participants / len(df) * 100,
                'application_rate': app_rate * 100,
                'lift_vs_baseline': lift,
                'avg_confidence': avg_confidence * 100,
                'avg_campaign_count': cluster_df['campaign_count'].mean(),
                'avg_email_count': cluster_df['email_count'].mean(),
                'avg_text_count': cluster_df['total_text_count'].mean()
            })

            logger.info(f"  Cluster {cluster_id}: {n_participants:,} ({app_rate:.2%} app rate, "
                       f"{avg_confidence:.1%} confidence)")

        cluster_stats_df = pd.DataFrame(cluster_stats)

        # Statistical significance
        contingency = pd.crosstab(df['phase3_cluster'], df['is_applicant'])
        chi2, p_value, _, _ = stats.chi2_contingency(contingency)
        logger.info(f"\nChi-square test: Chi2={chi2:.2f}, p={p_value:.4e}")

        return cluster_stats_df

    def prepare_for_pymc(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare data specifically for PyMC Bayesian modeling.

        Creates:
        - Cluster indices for hierarchical models
        - Soft assignment columns for mixture models
        - Treatment indicators for causal inference
        """
        logger.info("\nPreparing data for PyMC integration...")

        pymc_df = df.copy()

        # Treatment indicators
        pymc_df['has_text_treatment'] = (df['total_text_count'] > 0).astype(int)
        pymc_df['has_email_treatment'] = (df['email_count'] > 0).astype(int)
        pymc_df['has_both_treatment'] = ((df['email_count'] > 0) &
                                          (df['total_text_count'] > 0)).astype(int)

        # Outcome as integer for modeling
        pymc_df['applied'] = df['is_applicant'].astype(int)

        # Log-transform skewed features
        pymc_df['log_income'] = np.log1p(df['household_income'].fillna(0))
        pymc_df['log_campaigns'] = np.log1p(df['campaign_count'])

        # Standardized continuous features for modeling
        for col in ['household_income', 'household_size', 'campaign_count',
                    'email_count', 'total_text_count']:
            if col in df.columns:
                mean_val = df[col].mean()
                std_val = df[col].std()
                if std_val > 0:
                    pymc_df[f'{col}_std'] = (df[col] - mean_val) / std_val

        logger.info(f"Created {len([c for c in pymc_df.columns if c not in df.columns])} "
                   f"new columns for PyMC modeling")

        return pymc_df

    def run_phase3(self, max_components: int = 10) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Run complete Phase 3 pipeline."""
        if self.df is None:
            self.load_data()

        X, df = self.prepare_features(self.df)
        bgm = self.fit_bayesian_gmm(X, max_components=max_components)
        result_df = self.extract_soft_assignments(bgm, X, df)
        cluster_stats_df = self.analyze_clusters(result_df)

        # Prepare PyMC-ready data
        pymc_df = self.prepare_for_pymc(result_df)

        self._save_results(pymc_df, cluster_stats_df)

        return pymc_df, cluster_stats_df

    def _save_results(self, result_df: pd.DataFrame, cluster_stats_df: pd.DataFrame):
        """Save Phase 3 results."""
        # Save main results
        result_df.to_parquet(self.data_path / 'phase3_bayesian_integration.parquet', index=False)
        cluster_stats_df.to_csv(self.data_path / 'phase3_cluster_stats.csv', index=False)

        # Save probability matrix
        np.save(self.data_path / 'phase3_cluster_probs.npy', self.cluster_probs)

        # Save summary for PyMC modeling
        pymc_summary = {
            'n_participants': len(result_df),
            'n_applicants': int(result_df['is_applicant'].sum()),
            'n_effective_clusters': len(cluster_stats_df),
            'baseline_application_rate': float(result_df['is_applicant'].mean()),
            'cluster_prob_columns': [c for c in result_df.columns if c.startswith('cluster_prob_')],
            'treatment_columns': ['has_text_treatment', 'has_email_treatment', 'has_both_treatment'],
            'outcome_column': 'applied'
        }
        with open(self.data_path / 'phase3_pymc_summary.json', 'w') as f:
            json.dump(pymc_summary, f, indent=2)

        logger.info(f"Saved Phase 3 results to {self.data_path}")

    def print_summary(self, cluster_stats_df: pd.DataFrame, result_df: pd.DataFrame):
        """Print Phase 3 summary."""
        print("\n" + "=" * 80)
        print("PHASE 3: PROBABILISTIC CLUSTERING FOR BAYESIAN MODELING")
        print("=" * 80)

        print(f"\nEffective clusters: {len(cluster_stats_df)}")
        print(f"Mean cluster confidence: {result_df['cluster_confidence'].mean():.1%}")

        sorted_stats = cluster_stats_df.sort_values('application_rate', ascending=False)

        print("\nCluster Performance:")
        print("-" * 80)
        print(f"{'Cluster':<8} {'Size':<10} {'App Rate':<10} {'Lift':<8} {'Confidence':<12}")
        print("-" * 80)

        for _, row in sorted_stats.iterrows():
            print(f"{int(row['cluster']):<8} {int(row['n_participants']):,<10} "
                  f"{row['application_rate']:.2f}%{'':<4} "
                  f"{row['lift_vs_baseline']:.2f}x{'':<3} "
                  f"{row['avg_confidence']:.1f}%")

        print("-" * 80)

        # Treatment effect preview
        print("\nTreatment Effect Preview (for causal modeling):")
        print("-" * 80)
        text_only = result_df[(result_df['has_text_treatment'] == 1) &
                              (result_df['has_email_treatment'] == 0)]
        email_only = result_df[(result_df['has_email_treatment'] == 1) &
                               (result_df['has_text_treatment'] == 0)]
        both = result_df[(result_df['has_text_treatment'] == 1) &
                         (result_df['has_email_treatment'] == 1)]

        print(f"Text only:  {len(text_only):,} participants, "
              f"{text_only['is_applicant'].mean():.2%} app rate")
        print(f"Email only: {len(email_only):,} participants, "
              f"{email_only['is_applicant'].mean():.2%} app rate")
        print(f"Both:       {len(both):,} participants, "
              f"{both['is_applicant'].mean():.2%} app rate")

        print("\n→ Naive text effect: "
              f"{(text_only['is_applicant'].mean() - email_only['is_applicant'].mean()) * 100:.2f} "
              f"percentage points (unconditioned)")

        print("=" * 80)
        print("\nOutput files for PyMC modeling:")
        print(f"  - phase3_bayesian_integration.parquet (main data)")
        print(f"  - phase3_cluster_probs.npy (soft assignments)")
        print(f"  - phase3_pymc_summary.json (metadata)")


def main():
    """Run Phase 3 probabilistic clustering."""
    clusterer = Phase3ProbabilisticClustering()
    result_df, cluster_stats_df = clusterer.run_phase3(max_components=10)
    clusterer.print_summary(cluster_stats_df, result_df)
    return result_df, cluster_stats_df


if __name__ == '__main__':
    main()
