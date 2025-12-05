#!/usr/bin/env python3
"""
Fit Model 3: Demographics Model

This script:
1. Loads and prepares participant data with demographics
2. Fits Model 3 (energy burden + income + household size + kWh usage)
3. Runs diagnostics and hypothesis tests
4. Saves results and generates plots
5. Compares to Model 2 using LOO-CV

Usage:
    python src/bayesian_scripts/bayes_fit_model_03.py [--campaign-ids ID1,ID2,...]
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import arviz as az
from src.bayesian_tools.data_preparation import BayesianDataPrep, get_model_matrices
from src.bayesian_tools.diagnostics import BayesianDiagnostics, check_model_quality
from src.bayesian_models.model_03_demographics import DemographicsOpenModel


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Fit Model 3: Demographics Model'
    )
    parser.add_argument(
        '--campaign-ids',
        type=str,
        default=None,
        help='Comma-separated list of campaign IDs to include (default: all)'
    )
    parser.add_argument(
        '--draws',
        type=int,
        default=2000,
        help='Number of posterior samples per chain (default: 2000)'
    )
    parser.add_argument(
        '--tune',
        type=int,
        default=1000,
        help='Number of tuning samples (default: 1000)'
    )
    parser.add_argument(
        '--chains',
        type=int,
        default=4,
        help='Number of MCMC chains (default: 4)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/bayesian_models',
        help='Output directory for results (default: reports/bayesian_models)'
    )
    parser.add_argument(
        '--compare-model2',
        action='store_true',
        help='Compare with Model 2 using LOO-CV (requires model_02_trace.nc)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "🔬 " * 20)
    print("MODEL 3: DEMOGRAPHICS MODEL")
    print("🔬 " * 20 + "\n")

    # Parse campaign IDs if provided
    campaign_ids = None
    if args.campaign_ids:
        campaign_ids = [cid.strip() for cid in args.campaign_ids.split(',')]
        print(f"Filtering to {len(campaign_ids)} campaigns")

    # 1. Load and prepare data
    print("\n" + "=" * 60)
    print("STEP 1: DATA PREPARATION")
    print("=" * 60 + "\n")

    data_prep = BayesianDataPrep()

    try:
        df, metadata = data_prep.prepare_model_data(
            campaign_ids=campaign_ids,
            min_observations=100
        )
    except Exception as e:
        print(f"\n❌ Error preparing data: {e}")
        return 1

    # Save metadata
    import json
    metadata_path = output_dir / 'model_03_metadata.json'
    with open(metadata_path, 'w') as f:
        metadata_clean = {k: str(v) if not isinstance(v, (int, float, str, list, dict))
                         else v for k, v in metadata.items()}
        json.dump(metadata_clean, f, indent=2)
    print(f"\nMetadata saved to {metadata_path}")

    # 2. Extract model matrices
    print("\n" + "=" * 60)
    print("STEP 2: EXTRACT MODEL MATRICES")
    print("=" * 60 + "\n")

    model_data = get_model_matrices(df, model_spec='demographics')
    print(f"Model matrices extracted:")
    for key, value in model_data.items():
        if isinstance(value, np.ndarray):
            print(f"  {key}: shape {value.shape}, mean={value.mean():.3f}, std={value.std():.3f}")

    # Check for high energy burden households
    n_high_burden = (df['total_energy_burden'] > 0.06).sum()
    pct_high_burden = n_high_burden / len(df) * 100
    print(f"\nHigh energy burden (>6%): {n_high_burden} households ({pct_high_burden:.1f}%)")

    # Check kWh usage distribution
    kwh_mean = df['kwh'].mean()
    kwh_median = df['kwh'].median()
    kwh_std = df['kwh'].std()
    print(f"kWh usage: mean={kwh_mean:.0f}, median={kwh_median:.0f}, std={kwh_std:.0f}")

    # 3. Build and fit model
    print("\n" + "=" * 60)
    print("STEP 3: FIT MODEL")
    print("=" * 60 + "\n")

    model = DemographicsOpenModel()

    try:
        trace = model.fit(
            data=model_data,
            draws=args.draws,
            tune=args.tune,
            chains=args.chains,
        )
    except Exception as e:
        print(f"\n❌ Error fitting model: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 4. Run diagnostics
    print("\n" + "=" * 60)
    print("STEP 4: DIAGNOSTICS")
    print("=" * 60 + "\n")

    diagnostics = check_model_quality(
        trace=trace,
        y_observed=model_data['y_opened'],
        model_name="Model 3: Demographics",
        var_names=["intercept", "beta_burden", "beta_income", "beta_hhsize", "beta_kwh"]
    )

    # 5. Model summary
    print("\n" + "=" * 60)
    print("STEP 5: MODEL SUMMARY & HYPOTHESIS TEST")
    print("=" * 60 + "\n")

    model.summarize()

    # 6. Generate plots
    print("\n" + "=" * 60)
    print("STEP 6: GENERATE PLOTS")
    print("=" * 60 + "\n")

    # Trace plot
    trace_plot_path = output_dir / 'model_03_trace.png'
    BayesianDiagnostics.plot_trace(
        trace,
        var_names=["intercept", "beta_burden", "beta_income", "beta_hhsize", "beta_kwh"],
        save_path=str(trace_plot_path)
    )

    # Posterior distributions
    posterior_plot_path = output_dir / 'model_03_posterior.png'
    model.plot_coefficients(save_path=str(posterior_plot_path))

    # Forest plot
    forest_plot_path = output_dir / 'model_03_forest.png'
    BayesianDiagnostics.plot_forest(
        trace,
        var_names=["beta_burden", "beta_income", "beta_hhsize", "beta_kwh"],
        save_path=str(forest_plot_path)
    )

    # Posterior predictive check
    ppc_plot_path = output_dir / 'model_03_ppc.png'
    BayesianDiagnostics.posterior_predictive_check(
        trace,
        y_observed=model_data['y_opened'],
        model_type='binary',
        save_path=str(ppc_plot_path)
    )

    print(f"\nPlots saved to {output_dir}/")

    # 7. Save trace
    print("\n" + "=" * 60)
    print("STEP 7: SAVE RESULTS")
    print("=" * 60 + "\n")

    trace_path = output_dir / 'model_03_trace.nc'
    model.save_trace(str(trace_path))

    # Save summary to CSV
    summary_df = diagnostics['coefficients']
    summary_path = output_dir / 'model_03_summary.csv'
    summary_df.to_csv(summary_path)
    print(f"Summary saved to {summary_path}")

    # 8. Model comparison with Model 2
    if args.compare_model2:
        print("\n" + "=" * 60)
        print("STEP 8: COMPARE WITH MODEL 2")
        print("=" * 60 + "\n")

        model2_trace_path = output_dir / 'model_02_trace.nc'
        if model2_trace_path.exists():
            try:
                trace_model2 = az.from_netcdf(str(model2_trace_path))

                print("Computing LOO-CV for both models...")
                comparison = az.compare({
                    'Model 2 (Energy Burden)': trace_model2,
                    'Model 3 (Demographics)': trace
                })

                print("\n" + "=" * 60)
                print("MODEL COMPARISON (LOO-CV)")
                print("=" * 60 + "\n")
                print(comparison)

                # Save comparison
                comparison_path = output_dir / 'model_02_vs_03_comparison.csv'
                comparison.to_csv(comparison_path)
                print(f"\nComparison saved to {comparison_path}")

                # Interpret results
                print("\nInterpretation:")
                best_model = comparison.index[0]
                loo_diff = comparison.loc[comparison.index[1], 'loo']
                se_diff = comparison.loc[comparison.index[1], 'se']

                print(f"  Best model: {best_model}")
                if abs(loo_diff) > 2 * se_diff:
                    print(f"  LOO difference is significant (>{se_diff:.1f} > {2*se_diff:.1f})")
                    print(f"  Adding kWh usage {'improves' if best_model == 'Model 3 (Demographics)' else 'does not improve'} predictive performance")
                else:
                    print(f"  LOO difference is not significant ({abs(loo_diff):.1f} < {2*se_diff:.1f})")
                    print(f"  Models have similar predictive performance")

            except Exception as e:
                print(f"⚠️  Could not compare with Model 2: {e}")
        else:
            print(f"⚠️  Model 2 trace not found at {model2_trace_path}")
            print("   Run bayes_fit_model_02.py first to enable comparison")

    # 9. Final report
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60 + "\n")

    convergence = diagnostics['convergence']
    if convergence['converged']:
        print("✅ Model converged successfully!")
    else:
        print("⚠️  Model convergence issues detected")
        if convergence['rhat_issues']:
            print(f"   R-hat issues: {convergence['rhat_issues']}")
        if convergence['ess_issues']:
            print(f"   ESS issues: {convergence['ess_issues']}")

    print(f"\nResults saved to: {output_dir}/")
    print("\nFiles created:")
    print(f"  - {trace_path.name}: Model trace (InferenceData)")
    print(f"  - {summary_path.name}: Coefficient summary (CSV)")
    print(f"  - {metadata_path.name}: Data metadata (JSON)")
    print(f"  - {trace_plot_path.name}: Trace plot")
    print(f"  - {posterior_plot_path.name}: Posterior distributions")
    print(f"  - {forest_plot_path.name}: Forest plot")
    print(f"  - {ppc_plot_path.name}: Posterior predictive check")

    print("\n" + "✅ " * 20)
    print("MODEL 3 FITTING COMPLETE!")
    print("✅ " * 20 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
