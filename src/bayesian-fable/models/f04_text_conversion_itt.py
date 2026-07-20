"""F4 — Text75–84 → IMPACT approval, intention-to-treat vs EGE control.

Estimand: ITT effect of being assigned to a Text75–84 list on program
approval — the only design in this project with a real control group
(EGE no-text parcels).

    List(T) ──→ Text ──→ approved      D, B → List(T) confound unless the
    D, B ──→ List(T);  D, B → approved  arms are covariate-balanced
    G ──→ everything

**Deliverable 1 is not a model**: the covariate-balance table between arms
(``--balance``). If balanced (|SMD| < 0.1), the simple model suffices; if
not, covariate adjustment carries the weight and both fits are reported.

Data source: the combined campaign-control export CSV with the IMPACT
approved-report roll-up — NOT Mongo ``applications``, which is structurally
blind to control-arm conversions (all attribution paths run through tracked
text clicks; live-data finding #3).

Prior: ``b_text ~ Normal(0, 0.5)`` — the observed ~4× raw ratio must be
earned through the likelihood, not assumed. E-values (model-04 convention)
quantify how strong unmeasured list-construction confounding would need to
be to explain the effect away.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from core.frames import PARTICIPANT_COVARIATES, covariate_balance, index_factor, load_itt_frame, zscore

MODEL_ID = 'f04_text_conversion_itt'
OUTCOME = 'approved'


def load_frame(csv_path: str = None, **kwargs) -> pd.DataFrame:
    if not csv_path:
        raise ValueError(
            "F4 needs --csv <combined campaign-control export>. The Jun-15 "
            "export (11,240 parcels) is not in this repo; regenerate it or "
            "point at a CSV with columns "
            "texted, approved, estimated_income, household_size, "
            "total_energy_burden, county (or pass column_map).")
    return load_itt_frame(csv_path, column_map=kwargs.get('column_map'))


def balance(frame: pd.DataFrame) -> pd.DataFrame:
    """Deliverable 1: arm balance before any fitting."""
    table = covariate_balance(frame, arm_col='texted')
    print(table.to_string(index=False, float_format=lambda v: f'{v:.3f}'))
    flagged = table[table['smd'].abs() > 0.1].dropna(subset=['smd'])
    verdict = 'BALANCED' if flagged.empty else f'IMBALANCED on {list(flagged.covariate)}'
    print(f'\nArms are {verdict} (|SMD| > 0.1 threshold)')
    return table


def simulate(rng: np.random.Generator, n: int = 10000,
             b_text: float = 1.2) -> Tuple[pd.DataFrame, Dict[str, float]]:
    counties = [f'County{i}' for i in range(5)]
    county_re = rng.normal(0, 0.3, len(counties))
    county_idx = rng.integers(0, len(counties), n)
    covariate_betas = {'estimated_income': -0.15, 'household_size': 0.05,
                       'total_energy_burden': 0.3}
    frame = pd.DataFrame({'county': [counties[i] for i in county_idx],
                          'texted': rng.binomial(1, 0.65, n)})
    logit_p = -3.0 + b_text * frame['texted'].to_numpy() + county_re[county_idx]
    truth = {'a': -3.0, 'b_text': b_text}
    for col, beta in covariate_betas.items():
        frame[col] = rng.normal(0, 1, n)
        logit_p = logit_p + beta * frame[col].to_numpy()
        truth[f'b_{col}'] = beta
    frame['approved'] = rng.binomial(1, 1 / (1 + np.exp(-logit_p)))
    return frame, truth


def build(frame: pd.DataFrame, variant: str = 'adjusted', **_) -> pm.Model:
    """variant='simple' → texted + county only (use when arms are balanced);
    variant='adjusted' → adds the covariate adjustment set."""
    y = frame['approved'].to_numpy(dtype=int)
    texted = frame['texted'].to_numpy(dtype=int)
    county_idx, county_map = index_factor(frame['county'])
    base_rate = max(y.mean(), 1e-4)
    scalers, z_values = {}, {}
    covariates = PARTICIPANT_COVARIATES if variant == 'adjusted' else []
    for col in covariates:
        z_values[col], scalers[col] = zscore(frame[col])

    with pm.Model(coords={'county': list(county_map), 'obs': np.arange(len(frame))}) as model:
        a = pm.Normal('a', mu=float(np.log(base_rate / (1 - base_rate))), sigma=1.0)
        b_text = pm.Normal('b_text', mu=0.0, sigma=0.5)
        sigma_county = pm.Exponential('sigma_county', lam=2.0)
        offset = pm.Normal('county_offset', mu=0.0, sigma=1.0, dims='county')
        a_county = pm.Deterministic('a_county', sigma_county * offset, dims='county')
        logit_p = a + b_text * texted + a_county[county_idx]
        for col in covariates:
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=0.5)
            logit_p = logit_p + b * z_values[col]
        pm.Deterministic('odds_ratio_text', pm.math.exp(b_text))
        pm.Bernoulli('approved', logit_p=logit_p, observed=y, dims='obs')

    build.scalers = scalers
    return model


def e_value_report(idata) -> Dict:
    """Sensitivity to unmeasured confounding (reuses the canonical Gen-2 helper)."""
    from src.bayesian_models.validation import compute_e_values
    b_text = float(idata.posterior['b_text'].mean())
    return compute_e_values({'b_text': b_text})
