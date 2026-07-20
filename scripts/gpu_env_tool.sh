# Source this to run PyMC/JAX on the GPU from the repo venv.
# Fix: prepend the venv's pip-installed nvidia CUDA 12.9 libs so they are not
# shadowed by the system CUDA 12.4 toolkit in /usr/local/cuda (which exports an
# older libcublasLt.so.12 lacking cublasLtGetEnvironmentMode).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/venv/bin/activate"
NVIDIA_LIB_PATH="$(echo "$REPO_ROOT"/venv/lib/python3.10/site-packages/nvidia/*/lib | tr ' ' ':')"
export LD_LIBRARY_PATH="$NVIDIA_LIB_PATH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
