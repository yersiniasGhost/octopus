"""
Diagnostic functions for Bayesian model validation.

Following McElreath's Statistical Rethinking methodology:
- R-hat < 1.01 for all parameters
- ESS > 400 for reliable inference
- No divergent transitions
- PSIS-LOO for model comparison
- E-values for causal sensitivity
"""

from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import arviz as az
from scipy import stats


def check_convergence(trace: az.InferenceData, var_names: Optional[List[str]] = None,
                     r_hat_threshold: float = 1.01, ess_threshold: int = 400) -> Dict[str, Any]:
    """
    Check MCMC convergence using R-hat and ESS diagnostics.

    Args:
        trace: ArviZ InferenceData object
        var_names: List of variable names to check (None = all)
        r_hat_threshold: Maximum acceptable R-hat (default 1.01)
        ess_threshold: Minimum acceptable ESS (default 400)

    Returns:
        Dictionary with convergence diagnostics and pass/fail status
    """
    summary = az.summary(trace, var_names=var_names)

    # R-hat diagnostics
    r_hat_values = summary['r_hat']
    r_hat_max = float(r_hat_values.max())
    r_hat_problematic = list(summary[r_hat_values > r_hat_threshold].index)

    # ESS diagnostics
    ess_bulk = summary['ess_bulk']
    ess_tail = summary['ess_tail']
    ess_bulk_min = float(ess_bulk.min())
    ess_tail_min = float(ess_tail.min())
    ess_problematic = list(summary[(ess_bulk < ess_threshold) | (ess_tail < ess_threshold)].index)

    # Divergences
    divergences = 0
    if hasattr(trace, 'sample_stats') and 'diverging' in trace.sample_stats:
        divergences = int(trace.sample_stats['diverging'].sum().item())

    # Overall assessment
    r_hat_passed = r_hat_max < r_hat_threshold
    ess_passed = ess_bulk_min >= ess_threshold and ess_tail_min >= ess_threshold
    div_passed = divergences == 0
    all_passed = r_hat_passed and ess_passed and div_passed

    return {
        'passed': all_passed,
        'r_hat': {
            'passed': r_hat_passed,
            'max_value': r_hat_max,
            'threshold': r_hat_threshold,
            'problematic_params': r_hat_problematic
        },
        'ess': {
            'passed': ess_passed,
            'bulk_min': ess_bulk_min,
            'tail_min': ess_tail_min,
            'threshold': ess_threshold,
            'problematic_params': ess_problematic
        },
        'divergences': {
            'passed': div_passed,
            'count': divergences
        },
        'recommendation': _convergence_recommendation(r_hat_passed, ess_passed, div_passed)
    }


def _convergence_recommendation(r_hat_ok: bool, ess_ok: bool, div_ok: bool) -> str:
    """Generate recommendation based on convergence results."""
    if r_hat_ok and ess_ok and div_ok:
        return "Model converged well. Results are reliable."

    recommendations = []
    if not r_hat_ok:
        recommendations.append("R-hat > 1.01: Increase warmup or check model specification")
    if not ess_ok:
        recommendations.append("Low ESS: Increase samples or use thinning")
    if not div_ok:
        recommendations.append("Divergences detected: Increase target_accept or reparameterize")

    return "; ".join(recommendations)


def compute_e_values(effect_estimates: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    """
    Compute E-values for sensitivity analysis to unmeasured confounding.

    The E-value represents the minimum strength of association an unmeasured
    confounder would need with both treatment and outcome to explain away
    the observed effect.

    Args:
        effect_estimates: Dictionary mapping parameter names to odds ratios

    Returns:
        Dictionary with E-values and interpretations for each effect
    """
    e_values = {}

    for param_name, odds_ratio in effect_estimates.items():
        if odds_ratio >= 1:
            # For harmful effects (OR > 1)
            e_value = odds_ratio + np.sqrt(odds_ratio * (odds_ratio - 1))
        else:
            # For protective effects (OR < 1)
            or_inv = 1 / odds_ratio
            e_value = or_inv + np.sqrt(or_inv * (or_inv - 1))

        # Interpretation thresholds
        if e_value > 3.0:
            robustness = 'highly_robust'
            interpretation = 'Very robust to unmeasured confounding'
        elif e_value > 2.0:
            robustness = 'robust'
            interpretation = 'Robust to moderate confounding'
        elif e_value > 1.5:
            robustness = 'somewhat_robust'
            interpretation = 'Somewhat robust to confounding'
        else:
            robustness = 'sensitive'
            interpretation = 'Sensitive to unmeasured confounding'

        e_values[param_name] = {
            'odds_ratio': float(odds_ratio),
            'e_value': float(e_value),
            'robustness': robustness,
            'interpretation': interpretation
        }

    return e_values


def posterior_predictive_check(trace: az.InferenceData, observed_var: str = 'y_clicked',
                               n_samples: int = 100) -> Dict[str, Any]:
    """
    Perform posterior predictive check for model calibration.

    Compares observed outcome distribution to posterior predictive samples.

    Args:
        trace: ArviZ InferenceData with posterior_predictive group
        observed_var: Name of observed variable
        n_samples: Number of posterior samples to use

    Returns:
        Dictionary with PPC statistics and calibration metrics
    """
    if 'posterior_predictive' not in trace.groups():
        return {'error': 'No posterior_predictive group in trace. Run sample_posterior_predictive first.'}

    # Get observed data
    if 'observed_data' in trace.groups():
        y_obs = trace.observed_data[observed_var].values.flatten()
    else:
        return {'error': 'No observed_data group in trace.'}

    # Get posterior predictive samples
    y_pred = trace.posterior_predictive[observed_var].values

    # Flatten across chains
    n_chains, n_draws, n_obs = y_pred.shape
    y_pred_flat = y_pred.reshape(-1, n_obs)

    # Sample for efficiency
    if len(y_pred_flat) > n_samples:
        idx = np.random.choice(len(y_pred_flat), n_samples, replace=False)
        y_pred_samples = y_pred_flat[idx]
    else:
        y_pred_samples = y_pred_flat

    # Compute statistics
    obs_mean = float(y_obs.mean())
    pred_means = y_pred_samples.mean(axis=1)

    # Bayesian p-value: proportion of predictions more extreme than observed
    p_value = float(np.mean(pred_means >= obs_mean))

    # Calibration: bin predictions and compare to observed rates
    pred_probs = y_pred_samples.mean(axis=0)  # Mean prediction per observation
    calibration = _compute_calibration(y_obs, pred_probs)

    return {
        'observed_mean': obs_mean,
        'predicted_mean': float(pred_means.mean()),
        'predicted_std': float(pred_means.std()),
        'bayesian_p_value': p_value,
        'calibration': calibration,
        'interpretation': _ppc_interpretation(p_value, calibration['rmse'])
    }


def _compute_calibration(y_obs: np.ndarray, pred_probs: np.ndarray,
                        n_bins: int = 10) -> Dict[str, Any]:
    """Compute calibration metrics by binning predictions."""
    # Create bins
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(pred_probs, bin_edges) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    # Compute observed rate per bin
    bins = []
    for i in range(n_bins):
        mask = bin_indices == i
        if mask.sum() > 0:
            obs_rate = float(y_obs[mask].mean())
            pred_rate = float(pred_probs[mask].mean())
            count = int(mask.sum())
            bins.append({
                'bin_lower': float(bin_edges[i]),
                'bin_upper': float(bin_edges[i + 1]),
                'predicted_rate': pred_rate,
                'observed_rate': obs_rate,
                'count': count
            })

    # Compute RMSE of calibration
    if bins:
        pred_rates = np.array([b['predicted_rate'] for b in bins])
        obs_rates = np.array([b['observed_rate'] for b in bins])
        rmse = float(np.sqrt(np.mean((pred_rates - obs_rates) ** 2)))
    else:
        rmse = np.nan

    return {
        'bins': bins,
        'rmse': rmse,
        'well_calibrated': rmse < 0.05 if not np.isnan(rmse) else False
    }


def _ppc_interpretation(p_value: float, calibration_rmse: float) -> str:
    """Generate interpretation of PPC results."""
    issues = []

    if p_value < 0.05 or p_value > 0.95:
        issues.append("Model predictions systematically differ from observed data")

    if calibration_rmse > 0.10:
        issues.append("Poor calibration: predicted probabilities don't match observed rates")
    elif calibration_rmse > 0.05:
        issues.append("Moderate calibration issues")

    if not issues:
        return "Model shows good posterior predictive fit and calibration"

    return "; ".join(issues)


def compute_loo(trace: az.InferenceData, pointwise: bool = False) -> Dict[str, Any]:
    """
    Compute PSIS-LOO (Pareto-smoothed importance sampling leave-one-out)
    cross-validation for model comparison.

    Args:
        trace: ArviZ InferenceData with log_likelihood group
        pointwise: Whether to return pointwise LOO values

    Returns:
        Dictionary with LOO-CV results
    """
    try:
        loo_result = az.loo(trace, pointwise=pointwise)
    except Exception as e:
        return {'error': f'LOO computation failed: {e}'}

    # Extract key statistics
    elpd_loo = float(loo_result.elpd_loo)
    se = float(loo_result.se)
    p_loo = float(loo_result.p_loo)

    # Pareto k diagnostics
    pareto_k = loo_result.pareto_k.values if hasattr(loo_result, 'pareto_k') else None

    if pareto_k is not None:
        k_max = float(np.max(pareto_k))
        k_bad = int(np.sum(pareto_k > 0.7))
        k_very_bad = int(np.sum(pareto_k > 1.0))
    else:
        k_max = np.nan
        k_bad = 0
        k_very_bad = 0

    # Interpretation
    if k_very_bad > 0:
        loo_quality = 'poor'
        recommendation = f'{k_very_bad} observations have Pareto k > 1.0. LOO estimates unreliable.'
    elif k_bad > 0:
        loo_quality = 'moderate'
        recommendation = f'{k_bad} observations have Pareto k > 0.7. Consider moment matching.'
    else:
        loo_quality = 'good'
        recommendation = 'LOO estimates are reliable.'

    result = {
        'elpd_loo': elpd_loo,
        'se': se,
        'p_loo': p_loo,
        'pareto_k_max': k_max,
        'pareto_k_bad_count': k_bad,
        'pareto_k_very_bad_count': k_very_bad,
        'quality': loo_quality,
        'recommendation': recommendation
    }

    if pointwise and hasattr(loo_result, 'loo_i'):
        result['pointwise_loo'] = loo_result.loo_i.values.tolist()
        result['pareto_k'] = pareto_k.tolist() if pareto_k is not None else None

    return result


def compare_models(traces: Dict[str, az.InferenceData]) -> Dict[str, Any]:
    """
    Compare multiple models using PSIS-LOO.

    Args:
        traces: Dictionary mapping model names to InferenceData objects

    Returns:
        Comparison table and rankings
    """
    try:
        comparison = az.compare(traces, ic='loo')
    except Exception as e:
        return {'error': f'Model comparison failed: {e}'}

    # Extract rankings
    rankings = []
    for model_name in comparison.index:
        rankings.append({
            'model': model_name,
            'elpd_loo': float(comparison.loc[model_name, 'elpd_loo']),
            'se': float(comparison.loc[model_name, 'se']),
            'weight': float(comparison.loc[model_name, 'weight']),
            'rank': int(comparison.index.get_loc(model_name)) + 1
        })

    return {
        'rankings': rankings,
        'best_model': rankings[0]['model'],
        'comparison_table': comparison.to_dict()
    }
