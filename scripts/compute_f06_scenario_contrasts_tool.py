#!/usr/bin/env python
"""Posterior scenario contrasts for f06 (impact2026) on the outcome scale.

Rebuilds the impact2026 frame, loads the latest f06 trace + scaler params, and
reports population-average applications per 10,000 sends under counterfactual
settings of each factor (flag flipped for all rows, HDD at mean/+1SD, income at
$25k/$60k). These are logistic population counterfactuals — for flags whose
real-world rows differ compositionally (last-week especially), the observed raw
contrast is the safer headline; this table quantifies the model's adjusted view.

Usage:
    source venv/bin/activate
    python scripts/compute_f06_scenario_contrasts_tool.py
"""
import glob
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / 'src' / 'bayesian-fable')]

import arviz as az  # noqa: E402
import numpy as np  # noqa: E402

from core.frames import index_factor  # noqa: E402
from models import f06_application_hazard as f06  # noqa: E402

INFERENCE_DIR = REPO_ROOT / 'data' / 'inference' / 'fable' / 'f06_application_hazard'


def main() -> int:
    frame = f06.load_frame(variant='impact2026')
    trace = az.from_netcdf(sorted(glob.glob(str(INFERENCE_DIR / 'trace_*.nc')))[-1])
    report = json.load(open(sorted(glob.glob(str(INFERENCE_DIR / 'report_*.json')))[-1]))
    scalers = report['scalers']
    post = trace.posterior.stack(s=('chain', 'draw')).thin(s=40)

    county_idx, _ = index_factor(frame['county'])
    month_idx, _ = index_factor(frame['month'])
    a, a_county, a_month = post['a'].values, post['a_county'].values, post['a_month'].values
    bins = [c for c in f06.BINARY_PREDICTORS if f'b_{c}' in post and frame[c].nunique() > 1]

    def rate10k(df):
        lp = np.broadcast_to(a, (len(df), a.shape[0])).copy()
        lp += a_county[county_idx, :] + a_month[month_idx, :]
        for c in bins:
            lp += post[f'b_{c}'].values[None, :] * df[c].to_numpy(dtype=float)[:, None]
        for c in f06.CONTINUOUS_PREDICTORS:
            z = (df[c].to_numpy(dtype=float) - scalers[c]['mean']) / scalers[c]['std']
            lp += post[f'b_{c}'].values[None, :] * z[:, None]
        mean_p = (1 / (1 + np.exp(-lp))).mean(axis=0) * 10000
        return np.percentile(mean_p, [3, 50, 97])

    scenarios = {}
    for col in ['in_last_week_of_wave', 'is_first_in_wave', 'is_first_comm']:
        for v in (0, 1):
            d = frame.copy(); d[col] = v
            scenarios[f'{col}={v}'] = rate10k(d)
    hdd_mean, hdd_sd = scalers['hdd_base65']['mean'], scalers['hdd_base65']['std']
    for label, hdd in [(f'hdd=mean({hdd_mean:.0f})', hdd_mean), (f'hdd=+1SD({hdd_mean + hdd_sd:.0f})', hdd_mean + hdd_sd)]:
        d = frame.copy(); d['hdd_base65'] = hdd
        scenarios[label] = rate10k(d)
    for income in (25000, 60000):
        d = frame.copy(); d['estimated_income'] = income
        scenarios[f'income=${income // 1000}k'] = rate10k(d)
    scenarios['observed(as-is)'] = rate10k(frame)

    print('Posterior applications per 10,000 sends [3%, median, 97%]:')
    for k, (lo, med, hi) in scenarios.items():
        print(f'  {k:28s} {med:7.1f}  [{lo:.1f}, {hi:.1f}]')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
