#!/usr/bin/env python3
"""
Phase 1A: Messaging Effectiveness Model

2-stage hierarchical Bayesian logistic regression for email campaign effectiveness.
Funnel: Send → Open → Click

Model Structure:
- Stage 1: P(Open | features) - Logistic regression with campaign random effects
- Stage 2: P(Click | Open, features) - Conditional logistic regression

Features:
- Campaign-level random effects (partial pooling)
- Message type effects (cost, savings, urgency, personalization, improvement, event)
- Geographic effects (city/zip)
- Temporal effects (month)
- Offer characteristics (savings amount, cost, kwh)

Created: 2025-10-15
"""

import pymc as pm
import numpy as np
import pandas as pd
from typing import Dict, Optional


def build_messaging_model(
    data: Dict,
    prior_config: Optional[Dict] = None
) -> pm.Model:
    """
    Build 2-stage hierarchical Bayesian messaging effectiveness model.

    Parameters
    ----------
    data : Dict
        Prepared data dictionary from prepare_messaging_data.py containing:
        - n_records: Total number of contacts
        - n_campaigns: Number of campaigns
        - n_msg_types: Number of message types
        - n_locations: Number of unique locations
        - campaign_idx: Campaign indices for each record
        - msg_type_idx: Message type indices
        - location_idx: Location indices
        - month_idx: Month indices (0-11)
        - opened: Binary outcome (1=opened, 0=not opened)
        - clicked: Binary outcome (1=clicked, 0=not clicked)
        - savings_std: Standardized savings amount
        - monthly_cost_std: Standardized monthly cost
        - kwh_std: Standardized kwh usage

    prior_config : Dict, optional
        Custom prior configuration. If None, uses defaults based on
        email marketing benchmarks:
        - Open rate: ~20-30% → logit scale μ ≈ -1.5 to -0.8
        - Click rate (given open): ~10-20% → logit scale μ ≈ -2 to -1.4

    Returns
    -------
    pm.Model
        PyMC model ready for sampling
    """

    # Default prior configuration
    if prior_config is None:
        prior_config = {
            # Stage 1: Open rate priors (expecting low rates based on data: ~3-5%)
            'mu_alpha_open': {'mu': -3.0, 'sigma': 1.0},  # ~ 5% baseline
            'sigma_alpha_open': {'sigma': 0.5},

            # Stage 2: Click rate priors (given open: ~5-10%)
            'mu_alpha_click': {'mu': -2.5, 'sigma': 1.0},  # ~ 8% baseline
            'sigma_alpha_click': {'sigma': 0.5},

            # Message type effects (can vary ±50%)
            'msg_type_effect': {'sigma': 0.5},

            # Location effects (smaller variation)
            'location_effect': {'sigma': 0.3},

            # Temporal effects (seasonal variation)
            'month_effect': {'sigma': 0.2},

            # Offer sensitivity (weak to moderate effects)
            'offer_effect': {'sigma': 0.3}
        }

    # Extract dimensions
    n_campaigns = data['n_campaigns']
    n_msg_types = data['n_msg_types']
    n_locations = data['n_locations']

    # Extract data arrays
    campaign_idx = data['campaign_idx']
    msg_type_idx = data['msg_type_idx']
    location_idx = data['location_idx']
    month_idx = data['month_idx']

    opened = data['opened']
    clicked = data['clicked']

    savings_std = data['savings_std']
    monthly_cost_std = data['monthly_cost_std']
    kwh_std = data['kwh_std']

    with pm.Model() as model:

        # ========================================
        # STAGE 1: OPEN RATE MODEL
        # ========================================

        # Population-level parameters (non-centered parameterization)
        mu_alpha_open = pm.Normal(
            'mu_alpha_open',
            mu=prior_config['mu_alpha_open']['mu'],
            sigma=prior_config['mu_alpha_open']['sigma']
        )
        sigma_alpha_open = pm.HalfNormal(
            'sigma_alpha_open',
            sigma=prior_config['sigma_alpha_open']['sigma']
        )

        # Campaign random effects (non-centered)
        z_alpha_open = pm.Normal('z_alpha_open', 0, 1, shape=n_campaigns)
        alpha_open = pm.Deterministic(
            'alpha_open',
            mu_alpha_open + z_alpha_open * sigma_alpha_open
        )

        # Message type effects
        msg_type_effect_open = pm.Normal(
            'msg_type_effect_open',
            0,
            prior_config['msg_type_effect']['sigma'],
            shape=n_msg_types
        )

        # Location effects
        location_effect_open = pm.Normal(
            'location_effect_open',
            0,
            prior_config['location_effect']['sigma'],
            shape=n_locations
        )

        # Temporal effects (monthly seasonality)
        month_effect_open = pm.Normal(
            'month_effect_open',
            0,
            prior_config['month_effect']['sigma'],
            shape=12
        )

        # Offer characteristic effects
        beta_savings_open = pm.Normal(
            'beta_savings_open',
            0,
            prior_config['offer_effect']['sigma']
        )
        beta_cost_open = pm.Normal(
            'beta_cost_open',
            0,
            prior_config['offer_effect']['sigma']
        )
        beta_kwh_open = pm.Normal(
            'beta_kwh_open',
            0,
            prior_config['offer_effect']['sigma']
        )

        # Linear predictor for open rate
        logit_open = (
            alpha_open[campaign_idx] +
            msg_type_effect_open[msg_type_idx] +
            location_effect_open[location_idx] +
            month_effect_open[month_idx] +
            beta_savings_open * savings_std +
            beta_cost_open * monthly_cost_std +
            beta_kwh_open * kwh_std
        )

        # Open probability
        p_open = pm.Deterministic('p_open', pm.math.sigmoid(logit_open))

        # Likelihood for open
        opened_obs = pm.Bernoulli('opened_obs', p=p_open, observed=opened)

        # ========================================
        # STAGE 2: CLICK RATE MODEL (conditional on opened)
        # ========================================

        # Filter to only opened emails
        opened_mask = opened == 1
        n_opened = int(opened.sum())

        if n_opened > 0:  # Only if there are opened emails

            # Population-level parameters (non-centered)
            mu_alpha_click = pm.Normal(
                'mu_alpha_click',
                mu=prior_config['mu_alpha_click']['mu'],
                sigma=prior_config['mu_alpha_click']['sigma']
            )
            sigma_alpha_click = pm.HalfNormal(
                'sigma_alpha_click',
                sigma=prior_config['sigma_alpha_click']['sigma']
            )

            # Campaign random effects (non-centered)
            z_alpha_click = pm.Normal('z_alpha_click', 0, 1, shape=n_campaigns)
            alpha_click = pm.Deterministic(
                'alpha_click',
                mu_alpha_click + z_alpha_click * sigma_alpha_click
            )

            # Message type effects
            msg_type_effect_click = pm.Normal(
                'msg_type_effect_click',
                0,
                prior_config['msg_type_effect']['sigma'],
                shape=n_msg_types
            )

            # Location effects
            location_effect_click = pm.Normal(
                'location_effect_click',
                0,
                prior_config['location_effect']['sigma'],
                shape=n_locations
            )

            # Offer characteristic effects
            beta_savings_click = pm.Normal(
                'beta_savings_click',
                0,
                prior_config['offer_effect']['sigma']
            )
            beta_cost_click = pm.Normal(
                'beta_cost_click',
                0,
                prior_config['offer_effect']['sigma']
            )
            beta_kwh_click = pm.Normal(
                'beta_kwh_click',
                0,
                prior_config['offer_effect']['sigma']
            )

            # Linear predictor for click rate (only for opened emails)
            logit_click = (
                alpha_click[campaign_idx[opened_mask]] +
                msg_type_effect_click[msg_type_idx[opened_mask]] +
                location_effect_click[location_idx[opened_mask]] +
                beta_savings_click * savings_std[opened_mask] +
                beta_cost_click * monthly_cost_std[opened_mask] +
                beta_kwh_click * kwh_std[opened_mask]
            )

            # Click probability (conditional on opened)
            p_click = pm.Deterministic('p_click', pm.math.sigmoid(logit_click))

            # Likelihood for click (conditional on opened)
            clicked_obs = pm.Bernoulli(
                'clicked_obs',
                p=p_click,
                observed=clicked[opened_mask]
            )

        # ========================================
        # DERIVED QUANTITIES
        # ========================================

        # End-to-end conversion rate per campaign
        # E[conversion] = E[P(open)] * E[P(click|open)]
        # This is an approximation; exact computation would require integration

        # Average open rate per campaign
        avg_p_open_campaign = pm.Deterministic(
            'avg_p_open_campaign',
            pm.math.sigmoid(alpha_open)
        )

        if n_opened > 0:
            # Average click rate per campaign (conditional)
            avg_p_click_campaign = pm.Deterministic(
                'avg_p_click_campaign',
                pm.math.sigmoid(alpha_click)
            )

            # End-to-end conversion rate estimate per campaign
            conversion_rate_campaign = pm.Deterministic(
                'conversion_rate_campaign',
                avg_p_open_campaign * avg_p_click_campaign
            )

        # Message type effectiveness (marginal effects on logit scale)
        # These can be interpreted as log-odds ratios

    return model


def get_model_summary(trace, data: Dict) -> pd.DataFrame:
    """
    Generate human-readable summary of model results.

    Parameters
    ----------
    trace : arviz.InferenceData
        MCMC trace from sampling
    data : Dict
        Data dictionary with lookup mappings

    Returns
    -------
    pd.DataFrame
        Summary statistics for key parameters
    """
    import arviz as az

    summary = az.summary(
        trace,
        var_names=[
            'mu_alpha_open', 'sigma_alpha_open',
            'mu_alpha_click', 'sigma_alpha_click',
            'msg_type_effect_open', 'msg_type_effect_click',
            'beta_savings_open', 'beta_savings_click',
            'beta_cost_open', 'beta_cost_click',
            'beta_kwh_open', 'beta_kwh_click'
        ],
        hdi_prob=0.89
    )

    return summary


def predict_campaign_performance(
    trace,
    data: Dict,
    campaign_idx: int
) -> Dict[str, float]:
    """
    Predict performance metrics for a specific campaign.

    Parameters
    ----------
    trace : arviz.InferenceData
        MCMC trace
    data : Dict
        Data dictionary
    campaign_idx : int
        Campaign index to predict for

    Returns
    -------
    Dict[str, float]
        Predicted metrics with uncertainty
    """
    import arviz as az

    # Extract posterior samples
    posterior = trace.posterior

    # Open rate prediction
    open_rate_samples = posterior['avg_p_open_campaign'].values[:, :, campaign_idx].flatten()
    open_rate_mean = float(open_rate_samples.mean())
    open_rate_hdi = az.hdi(open_rate_samples, hdi_prob=0.89)

    # Click rate prediction (if available)
    if 'avg_p_click_campaign' in posterior:
        click_rate_samples = posterior['avg_p_click_campaign'].values[:, :, campaign_idx].flatten()
        click_rate_mean = float(click_rate_samples.mean())
        click_rate_hdi = az.hdi(click_rate_samples, hdi_prob=0.89)

        # Conversion rate
        conversion_samples = posterior['conversion_rate_campaign'].values[:, :, campaign_idx].flatten()
        conversion_mean = float(conversion_samples.mean())
        conversion_hdi = az.hdi(conversion_samples, hdi_prob=0.89)
    else:
        click_rate_mean = None
        click_rate_hdi = None
        conversion_mean = None
        conversion_hdi = None

    return {
        'open_rate_mean': open_rate_mean,
        'open_rate_lower': float(open_rate_hdi[0]),
        'open_rate_upper': float(open_rate_hdi[1]),
        'click_rate_mean': click_rate_mean,
        'click_rate_lower': float(click_rate_hdi[0]) if click_rate_hdi is not None else None,
        'click_rate_upper': float(click_rate_hdi[1]) if click_rate_hdi is not None else None,
        'conversion_rate_mean': conversion_mean,
        'conversion_rate_lower': float(conversion_hdi[0]) if conversion_hdi is not None else None,
        'conversion_rate_upper': float(conversion_hdi[1]) if conversion_hdi is not None else None
    }
