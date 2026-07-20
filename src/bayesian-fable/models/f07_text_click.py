"""F7 — What predicts text-link clicks in the 2026 IMPACT cohort?

Estimand set: relative contribution of (a) message themes, (b) window weather,
(c) participant demographics to per-send click probability, within the only
regime where clicks are observed (Jan–Mar 2026, 12 campaigns; finding #5 /
F6 §2b). ~12k events on ~39k sends — the richest outcome in the dataset.

Design: nested variant ladder on ONE frame, PSIS-LOO compared. Which block
buys predictive skill is the "most consequential predictor" question stated
statistically. Clusters (month, county, campaign) enter every rung, so blocks
are judged on what they add BEYOND cluster structure.

    re_only   varying intercepts only (month + county + campaign)
    demog     + estimated_income, household_size, total_energy_burden
    weather   demog + temp_mean_f, freezing_hours
    themes    demog + six message_types dummies (backfilled 2026-07-15)
    full      demog + weather + themes

Identification caveats (honest, per catalog §4.3a): weather and themes both
vary at the CAMPAIGN grain — 12 clusters — and campaign REs compete with
them for the same variation. Coefficients read as "what survives partial
pooling across 12 campaigns", not sharp causal effects. Demographics vary at
row grain and are cleanly identified.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from core.frames import MESSAGE_TYPES
from models.engagement import build_bernoulli_engagement, simulate_engagement

MODEL_ID = 'f07_text_click'
OUTCOME = 'text_clicked'
WEATHER_TERMS = {'temp_mean_f': 0.3, 'freezing_hours': 0.3}
THEME_TERMS = {f'has_{mt}': 0.5 for mt in MESSAGE_TYPES}
# NOT total_energy_burden: ~8% coverage in the IMPACT cohort would drop 92%
# of the frame (39k → 3.2k rows).
COVARIATES = ['estimated_income', 'household_size']
VARIANTS = ('re_only', 'demog', 'weather', 'themes', 'full')


def load_frame(**_) -> pd.DataFrame:
    from core.frames import load_exposure_frame
    frame = load_exposure_frame(channel='text', require_weather=True,
                                required_covariates=COVARIATES)
    frame = frame[frame['month'] >= '2026-01']  # click-tracking regime gate
    return frame.dropna(subset=list(WEATHER_TERMS)).reset_index(drop=True)


def simulate(rng: np.random.Generator, **kwargs) -> Tuple[pd.DataFrame, Dict[str, float]]:
    binary = {f'has_{mt}': (0.4, beta) for mt, beta in zip(
        MESSAGE_TYPES, [0.4, -0.2, 0.0, 0.15, 0.0, -0.3])}
    return simulate_engagement(
        rng, OUTCOME, a=-1.0,  # clicks are common (~31%), unlike replies
        campaign_terms={'temp_mean_f': -0.2, 'freezing_hours': 0.25},
        binary_terms=binary, **kwargs)


def build(frame: pd.DataFrame, variant: str = 'full', **_) -> pm.Model:
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, got '{variant}'")
    terms = WEATHER_TERMS if variant in ('weather', 'full') else {}
    binary = THEME_TERMS if variant in ('themes', 'full') else {}
    covariates = [] if variant == 're_only' else COVARIATES
    # campaign-only REs: every IMPACT campaign is single-month/single-county,
    # so month/county REs would be collinear with campaign REs (divergence
    # ridge observed 2026-07-16). Month/season and county contrasts are NOT
    # separable from campaign identity in this cohort.
    model, scalers = build_bernoulli_engagement(frame, OUTCOME, terms=terms,
                                                binary_terms=binary, covariates=covariates,
                                                clusters=('campaign',))
    build.scalers = scalers
    return model


def fit_all(frame: pd.DataFrame, label: str = '', **sampler_kwargs) -> pd.DataFrame:
    from core.workflow import fit_ladder
    prefix = f'{MODEL_ID}_{label}' if label else MODEL_ID
    return fit_ladder(build, frame, VARIANTS, prefix, OUTCOME, **sampler_kwargs)
