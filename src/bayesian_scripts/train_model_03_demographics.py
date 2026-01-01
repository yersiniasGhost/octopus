#!/usr/bin/env python
"""
Model 03 Demographics Training Script
======================================

Train the Demographics Email Open Model using the registry-based architecture.

This model tests the hypothesis: does electricity cost (kWh $) predict email
open rates, controlling for energy burden, income level, and household size?

Usage:
    python src/bayesian_scripts/train_model_03_demographics.py
    python src/bayesian_scripts/train_model_03_demographics.py --draws 3000 --chains 4
    python src/bayesian_scripts/train_model_03_demographics.py --dry-run

Outputs are saved to: data/inference/model_03_demographics/
    - traces/    : MCMC trace files (.nc)
    - reports/   : Summary statistics, metrics, hypothesis results
    - diagrams/  : DAG, posterior plots, trace plots, forest plots
    - checkpoints/ : Scaler parameters for inference
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_models.model_03_demographics import DemographicsOpenModel
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Train the Demographics Email Open Model",
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
    parser.add_argument("--collection", type=str, default="participants",
                        help="MongoDB collection to load data from")

    # Run options
    parser.add_argument("--dry-run", action="store_true",
                        help="Load data and build model but don't train")

    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 70)
    print("MODEL 03 DEMOGRAPHICS - EMAIL OPEN MODEL TRAINING")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  Draws: {args.draws}")
    print(f"  Tune: {args.tune}")
    print(f"  Chains: {args.chains}")
    print(f"  Target Accept: {args.target_accept}")
    print(f"  Seed: {args.seed}")
    print(f"  Collection: {args.collection}")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # STEP 1: Initialize Model
    # -------------------------------------------------------------------------
    print("STEP 1: Initializing Model")
    print("-" * 40)

    model = DemographicsOpenModel()
    print(f"Model: {model.metadata.name} (v{model.metadata.version})")
    print(f"Output directory: {model.output_dir}")

    # -------------------------------------------------------------------------
    # STEP 2: Load Data
    # -------------------------------------------------------------------------
    print("\nSTEP 2: Loading Data")
    print("-" * 40)

    data = model.load_data(collection=args.collection)
    n_obs = len(data['y_opened'])
    open_rate = data['y_opened'].mean()

    print(f"Loaded {n_obs} observations")
    print(f"Open rate: {open_rate:.2%}")
    print(f"Energy burden range (scaled): [{data['energy_burden'].min():.2f}, {data['energy_burden'].max():.2f}]")
    print(f"Income level range (scaled): [{data['income_level'].min():.2f}, {data['income_level'].max():.2f}]")
    print(f"Household size range (scaled): [{data['household_size'].min():.2f}, {data['household_size'].max():.2f}]")
    print(f"kWh cost range (scaled): [{data['kwh_cost'].min():.2f}, {data['kwh_cost'].max():.2f}]")

    if args.dry_run:
        print("\n[DRY RUN] Skipping training. Data loaded successfully.")
        return model, data, None

    # -------------------------------------------------------------------------
    # STEP 3: Train Model
    # -------------------------------------------------------------------------
    print("\nSTEP 3: Training Model")
    print("-" * 40)

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

    print("\nCoefficient Interpretation (Odds Ratios):")
    labels = {
        'beta_burden': 'Energy Burden',
        'beta_income': 'Income Level',
        'beta_hhsize': 'Household Size',
        'beta_kwh': 'kWh Cost'
    }
    for var, stats in results['odds_ratios'].items():
        credible = '[Credible]' if stats['credibly_nonzero'] else '[Includes Zero]'
        print(f"  {labels.get(var, var)}:")
        print(f"    Coefficient: {stats['coefficient']:.3f}")
        print(f"    Odds Ratio: {stats['odds_ratio']:.3f} [{stats['or_lower']:.3f}, {stats['or_upper']:.3f}]")
        print(f"    Effect: {stats['effect_pct']:+.1f}% change in odds per SD increase")
        print(f"    {credible}")

    # -------------------------------------------------------------------------
    # STEP 5: Hypothesis Test Result
    # -------------------------------------------------------------------------
    print("\nSTEP 5: Hypothesis Test")
    print("-" * 40)

    hyp = results['hypothesis_result']
    if hyp['supported'] is True:
        status = "[SUPPORTED]"
    elif hyp['supported'] is False:
        status = "[REJECTED]"
    else:
        status = "[INCONCLUSIVE]"

    print(f"PRIMARY HYPOTHESIS: Higher kWh cost -> Higher email open rates")
    print(f"Result: {status}")
    print(f"Interpretation: {hyp['interpretation']}")

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
                for f in files:
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
