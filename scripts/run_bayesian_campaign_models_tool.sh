#!/usr/bin/env bash
# Sequential GPU sweep of all bayesian-fable campaign-model configurations
# (2026-07-16 goal: predict clicks + applications; pooled and seasonal).
# Each step logs to data/inference/fable/logs/ and failures don't stop the sweep.
cd "$(dirname "$0")/.."
source scripts/gpu_env_tool.sh
LOGDIR=data/inference/fable/logs
mkdir -p "$LOGDIR"

run() {
    local name="$1"; shift
    echo "[$(date +%H:%M:%S)] START $name"
    if python src/bayesian-fable/run_fable.py "$@" > "$LOGDIR/${name}.log" 2>&1; then
        echo "[$(date +%H:%M:%S)] OK    $name"
    else
        echo "[$(date +%H:%M:%S)] FAIL  $name (see $LOGDIR/${name}.log)"
    fi
}

# Click outcomes — pooling ladders (campaign grain, LOO within ladder)
# (completed 2026-07-16 19:30; skipped on relaunch after the F7 frame fix)
[ -d data/inference/fable/f01_campaign_pooling_text_text_clicked_partial ] || \
    run f01_text_clicked  f01 fit --variant all --channel text  --outcome text_clicked  --sampler numpyro
[ -d data/inference/fable/f01_campaign_pooling_email_email_clicked_partial ] || \
    run f01_email_clicked f01 fit --variant all --channel email --outcome email_clicked --sampler numpyro

# Text clicks, IMPACT 2026 winter cohort — predictor ladder (LOO across variants)
run f07_ladder f07 fit --variant all --sampler numpyro --draws 1000

# Email clicks, summer 2025 collection — ladder (reduced draws: 125k-row loglik),
# then a full-variant coefficient run with proper draws and no loglik
run f08_ladder f08 fit --variant all  --sampler numpyro --draws 500
run f08_full   f08 fit --variant full --sampler numpyro --draws 1500 --no-loglik

# Replied (spans seasons) — seasonal configurations + pooled refit
# (pooled Jul-9 fit failed its convergence gate; refit at higher target_accept)
run f02_summer f02 fit --variant summer --sampler numpyro --no-loglik --target-accept 0.95
run f02_winter f02 fit --variant winter --sampler numpyro --no-loglik --target-accept 0.95
run f02_pooled f02 fit                  --sampler numpyro --no-loglik --target-accept 0.95

# Applications — refit now that message_types are coded on the 12 IMPACT
# campaigns (2026-07-15 backfill), with and without campaign REs
run f06_impact2026    f06 fit --variant impact2026    --sampler numpyro --no-loglik --target-accept 0.99
run f06_impact2026_re f06 fit --variant impact2026_re --sampler numpyro --no-loglik --target-accept 0.99

# Ordered engagement ladder — Jul-9 fit used the burden-gutted 3,249-row
# frame and predates the theme backfill; refit on the full IMPACT frame
run f05_ladder f05 fit --variant ladder --sampler numpyro --no-loglik
run f05_optout f05 fit --variant optout --sampler numpyro --no-loglik

echo "[$(date +%H:%M:%S)] SWEEP COMPLETE"
