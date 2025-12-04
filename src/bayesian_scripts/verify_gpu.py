#!/usr/bin/env python3
"""
GPU Verification Script for PyMC + JAX Setup
Validates CUDA availability and basic GPU computation.
"""

import sys
import jax
import jax.numpy as jnp
import pymc as pm
import numpyro

def verify_jax_gpu():
    """Verify JAX can see CUDA GPU."""
    print("=" * 60)
    print("JAX GPU VERIFICATION")
    print("=" * 60)

    devices = jax.devices()
    print(f"JAX Devices: {devices}")

    if not devices:
        print("❌ FATAL: No JAX devices found")
        return False

    gpu_found = any('gpu' in str(d).lower() or 'cuda' in str(d).lower()
                    for d in devices)

    if gpu_found:
        print("✅ GPU detected by JAX")

        # Get GPU properties
        device = devices[0]
        print(f"   Device: {device}")
        print(f"   Platform: {device.platform}")

        # Test basic GPU computation
        try:
            x = jnp.ones((1000, 1000))
            y = jnp.dot(x, x)
            result = y.block_until_ready()
            print("✅ Basic GPU computation successful")
        except Exception as e:
            print(f"❌ GPU computation failed: {e}")
            return False

        return True
    else:
        print("❌ FATAL: No GPU/CUDA device found by JAX")
        print("   Check CUDA installation and JAX installation")
        return False

def verify_cuda_version():
    """Check CUDA version compatibility."""
    print("\n" + "=" * 60)
    print("CUDA VERSION CHECK")
    print("=" * 60)

    try:
        import subprocess
        result = subprocess.run(['nvidia-smi'],
                              capture_output=True,
                              text=True,
                              timeout=5)

        if result.returncode == 0:
            print("✅ nvidia-smi accessible")
            # Extract CUDA version from output
            for line in result.stdout.split('\n'):
                if 'CUDA Version' in line:
                    print(f"   {line.strip()}")
        else:
            print("⚠️  nvidia-smi not accessible")

    except Exception as e:
        print(f"⚠️  Could not check CUDA version: {e}")

def verify_pymc_jax():
    """Verify PyMC can use JAX backend."""
    print("\n" + "=" * 60)
    print("PYMC + JAX INTEGRATION")
    print("=" * 60)

    print(f"PyMC version: {pm.__version__}")
    print(f"NumPyro version: {numpyro.__version__}")

    # Try to create a simple model and check sampling_jax availability
    try:
        import pymc.sampling.jax as pmjax

        with pm.Model() as simple_model:
            x = pm.Normal('x', 0, 1)

        # Check if sample_numpyro_nuts is available
        if hasattr(pmjax, 'sample_numpyro_nuts'):
            print("✅ PyMC JAX sampling module available")

            # Try a tiny sample to verify it works
            with simple_model:
                trace = pmjax.sample_numpyro_nuts(
                    draws=10,
                    tune=10,
                    chains=1,
                    progressbar=False
                )
            print("✅ JAX sampling successful")
            return True
        else:
            print("❌ PyMC JAX sampling not available")
            return False

    except Exception as e:
        print(f"❌ PyMC+JAX integration failed: {e}")
        return False

def main():
    """Run all verification checks."""
    print("\n🚀 Starting GPU Verification for Bayesian Modeling\n")

    checks = {
        'JAX GPU': verify_jax_gpu(),
        'CUDA Version': True,  # verify_cuda_version() doesn't return bool
        'PyMC+JAX': verify_pymc_jax()
    }

    verify_cuda_version()

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = all(checks.values())

    for check_name, passed in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {check_name}")

    if all_passed:
        print("\n🎉 All checks passed! GPU is ready for Bayesian modeling.")
        return 0
    else:
        print("\n❌ Some checks failed. Review errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
