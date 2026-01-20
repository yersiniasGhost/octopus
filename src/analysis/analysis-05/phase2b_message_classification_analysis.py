"""
Phase 2b: Message Classification Effectiveness Analysis
ANALYSIS-05: Message Type Focus

This dedicated analysis examines which message classifications drive applications:
- Per-message-type conversion rates
- Message type by channel interactions
- Optimal message exposure patterns
- Message type clustering to identify responder profiles

Message Types:
- informational: Educational content about program
- motivational_struggle: Empathy-based messaging addressing struggles
- personalized_qualified: Pre-qualification, personalized messaging
- relief_reassurance: Anxiety-reducing, reassurance messaging
- savings_financial: Financial benefit and savings emphasis
- urgency_deadline: Time-limited offers and deadlines

Output: Message effectiveness report and recommendations for campaign optimization.
"""
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class MessageClassificationAnalysis:
    """Dedicated analysis of message type effectiveness on application conversion."""

    MESSAGE_TYPES = [
        'informational',
        'motivational_struggle',
        'personalized_qualified',
        'relief_reassurance',
        'savings_financial',
        'urgency_deadline'
    ]

    MESSAGE_DESCRIPTIONS = {
        'informational': 'Educational content about program details',
        'motivational_struggle': 'Empathy-based messaging addressing struggles',
        'personalized_qualified': 'Pre-qualification, personalized messaging',
        'relief_reassurance': 'Anxiety-reducing, reassurance messaging',
        'savings_financial': 'Financial benefit and savings emphasis',
        'urgency_deadline': 'Time-limited offers and deadlines'
    }

    def __init__(self, data_path: str = '/home/yersinia/devel/octopus/data/clustering_results-05'):
        self.data_path = Path(data_path)
        self.df: Optional[pd.DataFrame] = None
        self.message_cols: List[str] = []
        self.results: Dict = {}

    def load_data(self) -> pd.DataFrame:
        """Load the clustered data from Phase 2."""
        logger.info("Loading Phase 2 clustered data...")
        phase2_path = self.data_path / 'phase2_clustered.parquet'
        self.df = pd.read_parquet(phase2_path)

        # Identify message type columns
        self.message_cols = [f'msgtype_{mt}_count' for mt in self.MESSAGE_TYPES
                            if f'msgtype_{mt}_count' in self.df.columns]
        logger.info(f"Found {len(self.message_cols)} message type columns: {self.message_cols}")
        logger.info(f"Loaded {len(self.df)} participants, {self.df['is_applicant'].sum()} applicants")
        return self.df

    def analyze_message_type_conversion_rates(self) -> pd.DataFrame:
        """
        Calculate conversion rates for participants exposed to each message type.

        For each message type:
        - % exposed (received at least 1 message of this type)
        - Conversion rate for exposed vs unexposed
        - Lift from exposure
        """
        logger.info("Analyzing per-message-type conversion rates...")
        results = []
        baseline_rate = self.df['is_applicant'].mean()

        for msg_type in self.MESSAGE_TYPES:
            col = f'msgtype_{msg_type}_count'
            if col not in self.df.columns:
                continue

            # Split into exposed vs unexposed
            exposed = self.df[self.df[col] > 0]
            unexposed = self.df[self.df[col] == 0]

            exposed_rate = exposed['is_applicant'].mean() if len(exposed) > 0 else 0
            unexposed_rate = unexposed['is_applicant'].mean() if len(unexposed) > 0 else 0

            # Calculate lift
            lift_vs_baseline = exposed_rate / baseline_rate if baseline_rate > 0 else 0
            lift_vs_unexposed = exposed_rate / unexposed_rate if unexposed_rate > 0 else float('inf')

            # Statistical test
            if len(exposed) > 0 and len(unexposed) > 0:
                contingency = pd.crosstab(self.df[col] > 0, self.df['is_applicant'])
                chi2, p_value, _, _ = stats.chi2_contingency(contingency)
            else:
                chi2, p_value = 0, 1.0

            results.append({
                'message_type': msg_type,
                'description': self.MESSAGE_DESCRIPTIONS.get(msg_type, ''),
                'n_exposed': len(exposed),
                'n_unexposed': len(unexposed),
                'pct_exposed': len(exposed) / len(self.df) * 100,
                'exposed_app_rate': exposed_rate * 100,
                'unexposed_app_rate': unexposed_rate * 100,
                'rate_difference_pp': (exposed_rate - unexposed_rate) * 100,
                'lift_vs_baseline': lift_vs_baseline,
                'lift_vs_unexposed': lift_vs_unexposed,
                'chi2': chi2,
                'p_value': p_value,
                'significant': p_value < 0.05
            })

        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('rate_difference_pp', ascending=False)
        self.results['message_type_rates'] = results_df
        return results_df

    def analyze_message_exposure_levels(self) -> pd.DataFrame:
        """
        Analyze conversion rates by message exposure intensity (low/medium/high).

        Groups participants by exposure level for each message type and measures
        conversion rate at each level to identify optimal exposure.
        """
        logger.info("Analyzing message exposure intensity effects...")
        results = []

        for msg_type in self.MESSAGE_TYPES:
            col = f'msgtype_{msg_type}_count'
            if col not in self.df.columns:
                continue

            # Create exposure bins: 0, 1-5, 6-15, 16+
            bins = [0, 1, 6, 16, float('inf')]
            labels = ['none', 'low (1-5)', 'medium (6-15)', 'high (16+)']
            self.df[f'{msg_type}_exposure_level'] = pd.cut(
                self.df[col], bins=bins, labels=labels, right=False
            )

            # Calculate conversion rate per exposure level
            for level in labels:
                subset = self.df[self.df[f'{msg_type}_exposure_level'] == level]
                if len(subset) > 0:
                    results.append({
                        'message_type': msg_type,
                        'exposure_level': level,
                        'n_participants': len(subset),
                        'n_applicants': subset['is_applicant'].sum(),
                        'conversion_rate': subset['is_applicant'].mean() * 100,
                        'avg_exposure': subset[col].mean()
                    })

        results_df = pd.DataFrame(results)
        self.results['exposure_levels'] = results_df
        return results_df

    def analyze_message_channel_interaction(self) -> pd.DataFrame:
        """
        Analyze message type effectiveness by channel (email vs text).

        Some message types may work better via text vs email. This analysis
        identifies channel-message type interactions.
        """
        logger.info("Analyzing message type x channel interactions...")
        results = []

        # Need channel combo
        if 'channel_combo' not in self.df.columns:
            logger.warning("channel_combo not in data, skipping interaction analysis")
            return pd.DataFrame()

        channels = ['letter+email', 'letter+text', 'letter+email+text']

        for msg_type in self.MESSAGE_TYPES:
            col = f'msgtype_{msg_type}_count'
            if col not in self.df.columns:
                continue

            for channel in channels:
                channel_df = self.df[self.df['channel_combo'] == channel]
                if len(channel_df) == 0:
                    continue

                # Compare exposed vs unexposed within this channel
                exposed = channel_df[channel_df[col] > 0]
                unexposed = channel_df[channel_df[col] == 0]

                exposed_rate = exposed['is_applicant'].mean() * 100 if len(exposed) > 0 else 0
                unexposed_rate = unexposed['is_applicant'].mean() * 100 if len(unexposed) > 0 else 0

                results.append({
                    'message_type': msg_type,
                    'channel': channel,
                    'n_total': len(channel_df),
                    'n_exposed': len(exposed),
                    'n_unexposed': len(unexposed),
                    'exposed_rate': exposed_rate,
                    'unexposed_rate': unexposed_rate,
                    'rate_diff': exposed_rate - unexposed_rate,
                    'avg_exposure': channel_df[col].mean()
                })

        results_df = pd.DataFrame(results)
        if not results_df.empty:
            results_df = results_df.sort_values(['message_type', 'rate_diff'], ascending=[True, False])
        self.results['channel_interaction'] = results_df
        return results_df

    def analyze_message_mix_patterns(self) -> pd.DataFrame:
        """
        Cluster participants by their message exposure patterns to identify
        which message mixes are most effective.
        """
        logger.info("Analyzing message mix patterns...")

        # Create binary indicators for exposure to each message type
        for msg_type in self.MESSAGE_TYPES:
            col = f'msgtype_{msg_type}_count'
            if col in self.df.columns:
                self.df[f'has_{msg_type}'] = (self.df[col] > 0).astype(int)

        # Create message mix identifier
        has_cols = [f'has_{mt}' for mt in self.MESSAGE_TYPES if f'has_{mt}' in self.df.columns]
        if not has_cols:
            return pd.DataFrame()

        # Create mix string
        def get_mix_string(row):
            types = [mt for mt in self.MESSAGE_TYPES if row.get(f'has_{mt}', 0) == 1]
            return '+'.join(types) if types else 'none'

        self.df['message_mix'] = self.df.apply(get_mix_string, axis=1)

        # Analyze conversion by message mix
        mix_stats = self.df.groupby('message_mix').agg({
            'is_applicant': ['sum', 'count', 'mean'],
            'campaign_count': 'mean'
        }).reset_index()
        mix_stats.columns = ['message_mix', 'n_applicants', 'n_total', 'conversion_rate', 'avg_campaigns']
        mix_stats['conversion_rate'] = mix_stats['conversion_rate'] * 100
        mix_stats['pct_of_total'] = mix_stats['n_total'] / len(self.df) * 100

        # Sort by conversion rate
        mix_stats = mix_stats.sort_values('conversion_rate', ascending=False)
        self.results['message_mix'] = mix_stats
        return mix_stats

    def cluster_by_message_profile(self, n_clusters: int = 5) -> pd.DataFrame:
        """
        Cluster participants based on their message type exposure profile.
        This creates segments based on message exposure patterns.
        """
        logger.info(f"Clustering participants by message profile (k={n_clusters})...")

        # Prepare message features
        msg_features = []
        for msg_type in self.MESSAGE_TYPES:
            col = f'msgtype_{msg_type}_count'
            if col in self.df.columns:
                msg_features.append(col)

        if not msg_features:
            return pd.DataFrame()

        X = self.df[msg_features].fillna(0).values

        # Standardize
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Cluster
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        self.df['message_cluster'] = kmeans.fit_predict(X_scaled)

        # Analyze clusters
        cluster_stats = []
        baseline_rate = self.df['is_applicant'].mean()

        for cluster_id in range(n_clusters):
            cluster_df = self.df[self.df['message_cluster'] == cluster_id]

            # Message profile
            msg_profile = {f'avg_{mt}': cluster_df[f'msgtype_{mt}_count'].mean()
                         for mt in self.MESSAGE_TYPES
                         if f'msgtype_{mt}_count' in cluster_df.columns}

            # Dominant message type
            dominant = max(msg_profile.items(), key=lambda x: x[1])[0].replace('avg_', '')

            cluster_stats.append({
                'cluster': cluster_id,
                'n_participants': len(cluster_df),
                'n_applicants': cluster_df['is_applicant'].sum(),
                'pct_of_total': len(cluster_df) / len(self.df) * 100,
                'conversion_rate': cluster_df['is_applicant'].mean() * 100,
                'lift_vs_baseline': cluster_df['is_applicant'].mean() / baseline_rate,
                'dominant_message_type': dominant,
                'avg_campaign_count': cluster_df['campaign_count'].mean(),
                **msg_profile
            })

        cluster_df = pd.DataFrame(cluster_stats)
        cluster_df = cluster_df.sort_values('conversion_rate', ascending=False)
        self.results['message_clusters'] = cluster_df
        return cluster_df

    def generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on message analysis."""
        recommendations = []

        # From message type rates
        if 'message_type_rates' in self.results:
            rates = self.results['message_type_rates']
            best = rates.iloc[0] if len(rates) > 0 else None
            worst = rates.iloc[-1] if len(rates) > 0 else None

            if best is not None and best['significant']:
                recommendations.append(
                    f"INCREASE '{best['message_type']}' messaging: "
                    f"{best['rate_difference_pp']:.2f}pp higher conversion rate "
                    f"(p={best['p_value']:.4f})"
                )

            if worst is not None and worst['rate_difference_pp'] < 0:
                recommendations.append(
                    f"REDUCE '{worst['message_type']}' messaging: "
                    f"{abs(worst['rate_difference_pp']):.2f}pp lower conversion rate"
                )

        # From channel interaction
        if 'channel_interaction' in self.results and not self.results['channel_interaction'].empty:
            interactions = self.results['channel_interaction']
            best_combo = interactions.loc[interactions['rate_diff'].idxmax()]
            recommendations.append(
                f"OPTIMIZE channel-message pairing: '{best_combo['message_type']}' via "
                f"'{best_combo['channel']}' shows +{best_combo['rate_diff']:.2f}pp lift"
            )

        # From message mix
        if 'message_mix' in self.results and not self.results['message_mix'].empty:
            mixes = self.results['message_mix']
            best_mix = mixes.iloc[0]
            if best_mix['n_total'] >= 50:  # Minimum sample size
                recommendations.append(
                    f"OPTIMAL MESSAGE MIX: '{best_mix['message_mix']}' achieves "
                    f"{best_mix['conversion_rate']:.2f}% conversion "
                    f"(n={best_mix['n_total']})"
                )

        return recommendations

    def save_results(self):
        """Save all analysis results to files."""
        logger.info("Saving message classification analysis results...")

        # Save individual result dataframes
        for name, df in self.results.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                csv_path = self.data_path / f'phase2b_{name}.csv'
                df.to_csv(csv_path, index=False)
                logger.info(f"Saved {csv_path}")

        # Save clustered data with message clusters
        if 'message_cluster' in self.df.columns:
            parquet_path = self.data_path / 'phase2b_message_clustered.parquet'
            self.df.to_parquet(parquet_path, index=False)
            logger.info(f"Saved {parquet_path}")

        # Generate summary report
        self._generate_summary_report()

    def _generate_summary_report(self):
        """Generate markdown summary report."""
        report_lines = [
            "# Phase 2b: Message Classification Effectiveness Report",
            f"\n**Analysis Date**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Total Participants**: {len(self.df):,}",
            f"**Total Applicants**: {self.df['is_applicant'].sum():,}",
            f"**Baseline Conversion Rate**: {self.df['is_applicant'].mean() * 100:.2f}%",
            "\n---\n",
            "## Message Type Conversion Rates\n"
        ]

        if 'message_type_rates' in self.results:
            rates = self.results['message_type_rates']
            report_lines.append("| Message Type | % Exposed | Exposed Rate | Unexposed Rate | Difference | Significant |")
            report_lines.append("|--------------|-----------|--------------|----------------|------------|-------------|")
            for _, row in rates.iterrows():
                sig = "Yes" if row['significant'] else "No"
                report_lines.append(
                    f"| {row['message_type']} | {row['pct_exposed']:.1f}% | "
                    f"{row['exposed_app_rate']:.2f}% | {row['unexposed_app_rate']:.2f}% | "
                    f"{row['rate_difference_pp']:+.2f}pp | {sig} |"
                )

        report_lines.append("\n---\n")
        report_lines.append("## Message Clusters (by Exposure Profile)\n")

        if 'message_clusters' in self.results:
            clusters = self.results['message_clusters']
            report_lines.append("| Cluster | N | Conv Rate | Lift | Dominant Type |")
            report_lines.append("|---------|---|-----------|------|---------------|")
            for _, row in clusters.iterrows():
                report_lines.append(
                    f"| {int(row['cluster'])} | {int(row['n_participants']):,} | "
                    f"{row['conversion_rate']:.2f}% | {row['lift_vs_baseline']:.2f}x | "
                    f"{row['dominant_message_type']} |"
                )

        report_lines.append("\n---\n")
        report_lines.append("## Recommendations\n")

        recommendations = self.generate_recommendations()
        for i, rec in enumerate(recommendations, 1):
            report_lines.append(f"{i}. {rec}")

        report_lines.append("\n---\n")
        report_lines.append("*Generated by Analysis-05 Phase 2b*")

        report_path = self.data_path / 'MESSAGE_CLASSIFICATION_REPORT.md'
        with open(report_path, 'w') as f:
            f.write('\n'.join(report_lines))
        logger.info(f"Saved {report_path}")

    def run_full_analysis(self) -> Dict:
        """Run complete message classification analysis pipeline."""
        logger.info("=" * 60)
        logger.info("PHASE 2b: MESSAGE CLASSIFICATION ANALYSIS")
        logger.info("=" * 60)

        self.load_data()

        # Run all analyses
        logger.info("\n--- Per-Message-Type Conversion Rates ---")
        rates = self.analyze_message_type_conversion_rates()
        print("\nMessage Type Conversion Rates:")
        print(rates[['message_type', 'pct_exposed', 'exposed_app_rate',
                    'unexposed_app_rate', 'rate_difference_pp', 'significant']].to_string())

        logger.info("\n--- Message Exposure Intensity ---")
        levels = self.analyze_message_exposure_levels()

        logger.info("\n--- Message Type x Channel Interactions ---")
        interactions = self.analyze_message_channel_interaction()
        if not interactions.empty:
            print("\nTop Channel-Message Interactions:")
            top_interactions = interactions.nlargest(10, 'rate_diff')
            print(top_interactions[['message_type', 'channel', 'n_exposed',
                                   'exposed_rate', 'rate_diff']].to_string())

        logger.info("\n--- Message Mix Patterns ---")
        mixes = self.analyze_message_mix_patterns()
        if not mixes.empty:
            print("\nTop Message Mixes by Conversion:")
            print(mixes.head(10).to_string())

        logger.info("\n--- Message Profile Clustering ---")
        clusters = self.cluster_by_message_profile(n_clusters=5)
        print("\nMessage Profile Clusters:")
        print(clusters.to_string())

        # Generate and print recommendations
        print("\n" + "=" * 60)
        print("RECOMMENDATIONS")
        print("=" * 60)
        recommendations = self.generate_recommendations()
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")

        # Save results
        self.save_results()

        return self.results


def main():
    """Run the message classification analysis."""
    analyzer = MessageClassificationAnalysis()
    results = analyzer.run_full_analysis()
    return results


if __name__ == "__main__":
    main()
