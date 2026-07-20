"""F6 — Which communication factors precede intake-form applications?

Estimand set (analyst request, 2026-07-13): per-send hazard of triggering an
application as a function of (a) channel, (b) message themes, (c) prior
communication count, (d) recency (receipt-lag adjusted), (e) window weather
(HDD/CDD + extremes), (f) first/last position in the campaign wave, adjusted
for demographics, county, and calendar month.

Design: discrete-time hazard at the exposure grain. Every deduped send is a
Bernoulli trial; y=1 iff the send is the best-confidence attributed trigger of
the participant's earliest application. Post-application sends are censored
(cannot cause a past event). This is the corrected framing of the analyst's
"look at every intake form completion" — case-only data cannot identify
influence; the ~300k non-converting sends are the comparison group.

DAG (catalog §4.3a extended): adjustment set for weather is {S: month, G:
county}; message/channel effects additionally lean on agency-driven
assignment, so campaign-level confounding is only partially closed — read
those coefficients as adjusted associations, not clean causal effects.

Variants:
    core         month + county varying intercepts (default)
    campaign_re  adds campaign varying intercepts (weather/message coefficients
                 then measure only what survives within-campaign pooling)
    strict       drops converters attributed with confidence < 0.85
                 (sensitivity to soft same-day/date-window attribution)
    text_only    restricts to text sends. Attribution runs through tracked
                 text clicks + mailer UTMs; email conversions are structurally
                 invisible (1 attributed event / 125k email sends), so channel
                 contrasts in `core` measure attribution observability, NOT
                 persuasion — within-text estimates are the trustworthy ones.
    impact2026   PRIMARY: text sends from 2026-01 on (the IMPACT cohort with
                 click ingestion). All 207 attributed text events fall here;
                 2025 text sends lack click tracking and cannot convert by
                 construction, so keeping them as trials would launder the
                 tracking regime into every campaign-level coefficient
                 (weather especially — the 2025 sends are the warm ones).

Rare outcome (~250 events / ~300k rows): intercept prior is centered on the
empirical base-rate logit; slopes Normal(0, 0.5) on z-scored predictors.
Fit advice: --sampler numpyro --no-loglik (pointwise log-lik would be ~10 GB).
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pymc as pm

from core.frames import MESSAGE_TYPES, index_factor, load_application_frame, zscore

MODEL_ID = 'f06_application_hazard'
OUTCOME = 'applied'

BINARY_PREDICTORS = ['is_first_comm', 'is_first_in_wave', 'in_last_week_of_wave',
                     'channel_text', 'channel_letter'] + [f'has_{mt}' for mt in MESSAGE_TYPES]
CONTINUOUS_PREDICTORS = ['log1p_n_prior', 'days_since_prev', 'hdd_base65', 'cdd_base65',
                         'estimated_income', 'household_size']
STRICT_CONFIDENCE = 0.85


def load_frame(variant: str = None, **_) -> pd.DataFrame:
    df = load_application_frame(require_weather=True)
    n0, k0 = len(df), int(df[OUTCOME].sum())
    df = df.dropna(subset=['county', 'estimated_income', 'household_size',
                           'hdd_base65', 'cdd_base65'])
    if variant == 'strict':
        soft = df[(df[OUTCOME] == 1) & (df['attribution_confidence'] < STRICT_CONFIDENCE)]
        df = df[~df['participant_id'].isin(soft['participant_id'])]
    if variant == 'text_only':
        df = df[df['channel'] == 'text']
    if variant in ('impact2026', 'impact2026_re'):
        df = df[(df['channel'] == 'text') & (df['sent_at'] >= pd.Timestamp('2026-01-01'))]
    df = df.copy()
    df['log1p_n_prior'] = np.log1p(df['n_prior_comms'])
    df['days_since_prev'] = df['days_since_prev'].fillna(0.0)  # paired with is_first_comm
    df['channel_text'] = (df['channel'] == 'text').astype(int)
    df['channel_letter'] = (df['channel'] == 'letter').astype(int)
    print(f'[{MODEL_ID}] frame: {len(df)} rows ({n0} pre-gates), '
          f'{int(df[OUTCOME].sum())} events ({k0} pre-gates); '
          f"channels: {df['channel'].value_counts().to_dict()}")
    return df


def simulate(rng: np.random.Generator, n: int = 60000) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Generative story with known coefficients for parameter recovery.

    Base rate is set well above the real ~0.001 (a=-5 → ~400 events): the
    recovery test needs enough events for the likelihood to dominate the
    Normal(0, 0.5) slope priors — at the real event count those priors
    legitimately shrink, which is calibration, not a bug.
    """
    counties = [f'County{i}' for i in range(6)]
    months = [f'2025-{m:02d}' for m in range(1, 13)]
    county_idx = rng.integers(0, len(counties), n)
    month_idx = rng.integers(0, len(months), n)
    county_re = rng.normal(0, 0.3, len(counties))
    month_re = rng.normal(0, 0.3, len(months))
    truth = {'a': -5.0, 'b_channel_text': 0.6, 'b_in_last_week_of_wave': 0.5,
             'b_hdd_base65': 0.3, 'b_log1p_n_prior': -0.2}
    frame = pd.DataFrame({
        'county': [counties[i] for i in county_idx],
        'month': [months[i] for i in month_idx],
        'channel_text': rng.binomial(1, 0.6, n),
        'channel_letter': np.zeros(n, dtype=int),
        'is_first_comm': rng.binomial(1, 0.2, n),
        'is_first_in_wave': rng.binomial(1, 0.25, n),
        'in_last_week_of_wave': rng.binomial(1, 0.3, n),
        'log1p_n_prior': rng.normal(1.0, 0.7, n),
        'days_since_prev': rng.exponential(20, n),
        'hdd_base65': rng.gamma(2, 40, n),
        'cdd_base65': rng.gamma(1.5, 15, n),
        'estimated_income': rng.normal(35000, 12000, n),
        'household_size': rng.integers(1, 6, n).astype(float),
    })
    for mt in MESSAGE_TYPES:
        frame[f'has_{mt}'] = rng.binomial(1, 0.3, n)
    logit_p = (truth['a'] + county_re[county_idx] + month_re[month_idx]
               + truth['b_channel_text'] * frame['channel_text']
               + truth['b_in_last_week_of_wave'] * frame['in_last_week_of_wave']
               + truth['b_hdd_base65'] * (frame['hdd_base65'] - frame['hdd_base65'].mean())
               / frame['hdd_base65'].std()
               + truth['b_log1p_n_prior'] * (frame['log1p_n_prior'] - frame['log1p_n_prior'].mean())
               / frame['log1p_n_prior'].std())
    frame['applied'] = rng.binomial(1, 1 / (1 + np.exp(-logit_p)))
    return frame, truth


def build(frame: pd.DataFrame, variant: str = 'core', **_) -> pm.Model:
    y = frame[OUTCOME].to_numpy(dtype=int)
    county_idx, county_map = index_factor(frame['county'])
    month_idx, month_map = index_factor(frame['month'])
    base_rate = max(y.mean(), 1e-6)
    scalers, z_values = {}, {}
    for col in CONTINUOUS_PREDICTORS:
        z_values[col], scalers[col] = zscore(frame[col])

    coords = {'county': list(county_map), 'month': list(month_map),
              'obs': np.arange(len(frame))}
    campaign_re = variant in ('campaign_re', 'impact2026_re')
    if campaign_re:
        campaign_idx, campaign_map = index_factor(frame['campaign_id'])
        coords['campaign'] = list(campaign_map)

    with pm.Model(coords=coords) as model:
        a = pm.Normal('a', mu=float(np.log(base_rate / (1 - base_rate))), sigma=1.0)
        logit_p = a
        for group, idx in [('county', county_idx), ('month', month_idx)]:
            sigma = pm.Exponential(f'sigma_{group}', lam=2.0)
            offset = pm.Normal(f'{group}_offset', mu=0.0, sigma=1.0, dims=group)
            logit_p = logit_p + pm.Deterministic(f'a_{group}', sigma * offset, dims=group)[idx]
        if campaign_re:
            sigma_c = pm.Exponential('sigma_campaign', lam=2.0)
            offset_c = pm.Normal('campaign_offset', mu=0.0, sigma=1.0, dims='campaign')
            logit_p = logit_p + pm.Deterministic('a_campaign', sigma_c * offset_c,
                                                 dims='campaign')[campaign_idx]
        for col in BINARY_PREDICTORS:
            if frame[col].nunique() < 2:  # e.g. channel dummies under text_only
                continue
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=0.5)
            logit_p = logit_p + b * frame[col].to_numpy(dtype=float)
        for col in CONTINUOUS_PREDICTORS:
            b = pm.Normal(f'b_{col}', mu=0.0, sigma=0.5)
            logit_p = logit_p + b * z_values[col]
        pm.Bernoulli(OUTCOME, logit_p=logit_p, observed=y, dims='obs')

    build.scalers = scalers
    return model


def odds_ratio_table(idata) -> pd.DataFrame:
    """Posterior odds ratios per factor — the analyst-facing summary."""
    rows = []
    for name in BINARY_PREDICTORS + CONTINUOUS_PREDICTORS:
        if f'b_{name}' not in idata.posterior:  # dropped constant column
            continue
        post = idata.posterior[f'b_{name}'].to_numpy().ravel()
        rows.append({'factor': name, 'odds_ratio': float(np.exp(post.mean())),
                     'or_hdi_3%': float(np.exp(np.quantile(post, 0.03))),
                     'or_hdi_97%': float(np.exp(np.quantile(post, 0.97))),
                     'p_positive': float((post > 0).mean())})
    return pd.DataFrame(rows).sort_values('p_positive', ascending=False)
