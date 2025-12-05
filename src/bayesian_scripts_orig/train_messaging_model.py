#!/usr/bin/env python3
"""
Phase 1A: Train Messaging Effectiveness Model

GPU-accelerated training using JAX/NumPyro backend for PyMC.

Created: 2025-10-15
"""

import pickle
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
import seaborn as sns

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from bayesian_models.messaging_effectiveness_model import (
    build_messaging_model,
    get_model_summary,
    predict_campaign_performance
)


# === CONFIGURATION ===

DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'processed'

# Output directory will be set based on phase (1a or 1c)
# This will be created in main() once we know which phase we're running
OUTPUT_DIR = None
TRACE_DIR = None
PLOTS_DIR = None

# Sampling configuration
# Phase 1C may need more tuning iterations due to increased complexity
SAMPLING_CONFIG_POC = {
    'draws': 2000,
    'tune': 1000,
    'chains': 4,
    'target_accept': 0.95,
    'random_seed': 42
}

SAMPLING_CONFIG_FULL = {
    'draws': 2000,
    'tune': 1500,  # More tuning for full dataset
    'chains': 4,
    'target_accept': 0.95,
    'random_seed': 42
}


def load_prepared_data(data_type='train', dataset='poc'):
    """Load prepared data from pickle file.

    Parameters
    ----------
    data_type : str
        'train', 'val', or 'full'
    dataset : str
        'poc' (Phase 1A, 15 campaigns) or 'full' (Phase 1C, all campaigns)
    """
    if data_type == 'train':
        data_file = DATA_DIR / f'messaging_{dataset}_train_data.pkl'
    elif data_type == 'val':
        data_file = DATA_DIR / f'messaging_{dataset}_val_data.pkl'
    else:  # 'full'
        data_file = DATA_DIR / f'messaging_{dataset}_data.pkl'

    print(f"Loading data from {data_file}...")
    with open(data_file, 'rb') as f:
        data = pickle.load(f)

    return data


def check_jax_devices():
    """Verify JAX can see GPU."""
    import jax
    print("\n" + "="*60)
    print("JAX DEVICE CHECK")
    print("="*60)
    devices = jax.devices()
    print(f"JAX devices: {devices}")
    if any('gpu' in str(d).lower() or 'cuda' in str(d).lower() for d in devices):
        print("✅ GPU detected by JAX")
        return True
    else:
        print("⚠️  No GPU detected - will use CPU")
        return False


def sample_model_gpu(model, data, config):
    """
    Sample model using JAX/NumPyro backend for GPU acceleration.

    Parameters
    ----------
    model : pm.Model
        PyMC model to sample
    data : Dict
        Data dictionary
    config : Dict
        Sampling configuration (SAMPLING_CONFIG_POC or SAMPLING_CONFIG_FULL)

    Returns
    -------
    trace : arviz.InferenceData
        MCMC trace
    sampling_time : float
        Total sampling time in seconds
    """
    print("\n" + "="*60)
    print("GPU SAMPLING (JAX + NumPyro)")
    print("="*60)

    has_gpu = check_jax_devices()

    print(f"\nSampling Configuration:")
    print(f"  Draws: {config['draws']}")
    print(f"  Tune: {config['tune']}")
    print(f"  Chains: {config['chains']}")
    print(f"  Target accept: {config['target_accept']}")
    print(f"  Random seed: {config['random_seed']}")

    start_time = time.time()

    with model:
        # Use JAX sampler (NumPyro NUTS)
        try:
            # Try newer API first
            trace = pm.sample(
                draws=config['draws'],
                tune=config['tune'],
                chains=config['chains'],
                target_accept=config['target_accept'],
                random_seed=config['random_seed'],
                nuts_sampler='numpyro',
                progress_bar=True
            )
        except TypeError:
            # Fallback to older API
            import pymc.sampling.jax
            trace = pymc.sampling.jax.sample_numpyro_nuts(
                draws=config['draws'],
                tune=config['tune'],
                chains=config['chains'],
                target_accept=config['target_accept'],
                random_seed=config['random_seed'],
                progress_bar=True
            )

    sampling_time = time.time() - start_time

    print(f"\n✅ Sampling completed in {sampling_time:.2f} seconds")
    print(f"   ({sampling_time/60:.2f} minutes)")

    return trace, sampling_time


def check_convergence(trace, threshold_rhat=1.01, threshold_ess=400):
    """
    Check MCMC convergence diagnostics.

    Parameters
    ----------
    trace : arviz.InferenceData
        MCMC trace
    threshold_rhat : float
        Maximum acceptable R̂ value
    threshold_ess : int
        Minimum acceptable ESS

    Returns
    -------
    bool
        True if all diagnostics pass
    """
    print("\n" + "="*60)
    print("CONVERGENCE DIAGNOSTICS")
    print("="*60)

    # Compute diagnostics
    summary = az.summary(trace, hdi_prob=0.89)

    # R̂ check
    max_rhat = summary['r_hat'].max()
    rhat_pass = max_rhat < threshold_rhat

    print(f"\nR̂ Diagnostic:")
    print(f"  Max R̂: {max_rhat:.4f}")
    print(f"  Threshold: < {threshold_rhat}")
    if rhat_pass:
        print(f"  ✅ PASS: All parameters converged")
    else:
        print(f"  ❌ FAIL: Some parameters did not converge")
        print(f"\nParameters with R̂ > {threshold_rhat}:")
        bad_params = summary[summary['r_hat'] > threshold_rhat]
        print(bad_params[['mean', 'sd', 'r_hat']])

    # ESS check
    min_ess_bulk = summary['ess_bulk'].min()
    min_ess_tail = summary['ess_tail'].min()
    ess_pass = (min_ess_bulk > threshold_ess) and (min_ess_tail > threshold_ess)

    print(f"\nESS Diagnostic:")
    print(f"  Min ESS (bulk): {min_ess_bulk:.0f}")
    print(f"  Min ESS (tail): {min_ess_tail:.0f}")
    print(f"  Threshold: > {threshold_ess}")
    if ess_pass:
        print(f"  ✅ PASS: Sufficient effective sample size")
    else:
        print(f"  ⚠️  WARNING: Low effective sample size")

    # Divergences check
    divergences = int(trace.sample_stats.diverging.sum())
    div_pass = divergences == 0

    print(f"\nDivergences:")
    print(f"  Count: {divergences}")
    if div_pass:
        print(f"  ✅ PASS: No divergences")
    else:
        print(f"  ⚠️  WARNING: {divergences} divergent transitions detected")

    all_pass = rhat_pass and ess_pass and div_pass

    print("\n" + "="*60)
    if all_pass:
        print("✅ ALL CONVERGENCE CHECKS PASSED")
    else:
        print("⚠️  SOME CONVERGENCE ISSUES DETECTED")
    print("="*60)

    return all_pass


def generate_diagnostic_plots(trace, data, output_dir=PLOTS_DIR):
    """Generate diagnostic plots for model validation."""
    print("\n" + "="*60)
    print("GENERATING DIAGNOSTIC PLOTS")
    print("="*60)

    # Set style
    sns.set_style('whitegrid')
    plt.rcParams['figure.dpi'] = 100

    # 1. Trace plot (key parameters)
    print("  → Trace plots...")
    fig, axes = plt.subplots(4, 2, figsize=(12, 10))
    az.plot_trace(
        trace,
        var_names=['mu_alpha_open', 'sigma_alpha_open',
                   'mu_alpha_click', 'sigma_alpha_click'],
        axes=axes
    )
    plt.tight_layout()
    trace_file = output_dir / 'trace_plot.png'
    plt.savefig(trace_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"     Saved: {trace_file}")

    # 2. Posterior distributions
    print("  → Posterior distributions...")
    fig = plt.figure(figsize=(14, 10))
    az.plot_posterior(
        trace,
        var_names=['mu_alpha_open', 'sigma_alpha_open',
                   'mu_alpha_click', 'sigma_alpha_click',
                   'beta_savings_open', 'beta_savings_click',
                   'beta_cost_open', 'beta_cost_click'],
        hdi_prob=0.89
    )
    plt.tight_layout()
    posterior_file = output_dir / 'posterior_distributions.png'
    plt.savefig(posterior_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"     Saved: {posterior_file}")

    # 3. Message type effects comparison
    print("  → Message type effects...")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Open rate effects
    az.plot_forest(
        trace,
        var_names=['msg_type_effect_open'],
        hdi_prob=0.89,
        ax=axes[0]
    )
    axes[0].set_title('Message Type Effects on Open Rate')
    axes[0].set_xlabel('Effect on Log-Odds')

    # Click rate effects
    if 'msg_type_effect_click' in trace.posterior:
        az.plot_forest(
            trace,
            var_names=['msg_type_effect_click'],
            hdi_prob=0.89,
            ax=axes[1]
        )
        axes[1].set_title('Message Type Effects on Click Rate')
        axes[1].set_xlabel('Effect on Log-Odds')

    plt.tight_layout()
    effects_file = output_dir / 'message_type_effects.png'
    plt.savefig(effects_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"     Saved: {effects_file}")

    # 4. Campaign-level effects
    print("  → Campaign random effects...")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    az.plot_forest(
        trace,
        var_names=['alpha_open'],
        hdi_prob=0.89,
        ax=axes[0]
    )
    axes[0].set_title('Campaign Random Effects (Open Rate)')
    axes[0].set_xlabel('Campaign-Specific Intercept')

    if 'alpha_click' in trace.posterior:
        az.plot_forest(
            trace,
            var_names=['alpha_click'],
            hdi_prob=0.89,
            ax=axes[1]
        )
        axes[1].set_title('Campaign Random Effects (Click Rate)')
        axes[1].set_xlabel('Campaign-Specific Intercept')

    plt.tight_layout()
    campaign_file = output_dir / 'campaign_effects.png'
    plt.savefig(campaign_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"     Saved: {campaign_file}")

    print("\n✅ All diagnostic plots generated")


def save_results(trace, data, sampling_time, config, output_dir=OUTPUT_DIR):
    """Save model results and summary statistics."""
    print("\n" + "="*60)
    print("SAVING RESULTS")
    print("="*60)

    # Save trace
    trace_file = TRACE_DIR / 'messaging_model_trace.nc'
    trace.to_netcdf(trace_file)
    print(f"  ✅ Trace saved: {trace_file}")

    # Save summary statistics
    summary = az.summary(trace, hdi_prob=0.89)
    summary_file = output_dir / 'parameter_summary.csv'
    summary.to_csv(summary_file)
    print(f"  ✅ Parameter summary: {summary_file}")

    # Save campaign predictions
    campaign_predictions = []
    for i in range(data['n_campaigns']):
        pred = predict_campaign_performance(trace, data, i)
        campaign_id = data['campaign_names'][i]
        pred['campaign_id'] = campaign_id
        campaign_predictions.append(pred)

    pred_df = pd.DataFrame(campaign_predictions)
    pred_file = output_dir / 'campaign_predictions.csv'
    pred_df.to_csv(pred_file, index=False)
    print(f"  ✅ Campaign predictions: {pred_file}")

    # Save metadata
    metadata = {
        'sampling_time_seconds': sampling_time,
        'sampling_time_minutes': sampling_time / 60,
        'n_records': data['n_records'],
        'n_campaigns': data['n_campaigns'],
        'n_msg_types': data['n_msg_types'],
        'n_locations': data['n_locations'],
        'draws': config['draws'],
        'tune': config['tune'],
        'chains': config['chains'],
        'target_accept': config['target_accept']
    }

    metadata_file = output_dir / 'training_metadata.txt'
    with open(metadata_file, 'w') as f:
        f.write("Phase 1A Training Metadata\n")
        f.write("="*60 + "\n\n")
        for key, value in metadata.items():
            f.write(f"{key}: {value}\n")

    print(f"  ✅ Metadata: {metadata_file}")


def main():
    """Main training pipeline."""
    import sys

    # Check if running Phase 1C (full-scale)
    use_full_dataset = '--full' in sys.argv or '--phase1c' in sys.argv
    dataset_type = 'full' if use_full_dataset else 'poc'
    phase = "1C (FULL-SCALE)" if use_full_dataset else "1A (POC)"

    # Set output directory based on phase
    global OUTPUT_DIR, TRACE_DIR, PLOTS_DIR
    OUTPUT_DIR = Path(__file__).parent.parent.parent / 'reports' / f'phase{phase[0:2].lower()}'
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    TRACE_DIR = OUTPUT_DIR / 'traces'
    TRACE_DIR.mkdir(exist_ok=True)

    PLOTS_DIR = OUTPUT_DIR / 'diagnostic_plots'
    PLOTS_DIR.mkdir(exist_ok=True)

    print("="*60)
    print(f"PHASE {phase}: MESSAGING MODEL TRAINING")
    print("="*60)

    # Load training data
    print("\n[1] Loading training data...")
    train_data = load_prepared_data('train', dataset=dataset_type)

    print(f"\nTraining Data Summary:")
    print(f"  Records: {train_data['n_records']:,}")
    print(f"  Campaigns: {train_data['n_campaigns']}")
    print(f"  Message types: {train_data['n_msg_types']}")
    print(f"  Locations: {train_data['n_locations']}")
    print(f"  Opens: {train_data['opened'].sum()} ({train_data['opened'].mean():.1%})")
    if train_data['opened'].sum() > 0:
        print(f"  Clicks (of opened): {train_data['clicked'][train_data['opened']==1].sum()} "
              f"({train_data['clicked'][train_data['opened']==1].mean():.1%})")

    # Build model
    print("\n[2] Building hierarchical Bayesian model...")
    model = build_messaging_model(train_data)
    print("✅ Model built successfully")

    # Print model summary
    print("\nModel Structure:")
    print(f"  Stage 1: Open Rate")
    print(f"    - Campaign random effects: {train_data['n_campaigns']}")
    print(f"    - Message type effects: {train_data['n_msg_types']}")
    print(f"    - Location effects: {train_data['n_locations']}")
    print(f"    - Temporal effects: 12 (months)")
    print(f"    - Offer effects: 3 (savings, cost, kwh)")
    print(f"  Stage 2: Click Rate (conditional on open)")
    print(f"    - Campaign random effects: {train_data['n_campaigns']}")
    print(f"    - Message type effects: {train_data['n_msg_types']}")
    print(f"    - Location effects: {train_data['n_locations']}")
    print(f"    - Offer effects: 3 (savings, cost, kwh)")

    total_params = (
        train_data['n_campaigns'] * 2 +  # alpha_open, alpha_click
        train_data['n_msg_types'] * 2 +  # msg effects
        train_data['n_locations'] * 2 +  # location effects
        12 +  # month effects (open only)
        6 +   # offer effects (3 open + 3 click)
        4     # hyperparameters
    )
    print(f"\nTotal parameters: ~{total_params}")

    # Sample model (use appropriate config for dataset size)
    print("\n[3] Sampling with GPU acceleration...")
    sampling_config = SAMPLING_CONFIG_FULL if use_full_dataset else SAMPLING_CONFIG_POC
    trace, sampling_time = sample_model_gpu(model, train_data, config=sampling_config)

    # Check convergence
    print("\n[4] Checking convergence...")
    converged = check_convergence(trace)

    # Generate plots
    print("\n[5] Generating diagnostic plots...")
    generate_diagnostic_plots(trace, train_data, PLOTS_DIR)

    # Save results
    print("\n[6] Saving results...")
    save_results(trace, train_data, sampling_time, sampling_config, OUTPUT_DIR)

    # Final summary
    print("\n" + "="*60)
    print("✅ TRAINING COMPLETE")
    print("="*60)
    print(f"\nTotal training time: {sampling_time:.2f} seconds ({sampling_time/60:.2f} minutes)")
    print(f"Convergence: {'✅ PASS' if converged else '⚠️  ISSUES DETECTED'}")
    print(f"\nOutputs saved to: {OUTPUT_DIR}")
    print(f"  - Trace: {TRACE_DIR / 'messaging_model_trace.nc'}")
    print(f"  - Plots: {PLOTS_DIR}")
    print(f"  - Predictions: {OUTPUT_DIR / 'campaign_predictions.csv'}")

    print("\nNext steps:")
    print("  1. Review diagnostic plots")
    print("  2. Analyze campaign predictions")
    print("  3. Compare message type effectiveness")
    print("  4. Validate on holdout data")


if __name__ == '__main__':
    main()
