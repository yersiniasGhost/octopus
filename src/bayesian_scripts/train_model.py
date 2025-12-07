#!/usr/bin/env python
"""
Click Model Training Script
===========================

Simple training script that uses the ClickModel classes to:
1. Load data (via load_data() or custom data source)
2. Preprocess and build the model
3. Run MCMC sampling
4. Save outputs (trace, summary, plots)

Usage:
    python src/bayesian_scripts/train_model.py
    python src/bayesian_scripts/train_model.py --draws 3000 --chains 4
    python src/bayesian_scripts/train_model.py --output-dir models/click_model/run_001
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt

from src.bayesian_models.click_model.model import ClickModel, SegmentPredictor
from src.bayesian_models.click_model.model_data import ClickModelData, load_data
from src.bayesian_models.click_model.segments import DEFAULT_SEGMENTS


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Train the Bayesian Click Model",
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

    # Compute options
    parser.add_argument("--cpu", action="store_true",
                        help="Use CPU instead of GPU (default: GPU via NumPyro)")

    # Output options
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: models/click_model/YYYYMMDD_HHMMSS)")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip generating plots")
    parser.add_argument("--no-save", action="store_true",
                        help="Skip saving outputs (dry run)")

    return parser.parse_args()


def setup_output_dir(output_dir: str = None) -> Path:
    """Create output directory structure."""
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = PROJECT_ROOT / "models" / "click_model" / timestamp
    else:
        output_dir = Path(output_dir)

    # Create subdirectories
    (output_dir / "traces").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)
    (output_dir / "plots").mkdir(parents=True, exist_ok=True)

    return output_dir


def main():
    args = parse_args()

    use_gpu = not args.cpu

    print("=" * 70)
    print("CLICK MODEL TRAINING")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  Draws: {args.draws}")
    print(f"  Tune: {args.tune}")
    print(f"  Chains: {args.chains}")
    print(f"  Target Accept: {args.target_accept}")
    print(f"  Seed: {args.seed}")
    print(f"  Backend: {'GPU (NumPyro/JAX)' if use_gpu else 'CPU (PyMC)'}")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # STEP 1: Load Data
    # -------------------------------------------------------------------------
    print("STEP 1: Loading Data")
    print("-" * 40)

    data = load_data()
    print(f"\n{data.summary()}\n")

    # -------------------------------------------------------------------------
    # STEP 2: Build Model
    # -------------------------------------------------------------------------
    print("\nSTEP 2: Building Model")
    print("-" * 40)

    model = ClickModel()
    model.build_model(data)

    # -------------------------------------------------------------------------
    # STEP 3: Fit Model (MCMC Sampling)
    # -------------------------------------------------------------------------
    print("\nSTEP 3: Fitting Model (MCMC Sampling)")
    print("-" * 40)

    trace = model.fit(
        draws=args.draws,
        tune=args.tune,
        chains=args.chains,
        target_accept=args.target_accept,
        random_seed=args.seed,
        use_gpu=use_gpu
    )

    # -------------------------------------------------------------------------
    # STEP 4: Model Summary
    # -------------------------------------------------------------------------
    print("\nSTEP 4: Model Summary")
    print("-" * 40)

    summary = model.summary()
    print(summary)

    # Interpret coefficients
    print("\nCoefficient Interpretation (on log-odds scale):")
    posterior = trace.posterior

    # Age is optional - check if it exists in the model
    if 'beta_age' in posterior:
        beta_age_mean = posterior['beta_age'].values.mean()
        print(f"  • Age: {beta_age_mean:.3f} → {'older = lower' if beta_age_mean < 0 else 'older = higher'} click prob")
    else:
        print(f"  • Age: not included (data not available)")

    beta_income_mean = posterior['beta_income'].values.mean()
    beta_eb_mean = posterior['beta_eb'].values.mean()

    print(f"  • Income: {beta_income_mean:.3f} → {'higher income = lower' if beta_income_mean < 0 else 'higher income = higher'} click prob")
    print(f"  • Energy Burden: {beta_eb_mean:.3f} → {'higher burden = lower' if beta_eb_mean < 0 else 'higher burden = higher'} click prob")

    # -------------------------------------------------------------------------
    # STEP 5: Segment Predictions
    # -------------------------------------------------------------------------
    print("\nSTEP 5: Segment Predictions")
    print("-" * 40)

    predictor = SegmentPredictor(model)

    # Use default segments from segments.py
    segments = DEFAULT_SEGMENTS

    print("\nSegment Comparison:")
    comparison = predictor.compare_segments(segments)
    print(comparison.to_string(index=False))

    # -------------------------------------------------------------------------
    # STEP 6: Save Outputs
    # -------------------------------------------------------------------------
    if not args.no_save:
        print("\nSTEP 6: Saving Outputs")
        print("-" * 40)

        output_dir = setup_output_dir(args.output_dir)
        print(f"Output directory: {output_dir}")

        # Save trace
        trace_path = output_dir / "traces" / "trace.nc"
        trace.to_netcdf(trace_path)
        print(f"  ✓ Trace saved: {trace_path}")

        # Save summary
        summary_path = output_dir / "reports" / "summary.csv"
        summary.to_csv(summary_path)
        print(f"  ✓ Summary saved: {summary_path}")

        # Save segment comparison
        comparison_path = output_dir / "reports" / "segment_comparison.csv"
        comparison.to_csv(comparison_path, index=False)
        print(f"  ✓ Segment comparison saved: {comparison_path}")

        # Save training metadata
        import json
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "draws": args.draws,
            "tune": args.tune,
            "chains": args.chains,
            "target_accept": args.target_accept,
            "seed": args.seed,
            "backend": "numpyro" if use_gpu else "pymc",
            "n_observations": data.n_contacts,
            "click_rate": float(data.click_rate),
        }
        metadata_path = output_dir / "reports" / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"  ✓ Metadata saved: {metadata_path}")

        # Generate and save plots
        if not args.no_plots:
            print("\n  Generating plots...")

            # Trace plot
            model.plot_trace()
            trace_plot_path = output_dir / "plots" / "trace_plot.png"
            plt.savefig(trace_plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ Trace plot saved: {trace_plot_path}")

            # Posterior plot
            model.plot_posterior()
            posterior_plot_path = output_dir / "plots" / "posterior_plot.png"
            plt.savefig(posterior_plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ Posterior plot saved: {posterior_plot_path}")

            # Segment comparison plot
            predictor.plot_segment_comparison(segments)
            segment_plot_path = output_dir / "plots" / "segment_comparison.png"
            plt.savefig(segment_plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  ✓ Segment comparison plot saved: {segment_plot_path}")

    # -------------------------------------------------------------------------
    # Done
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)

    return model, predictor, trace


if __name__ == "__main__":
    model, predictor, trace = main()
