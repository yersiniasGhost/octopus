#!/usr/bin/env python3
"""Correct the placeholder sent_at on the dm_impact_* direct-mail campaigns.

The four `dm_impact_*` letter campaigns were ingested from rumbleup audience
CSVs (DM-sample_250_*.csv) that carried no send date, so `sent_at` defaulted to
the ingestion timestamp 2026-05-14 (identical to created_at). The real drop was
~March 2026: every UTM-mail conversion attributable to these campaigns landed
2026-03-13 -> 03-31, which is impossible for a 2026-05-14 mailing.

This tool repoints `sent_at` (on the 4 campaigns AND their 1,000 letter
exposures) to the true/estimated drop date, while preserving provenance:
  - original placeholder kept in `sent_at_ingest`
  - `sent_at_estimated` flag + `sent_at_source` note when the date is inferred

Default date is INFERRED as the earliest attributable conversion date (a
"delivered no later than" floor) and is flagged estimated. Pass the real drop
date with --date YYYY-MM-DD (clears the estimated flag) once known.

Usage:
    source venv/bin/activate
    python scripts/fix_dm_campaign_sent_date_tool.py                     # dry-run, inferred date
    python scripts/fix_dm_campaign_sent_date_tool.py --date 2026-03-10   # dry-run, known date
    python scripts/fix_dm_campaign_sent_date_tool.py --date 2026-03-10 --apply
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.attribute_click_conversions_tool import get_db

DM_CAMPAIGNS = ["dm_impact_clickers_new", "dm_impact_clickers_old",
                "dm_impact_non_clickers_new", "dm_impact_non_clickers_old"]


def infer_drop_date(db):
    """Earliest entry_date among applications attributed to a dm_impact_* campaign,
    else earliest mail-UTM application. Returns (datetime, source_str)."""
    dates = []
    for a in db.applications.find(
        {"attribution.likely_campaigns.campaign_id": {"$in": DM_CAMPAIGNS}},
        {"entry_date": 1},
    ):
        if a.get("entry_date"):
            dates.append(a["entry_date"])
    src = "earliest dm_impact-attributed conversion"
    if not dates:
        for a in db.applications.find(
            {"attribution.utm.utm_source": "mail"}, {"entry_date": 1}):
            if a.get("entry_date"):
                dates.append(a["entry_date"])
        src = "earliest utm_source=mail conversion"
    if not dates:
        return None, "no signal"
    d = min(dates)
    return datetime(d.year, d.month, d.day), src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--date", help="known drop date YYYY-MM-DD (omit to infer + flag estimated)")
    args = ap.parse_args()
    dry = not args.apply
    db = get_db()

    if args.date:
        new_dt = datetime.strptime(args.date, "%Y-%m-%d")
        estimated, source = False, "provided via --date"
    else:
        new_dt, source = infer_drop_date(db)
        estimated = True
        if new_dt is None:
            print("Could not infer a drop date (no attributed conversions). Pass --date.")
            return

    print(f"{'DRY-RUN' if dry else 'APPLY'} | new sent_at = {new_dt.date()} "
          f"({'ESTIMATED — ' + source if estimated else source})\n")

    camp_set = {"sent_at": new_dt, "sent_at_estimated": estimated, "sent_at_source": source}
    total_exp = 0
    for cid in DM_CAMPAIGNS:
        c = db.campaigns.find_one({"campaign_id": cid}, {"sent_at": 1})
        if not c:
            print(f"  ! {cid}: campaign missing, skipping")
            continue
        n_exp = db.exposures.count_documents({"campaign_id": cid})
        total_exp += n_exp
        print(f"  {cid:30} sent_at {str(c.get('sent_at'))[:10]} -> {new_dt.date()}  ({n_exp} exposures)")
        if not dry:
            db.campaigns.update_one(
                {"campaign_id": cid},
                {"$set": camp_set, "$setOnInsert": {}},
            )
            # preserve original placeholder once
            db.campaigns.update_one(
                {"campaign_id": cid, "sent_at_ingest": {"$exists": False}},
                [{"$set": {"sent_at_ingest": c.get("sent_at")}}],
            )
            db.exposures.update_many(
                {"campaign_id": cid},
                [{"$set": {"sent_at_ingest": {"$ifNull": ["$sent_at_ingest", "$sent_at"]},
                          "sent_at": new_dt, "sent_at_estimated": estimated}}],
            )

    print(f"\n{'DRY-RUN: would update' if dry else 'APPLIED:'} 4 campaigns + {total_exp} exposures.")
    if dry:
        print("Re-run with --apply (and --date once the real drop date is confirmed).")


if __name__ == "__main__":
    main()
