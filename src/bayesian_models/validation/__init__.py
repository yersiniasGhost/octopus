"""
Bayesian Model Validation Framework

Provides comprehensive validation tools for Bayesian models including:
- Convergence diagnostics (R-hat, ESS, divergences)
- Posterior predictive checks
- Causal identification validation (E-values)
- Cross-validation (PSIS-LOO)
- Visual diagnostics for UI integration

Usage:
    from src.bayesian_models.validation import ModelValidator

    validator = ModelValidator(trace, model)
    report = validator.full_validation()
"""

from .validator import ModelValidator
from .diagnostics import (
    check_convergence,
    compute_e_values,
    posterior_predictive_check,
    compute_loo
)
from .visualizations import (
    create_trace_plot,
    create_forest_plot,
    create_posterior_predictive_plot,
    create_calibration_plot
)

__all__ = [
    'ModelValidator',
    'check_convergence',
    'compute_e_values',
    'posterior_predictive_check',
    'compute_loo',
    'create_trace_plot',
    'create_forest_plot',
    'create_posterior_predictive_plot',
    'create_calibration_plot'
]
