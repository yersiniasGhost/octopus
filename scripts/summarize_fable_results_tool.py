#!/usr/bin/env python
"""Consolidate bayesian-fable fit outputs into one markdown summary.

Walks data/inference/fable/<model_dir>/ for the LATEST report_*.json +
summary_*.csv per directory, plus any *_loo_compare_*.csv at the root, and
emits: convergence table, per-model coefficient tables (odds ratios for b_*
terms), RE scales/ICC, and LOO ladder comparisons.

Usage:
    python scripts/summarize_fable_results_tool.py [--filter f07] [--out FILE.md]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), '..', 'data', 'inference', 'fable')


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def model_dirs(name_filter=None):
    for d in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, d)
        if not os.path.isdir(path) or d == 'logs':
            continue
        if name_filter and name_filter not in d:
            continue
        report = latest(os.path.join(path, 'report_*.json'))
        if report:
            yield d, report, latest(os.path.join(path, 'summary_*.csv'))


def coefficient_table(summary_csv):
    df = pd.read_csv(summary_csv, index_col=0)
    rows = df[df.index.str.startswith(('b_', 'a', 'sigma_', 'icc', 'kappa'))].copy()
    rows = rows[~rows.index.str.contains(r'_offset|^a_(county|month|campaign)\[')]
    cols = [c for c in ['mean', 'sd', 'hdi_5.5%', 'hdi_94.5%', 'ess_bulk', 'r_hat'] if c in rows]
    rows = rows[cols]
    is_beta = rows.index.str.startswith('b_')
    rows.loc[is_beta, 'odds_ratio'] = np.exp(rows.loc[is_beta, 'mean']).round(3)
    return rows.round(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--filter', default=None, help='substring filter on model dir names')
    parser.add_argument('--out', default=None, help='write markdown here instead of stdout')
    args = parser.parse_args()

    lines = ['# bayesian-fable consolidated results', '']
    lines += ['## Convergence overview', '',
              '| model | trained | variant | n_obs | passed | divergences | max r̂ | min ESS |',
              '|---|---|---|---|---|---|---|---|']
    details = []
    for name, report_path, summary_path in model_dirs(args.filter):
        r = json.load(open(report_path))
        c = r.get('convergence') or {}
        lines.append(f"| {name} | {r.get('trained_at')} | {r.get('variant') or '—'} "
                     f"| {r.get('n_obs', '—')} | {c.get('passed')} "
                     f"| {(c.get('divergences') or {}).get('count', '—')} "
                     f"| {(c.get('r_hat') or {}).get('max_value', '—')} "
                     f"| {(c.get('ess') or {}).get('bulk_min', '—')} |")
        if summary_path:
            details += [f'\n## {name}', '',
                        coefficient_table(summary_path).to_markdown(), '']
    lines += [''] + details

    loo_files = sorted(glob.glob(os.path.join(ROOT, '*_loo_compare_*.csv')))
    if loo_files:
        lines += ['\n# PSIS-LOO ladder comparisons', '']
        for f in loo_files:
            if args.filter and args.filter not in os.path.basename(f):
                continue
            lines += [f'\n## {os.path.basename(f)}', '',
                      pd.read_csv(f, index_col=0).round(2).to_markdown(), '']

    text = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w') as fh:
            fh.write(text)
        print(f'wrote {args.out}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
