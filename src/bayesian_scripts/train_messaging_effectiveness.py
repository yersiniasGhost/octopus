#!/usr/bin/env python
"""
Messaging Effectiveness Model Training Script
==============================================

Train the 2-stage hierarchical Bayesian model for email campaign effectiveness.

This model analyzes the email funnel:
- Stage 1: P(Open | features) - What drives email opens?
- Stage 2: P(Click | Open, features) - What drives clicks among openers?

Prerequisites:
    Run data preparation first:
    python src/bayesian_scripts_orig/prepare_messaging_data.py

Usage:
    python src/bayesian_scripts/train_messaging_effectiveness.py
    python src/bayesian_scripts/train_messaging_effectiveness.py --draws 3000 --chains 4
    python src/bayesian_scripts/train_messaging_effectiveness.py --full-data
    python src/bayesian_scripts/train_messaging_effectiveness.py --dry-run

Outputs are saved to: data/inference/messaging_effectiveness/
    - traces/    : MCMC trace files (.nc)
    - reports/   : Summary statistics, effect estimates
    - diagrams/  : Trace plots, forest plots, campaign rankings
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_models.messaging_effectiveness import MessagingEffectivenessModel
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Train the Messaging Effectiveness Model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Sampling parameters
    parser.add_argument("--draws", type=int, default=2000,
                        help="Number of posterior samples per chain")
    parser.add_argument("--tune", type=int, default=1000,
                        help="Number of tuning samples (discarded)")
    parser.add_argument("--chains", type=int, default=4,
                        help="Number of MCMC chains")
    parser.add_argument("--target-accept", type=float, default=0.95,
                        help="Target acceptance rate for NUTS sampler")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")

    # Data options
    parser.add_argument("--full-data", action="store_true",
                        help="Use full dataset instead of POC subset")
    parser.add_argument("--data-file", type=str, default=None,
                        help="Custom path to prepared data pickle file")

    # Run options
    parser.add_argument("--dry-run", action="store_true",
                        help="Load data and build model but don't train")
    parser.add_argument("--show-rankings", action="store_true",
                        help="Show campaign rankings after training")

    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 70)
    print("MESSAGING EFFECTIVENESS MODEL TRAINING")
    print("2-Stage Hierarchical Bayesian Model: Open → Click")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  Draws: {args.draws}")
    print(f"  Tune: {args.tune}")
    print(f"  Chains: {args.chains}")
    print(f"  Target Accept: {args.target_accept}")
    print(f"  Seed: {args.seed}")
    print(f"  Dataset: {'Full' if args.full_data else 'POC subset'}")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # STEP 1: Initialize Model
    # -------------------------------------------------------------------------
    print("STEP 1: Initializing Model")
    print("-" * 40)

    model = MessagingEffectivenessModel()
    print(f"Model: {model.metadata.name} (v{model.metadata.version})")
    print(f"Output directory: {model.output_dir}")

    # -------------------------------------------------------------------------
    # STEP 2: Load Data
    # -------------------------------------------------------------------------
    print("\nSTEP 2: Loading Data")
    print("-" * 40)

    try:
        data = model.load_data(
            data_file=args.data_file,
            use_full=args.full_data
        )
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        print("\nTo prepare the data, run:")
        print("  python src/bayesian_scripts_orig/prepare_messaging_data.py")
        if args.full_data:
            print("  python src/bayesian_scripts_orig/prepare_messaging_data.py --full")
        return None, None, None

    n_records = data['n_records']
    n_campaigns = data['n_campaigns']
    n_msg_types = data['n_msg_types']
    n_locations = data['n_locations']

    open_rate = data['opened'].mean()
    n_opened = data['opened'].sum()
    click_rate_given_open = data['clicked'][data['opened'] == 1].mean() if n_opened > 0 else 0

    print(f"\nData Summary:")
    print(f"  Total records: {n_records:,}")
    print(f"  Campaigns: {n_campaigns}")
    print(f"  Message types: {n_msg_types}")
    print(f"  Locations: {n_locations}")
    print(f"\nEngagement Metrics:")
    print(f"  Open rate: {open_rate:.2%} ({n_opened:,} opens)")
    print(f"  Click rate (given open): {click_rate_given_open:.2%}")
    print(f"  End-to-end conversion: {open_rate * click_rate_given_open:.2%}")

    # Show message type distribution
    msg_type_names = data.get('msg_type_names', {})
    if msg_type_names:
        print(f"\nMessage Types:")
        for idx, name in sorted(msg_type_names.items()):
            count = (data['msg_type_idx'] == idx).sum()
            print(f"  [{idx}] {name}: {count:,} records")

    if args.dry_run:
        print("\n[DRY RUN] Skipping training. Data loaded successfully.")
        print("\nModel would be built with:")
        print(f"  - {n_campaigns} campaign random effects (non-centered)")
        print(f"  - {n_msg_types} message type effects")
        print(f"  - {n_locations} location effects")
        print(f"  - 12 monthly effects")
        print(f"  - 3 offer characteristic effects (savings, cost, kwh)")
        return model, data, None

    # -------------------------------------------------------------------------
    # STEP 3: Train Model
    # -------------------------------------------------------------------------
    print("\nSTEP 3: Training Model")
    print("-" * 40)
    print("This may take several minutes...")

    results = model.train(
        data=data,
        draws=args.draws,
        tune=args.tune,
        chains=args.chains,
        target_accept=args.target_accept,
        random_seed=args.seed
    )

    # -------------------------------------------------------------------------
    # STEP 4: Display Results
    # -------------------------------------------------------------------------
    print("\nSTEP 4: Results Summary")
    print("-" * 40)

    print("\nDiagnostics:")
    diag = results['diagnostics']
    print(f"  R-hat (max): {diag['r_hat_max']:.4f} {'[OK]' if diag['r_hat_max'] < 1.01 else '[WARN]'}")
    print(f"  ESS bulk (min): {diag['ess_bulk_min']:.0f} {'[OK]' if diag['ess_bulk_min'] > 400 else '[WARN]'}")
    print(f"  ESS tail (min): {diag['ess_tail_min']:.0f} {'[OK]' if diag['ess_tail_min'] > 400 else '[WARN]'}")
    print(f"  Divergences: {diag['divergences']} {'[OK]' if diag['divergences'] == 0 else '[WARN]'}")

    print("\nOpen Rate Model Effects:")
    open_effects = results['effects'].get('open', {})
    print(f"  Population intercept: {open_effects.get('population_intercept', {}).get('mean', 'N/A'):.3f}")
    print(f"  Between-campaign SD: {open_effects.get('between_campaign_sd', {}).get('mean', 'N/A'):.3f}")
    print(f"  Savings effect: {open_effects.get('savings_effect', {}).get('mean', 'N/A'):.3f}")
    print(f"  Cost effect: {open_effects.get('cost_effect', {}).get('mean', 'N/A'):.3f}")
    print(f"  kWh effect: {open_effects.get('kwh_effect', {}).get('mean', 'N/A'):.3f}")

    if 'click' in results['effects']:
        print("\nClick Rate Model Effects (conditional on open):")
        click_effects = results['effects']['click']
        print(f"  Population intercept: {click_effects.get('population_intercept', {}).get('mean', 'N/A'):.3f}")
        print(f"  Between-campaign SD: {click_effects.get('between_campaign_sd', {}).get('mean', 'N/A'):.3f}")
        print(f"  Savings effect: {click_effects.get('savings_effect', {}).get('mean', 'N/A'):.3f}")
        print(f"  Cost effect: {click_effects.get('cost_effect', {}).get('mean', 'N/A'):.3f}")
        print(f"  kWh effect: {click_effects.get('kwh_effect', {}).get('mean', 'N/A'):.3f}")

    # Message type effects
    if 'message_types_open' in results['effects']:
        print("\nMessage Type Effects on Open Rate (odds ratios):")
        for msg_type, effect in results['effects']['message_types_open'].items():
            or_val = effect.get('odds_ratio', 1.0)
            effect_pct = (or_val - 1) * 100
            sign = '+' if effect_pct >= 0 else ''
            print(f"  {msg_type}: OR={or_val:.3f} ({sign}{effect_pct:.1f}%)")

    # -------------------------------------------------------------------------
    # STEP 5: Campaign Rankings (optional)
    # -------------------------------------------------------------------------
    if args.show_rankings:
        print("\nSTEP 5: Top Campaign Rankings")
        print("-" * 40)

        rankings = model.get_campaign_rankings(metric='open_rate', top_n=10)
        if 'rankings' in rankings:
            print("\nTop 10 Campaigns by Open Rate:")
            for r in rankings['rankings']:
                print(f"  {r['rank']:2d}. {r['campaign_id'][:40]:40s} "
                      f"{r['mean']:.2%} [{r['hdi_lower']:.2%}, {r['hdi_upper']:.2%}]")

    # -------------------------------------------------------------------------
    # STEP 6: Show Output Locations
    # -------------------------------------------------------------------------
    print("\nSTEP 6: Saved Artifacts")
    print("-" * 40)

    for name, path in model.get_output_paths().items():
        if path.exists():
            files = list(path.glob('*'))
            if files:
                print(f"\n{name}/:")
                for f in sorted(files)[-5:]:  # Show last 5 files
                    size = f.stat().st_size if f.is_file() else 0
                    size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
                    print(f"  - {f.name} ({size_str})")

    # -------------------------------------------------------------------------
    # Done
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print(f"Model artifacts saved to: {model.output_dir}")
    print("=" * 70)

    return model, data, results


if __name__ == "__main__":
    model, data, results = main()
