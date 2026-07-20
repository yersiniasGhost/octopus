#!/usr/bin/env python
"""CLI for the bayesian-fable model series.

Usage (from the repo root, venv active):

    python src/bayesian-fable/run_fable.py <model> <mode> [options]

Models: f01 f02 f03 f04 f05
Modes:
    simulate   fit on generative synthetic data and report parameter
               recovery (McElreath's known-answer test; no MongoDB needed)
    prior      build the model on real data and run the prior predictive
               check only (no NUTS)
    fit        full workflow: prior predictive → NUTS → diagnostics gate →
               posterior predictive → persist to data/inference/fable/
    balance    (f04 only) covariate-balance table between arms — run this
               BEFORE fitting f04

Examples:
    python src/bayesian-fable/run_fable.py f01 simulate
    python src/bayesian-fable/run_fable.py f01 fit --variant all --channel text
    python src/bayesian-fable/run_fable.py f03 fit --variant reliable
    python src/bayesian-fable/run_fable.py f04 balance --csv data/exports/combined_campaign_control.csv
"""
import argparse
import importlib
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parents[1]), str(_HERE)):  # repo root, then this folder
    if _p not in sys.path:
        sys.path.insert(0, _p)

MODELS = {
    'f01': 'models.f01_campaign_pooling',
    'f02': 'models.f02_weather_text',
    'f03': 'models.f03_cooling_dose',
    'f04': 'models.f04_text_conversion_itt',
    'f05': 'models.f05_engagement_ordered',
    'f06': 'models.f06_application_hazard',
    'f07': 'models.f07_text_click',
    'f08': 'models.f08_email_click',
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('model', choices=sorted(MODELS))
    parser.add_argument('mode', choices=['simulate', 'prior', 'fit', 'balance'])
    parser.add_argument('--variant', default=None, help='model variant (f01: '
                        'complete/none/partial/all; f03: full/reliable; f04: '
                        'simple/adjusted; f05: ladder/optout; f06: '
                        'core/campaign_re/strict/text_only/impact2026)')
    parser.add_argument('--channel', default='text', help='f01: email or text')
    parser.add_argument('--outcome', default=None,
                        help='f01: override the per-channel default outcome '
                             '(e.g. text_clicked, email_clicked)')
    parser.add_argument('--csv', default=None, help='f04: combined campaign-control export')
    parser.add_argument('--draws', type=int, default=2000)
    parser.add_argument('--tune', type=int, default=1000)
    parser.add_argument('--chains', type=int, default=4)
    parser.add_argument('--target-accept', type=float, default=0.9)
    parser.add_argument('--sampler', default='pymc', choices=['pymc', 'numpyro', 'nutpie', 'blackjax'],
                        help='NUTS backend (numpyro is much faster on large frames)')
    parser.add_argument('--no-loglik', action='store_true',
                        help='skip pointwise log-likelihood (saves GBs on large frames; '
                             'LOO comparison then unavailable for this fit)')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    module = importlib.import_module(MODELS[args.model])
    build_kwargs = {'variant': args.variant} if args.variant else {}
    frame_kwargs = {'channel': args.channel, 'csv_path': args.csv,
                    'outcome': args.outcome, **build_kwargs}
    sampler = dict(draws=args.draws, tune=args.tune, chains=args.chains,
                   target_accept=args.target_accept, seed=args.seed,
                   nuts_sampler=args.sampler, log_likelihood=not args.no_loglik)

    from core import workflow

    if args.mode == 'simulate':
        import numpy as np
        rng = np.random.default_rng(args.seed)
        frame, truth = module.simulate(rng)
        print(f'[{module.MODEL_ID}] simulated frame: {len(frame)} rows; '
              f'{module.OUTCOME} mean = {frame[module.OUTCOME].mean():.3f}')
        model = module.build(frame, **build_kwargs)
        # reduced sampling: recovery needs breadth, not precision
        idata = workflow.fit(model, f'{module.MODEL_ID}_sim', module.OUTCOME,
                             draws=min(args.draws, 500), tune=min(args.tune, 500),
                             chains=min(args.chains, 2), target_accept=args.target_accept,
                             seed=args.seed, nuts_sampler=args.sampler)
        recovered = workflow.print_recovery(workflow.parameter_recovery(idata, truth))
        return 0 if recovered else 1

    if args.mode == 'balance':
        if args.model != 'f04':
            parser.error('balance mode is f04-only')
        module.balance(module.load_frame(**frame_kwargs))
        return 0

    frame = module.load_frame(**frame_kwargs)
    print(f'[{module.MODEL_ID}] loaded frame: {len(frame)} rows')

    if args.variant == 'all' and args.mode == 'fit' and hasattr(module, 'fit_all'):
        label = args.channel if args.model == 'f01' else ''
        if args.outcome:
            label = f'{label}_{args.outcome}'.strip('_')
        module.fit_all(frame, label=label, **sampler)
        return 0

    model = module.build(frame, **build_kwargs)
    if args.mode == 'prior':
        check = workflow.prior_predictive_summary(model, module.OUTCOME, seed=args.seed)
        print(f'prior predictive {module.OUTCOME}: {check}')
        return 0

    # Variant fits get their own output directory so configurations never
    # overwrite each other (f06's pre-2026-07-16 fits share the bare dir).
    model_id = f'{module.MODEL_ID}_{args.variant}' if args.variant else module.MODEL_ID
    outcome = getattr(module, 'OUTCOME_BY_VARIANT', {}).get(args.variant, module.OUTCOME)
    extra = {'n_obs': len(frame), 'variant': args.variant,
             'scalers': getattr(module.build, 'scalers', {})}
    idata = workflow.fit(model, model_id, outcome,
                         extra_report=extra, **sampler)
    if args.model == 'f03':
        print('dose contrast:', module.dose_contrast(idata))
    if args.model == 'f04':
        print('E-values:', module.e_value_report(idata))
    if args.model == 'f06':
        print(module.odds_ratio_table(idata).to_string(index=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
