#!/usr/bin/env python
"""Export the exposure-grain application-conversion dataset (F6 frame) to CSV.

One row per deduped (participant, campaign) send with: the ``applied`` outcome
(best-confidence attributed trigger of the participant's earliest application),
channel, message-theme codes, window weather (HDD/CDD, temps, extreme hours),
communication-sequence features (prior count, receipt-lag-adjusted recency,
first/last-in-wave flags), and participant demographics including the sparse
Franklin-enrichment fields.

This is the shareable companion to the f06 Bayesian model — same assembly code
(``src/bayesian-fable/core/frames.load_application_frame``), no weather gate,
LEFT-joined demographics so coverage gaps are visible rather than filtered.

Usage:
    source venv/bin/activate
    python scripts/export_application_exposure_dataset_tool.py [--out PATH]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'src' / 'bayesian-fable'))

from core.frames import MESSAGE_TYPES, SPARSE_DEMOGRAPHICS, load_application_frame  # noqa: E402

EXPORT_COLUMNS = [
    'participant_id', 'campaign_id', 'channel', 'agency', 'sent_at', 'received_at',
    'month', 'applied', 'entry_date', 'attribution_confidence', 'attribution_method',
    'n_prior_comms', 'days_since_prev', 'is_first_comm',
    'is_first_in_wave', 'is_last_in_wave', 'in_last_week_of_wave',
    *[f'has_{mt}' for mt in MESSAGE_TYPES],
    'weather_status', 'temp_mean_f', 'hdd_base65', 'cdd_base65',
    'freezing_hours', 'hot_hours', 'county_recipient_share',
    'county', 'estimated_income', 'household_size', 'total_energy_burden',
    *SPARSE_DEMOGRAPHICS,
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = REPO_ROOT / 'exports' / (
        f"application_exposure_dataset_{datetime.now():%Y%m%d_%H%M}.csv")
    parser.add_argument('--out', default=str(default_out))
    args = parser.parse_args()

    frame = load_application_frame(require_weather=False)
    frame = frame[EXPORT_COLUMNS]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)

    events = frame[frame['applied'] == 1]
    print(f"wrote {len(frame):,} rows -> {out}")
    print(f"application events: {len(events)} "
          f"(methods: {events['attribution_method'].value_counts().to_dict()})")
    print(f"channel mix: {frame['channel'].value_counts().to_dict()}")
    print(f"weather ok: {(frame['weather_status'] == 'ok').mean():.1%}")
    for col in ['estimated_income', 'owner_age', 'presence_of_children',
                'presence_of_senior', 'number_of_adults']:
        print(f"coverage {col}: {frame[col].notna().mean():.1%}")
    print(f"events by position: first_in_wave={int(events['is_first_in_wave'].sum())}, "
          f"last_week={int(events['in_last_week_of_wave'].sum())}, "
          f"n={len(events)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
