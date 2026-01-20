#!/usr/bin/env python3
"""
Training script for Model 04: Campaign Treatment Effects

This script trains a hierarchical Bayesian model to estimate causal effects
of campaign message types on click behavior.

Usage:
    python src/bayesian_scripts/train_model_04_campaign_effects.py

Options:
    --draws INT       Number of posterior samples (default: 2000)
    --tune INT        Number of tuning samples (default: 1000)
    --chains INT      Number of MCMC chains (default: 4)
    --quick          Quick run with fewer samples for testing
    --validate       Run validation checks after training

Output:
    - Trace files: data/inference/model_04_campaign_effects/traces/
    - Reports: data/inference/model_04_campaign_effects/reports/
    - Diagrams: data/inference/model_04_campaign_effects/diagrams/
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import argparse
import json
from datetime import datetime

from src.bayesian_models.model_04_campaign_effects import CampaignTreatmentEffectsModel
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_treatment_effects(results: dict):
    """Print treatment effects summary table."""
    print_section("Treatment Effects Summary")

    effects = results.get('treatment_effects', {})
    ranking = results.get('effect_ranking', [])

    print(f"{'Message Type':<25} {'OR':>8} {'95% CI':>20} {'Effect %':>10} {'Significant':>12}")
    print("-" * 80)

    for msg_type, effect in ranking:
        or_val = effect['odds_ratio']
        ci_str = f"[{effect['or_lower']:.2f}, {effect['or_upper']:.2f}]"
        effect_pct = effect['effect_pct']
        sig = "Yes" if effect['credibly_nonzero'] else "No"

        # Direction indicator
        if effect['credibly_positive']:
            direction = "+"
        elif effect['credibly_negative']:
            direction = "-"
        else:
            direction = " "

        print(f"{msg_type:<25} {or_val:>7.2f} {ci_str:>20} {effect_pct:>+9.1f}% {direction}{sig:>10}")

    print("\nInterpretation:")
    print("  OR > 1.0: Message type increases click probability")
    print("  OR < 1.0: Message type decreases click probability")
    print("  Significant: 89% CI excludes 1.0 (null effect)")


def print_e_values(results: dict):
    """Print E-values for sensitivity analysis."""
    print_section("Sensitivity Analysis (E-values)")

    e_values = results.get('e_values', {})
    ranking = results.get('effect_ranking', [])

    print("E-value: Minimum strength of unmeasured confounding required to")
    print("         explain away the observed effect.\n")

    print(f"{'Message Type':<25} {'E-value':>10} {'Interpretation':>40}")
    print("-" * 80)

    for msg_type, _ in ranking:
        e_val = e_values.get(msg_type, 0)
        if e_val > 2.0:
            interp = "Robust to moderate confounding"
        elif e_val > 1.5:
            interp = "Somewhat robust"
        else:
            interp = "Sensitive to confounding"

        print(f"{msg_type:<25} {e_val:>10.2f} {interp:>40}")


def print_diagnostics(results: dict):
    """Print convergence diagnostics."""
    print_section("Convergence Diagnostics")

    diag = results.get('diagnostics', {})

    print(f"R-hat (max):      {diag.get('r_hat_max', 'N/A'):>10}")
    print(f"ESS bulk (min):   {diag.get('ess_bulk_min', 'N/A'):>10.0f}")
    print(f"ESS tail (min):   {diag.get('ess_tail_min', 'N/A'):>10.0f}")
    print(f"Divergences:      {diag.get('divergences', 'N/A'):>10}")
    print(f"Converged:        {diag.get('converged', 'N/A'):>10}")

    # Quality assessment
    r_hat_ok = diag.get('r_hat_max', 2.0) < 1.01
    ess_ok = diag.get('ess_bulk_min', 0) > 400
    div_ok = diag.get('divergences', 1) == 0

    print("\nQuality Assessment:")
    print(f"  R-hat < 1.01:     {'PASS' if r_hat_ok else 'FAIL'}")
    print(f"  ESS > 400:        {'PASS' if ess_ok else 'FAIL'}")
    print(f"  No divergences:   {'PASS' if div_ok else 'FAIL'}")


def print_county_effects(results: dict):
    """Print county random effects summary."""
    print_section("County Random Effects")

    icc = results.get('icc', {})
    county_effects = results.get('county_effects', {})

    print(f"Intraclass Correlation (ICC): {icc.get('mean', 0):.3f}")
    print(f"  89% CI: [{icc.get('lower', 0):.3f}, {icc.get('upper', 0):.3f}]")
    print(f"\nInterpretation: {icc.get('mean', 0)*100:.1f}% of unexplained variance")
    print("                is between counties.\n")

    # Show top/bottom counties by effect
    sorted_counties = sorted(county_effects.items(), key=lambda x: x[1]['mean'], reverse=True)

    print("Top 5 counties (highest baseline click rates):")
    for county, effect in sorted_counties[:5]:
        print(f"  {county}: {effect['mean']:+.3f}")

    print("\nBottom 5 counties (lowest baseline click rates):")
    for county, effect in sorted_counties[-5:]:
        print(f"  {county}: {effect['mean']:+.3f}")


def run_validation(model, results: dict):
    """Run post-training validation checks."""
    print_section("Post-Training Validation")

    checks_passed = 0
    checks_total = 0

    # Check 1: Convergence
    checks_total += 1
    if results['diagnostics']['converged']:
        print("Convergence check: PASSED")
        checks_passed += 1
    else:
        print("Convergence check: FAILED - R-hat > 1.01")

    # Check 2: No divergences
    checks_total += 1
    if results['diagnostics']['divergences'] == 0:
        print("Divergence check: PASSED")
        checks_passed += 1
    else:
        print(f"Divergence check: FAILED - {results['diagnostics']['divergences']} divergences")

    # Check 3: Treatment effects have expected signs
    checks_total += 1
    effects = results['treatment_effects']
    personalized_positive = effects['personalized_qualified']['odds_ratio'] > 1.0
    if personalized_positive:
        print("Prior hypothesis check (personalization positive): PASSED")
        checks_passed += 1
    else:
        print("Prior hypothesis check: FAILED - personalization effect negative")

    # Check 4: ICC is reasonable (between 0.01 and 0.30)
    checks_total += 1
    icc_mean = results['icc']['mean']
    if 0.01 < icc_mean < 0.30:
        print(f"ICC plausibility check: PASSED (ICC={icc_mean:.3f})")
        checks_passed += 1
    else:
        print(f"ICC plausibility check: WARNING (ICC={icc_mean:.3f}, expected 0.01-0.30)")

    print(f"\nValidation Summary: {checks_passed}/{checks_total} checks passed")

    return checks_passed == checks_total


def main():
    parser = argparse.ArgumentParser(
        description='Train Model 04: Campaign Treatment Effects'
    )
    parser.add_argument('--draws', type=int, default=2000,
                       help='Number of posterior samples')
    parser.add_argument('--tune', type=int, default=1000,
                       help='Number of tuning samples')
    parser.add_argument('--chains', type=int, default=4,
                       help='Number of MCMC chains')
    parser.add_argument('--quick', action='store_true',
                       help='Quick run with fewer samples')
    parser.add_argument('--validate', action='store_true',
                       help='Run validation after training')
    args = parser.parse_args()

    # Adjust for quick mode
    if args.quick:
        args.draws = 500
        args.tune = 200
        args.chains = 2

    print_section("Model 04: Campaign Treatment Effects Training")

    print(f"Configuration:")
    print(f"  Draws: {args.draws}")
    print(f"  Tune: {args.tune}")
    print(f"  Chains: {args.chains}")
    print(f"  Quick mode: {args.quick}")
    print(f"  Validation: {args.validate}")

    # Initialize model
    print("\nInitializing model...")
    model = CampaignTreatmentEffectsModel()
    print(f"  Model: {model.metadata.name}")
    print(f"  Version: {model.metadata.version}")
    print(f"  Output: {model.output_dir}")

    # Load data
    print("\nLoading data...")
    try:
        data = model.load_data()
        print(f"  Observations: {len(data['y_clicked']):,}")
        print(f"  Counties: {data['n_counties']}")
        print(f"  Click rate: {data['y_clicked'].mean():.2%}")
    except Exception as e:
        logger.error(f"Data loading failed: {e}")
        print(f"\nERROR: {e}")
        return 1

    # Train model
    print("\nTraining model (this may take several minutes)...")
    start_time = datetime.now()

    try:
        results = model.train(
            data,
            draws=args.draws,
            tune=args.tune,
            chains=args.chains
        )
    except Exception as e:
        logger.error(f"Training failed: {e}")
        print(f"\nERROR: {e}")
        return 1

    elapsed = datetime.now() - start_time
    print(f"\nTraining completed in {elapsed}")

    # Print results
    print_treatment_effects(results)
    print_e_values(results)
    print_diagnostics(results)
    print_county_effects(results)

    # Validation
    if args.validate:
        validation_passed = run_validation(model, results)
        if not validation_passed:
            print("\nWARNING: Some validation checks failed. Review results carefully.")

    print_section("Training Complete")
    print(f"Results saved to: {model.output_dir}")
    print(f"  Traces: {model.traces_dir}")
    print(f"  Reports: {model.reports_dir}")
    print(f"  Diagrams: {model.diagrams_dir}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
