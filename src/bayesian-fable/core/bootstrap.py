"""Path bootstrap for the bayesian-fable folder.

The folder name contains a hyphen, so it cannot be imported as
``src.bayesian-fable``. Importing this module (or calling ``ensure_paths``)
puts the repo root (for ``src.*`` imports such as the canonical
``src.bayesian_models.validation`` diagnostics) and the bayesian-fable
directory itself (for ``core.*`` / ``models.*`` imports) on ``sys.path``.
"""
import sys
from pathlib import Path

FABLE_DIR = Path(__file__).resolve().parents[1]   # src/bayesian-fable
REPO_ROOT = FABLE_DIR.parents[1]                  # repo root
OUTPUT_ROOT = REPO_ROOT / 'data' / 'inference' / 'fable'


def ensure_paths() -> None:
    for path in (str(REPO_ROOT), str(FABLE_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)


ensure_paths()
