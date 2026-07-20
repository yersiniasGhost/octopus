"""F1 — Campaign engagement pooling ladder.

Estimand: how much do campaigns differ in engagement rate, and how much
should individual campaign estimates shrink toward the population mean?

Rethinking Ch. 13 (reedfrogs): three nested models on campaign-grain
Binomial counts —

    complete pooling:  logit(p)   = a_bar                (campaigns identical)
    no pooling:        logit(p_c) = a_c, independent     (campaigns unrelated)
    partial pooling:   a_c ~ Normal(a_bar, sigma)        (adaptive prior)

Compared with PSIS-LOO. The posterior for ``sigma`` (and the derived ICC)
is the empirical justification for campaign varying intercepts in every
downstream model. Fits in seconds → also the pipeline smoke test and the
reference LOO the registry never produced.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

MODEL_ID = 'f01_campaign_pooling'
OUTCOME = 'k'
VARIANTS = ('complete', 'none', 'partial')


def load_frame(channel: str = 'text', outcome: str = None, **_) -> pd.DataFrame:
    from core.frames import campaign_binomial_frame
    mapping = {channel: outcome} if outcome else None
    frame = campaign_binomial_frame(outcome_by_channel=mapping)
    frame = frame[frame['channel'] == channel]
    # Tracking-regime gate: text clicks are only ingested from 2026-01 (IMPACT
    # cohort). Earlier campaigns would enter as structural zeros and fake
    # heterogeneity that is really the tracking regime.
    if outcome == 'text_clicked':
        frame = frame[frame['month'] >= '2026-01']
    return frame.reset_index(drop=True)


def simulate(rng: np.random.Generator, n_campaigns: int = 60,
             a_bar: float = -2.5, sigma: float = 0.8) -> Tuple[pd.DataFrame, Dict[str, float]]:
    n = rng.integers(200, 3000, n_campaigns)
    a_campaign = rng.normal(a_bar, sigma, n_campaigns)
    k = rng.binomial(n, 1 / (1 + np.exp(-a_campaign)))
    frame = pd.DataFrame({'campaign_id': [f'sim-{i:03d}' for i in range(n_campaigns)],
                          'n': n, 'k': k})
    # With few clusters the posterior can only see the REALIZED heterogeneity,
    # so recovery is checked against the realized group-level moments.
    return frame, {'a_bar': float(a_campaign.mean()),
                   'sigma_campaign': float(a_campaign.std(ddof=1))}


def build(frame: pd.DataFrame, variant: str = 'partial', **_) -> pm.Model:
    n = frame['n'].to_numpy()
    k = frame['k'].to_numpy()
    coords = {'campaign': frame['campaign_id'].tolist()}

    with pm.Model(coords=coords) as model:
        if variant == 'complete':
            a_bar = pm.Normal('a_bar', mu=-2.5, sigma=1.0)
            pm.Binomial('k', n=n, logit_p=a_bar, observed=k, dims='campaign')
        elif variant == 'none':
            a_campaign = pm.Normal('a_campaign', mu=-2.5, sigma=1.5, dims='campaign')
            pm.Binomial('k', n=n, logit_p=a_campaign, observed=k, dims='campaign')
        elif variant == 'partial':
            a_bar = pm.Normal('a_bar', mu=-2.5, sigma=1.0)
            sigma = pm.Exponential('sigma_campaign', lam=1.0)
            offset = pm.Normal('campaign_offset', mu=0.0, sigma=1.0, dims='campaign')
            a_campaign = pm.Deterministic('a_campaign', a_bar + sigma * offset, dims='campaign')
            # ICC on the latent logit scale (residual variance pi^2/3)
            pm.Deterministic('icc', sigma**2 / (sigma**2 + np.pi**2 / 3))
            pm.Binomial('k', n=n, logit_p=a_campaign, observed=k, dims='campaign')
        else:
            raise ValueError(f"variant must be one of {VARIANTS}, got '{variant}'")

    return model


def fit_all(frame: pd.DataFrame, label: str = '', **sampler_kwargs) -> pd.DataFrame:
    """Fit the full ladder and compare with PSIS-LOO. `label` (e.g. the
    channel) keeps output directories separate across frames."""
    from core.workflow import fit_ladder
    prefix = f'{MODEL_ID}_{label}' if label else MODEL_ID
    return fit_ladder(build, frame, VARIANTS, prefix, OUTCOME, **sampler_kwargs)
