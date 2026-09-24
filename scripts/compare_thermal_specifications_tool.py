#!/usr/bin/env python3
"""
Compare candidate thermal-load regression specifications on agreed metrics.

Read-only. Writes nothing to MongoDB; --json writes one report file.

Why this exists: the superseded code fit two separate univariate regressions of
period-total kWh against period-total heating and cooling degree-hours. Replacing
it needs evidence, not a story -- switching to a joint fit on period totals makes
the negative-heating-slope share WORSE on real data (Franklin 33.3% -> 60.4%),
because billing period length, not weather, dominates both sides of the
regression (corr(days, heating degree-hours) = +0.916, periods 29 to 641 days).

Candidate specifications
    S0  legacy      two univariate fits, period totals
    S1  joint       kWh ~ heating + cooling, period totals
    S2  joint/day   kWh/day ~ heating/day + cooling/day
    S3  joint/day*  as S2, periods outside 20-45 days discarded
    S4  joint+days  kWh ~ heating + cooling + days, period totals
    S5  seasonal    kWh ~ heating, fit only on heating-dominant periods (hl > 4*cl);
                    the cooling coefficient is fit separately on cooling-dominant
                    periods. Sidesteps the collinearity instead of modelling
                    through it -- in a winter period cooling degree-hours are
                    near zero, so there is nothing for the omitted term to bias.
    S6  seasonal*   as S5, periods outside 20-45 days discarded
    S7  joint*      as S1, periods outside 20-45 days discarded. Exists to
                    isolate the period-length filter: every specification that
                    applies it scores below chance on fuel separation, and every
                    one that does not scores above it.

S2 and S3 divide both sides by period length. That removes the period-length
confound but risks inducing spurious correlation: dividing two variables by a
shared quantity correlates them even when the underlying series are independent
(Pearson, 1897). S4 controls for period length by carrying it as its own term
instead, which is the same correction without the ratio artifact.

Metrics
    1. Fuel separation    Cuyahoga only. Parcels metered in CuyahogaGasDB are
                          gas-heated and should show a near-zero heating
                          coefficient; parcels absent from it are more likely
                          electric-heated and should show a clearly positive one.
                          Reported as the two medians and the AUC of the split.
                          External ground truth, not an assumption about signs.
    2. Out-of-sample R2   k-fold across each parcel's billing periods, median of
                          the held-out scores. Specification-agnostic.
    3. Rank stability     Fit each parcel's first and second half separately and
                          rank-correlate the heating coefficient across parcels.
                          Targeting consumes a ranking; if half the data will not
                          reproduce it, it is not worth sorting on.

Usage:
    source venv/bin/activate
    python scripts/compare_thermal_specifications_tool.py --county Cuyahoga --sample 600
    python scripts/compare_thermal_specifications_tool.py --county Franklin --sample 600 \
        --json exports/thermal_spec_comparison.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import KFold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402

from src.tools.mongo import get_empower_db  # noqa: E402

SPECS = ('S0 legacy', 'S1 joint', 'S2 joint/day', 'S3 joint/day*', 'S4 joint+days',
         'S5 seasonal', 'S6 seasonal*', 'S7 joint*')
SEASON_RATIO = 4.0   # a period is heating-dominant when hl > 4 * cl
MIN_DAYS, MAX_DAYS = 20, 45


def design(rows: List[Dict], spec: str):
    """Return (X, y) for a specification, or None if too few usable periods."""
    df = pd.DataFrame(rows)
    if spec in ('S3 joint/day*', 'S6 seasonal*', 'S7 joint*'):
        df = df[(df['days'] >= MIN_DAYS) & (df['days'] <= MAX_DAYS)]
    if 'day' in spec:
        df = df[df['days'] > 0]
    if len(df) < 4:
        return None
    if spec == 'S0 legacy':
        return df[['hl']].values, df['kwh'].values
    if spec == 'S4 joint+days':
        return df[['hl', 'cl', 'days']].values, df['kwh'].values
    if spec.startswith('S5') or spec.startswith('S6'):
        # Heating coefficient from heating-dominant periods only. Shoulder
        # periods, where both drivers are active, are excluded from both fits.
        heating = df[df['hl'] > SEASON_RATIO * df['cl']]
        if len(heating) < 4:
            return None
        return heating[['hl']].values, heating['kwh'].values
    if 'day' in spec:
        return (np.column_stack([df['hl'] / df['days'], df['cl'] / df['days']]),
                (df['kwh'] / df['days']).values)
    return df[['hl', 'cl']].values, df['kwh'].values  # S1 and S7


def heating_coefficient(rows: List[Dict], spec: str):
    d = design(rows, spec)
    if d is None:
        return None
    X, y = d
    try:
        return float(LinearRegression().fit(X, y).coef_[0])
    except Exception:
        return None


def out_of_sample_r2(rows: List[Dict], spec: str, folds: int = 4):
    d = design(rows, spec)
    if d is None:
        return None
    X, y = d
    if len(y) < folds + 1:
        return None
    scores = []
    for train, test in KFold(n_splits=folds, shuffle=True, random_state=0).split(X):
        # r2 is undefined when the held-out fold has one sample or no variance;
        # such folds are skipped rather than allowed to poison the median.
        if len(test) < 2 or np.std(y[test]) == 0:
            continue
        try:
            score = r2_score(y[test], LinearRegression().fit(X[train], y[train]).predict(X[test]))
        except Exception:
            continue
        if np.isfinite(score):
            scores.append(float(score))
    return float(np.median(scores)) if scores else None


def split_half_coefficients(rows: List[Dict], spec: str):
    """Heating coefficient from the earlier and later halves of a history."""
    ordered = sorted(rows, key=lambda r: r['date'])
    mid = len(ordered) // 2
    if mid < 4:
        return None, None
    return (heating_coefficient(ordered[:mid], spec),
            heating_coefficient(ordered[mid:], spec))


def spearman(a: List[float], b: List[float]):
    """Rank correlation without a scipy dependency."""
    if len(a) < 3:
        return None
    ra, rb = pd.Series(a).rank(), pd.Series(b).rank()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def gas_metered_parcels(db, county: str):
    """Parcel ids with real metered gas usage, or None if the county has no GasDB."""
    name = f"{county}GasDB"
    if name not in db.list_collection_names():
        return None
    return {d['parcel_id'] for d in db[name].find({'parcel_id': {'$ne': None}}, {'parcel_id': 1})}


def evaluate(county: str, sample: int, verbose: bool = False) -> Dict:
    db = get_empower_db()
    weather, provenance = calc.load_weather_for_county(county)
    parcels = calc.get_target_parcels(db, county, recompute_all=True)[:sample]
    electrical, _multi_meter, _keys = calc.get_electrical_data(db, county, parcels)
    gas = gas_metered_parcels(db, county)

    histories = {}
    for pid in parcels:
        ts = electrical.get(pid)
        if not ts:
            continue
        rows, _ = calc.calculate_thermal_loads_for_parcel(weather, ts)
        if len(rows) >= 6:
            histories[pid] = rows
    if verbose:
        print(f"  {len(histories):,} usable billing histories", flush=True)

    report = {'county': county, 'parcels': len(histories),
              'weather': provenance['weather_range'], 'specs': {}}

    for spec in SPECS:
        coefs, oos, first, second, is_gas = {}, [], [], [], []
        for pid, rows in histories.items():
            c = heating_coefficient(rows, spec)
            if c is not None:
                coefs[pid] = c
                if gas is not None:
                    is_gas.append(pid in gas)
            r = out_of_sample_r2(rows, spec)
            if r is not None:
                oos.append(r)
            a, b = split_half_coefficients(rows, spec)
            if a is not None and b is not None:
                first.append(a)
                second.append(b)

        values = list(coefs.values())
        entry = {
            'n': len(values),
            'negative_share': float(np.mean([v < 0 for v in values])) if values else None,
            'median_coefficient': float(np.median(values)) if values else None,
            'out_of_sample_r2': float(np.median(oos)) if oos else None,
            'rank_stability': spearman(first, second),
        }
        if gas is not None and len(set(is_gas)) == 2:
            vals = np.array(values)
            flags = np.array(is_gas)
            entry['gas_median'] = float(np.median(vals[flags]))
            entry['non_gas_median'] = float(np.median(vals[~flags]))
            entry['gas_n'] = int(flags.sum())
            entry['non_gas_n'] = int((~flags).sum())
            try:
                # AUC that non-gas parcels rank above gas parcels by heating coefficient
                entry['fuel_auc'] = float(roc_auc_score(~flags, vals))
            except Exception:
                entry['fuel_auc'] = None
        report['specs'][spec] = entry
    return report


def render(report: Dict) -> None:
    print(f"\n  county {report['county']}   parcels {report['parcels']:,}"
          f"   weather {report['weather']['start'][:10]} -> {report['weather']['end'][:10]}\n")
    has_fuel = any('fuel_auc' in s for s in report['specs'].values())
    head = f"  {'specification':<16}{'n':>6}{'neg share':>11}{'median coef':>13}{'oos r2':>9}{'rank stab':>11}"
    if has_fuel:
        head += f"{'gas med':>10}{'non-gas med':>13}{'fuel AUC':>10}"
    print(head)
    for spec, s in report['specs'].items():
        line = (f"  {spec:<16}{s['n']:>6,}{s['negative_share']:>10.1%}"
                f"{s['median_coefficient']:>13.4f}"
                f"{(s['out_of_sample_r2'] if s['out_of_sample_r2'] is not None else float('nan')):>9.3f}"
                f"{(s['rank_stability'] if s['rank_stability'] is not None else float('nan')):>11.3f}")
        if has_fuel and 'fuel_auc' in s:
            line += (f"{s['gas_median']:>10.4f}{s['non_gas_median']:>13.4f}"
                     f"{(s['fuel_auc'] if s['fuel_auc'] is not None else float('nan')):>10.3f}")
        print(line)
    if has_fuel:
        g = next(iter(report['specs'].values()))
        print(f"\n  fuel ground truth: {g.get('gas_n', 0):,} parcels metered in "
              f"{report['county']}GasDB, {g.get('non_gas_n', 0):,} not")
        print("  AUC 0.5 = no separation between gas- and electric-heated homes; 1.0 = perfect")
    print()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--county', default='Cuyahoga')
    p.add_argument('--sample', type=int, default=600)
    p.add_argument('--json', help='write the report to this path')
    p.add_argument('--verbose', action='store_true')
    a = p.parse_args()

    print(f"\n  Comparing thermal specifications - read-only, nothing is written\n")
    report = evaluate(a.county, a.sample, a.verbose)
    render(report)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(report, indent=2))
        print(f"  report -> {a.json}\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
