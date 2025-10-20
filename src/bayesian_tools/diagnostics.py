"""
Diagnostic utilities for Bayesian models.

This module provides:
- Convergence diagnostics (R-hat, ESS)
- Posterior predictive checks
- Model comparison (LOO-CV, WAIC)
- Visualization utilities
"""

import numpy as np
import pandas as pd
import arviz as az
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Optional, Tuple
import pymc as pm


class BayesianDiagnostics:
    """Diagnostic tools for Bayesian model validation."""

    @staticmethod
    def check_convergence(trace,
                         var_names: Optional[List[str]] = None,
                         rhat_threshold: float = 1.01,
                         ess_threshold: int = 400) -> Dict:
        """
        Check convergence diagnostics for model parameters.

        Args:
            trace: PyMC InferenceData or trace object
            var_names: List of variable names to check (None = all)
            rhat_threshold: Maximum acceptable R-hat value
            ess_threshold: Minimum acceptable effective sample size

        Returns:
            Dictionary with convergence status and diagnostics
        """
        summary = az.summary(trace, var_names=var_names)

        # Check R-hat
        rhat_issues = summary[summary['r_hat'] > rhat_threshold]
        rhat_pass = len(rhat_issues) == 0

        # Check ESS
        ess_issues = summary[
            (summary['ess_bulk'] < ess_threshold) |
            (summary['ess_tail'] < ess_threshold)
        ]
        ess_pass = len(ess_issues) == 0

        convergence_status = {
            'converged': rhat_pass and ess_pass,
            'rhat_pass': rhat_pass,
            'ess_pass': ess_pass,
            'rhat_issues': rhat_issues.index.tolist() if not rhat_pass else [],
            'ess_issues': ess_issues.index.tolist() if not ess_pass else [],
            'summary': summary,
        }

        # Print diagnostics
        print("=" * 60)
        print("CONVERGENCE DIAGNOSTICS")
        print("=" * 60)
        print(f"R-hat check: {'✅ PASS' if rhat_pass else '❌ FAIL'}")
        if not rhat_pass:
            print(f"  Issues with {len(rhat_issues)} parameters:")
            for var in rhat_issues.index[:5]:  # Show first 5
                print(f"    {var}: R-hat = {rhat_issues.loc[var, 'r_hat']:.4f}")

        print(f"\nESS check: {'✅ PASS' if ess_pass else '❌ FAIL'}")
        if not ess_pass:
            print(f"  Issues with {len(ess_issues)} parameters:")
            for var in ess_issues.index[:5]:
                print(f"    {var}: ESS_bulk = {ess_issues.loc[var, 'ess_bulk']:.0f}, "
                     f"ESS_tail = {ess_issues.loc[var, 'ess_tail']:.0f}")

        print(f"\nOverall: {'✅ CONVERGED' if convergence_status['converged'] else '⚠️  CHECK REQUIRED'}")
        print("=" * 60)

        return convergence_status

    @staticmethod
    def plot_trace(trace,
                  var_names: Optional[List[str]] = None,
                  figsize: Tuple[int, int] = (12, 8),
                  save_path: Optional[str] = None):
        """
        Plot trace plots for visual convergence assessment.

        Args:
            trace: PyMC InferenceData object
            var_names: Variables to plot (None = all)
            figsize: Figure size
            save_path: Optional path to save figure
        """
        fig = az.plot_trace(trace, var_names=var_names, figsize=figsize)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Trace plot saved to {save_path}")

        return fig

    @staticmethod
    def posterior_predictive_check(trace,
                                  y_observed: np.ndarray,
                                  model_type: str = 'binary',
                                  n_samples: int = 100,
                                  figsize: Tuple[int, int] = (10, 6),
                                  save_path: Optional[str] = None):
        """
        Perform posterior predictive checks.

        Args:
            trace: PyMC InferenceData with posterior_predictive
            y_observed: Observed outcome data
            model_type: 'binary' or 'continuous'
            n_samples: Number of posterior samples to plot
            figsize: Figure size
            save_path: Optional path to save figure
        """
        if 'posterior_predictive' not in trace.groups():
            print("⚠️  No posterior predictive samples found in trace")
            return None

        # Extract posterior predictive samples
        y_pred_samples = az.extract(trace.posterior_predictive)

        # Get the first data variable (usually y_open or y_click)
        y_pred_var = list(y_pred_samples.data_vars.keys())[0]
        y_pred = y_pred_samples[y_pred_var].values

        fig, axes = plt.subplots(1, 2, figsize=figsize)

        if model_type == 'binary':
            # For binary outcomes, compare proportions
            # Calculate mean prediction for each observation
            y_pred_mean = y_pred.mean(axis=1)

            # Plot 1: Predicted vs Observed proportions
            axes[0].scatter(y_observed, y_pred_mean, alpha=0.3, s=10)
            axes[0].plot([0, 1], [0, 1], 'r--', label='Perfect prediction')
            axes[0].set_xlabel('Observed')
            axes[0].set_ylabel('Predicted Probability')
            axes[0].set_title('Predicted vs Observed')
            axes[0].legend()

            # Plot 2: Distribution of predictions by observed outcome
            sns.violinplot(x=y_observed, y=y_pred_mean, ax=axes[1])
            axes[1].set_xlabel('Observed Outcome')
            axes[1].set_ylabel('Predicted Probability')
            axes[1].set_title('Prediction Distribution by Outcome')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Posterior predictive check saved to {save_path}")

        # Calculate calibration metrics
        if model_type == 'binary':
            y_pred_binary = (y_pred_mean > 0.5).astype(int)
            accuracy = (y_pred_binary == y_observed).mean()
            print(f"\nCalibration Metrics:")
            print(f"  Accuracy: {accuracy:.3f}")
            print(f"  Mean predicted prob: {y_pred_mean.mean():.3f}")
            print(f"  Observed rate: {y_observed.mean():.3f}")

        return fig

    @staticmethod
    def compare_models(traces: Dict[str, az.InferenceData],
                      y_observed: np.ndarray,
                      model_names: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Compare multiple models using LOO-CV and WAIC.

        Args:
            traces: Dictionary of model_name -> InferenceData
            y_observed: Observed outcomes
            model_names: Optional custom names for models

        Returns:
            DataFrame with comparison metrics
        """
        if model_names is None:
            model_names = list(traces.keys())

        comparison_data = {}

        print("=" * 60)
        print("MODEL COMPARISON")
        print("=" * 60)

        for name, trace in traces.items():
            # Calculate LOO-CV
            try:
                loo = az.loo(trace)
                comparison_data[name] = {
                    'loo': loo.loo,
                    'loo_se': loo.se,
                    'p_loo': loo.p_loo,
                }
                print(f"\n{name}:")
                print(f"  LOO: {loo.loo:.2f} (SE: {loo.se:.2f})")
                print(f"  p_loo: {loo.p_loo:.2f}")

                # Check for warnings
                if hasattr(loo, 'warning') and loo.warning:
                    print(f"  ⚠️  Warning: {loo.warning}")

            except Exception as e:
                print(f"  ❌ LOO calculation failed: {e}")
                comparison_data[name] = {
                    'loo': np.nan,
                    'loo_se': np.nan,
                    'p_loo': np.nan,
                }

            # Calculate WAIC
            try:
                waic = az.waic(trace)
                comparison_data[name]['waic'] = waic.waic
                comparison_data[name]['waic_se'] = waic.se
                print(f"  WAIC: {waic.waic:.2f} (SE: {waic.se:.2f})")
            except Exception as e:
                print(f"  ❌ WAIC calculation failed: {e}")
                comparison_data[name]['waic'] = np.nan
                comparison_data[name]['waic_se'] = np.nan

        print("=" * 60)

        # Create comparison DataFrame
        comparison_df = pd.DataFrame(comparison_data).T

        # Rank by LOO (lower is better)
        comparison_df['loo_rank'] = comparison_df['loo'].rank()

        # Calculate differences from best model
        best_loo = comparison_df['loo'].min()
        comparison_df['loo_diff'] = comparison_df['loo'] - best_loo

        return comparison_df.sort_values('loo_rank')

    @staticmethod
    def plot_posterior_distributions(trace,
                                    var_names: List[str],
                                    figsize: Tuple[int, int] = (12, 6),
                                    save_path: Optional[str] = None):
        """
        Plot posterior distributions for key parameters.

        Args:
            trace: PyMC InferenceData
            var_names: Variables to plot
            figsize: Figure size
            save_path: Optional path to save figure
        """
        fig = az.plot_posterior(trace, var_names=var_names, figsize=figsize,
                               hdi_prob=0.95, ref_val=0)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Posterior distributions saved to {save_path}")

        return fig

    @staticmethod
    def extract_coefficient_summary(trace,
                                   var_names: Optional[List[str]] = None,
                                   hdi_prob: float = 0.95) -> pd.DataFrame:
        """
        Extract summary statistics for model coefficients.

        Args:
            trace: PyMC InferenceData
            var_names: Variables to summarize
            hdi_prob: Probability for HDI interval

        Returns:
            DataFrame with coefficient summaries
        """
        summary = az.summary(trace, var_names=var_names, hdi_prob=hdi_prob)

        # Calculate odds ratios for logistic regression coefficients
        beta_vars = [v for v in summary.index if 'beta' in v.lower()]
        if beta_vars:
            summary['odds_ratio'] = np.exp(summary['mean'])
            summary['or_lower'] = np.exp(summary[f'hdi_{(1-hdi_prob)/2*100:.0f}%'])
            summary['or_upper'] = np.exp(summary[f'hdi_{100-((1-hdi_prob)/2*100):.0f}%'])

        return summary

    @staticmethod
    def plot_forest(trace,
                   var_names: List[str],
                   figsize: Tuple[int, int] = (10, 6),
                   save_path: Optional[str] = None):
        """
        Create forest plot for coefficient estimates.

        Args:
            trace: PyMC InferenceData
            var_names: Variables to plot
            figsize: Figure size
            save_path: Optional path to save figure
        """
        fig = az.plot_forest(trace, var_names=var_names, figsize=figsize,
                            combined=True, hdi_prob=0.95)
        plt.axvline(x=0, color='red', linestyle='--', alpha=0.5)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Forest plot saved to {save_path}")

        return fig


def check_model_quality(trace,
                       y_observed: np.ndarray,
                       model_name: str = "Model",
                       var_names: Optional[List[str]] = None) -> Dict:
    """
    Comprehensive model quality check.

    Args:
        trace: PyMC InferenceData
        y_observed: Observed outcomes
        model_name: Name for reporting
        var_names: Variables to check

    Returns:
        Dictionary with all diagnostic results
    """
    diagnostics = BayesianDiagnostics()

    print(f"\n{'='*60}")
    print(f"QUALITY CHECK: {model_name}")
    print(f"{'='*60}\n")

    # 1. Convergence diagnostics
    convergence = diagnostics.check_convergence(trace, var_names=var_names)

    # 2. Posterior predictive check
    print("\nPosterior Predictive Check:")
    try:
        diagnostics.posterior_predictive_check(trace, y_observed, model_type='binary')
    except Exception as e:
        print(f"⚠️  Posterior predictive check failed: {e}")

    # 3. Extract coefficient summary
    print("\nCoefficient Summary:")
    coef_summary = diagnostics.extract_coefficient_summary(trace, var_names=var_names)
    print(coef_summary[['mean', 'sd', 'hdi_2.5%', 'hdi_97.5%', 'r_hat', 'ess_bulk']])

    return {
        'convergence': convergence,
        'coefficients': coef_summary,
    }
