"""Stage 0 — Migrate legacy off-model `text_clicked` fields into TextEngagement.

Discovered during dry-run that 17,901 docs carry top-level `text_clicked`, not
the 1,134 expected. Breakdown:

  - 1,134 docs have `text_clicked: True` (all in `text_impact_lastday_83`) —
    written by mark_clicked_from_csv_tool.py on 2026-05-05.

  - 16,767 docs have `text_clicked: False` (across Text79-84) — noise stamped
    by impact-cold/endssoon-lastday tools' TAG_ENGAGEMENT default that emits
    `text_clicked: false` at the top level for every exposure they create.

This tool migrates both groups:
  - True docs  → set `text_engagement.clicked = True`, preserve `clicked_at`,
                 then unset legacy fields.
  - False docs → just unset legacy fields (don't preserve False as noise).

OUT OF SCOPE — flagged for separate follow-up: 4,116 exposures have
`unified_status: "clicked"` WITHOUT the legacy `text_clicked` field:
  - Text75 (1,009)  → will be WIPED in Stage 3 (covered there).
  - Text76 (996)    → will be WIPED in Stage 3 (covered there).
  - WCP Text2 Section 1 (1,066)  → older Jan-2026 campaign, untouched here.
  - WCP Text2 Section 2 (1,045)  → older Jan-2026 campaign, untouched here.

The Pydantic model was updated in this same commit:
  - src/models/campaign_data.py:247  TextEngagement.clicked / clicked_at added
  - src/models/campaign_data.py:505  Exposure.compute_unified_status text branch
    rewritten with new precedence (opted_out > undeliverable > engaged
    > clicked > received > no_engagement) — matches mark_clicked_from_csv_tool.py.

Pure schema migration. No `unified_status` field is touched (the existing
"clicked" docs keep their existing status string). Idempotent — re-runs after
success move zero docs.

Usage:
    source venv/bin/activate
    python scripts/migrate_text_engagement_clicked_tool.py                # default: dry-run
    python scripts/migrate_text_engagement_clicked_tool.py --apply
"""

import argparse
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

LEGACY_FILTER_ALL = {'text_clicked': {'$exists': True}}
LEGACY_FILTER_TRUE = {'text_clicked': True}
LEGACY_FILTER_FALSE = {'text_clicked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Execute the migration. Without this flag, runs in dry-run mode.')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('STAGE 0 — MIGRATE legacy text_clicked → text_engagement.clicked')
    print('=' * 80)

    total = db.exposures.count_documents(LEGACY_FILTER_ALL)
    true_count = db.exposures.count_documents(LEGACY_FILTER_TRUE)
    false_count = db.exposures.count_documents(LEGACY_FILTER_FALSE)
    print(f'\nLegacy doc counts:')
    print(f'  Total with `text_clicked` field present: {total}')
    print(f'    text_clicked=True  (carry click data): {true_count}')
    print(f'    text_clicked=False (junk default):     {false_count}')

    if total == 0:
        print('Nothing to migrate. Idempotent re-run detected.')
        client.close()
        return

    # Out-of-scope tally (informational)
    out_of_scope = db.exposures.count_documents({
        'unified_status': 'clicked',
        'text_clicked': {'$exists': False},
    })
    print(f'\nOut-of-scope (NOT touched by this script):')
    print(f'  unified_status=clicked docs without legacy text_clicked field: {out_of_scope}')
    print(f'  (Text75/76 wiped in Stage 3; WCP Text2 Jan-2026 left for follow-up.)')

    # Spot-check samples from each group
    print('\nSample TRUE docs (pre-migration):')
    true_samples = list(db.exposures.find(LEGACY_FILTER_TRUE, {
        '_id': 1, 'campaign_id': 1, 'participant_id': 1, 'unified_status': 1,
        'text_clicked': 1, 'text_clicked_at': 1, 'text_engagement': 1,
    }).limit(2))
    for s in true_samples:
        print(f'  {s["_id"]}: campaign={s["campaign_id"]} status={s["unified_status"]} '
              f'text_clicked={s["text_clicked"]} text_clicked_at={s.get("text_clicked_at")}')
        print(f'    text_engagement (current): {s.get("text_engagement")}')

    print('\nSample FALSE docs (pre-migration):')
    false_samples = list(db.exposures.find(LEGACY_FILTER_FALSE, {
        '_id': 1, 'campaign_id': 1, 'unified_status': 1, 'text_clicked': 1,
    }).limit(2))
    for s in false_samples:
        print(f'  {s["_id"]}: campaign={s["campaign_id"]} status={s["unified_status"]} '
              f'text_clicked={s["text_clicked"]} (will just be unset)')

    # Pass A: TRUE docs — copy to nested, preserve clicked_at, then unset legacy
    pipeline_true = [
        {'$set': {
            'text_engagement.clicked': '$text_clicked',
            'text_engagement.clicked_at': '$text_clicked_at',
        }},
        {'$unset': ['text_clicked', 'text_clicked_at']},
    ]
    # Pass B: FALSE docs — just unset legacy noise
    pipeline_false = [
        {'$unset': ['text_clicked', 'text_clicked_at']},
    ]

    print('\nPlanned operations:')
    print(f'  Pass A (1,134 True docs):')
    print(f'    db.exposures.update_many({LEGACY_FILTER_TRUE!r}, <pipeline>)')
    for stage in pipeline_true:
        print(f'      {stage}')
    print(f'  Pass B (16,767 False docs):')
    print(f'    db.exposures.update_many({LEGACY_FILTER_FALSE!r}, <pipeline>)')
    for stage in pipeline_false:
        print(f'      {stage}')

    if not args.apply:
        print(f'\n📋 DRY-RUN — no changes made. Re-run with --apply.')
        client.close()
        return

    # Apply Pass A
    print(f'\n💾 Applying Pass A on {true_count} True docs...')
    started = datetime.utcnow()
    res_true = db.exposures.update_many(LEGACY_FILTER_TRUE, pipeline_true)
    elapsed_true = (datetime.utcnow() - started).total_seconds()
    print(f'   matched={res_true.matched_count} modified={res_true.modified_count} ({elapsed_true:.2f}s)')

    # Apply Pass B
    print(f'\n💾 Applying Pass B on {false_count} False docs...')
    started = datetime.utcnow()
    res_false = db.exposures.update_many(LEGACY_FILTER_FALSE, pipeline_false)
    elapsed_false = (datetime.utcnow() - started).total_seconds()
    print(f'   matched={res_false.matched_count} modified={res_false.modified_count} ({elapsed_false:.2f}s)')

    # Verify
    remaining_legacy = db.exposures.count_documents(LEGACY_FILTER_ALL)
    migrated_true = db.exposures.count_documents({'text_engagement.clicked': True})
    print(f'\nVerification:')
    print(f'  Remaining with legacy text_clicked field: {remaining_legacy}  (expected 0)')
    print(f'  Total with text_engagement.clicked=True: {migrated_true}  (expected = {true_count})')

    print('\nSample TRUE docs (post-migration):')
    for s in db.exposures.find({'_id': {'$in': [doc['_id'] for doc in true_samples]}}, {
        '_id': 1, 'unified_status': 1, 'text_clicked': 1, 'text_clicked_at': 1, 'text_engagement': 1,
    }):
        print(f'  {s["_id"]}: status={s["unified_status"]} text_clicked={s.get("text_clicked")} (absent ✓) '
              f'text_engagement.clicked={(s.get("text_engagement") or {}).get("clicked")} '
              f'text_engagement.clicked_at={(s.get("text_engagement") or {}).get("clicked_at")}')

    print('\nSample FALSE docs (post-migration):')
    for s in db.exposures.find({'_id': {'$in': [doc['_id'] for doc in false_samples]}}, {
        '_id': 1, 'text_clicked': 1, 'text_engagement.clicked': 1,
    }):
        print(f'  {s["_id"]}: text_clicked={s.get("text_clicked")} (absent ✓) '
              f'text_engagement.clicked={(s.get("text_engagement") or {}).get("clicked")} (absent ✓)')

    print('\n✅ Stage 0 migration complete.')
    client.close()


if __name__ == '__main__':
    main()
