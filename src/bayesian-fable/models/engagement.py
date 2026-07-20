"""Shared engagement-model machinery for F2 (weather) and F3 (cooling dose).

Structure (Rethinking Ch. 13 — multiple cluster types, non-centered):

    y ~ Bernoulli(logit_p)
    logit_p = a + a_month[m] + a_county[g] + a_campaign[c]
            + Σ b_k · z(term_k)                (campaign- and row-grain terms)
            + b_int · z(col_a) · z(col_b)      (optional interaction)
            + Σ b_j · z(covariate_j)           (participant adjustment set)
"""
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from core.frames import PARTICIPANT_COVARIATES, index_factor, zscore
from core.workflow import noncentered_re

CLUSTER_COLS = {'month': 'month', 'county': 'county', 'campaign': 'campaign_id'}


def build_bernoulli_engagement(frame: pd.DataFrame, outcome: str, terms: Dict[str, float],
                               interaction: Optional[Tuple[str, str, str]] = None,
                               covariates=PARTICIPANT_COVARIATES,
                               binary_terms: Optional[Dict[str, float]] = None,
                               clusters: Tuple[str, ...] = ('month', 'county', 'campaign')
                               ) -> Tuple[pm.Model, Dict]:
    """Build the hierarchical Bernoulli model.

    terms: {column: prior_sigma} — each gets ``b_<column> ~ Normal(0, prior_sigma)``.
    interaction: (name, col_a, col_b) — adds ``b_<name> ~ Normal(0, 0.3)`` on
        the product of the two already-standardized columns.
    binary_terms: {column: prior_sigma} — 0/1 columns entered RAW (exp(b) is
        the odds ratio directly); constant columns are skipped, not errored.
    clusters: which varying-intercept sets to include. In the 2026 IMPACT
        cohort every campaign is single-month AND single-county, so month and
        county REs are perfect linear combinations of campaign REs — fitting
        all three there creates a degenerate ridge (~150 divergences/fit,
        observed 2026-07-16). Pass ('campaign',) for that cohort.
    Returns (model, scaler_params) — persist scalers with the trace.
    """
    y = frame[outcome].to_numpy(dtype=int)
    base_rate = max(y.mean(), 1e-4)
    scalers, z_values = {}, {}
    for col in list(terms) + list(covariates):
        z_values[col], scalers[col] = zscore(frame[col])
    binary_terms = {col: ps for col, ps in (binary_terms or {}).items()
                    if frame[col].nunique() > 1}

    indices, coords = {}, {}
    for cluster in clusters:
        indices[cluster], mapping = index_factor(frame[CLUSTER_COLS[cluster]])
        coords[cluster] = list(mapping)
    coords['obs'] = np.arange(len(frame))

    with pm.Model(coords=coords) as model:
        a = pm.Normal('a', mu=float(np.log(base_rate / (1 - base_rate))), sigma=1.0)
        logit_p = a
        for cluster in clusters:
            re = noncentered_re(cluster, len(coords[cluster]), dims=cluster)
            logit_p = logit_p + re[indices[cluster]]
        for col, prior_sigma in terms.items():
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=prior_sigma)
            logit_p = logit_p + b * z_values[col]
        for col, prior_sigma in binary_terms.items():
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=prior_sigma)
            logit_p = logit_p + b * frame[col].to_numpy(dtype=float)
        if interaction:
            name, col_a, col_b = interaction
            b_int = pm.Normal(f'b_{name}', mu=0.0, sigma=0.3)
            logit_p = logit_p + b_int * z_values[col_a] * z_values[col_b]
        for col in covariates:
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=0.5)
            logit_p = logit_p + b * z_values[col]
        pm.Bernoulli(outcome, logit_p=logit_p, observed=y, dims='obs')

    return model, scalers


def simulate_engagement(rng: np.random.Generator, outcome: str, campaign_terms: Dict[str, float],
                        row_terms: Optional[Dict[str, float]] = None,
                        interaction: Optional[Tuple[str, str, str, float]] = None,
                        binary_terms: Optional[Dict[str, Tuple[float, float]]] = None,
                        n_campaigns: int = 40, n_per_campaign: int = 400,
                        a: float = -2.5) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Generative simulation from the assumed process (known-answer test).

    campaign_terms / row_terms: {column: true_beta} at campaign / row grain.
    interaction: (name, col_a, col_b, true_beta).
    binary_terms: {column: (prevalence, true_beta)} — campaign-grain 0/1 flags
        (message themes are properties of the send, so they vary by campaign).
    """
    row_terms = row_terms or {}

    def _std(values: np.ndarray) -> np.ndarray:
        # Standardize within-sample so the sim matches the statistical model
        # exactly (the builder z-scores per-sample; with few campaign-level
        # values, raw≠z would leak the interaction into the main effects).
        return (values - values.mean()) / values.std()

    sigmas = {'month': 0.25, 'county': 0.3, 'campaign': 0.4}
    months = [f'2025-{m:02d}' for m in range(1, 9)]
    counties = [f'County{i}' for i in range(6)]

    campaign_month = rng.integers(0, len(months), n_campaigns)
    month_re = rng.normal(0, sigmas['month'], len(months))
    county_re = rng.normal(0, sigmas['county'], len(counties))
    campaign_re = rng.normal(0, sigmas['campaign'], n_campaigns)
    campaign_values = {col: rng.normal(0, 1, n_campaigns) for col in campaign_terms}

    n = n_campaigns * n_per_campaign
    campaign_idx = np.repeat(np.arange(n_campaigns), n_per_campaign)
    county_idx = rng.integers(0, len(counties), n)

    covariate_betas = {'estimated_income': -0.1, 'household_size': 0.05,
                       'total_energy_burden': 0.2}
    frame = pd.DataFrame({
        'campaign_id': [f'sim-{i:03d}' for i in campaign_idx],
        'month': [months[campaign_month[i]] for i in campaign_idx],
        'county': [counties[i] for i in county_idx],
    })
    logit_p = (a + month_re[campaign_month[campaign_idx]] + county_re[county_idx]
               + campaign_re[campaign_idx])
    truth = {'a': a}
    for col, beta in campaign_terms.items():
        frame[col] = _std(campaign_values[col][campaign_idx])
        logit_p = logit_p + beta * frame[col].to_numpy()
        truth[f'b_{col}'] = beta
    for col, beta in row_terms.items():
        frame[col] = _std(rng.normal(0, 1, n))
        logit_p = logit_p + beta * frame[col].to_numpy()
        truth[f'b_{col}'] = beta
    for col, (prevalence, beta) in (binary_terms or {}).items():
        flags = rng.binomial(1, prevalence, n_campaigns)
        frame[col] = flags[campaign_idx]
        logit_p = logit_p + beta * frame[col].to_numpy()
        truth[f'b_{col}'] = beta
    for col, beta in covariate_betas.items():
        frame[col] = _std(rng.normal(0, 1, n))
        logit_p = logit_p + beta * frame[col].to_numpy()
        truth[f'b_{col}'] = beta
    if interaction:
        name, col_a, col_b, beta = interaction
        logit_p = logit_p + beta * frame[col_a].to_numpy() * frame[col_b].to_numpy()
        truth[f'b_{name}'] = beta

    frame[outcome] = rng.binomial(1, 1 / (1 + np.exp(-logit_p)))
    return frame, truth
