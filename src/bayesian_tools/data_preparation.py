"""
Data preparation utilities for Bayesian modeling.

This module handles:
- Loading data from MongoDB collections
- Merging participant, demographic, property, and energy data
- Handling missing values
- Scaling continuous predictors
- Encoding categorical variables
- Creating campaign and ZIP indices
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, List, Optional
from sklearn.preprocessing import StandardScaler
from pymongo import MongoClient

from src.utils.envvars import EnvVars


class BayesianDataPrep:
    """Data preparation for Bayesian engagement models."""

    def __init__(self):
        """
        Initialize with MongoDB connections from environment variables.

        Uses two databases:
        - MONGODB_OCTOPUS: Campaign and participant data
        - MONGODB_DATABASE: Demographic, residential, and energy data
        """
        env = EnvVars()

        # Get connection details
        host = env.get_env('MONGODB_HOST', 'localhost')
        port = int(env.get_env('MONGODB_PORT', '27017'))

        # Get database names
        octopus_db_name = env.get_env('MONGODB_OCTOPUS')
        county_db_name = env.get_env('MONGODB_DATABASE')

        if not octopus_db_name:
            raise ValueError("MONGODB_OCTOPUS environment variable is required for participant data")
        if not county_db_name:
            raise ValueError("MONGODB_DATABASE environment variable is required for demographic data")

        # Create MongoDB client
        self.client = MongoClient(host, port)

        # Connect to both databases
        self.octopus_db = self.client[octopus_db_name]  # Participants, campaigns
        self.county_db = self.client[county_db_name]    # Demographics, property data

        # For backwards compatibility
        self.db = self.octopus_db

        self.scaler = StandardScaler()

        print(f"Connected to MongoDB at {host}:{port}")
        print(f"  - Octopus DB (participants/campaigns): {octopus_db_name}")
        print(f"  - County DB (demographics/property): {county_db_name}")

    def load_participants(self, campaign_ids: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Load participant data with engagement outcomes.

        Args:
            campaign_ids: Optional list of campaign IDs to filter. If None, loads all.

        Returns:
            DataFrame with participant data
        """
        query = {}
        if campaign_ids:
            query['campaign_id'] = {'$in': campaign_ids}

        participants = list(self.octopus_db.participants.find(query))

        if not participants:
            raise ValueError("No participants found with the given criteria")

        # Extract relevant fields
        data = []
        for p in participants:
            row = {
                'participant_id': str(p['_id']),
                'campaign_id': p['campaign_id'],
                'email': p.get('email_address', ''),
                'opened': 1 if p.get('engagement', {}).get('opened', False) else 0,
                'clicked': 1 if p.get('engagement', {}).get('clicked', False) else 0,
            }

            # Extract custom fields
            fields = p.get('fields', {})
            row['first_name'] = fields.get('FirstName', '')
            row['last_name'] = fields.get('LastName', '')
            row['city'] = fields.get('City', '')
            row['zip'] = fields.get('ZIP', '')
            row['kwh'] = float(fields.get('kWh', -1))
            row['cell'] = fields.get('Cell', '')
            row['address'] = fields.get('Address', '')
            row['annual_cost'] = float(fields.get('annualcost', -1))
            row['annual_savings'] = float(fields.get('AnnualSavings', -1))

            data.append(row)

        df = pd.DataFrame(data)

        # Create campaign index
        df['campaign_idx'] = pd.Categorical(df['campaign_id']).codes

        # Create ZIP index (convert to string first to handle various formats)
        df['zip_str'] = df['zip'].astype(str).str[:5]  # Take first 5 digits
        df['zip_idx'] = pd.Categorical(df['zip_str']).codes

        return df

    def load_demographics(self) -> pd.DataFrame:
        """
        Load demographic data from county demographic collections.

        Returns:
            DataFrame with demographic data
        """
        # Get all county demographic collections from county database
        collections = [name for name in self.county_db.list_collection_names()
                      if 'CountyDemographic' in name]

        if not collections:
            raise ValueError("No demographic collections found")

        all_demographics = []
        for coll_name in collections:
            demographics = list(self.county_db[coll_name].find())
            all_demographics.extend(demographics)

        if not all_demographics:
            raise ValueError("No demographic data found")

        # Extract relevant fields
        data = []
        for d in all_demographics:
            row = {
                'parcel_id': d.get('parcel_id'),
                'address': d.get('address', ''),
                'energy_burden_gas': float(d.get('energy_burden_gas', -1)),
                'energy_burden_kwh': float(d.get('energy_burden_kwh', -1)),
                'annual_kwh_cost': float(d.get('annual_kwh_cost', -1)),
                'annual_gas_cost': float(d.get('annual_gas_cost', -1)),
                'total_energy_burden': float(d.get('total_energy_burden', -1)),
                'estimated_income': float(d.get('estimated_income', -1)),
                'income_level': float(d.get('income_level', -1)),
                'md_householdsize': float(d.get('md_householdsize', -1)),
                'has_mobile': 1 if d.get('mobile', -1) != -1 else 0,
                'parcel_zip': str(d.get('parcel_zip', '')),
                'service_city': d.get('service_city', ''),
            }
            data.append(row)

        return pd.DataFrame(data)

    def load_property_data(self) -> pd.DataFrame:
        """
        Load property characteristics from county residential collections.

        Returns:
            DataFrame with property data
        """
        collections = [name for name in self.county_db.list_collection_names()
                      if 'CountyResidential' in name]

        if not collections:
            raise ValueError("No residential collections found")

        all_residential = []
        for coll_name in collections:
            residential = list(self.county_db[coll_name].find())
            all_residential.extend(residential)

        if not all_residential:
            raise ValueError("No property data found")

        # Extract relevant fields
        data = []
        for r in all_residential:
            row = {
                'parcel_id': r.get('parcel_id'),
                'parcel_zip': str(r.get('parcel_zip', '')),
                'address': r.get('address', ''),
                'story_height': float(r.get('story_height', -1)),
                'age': float(r.get('age', -1)),
                'heat_type': r.get('heat_type', 'NA'),
                'living_area_total': float(r.get('living_area_total', -1)),
                'bedrooms': float(r.get('bedrooms', -1)),
                'census_tract': r.get('census_tract', 'NA'),
            }
            data.append(row)

        return pd.DataFrame(data)

    def merge_all_data(self, participants_df: pd.DataFrame,
                       demographics_df: pd.DataFrame,
                       property_df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge participant, demographic, and property data.

        Matching strategy:
        1. Try to match on address (normalized)
        2. Fall back to ZIP code matching for aggregated demographics

        Args:
            participants_df: Participant data with engagement outcomes
            demographics_df: Demographic data
            property_df: Property characteristics

        Returns:
            Merged DataFrame
        """
        # Normalize addresses for matching
        for df in [participants_df, demographics_df, property_df]:
            if 'address' in df.columns:
                df['address_normalized'] = (
                    df['address']
                    .str.upper()
                    .str.replace(r'[^A-Z0-9]', '', regex=True)
                )

        # First merge demographics with property on parcel_id
        demo_property = pd.merge(
            demographics_df,
            property_df,
            on='parcel_id',
            how='left',
            suffixes=('_demo', '_prop')
        )

        # Then merge with participants on normalized address
        merged = pd.merge(
            participants_df,
            demo_property,
            left_on='address_normalized',
            right_on='address_normalized',
            how='left',
            suffixes=('_part', '_demo')
        )

        # For rows that didn't match on address, try ZIP code
        unmatched_mask = merged['parcel_id'].isna()
        if unmatched_mask.sum() > 0:
            # Calculate ZIP-level averages for demographics
            zip_demographics = demographics_df.groupby('parcel_zip').agg({
                'total_energy_burden': 'mean',
                'estimated_income': 'mean',
                'income_level': 'mean',
                'md_householdsize': 'mean',
                'annual_kwh_cost': 'mean',
                'annual_gas_cost': 'mean',
            }).reset_index()

            # Merge ZIP-level averages for unmatched rows
            for idx in merged[unmatched_mask].index:
                zip_code = merged.loc[idx, 'zip_str']
                zip_data = zip_demographics[zip_demographics['parcel_zip'] == zip_code]
                if not zip_data.empty:
                    for col in zip_demographics.columns:
                        if col != 'parcel_zip':
                            merged.loc[idx, col] = zip_data.iloc[0][col]

        return merged

    def handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Handle missing values according to project conventions.

        Strategy:
        - -1 indicates missing for numeric fields
        - Replace -1 with median for continuous predictors
        - Create missing indicators for important features

        Args:
            df: DataFrame with potential missing values

        Returns:
            DataFrame with missing values handled
        """
        df = df.copy()

        # Continuous predictors to impute
        continuous_features = [
            'total_energy_burden', 'estimated_income', 'income_level',
            'md_householdsize', 'annual_kwh_cost', 'annual_gas_cost',
            'living_area_total', 'age', 'kwh', 'annual_cost', 'annual_savings'
        ]

        for feature in continuous_features:
            if feature in df.columns:
                # Create missing indicator
                df[f'{feature}_missing'] = (df[feature] == -1).astype(int)

                # Replace -1 with median of non-missing values
                valid_values = df[df[feature] != -1][feature]
                if len(valid_values) > 0:
                    median_value = valid_values.median()
                    df.loc[df[feature] == -1, feature] = median_value

        return df

    def scale_continuous_predictors(self, df: pd.DataFrame,
                                   features: List[str],
                                   fit: bool = True) -> pd.DataFrame:
        """
        Standardize continuous predictors (z-scores).

        Args:
            df: DataFrame with features to scale
            features: List of feature names to scale
            fit: Whether to fit the scaler (True for training, False for test)

        Returns:
            DataFrame with scaled features (suffixed with _scaled)
        """
        df = df.copy()

        # Only scale features that exist and aren't all missing
        features_to_scale = [f for f in features if f in df.columns]

        if fit:
            scaled_values = self.scaler.fit_transform(df[features_to_scale])
        else:
            scaled_values = self.scaler.transform(df[features_to_scale])

        # Add scaled features with _scaled suffix
        for i, feature in enumerate(features_to_scale):
            df[f'{feature}_scaled'] = scaled_values[:, i]

        return df

    def encode_categorical(self, df: pd.DataFrame,
                          feature: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Encode categorical variables.

        Args:
            df: DataFrame with categorical feature
            feature: Name of categorical feature

        Returns:
            Tuple of (DataFrame with encoded feature, encoding dictionary)
        """
        df = df.copy()

        if feature not in df.columns:
            return df, {}

        # Create categorical codes
        categories = pd.Categorical(df[feature])
        df[f'{feature}_encoded'] = categories.codes

        # Create encoding dictionary
        encoding = dict(enumerate(categories.categories))

        return df, encoding

    def prepare_model_data(self,
                          campaign_ids: Optional[List[str]] = None,
                          min_observations: int = 100) -> Tuple[pd.DataFrame, Dict]:
        """
        Complete data preparation pipeline for Bayesian modeling.

        Args:
            campaign_ids: Optional list of campaign IDs to include
            min_observations: Minimum required observations

        Returns:
            Tuple of (prepared DataFrame, metadata dictionary)
        """
        print("Loading participants...")
        participants = self.load_participants(campaign_ids)
        print(f"Loaded {len(participants)} participants")

        print("Loading demographics...")
        demographics = self.load_demographics()
        print(f"Loaded {len(demographics)} demographic records")

        print("Loading property data...")
        property_data = self.load_property_data()
        print(f"Loaded {len(property_data)} property records")

        print("Merging datasets...")
        merged = self.merge_all_data(participants, demographics, property_data)
        print(f"Merged dataset: {len(merged)} rows")

        print("Handling missing values...")
        merged = self.handle_missing_values(merged)

        print("Scaling continuous predictors...")
        continuous_features = [
            'total_energy_burden', 'estimated_income', 'income_level',
            'md_householdsize', 'annual_kwh_cost', 'annual_gas_cost',
            'living_area_total', 'age', 'kwh', 'annual_cost', 'annual_savings'
        ]
        merged = self.scale_continuous_predictors(merged, continuous_features)

        print("Encoding categorical variables...")
        merged, heat_type_encoding = self.encode_categorical(merged, 'heat_type')

        # Filter to rows with complete outcome data
        merged = merged[merged['opened'].notna()].copy()

        if len(merged) < min_observations:
            raise ValueError(
                f"Insufficient observations: {len(merged)} < {min_observations}"
            )

        # Prepare metadata
        metadata = {
            'n_observations': len(merged),
            'n_campaigns': merged['campaign_idx'].nunique(),
            'n_zips': merged['zip_idx'].nunique(),
            'open_rate': merged['opened'].mean(),
            'click_rate': merged['clicked'].mean(),
            'heat_type_encoding': heat_type_encoding,
            'continuous_features': continuous_features,
            'campaign_ids': merged['campaign_id'].unique().tolist(),
        }

        print("\nData preparation complete!")
        print(f"  Observations: {metadata['n_observations']}")
        print(f"  Campaigns: {metadata['n_campaigns']}")
        print(f"  ZIP codes: {metadata['n_zips']}")
        print(f"  Open rate: {metadata['open_rate']:.2%}")
        print(f"  Click rate: {metadata['click_rate']:.2%}")

        return merged, metadata


def get_model_matrices(df: pd.DataFrame,
                      model_spec: str = 'baseline') -> Dict[str, np.ndarray]:
    """
    Extract model matrices for specific model specifications.

    Args:
        df: Prepared DataFrame
        model_spec: Model specification ('baseline', 'energy_burden', 'demographics', etc.)

    Returns:
        Dictionary with model matrices (X features, y outcomes, indices)
    """
    matrices = {
        'y_opened': df['opened'].values,
        'y_clicked': df['clicked'].values,
        'campaign_idx': df['campaign_idx'].values,
        'zip_idx': df['zip_idx'].values,
    }

    if model_spec == 'baseline':
        matrices['annual_cost'] = df['annual_cost_scaled'].values
        matrices['annual_savings'] = df['annual_savings_scaled'].values

    elif model_spec == 'energy_burden':
        matrices['energy_burden'] = df['total_energy_burden_scaled'].values
        matrices['income_level'] = df['income_level_scaled'].values
        matrices['household_size'] = df['md_householdsize_scaled'].values

    elif model_spec == 'demographics':
        matrices['energy_burden'] = df['total_energy_burden_scaled'].values
        matrices['income_level'] = df['income_level_scaled'].values
        matrices['household_size'] = df['md_householdsize_scaled'].values
        matrices['has_mobile'] = df['has_mobile'].values
        matrices['estimated_income'] = df['estimated_income_scaled'].values

    elif model_spec == 'property':
        matrices['energy_burden'] = df['total_energy_burden_scaled'].values
        matrices['income_level'] = df['income_level_scaled'].values
        matrices['household_size'] = df['md_householdsize_scaled'].values
        matrices['has_mobile'] = df['has_mobile'].values
        matrices['living_area'] = df['living_area_total_scaled'].values
        matrices['age'] = df['age_scaled'].values
        matrices['heat_type'] = df['heat_type_encoded'].values

    else:
        raise ValueError(f"Unknown model specification: {model_spec}")

    return matrices
