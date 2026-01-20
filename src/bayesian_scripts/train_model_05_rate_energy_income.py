#!/usr/bin/env python
"""
Model 05: Click Rate by Energy Cost × Income Category - Training Script
========================================================================

Train the hierarchical varying slopes model for click rate prediction.

This model uses energy cost and income category as separate predictors
with an interaction term that captures how the energy cost effect varies
by income category - implicitly modeling energy burden without discretization.

Usage:
    python src/bayesian_scripts/train_model_05_rate_energy_income.py
    python src/bayesian_scripts/train_model_05_rate_energy_income.py --draws 3000 --chains 4
    python src/bayesian_scripts/train_model_05_rate_energy_income.py --dry-run
    python src/bayesian_scripts/train_model_05_rate_energy_income.py --no-gpu

Outputs are saved to: data/inference/model_05_rate_energy_income/
    - traces/      : MCMC trace files (.nc)
    - reports/     : Summary statistics, category effects
    - diagrams/    : DAG, posterior plots, interaction plots
    - checkpoints/ : Scaler parameters for inference
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_models.model_05_rate_energy_income import (
    ClickRateEnergyIncomeModel,
    INCOME_CATEGORY_LABELS
)
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Train the Click Rate Energy×Income Model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Sampling parameters
    parser.add_argument("--draws", type=int, default=2000,
                        help="Number of posterior samples per chain")
    parser.add_argument("--tune", type=int, default=1000,
                        help="Number of tuning samples (discarded)")
    parser.add_argument("--chains", type=int, default=4,
                        help="Number of MCMC chains")
    parser.add_argument("--target-accept", type=float, default=0.9,
                        help="Target acceptance rate for NUTS sampler")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")

    # GPU options
    parser.add_argument("--no-gpu", action="store_true",
                        help="Disable GPU acceleration (use CPU only)")

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
    print("MODEL 05: CLICK RATE - ENERGY COST × INCOME CATEGORY")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  Draws: {args.draws}")
    print(f"  Tune: {args.tune}")
    print(f"  Chains: {args.chains}")
    print(f"  Target Accept: {args.target_accept}")
    print(f"  Seed: {args.seed}")
    print(f"  GPU: {'Disabled' if args.no_gpu else 'Enabled (NumPyro)'}")
    print(f"  Collection: {args.collection}")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # STEP 1: Initialize Model
    # -------------------------------------------------------------------------
    print("STEP 1: Initializing Model")
    print("-" * 40)

    model = ClickRateEnergyIncomeModel()
    print(f"Model: {model.metadata.name} (v{model.metadata.version})")
    print(f"Output directory: {model.output_dir}")

    # -------------------------------------------------------------------------
    # STEP 2: Load Data
    # -------------------------------------------------------------------------
    print("\nSTEP 2: Loading Data")
    print("-" * 40)

    data = model.load_data(collection=args.collection)
    n_obs = data['n_obs']
    click_rate = data['y_clicked'].mean()

    print(f"Loaded {n_obs} observations")
    print(f"Click rate: {click_rate:.2%}")
    print(f"Income categories: {data['n_categories']}")
    print(f"Energy cost (scaled): [{data['energy_cost_scaled'].min():.2f}, {data['energy_cost_scaled'].max():.2f}]")

    # Show category distribution
    print("\nIncome Category Distribution:")
    for k in range(data['n_categories']):
        count = (data['income_cat_idx'] == k).sum()
        pct = count / n_obs * 100
        print(f"  {INCOME_CATEGORY_LABELS[k]}: {count:,} ({pct:.1f}%)")

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
        random_seed=args.seed,
        use_gpu=not args.no_gpu
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

    print("\nMain Effects:")
    main = results['main_effects']['beta_energy']
    print(f"  Energy Cost (β):")
    print(f"    Coefficient: {main['coefficient']:.3f}")
    print(f"    Odds Ratio: {main['odds_ratio']:.3f} [{main['or_lower']:.3f}, {main['or_upper']:.3f}]")
    print(f"    Effect: {main['effect_pct']:+.1f}% change in odds per SD increase")
    print(f"    Credibly non-zero: {main['credibly_nonzero']}")

    # -------------------------------------------------------------------------
    # STEP 5: Category Effects
    # -------------------------------------------------------------------------
    print("\nSTEP 5: Income Category Effects")
    print("-" * 40)

    print("\n{:<15} {:>10} {:>10} {:>12}".format(
        "Category", "γ (shift)", "δ (slope)", "Total Slope"))
    print("-" * 50)

    for label, effects in results['category_effects'].items():
        print("{:<15} {:>10.3f} {:>10.3f} {:>12.3f}".format(
            label,
            effects['gamma'],
            effects['delta'],
            effects['total_slope']
        ))

    # -------------------------------------------------------------------------
    # STEP 6: Slope Variation Hypothesis
    # -------------------------------------------------------------------------
    print("\nSTEP 6: Slope Variation Analysis")
    print("-" * 40)

    var = results['slope_variation']
    status = "[SUPPORTED]" if var['supported'] else "[NOT SUPPORTED]"
    print(f"Hypothesis: Energy cost effect varies by income category")
    print(f"Result: {status}")
    print(f"σ_δ (slope variation): {var['sigma_delta']:.3f}")
    print(f"Interpretation: {var['interpretation']}")

    # -------------------------------------------------------------------------
    # STEP 7: Show Output Locations
    # -------------------------------------------------------------------------
    print("\nSTEP 7: Saved Artifacts")
    print("-" * 40)

    for name, path in model.get_output_paths().items():
        if path.exists():
            files = list(path.glob('*'))
            if files:
                print(f"\n{name}/:")
                for f in sorted(files):
                    size = f.stat().st_size if f.is_file() else 0
                    size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
                    print(f"  - {f.name} ({size_str})")

    # -------------------------------------------------------------------------
    # STEP 8: Example Predictions
    # -------------------------------------------------------------------------
    print("\nSTEP 8: Example Predictions")
    print("-" * 40)

    print("\nClick probability by income category (at $150/month energy cost):")
    comparison = model.compare_income_categories(energy_cost=150.0)
    print(comparison.to_string(index=False))

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
