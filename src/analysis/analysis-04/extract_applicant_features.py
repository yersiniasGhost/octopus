"""
Extract and aggregate participant-level features for applicant analysis.
ANALYSIS-04: Applicant-Centric Clustering

Key differences from analysis-03:
1. Outcome variable: is_applicant (binary) - who converted to application
2. Demographics: Self-reported for applicants (when available), fallback to participant
3. Include both house_age AND participant age
4. All participants included with is_applicant flag
5. Channel exposure: letter=baseline (everyone), email/text=variable
6. UTM attribution: Track channel_of_conversion for applicants

Purpose: Understand what drives applications for Bayesian causal modeling.

Output: DataFrame with participant-level features + is_applicant outcome.
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ApplicantFeatureExtractor:
    """Extract participant-level features with applicant outcome for clustering."""

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "campaign_data"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.message_types: List[str] = []

    def extract_applications(self) -> pd.DataFrame:
        """Extract application data with self-reported demographics and UTM."""
        logger.info("Extracting applications...")

        applications = list(self.db.applications.find({}, {
            'application_id': 1,
            'applicant': 1,
            'address': 1,
            'self_reported': 1,
            'attribution': 1,
            'participant_match': 1,
            'entry_date': 1
        }))

        records = []
        for app in applications:
            self_rep = app.get('self_reported', {})
            utm = app.get('attribution', {}).get('utm', {})
            match = app.get('participant_match', {})
            address = app.get('address', {})
            applicant = app.get('applicant', {})

            records.append({
                'application_id': app['application_id'],
                # Linkage to participant
                'matched_participant_id': match.get('participant_id'),
                'match_method': match.get('match_method'),
                'match_confidence': match.get('match_confidence', 0.0),
                # Self-reported demographics
                'sr_age': self_rep.get('age'),
                'sr_household_income': self_rep.get('household_income'),
                'sr_household_members': self_rep.get('household_members'),
                'sr_housing_status': self_rep.get('housing_status'),
                'sr_needs_housing_help': self_rep.get('needs_housing_help'),
                'sr_has_dependent_children': self_rep.get('has_dependent_children'),
                'sr_pre_1978_home': self_rep.get('pre_1978_home'),
                # UTM attribution
                'utm_source': utm.get('utm_source'),
                'utm_medium': utm.get('utm_medium'),
                'utm_campaign': utm.get('utm_campaign'),
                'utm_id': utm.get('utm_id'),
                'utm_content': utm.get('utm_content'),
                # Location for matching
                'app_county': address.get('county'),
                'app_zip': address.get('zip'),
                'app_email': applicant.get('email'),
                'app_phone': applicant.get('phone'),
                # Timing
                'application_date': app.get('entry_date')
            })

        df = pd.DataFrame(records)
        logger.info(f"Extracted {len(df)} applications")

        # Derive channel_of_conversion from UTM
        if len(df) > 0:
            df['channel_of_conversion'] = df['utm_medium'].apply(self._classify_conversion_channel)

        return df

    def _classify_conversion_channel(self, utm_medium: Optional[str]) -> str:
        """Classify conversion channel from UTM medium."""
        if not utm_medium:
            return 'unknown'
        medium_lower = str(utm_medium).lower()
        if medium_lower in ['letter', 'mail', 'mailer', 'postal']:
            return 'letter'
        elif medium_lower in ['sms', 'text']:
            return 'text'
        elif medium_lower in ['email', 'emailoctopus']:
            return 'email'
        else:
            return 'other'

    def extract_participant_demographics(self) -> pd.DataFrame:
        """Extract participant demographics from participants collection."""
        logger.info("Extracting participant demographics...")

        participants = list(self.db.participants.find({}, {
            'participant_id': 1,
            'demographics': 1,
            'residence': 1,
            'data_quality': 1,
            'engagement_summary': 1,
            'email': 1,
            'phone': 1
        }))

        records = []
        for p in participants:
            demo = p.get('demographics', {})
            res = p.get('residence', {})
            qual = p.get('data_quality', {})

            records.append({
                'participant_id': p['participant_id'],
                'email': p.get('email'),
                'phone': p.get('phone'),
                # Demographics (continuous) - from participant enrichment
                'p_estimated_income': demo.get('estimated_income'),
                'p_household_size': demo.get('household_size'),
                'p_total_energy_burden': demo.get('total_energy_burden'),
                'p_number_of_adults': demo.get('number_of_adults'),
                'p_annual_kwh_cost': demo.get('annual_kwh_cost'),
                'p_annual_gas_cost': demo.get('annual_gas_cost'),
                # Demographics (categorical)
                'p_age_bracket': demo.get('age_bracket'),
                'p_home_owner': demo.get('home_owner'),
                'p_dwelling_type': demo.get('dwelling_type'),
                'p_marital_status': demo.get('marital_status'),
                'p_presence_of_children': demo.get('presence_of_children'),
                # Residence
                'p_living_area_sqft': res.get('living_area_sqft'),
                'p_house_age': res.get('house_age'),
                'p_year_built': res.get('year_built'),
                'p_bedrooms': res.get('bedrooms'),
                'p_bathrooms': res.get('bathrooms'),
                'p_heat_type': res.get('heat_type'),
                'p_air_conditioning': res.get('air_conditioning'),
                # Data quality
                'has_demographics': qual.get('has_demographics', False),
                'has_residence': qual.get('has_residence', False),
                'completeness_score': qual.get('completeness_score', 0.0)
            })

        df = pd.DataFrame(records)
        logger.info(f"Extracted {len(df)} participants with demographics")
        return df

    def extract_campaign_exposures(self) -> pd.DataFrame:
        """Aggregate campaign exposure data to participant level."""
        logger.info("Aggregating campaign exposures...")

        # Build campaign_id -> message_types lookup
        campaigns = list(self.db.campaigns.find({}, {'campaign_id': 1, 'message_types': 1, 'channel': 1}))
        campaign_types = {c['campaign_id']: c.get('message_types') or [] for c in campaigns}
        campaign_channels = {c['campaign_id']: c.get('channel', 'unknown') for c in campaigns}

        # Get all unique message types
        all_message_types = set()
        for types in campaign_types.values():
            if types:
                all_message_types.update(types)
        self.message_types = sorted(all_message_types)
        logger.info(f"Found {len(self.message_types)} message types: {self.message_types}")

        pipeline = [
            {
                '$group': {
                    '_id': '$participant_id',
                    # Campaign counts
                    'campaign_count': {'$sum': 1},
                    # Channel distribution
                    'email_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'email']}, 1, 0]}},
                    'text_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'text']}, 1, 0]}},
                    'text_morning_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'text_morning']}, 1, 0]}},
                    'text_evening_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'text_evening']}, 1, 0]}},
                    'mailer_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'mailer']}, 1, 0]}},
                    'letter_count': {'$sum': {'$cond': [{'$eq': ['$channel', 'letter']}, 1, 0]}},
                    # Email engagement
                    'email_opens': {'$sum': {'$cond': ['$email_opened', 1, 0]}},
                    'email_clicks': {'$sum': {'$cond': ['$email_clicked', 1, 0]}},
                    # Text engagement
                    'text_delivered': {'$sum': {'$cond': ['$text_delivered', 1, 0]}},
                    'text_replied': {'$sum': {'$cond': ['$text_replied', 1, 0]}},
                    # Unified engagement
                    'engaged_count': {'$sum': {'$cond': [{'$eq': ['$unified_status', 'engaged']}, 1, 0]}},
                    'received_count': {'$sum': {'$cond': [{'$eq': ['$unified_status', 'received']}, 1, 0]}},
                    # Timing
                    'first_sent': {'$min': '$sent_at'},
                    'last_sent': {'$max': '$sent_at'},
                    # Unique campaigns for message type lookup
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
                    'text_delivered': 1,
                    'text_replied': 1,
                    'engaged_count': 1,
                    'received_count': 1,
                    'first_sent': 1,
                    'last_sent': 1,
                    'unique_campaigns': 1
                }
            }
        ]

        results = list(self.db.campaign_exposures.aggregate(pipeline))
        df = pd.DataFrame(results)

        if len(df) > 0:
            # Compute message type exposure counts
            for msg_type in self.message_types:
                col_name = f'msgtype_{msg_type}_count'
                df[col_name] = df['unique_campaigns'].apply(
                    lambda camps: sum(1 for c in camps if msg_type in campaign_types.get(c, []))
                )

            # Drop unique_campaigns list
            df = df.drop(columns=['unique_campaigns'])

            # Compute derived metrics
            df['total_text_count'] = df['text_count'] + df['text_morning_count'] + df['text_evening_count']
            df['postal_count'] = df['mailer_count'] + df['letter_count']

            # Engagement rates
            df['email_open_rate'] = np.where(df['email_count'] > 0, df['email_opens'] / df['email_count'], 0)
            df['email_click_rate'] = np.where(df['email_count'] > 0, df['email_clicks'] / df['email_count'], 0)
            df['text_delivery_rate'] = np.where(df['total_text_count'] > 0,
                                                 df['text_delivered'] / df['total_text_count'], 0)
            df['text_reply_rate'] = np.where(df['total_text_count'] > 0,
                                              df['text_replied'] / df['total_text_count'], 0)

            # Binary flags
            df['ever_engaged'] = df['engaged_count'] > 0
            df['ever_clicked'] = df['email_clicks'] > 0
            df['ever_replied_text'] = df['text_replied'] > 0

            # Exposure duration
            df['exposure_days'] = (df['last_sent'] - df['first_sent']).dt.days.fillna(0)

            # Channel diversity (excluding letter since everyone got it)
            df['channel_diversity'] = (
                (df['email_count'] > 0).astype(int) +
                (df['total_text_count'] > 0).astype(int)
            )

            # Channel combination feature (letter is baseline)
            df['channel_combo'] = df.apply(self._get_channel_combo, axis=1)

            # Channel flags
            df['has_email'] = df['email_count'] > 0
            df['has_text'] = df['total_text_count'] > 0

        logger.info(f"Aggregated exposures for {len(df)} participants")
        return df

    def _get_channel_combo(self, row) -> str:
        """Classify channel combination (letter is baseline for everyone)."""
        has_email = row.get('email_count', 0) > 0
        has_text = row.get('total_text_count', 0) > 0

        if has_email and has_text:
            return 'letter+email+text'
        elif has_email:
            return 'letter+email'
        elif has_text:
            return 'letter+text'
        else:
            return 'letter_only'

    def build_unified_dataset(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Build unified participant dataset with applicant outcome.

        Returns:
            Tuple of (full_dataset, discrepancy_report)
        """
        logger.info("Building unified analysis dataset...")

        # Extract all components
        participants_df = self.extract_participant_demographics()
        exposures_df = self.extract_campaign_exposures()
        applications_df = self.extract_applications()

        # Merge participant demographics with campaign exposures
        df = participants_df.merge(exposures_df, on='participant_id', how='left')

        # Fill missing exposure values
        exposure_cols = ['campaign_count', 'email_count', 'text_count', 'total_text_count', 'postal_count',
                        'engaged_count', 'received_count', 'email_opens', 'email_clicks',
                        'text_delivered', 'text_replied', 'channel_diversity', 'exposure_days']
        for col in exposure_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        # Fill channel flags (explicit bool conversion to avoid FutureWarning)
        for col in ['has_email', 'has_text', 'ever_engaged', 'ever_clicked', 'ever_replied_text']:
            if col in df.columns:
                df[col] = df[col].fillna(False).astype(bool)

        # Fill channel_combo
        if 'channel_combo' in df.columns:
            df['channel_combo'] = df['channel_combo'].fillna('letter_only')

        # Fill message type counts
        msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
        for col in msgtype_cols:
            df[col] = df[col].fillna(0)

        # Create applicant lookup by participant_id
        # Handle duplicates: take most recent application per participant
        matched_apps = applications_df[applications_df['matched_participant_id'].notna()].copy()
        matched_apps = matched_apps.sort_values('application_date', ascending=False)
        matched_apps = matched_apps.drop_duplicates(subset=['matched_participant_id'], keep='first')
        logger.info(f"Unique matched applications: {len(matched_apps)} (after deduplication)")
        applicant_lookup = matched_apps.set_index('matched_participant_id').to_dict('index')

        # Mark applicants and merge self-reported demographics
        df['is_applicant'] = df['participant_id'].isin(applicant_lookup.keys())
        logger.info(f"Applicants matched to participants: {df['is_applicant'].sum()}")

        # Initialize self-reported columns
        sr_cols = ['sr_age', 'sr_household_income', 'sr_household_members', 'sr_housing_status',
                   'sr_needs_housing_help', 'sr_has_dependent_children', 'sr_pre_1978_home',
                   'channel_of_conversion', 'application_date']
        for col in sr_cols:
            df[col] = None

        # Populate self-reported data for applicants
        for idx, row in df[df['is_applicant']].iterrows():
            app_data = applicant_lookup.get(row['participant_id'], {})
            for col in sr_cols:
                if col in app_data:
                    df.at[idx, col] = app_data[col]

        # Build final demographic columns using hierarchical logic:
        # Self-reported (for applicants) → Participant fallback
        df = self._merge_demographics(df)

        # Build discrepancy report before merging
        discrepancy_df = self._build_discrepancy_report(df, applications_df)

        logger.info(f"Final dataset: {len(df)} participants, {df['is_applicant'].sum()} applicants")
        return df, discrepancy_df

    def _merge_demographics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge self-reported and participant demographics.

        Priority: Self-reported (applicants only) → Participant fallback
        """
        # Age: use self-reported if available, else derive from age_bracket
        df['age'] = df['sr_age'].combine_first(
            df['p_age_bracket'].apply(self._age_bracket_to_midpoint)
        )

        # House age: from participant residence data
        df['house_age'] = df['p_house_age']

        # Household income: self-reported → participant estimated
        df['household_income'] = df['sr_household_income'].combine_first(df['p_estimated_income'])

        # Household size: self-reported → participant
        df['household_size'] = df['sr_household_members'].combine_first(df['p_household_size'])

        # Housing status: self-reported → participant home_owner
        df['home_owner'] = df['sr_housing_status'].apply(
            lambda x: True if x == 'own' else (False if x == 'rent' else None)
        ).combine_first(df['p_home_owner'])

        # Presence of children: self-reported → participant
        df['presence_of_children'] = df['sr_has_dependent_children'].combine_first(df['p_presence_of_children'])

        # Pre-1978 home: self-reported only (no participant equivalent)
        df['pre_1978_home'] = df['sr_pre_1978_home']

        # Needs housing help: self-reported only
        df['needs_housing_help'] = df['sr_needs_housing_help']

        # Energy burden: participant only
        df['total_energy_burden'] = df['p_total_energy_burden']

        # Residence features: participant only
        df['living_area_sqft'] = df['p_living_area_sqft']
        df['bedrooms'] = df['p_bedrooms']
        df['bathrooms'] = df['p_bathrooms']
        df['dwelling_type'] = df['p_dwelling_type']

        return df

    def _age_bracket_to_midpoint(self, bracket: Optional[str]) -> Optional[float]:
        """Convert age bracket string to midpoint value."""
        if not bracket:
            return None
        bracket_map = {
            '18-24': 21, '25-34': 29.5, '35-44': 39.5, '45-54': 49.5,
            '55-64': 59.5, '65-74': 69.5, '75+': 80, '75-84': 79.5, '85+': 87
        }
        return bracket_map.get(bracket)

    def _build_discrepancy_report(self, df: pd.DataFrame, applications_df: pd.DataFrame) -> pd.DataFrame:
        """
        Build report comparing self-reported vs participant demographics.

        Only for applicants who matched to participants AND have both data sources.
        """
        logger.info("Building demographics discrepancy report...")

        applicants = df[df['is_applicant']].copy()
        if len(applicants) == 0:
            return pd.DataFrame()

        records = []
        for idx, row in applicants.iterrows():
            record = {
                'participant_id': row['participant_id'],
                # Age comparison
                'sr_age': row['sr_age'],
                'p_age_bracket': row['p_age_bracket'],
                'p_age_midpoint': self._age_bracket_to_midpoint(row['p_age_bracket']),
                'age_discrepancy': None,
                # Income comparison
                'sr_household_income': row['sr_household_income'],
                'p_estimated_income': row['p_estimated_income'],
                'income_discrepancy': None,
                'income_discrepancy_pct': None,
                # Household size comparison
                'sr_household_members': row['sr_household_members'],
                'p_household_size': row['p_household_size'],
                'household_size_discrepancy': None,
                # Home ownership comparison
                'sr_housing_status': row['sr_housing_status'],
                'p_home_owner': row['p_home_owner'],
                'home_owner_match': None,
                # Children comparison
                'sr_has_children': row['sr_has_dependent_children'],
                'p_presence_of_children': row['p_presence_of_children'],
                'children_match': None
            }

            # Calculate discrepancies
            p_age_mid = record['p_age_midpoint']
            if record['sr_age'] and p_age_mid:
                record['age_discrepancy'] = record['sr_age'] - p_age_mid

            if record['sr_household_income'] and record['p_estimated_income']:
                record['income_discrepancy'] = record['sr_household_income'] - record['p_estimated_income']
                if record['p_estimated_income'] > 0:
                    record['income_discrepancy_pct'] = (
                        record['income_discrepancy'] / record['p_estimated_income'] * 100
                    )

            if record['sr_household_members'] is not None and record['p_household_size'] is not None:
                record['household_size_discrepancy'] = record['sr_household_members'] - record['p_household_size']

            # Boolean matches
            sr_owner = True if row['sr_housing_status'] == 'own' else (False if row['sr_housing_status'] == 'rent' else None)
            if sr_owner is not None and row['p_home_owner'] is not None:
                record['home_owner_match'] = sr_owner == row['p_home_owner']

            if row['sr_has_dependent_children'] is not None and row['p_presence_of_children'] is not None:
                record['children_match'] = row['sr_has_dependent_children'] == row['p_presence_of_children']

            records.append(record)

        discrepancy_df = pd.DataFrame(records)

        # Summary statistics
        if len(discrepancy_df) > 0:
            logger.info("Discrepancy Summary:")
            if discrepancy_df['age_discrepancy'].notna().any():
                logger.info(f"  Age: mean={discrepancy_df['age_discrepancy'].mean():.1f}, "
                           f"std={discrepancy_df['age_discrepancy'].std():.1f}")
            if discrepancy_df['income_discrepancy_pct'].notna().any():
                logger.info(f"  Income: mean={discrepancy_df['income_discrepancy_pct'].mean():.1f}%, "
                           f"std={discrepancy_df['income_discrepancy_pct'].std():.1f}%")
            if discrepancy_df['home_owner_match'].notna().any():
                match_rate = discrepancy_df['home_owner_match'].mean() * 100
                logger.info(f"  Home ownership match: {match_rate:.1f}%")
            if discrepancy_df['children_match'].notna().any():
                match_rate = discrepancy_df['children_match'].mean() * 100
                logger.info(f"  Children match: {match_rate:.1f}%")

        return discrepancy_df

    def get_feature_sets(self, df: pd.DataFrame) -> Dict:
        """
        Define feature sets for progressive clustering phases.

        Returns dict with:
        - phase1_continuous: Demographics continuous features
        - phase1_categorical: Demographics categorical features
        - phase2_continuous: + Campaign exposure + message types
        - outcome_variable: is_applicant (binary)
        """
        msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]

        return {
            # Phase 1: Demographics only
            'phase1_continuous': [
                'age', 'house_age', 'household_income', 'household_size',
                'total_energy_burden', 'living_area_sqft', 'bedrooms', 'bathrooms'
            ],
            'phase1_categorical': [
                'home_owner', 'dwelling_type', 'presence_of_children', 'pre_1978_home'
            ],
            # Phase 2: Add campaign exposure + message types
            'phase2_continuous': [
                'age', 'house_age', 'household_income', 'household_size',
                'total_energy_burden', 'living_area_sqft', 'bedrooms', 'bathrooms',
                'campaign_count', 'email_count', 'total_text_count',
                'exposure_days', 'channel_diversity'
            ] + msgtype_cols,
            'phase2_categorical': [
                'home_owner', 'dwelling_type', 'presence_of_children', 'pre_1978_home',
                'channel_combo'
            ],
            # Message type features
            'message_type_features': msgtype_cols,
            # Channel features
            'channel_features': [
                'email_count', 'total_text_count', 'channel_diversity', 'channel_combo',
                'has_email', 'has_text'
            ],
            # Engagement features (intermediate outcomes, not for causal model input)
            'engagement_features': [
                'ever_engaged', 'ever_clicked', 'ever_replied_text',
                'email_open_rate', 'email_click_rate', 'text_reply_rate'
            ],
            # Primary outcome variable
            'outcome_variable': 'is_applicant',
            # Secondary outcome for applicants only
            'conversion_channel': 'channel_of_conversion'
        }

    def print_summary(self, df: pd.DataFrame):
        """Print summary statistics for the analysis dataset."""
        print("\n" + "=" * 70)
        print("ANALYSIS-04: APPLICANT-CENTRIC DATASET SUMMARY")
        print("=" * 70)

        print(f"\nTotal participants: {len(df):,}")
        applicants = df['is_applicant'].sum()
        print(f"Total applicants: {applicants:,} ({100 * applicants / len(df):.2f}%)")

        # Data quality
        print(f"\nData Quality:")
        print(f"  With demographics: {df['has_demographics'].sum():,} ({100 * df['has_demographics'].mean():.1f}%)")
        print(f"  With residence: {df['has_residence'].sum():,} ({100 * df['has_residence'].mean():.1f}%)")

        # Channel exposure
        print(f"\nChannel Exposure:")
        if 'channel_combo' in df.columns:
            for combo in ['letter_only', 'letter+email', 'letter+text', 'letter+email+text']:
                count = (df['channel_combo'] == combo).sum()
                app_rate = df[df['channel_combo'] == combo]['is_applicant'].mean() * 100
                print(f"  {combo}: {count:,} ({100 * count / len(df):.1f}%) - Application rate: {app_rate:.2f}%")

        # Conversion channel for applicants
        if 'channel_of_conversion' in df.columns:
            print(f"\nConversion Channel (applicants only):")
            applicant_df = df[df['is_applicant']]
            for channel in applicant_df['channel_of_conversion'].value_counts().index:
                count = (applicant_df['channel_of_conversion'] == channel).sum()
                print(f"  {channel}: {count} ({100 * count / len(applicant_df):.1f}%)")

        # Demographics coverage
        print(f"\nDemographics Coverage:")
        for col in ['age', 'house_age', 'household_income', 'household_size', 'home_owner']:
            if col in df.columns:
                coverage = df[col].notna().sum()
                print(f"  {col}: {coverage:,} ({100 * coverage / len(df):.1f}%)")

        # Message type exposure
        msgtype_cols = [c for c in df.columns if c.startswith('msgtype_') and c.endswith('_count')]
        if msgtype_cols:
            print(f"\nMessage Type Exposure (mean per participant):")
            for col in sorted(msgtype_cols):
                msg_name = col.replace('msgtype_', '').replace('_count', '')
                mean_exp = df[col].mean()
                has_any = (df[col] > 0).sum()
                # Application rate for those exposed
                app_rate = df[df[col] > 0]['is_applicant'].mean() * 100 if has_any > 0 else 0
                print(f"  {msg_name}: {mean_exp:.1f} avg, {has_any:,} exposed, {app_rate:.2f}% app rate")

        print("\n" + "=" * 70)


def main(output_dir: str = '/home/yersinia/devel/octopus/data/clustering_results-04'):
    """Extract and save participant features with applicant outcome."""
    from pathlib import Path
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    extractor = ApplicantFeatureExtractor()

    # Build unified dataset
    df, discrepancy_df = extractor.build_unified_dataset()

    # Print summary
    extractor.print_summary(df)

    # Save main dataset
    output_path = f'{output_dir}/participant_applicant_features.parquet'
    df.to_parquet(output_path, index=False)
    logger.info(f"Saved main dataset to {output_path}")

    # Save discrepancy report
    if len(discrepancy_df) > 0:
        discrepancy_path = f'{output_dir}/demographics_discrepancy_report.parquet'
        discrepancy_df.to_parquet(discrepancy_path, index=False)
        logger.info(f"Saved discrepancy report to {discrepancy_path}")

        # Also save as CSV for easy viewing
        csv_path = f'{output_dir}/demographics_discrepancy_report.csv'
        discrepancy_df.to_csv(csv_path, index=False)
        logger.info(f"Saved discrepancy report CSV to {csv_path}")

    # Save feature set definitions
    feature_sets = extractor.get_feature_sets(df)
    import json
    with open(f'{output_dir}/feature_sets.json', 'w') as f:
        # Convert to JSON-serializable format
        json_sets = {k: v for k, v in feature_sets.items() if isinstance(v, (list, str))}
        json.dump(json_sets, f, indent=2)
    logger.info(f"Saved feature set definitions")

    return df, discrepancy_df


if __name__ == '__main__':
    main()
