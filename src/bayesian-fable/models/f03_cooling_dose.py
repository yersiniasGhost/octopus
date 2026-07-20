"""F3 — Cooling-dose weather salience (mechanism question; series flagship).

Estimand: does recently-experienced cooling demand drive engagement *through
felt bills*? The dose is ``cdd_base65 × kwh_cl_slope`` — campaign-window
cooling degree days × the building's physical cooling sensitivity (Gen-1
thermal physics joined to Gen-2 engagement for the first time).

Identification: the interaction varies WITHIN campaign (recipients of the
same send differ in slope), so campaign-level confounders (message, agency,
list construction) cannot mimic ``b_dose`` — campaign varying intercepts
absorb them entirely. Rethinking Ch. 8 (interactions) + Ch. 13 (clusters).

The heating-side analogue (HDD × kwh_hl_slope) is NOT estimable with today's
data — 99.96% of dose rows are May–Sep 2025 sends (34 winter rows) — and is
deliberately not fit (live-data finding #1, proposals doc §1).

Robustness: refit with ``kwh_cl_r2 >= 0.5`` (slopes are estimates; r² is
their precision) via ``--variant reliable``.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from models.engagement import build_bernoulli_engagement, simulate_engagement

MODEL_ID = 'f03_cooling_dose'
OUTCOME = 'replied'
TERMS = {'cdd_base65': 0.3, 'kwh_cl_slope': 0.3}
INTERACTION = ('dose', 'cdd_base65', 'kwh_cl_slope')


def load_frame(variant: str = 'full', **_) -> pd.DataFrame:
    from core.frames import load_exposure_frame
    frame = load_exposure_frame(channel='text', require_weather=True, require_thermal=True)
    frame = frame.dropna(subset=['cdd_base65', 'kwh_cl_slope'])
    if variant == 'reliable':
        frame = frame[frame['kwh_cl_r2'].fillna(0) >= 0.5]
    return frame.reset_index(drop=True)


def simulate(rng: np.random.Generator, **kwargs) -> Tuple[pd.DataFrame, Dict[str, float]]:
    return simulate_engagement(
        rng, OUTCOME,
        campaign_terms={'cdd_base65': 0.15},
        row_terms={'kwh_cl_slope': 0.1},
        interaction=('dose', 'cdd_base65', 'kwh_cl_slope', 0.3),
        **kwargs)


def build(frame: pd.DataFrame, **_) -> pm.Model:
    model, scalers = build_bernoulli_engagement(frame, OUTCOME, terms=TERMS,
                                                interaction=INTERACTION)
    build.scalers = scalers
    return model


def dose_contrast(idata, cdd_z: float = 1.0, slope_hi: float = 1.0,
                  slope_lo: float = -1.0) -> Dict[str, float]:
    """Decision output: hot-week vs mild-week send contrast, high- vs
    low-sensitivity household, on the probability scale (posterior means of
    the marginal contrast; REs at zero)."""
    post = idata.posterior

    def prob(cdd, slope):
        logit = (post['a'] + post['b_cdd_base65'] * cdd + post['b_kwh_cl_slope'] * slope
                 + post['b_dose'] * cdd * slope).values.flatten()
        return 1 / (1 + np.exp(-logit))

    contrast_hi = prob(cdd_z, slope_hi) - prob(0.0, slope_hi)
    contrast_lo = prob(cdd_z, slope_lo) - prob(0.0, slope_lo)
    diff = contrast_hi - contrast_lo
    return {
        'hot_vs_mild_high_slope_mean': float(contrast_hi.mean()),
        'hot_vs_mild_low_slope_mean': float(contrast_lo.mean()),
        'difference_mean': float(diff.mean()),
        'difference_p_gt_0': float((diff > 0).mean()),
    }
