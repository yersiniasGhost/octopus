#!/usr/bin/env python3
"""
Test Hierarchical Model for GPU Validation

Simple 3-level hierarchical structure to validate:
1. PyMC + JAX sampling works on GPU
2. Non-centered parameterization compiles correctly
3. Convergence diagnostics pass
4. Posterior recovery matches true parameters
"""

import numpy as np
import pymc as pm
import pymc.sampling.jax as pmjax
import arviz as az
import jax
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from pathlib import Path

# Configuration
RANDOM_SEED = 42
N_GROUPS = 100
N_PER_GROUP = 10
DRAWS = 2000
TUNE = 1000
CHAINS = 4
TARGET_ACCEPT = 0.95

def generate_synthetic_data(seed=RANDOM_SEED):
    """Generate synthetic hierarchical data with known parameters."""
    np.random.seed(seed)

    # True population parameters
    true_μ_pop = 50.0
    true_σ_pop = 10.0
    true_σ_obs = 2.0

    # Generate group means from population
    true_μ_groups = np.random.normal(true_μ_pop, true_σ_pop, N_GROUPS)

    # Generate observations from group means
    n_obs = N_GROUPS * N_PER_GROUP
    group_idx = np.repeat(np.arange(N_GROUPS), N_PER_GROUP)
    y_obs = np.random.normal(true_μ_groups[group_idx], true_σ_obs)

    print("=" * 60)
    print("SYNTHETIC DATA GENERATION")
    print("=" * 60)
    print(f"True μ_pop: {true_μ_pop:.2f}")
    print(f"True σ_pop: {true_σ_pop:.2f}")
    print(f"True σ_obs: {true_σ_obs:.2f}")
    print(f"Number of groups: {N_GROUPS}")
    print(f"Observations per group: {N_PER_GROUP}")
    print(f"Total observations: {n_obs}")

    return {
        'y_obs': y_obs,
        'group_idx': group_idx,
        'n_groups': N_GROUPS,
        'true_params': {
            'μ_pop': true_μ_pop,
            'σ_pop': true_σ_pop,
            'σ_obs': true_σ_obs,
            'μ_groups': true_μ_groups
        }
    }

def build_hierarchical_model(data):
    """Build hierarchical model with non-centered parameterization."""

    with pm.Model() as model:
        # Hyperpriors (population-level)
        μ_pop = pm.Normal('μ_pop', 50, 20)
        σ_pop = pm.HalfNormal('σ_pop', 15)

        # Group-level with non-centered parameterization
        μ_group_z = pm.Normal('μ_group_z', 0, 1, shape=data['n_groups'])
        μ_group = pm.Deterministic('μ_group', μ_pop + σ_pop * μ_group_z)

        # Observation-level
        σ_obs = pm.HalfNormal('σ_obs', 5)
        y_pred = μ_group[data['group_idx']]
        y = pm.Normal('y', y_pred, σ_obs, observed=data['y_obs'])

    return model

def sample_gpu(model, data):
    """Sample using GPU-accelerated JAX backend."""
    print("\n" + "=" * 60)
    print("GPU SAMPLING (JAX + NumPyro)")
    print("=" * 60)

    # Verify GPU is available
    devices = jax.devices()
    print(f"JAX devices: {devices}")

    if not any('gpu' in str(d).lower() or 'cuda' in str(d).lower() for d in devices):
        print("⚠️  WARNING: No GPU detected, sampling will use CPU")

    with model:
        trace = pmjax.sample_numpyro_nuts(
            draws=DRAWS,
            tune=TUNE,
            chains=CHAINS,
            target_accept=TARGET_ACCEPT,
            random_seed=RANDOM_SEED,
            progressbar=True
        )

    print("✅ GPU sampling completed")
    return trace

def validate_convergence(trace, data):
    """Validate convergence and posterior recovery."""
    print("\n" + "=" * 60)
    print("CONVERGENCE DIAGNOSTICS")
    print("=" * 60)

    # R-hat
    rhat = az.rhat(trace)
    rhat_max = float(rhat.to_array().max().values)
    rhat_status = "✅ PASS" if rhat_max < 1.01 else "❌ FAIL"
    print(f"{rhat_status} Max R̂: {rhat_max:.4f} (threshold: < 1.01)")

    # Effective sample size
    ess = az.ess(trace)
    ess_min = float(ess.to_array().min().values)
    ess_status = "✅ PASS" if ess_min > 400 else "❌ FAIL"
    print(f"{ess_status} Min ESS: {ess_min:.0f} (threshold: > 400)")

    # Posterior recovery
    print("\n" + "=" * 60)
    print("POSTERIOR RECOVERY")
    print("=" * 60)

    posterior = trace.posterior

    # Population mean
    μ_pop_post = posterior['μ_pop'].values.flatten()
    μ_pop_mean = μ_pop_post.mean()
    μ_pop_hdi = az.hdi(trace, var_names=['μ_pop'], hdi_prob=0.89)['μ_pop'].values
    true_μ_pop = data['true_params']['μ_pop']
    μ_pop_recovered = μ_pop_hdi[0] <= true_μ_pop <= μ_pop_hdi[1]
    μ_pop_status = "✅ RECOVERED" if μ_pop_recovered else "⚠️  OUTSIDE HDI"

    print(f"{μ_pop_status} μ_pop:")
    print(f"   True: {true_μ_pop:.2f}")
    print(f"   Posterior mean: {μ_pop_mean:.2f}")
    print(f"   89% HDI: [{μ_pop_hdi[0]:.2f}, {μ_pop_hdi[1]:.2f}]")

    # Population std
    σ_pop_post = posterior['σ_pop'].values.flatten()
    σ_pop_mean = σ_pop_post.mean()
    σ_pop_hdi = az.hdi(trace, var_names=['σ_pop'], hdi_prob=0.89)['σ_pop'].values
    true_σ_pop = data['true_params']['σ_pop']
    σ_pop_recovered = σ_pop_hdi[0] <= true_σ_pop <= σ_pop_hdi[1]
    σ_pop_status = "✅ RECOVERED" if σ_pop_recovered else "⚠️  OUTSIDE HDI"

    print(f"{σ_pop_status} σ_pop:")
    print(f"   True: {true_σ_pop:.2f}")
    print(f"   Posterior mean: {σ_pop_mean:.2f}")
    print(f"   89% HDI: [{σ_pop_hdi[0]:.2f}, {σ_pop_hdi[1]:.2f}]")

    # Observation std
    σ_obs_post = posterior['σ_obs'].values.flatten()
    σ_obs_mean = σ_obs_post.mean()
    σ_obs_hdi = az.hdi(trace, var_names=['σ_obs'], hdi_prob=0.89)['σ_obs'].values
    true_σ_obs = data['true_params']['σ_obs']
    σ_obs_recovered = σ_obs_hdi[0] <= true_σ_obs <= σ_obs_hdi[1]
    σ_obs_status = "✅ RECOVERED" if σ_obs_recovered else "⚠️  OUTSIDE HDI"

    print(f"{σ_obs_status} σ_obs:")
    print(f"   True: {true_σ_obs:.2f}")
    print(f"   Posterior mean: {σ_obs_mean:.2f}")
    print(f"   89% HDI: [{σ_obs_hdi[0]:.2f}, {σ_obs_hdi[1]:.2f}]")

    # Overall validation
    all_passed = (rhat_max < 1.01 and ess_min > 400 and
                  μ_pop_recovered and σ_pop_recovered and σ_obs_recovered)

    return {
        'passed': all_passed,
        'rhat_max': rhat_max,
        'ess_min': ess_min,
        'μ_pop_recovered': μ_pop_recovered,
        'σ_pop_recovered': σ_pop_recovered,
        'σ_obs_recovered': σ_obs_recovered
    }

def plot_diagnostics(trace, data, output_dir='../../reports/phase0'):
    """Generate diagnostic plots."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Trace plot
    az.plot_trace(trace, var_names=['μ_pop', 'σ_pop', 'σ_obs'])
    plt.tight_layout()
    plt.savefig(f'{output_dir}/trace_plot.png', dpi=150)
    plt.close()

    # Posterior plot
    az.plot_posterior(trace, var_names=['μ_pop', 'σ_pop', 'σ_obs'],
                      hdi_prob=0.89)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/posterior_plot.png', dpi=150)
    plt.close()

    # Forest plot
    az.plot_forest(trace, var_names=['μ_pop', 'σ_pop', 'σ_obs'],
                   hdi_prob=0.89, combined=True)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/forest_plot.png', dpi=150)
    plt.close()

    print(f"\n✅ Diagnostic plots saved to {output_dir}/")

def main():
    """Run complete GPU validation workflow."""
    print("\n🚀 Test Hierarchical Model - GPU Validation\n")

    # Generate data
    data = generate_synthetic_data()

    # Build model
    model = build_hierarchical_model(data)
    print("\n✅ Model built successfully")

    # Sample on GPU
    trace = sample_gpu(model, data)

    # Validate
    validation = validate_convergence(trace, data)

    # Plot diagnostics
    plot_diagnostics(trace, data)

    # Save trace
    output_path = Path('../../reports/phase0/traces/test_trace.nc')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trace.to_netcdf(str(output_path))
    print(f"\n✅ Trace saved to {output_path}")

    # Final summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    if validation['passed']:
        print("🎉 All validation checks PASSED")
        print("   GPU-accelerated sampling is working correctly")
        return 0
    else:
        print("❌ Some validation checks FAILED")
        print("   Review diagnostics above")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
