"""F8 — What predicts email-link clicks? (rare-event companion to F7)

Estimand set mirrors F7 — themes / weather / demographics — on the email
channel, where clicks ARE tracked across all campaigns (unlike text).
249 events on ~119k sends (~0.2%).

Two grains, matched to where each predictor varies (2026-07-16 redesign
after the exposure-grain LOO ladder was OOM-killed — pointwise log-lik at
119k rows × 4 variants needs more RAM than this box has free):

* **Campaign-grain Binomial ladder** (63 rows): weather and themes are
  campaign-constant, so summing Bernoullis to Binomial is likelihood-
  equivalent for those blocks — and PSIS-LOO on 63 rows is free.
  Variants: re_only / weather / themes / full. A per-campaign
  overdispersion RE plays the role campaign REs played at exposure grain;
  month varying intercepts close the season→weather backdoor.
* **`full_exposure`** (~119k rows, no loglik): row-grain demographic
  coefficients, adjusted for campaign/month/county REs + weather + themes.

Season note: 62 of 63 email campaigns are summer 2025 (one small 2026-03
send, 8 clicks). This frame IS the summer collection — an email seasonal
split is not estimable and is documented rather than fit.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from core.frames import MESSAGE_TYPES, PARTICIPANT_COVARIATES, index_factor, zscore
from models.engagement import build_bernoulli_engagement, simulate_engagement

MODEL_ID = 'f08_email_click'
OUTCOME = 'email_clicked'
WEATHER_TERMS = {'temp_mean_f': 0.3, 'hot_hours': 0.3}  # summer frame: heat, not freeze
THEME_TERMS = {f'has_{mt}': 0.5 for mt in MESSAGE_TYPES}
VARIANTS = ('re_only', 'weather', 'themes', 'full')  # campaign-grain ladder


def _exposure_frame() -> pd.DataFrame:
    from core.frames import load_exposure_frame
    frame = load_exposure_frame(channel='email', require_weather=True)
    return frame.dropna(subset=list(WEATHER_TERMS)).reset_index(drop=True)


def load_frame(variant: str = None, **_) -> pd.DataFrame:
    frame = _exposure_frame()
    if variant == 'full_exposure':
        return frame
    firsts = {c: (c, 'first') for c in [*WEATHER_TERMS, *THEME_TERMS, 'month']}
    return (frame.groupby('campaign_id')
            .agg(n=(OUTCOME, 'size'), k=(OUTCOME, 'sum'), **firsts)
            .reset_index())


def simulate(rng: np.random.Generator, **kwargs) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Known-answer test for the exposure-grain (full_exposure) builder; the
    campaign-grain Binomial pattern is validated by F1's recovery gate."""
    binary = {f'has_{mt}': (0.4, beta) for mt, beta in zip(
        MESSAGE_TYPES, [0.3, 0.0, -0.25, 0.0, 0.2, 0.0])}
    return simulate_engagement(
        rng, OUTCOME, a=-4.0,
        campaign_terms={'temp_mean_f': 0.2, 'hot_hours': -0.15},
        binary_terms=binary, **kwargs)


def _build_campaign_binomial(frame: pd.DataFrame, variant: str) -> Tuple[pm.Model, Dict]:
    terms = WEATHER_TERMS if variant in ('weather', 'full') else {}
    binary = THEME_TERMS if variant in ('themes', 'full') else {}
    binary = {c: s for c, s in binary.items() if frame[c].nunique() > 1}
    n, k = frame['n'].to_numpy(), frame['k'].to_numpy()
    base_rate = max(k.sum() / n.sum(), 1e-6)
    month_idx, month_map = index_factor(frame['month'])
    scalers, z_values = {}, {}
    for col in terms:
        z_values[col], scalers[col] = zscore(frame[col])

    coords = {'campaign': frame['campaign_id'].tolist(), 'month': list(month_map)}
    with pm.Model(coords=coords) as model:
        a = pm.Normal('a', mu=float(np.log(base_rate / (1 - base_rate))), sigma=1.0)
        # per-campaign overdispersion RE (the campaign RE of the exposure grain)
        sigma_c = pm.Exponential('sigma_campaign', lam=1.0)
        z_c = pm.Normal('campaign_offset', mu=0.0, sigma=1.0, dims='campaign')
        sigma_m = pm.Exponential('sigma_month', lam=2.0)
        z_m = pm.Normal('month_offset', mu=0.0, sigma=1.0, dims='month')
        logit_p = a + sigma_c * z_c + (sigma_m * z_m)[month_idx]
        for col, prior_sigma in terms.items():
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=prior_sigma)
            logit_p = logit_p + b * z_values[col]
        for col, prior_sigma in binary.items():
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=prior_sigma)
            logit_p = logit_p + b * frame[col].to_numpy(dtype=float)
        pm.Binomial(OUTCOME, n=n, logit_p=logit_p, observed=k, dims='campaign')
    return model, scalers


def build(frame: pd.DataFrame, variant: str = 'full_exposure', **_) -> pm.Model:
    if variant == 'full_exposure':
        model, scalers = build_bernoulli_engagement(
            frame, OUTCOME, terms=WEATHER_TERMS, binary_terms=THEME_TERMS,
            covariates=PARTICIPANT_COVARIATES)
    elif variant in VARIANTS:
        model, scalers = _build_campaign_binomial(frame, variant)
    else:
        raise ValueError(f"variant must be 'full_exposure' or one of {VARIANTS}")
    build.scalers = scalers
    return model


def fit_all(frame: pd.DataFrame, label: str = '', **sampler_kwargs) -> pd.DataFrame:
    from core.workflow import fit_ladder
    prefix = f'{MODEL_ID}_{label}' if label else MODEL_ID
    return fit_ladder(build, frame, VARIANTS, prefix, OUTCOME, **sampler_kwargs)
