# bayesian-fable — McElreath-style model series (July 2026)

Third-generation Bayesian models for this project, following the *Statistical
Rethinking* workflow: **estimand → DAG → generative simulation → statistical
model → prior predictive → fit → diagnostics → posterior predictive →
contrasts on the outcome scale**.

Design rationale, DAGs, priors, and how this differs from Gen 1
(`~/devel/empower/src/bayesian`) and Gen 2 (`src/bayesian_models/`):
[`.claude_docs/20260709_1745_bayesian_fable_model_series.md`](../../.claude_docs/20260709_1745_bayesian_fable_model_series.md).

## Models

| ID | Estimand | Frame |
|----|----------|-------|
| f01 | Campaign heterogeneity + shrinkage (pooling ladder, LOO-compared) | campaign Binomial |
| f02 | Weather → text replies, total direct effect ("send when it's cold?") | text exposures, weather-ok |
| f03 | **Flagship**: CDD × cooling-slope dose — does weather act through felt bills? | dose exposures |
| f04 | ITT: Text75–84 assignment → IMPACT approval vs EGE control | combined export CSV |
| f05 | Ordered engagement ladder (none < clicked < replied) + opt-out companion | 2026 IMPACT text cohort |
| f06 | Application hazard: channel, themes, sequence position, recency, HDD/CDD → intake-form conversion | all-channel exposures, attributed applications |

## Running

```bash
source venv/bin/activate
# GPU sampling (--sampler numpyro): the pip CUDA libs must shadow the older
# system CUDA 12.4 — otherwise jax falls back to CPU with a cuSPARSE error.
export LD_LIBRARY_PATH=$(python -c "import glob,sys;print(':'.join(sorted(set(glob.glob(sys.prefix+'/lib/python3.10/site-packages/nvidia/*/lib')))))")
python src/bayesian-fable/run_fable.py f01 simulate            # known-answer test, no DB
python src/bayesian-fable/run_fable.py f01 fit --variant all   # pooling ladder + LOO
python src/bayesian-fable/run_fable.py f02 prior               # prior predictive only
python src/bayesian-fable/run_fable.py f03 fit --variant reliable
python src/bayesian-fable/run_fable.py f04 balance --csv <combined-export.csv>
```

Every model supports `simulate` (fit on synthetic data from its own
generative story, report parameter recovery), `prior`, and `fit`. Outputs go
to `data/inference/fable/<model_id>/` (trace `.nc`, `summary_*.csv`,
`report_*.json` with convergence gate + scaler params).

## Layout

```
core/bootstrap.py   sys.path shim (folder has a hyphen → not importable as src.bayesian-fable)
core/frames.py      universal data gates (dedupe, county normalization, weather-ok,
                    estimated_income) + frame assembly
core/workflow.py    prior-pred → NUTS(log_likelihood) → convergence gate →
                    post-pred → persist; parameter-recovery reporting
models/engagement.py  shared hierarchical Bernoulli builder + generative simulator (f02/f03)
models/f0*.py         one module per estimand; protocol: MODEL_ID, OUTCOME,
                      simulate(), load_frame(), build()
```

Diagnostics reuse `src.bayesian_models.validation` (the canonical Gen-2 gate)
— no third diagnostics path.

## Data gates (enforced once, in `core/frames.py`)

1. Exposures deduped on `(participant_id, campaign_id)` (129k duplicate pairs).
2. `county_key` normalized (`FranklinCounty` → `Franklin`).
3. Weather models filter `campaigns.weather.status == 'ok'`.
4. Adjustment uses `estimated_income` (99.8% coverage), never `income_level` (13.2%).
5. Continuous predictors z-scored in-model; scaler params persisted in reports.
6. `replied` is the universal text outcome; `clicked` only inside the 2026 IMPACT cohort.

## Known input dependency

f04 requires the combined campaign-control export (Text75–84 cohort ∪ EGE
no-text control with the IMPACT approved roll-up, ~11,240 parcels, built
Jun 15 2026). It is not currently present in this repo — regenerate it or
pass any CSV with columns `texted, approved, estimated_income,
household_size, total_energy_burden, county`.
