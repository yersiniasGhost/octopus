#!/usr/bin/env python3
"""
Template Training Script for Bayesian Models

Copy this template and customize for each new model:
    cp src/bayesian_scripts/_template_train.py src/bayesian_scripts/{model_name}_train.py

Usage:
    python src/bayesian_scripts/{model_name}_train.py
    python src/bayesian_scripts/{model_name}_train.py --draws 2000 --chains 4
    python src/bayesian_scripts/{model_name}_train.py --gpu  # Force GPU sampling
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import arviz as az
import matplotlib.pyplot as plt


# =============================================================================
# CONFIGURATION
# =============================================================================

# Model identifier - must match directory name in src/bayesian_models/
MODEL_ID = 'your_model_name'  # TODO: Change this

# Default sampling configuration
DEFAULT_CONFIG = {
    'draws': 2000,
    'tune': 1000,
    'chains': 4,
    'target_accept': 0.95,
    'random_seed': 42
}


# =============================================================================
# DATA LOADING
# =============================================================================

def load_training_data() -> pd.DataFrame:
    """
    Load and prepare training data.

    Returns:
        pd.DataFrame: Prepared training data

    TODO: Customize this function for your model's data requirements
    """
    # Example: Load from prepared parquet file
    data_path = PROJECT_ROOT / 'data' / 'bayes' / 'prepared_data_all_campaigns.parquet'

    if not data_path.exists():
        raise FileNotFoundError(
            f"Training data not found: {data_path}\n"
            f"Run data preparation scripts first."
        )

    df = pd.read_parquet(data_path)
    print(f"Loaded {len(df):,} records from {data_path.name}")

    # TODO: Add your data preprocessing here
    # Example: Filter, transform, create features

    return df


# =============================================================================
# MODEL BUILDING
# =============================================================================

def build_model(data: pd.DataFrame):
    """
    Build the PyMC model.

    Args:
        data: Prepared training data

    Returns:
        pm.Model: Compiled PyMC model

    TODO: Customize this function for your model structure
    """
    import pymc as pm

    with pm.Model() as model:
        # =================================================================
        # DATA (as PyMC Data containers for potential prediction)
        # =================================================================
        # Example:
        # x = pm.Data('x', data['feature'].values)
        # y_obs = data['target'].values

        # =================================================================
        # PRIORS
        # =================================================================
        # Example:
        # alpha = pm.Normal('alpha', mu=0, sigma=1)
        # beta = pm.Normal('beta', mu=0, sigma=0.5)

        # =================================================================
        # LINEAR MODEL / LIKELIHOOD
        # =================================================================
        # Example:
        # mu = alpha + beta * x
        # y = pm.Normal('y', mu=mu, sigma=sigma, observed=y_obs)

        pass  # TODO: Replace with your model

    return model


# =============================================================================
# SAMPLING
# =============================================================================

def check_gpu_available() -> bool:
    """Check if GPU is available for JAX/NumPyro sampling."""
    try:
        import jax
        devices = jax.devices()
        has_gpu = any('gpu' in str(d).lower() or 'cuda' in str(d).lower()
                      for d in devices)
        print(f"JAX devices: {devices}")
        return has_gpu
    except ImportError:
        return False


def sample_model(model, config: dict, use_gpu: bool = True):
    """
    Sample the model using MCMC.

    Args:
        model: PyMC model
        config: Sampling configuration
        use_gpu: Whether to use GPU acceleration (if available)

    Returns:
        tuple: (trace, sampling_time_seconds)
    """
    import pymc as pm

    print("\n" + "=" * 60)
    print("MCMC SAMPLING")
    print("=" * 60)
    print(f"  Draws: {config['draws']}")
    print(f"  Tune: {config['tune']}")
    print(f"  Chains: {config['chains']}")
    print(f"  Target accept: {config['target_accept']}")

    start_time = time.time()

    with model:
        if use_gpu and check_gpu_available():
            print("\n  Using GPU acceleration (NumPyro NUTS)...")
            try:
                trace = pm.sample(
                    draws=config['draws'],
                    tune=config['tune'],
                    chains=config['chains'],
                    target_accept=config['target_accept'],
                    random_seed=config['random_seed'],
                    nuts_sampler='numpyro',
                    progressbar=True
                )
            except Exception as e:
                print(f"  GPU sampling failed: {e}")
                print("  Falling back to CPU...")
                trace = pm.sample(
                    draws=config['draws'],
                    tune=config['tune'],
                    chains=config['chains'],
                    target_accept=config['target_accept'],
                    random_seed=config['random_seed'],
                    progressbar=True
                )
        else:
            print("\n  Using CPU sampling...")
            trace = pm.sample(
                draws=config['draws'],
                tune=config['tune'],
                chains=config['chains'],
                target_accept=config['target_accept'],
                random_seed=config['random_seed'],
                progressbar=True
            )

    sampling_time = time.time() - start_time
    print(f"\n✓ Sampling completed in {sampling_time:.2f}s ({sampling_time/60:.2f} min)")

    return trace, sampling_time


# =============================================================================
# DIAGNOSTICS
# =============================================================================

def check_convergence(trace, var_names=None) -> bool:
    """
    Check MCMC convergence diagnostics.

    Args:
        trace: ArviZ InferenceData
        var_names: Variable names to check (None = all)

    Returns:
        bool: True if all checks pass
    """
    print("\n" + "=" * 60)
    print("CONVERGENCE DIAGNOSTICS")
    print("=" * 60)

    summary = az.summary(trace, var_names=var_names, hdi_prob=0.94)

    # R-hat check (should be < 1.01)
    max_rhat = summary['r_hat'].max()
    rhat_ok = max_rhat < 1.01
    print(f"\nR-hat: max={max_rhat:.4f} {'✓' if rhat_ok else '✗ WARNING'}")

    # ESS check (should be > 400)
    min_ess = min(summary['ess_bulk'].min(), summary['ess_tail'].min())
    ess_ok = min_ess > 400
    print(f"ESS: min={min_ess:.0f} {'✓' if ess_ok else '✗ WARNING'}")

    # Divergences check
    divergences = int(trace.sample_stats.diverging.sum())
    div_ok = divergences == 0
    print(f"Divergences: {divergences} {'✓' if div_ok else '✗ WARNING'}")

    all_ok = rhat_ok and ess_ok and div_ok
    print(f"\nOverall: {'✓ ALL CHECKS PASSED' if all_ok else '✗ ISSUES DETECTED'}")

    return all_ok


# =============================================================================
# SAVING RESULTS
# =============================================================================

def save_results(trace, model_id: str, sampling_time: float, config: dict):
    """
    Save training results to models/{model_id}/ directory.

    Args:
        trace: ArviZ InferenceData
        model_id: Model identifier
        sampling_time: Sampling time in seconds
        config: Sampling configuration used
    """
    from src.bayesian_models.base_model import MODELS_OUTPUT_DIR

    output_dir = MODELS_OUTPUT_DIR / model_id
    traces_dir = output_dir / 'traces'
    reports_dir = output_dir / 'reports'
    diagrams_dir = output_dir / 'diagrams'

    # Create directories
    for d in [traces_dir, reports_dir, diagrams_dir]:
        d.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    print("\n" + "=" * 60)
    print("SAVING RESULTS")
    print("=" * 60)

    # 1. Save trace (NetCDF format)
    trace_file = traces_dir / f'trace_{timestamp}.nc'
    trace.to_netcdf(trace_file)
    print(f"✓ Trace: {trace_file}")

    # 2. Save parameter summary
    summary = az.summary(trace, hdi_prob=0.94)
    summary_file = reports_dir / f'summary_{timestamp}.csv'
    summary.to_csv(summary_file)
    print(f"✓ Summary: {summary_file}")

    # 3. Save metadata
    metadata = {
        'model_id': model_id,
        'timestamp': timestamp,
        'sampling_time_seconds': sampling_time,
        'config': config
    }
    import json
    metadata_file = reports_dir / f'metadata_{timestamp}.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Metadata: {metadata_file}")

    # 4. Generate diagnostic plots
    print("\nGenerating diagnostic plots...")

    # Trace plot
    az.plot_trace(trace)
    plt.tight_layout()
    trace_plot = diagrams_dir / f'trace_plot_{timestamp}.png'
    plt.savefig(trace_plot, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Trace plot: {trace_plot}")

    # Posterior plot
    az.plot_posterior(trace, hdi_prob=0.94)
    plt.tight_layout()
    posterior_plot = diagrams_dir / f'posterior_{timestamp}.png'
    plt.savefig(posterior_plot, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Posterior plot: {posterior_plot}")

    print(f"\n✓ All results saved to: {output_dir}")


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=f'Train {MODEL_ID} Bayesian model'
    )
    parser.add_argument('--draws', type=int, default=DEFAULT_CONFIG['draws'],
                        help='Number of posterior samples per chain')
    parser.add_argument('--tune', type=int, default=DEFAULT_CONFIG['tune'],
                        help='Number of tuning samples')
    parser.add_argument('--chains', type=int, default=DEFAULT_CONFIG['chains'],
                        help='Number of MCMC chains')
    parser.add_argument('--target-accept', type=float,
                        default=DEFAULT_CONFIG['target_accept'],
                        help='Target acceptance rate')
    parser.add_argument('--seed', type=int, default=DEFAULT_CONFIG['random_seed'],
                        help='Random seed')
    parser.add_argument('--gpu', action='store_true',
                        help='Force GPU sampling')
    parser.add_argument('--cpu', action='store_true',
                        help='Force CPU sampling')
    return parser.parse_args()


def main():
    """Main training pipeline."""
    args = parse_args()

    config = {
        'draws': args.draws,
        'tune': args.tune,
        'chains': args.chains,
        'target_accept': args.target_accept,
        'random_seed': args.seed
    }

    print("=" * 60)
    print(f"TRAINING: {MODEL_ID}")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Step 1: Load data
    print("\n[1/5] Loading training data...")
    data = load_training_data()

    # Step 2: Build model
    print("\n[2/5] Building model...")
    model = build_model(data)
    print("✓ Model built successfully")

    # Step 3: Sample
    print("\n[3/5] Sampling...")
    use_gpu = args.gpu or (not args.cpu)
    trace, sampling_time = sample_model(model, config, use_gpu=use_gpu)

    # Step 4: Check convergence
    print("\n[4/5] Checking convergence...")
    converged = check_convergence(trace)

    # Step 5: Save results
    print("\n[5/5] Saving results...")
    save_results(trace, MODEL_ID, sampling_time, config)

    # Summary
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Model: {MODEL_ID}")
    print(f"Time: {sampling_time:.2f}s ({sampling_time/60:.2f} min)")
    print(f"Convergence: {'✓ PASSED' if converged else '✗ ISSUES DETECTED'}")

    return 0 if converged else 1


if __name__ == '__main__':
    sys.exit(main())
