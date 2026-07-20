"""Shared fit workflow: prior predictive → NUTS → diagnostics gate →
posterior predictive → persist.

Diagnostics reuse the canonical gate in ``src.bayesian_models.validation``
(DRY — no third diagnostics path; see review doc 20260707_2325).
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import arviz as az
import numpy as np
import pymc as pm

from core.bootstrap import OUTPUT_ROOT


def noncentered_re(name: str, n_levels: int, sigma_rate: float = 2.0, dims: Optional[str] = None):
    """Non-centered varying intercepts: sigma ~ Exp(rate), offset ~ N(0,1)."""
    sigma = pm.Exponential(f'sigma_{name}', lam=sigma_rate)
    kwargs = {'dims': dims} if dims else {'shape': n_levels}
    offset = pm.Normal(f'{name}_offset', mu=0.0, sigma=1.0, **kwargs)
    return pm.Deterministic(f'a_{name}', sigma * offset, **kwargs)


def _serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def prior_predictive_summary(model: pm.Model, outcome: str, seed: int = 42) -> Dict[str, float]:
    """Draw from the prior predictive and summarize the implied outcome rate."""
    with model:
        prior = pm.sample_prior_predictive(draws=500, random_seed=seed)
    draws = prior.prior_predictive[outcome].values
    rate = draws.mean(axis=-1).flatten()
    return {'implied_rate_mean': float(rate.mean()),
            'implied_rate_p05': float(np.quantile(rate, 0.05)),
            'implied_rate_p95': float(np.quantile(rate, 0.95))}


def fit(model: pm.Model, model_id: str, outcome: str, draws: int = 2000, tune: int = 1000,
        chains: int = 4, target_accept: float = 0.9, seed: int = 42, nuts_sampler: str = 'pymc',
        log_likelihood: bool = True, extra_report: Optional[Dict[str, Any]] = None,
        out_dir: Optional[Path] = None) -> az.InferenceData:
    """Run the full workflow and persist trace + report under data/inference/fable/."""
    from src.bayesian_models.validation import check_convergence

    out_dir = Path(out_dir) if out_dir else OUTPUT_ROOT / model_id
    out_dir.mkdir(parents=True, exist_ok=True)

    prior_check = prior_predictive_summary(model, outcome, seed)
    print(f"[{model_id}] prior predictive {outcome} rate: "
          f"{prior_check['implied_rate_mean']:.3f} "
          f"({prior_check['implied_rate_p05']:.3f}–{prior_check['implied_rate_p95']:.3f})")

    with model:
        idata = pm.sample(draws=draws, tune=tune, chains=chains, target_accept=target_accept,
                          random_seed=seed, nuts_sampler=nuts_sampler,
                          # pointwise log-lik is chains*draws*n_obs floats — only
                          # store it when a LOO comparison on this frame is planned
                          idata_kwargs={'log_likelihood': log_likelihood})
        # PPC draws are chains×draws×n_obs — thin to ≤50 draws/chain so the
        # calibration check doesn't cost GBs on exposure-grain frames
        # (group-level calibration is stable with ~200 total draws)
        thin = max(1, draws // 50)
        ppc_source = idata.sel(draw=slice(None, None, thin)) if thin > 1 else idata
        ppc = pm.sample_posterior_predictive(ppc_source, random_seed=seed)
        idata.extend(ppc)

    convergence = check_convergence(idata)
    summary = az.summary(idata, hdi_prob=0.89,
                         var_names=['~_offset'], filter_vars='like')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Persist WITHOUT pointwise log-likelihood: at exposure grain it is GBs
    # per file (disk at 97%, 2026-07-16); LOO is computed in-session by
    # fit_ladder and is recoverable from posterior + model. Detach → save →
    # re-attach rather than copy (copying doubles peak RAM on a loaded box).
    loglik_group = getattr(idata, 'log_likelihood', None)
    if loglik_group is not None:
        del idata.log_likelihood
    idata.to_netcdf(out_dir / f'trace_{timestamp}.nc')
    if loglik_group is not None:
        idata.add_groups(log_likelihood=loglik_group)
    summary.to_csv(out_dir / f'summary_{timestamp}.csv')
    report = {'model_id': model_id, 'outcome': outcome, 'trained_at': timestamp,
              'prior_predictive': prior_check, 'convergence': convergence,
              'sampler': {'draws': draws, 'tune': tune, 'chains': chains,
                          'target_accept': target_accept, 'seed': seed}}
    if extra_report:
        report.update(extra_report)
    with open(out_dir / f'report_{timestamp}.json', 'w') as f:
        json.dump(_serializable(report), f, indent=2)

    print(f"[{model_id}] convergence passed={convergence.get('passed')} → {out_dir}")
    return idata


def fit_ladder(build_fn, frame, variants, model_id: str, outcome: str, **sampler) -> "az.DataFrame":
    """Fit a family of nested variants on ONE frame and compare with PSIS-LOO.

    LOO is only meaningful within a frame (same rows, same outcome), so this
    helper owns that invariant: one frame in, one comparison table out.
    Persists the comparison CSV next to the variant output directories.
    """
    import gc
    loos = {}
    for variant in variants:
        model = build_fn(frame, variant=variant)
        idata = fit(model, f'{model_id}_{variant}', outcome, **sampler)
        # Keep only the ELPDData (pointwise ELPD is n_obs floats) — holding
        # every variant's full trace+loglik OOM-killed the 2026-07-16 sweep.
        loos[variant] = az.loo(idata)
        del idata, model
        gc.collect()
    comparison = az.compare(loos, ic='loo')
    cols = ['rank', 'elpd_loo', 'se', 'elpd_diff', 'dse', 'p_loo', 'warning']
    print(f'\nPSIS-LOO comparison ({model_id}):')
    print(comparison[cols])
    out = OUTPUT_ROOT / f'{model_id}_loo_compare_{datetime.now():%Y%m%d_%H%M%S}.csv'
    comparison.to_csv(out)
    return comparison


def parameter_recovery(idata: az.InferenceData, truth: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """Compare posterior against known simulation parameters (McElreath's
    'test on data where you know the answer'). A parameter recovers if the
    truth lies inside its 89% HDI."""
    results = {}
    for name, true_value in truth.items():
        index = None
        if name.endswith(']') and '[' in name:  # vector element, e.g. 'kappa[0]'
            name, index = name[:-1].split('[')
            index = int(index)
        if name not in idata.posterior:
            continue
        samples = idata.posterior[name].values
        if index is not None:
            samples = samples[..., index]
        samples = samples.flatten()
        name = name if index is None else f'{name}[{index}]'
        hdi_lo, hdi_hi = az.hdi(samples, hdi_prob=0.89)
        results[name] = {'truth': float(true_value), 'posterior_mean': float(samples.mean()),
                         'hdi_5.5%': float(hdi_lo), 'hdi_94.5%': float(hdi_hi),
                         'recovered': bool(hdi_lo <= true_value <= hdi_hi)}
    return results


def print_recovery(results: Dict[str, Dict[str, float]]) -> bool:
    ok = True
    print(f"\n{'parameter':<22}{'truth':>9}{'post.mean':>11}{'89% HDI':>22}{'ok':>5}")
    for name, r in results.items():
        ok &= r['recovered']
        print(f"{name:<22}{r['truth']:>9.3f}{r['posterior_mean']:>11.3f}"
              f"{'[' + format(r['hdi_5.5%'], '.3f') + ', ' + format(r['hdi_94.5%'], '.3f') + ']':>22}"
              f"{'✓' if r['recovered'] else '✗':>5}")
    print(f"\nrecovery {'PASSED' if ok else 'FAILED'}")
    return ok
