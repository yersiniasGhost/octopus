"""F5 — Ordered engagement ladder (new outcome family).

Estimand: how do message treatments shift the whole engagement ladder
``no_engagement < clicked < replied`` at once?

Rethinking Ch. 12: engagement intensity is ordinal, not binary — a
cumulative-logit model with ordered cutpoints lets one treatment effect
move the entire ladder instead of fitting separate, incompatible
Bernoullis for click and reply.

    R ~ OrderedLogistic(phi, kappa),  kappa ordered
    phi = a_campaign[c] + Σ_t b_t · has_type_t + covariate adjustment

Frame restriction: 2026 IMPACT text cohort only — the single tracking
regime where text clicks are recorded (live-data finding #5; pooling
click across regimes would confound tracking with behavior).

Opt-out is NOT forced onto the ladder (it is qualitatively different, not
"less engagement"): ``variant='optout'`` fits a companion Bernoulli with
the same predictor structure, so a message type that raises replies AND
raises opt-outs is visible as such.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from core.frames import MESSAGE_TYPES, index_factor, zscore

try:  # transform name moved across PyMC 5.x releases
    from pymc.distributions.transforms import ordered
except ImportError:  # pragma: no cover
    from pymc.distributions.transforms import univariate_ordered as ordered

MODEL_ID = 'f05_engagement_ordered'
OUTCOME = 'ladder'
OUTCOME_BY_VARIANT = {'optout': 'opted_out'}  # companion Bernoulli observes opted_out
LADDER_LEVELS = ['no_engagement', 'clicked', 'replied']
# 2026-07-16: burden dropped — ~8% coverage in the IMPACT cohort meant the
# Jul-9 fit saw only 3,249 of ~38k rows (and predates the theme backfill).
COVARIATES = ['estimated_income', 'household_size']


def load_frame(**_) -> pd.DataFrame:
    from core.frames import load_exposure_frame
    frame = load_exposure_frame(channel='text', require_weather=False,
                                required_covariates=COVARIATES)
    frame = frame[frame['agency'].fillna('').str.contains('IMPACT') &
                  (pd.to_datetime(frame['sent_at']) >= '2026-01-01')]
    frame = frame.copy()
    frame['ladder'] = np.select(
        [frame['replied'] == 1, frame['text_clicked'] == 1], [2, 1], default=0)
    return frame.reset_index(drop=True)


def simulate(rng: np.random.Generator, n_campaigns: int = 12,
             n_per_campaign: int = 1500) -> Tuple[pd.DataFrame, Dict[str, float]]:
    kappa = np.array([1.8, 3.2])
    treatment_betas = {'urgency_deadline': 0.4, 'savings_financial': 0.2,
                       'personalized_qualified': 0.5}
    covariate_betas = {'estimated_income': -0.1, 'household_size': 0.05,
                       'total_energy_burden': 0.2}
    campaign_re = rng.normal(0, 0.3, n_campaigns)
    campaign_types = {mt: rng.binomial(1, 0.4, n_campaigns) for mt in MESSAGE_TYPES}

    n = n_campaigns * n_per_campaign
    campaign_idx = np.repeat(np.arange(n_campaigns), n_per_campaign)
    frame = pd.DataFrame({'campaign_id': [f'sim-{i:03d}' for i in campaign_idx]})
    phi = campaign_re[campaign_idx]
    truth: Dict[str, float] = {'kappa[0]': kappa[0], 'kappa[1]': kappa[1]}
    for mt in MESSAGE_TYPES:
        frame[f'has_{mt}'] = campaign_types[mt][campaign_idx]
        beta = treatment_betas.get(mt, 0.0)
        phi = phi + beta * frame[f'has_{mt}'].to_numpy()
        truth[f'b_{mt}'] = beta
    for col, beta in covariate_betas.items():
        frame[col] = rng.normal(0, 1, n)
        phi = phi + beta * frame[col].to_numpy()
        truth[f'b_{col}'] = beta

    # cumulative logit: P(R <= k) = invlogit(kappa_k - phi)
    p_le = 1 / (1 + np.exp(-(kappa[None, :] - phi[:, None])))
    u = rng.uniform(size=n)
    frame['ladder'] = (u[:, None] > p_le).sum(axis=1)
    frame['opted_out'] = 0  # companion outcome unused in simulation
    return frame, truth


def _linear_predictor(model_frame: pd.DataFrame, scalers: Dict) -> Tuple:
    """Campaign RE + message-type treatments + covariate adjustment (shared
    between the ladder and opt-out variants)."""
    campaign_idx, campaign_map = index_factor(model_frame['campaign_id'])
    sigma = pm.Exponential('sigma_campaign', lam=2.0)
    offset = pm.Normal('campaign_offset', mu=0.0, sigma=1.0, dims='campaign')
    phi = (sigma * offset)[campaign_idx]
    for mt in MESSAGE_TYPES:
        if model_frame[f'has_{mt}'].nunique() > 1:  # skip constant treatments
            b = pm.Normal(f'b_{mt}', mu=0.0, sigma=0.5)
            phi = phi + b * model_frame[f'has_{mt}'].to_numpy()
    for col in COVARIATES:
        z, scalers[col] = zscore(model_frame[col])
        b = pm.Normal(f'b_{col}', mu=0.0, sigma=0.5)
        phi = phi + b * z
    return phi, campaign_map


def build(frame: pd.DataFrame, variant: str = 'ladder', **_) -> pm.Model:
    scalers: Dict = {}
    _, campaign_map = index_factor(frame['campaign_id'])
    coords = {'campaign': list(campaign_map), 'obs': np.arange(len(frame)),
              'cutpoint': [0, 1]}

    with pm.Model(coords=coords) as model:
        phi, _ = _linear_predictor(frame, scalers)
        if variant == 'ladder':
            # Ordered prior means give an ordered default initval — an explicit
            # initval would break pm.compute_log_likelihood (fgraph limitation).
            kappa = pm.Normal('kappa', mu=np.array([-1.0, 1.0]), sigma=1.5,
                              transform=ordered, dims='cutpoint')
            pm.OrderedLogistic('ladder', eta=phi, cutpoints=kappa,
                               observed=frame['ladder'].to_numpy(dtype=int),
                               compute_p=False)
        elif variant == 'optout':
            a = pm.Normal('a', mu=-3.0, sigma=1.0)
            pm.Bernoulli('opted_out', logit_p=a + phi,
                         observed=frame['opted_out'].to_numpy(dtype=int), dims='obs')
        else:
            raise ValueError(f"variant must be 'ladder' or 'optout', got '{variant}'")

    build.scalers = scalers
    return model
