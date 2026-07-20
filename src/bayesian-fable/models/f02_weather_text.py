"""F2 — Weather main effects on text engagement (policy question).

Estimand: total direct effect of window weather on text replies —
"should we send more when it's cold?"

DAG / identification (inputs-catalog §4.3a):

    S(month) ──→ W ──→ Y        backdoor W ← S → Y closed by month effects
    G(county) ──→ W             backdoor W ← G → D/B → Y closed by county effects
    campaign REs absorb residual message/agency/list variation

Adjustment set {S, G}; weather axes: one temperature axis (temp_mean_f — HDD
correlates at −0.94, pick one) plus one extremes axis (freezing_hours).
Honest caveat: weather varies at the campaign grain → effective N ≈ 86
campaigns, and temp/freeze correlate at r ≈ −0.77; report the joint posterior.

Outcome: `replied` — the universal text outcome across tracking regimes.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from models.engagement import build_bernoulli_engagement, simulate_engagement

MODEL_ID = 'f02_weather_text'
OUTCOME = 'replied'
WEATHER_TERMS = {'temp_mean_f': 0.3, 'freezing_hours': 0.3}
# 2026-07-16: total_energy_burden dropped from the adjustment set — it covers
# ~8% of the winter/IMPACT cohort, and season contrasts need a common
# adjustment set on comparable frames. (The Jul-9 pooled fit kept burden and
# therefore silently excluded 92% of winter rows.)
COVARIATES = ['estimated_income', 'household_size']


SEASON_MONTHS = {'summer': lambda m: '2025-05' <= m <= '2025-09',
                 'winter': lambda m: m >= '2025-11'}
# Season-appropriate extremes axis: freezing_hours is constant 0 in summer
# (zscore would crash) and hot_hours constant 0 in winter; the pooled model
# keeps the original temp+freezing spec for continuity with the Jul-9 fit.
SEASON_WEATHER = {'summer': {'temp_mean_f': 0.3, 'hot_hours': 0.3},
                  'winter': {'temp_mean_f': 0.3, 'freezing_hours': 0.3}}


def weather_terms(variant: str = None) -> Dict[str, float]:
    return SEASON_WEATHER.get(variant, WEATHER_TERMS)


def load_frame(variant: str = None, **_) -> pd.DataFrame:
    """variant: None/'all' → pooled; 'summer'/'winter' → seasonal subset.

    Seasonal caveat: season ≈ cohort here (summer = 2025 agencies/lists,
    winter = 2026 IMPACT), so cross-season coefficient differences read as
    "season + cohort", not season alone.
    """
    from core.frames import load_exposure_frame
    frame = load_exposure_frame(channel='text', require_weather=True,
                                required_covariates=COVARIATES)
    if variant in SEASON_MONTHS:
        frame = frame[frame['month'].map(SEASON_MONTHS[variant])]
    return frame.dropna(subset=list(weather_terms(variant))).reset_index(drop=True)


def simulate(rng: np.random.Generator, **kwargs) -> Tuple[pd.DataFrame, Dict[str, float]]:
    return simulate_engagement(
        rng, OUTCOME,
        campaign_terms={'temp_mean_f': -0.2, 'freezing_hours': 0.25},
        **kwargs)


def build(frame: pd.DataFrame, variant: str = None, **_) -> pm.Model:
    # Winter frame = the 12 IMPACT campaigns, each single-month/single-county:
    # month/county REs would be collinear with campaign REs there (see
    # engagement.build_bernoulli_engagement docstring).
    clusters = ('campaign',) if variant == 'winter' else ('month', 'county', 'campaign')
    model, scalers = build_bernoulli_engagement(frame, OUTCOME, terms=weather_terms(variant),
                                                covariates=COVARIATES, clusters=clusters)
    build.scalers = scalers  # exposed for persistence by the runner
    return model
