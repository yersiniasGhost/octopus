#!/usr/bin/env python3
"""
Phase 1A: Messaging Campaign Data Preparation

Loads, cleans, and preprocesses campaign data for Bayesian messaging effectiveness model.
Selects 10-20 representative campaigns for proof of concept.

Created: 2025-10-15
"""

import pandas as pd
import numpy as np
from pathlib import Path
import re
from typing import Dict, List, Tuple
import pickle


# === CONFIGURATION ===

DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'exports'
OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'processed'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Campaign selection criteria
POC_CAMPAIGN_COUNT = 15  # Target number of campaigns for POC (Phase 1A/1B)
MIN_RECORDS_PER_CAMPAIGN = 30  # Minimum contacts per campaign


# === MESSAGE TYPE CATEGORIZATION ===

MESSAGE_TYPE_PATTERNS = {
    'cost_framing': [
        'Daily_Cost', 'DailyCost', 'Monthly_Cost', 'Annual_Cost'
    ],
    'savings_framing': [
        'Monthly_Savings', 'Monthly_Saving', 'Would_$_Per_Month'
    ],
    'urgency': [
        'Summer_Surge', 'Summer_Crisis', 'SummerCrisis',
        'Crisis', 'FinalDays', 'Final_Days'
    ],
    'personalization': [
        'Your_Home_Selected', 'Claude_Content'
    ],
    'improvement': [
        'Improve'
    ],
    'event': [
        'Webinar'
    ]
}


def extract_message_type(campaign_name: str) -> str:
    """
    Extract message type category from campaign name.

    Examples:
        'MVCAP_Daily_Cost_20250514' -> 'cost_framing'
        'OHCAC_Summer_Crisis_20250708' -> 'urgency'
    """
    for msg_type, patterns in MESSAGE_TYPE_PATTERNS.items():
        for pattern in patterns:
            if pattern in campaign_name:
                return msg_type

    # Default to 'other' if no pattern matches
    return 'other'


def extract_utility(campaign_name: str) -> str:
    """
    Extract utility company from campaign name.

    Examples:
        'MVCAP_Daily_Cost_20250514' -> 'MVCAP'
        'IMPACT_Summer_Surge_20250610' -> 'IMPACT'
    """
    parts = campaign_name.split('_')
    if len(parts) > 0:
        return parts[0]
    return 'unknown'


def extract_campaign_date(campaign_name: str) -> pd.Timestamp:
    """
    Extract campaign send date from filename.

    Example:
        'enriched_campaign_..._MVCAP_Daily_Cost_20250514.csv' -> 2025-05-14
    """
    date_pattern = r'(\d{8})'
    match = re.search(date_pattern, campaign_name)

    if match:
        date_str = match.group(1)
        return pd.to_datetime(date_str, format='%Y%m%d')

    return pd.NaT


def load_campaign_data(campaign_file: Path) -> pd.DataFrame:
    """
    Load and perform basic cleaning on single campaign file.

    Handles data from data/exports/ with Yes/No format for engagement fields.
    """
    df = pd.read_csv(campaign_file)

    # Convert Yes/No strings to binary (1/0)
    for col in ['opened', 'clicked', 'bounced', 'complained', 'unsubscribed']:
        if col in df.columns:
            df[col] = (df[col] == 'Yes').astype(int)

    # Extract metadata from filename
    campaign_id = campaign_file.stem
    df['campaign_id'] = campaign_id
    df['campaign_file'] = campaign_file.name

    # Parse campaign name components
    if 'campaign_name' in df.columns and len(df) > 0:
        df['message_type'] = extract_message_type(df['campaign_name'].iloc[0])
        df['utility'] = extract_utility(df['campaign_name'].iloc[0])
    else:
        df['message_type'] = 'other'
        df['utility'] = 'unknown'

    df['campaign_date'] = extract_campaign_date(campaign_file.name)

    # Extract temporal features
    if pd.notna(df['campaign_date'].iloc[0]):
        df['campaign_month'] = df['campaign_date'].dt.month
        df['campaign_day_of_week'] = df['campaign_date'].dt.dayofweek
    else:
        df['campaign_month'] = np.nan
        df['campaign_day_of_week'] = np.nan

    return df


def compute_campaign_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute performance statistics for each campaign.
    """
    # Ensure message_type and utility exist
    if 'message_type' not in df.columns:
        df['message_type'] = 'other'
    if 'utility' not in df.columns:
        df['utility'] = 'unknown'

    stats = df.groupby('campaign_id').agg({
        'email': 'count',
        'opened': ['sum', 'mean'],
        'clicked': ['sum', 'mean'],
        'bounced': 'sum',
        'complained': 'sum',
        'unsubscribed': 'sum',
        'message_type': 'first',
        'utility': 'first',
        'campaign_date': 'first'
    }).reset_index()

    # Flatten column names
    stats.columns = ['_'.join(col).strip('_') if col[1] else col[0]
                     for col in stats.columns.values]

    # Rename for clarity
    stats = stats.rename(columns={
        'email_count': 'n_sent',
        'opened_sum': 'n_opened',
        'opened_mean': 'open_rate',
        'clicked_sum': 'n_clicked',
        'clicked_mean': 'click_rate_overall',
        'message_type_first': 'message_type',
        'utility_first': 'utility',
        'campaign_date_first': 'campaign_date'
    })

    # Click rate conditional on opened
    opened_df = df[df['opened'] == 1]
    click_given_open = opened_df.groupby('campaign_id')['clicked'].mean()
    stats = stats.merge(
        click_given_open.rename('click_rate_given_open'),
        left_on='campaign_id',
        right_index=True,
        how='left'
    )

    # End-to-end conversion
    stats['conversion_rate'] = stats['open_rate'] * stats['click_rate_given_open']

    return stats


def select_poc_campaigns(
    stats: pd.DataFrame,
    n_campaigns: int = POC_CAMPAIGN_COUNT,
    min_records: int = MIN_RECORDS_PER_CAMPAIGN
) -> List[str]:
    """
    Select diverse set of campaigns for POC.

    Selection criteria:
    1. Message type diversity (at least 1 from each type)
    2. Sample size (>= min_records)
    3. Performance variation (mix of high/med/low)
    4. Temporal spread (different months)
    """

    # Filter by minimum sample size
    eligible = stats[stats['n_sent'] >= min_records].copy()

    print(f"Total campaigns: {len(stats)}")
    print(f"Eligible campaigns (>= {min_records} records): {len(eligible)}")

    # Message type distribution
    print("\nMessage type distribution:")
    print(eligible['message_type'].value_counts())

    # Stratified sampling: ensure message type diversity
    selected = []

    for msg_type in eligible['message_type'].unique():
        type_campaigns = eligible[eligible['message_type'] == msg_type]

        # Sort by performance to get diversity
        type_campaigns = type_campaigns.sort_values('open_rate')

        # Select 1-3 campaigns per type (depending on total target)
        n_select = min(3, max(1, len(type_campaigns)))

        # Take top, middle, bottom performers
        if len(type_campaigns) >= 3:
            indices = [0, len(type_campaigns) // 2, len(type_campaigns) - 1]
            sampled = type_campaigns.iloc[indices[:n_select]]
        else:
            sampled = type_campaigns.head(n_select)

        selected.append(sampled)

    selected_df = pd.concat(selected)

    # If we don't have enough, add more top performers
    if len(selected_df) < n_campaigns:
        remaining = n_campaigns - len(selected_df)
        extra = eligible[~eligible['campaign_id'].isin(selected_df['campaign_id'])]
        extra = extra.nlargest(remaining, 'conversion_rate')
        selected_df = pd.concat([selected_df, extra])

    # Trim to exact target if overshot
    if len(selected_df) > n_campaigns:
        selected_df = selected_df.head(n_campaigns)

    return selected_df['campaign_id'].tolist()


def prepare_model_data(df: pd.DataFrame) -> Dict:
    """
    Prepare data for Bayesian model.

    Returns dictionary with:
    - Data arrays (standardized)
    - Indexing arrays (campaign, location, message type)
    - Metadata
    """

    # Filter valid records (exclude bounced)
    df = df[df['bounced'] == 0].copy()

    # Create integer indices
    campaign_lookup = {c: i for i, c in enumerate(df['campaign_id'].unique())}
    df['campaign_idx'] = df['campaign_id'].map(campaign_lookup)

    # Message type indexing
    msg_type_lookup = {t: i for i, t in enumerate(sorted(df['message_type'].unique()))}
    df['msg_type_idx'] = df['message_type'].map(msg_type_lookup)

    # Location indexing (use city if available, else zip)
    df['location'] = df['city'].fillna(df['zip'].astype(str))
    location_lookup = {loc: i for i, loc in enumerate(df['location'].unique())}
    df['location_idx'] = df['location'].map(location_lookup)

    # Handle missing numerical features
    numerical_features = ['annual_savings', 'monthly_cost', 'monthly_saving',
                          'daily_cost', 'kwh']

    for feat in numerical_features:
        if feat in df.columns:
            # Clean currency formatting (remove $, commas)
            if df[feat].dtype == 'object':
                df[feat] = df[feat].astype(str).str.replace('$', '', regex=False)
                df[feat] = df[feat].str.replace(',', '', regex=False)
                df[feat] = pd.to_numeric(df[feat], errors='coerce')

            # Fill missing with median
            median_val = df[feat].median()
            if pd.notna(median_val):
                df[feat] = df[feat].fillna(median_val)
            else:
                df[feat] = df[feat].fillna(0.0)
        else:
            # Create dummy column if not present
            df[feat] = 0.0

    # Standardize numerical features
    standardized = {}
    for feat in numerical_features:
        mean_val = df[feat].mean()
        std_val = df[feat].std()

        if std_val > 0:
            df[f'{feat}_std'] = (df[feat] - mean_val) / std_val
        else:
            df[f'{feat}_std'] = 0.0

        standardized[feat] = {'mean': mean_val, 'std': std_val}

    # Prepare output dictionary
    data_dict = {
        # Dimensions
        'n_records': len(df),
        'n_campaigns': df['campaign_idx'].nunique(),
        'n_msg_types': df['msg_type_idx'].nunique(),
        'n_locations': df['location_idx'].nunique(),

        # Indexing arrays
        'campaign_idx': df['campaign_idx'].values,
        'msg_type_idx': df['msg_type_idx'].values,
        'location_idx': df['location_idx'].values,
        'month_idx': df['campaign_month'].fillna(6).astype(int).values - 1,  # 0-indexed

        # Outcome variables
        'opened': df['opened'].values.astype(int),
        'clicked': df['clicked'].values.astype(int),

        # Features (standardized)
        'savings_std': df['annual_savings_std'].values,
        'monthly_cost_std': df['monthly_cost_std'].values,
        'kwh_std': df['kwh_std'].values,

        # Lookups
        'campaign_lookup': campaign_lookup,
        'msg_type_lookup': msg_type_lookup,
        'location_lookup': location_lookup,

        # Reverse lookups
        'campaign_names': {v: k for k, v in campaign_lookup.items()},
        'msg_type_names': {v: k for k, v in msg_type_lookup.items()},
        'location_names': {v: k for k, v in location_lookup.items()},

        # Standardization parameters
        'standardization': standardized,

        # Raw dataframe (for validation)
        'df': df
    }

    return data_dict


def create_train_val_split(
    data_dict: Dict,
    val_fraction: float = 0.2,
    random_seed: int = 42
) -> Tuple[Dict, Dict]:
    """
    Create train/validation split stratified by campaign.
    """
    np.random.seed(random_seed)

    df = data_dict['df']
    n_total = len(df)
    n_val = int(n_total * val_fraction)

    # Stratified split by campaign
    val_indices = []
    for campaign_id in df['campaign_id'].unique():
        campaign_df = df[df['campaign_id'] == campaign_id]
        n_campaign_val = max(1, int(len(campaign_df) * val_fraction))

        campaign_val_idx = np.random.choice(
            campaign_df.index,
            size=n_campaign_val,
            replace=False
        )
        val_indices.extend(campaign_val_idx)

    train_indices = [i for i in df.index if i not in val_indices]

    # Create train and validation data dicts
    train_df = df.loc[train_indices].reset_index(drop=True)
    val_df = df.loc[val_indices].reset_index(drop=True)

    train_dict = prepare_model_data(train_df)
    val_dict = prepare_model_data(val_df)

    print(f"\nTrain/Val Split:")
    print(f"  Train: {len(train_df)} records ({len(train_df)/len(df)*100:.1f}%)")
    print(f"  Val: {len(val_df)} records ({len(val_df)/len(df)*100:.1f}%)")

    return train_dict, val_dict


def main():
    """
    Main data preparation pipeline.
    """

    import sys
    phase = "1C (FULL-SCALE)" if ('--full' in sys.argv or '--phase1c' in sys.argv) else "1A (POC)"

    print("="*60)
    print(f"PHASE {phase}: MESSAGING DATA PREPARATION")
    print("="*60)

    # === STEP 1: Load all campaigns ===
    print("\n[1] Loading campaign data...")

    # Look for campaign files in exports directory
    campaign_files = sorted(DATA_DIR.glob('*.csv'))
    print(f"Found {len(campaign_files)} campaign files in {DATA_DIR}")

    campaigns = []
    for f in campaign_files:
        try:
            df = load_campaign_data(f)
            campaigns.append(df)
        except Exception as e:
            print(f"  ⚠️  Failed to load {f.name}: {e}")

    all_data = pd.concat(campaigns, ignore_index=True)
    print(f"Total records loaded: {len(all_data):,}")

    # === STEP 2: Compute campaign statistics ===
    print("\n[2] Computing campaign statistics...")

    stats = compute_campaign_stats(all_data)
    print(f"\nOverall Statistics:")
    print(f"  Campaigns: {len(stats)}")
    print(f"  Total sent: {stats['n_sent'].sum():,}")
    print(f"  Avg open rate: {stats['open_rate'].mean():.1%}")
    print(f"  Avg click rate (given open): {stats['click_rate_given_open'].mean():.1%}")
    print(f"  Avg conversion rate: {stats['conversion_rate'].mean():.1%}")

    # Save campaign statistics
    stats_file = OUTPUT_DIR / 'campaign_statistics.csv'
    stats.to_csv(stats_file, index=False)
    print(f"\n✅ Campaign statistics saved to {stats_file}")

    # === STEP 3: Select campaigns (POC or FULL) ===
    # For Phase 1C, use ALL campaigns instead of POC subset
    import sys
    use_all_campaigns = '--full' in sys.argv or '--phase1c' in sys.argv

    if use_all_campaigns:
        print(f"\n[3] Using ALL campaigns (Phase 1C full-scale analysis)...")
        # Filter by minimum sample size only
        min_records = 30
        selected_campaigns = stats[stats['n_sent'] >= min_records]['campaign_id'].tolist()
        print(f"\n✅ Selected {len(selected_campaigns)} campaigns (>= {min_records} records each)")
    else:
        print(f"\n[3] Selecting {POC_CAMPAIGN_COUNT} campaigns for POC...")
        selected_campaigns = select_poc_campaigns(stats)
        print(f"\n✅ Selected {len(selected_campaigns)} campaigns:")

    selected_stats = stats[stats['campaign_id'].isin(selected_campaigns)]
    print(selected_stats[['campaign_id', 'message_type', 'n_sent',
                          'open_rate', 'click_rate_given_open',
                          'conversion_rate']].to_string(index=False))

    # === STEP 4: Prepare model data ===
    print("\n[4] Preparing model data...")

    poc_data = all_data[all_data['campaign_id'].isin(selected_campaigns)].copy()

    # Prepare full dataset
    model_data = prepare_model_data(poc_data)

    print(f"\nModel Data Summary:")
    print(f"  Records: {model_data['n_records']:,}")
    print(f"  Campaigns: {model_data['n_campaigns']}")
    print(f"  Message types: {model_data['n_msg_types']}")
    print(f"  Locations: {model_data['n_locations']}")
    print(f"\n  Opened: {model_data['opened'].sum()} / {len(model_data['opened'])} "
          f"({model_data['opened'].mean():.1%})")
    print(f"  Clicked (of opened): {model_data['clicked'][model_data['opened']==1].sum()} / "
          f"{model_data['opened'].sum()} "
          f"({model_data['clicked'][model_data['opened']==1].mean():.1%})")

    # === STEP 5: Create train/val split ===
    print("\n[5] Creating train/validation split...")

    train_data, val_data = create_train_val_split(model_data)

    # === STEP 6: Save prepared data ===
    print("\n[6] Saving prepared data...")

    # Save with appropriate naming
    dataset_type = 'full' if use_all_campaigns else 'poc'

    # Full dataset
    full_file = OUTPUT_DIR / f'messaging_{dataset_type}_data.pkl'
    with open(full_file, 'wb') as f:
        pickle.dump(model_data, f)
    print(f"  ✅ Full data: {full_file}")

    # Train data
    train_file = OUTPUT_DIR / f'messaging_{dataset_type}_train_data.pkl'
    with open(train_file, 'wb') as f:
        pickle.dump(train_data, f)
    print(f"  ✅ Train data: {train_file}")

    # Val data
    val_file = OUTPUT_DIR / f'messaging_{dataset_type}_val_data.pkl'
    with open(val_file, 'wb') as f:
        pickle.dump(val_data, f)
    print(f"  ✅ Val data: {val_file}")

    # Campaign selection list
    selection_file = OUTPUT_DIR / 'poc_campaign_selection.txt'
    with open(selection_file, 'w') as f:
        f.write("Phase 1 POC Campaign Selection\n")
        f.write("="*60 + "\n\n")
        for campaign_id in selected_campaigns:
            f.write(f"{campaign_id}\n")
    print(f"  ✅ Campaign list: {selection_file}")

    print("\n" + "="*60)
    print("✅ DATA PREPARATION COMPLETE")
    print("="*60)
    print(f"\nNext step: Train model with GPU acceleration")
    print(f"  python src/bayesian_scripts/train_messaging_model.py")


if __name__ == '__main__':
    main()
