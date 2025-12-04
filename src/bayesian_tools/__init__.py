"""
Bayesian Tools for Data Preparation and Diagnostics

This package provides utilities for:
- Data preparation and preprocessing
- Model diagnostics and quality checks
- Convergence assessment
- Posterior predictive checks
- Model comparison
"""

from .data_preparation import BayesianDataPrep, get_model_matrices
from .diagnostics import BayesianDiagnostics, check_model_quality

__all__ = [
    'BayesianDataPrep',
    'get_model_matrices',
    'BayesianDiagnostics',
    'check_model_quality',
]

__version__ = '0.1.0'
