#!/usr/bin/env python3
"""
Generate Data Summary for Bayesian Models

This script generates data ingestion summaries for trained Bayesian models.
It reads training data using each model's data loader and creates a summary
showing participant counts, campaigns, counties, and missing data.

Usage:
    python scripts/generate_data_summary.py --model model_04_campaign_effects
    python scripts/generate_data_summary.py --all
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.log_manager import LogManager
from src.bayesian_models.data_summary import (
    DataIngestionSummary, CountySummary, CampaignSummary, MissingDataSummary
)
from src.bayesian_models.base_model import MODELS_OUTPUT_DIR
from src.bayesian_models.model_registry import get_registry

logger = LogManager().get_logger(__name__)


def generate_summary_for_click_model_02() -> DataIngestionSummary:
    """Generate data summary for click_model_02."""
    from src.bayesian_models.click_model_02.model_data import (
        load_data, get_mongo_client, load_demographic_index, load_residential_index
    )

    # Get diagnostic info for missing data
    client, db_name = get_mongo_client()
    db = client[db_name]

    demo_by_email = load_demographic_index(db, verbose=False)
    res_by_parcel = load_residential_index(db, verbose=False)

    # Load the actual data
    data = load_data(verbose=False)

    # Calculate stats
    unique_counties = set(data.county) if data.county is not None else set()

    # County breakdown
    counties = []
    if data.county is not None:
        import pandas as pd
        df = pd.DataFrame({'county': data.county, 'click': data.click})
        county_stats = df.groupby('county').agg({
            'click': ['count', 'sum', 'mean']
        })
        for county_name in county_stats.index:
            stats = county_stats.loc[county_name]
            counties.append(CountySummary(
                name=county_name,
                participant_count=int(stats[('click', 'count')]),
                click_count=int(stats[('click', 'sum')]),
                click_rate=float(stats[('click', 'mean')])
            ))

    # Count missing data
    participants_coll = db['participants']
    total_participant_records = participants_coll.count_documents({'campaign_id': {'$exists': True}})

    # Estimate missing data
    missing = MissingDataSummary(
        participants_no_county=0,  # We filter these out during loading
        participants_no_demographics=total_participant_records - len(demo_by_email),
        participants_no_income=0,  # Handled in loader
        participants_no_energy_burden=0,  # Handled in loader
    )

    client.close()

    summary = DataIngestionSummary(
        total_participants=data.n_contacts,
        total_observations=data.n_contacts,  # One obs per participant
        total_campaigns=1,  # Aggregated across campaigns
        total_counties=len(unique_counties),
        click_count=int(data.click.sum()),
        overall_click_rate=float(data.click_rate),
        counties=counties,
        campaigns=[],  # Aggregated
        missing_data=missing,
        model_id='click_model_02',
        data_sources=['participants', 'demographics', 'residential'],
    )

    return summary


def generate_summary_for_model_04() -> DataIngestionSummary:
    """Generate data summary for model_04_campaign_effects.

    Loads data directly from MongoDB to get accurate counts, then
    augments with model-processed data for treatment summaries.
    """
    from src.bayesian_models.model_04_campaign_effects.model import (
        CampaignTreatmentEffectsModel, MESSAGE_TYPES
    )
    from src.tools.mongo import get_campaign_db
    import numpy as np
    import pandas as pd

    db = get_campaign_db()

    # Load campaigns with message_types directly from DB
    logger.info("Loading campaigns from database...")
    campaigns_cursor = db.campaigns.find(
        {'message_types': {'$exists': True, '$ne': []}},
        {'campaign_id': 1, 'message_types': 1, 'name': 1}
    )
    campaign_data = {c['campaign_id']: c for c in campaigns_cursor}
    logger.info(f"Found {len(campaign_data)} campaigns with message_types")

    # Now load the model to get processed training data
    model = CampaignTreatmentEffectsModel()
    data = model.load_data()

    if data is None:
        raise ValueError("Could not load data for model_04_campaign_effects")

    # data is a dict with arrays - note y_clicked is the key
    clicked = data['y_clicked']
    county_idx = data.get('county_idx', np.array([]))

    # Build county summaries using model's county mapping
    counties = []
    county_mapping = getattr(model, '_county_mapping', None)
    if county_mapping and len(county_idx) > 0:
        df = pd.DataFrame({'county_idx': county_idx, 'clicked': clicked})
        idx_to_county = {v: k for k, v in county_mapping.items()}

        for cidx in np.unique(county_idx):
            county_name = idx_to_county.get(cidx, f"county_{cidx}")
            mask = df['county_idx'] == cidx

            counties.append(CountySummary(
                name=county_name,
                participant_count=int(mask.sum()),
                click_count=int(df.loc[mask, 'clicked'].sum()),
                click_rate=float(df.loc[mask, 'clicked'].mean())
            ))

    # Build campaign summaries from database data
    # Count exposures per campaign from exposures collection
    logger.info("Counting campaign exposures...")
    pipeline = [
        {'$match': {'campaign_id': {'$in': list(campaign_data.keys())}}},
        {'$group': {
            '_id': '$campaign_id',
            'exposure_count': {'$sum': 1},
            'click_count': {'$sum': {'$cond': ['$email_clicked', 1, 0]}}
        }}
    ]
    exposure_stats = {doc['_id']: doc for doc in db.exposures.aggregate(pipeline)}

    campaigns = []
    for campaign_id, cdata in campaign_data.items():
        stats = exposure_stats.get(campaign_id, {'exposure_count': 0, 'click_count': 0})
        exp_count = stats['exposure_count']
        clk_count = stats['click_count']

        campaigns.append(CampaignSummary(
            campaign_id=campaign_id,
            name=cdata.get('name'),
            exposure_count=exp_count,
            click_count=clk_count,
            click_rate=float(clk_count / exp_count) if exp_count > 0 else 0.0,
            message_types=cdata.get('message_types', [])
        ))

    # Count missing data from database
    total_participants = db.participants.count_documents({})
    participants_with_county = db.participants.count_documents(
        {'linkage.county_key': {'$exists': True}}
    )
    participants_with_demographics = db.participants.count_documents(
        {'demographics.income_level': {'$type': 'number'}}
    )

    missing = MissingDataSummary(
        participants_no_county=total_participants - participants_with_county,
        participants_no_demographics=total_participants - participants_with_demographics,
        participants_no_income=0,
        participants_no_energy_burden=0,
    )

    # Treatment summary for message types (keys are has_{mt_name})
    treatment_summary = {}
    for mt_name in MESSAGE_TYPES:
        key = f'has_{mt_name}'
        if key in data:
            mt_arr = data[key]
            treated = mt_arr == 1
            treatment_summary[mt_name] = {
                'treated_count': int(np.sum(treated)),
                'control_count': int(np.sum(~treated)),
                'treated_click_rate': float(np.mean(clicked[treated])) if np.sum(treated) > 0 else 0,
                'control_click_rate': float(np.mean(clicked[~treated])) if np.sum(~treated) > 0 else 0,
            }

    # Get unique participant count - this is participants WITH demographics
    # that actually made it into the training data (1806 per model logs)
    # The scaler_params doesn't store this, so we count from participant lookup
    participant_lookup_count = db.participants.count_documents({
        'linkage.county_key': {'$exists': True},
        'demographics.income_level': {'$type': 'number'}
    })
    n_participants = participant_lookup_count

    summary = DataIngestionSummary(
        total_participants=n_participants,
        total_observations=len(clicked),
        total_campaigns=len(campaign_data),
        total_counties=len(counties),
        click_count=int(clicked.sum()),
        overall_click_rate=float(clicked.mean()),
        counties=counties,
        campaigns=campaigns,
        missing_data=missing,
        model_id='model_04_campaign_effects',
        data_sources=['participants', 'exposures', 'campaigns'],
        treatment_summary=treatment_summary
    )

    return summary


def generate_summary_for_model_03() -> DataIngestionSummary:
    """Generate data summary for model_03_demographics."""
    try:
        from src.bayesian_models.model_03_demographics.model import DemographicsClickRateModel
        model = DemographicsClickRateModel()
        data = model.load_data()
    except ImportError:
        logger.warning("model_03_demographics not found or cannot be loaded")
        return None

    if data is None:
        return None

    import numpy as np
    import pandas as pd

    # Get unique counties from county array
    counties = []
    if hasattr(data, 'county') and data.county is not None:
        unique_counties = np.unique(data.county)
        df = pd.DataFrame({'county': data.county, 'click': data.clicked})

        for county_name in unique_counties:
            mask = df['county'] == county_name
            counties.append(CountySummary(
                name=county_name,
                participant_count=int(mask.sum()),
                click_count=int(df.loc[mask, 'click'].sum()),
                click_rate=float(df.loc[mask, 'click'].mean())
            ))

    missing = MissingDataSummary()

    summary = DataIngestionSummary(
        total_participants=len(data.clicked),
        total_observations=len(data.clicked),
        total_campaigns=0,
        total_counties=len(counties),
        click_count=int(data.clicked.sum()),
        overall_click_rate=float(data.clicked.mean()),
        counties=counties,
        campaigns=[],
        missing_data=missing,
        model_id='model_03_demographics',
        data_sources=['participants', 'demographics'],
    )

    return summary


MODEL_GENERATORS = {
    'click_model_02': generate_summary_for_click_model_02,
    'model_03_demographics': generate_summary_for_model_03,
    'model_04_campaign_effects': generate_summary_for_model_04,
}


def generate_and_save_summary(model_id: str) -> Optional[Path]:
    """Generate and save data summary for a specific model."""

    if model_id not in MODEL_GENERATORS:
        logger.warning(f"No summary generator for model: {model_id}")
        return None

    try:
        logger.info(f"Generating data summary for {model_id}...")
        summary = MODEL_GENERATORS[model_id]()

        if summary is None:
            logger.warning(f"Could not generate summary for {model_id}")
            return None

        # Save to model's reports directory
        output_dir = MODELS_OUTPUT_DIR / model_id / 'reports'
        output_path = summary.save(output_dir)

        logger.info(f"Data summary saved: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error generating summary for {model_id}: {e}", exc_info=True)
        return None


def main():
    parser = argparse.ArgumentParser(description="Generate data summaries for Bayesian models")
    parser.add_argument('--model', '-m', type=str, help="Model ID to generate summary for")
    parser.add_argument('--all', '-a', action='store_true', help="Generate summaries for all models")
    parser.add_argument('--list', '-l', action='store_true', help="List available models")

    args = parser.parse_args()

    if args.list:
        print("Available models with summary generators:")
        for model_id in MODEL_GENERATORS.keys():
            print(f"  - {model_id}")
        return

    if args.all:
        for model_id in MODEL_GENERATORS.keys():
            generate_and_save_summary(model_id)
    elif args.model:
        generate_and_save_summary(args.model)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
