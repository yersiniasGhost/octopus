#!/usr/bin/env python3
"""Backfill campaign attribution for the 2026-01-23 Winter same-day conversions.

Four IMPACT participants submitted GravityForms applications on the EmpowerSaves
landing page (reduceenergyburdenohio.com) on 2026-01-23 -- the same day they
received the Winter text blast (Text75 Section1 / Text76 Section2) -- yet their
`attribution.likely_campaigns` is empty because the form carried no UTM.

This tool writes the missing CampaignLink to each application, calibrated by
evidence strength:
  - participants with a recorded Text76 *click*  -> confidence 0.95, method click_same_day_landing
  - participant with same-day Text75 *receipt*    -> confidence 0.70, method receipt_same_day_landing

Idempotent: skips an application that already carries a link for the target
campaign_id (mirrors export_campaign_color_csvs_tool.py's guard). Verifies the
campaign exists and that the application's entry_date falls on the send day
before writing.

Usage:
    source venv/bin/activate
    python scripts/attribute_winter_sameday_conversions_tool.py            # dry-run (default)
    python scripts/attribute_winter_sameday_conversions_tool.py --apply    # write
"""
import argparse
import sys
from datetime import date
from pathlib import Path

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.envvars import EnvVars

# (application_id, campaign_id slug, confidence, method, evidence note)
TARGETS = [
    ("437", "text_impact_winter_76", 0.95, "click_same_day_landing", "Wilborn - Text76 click + same-day app"),
    ("440", "text_impact_winter_76", 0.95, "click_same_day_landing", "Davis - Text76 click + same-day app"),
    ("412", "text_impact_winter_76", 0.95, "click_same_day_landing", "Messmer - Text76 click + same-day app"),
    ("408", "text_impact_winter_75", 0.70, "receipt_same_day_landing", "Toney - Text75 receipt + same-day app (no click)"),
]
SEND_DAY = date(2026, 1, 23)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()
    dry = not args.apply

    env = EnvVars()
    mongo_uri = env.get_env("MONGO_URI", "mongodb://localhost:27017")
    db_name = env.get_env("MONGODB_OCTOPUS") or "empower_development"
    db = MongoClient(mongo_uri)[db_name]

    print(f"{'DRY-RUN' if dry else 'APPLY'} - attributing {len(TARGETS)} Winter same-day conversions\n")
    updated = skipped = missing = 0

    for app_id, campaign_id, conf, method, note in TARGETS:
        app = db.applications.find_one({"application_id": app_id})
        if not app:
            print(f"  ! app {app_id}: NOT FOUND - skipping")
            missing += 1
            continue

        if not db.campaigns.find_one({"campaign_id": campaign_id}):
            print(f"  ! app {app_id}: campaign '{campaign_id}' missing - skipping")
            missing += 1
            continue

        entry = app.get("entry_date")
        entry_day = entry.date() if entry else None
        if entry_day != SEND_DAY:
            print(f"  ! app {app_id}: entry_date {entry_day} != send day {SEND_DAY} - skipping (safety)")
            missing += 1
            continue

        existing = (app.get("attribution") or {}).get("likely_campaigns") or []
        if any(lc.get("campaign_id") == campaign_id for lc in existing):
            print(f"  = app {app_id}: already linked to {campaign_id} - skipping")
            skipped += 1
            continue

        link = {"campaign_id": campaign_id, "confidence": conf, "method": method}
        print(f"  + app {app_id}: link {link}  ({note})")
        if not dry:
            db.applications.update_one(
                {"_id": app["_id"]},
                {"$push": {"attribution.likely_campaigns": link}},
            )
            updated += 1

    print(f"\nSummary: {'would update' if dry else 'updated'}={updated if not dry else len(TARGETS)-skipped-missing} "
          f"skipped(existing)={skipped} skipped(safety/missing)={missing}")
    if dry:
        print("Re-run with --apply to write.")


if __name__ == "__main__":
    main()
