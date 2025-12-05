#!/usr/bin/env python3
"""
GPU Verification Script for Bayesian Modeling

This script verifies:
1. JAX installation and GPU availability
2. PyMC installation and configuration
3. CUDA/GPU compute capability
4. Memory availability for model fitting

Run this before fitting models to ensure GPU acceleration is available.
"""

import sys
import platform


def check_system_info():
    """Print system information."""
    print("=" * 60)
    print("SYSTEM INFORMATION")
    print("=" * 60)
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"Processor: {platform.processor()}")
    print()


def check_jax():
    """Check JAX installation and GPU availability."""
    print("=" * 60)
    print("JAX VERIFICATION")
    print("=" * 60)

    try:
        import jax
        print(f"✅ JAX installed: version {jax.__version__}")

        # Check available devices
        devices = jax.devices()
        print(f"\nAvailable devices: {len(devices)}")
        for i, device in enumerate(devices):
            print(f"  Device {i}: {device.device_kind} - {device}")

        # Check for GPU
        gpu_devices = [d for d in devices if d.device_kind == 'gpu']
        if gpu_devices:
            print(f"\n✅ GPU acceleration available: {len(gpu_devices)} GPU(s)")
            for i, gpu in enumerate(gpu_devices):
                print(f"  GPU {i}: {gpu}")
        else:
            print("\n⚠️  No GPU devices found - will use CPU")
            print("   JAX will run on CPU, which is slower for large models")

        # Test basic JAX operation
        print("\nTesting JAX computation...")
        import jax.numpy as jnp
        x = jnp.array([1.0, 2.0, 3.0])
        y = jnp.sum(x ** 2)
        print(f"  Test computation: sum([1, 2, 3]^2) = {y}")
        print("  ✅ JAX computations working")

        return True

    except ImportError as e:
        print(f"❌ JAX not installed: {e}")
        print("\nInstall JAX with:")
        print("  pip install jax jaxlib")
        print("\nFor GPU support:")
        print("  pip install jax[cuda12]")
        return False


def check_pymc():
    """Check PyMC installation and configuration."""
    print("\n" + "=" * 60)
    print("PYMC VERIFICATION")
    print("=" * 60)

    try:
        import pymc as pm
        print(f"✅ PyMC installed: version {pm.__version__}")

        # Check sampling backend
        print(f"\nDefault sampling backend: {pm.NUTS}")

        # Test basic model creation
        print("\nTesting basic model creation...")
        with pm.Model() as test_model:
            x = pm.Normal("x", mu=0, sigma=1)
            print("  ✅ Model creation working")

        # Check if JAX is being used
        try:
            import pymc.sampling.jax as pmjax
            print("  ✅ PyMC JAX backend available")
        except ImportError:
            print("  ⚠️  PyMC JAX backend not available")

        return True

    except ImportError as e:
        print(f"❌ PyMC not installed: {e}")
        print("\nInstall PyMC with:")
        print("  pip install pymc")
        return False


def check_arviz():
    """Check ArviZ installation for diagnostics."""
    print("\n" + "=" * 60)
    print("ARVIZ VERIFICATION")
    print("=" * 60)

    try:
        import arviz as az
        print(f"✅ ArviZ installed: version {az.__version__}")

        # Test basic operations
        print("\nTesting ArviZ operations...")
        import numpy as np
        test_data = az.from_dict({"x": np.random.randn(1000, 2)})
        summary = az.summary(test_data)
        print("  ✅ ArviZ diagnostics working")

        return True

    except ImportError as e:
        print(f"❌ ArviZ not installed: {e}")
        print("\nInstall ArviZ with:")
        print("  pip install arviz")
        return False


def check_gpu_memory():
    """Check GPU memory if available."""
    print("\n" + "=" * 60)
    print("GPU MEMORY CHECK")
    print("=" * 60)

    try:
        import jax
        devices = jax.devices()
        gpu_devices = [d for d in devices if d.device_kind == 'gpu']

        if not gpu_devices:
            print("⚠️  No GPU devices found")
            return False

        # Try to query GPU memory using nvidia-smi
        try:
            import subprocess
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.total,memory.free,memory.used',
                 '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                check=True
            )

            print("GPU Memory Status:")
            for i, line in enumerate(result.stdout.strip().split('\n')):
                total, free, used = line.split(',')
                total_gb = float(total) / 1024
                free_gb = float(free) / 1024
                used_gb = float(used) / 1024

                print(f"\n  GPU {i}:")
                print(f"    Total: {total_gb:.2f} GB")
                print(f"    Free:  {free_gb:.2f} GB")
                print(f"    Used:  {used_gb:.2f} GB")

                if free_gb < 2.0:
                    print(f"    ⚠️  Low free memory - may need to reduce model size")
                else:
                    print(f"    ✅ Sufficient memory for most models")

            return True

        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  Could not query GPU memory (nvidia-smi not available)")
            return False

    except Exception as e:
        print(f"❌ Error checking GPU memory: {e}")
        return False


def run_simple_benchmark():
    """Run a simple benchmark to test performance."""
    print("\n" + "=" * 60)
    print("SIMPLE PERFORMANCE BENCHMARK")
    print("=" * 60)

    try:
        import time
        import pymc as pm
        import numpy as np

        print("\nFitting simple logistic regression model...")
        print("  100 observations, 2 predictors, 500 samples × 2 chains")

        # Generate synthetic data
        np.random.seed(42)
        n = 100
        X = np.random.randn(n, 2)
        y = (X[:, 0] + 0.5 * X[:, 1] + np.random.randn(n) * 0.5 > 0).astype(int)

        # Fit model
        with pm.Model() as simple_model:
            beta = pm.Normal("beta", mu=0, sigma=1, shape=2)
            logit_p = pm.math.dot(X, beta)
            y_obs = pm.Bernoulli("y", logit_p=logit_p, observed=y)

            start_time = time.time()
            trace = pm.sample(
                draws=500,
                tune=500,
                chains=2,
                return_inferencedata=True,
                progressbar=False,
            )
            elapsed = time.time() - start_time

        print(f"\n  ✅ Sampling completed in {elapsed:.2f} seconds")

        if elapsed < 10:
            print("  🚀 Fast sampling (likely using GPU)")
        elif elapsed < 30:
            print("  ✅ Reasonable sampling speed")
        else:
            print("  ⚠️  Slow sampling - check GPU configuration")

        # Check convergence
        import arviz as az
        summary = az.summary(trace)
        rhat_max = summary['r_hat'].max()

        if rhat_max < 1.01:
            print(f"  ✅ Good convergence (max R-hat = {rhat_max:.4f})")
        else:
            print(f"  ⚠️  Convergence issues (max R-hat = {rhat_max:.4f})")

        return True

    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification checks."""
    print("\n" + "🔍 " * 20)
    print("BAYESIAN MODELING GPU VERIFICATION")
    print("🔍 " * 20 + "\n")

    results = {}

    # Run checks
    check_system_info()
    results['jax'] = check_jax()
    results['pymc'] = check_pymc()
    results['arviz'] = check_arviz()
    results['gpu_memory'] = check_gpu_memory()

    # Run benchmark if basic checks pass
    if results['pymc'] and results['arviz']:
        results['benchmark'] = run_simple_benchmark()

    # Final summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = all(results.values())

    if all_passed:
        print("✅ All checks passed - ready for Bayesian modeling!")
        print("\nYou can now run:")
        print("  python src/bayesian_scripts/bayes_fit_model_01.py")
        print("  python src/bayesian_scripts/bayes_fit_model_02.py")
    else:
        print("⚠️  Some checks failed - see details above")
        print("\nInstall missing dependencies:")
        if not results.get('jax'):
            print("  pip install jax jaxlib")
        if not results.get('pymc'):
            print("  pip install pymc")
        if not results.get('arviz'):
            print("  pip install arviz")

    print("\n" + "=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
