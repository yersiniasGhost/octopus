#!/usr/bin/env python3
"""
Validate a trained Bayesian model.

This script performs comprehensive validation including:
- Convergence diagnostics (R-hat, ESS, divergences)
- Posterior predictive checks
- PSIS-LOO cross-validation
- E-values for causal sensitivity
- Generate diagnostic plots

Usage:
    python scripts/validate_bayesian_model.py model_04_campaign_effects
    python scripts/validate_bayesian_model.py model_03_demographics --plots
    python scripts/validate_bayesian_model.py model_04_campaign_effects --output-json results.json

Options:
    MODEL_ID         Model identifier (directory name in src/bayesian_models/)
    --plots          Generate diagnostic plots
    --output-json    Save validation report to JSON file
    --no-loo         Skip LOO computation (faster)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import json
from datetime import datetime

import arviz as az

from src.bayesian_models.validation import ModelValidator
from src.bayesian_models.model_registry import ModelRegistry
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


def print_section(title: str):
    """Print formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_convergence(report: dict):
    """Print convergence diagnostics."""
    print_section("Convergence Diagnostics")

    conv = report.get('convergence', {})

    r_hat = conv.get('r_hat', {})
    print(f"R-hat (max):        {r_hat.get('max_value', 'N/A'):>10.4f}  {'PASS' if r_hat.get('passed') else 'FAIL'}")

    ess = conv.get('ess', {})
    print(f"ESS bulk (min):     {ess.get('bulk_min', 'N/A'):>10.0f}  {'PASS' if ess.get('passed') else 'FAIL'}")
    print(f"ESS tail (min):     {ess.get('tail_min', 'N/A'):>10.0f}")

    div = conv.get('divergences', {})
    print(f"Divergences:        {div.get('count', 'N/A'):>10}  {'PASS' if div.get('passed') else 'FAIL'}")

    if conv.get('r_hat', {}).get('problematic_params'):
        print(f"\nProblematic parameters (R-hat): {conv['r_hat']['problematic_params']}")

    print(f"\nRecommendation: {conv.get('recommendation', 'N/A')}")


def print_ppc(report: dict):
    """Print posterior predictive check results."""
    print_section("Posterior Predictive Check")

    ppc = report.get('posterior_predictive', {})

    if 'error' in ppc or 'skipped' in ppc:
        print(f"Skipped: {ppc.get('error') or ppc.get('skipped')}")
        return

    print(f"Observed mean:      {ppc.get('observed_mean', 0):.4f}")
    print(f"Predicted mean:     {ppc.get('predicted_mean', 0):.4f} (+/- {ppc.get('predicted_std', 0):.4f})")
    print(f"Bayesian p-value:   {ppc.get('bayesian_p_value', 0):.4f}")

    cal = ppc.get('calibration', {})
    print(f"Calibration RMSE:   {cal.get('rmse', 0):.4f}  {'PASS' if cal.get('well_calibrated') else 'WARN'}")

    print(f"\nInterpretation: {ppc.get('interpretation', 'N/A')}")


def print_loo(report: dict):
    """Print LOO cross-validation results."""
    print_section("Leave-One-Out Cross-Validation")

    loo = report.get('loo', {})

    if 'error' in loo or 'skipped' in loo:
        print(f"Skipped: {loo.get('error') or loo.get('skipped')}")
        return

    print(f"ELPD LOO:           {loo.get('elpd_loo', 0):>10.1f}")
    print(f"Standard Error:     {loo.get('se', 0):>10.1f}")
    print(f"p_loo:              {loo.get('p_loo', 0):>10.1f}")
    print(f"Pareto k (max):     {loo.get('pareto_k_max', 0):>10.3f}")
    print(f"Bad Pareto k (>0.7):{loo.get('pareto_k_bad_count', 0):>10}")
    print(f"Quality:            {loo.get('quality', 'N/A'):>10}")

    print(f"\nRecommendation: {loo.get('recommendation', 'N/A')}")


def print_e_values(report: dict):
    """Print E-values for sensitivity analysis."""
    print_section("Sensitivity Analysis (E-values)")

    e_values = report.get('e_values', {})

    if not e_values or 'error' in e_values:
        print("E-values not computed (no treatment effects provided)")
        return

    print("E-value: Minimum unmeasured confounding strength to explain away effect")
    print()
    print(f"{'Parameter':<30} {'E-value':>10} {'Robustness':>20}")
    print("-" * 65)

    for param, data in sorted(e_values.items(), key=lambda x: x[1]['e_value'], reverse=True):
        print(f"{param:<30} {data['e_value']:>10.2f} {data['robustness']:>20}")


def print_overall(report: dict):
    """Print overall assessment."""
    print_section("Overall Assessment")

    overall = report.get('overall', {})

    status = overall.get('status', 'UNKNOWN')
    status_symbol = {'PASSED': 'PASS', 'PASSED_WITH_WARNINGS': 'WARN', 'FAILED': 'FAIL'}.get(status, '???')

    print(f"Status: {status_symbol}")
    print(f"Message: {overall.get('message', 'N/A')}")

    if overall.get('issues'):
        print(f"\nIssues:")
        for issue in overall['issues']:
            print(f"  - {issue}")

    if overall.get('warnings'):
        print(f"\nWarnings:")
        for warning in overall['warnings']:
            print(f"  - {warning}")


def main():
    parser = argparse.ArgumentParser(description='Validate a trained Bayesian model')
    parser.add_argument('model_id', help='Model identifier (e.g., model_04_campaign_effects)')
    parser.add_argument('--plots', action='store_true', help='Generate diagnostic plots')
    parser.add_argument('--output-json', type=str, help='Save report to JSON file')
    parser.add_argument('--no-loo', action='store_true', help='Skip LOO computation')
    args = parser.parse_args()

    print_section(f"Validating Model: {args.model_id}")

    # Load model
    registry = ModelRegistry()
    model = registry.load_model_instance(args.model_id)

    if model is None:
        print(f"ERROR: Model '{args.model_id}' not found in registry")
        print(f"Available models: {list(registry.get_all_models().keys())}")
        return 1

    # Check for trained model
    latest_trace = model.get_latest_trace()
    if latest_trace is None:
        print(f"ERROR: No trained model found for '{args.model_id}'")
        print(f"Run training script first: python src/bayesian_scripts/train_{args.model_id}.py")
        return 1

    print(f"Loading trace: {latest_trace}")
    trace = az.from_netcdf(latest_trace)

    # Load treatment effects if available
    treatment_effects = None
    county_effects = None

    # Try to load from latest results file
    if model.reports_dir.exists():
        results_files = sorted(model.reports_dir.glob('results_*.json'))
        if results_files:
            with open(results_files[-1], 'r') as f:
                results = json.load(f)
                treatment_effects = results.get('treatment_effects')
                county_effects = results.get('county_effects')

    # Create validator
    validator = ModelValidator(
        trace,
        model_name=model.metadata.name,
        treatment_effects=treatment_effects,
        county_effects=county_effects
    )

    # Run validation
    report = validator.full_validation(include_loo=not args.no_loo)

    # Print results
    print_convergence(report)
    print_ppc(report)
    print_loo(report)
    print_e_values(report)
    print_overall(report)

    # Generate plots
    if args.plots:
        print_section("Generating Plots")
        output_dir = model.diagrams_dir / 'validation'
        plots = validator.generate_all_plots(output_dir)
        print(f"Plots saved to: {output_dir}")
        for name, info in plots.items():
            print(f"  - {name}: {info.get('saved_to', 'N/A')}")

    # Save JSON report
    if args.output_json:
        output_path = Path(args.output_json)
        validator.save_report(output_path)
        print(f"\nReport saved to: {output_path}")

    # Return code based on validation status
    status = report.get('overall', {}).get('status', 'UNKNOWN')
    if status == 'PASSED':
        return 0
    elif status == 'PASSED_WITH_WARNINGS':
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
