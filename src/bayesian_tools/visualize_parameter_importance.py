#!/usr/bin/env python3
"""
Visualize parameter importance for open rates from Phase 1A model.

Creates forest plots showing effect sizes and credible intervals for all
parameter categories that influence email open rates.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path


def load_parameter_data():
    """Load and categorize parameter estimates."""
    df = pd.read_csv('/home/yersinia/devel/octopus/reports/phase1/parameter_summary.csv')

    # Filter to open rate parameters only
    open_params = df[df.iloc[:, 0].str.contains('_open', na=False)].copy()

    # Remove non-centered parameters
    open_params = open_params[~open_params.iloc[:, 0].str.contains('z_alpha')].copy()

    # Add absolute mean for sorting
    open_params['abs_mean'] = np.abs(open_params['mean'])

    # Categorize parameters
    def categorize_param(name):
        if name.startswith('alpha_open['):
            return 'campaign_intercept'
        elif name.startswith('msg_type_effect_open'):
            return 'message_type'
        elif name.startswith('location_effect_open'):
            return 'location'
        elif name.startswith('month_effect_open'):
            return 'temporal'
        elif name.startswith('beta_') and '_open' in name:
            return 'offer_characteristic'
        elif name in ['mu_alpha_open', 'sigma_alpha_open']:
            return 'population_hyperparameter'
        else:
            return 'other'

    open_params['category'] = open_params.iloc[:, 0].apply(categorize_param)

    return open_params


def create_forest_plot_by_category(data, output_path):
    """Create forest plot showing top parameters by category."""

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Parameter Importance for Email Open Rates - Phase 1A\n' +
                 '15 Campaigns | 22,050 Contacts | 89% Credible Intervals',
                 fontsize=16, fontweight='bold', y=0.995)

    axes = axes.flatten()

    categories = [
        ('campaign_intercept', 'Campaign-Specific Intercepts', 10, True),
        ('location', 'Geographic Location Effects', 15, False),
        ('message_type', 'Message Type Effects', 5, False),
        ('temporal', 'Temporal Effects (Month)', 12, False),
        ('offer_characteristic', 'Offer Characteristics', 3, False),
        ('population_hyperparameter', 'Population Hyperparameters', 2, False)
    ]

    colors = {
        'campaign_intercept': '#1f77b4',
        'location': '#2ca02c',
        'message_type': '#9467bd',
        'temporal': '#ff7f0e',
        'offer_characteristic': '#d62728',
        'population_hyperparameter': '#8c564b'
    }

    for idx, (category, title, n_show, show_best_worst) in enumerate(categories):
        ax = axes[idx]
        cat_data = data[data['category'] == category].copy()

        if len(cat_data) == 0:
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(title, fontweight='bold', fontsize=11)
            ax.axis('off')
            continue

        # Sort by absolute mean
        cat_data = cat_data.sort_values('abs_mean', ascending=False)

        if show_best_worst:
            # Show top 5 best and top 5 worst
            best = cat_data.head(5).copy()
            worst = cat_data.tail(5).copy()
            plot_data = pd.concat([best, worst])
            plot_data['label'] = ['Best ' + str(i+1) for i in range(5)] + \
                                 ['Worst ' + str(i+1) for i in range(5)]
        else:
            plot_data = cat_data.head(n_show).copy()
            plot_data['label'] = plot_data.iloc[:, 0].str.extract(r'\[(\d+)\]')[0]
            plot_data['label'] = plot_data['label'].fillna(
                plot_data.iloc[:, 0].str.replace('_open', '').str.replace('_', ' ')
            )

        # Determine statistical significance
        plot_data['significant'] = ~(
            (plot_data['hdi_5.5%'] < 0) & (plot_data['hdi_94.5%'] > 0)
        )

        # Create forest plot
        y_positions = np.arange(len(plot_data))

        for i, (_, row) in enumerate(plot_data.iterrows()):
            color = colors[category]
            alpha = 0.9 if row['significant'] else 0.4
            marker = 'o' if row['significant'] else 'o'
            markersize = 8 if row['significant'] else 6

            # Plot credible interval
            ax.plot([row['hdi_5.5%'], row['hdi_94.5%']],
                   [y_positions[i], y_positions[i]],
                   color=color, alpha=alpha, linewidth=2, zorder=1)

            # Plot point estimate
            ax.scatter(row['mean'], y_positions[i],
                      color=color, alpha=alpha, s=markersize**2,
                      marker=marker, zorder=2, edgecolors='black', linewidths=0.5)

        # Add zero reference line
        ax.axvline(x=0, color='gray', linestyle='--', linewidth=1, alpha=0.5, zorder=0)

        # Formatting
        ax.set_yticks(y_positions)
        ax.set_yticklabels(plot_data['label'], fontsize=9)
        ax.set_xlabel('Effect Size (Logit Scale)', fontsize=10)
        ax.set_title(title, fontweight='bold', fontsize=11, pad=10)
        ax.grid(axis='x', alpha=0.3, linestyle=':')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Add sample stats
        mean_val = cat_data['mean'].mean()
        std_val = cat_data['mean'].std()
        stats_text = f'Mean: {mean_val:.3f}\nStd: {std_val:.3f}\n({len(cat_data)} params)'
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=8, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    # Add legend
    sig_patch = mpatches.Patch(color='black', alpha=0.9, label='Statistically Significant (HDI excludes 0)')
    unsig_patch = mpatches.Patch(color='black', alpha=0.4, label='Uncertain (HDI crosses 0)')
    fig.legend(handles=[sig_patch, unsig_patch], loc='lower center',
              ncol=2, fontsize=10, frameon=True, bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.02, 1, 0.99])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Forest plot saved: {output_path}")
    plt.close()


def create_feature_importance_bar_chart(data, output_path):
    """Create bar chart showing relative importance of feature categories."""

    # Calculate category-level statistics
    categories = ['campaign_intercept', 'location', 'message_type', 'temporal', 'offer_characteristic']
    category_names = ['Campaign\nIdentity', 'Geographic\nLocation', 'Message\nType', 'Temporal\n(Month)', 'Offer\nCharacteristics']

    stats = []
    for cat in categories:
        cat_data = data[data['category'] == cat]
        if len(cat_data) > 0:
            max_abs_effect = cat_data['abs_mean'].max()
            mean_abs_effect = cat_data['abs_mean'].mean()
            pct_significant = (
                ~((cat_data['hdi_5.5%'] < 0) & (cat_data['hdi_94.5%'] > 0))
            ).mean() * 100
            stats.append({
                'category': cat,
                'max_effect': max_abs_effect,
                'mean_effect': mean_abs_effect,
                'pct_significant': pct_significant,
                'n_params': len(cat_data)
            })

    stats_df = pd.DataFrame(stats)

    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Feature Importance Summary - Phase 1A Open Rates',
                 fontsize=14, fontweight='bold', y=0.98)

    colors_list = ['#1f77b4', '#2ca02c', '#9467bd', '#ff7f0e', '#d62728']

    # Panel 1: Maximum absolute effect size
    ax1.barh(range(len(stats_df)), stats_df['max_effect'], color=colors_list, alpha=0.8, edgecolor='black')
    ax1.set_yticks(range(len(stats_df)))
    ax1.set_yticklabels(category_names, fontsize=11)
    ax1.set_xlabel('Maximum Absolute Effect Size (Logit Scale)', fontsize=11, fontweight='bold')
    ax1.set_title('A) Maximum Effect Size by Category', fontsize=12, fontweight='bold', pad=10)
    ax1.grid(axis='x', alpha=0.3, linestyle=':')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # Add values on bars
    for i, v in enumerate(stats_df['max_effect']):
        ax1.text(v + 0.02, i, f'{v:.3f}', va='center', fontweight='bold', fontsize=10)

    # Panel 2: Percentage of statistically significant parameters
    ax2.barh(range(len(stats_df)), stats_df['pct_significant'], color=colors_list, alpha=0.8, edgecolor='black')
    ax2.set_yticks(range(len(stats_df)))
    ax2.set_yticklabels(category_names, fontsize=11)
    ax2.set_xlabel('% Parameters Statistically Significant', fontsize=11, fontweight='bold')
    ax2.set_title('B) Statistical Confidence by Category', fontsize=12, fontweight='bold', pad=10)
    ax2.set_xlim(0, 105)
    ax2.grid(axis='x', alpha=0.3, linestyle=':')
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    # Add values on bars
    for i, v in enumerate(stats_df['pct_significant']):
        ax2.text(v + 2, i, f'{v:.0f}%', va='center', fontweight='bold', fontsize=10)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Feature importance bar chart saved: {output_path}")
    plt.close()


def create_campaign_comparison_plot(data, output_path):
    """Create visualization comparing best vs worst campaigns."""

    campaign_data = data[data['category'] == 'campaign_intercept'].copy()
    campaign_data = campaign_data.sort_values('mean')

    # Get campaign IDs from predictions file
    pred_df = pd.read_csv('/home/yersinia/devel/octopus/reports/phase1/campaign_predictions.csv')
    pred_df['campaign_idx'] = range(len(pred_df))

    # Merge
    campaign_data['campaign_idx'] = campaign_data.iloc[:, 0].str.extract(r'\[(\d+)\]')[0].astype(int)
    campaign_data = campaign_data.merge(pred_df[['campaign_idx', 'campaign_id', 'open_rate_mean']],
                                        on='campaign_idx', how='left')

    # Shorten campaign IDs for display
    campaign_data['short_id'] = campaign_data['campaign_id'].str.split('_').str[-1]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle('Campaign-Level Open Rate Analysis - Phase 1A\n' +
                 'Campaign Identity Explains 90% of Variation (2.4x Range)',
                 fontsize=14, fontweight='bold', y=0.97)

    # Panel 1: Open rates with error bars
    y_pos = np.arange(len(campaign_data))

    # Convert to probability scale for interpretability
    open_rates = campaign_data['open_rate_mean'] * 100  # Convert to percentage
    colors_gradient = plt.cm.RdYlGn(np.linspace(0.2, 0.8, len(campaign_data)))

    ax1.barh(y_pos, open_rates, color=colors_gradient, alpha=0.8, edgecolor='black')
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(campaign_data['short_id'], fontsize=9)
    ax1.set_xlabel('Open Rate (%)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Campaign', fontsize=12, fontweight='bold')
    ax1.set_title('A) Predicted Open Rates by Campaign', fontsize=12, fontweight='bold', pad=10)
    ax1.grid(axis='x', alpha=0.3, linestyle=':')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # Add reference line for mean
    mean_rate = open_rates.mean()
    ax1.axvline(x=mean_rate, color='black', linestyle='--', linewidth=2, alpha=0.7, label=f'Mean: {mean_rate:.1f}%')
    ax1.legend(loc='lower right', fontsize=10)

    # Add values on bars
    for i, v in enumerate(open_rates):
        ax1.text(v + 0.1, i, f'{v:.1f}%', va='center', fontsize=9, fontweight='bold')

    # Panel 2: Effect sizes (logit scale)
    means = campaign_data['mean'].values
    lower = campaign_data['hdi_5.5%'].values
    upper = campaign_data['hdi_94.5%'].values

    ax2.errorbar(means, y_pos, xerr=[means - lower, upper - means],
                fmt='o', color='steelblue', ecolor='steelblue',
                markersize=8, capsize=5, alpha=0.8, linewidth=2)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(campaign_data['short_id'], fontsize=9)
    ax2.set_xlabel('Campaign Intercept (Logit Scale)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Campaign', fontsize=12, fontweight='bold')
    ax2.set_title('B) Campaign-Specific Effects (89% HDI)', fontsize=12, fontweight='bold', pad=10)
    ax2.grid(axis='x', alpha=0.3, linestyle=':')
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.axvline(x=campaign_data['mean'].mean(), color='red', linestyle='--',
               linewidth=2, alpha=0.7, label='Population Mean')
    ax2.legend(loc='lower right', fontsize=10)

    # Add key insight box
    best_rate = open_rates.max()
    worst_rate = open_rates.min()
    improvement = ((best_rate - worst_rate) / worst_rate) * 100

    insight_text = (f'🎯 KEY INSIGHT\n\n'
                   f'Best Campaign: {best_rate:.1f}%\n'
                   f'Worst Campaign: {worst_rate:.1f}%\n'
                   f'Ratio: {best_rate/worst_rate:.1f}x\n'
                   f'Improvement Potential: {improvement:.0f}%\n\n'
                   f'Campaign identity is the\nDOMINANT factor in\nemail open rates.')

    ax2.text(0.02, 0.98, insight_text, transform=ax2.transAxes,
            fontsize=10, verticalalignment='top', fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9, edgecolor='black', linewidth=2))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Campaign comparison plot saved: {output_path}")
    plt.close()


def main():
    """Generate all parameter importance visualizations."""

    # Create output directory
    output_dir = Path('/home/yersinia/devel/octopus/reports/phase1')
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("GENERATING PARAMETER IMPORTANCE VISUALIZATIONS")
    print("=" * 80)
    print()

    # Load data
    print("Loading parameter data...")
    data = load_parameter_data()
    print(f"✓ Loaded {len(data)} open-rate parameters across {data['category'].nunique()} categories")
    print()

    # Create visualizations
    print("Creating forest plot by category...")
    create_forest_plot_by_category(data, output_dir / 'parameter_importance_forest.png')
    print()

    print("Creating feature importance summary...")
    create_feature_importance_bar_chart(data, output_dir / 'parameter_importance_summary.png')
    print()

    print("Creating campaign comparison plot...")
    create_campaign_comparison_plot(data, output_dir / 'campaign_open_rate_comparison.png')
    print()

    print("=" * 80)
    print("✅ ALL VISUALIZATIONS COMPLETE")
    print("=" * 80)
    print()
    print(f"Output directory: {output_dir}")
    print()
    print("Files generated:")
    print("  1. parameter_importance_forest.png (forest plots by category)")
    print("  2. parameter_importance_summary.png (feature importance bar charts)")
    print("  3. campaign_open_rate_comparison.png (best vs worst campaigns)")
    print()


if __name__ == '__main__':
    main()
