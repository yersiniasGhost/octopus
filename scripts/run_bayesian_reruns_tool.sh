#!/usr/bin/env bash
# Follow-up fits after the 2026-07-16 sweep: the steps that needed code fixes.
#   f02_summer — season-appropriate weather axis (hot_hours, not freezing)
#   f05_optout — variant-aware outcome name
#   f08_ladder — campaign-grain Binomial ladder (memory-safe LOO design)
#   f07_ladder — exposure ladder at 500 draws (pointwise loglik ~0.6 GB)
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

run f02_summer f02 fit --variant summer --sampler numpyro --no-loglik --target-accept 0.95
run f05_optout f05 fit --variant optout --sampler numpyro --no-loglik
run f08_ladder f08 fit --variant all --sampler numpyro
run f07_ladder f07 fit --variant all --sampler numpyro --draws 500

echo "[$(date +%H:%M:%S)] RERUNS COMPLETE"
