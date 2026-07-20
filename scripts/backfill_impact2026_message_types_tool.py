#!/usr/bin/env python
"""Backfill message_types on the 12 IMPACT-2026 text campaigns (Jan-Mar 2026).

Each of the 12 campaigns reuses one of 4 message bodies that already exist,
verbatim, on coded 2025 campaigns. Codes are inherited from those twins so the
theme labels stay consistent with the original coder's conventions:

  WCP "extreme heat"      <- Text31-34 SummerCrisisProgram (2025-07-24)
  StayCool "temps rise"   <- Text19-22 StayCool            (2025-07-09)
  EndsSoon "running out"  <- Text63-68 Time_Running_Out    (2025-09-26)
  LastDay "FINAL DAY"     <- Text71-74 Final_Day           (2025-09-30)

Usage:
    source venv/bin/activate
    python scripts/backfill_impact2026_message_types_tool.py [--dry-run]
"""
import argparse
import os

from dotenv import load_dotenv
from pymongo import MongoClient

ASSIGNMENTS = {
    # WCP "extreme heat" body — twin: 62776 Text31 SummerCrisisProgram
    'bf86a179-5c5e-469f-95ec-14a679bd2434': ['urgency_deadline', 'personalized_qualified', 'relief_reassurance'],
    'afb3d74b-aaa5-4be2-9dbd-4de1b5def74d': ['urgency_deadline', 'personalized_qualified', 'relief_reassurance'],
    'text_impact_wcp_77': ['urgency_deadline', 'personalized_qualified', 'relief_reassurance'],
    'text_impact_wcp_78': ['urgency_deadline', 'personalized_qualified', 'relief_reassurance'],
    # StayCool "as temperatures rise" body — twin: 62629 Text19 StayCool
    'text_impact_winter_75': ['informational', 'motivational_struggle', 'relief_reassurance'],
    'text_impact_winter_76': ['informational', 'motivational_struggle', 'relief_reassurance'],
    'text_impact_cold_79': ['informational', 'motivational_struggle', 'relief_reassurance'],
    'text_impact_cold_80': ['informational', 'motivational_struggle', 'relief_reassurance'],
    # EndsSoon "time is running out" body — twin: 64484 Text63 Time_Running_Out
    'text_impact_endssoon_81': ['urgency_deadline', 'savings_financial', 'relief_reassurance'],
    'text_impact_endssoon_82': ['urgency_deadline', 'savings_financial', 'relief_reassurance'],
    # LastDay "FINAL DAY" body — twin: 64577 Text72 Final_Day
    'text_impact_lastday_83': ['urgency_deadline', 'relief_reassurance'],
    'text_impact_lastday_84': ['urgency_deadline', 'relief_reassurance'],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='report without writing')
    args = parser.parse_args()

    load_dotenv()
    db = MongoClient(os.environ.get('MONGODB_URI', 'mongodb://localhost:27017'))[
        os.environ.get('MONGODB_OCTOPUS', 'empower_development')]

    updated = 0
    for campaign_id, types in ASSIGNMENTS.items():
        doc = db.campaigns.find_one({'campaign_id': campaign_id}, {'name': 1, 'message_types': 1})
        if doc is None:
            print(f"MISSING: {campaign_id}")
            continue
        existing = doc.get('message_types') or []
        if existing and sorted(existing) != sorted(types):
            print(f"CONFLICT (skipped): {campaign_id} has {existing}, proposed {types}")
            continue
        action = 'would set' if args.dry_run else 'set'
        if not args.dry_run:
            db.campaigns.update_one({'campaign_id': campaign_id},
                                    {'$set': {'message_types': types}})
        updated += 1
        print(f"{action} {campaign_id} ({doc.get('name')}) -> {types}")

    print(f"\n{updated}/{len(ASSIGNMENTS)} campaigns {'would be ' if args.dry_run else ''}updated")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
