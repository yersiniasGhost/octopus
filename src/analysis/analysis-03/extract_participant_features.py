"""
Extract and aggregate participant-level features for clustering analysis.
ANALYSIS-03: Email + Text Campaign Integration

This script prepares data following the CLUSTERING_PROJECT.md strategy:
1. Aggregate from observation level (~175K exposures) to participant level (~7.4K)
2. Include BOTH email and text campaign channels
3. Separate pre-treatment features from behavioral outcomes
4. Handle missing values appropriately for clustering algorithms

Key differences from analysis-02:
- Includes text campaign exposures (46K additional exposures)
- Adds text-specific engagement metrics (text_delivered, text_replied)
- Captures 373 new text-only participants
- Overall engagement rate: 8.54% (vs 2.18% email-only)

Output: DataFrame with participant-level features ready for FAMD and clustering.
"""
import logging
from typing import Optional, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParticipantFeatureExtractor:
    """Extract participant-level features from campaign_data database."""

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "campaign_data"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    def extract_demographics(self) -> pd.DataFrame:
        """Extract demographic features from participants collection."""
        logger.info("Extracting demographic features...")

        participants = list(self.db.participants.find({}, {
            'participant_id': 1,
            'demographics': 1,
            'residence': 1,
            'data_quality': 1,
            'engagement_summary': 1
        }))

        records = []
        for p in participants:
            demo = p.get('demographics', {})
            res = p.get('residence', {})
            qual = p.get('data_quality', {})
            eng = p.get('engagement_summary', {})

            records.append({
                'participant_id': p['participant_id'],
                # Demographics (continuous)
                'estimated_income': demo.get('estimated_income'),
                'income_level': demo.get('income_level'),
                'household_size': demo.get('household_size'),
                'total_energy_burden': demo.get('total_energy_burden'),
                'energy_burden_kwh': demo.get('energy_burden_kwh'),
                'energy_burden_gas': demo.get('energy_burden_gas'),
                'number_of_adults': demo.get('number_of_adults'),
                'annual_kwh_cost': demo.get('annual_kwh_cost'),
                'annual_gas_cost': demo.get('annual_gas_cost'),
                # Demographics (categorical)
                'age_bracket': demo.get('age_bracket'),
                'home_owner': demo.get('home_owner'),
                'dwelling_type': demo.get('dwelling_type'),
                'marital_status': demo.get('marital_status'),
                'presence_of_children': demo.get('presence_of_children'),
                # Residence (continuous)
                'living_area_sqft': res.get('living_area_sqft'),
                'house_age': res.get('house_age'),
                'year_built': res.get('year_built'),
                'bedrooms': res.get('bedrooms'),
                'bathrooms': res.get('bathrooms'),
                'rooms_total': res.get('rooms_total'),
                'story_height': res.get('story_height'),
                'garage_size': res.get('garage_size'),
                # Residence (categorical)
                'heat_type': res.get('heat_type'),
                'air_conditioning': res.get('air_conditioning'),
                'construction_quality': res.get('construction_quality'),
                # Data quality flags
                'has_demographics': qual.get('has_demographics', False),
                'has_residence': qual.get('has_residence', False),
                'completeness_score': qual.get('completeness_score', 0.0),
                'analysis_ready': qual.get('analysis_ready', False),
                # Pre-computed engagement (for outcome analysis, not clustering input)
                'total_campaigns': eng.get('total_campaigns', 0),
                'total_exposures': eng.get('total_exposures', 0),
                'ever_received': eng.get('ever_received', False),
                'ever_engaged': eng.get('ever_engaged', False),
                'overall_receive_rate': eng.get('overall_receive_rate', 0.0),
                'overall_engage_rate': eng.get('overall_engage_rate', 0.0)
            })

        df = pd.DataFrame(records)
        logger.info(f"Extracted {len(df)} participants with demographics")
        return df

    def extract_campaign_exposure_aggregates(self) -> pd.DataFrame:
        """Aggregate campaign exposure data to participant level."""
        logger.info("Aggregating campaign exposures...")

        # Build campaign_id -> message_types lookup
        campaigns = list(self.db.campaigns.find({}, {'campaign_id': 1, 'message_types': 1}))
        campaign_types = {c['campaign_id']: c.get('message_types') or [] for c in campaigns}

        # Get all unique message types (handle None values)
        all_message_types = set()
        for types in campaign_types.values():
            if types:  # Only update if not None/empty
                all_message_types.update(types)
        self.message_types = sorted(all_message_types)
        logger.info(f"Found {len(self.message_types)} message types: {self.message_types}")

        pipeline = [
            {
                '$group': {
                    '_id': '$participant_id',
                    # Campaign counts
                    'campaign_count': {'$sum': 1},
                    # Channel distribution - email
                    'email_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'email']}, 1, 0]}},
                    # Channel distribution - text (single 'text' channel in data)
                    'text_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'text']}, 1, 0]}},
                    # Legacy text channels (for backwards compatibility)
                    'text_morning_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'text_morning']}, 1, 0]}},
                    'text_evening_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'text_evening']}, 1, 0]}},
                    # Postal channels
                    'mailer_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'mailer']}, 1, 0]}},
                    'letter_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'letter']}, 1, 0]}},
                    # Email engagement
                    'email_opens': {'$sum': {'$cond': ['$email_opened', 1, 0]}},
                    'email_clicks': {'$sum': {'$cond': ['$email_clicked', 1, 0]}},
                    'email_bounces': {'$sum': {'$cond': ['$email_bounced', 1, 0]}},
                    'email_complaints': {'$sum': {'$cond': ['$email_complained', 1, 0]}},
                    # Text engagement (NEW for analysis-03)
                    'text_delivered': {'$sum': {'$cond': ['$text_delivered', 1, 0]}},
                    'text_replied': {'$sum': {'$cond': ['$text_replied', 1, 0]}},
                    # Unified engagement
                    'engaged_count': {'$sum': {'$cond': [{'$eq': ['$unified_status', 'engaged']}, 1, 0]}},
                    'received_count': {'$sum': {'$cond': [{'$eq': ['$unified_status', 'received']}, 1, 0]}},
                    # Timing
                    'first_sent': {'$min': '$sent_at'},
                    'last_sent': {'$max': '$sent_at'},
                    # Unique campaigns - keep IDs for message type lookup
                    'unique_campaigns': {'$addToSet': '$campaign_id'}
                }
            },
            {
                '$project': {
                    'participant_id': '$_id',
                    'campaign_count': 1,
                    'email_count': 1,
                    'text_count': 1,
                    'text_morning_count': 1,
                    'text_evening_count': 1,
                    'mailer_count': 1,
                    'letter_count': 1,
                    'email_opens': 1,
                    'email_clicks': 1,
                    'email_bounces': 1,
                    'email_complaints': 1,
                    'text_delivered': 1,
                    'text_replied': 1,
                    'engaged_count': 1,
                    'received_count': 1,
                    'first_sent': 1,
                    'last_sent': 1,
                    'unique_campaigns': 1,
                    'unique_campaign_count': {'$size': '$unique_campaigns'}
                }
            }
        ]

        results = list(self.db.campaign_exposures.aggregate(pipeline))
        df = pd.DataFrame(results)

        # Compute message type exposure counts for each participant
        if len(df) > 0:
            for msg_type in self.message_types:
                col_name = f'msgtype_{msg_type}_count'
                df[col_name] = df['unique_campaigns'].apply(
                    lambda camps: sum(1 for c in camps if msg_type in campaign_types.get(c, []))
                )

            # Drop unique_campaigns list (no longer needed)
            df = df.drop(columns=['unique_campaigns'])

        if len(df) > 0:
            # Compute derived metrics
            # Combine text channels (text + legacy text_morning + text_evening)
            df['total_text_count'] = (df['text_count'] +
                                       df['text_morning_count'] +
                                       df['text_evening_count'])
            df['postal_count'] = df['mailer_count'] + df['letter_count']

            # Email engagement rates (with exposure)
            df['email_open_rate'] = np.where(df['email_count'] > 0,
                                              df['email_opens'] / df['email_count'], 0)
            df['email_click_rate'] = np.where(df['email_count'] > 0,
                                               df['email_clicks'] / df['email_count'], 0)

            # Text engagement rates (NEW for analysis-03)
            df['text_delivery_rate'] = np.where(df['total_text_count'] > 0,
                                                 df['text_delivered'] / df['total_text_count'], 0)
            df['text_reply_rate'] = np.where(df['total_text_count'] > 0,
                                              df['text_replied'] / df['total_text_count'], 0)

            # Overall engagement rate
            df['engage_rate'] = np.where(df['campaign_count'] > 0,
                                          df['engaged_count'] / df['campaign_count'], 0)
            df['receive_rate'] = np.where(df['campaign_count'] > 0,
                                           df['received_count'] / df['campaign_count'], 0)

            # Binary outcomes
            df['ever_engaged'] = df['engaged_count'] > 0
            df['ever_received'] = df['received_count'] > 0
            df['ever_clicked'] = df['email_clicks'] > 0
            df['ever_replied_text'] = df['text_replied'] > 0  # NEW for analysis-03

            # Campaign exposure duration
            df['exposure_days'] = (df['last_sent'] - df['first_sent']).dt.days.fillna(0)

            # Channel diversity (number of distinct channels used)
            df['channel_diversity'] = (
                (df['email_count'] > 0).astype(int) +
                (df['total_text_count'] > 0).astype(int) +
                (df['postal_count'] > 0).astype(int)
            )

            # Channel flags for analysis (NEW for analysis-03)
            df['has_email'] = df['email_count'] > 0
            df['has_text'] = df['total_text_count'] > 0
            df['has_postal'] = df['postal_count'] > 0

        logger.info(f"Aggregated exposures for {len(df)} participants")
        return df

    def build_analysis_dataset(self, require_demographics: bool = True,
                                require_residence: bool = False,
                                min_completeness: float = 0.0) -> pd.DataFrame:
        """
        Build complete participant-level dataset for clustering.

        Args:
            require_demographics: Filter to participants with demographics
            require_residence: Filter to participants with residence data
            min_completeness: Minimum completeness score threshold

        Returns:
            DataFrame with participant-level features
        """
        logger.info("Building analysis dataset...")

        # Extract base features
        demo_df = self.extract_demographics()
        exposure_df = self.extract_campaign_exposure_aggregates()

        # Merge datasets
        df = demo_df.merge(exposure_df, on='participant_id', how='left', suffixes=('', '_exp'))

        # Apply filters
        if require_demographics:
            df = df[df['has_demographics'] == True]
            logger.info(f"After demographics filter: {len(df)} participants")

        if require_residence:
            df = df[df['has_residence'] == True]
            logger.info(f"After residence filter: {len(df)} participants")

        if min_completeness > 0:
            df = df[df['completeness_score'] >= min_completeness]
            logger.info(f"After completeness filter: {len(df)} participants")

        # Fill missing exposure values for participants without exposures
        exposure_cols = ['campaign_count', 'email_count', 'text_count', 'total_text_count', 'postal_count',
                        'engaged_count', 'received_count', 'email_opens', 'email_clicks',
                        'text_delivered', 'text_replied']
        for col in exposure_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        logger.info(f"Final analysis dataset: {len(df)} participants")
        return df

    def get_clustering_feature_sets(self, df: pd.DataFrame) -> dict:
        """
        Define feature sets for progressive clustering phases.

        Returns dict with:
        - phase1_continuous: Demographics continuous features
        - phase1_categorical: Demographics categorical features
        - phase2_continuous: + Campaign exposure features + message type features
        - outcome_features: Binary outcomes for validation (not clustering)
        """
        # Dynamically get message type columns from dataframe
        msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]

        return {
            # Phase 1: Demographics only
            'phase1_continuous': [
                'estimated_income', 'income_level', 'household_size',
                'total_energy_burden', 'number_of_adults',
                'living_area_sqft', 'house_age', 'bedrooms', 'bathrooms'
            ],
            'phase1_categorical': [
                'home_owner', 'dwelling_type', 'presence_of_children'
            ],
            # Phase 2: Add campaign exposure + message types (updated for analysis-03)
            'phase2_continuous': [
                'estimated_income', 'income_level', 'household_size',
                'total_energy_burden', 'number_of_adults',
                'living_area_sqft', 'house_age', 'bedrooms', 'bathrooms',
                'campaign_count', 'email_count', 'total_text_count', 'postal_count',
                'exposure_days', 'channel_diversity'
            ] + msgtype_cols,
            'phase2_categorical': [
                'home_owner', 'dwelling_type', 'presence_of_children'
            ],
            # Message type features separately for Phase 2b analysis
            'message_type_features': msgtype_cols,
            # Channel-specific features (NEW for analysis-03)
            'channel_features': [
                'email_count', 'total_text_count', 'postal_count',
                'email_open_rate', 'email_click_rate',
                'text_delivery_rate', 'text_reply_rate',
                'channel_diversity'
            ],
            # Outcomes for validation (NOT clustering input) - updated for analysis-03
            'outcome_features': [
                'ever_engaged', 'ever_clicked', 'ever_received', 'ever_replied_text',
                'engage_rate', 'email_click_rate', 'text_reply_rate', 'engaged_count'
            ]
        }

    def print_data_summary(self, df: pd.DataFrame):
        """Print summary statistics for the analysis dataset."""
        print("\n" + "="*60)
        print("ANALYSIS-03: EMAIL + TEXT CAMPAIGN DATASET SUMMARY")
        print("="*60)

        print(f"\nTotal participants: {len(df):,}")

        # Data quality
        print(f"\nData Quality:")
        print(f"  With demographics: {df['has_demographics'].sum():,} ({100*df['has_demographics'].mean():.1f}%)")
        print(f"  With residence: {df['has_residence'].sum():,} ({100*df['has_residence'].mean():.1f}%)")
        print(f"  Analysis ready: {df['analysis_ready'].sum():,} ({100*df['analysis_ready'].mean():.1f}%)")

        # Channel coverage (NEW for analysis-03)
        if 'has_email' in df.columns:
            print(f"\nChannel Coverage:")
            email_only = ((df['has_email']) & (~df['has_text'])).sum()
            text_only = ((~df['has_email']) & (df['has_text'])).sum()
            both = ((df['has_email']) & (df['has_text'])).sum()
            print(f"  Email only: {email_only:,} ({100*email_only/len(df):.1f}%)")
            print(f"  Text only: {text_only:,} ({100*text_only/len(df):.1f}%)")
            print(f"  Both channels: {both:,} ({100*both/len(df):.1f}%)")

        # Engagement outcomes (for rare outcome analysis)
        if 'ever_engaged' in df.columns:
            engaged = df['ever_engaged'].sum() if df['ever_engaged'].dtype == bool else (df['ever_engaged'] == True).sum()
            print(f"\nEngagement Outcomes:")
            print(f"  Ever engaged (any channel): {engaged:,} ({100*engaged/len(df):.2f}%)")

        if 'ever_clicked' in df.columns:
            clicked = df['ever_clicked'].sum() if df['ever_clicked'].dtype == bool else (df['ever_clicked'] == True).sum()
            print(f"  Ever clicked (email): {clicked:,} ({100*clicked/len(df):.2f}%)")

        if 'ever_replied_text' in df.columns:
            replied = df['ever_replied_text'].sum() if df['ever_replied_text'].dtype == bool else (df['ever_replied_text'] == True).sum()
            print(f"  Ever replied (text): {replied:,} ({100*replied/len(df):.2f}%)")

        # Message type exposure summary
        msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
        if msgtype_cols:
            print(f"\nMessage Type Exposure (mean campaigns per participant):")
            for col in sorted(msgtype_cols):
                msg_name = col.replace('msgtype_', '').replace('_count', '')
                mean_exp = df[col].mean()
                has_any = (df[col] > 0).sum()
                print(f"  {msg_name}: {mean_exp:.1f} avg, {has_any:,} participants ({100*has_any/len(df):.1f}%)")

        # Feature completeness
        feature_sets = self.get_clustering_feature_sets(df)
        print(f"\nPhase 1 Features (Demographics):")
        for col in feature_sets['phase1_continuous']:
            if col in df.columns:
                non_null = df[col].notna().sum()
                print(f"  {col}: {non_null:,} ({100*non_null/len(df):.1f}%)")

        print("\n" + "="*60)


def main(output_dir: str = '/home/yersinia/devel/octopus/data/clustering_results-03'):
    """Extract and save participant features for clustering analysis (analysis-03: email + text)."""
    from pathlib import Path
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    extractor = ParticipantFeatureExtractor()

    # Build dataset with minimal filtering first
    df_all = extractor.build_analysis_dataset(
        require_demographics=False,
        require_residence=False,
        min_completeness=0.0
    )

    # Print summary
    extractor.print_data_summary(df_all)

    # Save full dataset
    output_path = f'{output_dir}/participant_features.parquet'
    df_all.to_parquet(output_path, index=False)
    logger.info(f"Saved full dataset to {output_path}")

    # Also create filtered dataset for analysis
    df_analysis = extractor.build_analysis_dataset(
        require_demographics=True,
        require_residence=False,
        min_completeness=0.3
    )

    analysis_path = f'{output_dir}/participant_features_analysis.parquet'
    df_analysis.to_parquet(analysis_path, index=False)
    logger.info(f"Saved analysis dataset to {analysis_path}")

    return df_all, df_analysis


if __name__ == '__main__':
    main()
