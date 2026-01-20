"""
Visualization functions for Bayesian model validation.

Generates plots suitable for both CLI display and UI embedding.
All functions return figure objects or base64-encoded images for web display.
"""

from typing import Dict, Any, Optional, List, Tuple
import io
import base64
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import arviz as az


def create_trace_plot(trace: az.InferenceData, var_names: Optional[List[str]] = None,
                     figsize: Tuple[int, int] = (12, 8), save_path: Optional[Path] = None,
                     return_base64: bool = False) -> Dict[str, Any]:
    """
    Create trace plot showing MCMC chains and posterior distributions.

    Args:
        trace: ArviZ InferenceData object
        var_names: Variables to plot (None = all)
        figsize: Figure size
        save_path: Path to save figure
        return_base64: Return base64 encoded image for web

    Returns:
        Dictionary with figure info and optionally base64 data
    """
    fig = az.plot_trace(trace, var_names=var_names, figsize=figsize)
    plt.tight_layout()

    result = {'type': 'trace_plot', 'var_names': var_names}

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(plt.gcf())

    plt.close()
    return result


def create_forest_plot(trace: az.InferenceData, var_names: List[str],
                      combined: bool = True, hdi_prob: float = 0.89,
                      title: str = 'Parameter Estimates',
                      save_path: Optional[Path] = None,
                      return_base64: bool = False) -> Dict[str, Any]:
    """
    Create forest plot showing parameter estimates with credible intervals.

    Args:
        trace: ArviZ InferenceData object
        var_names: Variables to include
        combined: Combine chains
        hdi_prob: HDI probability level
        title: Plot title
        save_path: Path to save figure
        return_base64: Return base64 encoded image

    Returns:
        Dictionary with figure info
    """
    fig = az.plot_forest(trace, var_names=var_names, combined=combined,
                        hdi_prob=hdi_prob, figsize=(10, max(4, len(var_names) * 0.5)))
    plt.title(title)
    plt.tight_layout()

    result = {'type': 'forest_plot', 'var_names': var_names, 'hdi_prob': hdi_prob}

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(plt.gcf())

    plt.close()
    return result


def create_posterior_predictive_plot(trace: az.InferenceData,
                                    observed_var: str = 'y_clicked',
                                    n_samples: int = 50,
                                    save_path: Optional[Path] = None,
                                    return_base64: bool = False) -> Dict[str, Any]:
    """
    Create posterior predictive check visualization.

    Shows distribution of observed data vs posterior predictive samples.

    Args:
        trace: ArviZ InferenceData with posterior_predictive
        observed_var: Name of observed variable
        n_samples: Number of posterior samples to plot
        save_path: Path to save figure
        return_base64: Return base64 encoded image

    Returns:
        Dictionary with figure info
    """
    if 'posterior_predictive' not in trace.groups():
        return {'error': 'No posterior_predictive in trace'}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Get data
    y_obs = trace.observed_data[observed_var].values.flatten()
    y_pred = trace.posterior_predictive[observed_var].values

    # Flatten predictions
    n_chains, n_draws, n_obs = y_pred.shape
    y_pred_flat = y_pred.reshape(-1, n_obs)

    # Plot 1: Mean rate comparison
    ax1 = axes[0]
    obs_mean = y_obs.mean()
    pred_means = y_pred_flat.mean(axis=1)

    ax1.hist(pred_means, bins=30, alpha=0.7, density=True, label='Predicted means')
    ax1.axvline(obs_mean, color='red', linewidth=2, label=f'Observed mean ({obs_mean:.3f})')
    ax1.set_xlabel('Mean Rate')
    ax1.set_ylabel('Density')
    ax1.set_title('Posterior Predictive Check: Mean Comparison')
    ax1.legend()

    # Plot 2: Distribution comparison
    ax2 = axes[1]

    # Sample predictions
    sample_idx = np.random.choice(len(y_pred_flat), min(n_samples, len(y_pred_flat)), replace=False)

    for idx in sample_idx[:20]:  # Limit display
        pred_mean = y_pred_flat[idx].mean()
        ax2.scatter([pred_mean], [idx], color='blue', alpha=0.3, s=20)

    ax2.axvline(obs_mean, color='red', linewidth=2, label='Observed')
    ax2.set_xlabel('Sample Mean')
    ax2.set_ylabel('Sample Index')
    ax2.set_title('Posterior Predictive Samples')

    plt.tight_layout()

    result = {'type': 'posterior_predictive_plot', 'observed_var': observed_var}

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(fig)

    plt.close()
    return result


def create_calibration_plot(y_obs: np.ndarray, pred_probs: np.ndarray,
                           n_bins: int = 10,
                           save_path: Optional[Path] = None,
                           return_base64: bool = False) -> Dict[str, Any]:
    """
    Create calibration plot comparing predicted probabilities to observed rates.

    Args:
        y_obs: Observed binary outcomes
        pred_probs: Predicted probabilities
        n_bins: Number of calibration bins
        save_path: Path to save figure
        return_base64: Return base64 encoded image

    Returns:
        Dictionary with figure info and calibration statistics
    """
    fig, ax = plt.subplots(figsize=(8, 8))

    # Create bins
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(pred_probs, bin_edges) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    # Compute observed rate per bin
    pred_rates = []
    obs_rates = []
    counts = []

    for i in range(n_bins):
        mask = bin_indices == i
        if mask.sum() > 0:
            pred_rates.append(pred_probs[mask].mean())
            obs_rates.append(y_obs[mask].mean())
            counts.append(mask.sum())

    pred_rates = np.array(pred_rates)
    obs_rates = np.array(obs_rates)
    counts = np.array(counts)

    # Compute calibration error
    rmse = np.sqrt(np.mean((pred_rates - obs_rates) ** 2))

    # Plot
    ax.scatter(pred_rates, obs_rates, s=counts/10 + 20, alpha=0.7, label='Bins')
    ax.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')

    ax.set_xlabel('Predicted Probability')
    ax.set_ylabel('Observed Rate')
    ax.set_title(f'Calibration Plot (RMSE: {rmse:.3f})')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_aspect('equal')

    plt.tight_layout()

    result = {
        'type': 'calibration_plot',
        'rmse': float(rmse),
        'n_bins': n_bins,
        'well_calibrated': rmse < 0.05
    }

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(fig)

    plt.close()
    return result


def create_treatment_effects_plot(effects: Dict[str, Dict[str, Any]],
                                 title: str = 'Treatment Effects',
                                 save_path: Optional[Path] = None,
                                 return_base64: bool = False) -> Dict[str, Any]:
    """
    Create forest plot of treatment effects with odds ratios.

    Args:
        effects: Dictionary of treatment effects with odds_ratio, or_lower, or_upper
        title: Plot title
        save_path: Path to save figure
        return_base64: Return base64 encoded image

    Returns:
        Dictionary with figure info
    """
    fig, ax = plt.subplots(figsize=(10, max(4, len(effects) * 0.6)))

    # Sort by effect size
    sorted_effects = sorted(effects.items(), key=lambda x: x[1]['odds_ratio'], reverse=True)

    y_positions = np.arange(len(sorted_effects))
    labels = []
    means = []
    errors_low = []
    errors_high = []
    colors = []

    for name, effect in sorted_effects:
        labels.append(name.replace('_', ' ').title())
        or_val = effect['odds_ratio']
        means.append(or_val)
        errors_low.append(or_val - effect['or_lower'])
        errors_high.append(effect['or_upper'] - or_val)

        # Color by significance
        if effect.get('credibly_positive', False):
            colors.append('#2E7D32')  # Green
        elif effect.get('credibly_negative', False):
            colors.append('#C62828')  # Red
        else:
            colors.append('#757575')  # Gray

    # Plot error bars
    ax.errorbar(means, y_positions, xerr=[errors_low, errors_high],
               fmt='none', capsize=5, capthick=2, color='black', ecolor='black')

    # Plot points with colors
    for i, (mean, color) in enumerate(zip(means, colors)):
        ax.scatter([mean], [i], color=color, s=120, zorder=5, edgecolors='black')

    # Reference line
    ax.axvline(x=1, color='black', linestyle='--', alpha=0.5, label='No Effect (OR=1)')

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.set_xlabel('Odds Ratio (89% Credible Interval)')
    ax.set_title(title)

    # Legend
    green_patch = mpatches.Patch(color='#2E7D32', label='Credibly Positive')
    red_patch = mpatches.Patch(color='#C62828', label='Credibly Negative')
    gray_patch = mpatches.Patch(color='#757575', label='Inconclusive')
    ax.legend(handles=[green_patch, red_patch, gray_patch], loc='lower right')

    plt.tight_layout()

    result = {'type': 'treatment_effects_plot', 'n_effects': len(effects)}

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(fig)

    plt.close()
    return result


def create_e_value_plot(e_values: Dict[str, Dict[str, Any]],
                       save_path: Optional[Path] = None,
                       return_base64: bool = False) -> Dict[str, Any]:
    """
    Create bar chart of E-values for sensitivity analysis.

    Args:
        e_values: Dictionary with E-value results from compute_e_values
        save_path: Path to save figure
        return_base64: Return base64 encoded image

    Returns:
        Dictionary with figure info
    """
    fig, ax = plt.subplots(figsize=(10, max(4, len(e_values) * 0.6)))

    # Sort by E-value
    sorted_vals = sorted(e_values.items(), key=lambda x: x[1]['e_value'], reverse=True)

    names = [item[0].replace('_', ' ').title() for item in sorted_vals]
    values = [item[1]['e_value'] for item in sorted_vals]

    # Color by robustness
    colors = []
    for item in sorted_vals:
        robustness = item[1]['robustness']
        if robustness == 'highly_robust':
            colors.append('#1B5E20')
        elif robustness == 'robust':
            colors.append('#4CAF50')
        elif robustness == 'somewhat_robust':
            colors.append('#FFC107')
        else:
            colors.append('#F44336')

    y_pos = np.arange(len(names))

    bars = ax.barh(y_pos, values, color=colors, edgecolor='black')

    # Reference lines
    ax.axvline(x=2.0, color='orange', linestyle='--', alpha=0.7, label='Moderate robustness')
    ax.axvline(x=3.0, color='green', linestyle='--', alpha=0.7, label='High robustness')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.set_xlabel('E-value')
    ax.set_title('Sensitivity Analysis: E-values for Treatment Effects')
    ax.legend(loc='lower right')

    plt.tight_layout()

    result = {'type': 'e_value_plot', 'n_effects': len(e_values)}

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(fig)

    plt.close()
    return result


def create_county_effects_map(county_effects: Dict[str, Dict[str, float]],
                             save_path: Optional[Path] = None,
                             return_base64: bool = False) -> Dict[str, Any]:
    """
    Create horizontal bar chart of county random effects.

    Note: For a true geographic map, would need county shapefiles.
    This provides a ranked bar chart visualization.

    Args:
        county_effects: Dictionary with county effect means and SDs
        save_path: Path to save figure
        return_base64: Return base64 encoded image

    Returns:
        Dictionary with figure info
    """
    fig, ax = plt.subplots(figsize=(10, max(6, len(county_effects) * 0.4)))

    # Sort by effect
    sorted_effects = sorted(county_effects.items(), key=lambda x: x[1]['mean'], reverse=True)

    names = [item[0] for item in sorted_effects]
    means = [item[1]['mean'] for item in sorted_effects]
    sds = [item[1].get('sd', 0) for item in sorted_effects]

    y_pos = np.arange(len(names))

    # Color by direction
    colors = ['#2E7D32' if m > 0 else '#C62828' for m in means]

    ax.barh(y_pos, means, xerr=sds, color=colors, edgecolor='black', capsize=3)
    ax.axvline(x=0, color='black', linestyle='-', linewidth=1)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.set_xlabel('Random Effect (log-odds)')
    ax.set_title('County Random Effects\n(Green = Above Average, Red = Below Average)')

    plt.tight_layout()

    result = {'type': 'county_effects_plot', 'n_counties': len(county_effects)}

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        result['saved_to'] = str(save_path)

    if return_base64:
        result['base64'] = _fig_to_base64(fig)

    plt.close()
    return result


def _fig_to_base64(fig) -> str:
    """Convert matplotlib figure to base64 encoded PNG."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode('utf-8')
