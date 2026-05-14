"""Fix #1 — Backfill `text_engagement.clicked=true` on WCP Text2 Jan-2026 docs.

The 2,111 exposures in two WCP Text2 Section 1/2 campaigns (Jan 2026)
were flagged during the Text75-84 ingest work: they carry
`unified_status: "clicked"` but their `text_engagement.clicked` field is
absent/null. They never went through the May-2026 legacy `text_clicked: True`
phase (which was Text83-only), so the 17:52 migration that folded that legacy
field into the nested path didn't touch them. The status string was apparently
set imperatively at the original ingest time without populating the underlying
channel-specific flag.

This tool sets `text_engagement.clicked = true` on those 2,111 docs so that the
nested-field and unified-status views stay consistent. `clicked_at` is NOT
populated (we don't know the original click timestamps; better to leave the
field as-is than fabricate a value).

Affected campaigns:
  - bf86a179-5c5e-469f-95ec-14a679bd2434  (EmpowerSaves WCP Text2 Section 1, 2026-01-10)
  - afb3d74b-aaa5-4be2-9dbd-4de1b5def74d  (EmpowerSaves WCP Text2 Section 2, 2026-01-10)

Idempotent: re-runs after success match 0 docs.

Usage:
    source venv/bin/activate
    python scripts/backfill_wcp_text2_clicked_flag_tool.py
    python scripts/backfill_wcp_text2_clicked_flag_tool.py --apply
"""

import argparse
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

AFFECTED_CAMPAIGN_IDS = [
    'bf86a179-5c5e-469f-95ec-14a679bd2434',
    'afb3d74b-aaa5-4be2-9dbd-4de1b5def74d',
]

FILTER = {
    'campaign_id': {'$in': AFFECTED_CAMPAIGN_IDS},
    'unified_status': 'clicked',
    'text_engagement.clicked': {'$ne': True},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('FIX #1 — Backfill text_engagement.clicked on WCP Text2 Jan-2026')
    print('=' * 80)

    # Per-campaign counts before
    print('\nPre-state per affected campaign:')
    for cid in AFFECTED_CAMPAIGN_IDS:
        total = db.exposures.count_documents({'campaign_id': cid})
        status_clicked = db.exposures.count_documents({'campaign_id': cid, 'unified_status': 'clicked'})
        flag_true = db.exposures.count_documents({'campaign_id': cid, 'text_engagement.clicked': True})
        need_backfill = db.exposures.count_documents({
            'campaign_id': cid, 'unified_status': 'clicked',
            'text_engagement.clicked': {'$ne': True},
        })
        print(f'  {cid}: total={total}  status=clicked={status_clicked}  '
              f'flag=True={flag_true}  need_backfill={need_backfill}')

    to_update = db.exposures.count_documents(FILTER)
    print(f'\nTotal docs needing backfill: {to_update}')

    if to_update == 0:
        print('Nothing to do (idempotent re-run).')
        client.close()
        return

    # Sample a doc to confirm shape
    sample = db.exposures.find_one(FILTER)
    print(f'\nSample doc {sample["_id"]}:')
    print(f'  campaign_id={sample["campaign_id"]}')
    print(f'  unified_status={sample.get("unified_status")}')
    print(f'  text_engagement={sample.get("text_engagement")}')

    print(f'\nPlanned op:')
    print(f'  db.exposures.update_many({FILTER!r},')
    print(f'    {{"$set": {{"text_engagement.clicked": True}}}})')
    print(f'  (clicked_at intentionally NOT set — original timestamp unknown)')

    if not args.apply:
        print(f'\n📋 DRY-RUN — no changes made. Re-run with --apply to update {to_update} docs.')
        client.close()
        return

    print(f'\n💾 Applying...')
    started = datetime.utcnow()
    result = db.exposures.update_many(FILTER, {'$set': {'text_engagement.clicked': True}})
    elapsed = (datetime.utcnow() - started).total_seconds()
    print(f'   matched={result.matched_count} modified={result.modified_count} ({elapsed:.2f}s)')

    # Verify
    remaining = db.exposures.count_documents(FILTER)
    print(f'\nVerification:')
    print(f'  Remaining without flag: {remaining}  (expected 0)')
    for cid in AFFECTED_CAMPAIGN_IDS:
        status_clicked = db.exposures.count_documents({'campaign_id': cid, 'unified_status': 'clicked'})
        flag_true = db.exposures.count_documents({'campaign_id': cid, 'text_engagement.clicked': True})
        print(f'  {cid}: status=clicked={status_clicked}  flag=True={flag_true}  (should be equal)')

    print('\n✅ Fix #1 complete.')
    client.close()


if __name__ == '__main__':
    main()
