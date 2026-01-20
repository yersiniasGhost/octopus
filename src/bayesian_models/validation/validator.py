"""
ModelValidator: Comprehensive validation class for Bayesian models.

Provides a unified interface for all validation operations with both
programmatic access and UI-friendly output formats.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import json

import numpy as np
import arviz as az

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
    create_calibration_plot,
    create_treatment_effects_plot,
    create_e_value_plot,
    create_county_effects_map
)
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class ModelValidator:
    """
    Comprehensive validator for Bayesian models.

    Usage:
        validator = ModelValidator(trace)
        report = validator.full_validation()
        validator.generate_all_plots(output_dir)
    """

    def __init__(self, trace: az.InferenceData,
                 model_name: Optional[str] = None,
                 treatment_effects: Optional[Dict[str, Dict]] = None,
                 county_effects: Optional[Dict[str, Dict]] = None):
        """
        Initialize validator with trace and optional metadata.

        Args:
            trace: ArviZ InferenceData object
            model_name: Name of the model for reports
            treatment_effects: Pre-computed treatment effects
            county_effects: Pre-computed county effects
        """
        self.trace = trace
        self.model_name = model_name or "Bayesian Model"
        self.treatment_effects = treatment_effects
        self.county_effects = county_effects

        # Extract variable names from trace
        self.var_names = list(trace.posterior.data_vars.keys())

        # Validation results cache
        self._convergence = None
        self._ppc = None
        self._loo = None
        self._e_values = None

    def check_convergence(self, r_hat_threshold: float = 1.01,
                         ess_threshold: int = 400) -> Dict[str, Any]:
        """
        Run convergence diagnostics.

        Returns cached results if already computed.
        """
        if self._convergence is None:
            self._convergence = check_convergence(
                self.trace,
                r_hat_threshold=r_hat_threshold,
                ess_threshold=ess_threshold
            )
        return self._convergence

    def check_posterior_predictive(self, observed_var: str = 'y_clicked') -> Dict[str, Any]:
        """
        Run posterior predictive check.

        Returns cached results if already computed.
        """
        if self._ppc is None:
            self._ppc = posterior_predictive_check(self.trace, observed_var)
        return self._ppc

    def compute_loo(self, pointwise: bool = False) -> Dict[str, Any]:
        """
        Compute PSIS-LOO cross-validation.

        Returns cached results if already computed.
        """
        if self._loo is None or pointwise:
            self._loo = compute_loo(self.trace, pointwise=pointwise)
        return self._loo

    def compute_e_values(self, treatment_effects: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Compute E-values for sensitivity analysis.

        Args:
            treatment_effects: Dict mapping names to effects with 'odds_ratio' key
                             Uses pre-set treatment_effects if not provided
        """
        effects = treatment_effects or self.treatment_effects
        if effects is None:
            return {'error': 'No treatment effects provided'}

        # Extract odds ratios
        odds_ratios = {name: eff['odds_ratio'] for name, eff in effects.items()
                      if 'odds_ratio' in eff}

        self._e_values = compute_e_values(odds_ratios)
        return self._e_values

    def full_validation(self, observed_var: str = 'y_clicked',
                       include_loo: bool = True) -> Dict[str, Any]:
        """
        Run complete validation suite.

        Args:
            observed_var: Name of observed variable for PPC
            include_loo: Whether to compute LOO (can be slow)

        Returns:
            Comprehensive validation report
        """
        logger.info(f"Running full validation for {self.model_name}")

        report = {
            'model_name': self.model_name,
            'timestamp': datetime.now().isoformat(),
            'n_variables': len(self.var_names),
            'var_names': self.var_names
        }

        # Convergence diagnostics
        logger.info("Checking convergence...")
        report['convergence'] = self.check_convergence()

        # Posterior predictive check
        if 'posterior_predictive' in self.trace.groups():
            logger.info("Running posterior predictive check...")
            report['posterior_predictive'] = self.check_posterior_predictive(observed_var)
        else:
            report['posterior_predictive'] = {'skipped': 'No posterior_predictive in trace'}

        # LOO cross-validation
        if include_loo and 'log_likelihood' in self.trace.groups():
            logger.info("Computing LOO...")
            report['loo'] = self.compute_loo()
        else:
            report['loo'] = {'skipped': 'No log_likelihood or LOO disabled'}

        # E-values
        if self.treatment_effects:
            logger.info("Computing E-values...")
            report['e_values'] = self.compute_e_values()

        # Overall assessment
        report['overall'] = self._assess_overall(report)

        logger.info(f"Validation complete: {report['overall']['status']}")
        return report

    def _assess_overall(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate overall assessment from validation results."""
        issues = []
        warnings = []

        # Check convergence
        conv = report.get('convergence', {})
        if not conv.get('passed', True):
            if not conv.get('r_hat', {}).get('passed', True):
                issues.append('R-hat exceeds threshold')
            if not conv.get('ess', {}).get('passed', True):
                warnings.append('Low effective sample size')
            if not conv.get('divergences', {}).get('passed', True):
                issues.append('Divergent transitions detected')

        # Check PPC
        ppc = report.get('posterior_predictive', {})
        if 'error' not in ppc and 'skipped' not in ppc:
            p_val = ppc.get('bayesian_p_value', 0.5)
            if p_val < 0.05 or p_val > 0.95:
                warnings.append('Model may not fit data well (extreme Bayesian p-value)')

            cal = ppc.get('calibration', {})
            if not cal.get('well_calibrated', True):
                warnings.append('Calibration issues detected')

        # Check LOO
        loo = report.get('loo', {})
        if 'error' not in loo and 'skipped' not in loo:
            if loo.get('quality') == 'poor':
                issues.append('LOO estimates unreliable (Pareto k > 1.0)')
            elif loo.get('quality') == 'moderate':
                warnings.append('Some LOO estimates may be unreliable')

        # Overall status
        if issues:
            status = 'FAILED'
            message = f"Critical issues: {'; '.join(issues)}"
        elif warnings:
            status = 'PASSED_WITH_WARNINGS'
            message = f"Warnings: {'; '.join(warnings)}"
        else:
            status = 'PASSED'
            message = 'All validation checks passed'

        return {
            'status': status,
            'message': message,
            'issues': issues,
            'warnings': warnings
        }

    def generate_all_plots(self, output_dir: Path, return_base64: bool = False) -> Dict[str, Any]:
        """
        Generate all validation plots.

        Args:
            output_dir: Directory to save plots
            return_base64: Also return base64 encoded images

        Returns:
            Dictionary with plot information
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        plots = {}

        # Trace plot
        logger.info("Generating trace plot...")
        plots['trace'] = create_trace_plot(
            self.trace,
            var_names=self.var_names[:10],  # Limit for readability
            save_path=output_dir / 'trace_plot.png',
            return_base64=return_base64
        )

        # Forest plot for main parameters
        main_vars = [v for v in self.var_names if not v.startswith('gamma_') and not v.endswith('_offset')]
        if main_vars:
            logger.info("Generating forest plot...")
            plots['forest'] = create_forest_plot(
                self.trace,
                var_names=main_vars[:15],
                save_path=output_dir / 'forest_plot.png',
                return_base64=return_base64
            )

        # Posterior predictive plot
        if 'posterior_predictive' in self.trace.groups():
            logger.info("Generating PPC plot...")
            plots['ppc'] = create_posterior_predictive_plot(
                self.trace,
                save_path=output_dir / 'ppc_plot.png',
                return_base64=return_base64
            )

        # Treatment effects plot
        if self.treatment_effects:
            logger.info("Generating treatment effects plot...")
            plots['treatment_effects'] = create_treatment_effects_plot(
                self.treatment_effects,
                save_path=output_dir / 'treatment_effects.png',
                return_base64=return_base64
            )

            # E-value plot
            if self._e_values:
                logger.info("Generating E-value plot...")
                plots['e_values'] = create_e_value_plot(
                    self._e_values,
                    save_path=output_dir / 'e_values.png',
                    return_base64=return_base64
                )

        # County effects
        if self.county_effects:
            logger.info("Generating county effects plot...")
            plots['county_effects'] = create_county_effects_map(
                self.county_effects,
                save_path=output_dir / 'county_effects.png',
                return_base64=return_base64
            )

        return plots

    def get_summary_for_ui(self) -> Dict[str, Any]:
        """
        Get validation summary formatted for UI display.

        Returns data suitable for rendering in web dashboard.
        """
        report = self.full_validation()

        # Format for UI
        ui_summary = {
            'model_name': self.model_name,
            'overall_status': report['overall']['status'],
            'status_color': {
                'PASSED': 'green',
                'PASSED_WITH_WARNINGS': 'yellow',
                'FAILED': 'red'
            }.get(report['overall']['status'], 'gray'),
            'message': report['overall']['message'],

            # Convergence card
            'convergence': {
                'passed': report['convergence'].get('passed', False),
                'r_hat_max': report['convergence'].get('r_hat', {}).get('max_value', None),
                'ess_min': min(
                    report['convergence'].get('ess', {}).get('bulk_min', 0),
                    report['convergence'].get('ess', {}).get('tail_min', 0)
                ),
                'divergences': report['convergence'].get('divergences', {}).get('count', 0)
            },

            # Model fit card
            'model_fit': {},

            # Issues and warnings
            'issues': report['overall']['issues'],
            'warnings': report['overall']['warnings']
        }

        # Add PPC results if available
        ppc = report.get('posterior_predictive', {})
        if 'error' not in ppc and 'skipped' not in ppc:
            ui_summary['model_fit'] = {
                'observed_rate': ppc.get('observed_mean'),
                'predicted_rate': ppc.get('predicted_mean'),
                'calibration_rmse': ppc.get('calibration', {}).get('rmse'),
                'bayesian_p_value': ppc.get('bayesian_p_value')
            }

        # Add LOO if available
        loo = report.get('loo', {})
        if 'error' not in loo and 'skipped' not in loo:
            ui_summary['loo'] = {
                'elpd': loo.get('elpd_loo'),
                'quality': loo.get('quality')
            }

        return ui_summary

    def save_report(self, output_path: Path) -> None:
        """Save full validation report as JSON."""
        report = self.full_validation()

        # Make numpy types serializable
        def make_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [make_serializable(v) for v in obj]
            elif isinstance(obj, (np.integer, np.int64)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        with open(output_path, 'w') as f:
            json.dump(make_serializable(report), f, indent=2)

        logger.info(f"Validation report saved to {output_path}")
