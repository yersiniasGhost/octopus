#!/usr/bin/env python3
"""
CPU vs GPU Performance Benchmark

Compares sampling performance between CPU and GPU backends
for the test hierarchical model.
"""

import time
import numpy as np
import pymc as pm
import pymc.sampling.jax as pmjax
import arviz as az
import jax
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from bayesian_models.test_hierarchical_gpu import generate_synthetic_data, build_hierarchical_model

# Configuration
RANDOM_SEED = 42
DRAWS = 2000
TUNE = 1000
CHAINS = 4
TARGET_ACCEPT = 0.95

def benchmark_cpu(model):
    """Benchmark CPU sampling."""
    print("\n" + "=" * 60)
    print("CPU BENCHMARK (PyMC Native)")
    print("=" * 60)

    start_time = time.time()

    with model:
        trace = pm.sample(
            draws=DRAWS,
            tune=TUNE,
            chains=CHAINS,
            cores=CHAINS,
            target_accept=TARGET_ACCEPT,
            random_seed=RANDOM_SEED,
            progressbar=True
        )

    elapsed_time = time.time() - start_time

    print(f"\n✅ CPU sampling completed")
    print(f"   Total time: {elapsed_time:.2f} seconds")
    print(f"   Time per 1000 samples: {elapsed_time/(DRAWS*CHAINS)*1000:.2f} seconds")

    # Quick convergence check
    rhat_max = float(az.rhat(trace).to_array().max())
    print(f"   Max R̂: {rhat_max:.4f}")

    return {
        'trace': trace,
        'elapsed_time': elapsed_time,
        'time_per_1000': elapsed_time/(DRAWS*CHAINS)*1000,
        'rhat_max': rhat_max
    }

def benchmark_gpu(model):
    """Benchmark GPU sampling."""
    print("\n" + "=" * 60)
    print("GPU BENCHMARK (JAX + NumPyro)")
    print("=" * 60)

    # Verify GPU
    devices = jax.devices()
    print(f"JAX devices: {devices}")

    if not any('gpu' in str(d).lower() or 'cuda' in str(d).lower() for d in devices):
        print("⚠️  WARNING: No GPU detected, benchmark may use CPU")

    start_time = time.time()

    with model:
        trace = pmjax.sample_numpyro_nuts(
            draws=DRAWS,
            tune=TUNE,
            chains=CHAINS,
            target_accept=TARGET_ACCEPT,
            random_seed=RANDOM_SEED,
            progressbar=True
        )

    elapsed_time = time.time() - start_time

    print(f"\n✅ GPU sampling completed")
    print(f"   Total time: {elapsed_time:.2f} seconds")
    print(f"   Time per 1000 samples: {elapsed_time/(DRAWS*CHAINS)*1000:.2f} seconds")

    # Quick convergence check
    rhat_max = float(az.rhat(trace).to_array().max())
    print(f"   Max R̂: {rhat_max:.4f}")

    return {
        'trace': trace,
        'elapsed_time': elapsed_time,
        'time_per_1000': elapsed_time/(DRAWS*CHAINS)*1000,
        'rhat_max': rhat_max
    }

def compare_posteriors(cpu_results, gpu_results):
    """Compare posterior distributions between CPU and GPU."""
    print("\n" + "=" * 60)
    print("POSTERIOR COMPARISON")
    print("=" * 60)

    cpu_trace = cpu_results['trace']
    gpu_trace = gpu_results['trace']

    params = ['μ_pop', 'σ_pop', 'σ_obs']

    for param in params:
        cpu_mean = cpu_trace.posterior[param].values.flatten().mean()
        gpu_mean = gpu_trace.posterior[param].values.flatten().mean()

        cpu_std = cpu_trace.posterior[param].values.flatten().std()
        gpu_std = gpu_trace.posterior[param].values.flatten().std()

        mean_diff_pct = abs(cpu_mean - gpu_mean) / cpu_mean * 100
        std_diff_pct = abs(cpu_std - gpu_std) / cpu_std * 100

        status = "✅ MATCH" if mean_diff_pct < 5 and std_diff_pct < 10 else "⚠️  DIFFER"

        print(f"\n{status} {param}:")
        print(f"   CPU mean: {cpu_mean:.4f} ± {cpu_std:.4f}")
        print(f"   GPU mean: {gpu_mean:.4f} ± {gpu_std:.4f}")
        print(f"   Mean difference: {mean_diff_pct:.2f}%")
        print(f"   Std difference: {std_diff_pct:.2f}%")

def generate_report(cpu_results, gpu_results, output_dir='../../reports/phase0'):
    """Generate performance comparison report."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Calculate speedup
    speedup = cpu_results['elapsed_time'] / gpu_results['elapsed_time']

    # Performance comparison plot
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Timing comparison
    backends = ['CPU', 'GPU']
    times = [cpu_results['elapsed_time'], gpu_results['elapsed_time']]
    colors = ['#3498db', '#2ecc71']

    axes[0].bar(backends, times, color=colors, alpha=0.7)
    axes[0].set_ylabel('Total Sampling Time (seconds)')
    axes[0].set_title('CPU vs GPU Performance')
    axes[0].grid(axis='y', alpha=0.3)

    # Add speedup annotation
    axes[0].text(1, gpu_results['elapsed_time'],
                f'{speedup:.2f}x\nspeedup',
                ha='center', va='bottom', fontsize=12, fontweight='bold')

    # Samples per second
    cpu_samples_per_sec = (DRAWS * CHAINS) / cpu_results['elapsed_time']
    gpu_samples_per_sec = (DRAWS * CHAINS) / gpu_results['elapsed_time']

    samples = [cpu_samples_per_sec, gpu_samples_per_sec]
    axes[1].bar(backends, samples, color=colors, alpha=0.7)
    axes[1].set_ylabel('Samples per Second')
    axes[1].set_title('Sampling Throughput')
    axes[1].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(f'{output_dir}/performance_comparison.png', dpi=150)
    plt.close()

    # Write text report
    report_path = f'{output_dir}/benchmark_report.txt'
    with open(report_path, 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("CPU vs GPU BENCHMARK REPORT\n")
        f.write("=" * 60 + "\n\n")

        f.write("Configuration:\n")
        f.write(f"  Draws: {DRAWS}\n")
        f.write(f"  Tune: {TUNE}\n")
        f.write(f"  Chains: {CHAINS}\n")
        f.write(f"  Target Accept: {TARGET_ACCEPT}\n\n")

        f.write("CPU Results:\n")
        f.write(f"  Total time: {cpu_results['elapsed_time']:.2f} seconds\n")
        f.write(f"  Samples/sec: {cpu_samples_per_sec:.2f}\n")
        f.write(f"  Max R̂: {cpu_results['rhat_max']:.4f}\n\n")

        f.write("GPU Results:\n")
        f.write(f"  Total time: {gpu_results['elapsed_time']:.2f} seconds\n")
        f.write(f"  Samples/sec: {gpu_samples_per_sec:.2f}\n")
        f.write(f"  Max R̂: {gpu_results['rhat_max']:.4f}\n\n")

        f.write(f"Speedup: {speedup:.2f}x\n\n")

        if speedup >= 3.0:
            f.write("✅ PASS: Speedup meets target (≥3x)\n")
        else:
            f.write(f"⚠️  WARNING: Speedup below target ({speedup:.2f}x < 3x)\n")

    print(f"\n✅ Report saved to {report_path}")

    return speedup

def main():
    """Run complete benchmark workflow."""
    print("\n🚀 CPU vs GPU Performance Benchmark\n")

    # Generate data
    data = generate_synthetic_data()

    # Build model
    model = build_hierarchical_model(data)

    # Run benchmarks
    cpu_results = benchmark_cpu(model)
    gpu_results = benchmark_gpu(model)

    # Compare posteriors
    compare_posteriors(cpu_results, gpu_results)

    # Generate report
    speedup = generate_report(cpu_results, gpu_results)

    # Final summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"CPU time: {cpu_results['elapsed_time']:.2f} seconds")
    print(f"GPU time: {gpu_results['elapsed_time']:.2f} seconds")
    print(f"Speedup: {speedup:.2f}x")

    if speedup >= 3.0:
        print("\n🎉 SUCCESS: GPU speedup meets target (≥3x)")
        return 0
    else:
        print(f"\n⚠️  WARNING: GPU speedup below target ({speedup:.2f}x < 3x)")
        print("   This is still functional but may indicate:")
        print("   - GPU overhead dominates for this small model")
        print("   - CUDA/JAX configuration issues")
        print("   - Expected behavior for simple hierarchical structure")
        return 0  # Not a failure, just FYI

if __name__ == '__main__':
    import sys
    sys.exit(main())
