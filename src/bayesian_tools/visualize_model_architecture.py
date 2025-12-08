#!/usr/bin/env python3
"""
Visualize Hierarchical Bayesian Messaging Model Architecture

Creates comprehensive diagrams showing:
1. Model structure (plate notation)
2. Parameter hierarchy
3. Data flow diagram
4. Full mathematical specification

Phase 1A/1B/1C Model Visualization
2-Stage Hierarchical Logistic Regression for Email Campaign Effectiveness

Created: 2025-10-16
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle
import numpy as np

# Set publication-quality defaults
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica']
plt.rcParams['font.size'] = 10
plt.rcParams['axes.linewidth'] = 1.5


def create_plate_notation_diagram():
    """
    Create plate notation diagram showing hierarchical structure
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Title
    ax.text(5, 9.5, 'Hierarchical Bayesian Messaging Model\n2-Stage Conversion Funnel',
            ha='center', va='top', fontsize=16, fontweight='bold')

    # ========================================
    # HYPERPRIORS (Population Level)
    # ========================================

    # Stage 1: Open Rate Hyperpriors
    hyperprior_y = 8.5
    ax.add_patch(FancyBboxPatch((0.2, hyperprior_y - 0.8), 1.5, 0.7,
                                boxstyle="round,pad=0.05",
                                facecolor='#E8F4FD', edgecolor='#1E88E5', linewidth=2))
    ax.text(0.95, hyperprior_y - 0.15, r'$\mu_{\alpha_{open}}$', ha='center', fontsize=11, fontweight='bold')
    ax.text(0.95, hyperprior_y - 0.45, r'$\mathcal{N}(-3.0, 1.0)$', ha='center', fontsize=9)

    ax.add_patch(FancyBboxPatch((2.0, hyperprior_y - 0.8), 1.5, 0.7,
                                boxstyle="round,pad=0.05",
                                facecolor='#E8F4FD', edgecolor='#1E88E5', linewidth=2))
    ax.text(2.75, hyperprior_y - 0.15, r'$\sigma_{\alpha_{open}}$', ha='center', fontsize=11, fontweight='bold')
    ax.text(2.75, hyperprior_y - 0.45, r'$\mathrm{HalfNormal}(0.5)$', ha='center', fontsize=9)

    # Stage 2: Click Rate Hyperpriors
    ax.add_patch(FancyBboxPatch((3.8, hyperprior_y - 0.8), 1.5, 0.7,
                                boxstyle="round,pad=0.05",
                                facecolor='#FFF3E0', edgecolor='#FB8C00', linewidth=2))
    ax.text(4.55, hyperprior_y - 0.15, r'$\mu_{\alpha_{click}}$', ha='center', fontsize=11, fontweight='bold')
    ax.text(4.55, hyperprior_y - 0.45, r'$\mathcal{N}(-2.5, 1.0)$', ha='center', fontsize=9)

    ax.add_patch(FancyBboxPatch((5.6, hyperprior_y - 0.8), 1.5, 0.7,
                                boxstyle="round,pad=0.05",
                                facecolor='#FFF3E0', edgecolor='#FB8C00', linewidth=2))
    ax.text(6.35, hyperprior_y - 0.15, r'$\sigma_{\alpha_{click}}$', ha='center', fontsize=11, fontweight='bold')
    ax.text(6.35, hyperprior_y - 0.45, r'$\mathrm{HalfNormal}(0.5)$', ha='center', fontsize=9)

    # Population Effects Label
    ax.text(3.5, hyperprior_y + 0.4, 'POPULATION-LEVEL HYPERPRIORS',
            ha='center', fontsize=12, fontweight='bold', color='#424242',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=1.5))

    # ========================================
    # CAMPAIGN-LEVEL RANDOM EFFECTS
    # ========================================

    campaign_y = 6.8

    # Non-centered parameterization box
    ax.add_patch(FancyBboxPatch((0.5, campaign_y - 1.2), 3.0, 1.0,
                                boxstyle="round,pad=0.1",
                                facecolor='#E3F2FD', edgecolor='#1976D2', linewidth=2.5))
    ax.text(2.0, campaign_y - 0.2, 'Campaign Random Effects (Open)',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(2.0, campaign_y - 0.55, r'$z_{\alpha_{open}}^{(c)} \sim \mathcal{N}(0, 1)$', ha='center', fontsize=10)
    ax.text(2.0, campaign_y - 0.85, r'$\alpha_{open}^{(c)} = \mu_{\alpha_{open}} + \sigma_{\alpha_{open}} \cdot z_{\alpha_{open}}^{(c)}$',
            ha='center', fontsize=9)

    ax.add_patch(FancyBboxPatch((3.8, campaign_y - 1.2), 3.0, 1.0,
                                boxstyle="round,pad=0.1",
                                facecolor='#FFF8E1', edgecolor='#F57C00', linewidth=2.5))
    ax.text(5.3, campaign_y - 0.2, 'Campaign Random Effects (Click)',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(5.3, campaign_y - 0.55, r'$z_{\alpha_{click}}^{(c)} \sim \mathcal{N}(0, 1)$', ha='center', fontsize=10)
    ax.text(5.3, campaign_y - 0.85, r'$\alpha_{click}^{(c)} = \mu_{\alpha_{click}} + \sigma_{\alpha_{click}} \cdot z_{\alpha_{click}}^{(c)}$',
            ha='center', fontsize=9)

    # Plate notation (campaigns)
    ax.add_patch(Rectangle((0.3, campaign_y - 1.35), 6.7, 1.3,
                           fill=False, edgecolor='black', linewidth=2.5, linestyle='--'))
    ax.text(0.5, campaign_y - 1.55, r'$c \in \{1, ..., N_{campaigns}\}$',
            fontsize=10, style='italic')

    # Arrows from hyperpriors to campaign effects
    ax.annotate('', xy=(2.0, campaign_y - 0.15), xytext=(0.95, hyperprior_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=2, color='#1976D2'))
    ax.annotate('', xy=(2.0, campaign_y - 0.15), xytext=(2.75, hyperprior_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=2, color='#1976D2'))

    ax.annotate('', xy=(5.3, campaign_y - 0.15), xytext=(4.55, hyperprior_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=2, color='#F57C00'))
    ax.annotate('', xy=(5.3, campaign_y - 0.15), xytext=(6.35, hyperprior_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=2, color='#F57C00'))

    # ========================================
    # FEATURE EFFECTS
    # ========================================

    feature_y = 4.8

    # Message Type Effects
    ax.add_patch(FancyBboxPatch((0.3, feature_y - 0.6), 1.8, 0.5,
                                boxstyle="round,pad=0.05",
                                facecolor='#F3E5F5', edgecolor='#8E24AA', linewidth=2))
    ax.text(1.2, feature_y - 0.15, r'$\beta_{msg}^{open}$', ha='center', fontsize=10, fontweight='bold')
    ax.text(1.2, feature_y - 0.4, r'$\mathcal{N}(0, 0.5)$', ha='center', fontsize=8)

    # Location Effects
    ax.add_patch(FancyBboxPatch((2.3, feature_y - 0.6), 1.8, 0.5,
                                boxstyle="round,pad=0.05",
                                facecolor='#E8F5E9', edgecolor='#43A047', linewidth=2))
    ax.text(3.2, feature_y - 0.15, r'$\beta_{loc}^{open}$', ha='center', fontsize=10, fontweight='bold')
    ax.text(3.2, feature_y - 0.4, r'$\mathcal{N}(0, 0.3)$', ha='center', fontsize=8)

    # Temporal Effects
    ax.add_patch(FancyBboxPatch((4.3, feature_y - 0.6), 1.8, 0.5,
                                boxstyle="round,pad=0.05",
                                facecolor='#FCE4EC', edgecolor='#C2185B', linewidth=2))
    ax.text(5.2, feature_y - 0.15, r'$\beta_{month}^{open}$', ha='center', fontsize=10, fontweight='bold')
    ax.text(5.2, feature_y - 0.4, r'$\mathcal{N}(0, 0.2)$', ha='center', fontsize=8)

    # Offer Characteristics
    ax.add_patch(FancyBboxPatch((6.3, feature_y - 0.6), 2.5, 0.5,
                                boxstyle="round,pad=0.05",
                                facecolor='#FFF9C4', edgecolor='#F9A825', linewidth=2))
    ax.text(7.55, feature_y - 0.15, r'$\beta_{savings}, \beta_{cost}, \beta_{kwh}$', ha='center', fontsize=10, fontweight='bold')
    ax.text(7.55, feature_y - 0.4, r'$\mathcal{N}(0, 0.3)$', ha='center', fontsize=8)

    ax.text(4.4, feature_y + 0.3, 'FIXED EFFECTS (Shared across campaigns)',
            ha='center', fontsize=11, fontweight='bold', color='#424242',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=1.5))

    # ========================================
    # LINEAR PREDICTORS & LIKELIHOOD
    # ========================================

    predictor_y = 3.0

    # Stage 1: Open Rate
    ax.add_patch(FancyBboxPatch((0.5, predictor_y - 0.8), 3.0, 0.7,
                                boxstyle="round,pad=0.1",
                                facecolor='#BBDEFB', edgecolor='#1565C0', linewidth=2.5))
    ax.text(2.0, predictor_y - 0.15, 'Stage 1: Open Rate', ha='center', fontsize=11, fontweight='bold')
    ax.text(2.0, predictor_y - 0.5, r'$\mathrm{logit}(p_{open}) = \alpha_{open}^{(c)} + \beta_{msg} + \beta_{loc} + \beta_{month} + ...$',
            ha='center', fontsize=9)

    # Stage 2: Click Rate (conditional)
    ax.add_patch(FancyBboxPatch((3.8, predictor_y - 0.8), 3.0, 0.7,
                                boxstyle="round,pad=0.1",
                                facecolor='#FFE0B2', edgecolor='#EF6C00', linewidth=2.5))
    ax.text(5.3, predictor_y - 0.15, 'Stage 2: Click Rate', ha='center', fontsize=11, fontweight='bold')
    ax.text(5.3, predictor_y - 0.5, r'$\mathrm{logit}(p_{click} | open) = \alpha_{click}^{(c)} + \beta_{msg} + ...$',
            ha='center', fontsize=9)

    # Arrows from campaign effects to predictors
    ax.annotate('', xy=(2.0, predictor_y - 0.15), xytext=(2.0, campaign_y - 1.25),
                arrowprops=dict(arrowstyle='->', lw=2.5, color='#1565C0'))
    ax.annotate('', xy=(5.3, predictor_y - 0.15), xytext=(5.3, campaign_y - 1.25),
                arrowprops=dict(arrowstyle='->', lw=2.5, color='#EF6C00'))

    # Arrows from feature effects to predictors
    for x_feat in [1.2, 3.2, 5.2, 7.55]:
        ax.annotate('', xy=(2.0, predictor_y - 0.15), xytext=(x_feat, feature_y - 0.65),
                    arrowprops=dict(arrowstyle='->', lw=1.5, color='gray', alpha=0.6))
        ax.annotate('', xy=(5.3, predictor_y - 0.15), xytext=(x_feat, feature_y - 0.65),
                    arrowprops=dict(arrowstyle='->', lw=1.5, color='gray', alpha=0.6))

    # ========================================
    # OBSERVED DATA
    # ========================================

    data_y = 1.2

    ax.add_patch(FancyBboxPatch((0.5, data_y - 0.6), 3.0, 0.5,
                                boxstyle="round,pad=0.1",
                                facecolor='#C5CAE9', edgecolor='#3F51B5', linewidth=3))
    ax.text(2.0, data_y - 0.15, r'$y_{open} \sim \mathrm{Bernoulli}(p_{open})$',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(2.0, data_y - 0.4, 'Observed: 831 opens / 22,050 contacts', ha='center', fontsize=8, style='italic')

    ax.add_patch(FancyBboxPatch((3.8, data_y - 0.6), 3.0, 0.5,
                                boxstyle="round,pad=0.1",
                                facecolor='#FFCCBC', edgecolor='#D84315', linewidth=3))
    ax.text(5.3, data_y - 0.15, r'$y_{click} \sim \mathrm{Bernoulli}(p_{click})$',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(5.3, data_y - 0.4, 'Observed: 46 clicks / 831 opens', ha='center', fontsize=8, style='italic')

    # Arrows from predictors to data
    ax.annotate('', xy=(2.0, data_y - 0.05), xytext=(2.0, predictor_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=3, color='#3F51B5'))
    ax.annotate('', xy=(5.3, data_y - 0.05), xytext=(5.3, predictor_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=3, color='#D84315'))

    # Conditional dependency arrow
    ax.annotate('Conditional on\nEmail Opened', xy=(5.3, data_y - 0.05), xytext=(2.8, data_y - 0.3),
                arrowprops=dict(arrowstyle='->', lw=2, color='#E91E63', linestyle='dashed'),
                fontsize=8, color='#E91E63', ha='center')

    # ========================================
    # PLATE NOTATION FOR OBSERVATIONS
    # ========================================

    ax.add_patch(Rectangle((0.3, data_y - 0.75), 6.7, 0.7,
                           fill=False, edgecolor='black', linewidth=3, linestyle='--'))
    ax.text(0.5, data_y - 0.95, r'$i \in \{1, ..., N_{contacts}\}$',
            fontsize=10, style='italic')

    # ========================================
    # LEGEND & ANNOTATIONS
    # ========================================

    legend_y = 0.3

    # Model info box
    info_text = (
        'Model: 2-Stage Hierarchical Bayesian Logistic Regression\n'
        'Campaigns: 15 (Phase 1A) → 73 (Phase 1C)\n'
        'Parameters: ~342 (Phase 1A) → ~250 (Phase 1B) → ~300 (Phase 1C)\n'
        'Sampler: NumPyro NUTS (GPU-accelerated via JAX)\n'
        'Convergence: R̂ = 1.0, ESS > 3,000 ✓'
    )
    ax.text(7.8, legend_y + 0.3, info_text, fontsize=8,
            bbox=dict(boxstyle='round', facecolor='#FAFAFA', edgecolor='gray', linewidth=1.5),
            verticalalignment='top')

    # Color coding legend
    ax.text(0.5, legend_y, 'Color Coding:', fontsize=9, fontweight='bold')

    # Open rate components (blue)
    ax.add_patch(Rectangle((0.5, legend_y - 0.4), 0.3, 0.2, facecolor='#E3F2FD', edgecolor='#1976D2', linewidth=1.5))
    ax.text(0.9, legend_y - 0.3, 'Open Rate Components', fontsize=8)

    # Click rate components (orange)
    ax.add_patch(Rectangle((2.8, legend_y - 0.4), 0.3, 0.2, facecolor='#FFF8E1', edgecolor='#F57C00', linewidth=1.5))
    ax.text(3.2, legend_y - 0.3, 'Click Rate Components', fontsize=8)

    # Feature effects (various)
    ax.add_patch(Rectangle((5.2, legend_y - 0.4), 0.3, 0.2, facecolor='#F3E5F5', edgecolor='#8E24AA', linewidth=1.5))
    ax.text(5.6, legend_y - 0.3, 'Shared Feature Effects', fontsize=8)

    plt.tight_layout()
    return fig


def create_data_flow_diagram():
    """
    Create data flow diagram showing input → model → output
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Title
    ax.text(5, 9.5, 'Data Flow: Campaign Data → Bayesian Model → Predictions',
            ha='center', va='top', fontsize=16, fontweight='bold')

    # ========================================
    # INPUT DATA
    # ========================================

    input_y = 7.5

    # Campaign data
    ax.add_patch(FancyBboxPatch((0.3, input_y - 1.0), 2.0, 0.9,
                                boxstyle="round,pad=0.1",
                                facecolor='#E1F5FE', edgecolor='#01579B', linewidth=2))
    ax.text(1.3, input_y - 0.2, 'Campaign Data', ha='center', fontsize=11, fontweight='bold')
    ax.text(1.3, input_y - 0.45, '• campaign_id\n• message_type\n• sent_date',
            ha='center', fontsize=8)

    # Contact data
    ax.add_patch(FancyBboxPatch((2.5, input_y - 1.0), 2.0, 0.9,
                                boxstyle="round,pad=0.1",
                                facecolor='#E8F5E9', edgecolor='#1B5E20', linewidth=2))
    ax.text(3.5, input_y - 0.2, 'Contact Data', ha='center', fontsize=11, fontweight='bold')
    ax.text(3.5, input_y - 0.45, '• email, city, zip\n• kwh, savings\n• monthly_cost',
            ha='center', fontsize=8)

    # Engagement data
    ax.add_patch(FancyBboxPatch((4.7, input_y - 1.0), 2.0, 0.9,
                                boxstyle="round,pad=0.1",
                                facecolor='#FCE4EC', edgecolor='#880E4F', linewidth=2))
    ax.text(5.7, input_y - 0.2, 'Engagement', ha='center', fontsize=11, fontweight='bold')
    ax.text(5.7, input_y - 0.45, '• opened (Yes/No)\n• clicked (Yes/No)\n• timestamps',
            ha='center', fontsize=8)

    # MongoDB enrichment (optional Phase 1B)
    ax.add_patch(FancyBboxPatch((7.0, input_y - 1.0), 2.5, 0.9,
                                boxstyle="round,pad=0.1",
                                facecolor='#FFF3E0', edgecolor='#E65100', linewidth=2, linestyle='--'))
    ax.text(8.25, input_y - 0.2, 'MongoDB (Phase 1B)', ha='center', fontsize=11, fontweight='bold')
    ax.text(8.25, input_y - 0.45, '• Demographics\n• Home age, size\n• Household size',
            ha='center', fontsize=8, style='italic')

    ax.text(5, input_y + 0.5, 'INPUT DATA', ha='center', fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='black', linewidth=2))

    # ========================================
    # DATA PREPARATION
    # ========================================

    prep_y = 5.5

    ax.add_patch(FancyBboxPatch((1.5, prep_y - 0.7), 6.5, 0.6,
                                boxstyle="round,pad=0.1",
                                facecolor='#F5F5F5', edgecolor='#616161', linewidth=2))
    ax.text(4.75, prep_y - 0.15, 'Data Preparation Pipeline', ha='center', fontsize=11, fontweight='bold')
    ax.text(4.75, prep_y - 0.45, 'Feature engineering • Index creation • Standardization • Train/test split',
            ha='center', fontsize=9)

    # Arrows from input to preparation
    for x_in in [1.3, 3.5, 5.7, 8.25]:
        ax.annotate('', xy=(4.75, prep_y - 0.05), xytext=(x_in, input_y - 1.05),
                    arrowprops=dict(arrowstyle='->', lw=2, color='#616161'))

    # ========================================
    # BAYESIAN MODEL
    # ========================================

    model_y = 3.8

    # Model box
    ax.add_patch(FancyBboxPatch((2.0, model_y - 1.2), 5.5, 1.1,
                                boxstyle="round,pad=0.15",
                                facecolor='#E8EAF6', edgecolor='#283593', linewidth=3))
    ax.text(4.75, model_y - 0.2, 'Hierarchical Bayesian Model', ha='center', fontsize=12, fontweight='bold')
    ax.text(4.75, model_y - 0.5, 'GPU-Accelerated Sampling (NumPyro NUTS)', ha='center', fontsize=10)
    ax.text(4.75, model_y - 0.75, '2,000 draws × 4 chains = 8,000 posterior samples', ha='center', fontsize=9)
    ax.text(4.75, model_y - 0.95, 'Training time: 6.67 minutes (Phase 1A)', ha='center', fontsize=8, style='italic')

    # Arrow from preparation to model
    ax.annotate('', xy=(4.75, model_y - 0.05), xytext=(4.75, prep_y - 0.75),
                arrowprops=dict(arrowstyle='->', lw=3, color='#283593'))

    # ========================================
    # OUTPUTS
    # ========================================

    output_y = 1.8

    # Posterior samples
    ax.add_patch(FancyBboxPatch((0.5, output_y - 0.7), 2.2, 0.6,
                                boxstyle="round,pad=0.1",
                                facecolor='#C8E6C9', edgecolor='#2E7D32', linewidth=2))
    ax.text(1.6, output_y - 0.15, 'Posterior Samples', ha='center', fontsize=10, fontweight='bold')
    ax.text(1.6, output_y - 0.45, 'Trace: 342 parameters\n8,000 samples each',
            ha='center', fontsize=8)

    # Campaign predictions
    ax.add_patch(FancyBboxPatch((2.9, output_y - 0.7), 2.2, 0.6,
                                boxstyle="round,pad=0.1",
                                facecolor='#BBDEFB', edgecolor='#1565C0', linewidth=2))
    ax.text(4.0, output_y - 0.15, 'Campaign Predictions', ha='center', fontsize=10, fontweight='bold')
    ax.text(4.0, output_y - 0.45, 'Open rate: 2.6%-6.3%\nWith 89% HDI',
            ha='center', fontsize=8)

    # Diagnostic plots
    ax.add_patch(FancyBboxPatch((5.3, output_y - 0.7), 2.2, 0.6,
                                boxstyle="round,pad=0.1",
                                facecolor='#FFE0B2', edgecolor='#EF6C00', linewidth=2))
    ax.text(6.4, output_y - 0.15, 'Diagnostics', ha='center', fontsize=10, fontweight='bold')
    ax.text(6.4, output_y - 0.45, 'R̂, ESS, Trace plots\nConvergence checks',
            ha='center', fontsize=8)

    # Insights & recommendations
    ax.add_patch(FancyBboxPatch((7.7, output_y - 0.7), 2.0, 0.6,
                                boxstyle="round,pad=0.1",
                                facecolor='#F8BBD0', edgecolor='#C2185B', linewidth=2))
    ax.text(8.7, output_y - 0.15, 'Insights', ha='center', fontsize=10, fontweight='bold')
    ax.text(8.7, output_y - 0.45, 'Campaign rankings\nMessage effectiveness',
            ha='center', fontsize=8)

    # Arrows from model to outputs
    for x_out in [1.6, 4.0, 6.4, 8.7]:
        ax.annotate('', xy=(x_out, output_y + 0.05), xytext=(4.75, model_y - 1.25),
                    arrowprops=dict(arrowstyle='->', lw=2, color='#424242'))

    ax.text(5, output_y + 0.75, 'OUTPUTS & ANALYSIS', ha='center', fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='black', linewidth=2))

    # ========================================
    # PHASE INFORMATION
    # ========================================

    phase_y = 0.5

    phase_info = (
        'Phase 1A (Completed): 15 campaigns, CSV features only, 6.67 min training\n'
        'Phase 1B (Next): Add MongoDB demographics, 10-15 min training\n'
        'Phase 1C (Future): All 73 campaigns, 15-25 min training'
    )
    ax.text(5, phase_y, phase_info, ha='center', fontsize=9,
            bbox=dict(boxstyle='round', facecolor='#FFFDE7', edgecolor='#F57F17', linewidth=2))

    plt.tight_layout()
    return fig


def create_parameter_hierarchy_diagram():
    """
    Create hierarchical tree showing parameter structure
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Title
    ax.text(5, 9.5, 'Parameter Hierarchy\nFrom Population to Individual Predictions',
            ha='center', va='top', fontsize=16, fontweight='bold')

    # ========================================
    # LEVEL 1: POPULATION HYPERPARAMETERS
    # ========================================

    level1_y = 8.2

    ax.add_patch(FancyBboxPatch((3.5, level1_y - 0.5), 3.0, 0.4,
                                boxstyle="round,pad=0.1",
                                facecolor='#1565C0', edgecolor='black', linewidth=2))
    ax.text(5, level1_y - 0.15, 'POPULATION HYPERPARAMETERS (4)',
            ha='center', fontsize=11, fontweight='bold', color='white')

    # Hyperparameter boxes
    hyper_y = 7.2

    boxes = [
        (0.8, r'$\mu_{\alpha_{open}}$', '#E3F2FD', '#1976D2'),
        (2.4, r'$\sigma_{\alpha_{open}}$', '#E3F2FD', '#1976D2'),
        (4.0, r'$\mu_{\alpha_{click}}$', '#FFF8E1', '#F57C00'),
        (5.6, r'$\sigma_{\alpha_{click}}$', '#FFF8E1', '#F57C00')
    ]

    for x, label, facecolor, edgecolor in boxes:
        ax.add_patch(FancyBboxPatch((x - 0.6, hyper_y - 0.4), 1.2, 0.3,
                                    boxstyle="round,pad=0.05",
                                    facecolor=facecolor, edgecolor=edgecolor, linewidth=2))
        ax.text(x, hyper_y - 0.25, label, ha='center', fontsize=10, fontweight='bold')

        # Arrow from population box
        ax.annotate('', xy=(x, hyper_y - 0.1), xytext=(5, level1_y - 0.55),
                    arrowprops=dict(arrowstyle='->', lw=1.5, color='gray'))

    # ========================================
    # LEVEL 2: CAMPAIGN-LEVEL PARAMETERS
    # ========================================

    level2_y = 6.0

    ax.add_patch(FancyBboxPatch((2.5, level2_y - 0.5), 5.0, 0.4,
                                boxstyle="round,pad=0.1",
                                facecolor='#388E3C', edgecolor='black', linewidth=2))
    ax.text(5, level2_y - 0.15, 'CAMPAIGN-LEVEL PARAMETERS (30 = 15 × 2 stages)',
            ha='center', fontsize=11, fontweight='bold', color='white')

    # Campaign parameter groups
    campaign_y = 5.0

    # Open rate campaigns
    ax.add_patch(FancyBboxPatch((1.0, campaign_y - 0.8), 3.5, 0.7,
                                boxstyle="round,pad=0.1",
                                facecolor='#BBDEFB', edgecolor='#1565C0', linewidth=2))
    ax.text(2.75, campaign_y - 0.2, r'$\alpha_{open}^{(1)}, \alpha_{open}^{(2)}, ..., \alpha_{open}^{(15)}$',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(2.75, campaign_y - 0.5, 'Campaign-specific open rate intercepts', ha='center', fontsize=8)

    # Click rate campaigns
    ax.add_patch(FancyBboxPatch((5.0, campaign_y - 0.8), 3.5, 0.7,
                                boxstyle="round,pad=0.1",
                                facecolor='#FFE0B2', edgecolor='#EF6C00', linewidth=2))
    ax.text(6.75, campaign_y - 0.2, r'$\alpha_{click}^{(1)}, \alpha_{click}^{(2)}, ..., \alpha_{click}^{(15)}$',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(6.75, campaign_y - 0.5, 'Campaign-specific click rate intercepts', ha='center', fontsize=8)

    # Arrows from hyperparameters to campaigns
    ax.annotate('', xy=(2.75, campaign_y - 0.1), xytext=(1.7, hyper_y - 0.45),
                arrowprops=dict(arrowstyle='->', lw=2, color='#1565C0'))
    ax.annotate('', xy=(6.75, campaign_y - 0.1), xytext=(4.8, hyper_y - 0.45),
                arrowprops=dict(arrowstyle='->', lw=2, color='#EF6C00'))

    # ========================================
    # LEVEL 3: FEATURE EFFECTS
    # ========================================

    level3_y = 3.5

    ax.add_patch(FancyBboxPatch((1.5, level3_y - 0.5), 7.0, 0.4,
                                boxstyle="round,pad=0.1",
                                facecolor='#7B1FA2', edgecolor='black', linewidth=2))
    ax.text(5, level3_y - 0.15, 'FIXED FEATURE EFFECTS (~308 parameters)',
            ha='center', fontsize=11, fontweight='bold', color='white')

    # Feature groups
    feature_y = 2.5

    features = [
        (1.2, 'Message Type\n(5+5=10)', '#F3E5F5', '#8E24AA'),
        (2.8, 'Location\n(140+140=280)', '#E8F5E9', '#43A047'),
        (4.4, 'Temporal\n(12 months)', '#FCE4EC', '#C2185B'),
        (6.0, 'Offer Effects\n(3+3=6)', '#FFF9C4', '#F9A825')
    ]

    for x, label, facecolor, edgecolor in features:
        ax.add_patch(FancyBboxPatch((x - 0.6, feature_y - 0.5), 1.2, 0.4,
                                    boxstyle="round,pad=0.05",
                                    facecolor=facecolor, edgecolor=edgecolor, linewidth=2))
        ax.text(x, feature_y - 0.3, label, ha='center', fontsize=9, fontweight='bold')

        # Arrow from feature level box
        ax.annotate('', xy=(x, feature_y - 0.1), xytext=(5, level3_y - 0.55),
                    arrowprops=dict(arrowstyle='->', lw=1.5, color='gray'))

    # ========================================
    # LEVEL 4: INDIVIDUAL PREDICTIONS
    # ========================================

    level4_y = 1.2

    ax.add_patch(FancyBboxPatch((2.0, level4_y - 0.5), 6.0, 0.4,
                                boxstyle="round,pad=0.1",
                                facecolor='#D32F2F', edgecolor='black', linewidth=2))
    ax.text(5, level4_y - 0.15, 'INDIVIDUAL CONTACT PREDICTIONS (22,050 contacts)',
            ha='center', fontsize=11, fontweight='bold', color='white')

    # Individual predictions
    indiv_y = 0.3

    predictions = [
        (2.5, r'$p_{open}^{(i)}$', '#C5CAE9', '#3F51B5'),
        (4.5, r'$p_{click}^{(i)}$', '#FFCCBC', '#D84315'),
        (6.5, r'$p_{convert}^{(i)}$', '#F8BBD0', '#C2185B')
    ]

    for x, label, facecolor, edgecolor in predictions:
        ax.add_patch(FancyBboxPatch((x - 0.7, indiv_y - 0.25), 1.4, 0.2,
                                    boxstyle="round,pad=0.05",
                                    facecolor=facecolor, edgecolor=edgecolor, linewidth=2))
        ax.text(x, indiv_y - 0.15, label, ha='center', fontsize=10, fontweight='bold')

        # Arrow from prediction level box
        ax.annotate('', xy=(x, indiv_y + 0.02), xytext=(5, level4_y - 0.55),
                    arrowprops=dict(arrowstyle='->', lw=1.5, color='#D32F2F'))

    # Arrows showing combination from campaigns + features
    ax.annotate('', xy=(4.5, indiv_y + 0.02), xytext=(2.75, campaign_y - 0.85),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='#1565C0', alpha=0.5))
    ax.annotate('', xy=(4.5, indiv_y + 0.02), xytext=(3.2, feature_y - 0.55),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='#43A047', alpha=0.5))

    # ========================================
    # PARAMETER COUNT SUMMARY
    # ========================================

    summary_text = (
        'Total Parameters: ~342\n\n'
        'Population Level: 4\n'
        'Campaign Level: 30 (15 campaigns × 2 stages)\n'
        'Message Types: 10 (5 types × 2 stages)\n'
        'Locations: 280 (140 locations × 2 stages)\n'
        'Temporal: 12 (monthly effects, open only)\n'
        'Offer Effects: 6 (3 features × 2 stages)\n\n'
        'All estimated with full uncertainty\nvia 8,000 posterior samples'
    )
    ax.text(8.5, 5.5, summary_text, fontsize=8,
            bbox=dict(boxstyle='round', facecolor='#FAFAFA', edgecolor='gray', linewidth=2),
            verticalalignment='top')

    plt.tight_layout()
    return fig


def main():
    """
    Generate all model visualization diagrams
    """
    print("Generating Hierarchical Bayesian Model Visualizations...")
    print("="*70)

    # Create output directory
    import os
    output_dir = '/home/yersinia/devel/octopus/reports/model_diagrams'
    os.makedirs(output_dir, exist_ok=True)

    # Generate diagrams
    print("\n1. Creating Plate Notation Diagram...")
    fig1 = create_plate_notation_diagram()
    fig1.savefig(f'{output_dir}/model_plate_notation.png', dpi=300, bbox_inches='tight')
    print(f"   ✓ Saved: {output_dir}/model_plate_notation.png")
    plt.close(fig1)

    print("\n2. Creating Data Flow Diagram...")
    fig2 = create_data_flow_diagram()
    fig2.savefig(f'{output_dir}/model_data_flow.png', dpi=300, bbox_inches='tight')
    print(f"   ✓ Saved: {output_dir}/model_data_flow.png")
    plt.close(fig2)

    print("\n3. Creating Parameter Hierarchy Diagram...")
    fig3 = create_parameter_hierarchy_diagram()
    fig3.savefig(f'{output_dir}/model_parameter_hierarchy.png', dpi=300, bbox_inches='tight')
    print(f"   ✓ Saved: {output_dir}/model_parameter_hierarchy.png")
    plt.close(fig3)

    print("\n" + "="*70)
    print("All diagrams generated successfully!")
    print(f"\nOutput location: {output_dir}/")
    print("\nGenerated files:")
    print("  • model_plate_notation.png - Formal statistical model structure")
    print("  • model_data_flow.png - Data pipeline and outputs")
    print("  • model_parameter_hierarchy.png - Parameter organization")
    print("="*70)


if __name__ == '__main__':
    main()
