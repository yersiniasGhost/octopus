"""Stage 2 — Find and delete duplicate (campaign_id, participant_id) exposure pairs.

The compound index on `(participant_id, campaign_id)` is non-unique on
`db.exposures`, and Stage 1 investigation surfaced 3 known duplicate pairs (phone
`6145078892` in Text79, Text81, Text83). This tool scans ALL text-channel
campaigns for the same pattern — broader than just the known 3 — and for each
duplicate pair keeps the doc with the EARLIEST `created_at` and drops the rest.

Why keep earliest: vendor retries on the same outbound send produce additional
rows; the first row is the original send event. Keeping the earliest preserves
the canonical event timestamp. In practice both rows for these dups carry
identical content snapshots — the choice is largely cosmetic, but consistent.

Dry-run by default. `--apply` performs deletes. Scope defaults to ALL text-
channel campaigns; pass `--campaigns id1,id2` to limit.

Usage:
    source venv/bin/activate
    python scripts/cleanup_duplicate_text_exposures_tool.py
    python scripts/cleanup_duplicate_text_exposures_tool.py --apply
    python scripts/cleanup_duplicate_text_exposures_tool.py --campaigns text_impact_cold_79
"""

import argparse
import os
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId


def find_dup_pairs(db, campaign_filter: dict) -> list[dict]:
    """Find all (campaign_id, participant_id) duplicate exposure pairs.

    Returns list of dicts:
        {campaign_id, participant_id, docs: [<full doc dicts ordered by created_at>]}
    """
    match_stage = {'channel': 'text'}
    if campaign_filter:
        match_stage.update(campaign_filter)

    pipeline = [
        {'$match': match_stage},
        {'$group': {
            '_id': {'cid': '$campaign_id', 'pid': '$participant_id'},
            'n': {'$sum': 1},
            'doc_ids': {'$push': '$_id'},
        }},
        {'$match': {'n': {'$gt': 1}}},
        {'$sort': {'n': -1, '_id.cid': 1, '_id.pid': 1}},
    ]
    pairs = list(db.exposures.aggregate(pipeline))

    # For each duplicate group, fetch full docs to inspect created_at + snapshots
    results = []
    for grp in pairs:
        docs = list(db.exposures.find({'_id': {'$in': grp['doc_ids']}}))
        docs.sort(key=lambda d: d.get('created_at') or datetime.min)
        results.append({
            'campaign_id': grp['_id']['cid'],
            'participant_id': grp['_id']['pid'],
            'count': grp['n'],
            'docs': docs,
        })
    return results


def fmt_dt(dt):
    if dt is None:
        return 'None'
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Execute deletes. Default is dry-run.')
    parser.add_argument('--campaigns', type=str, default=None,
                        help='Comma-separated campaign_ids to limit scope. Default: all text channel.')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('STAGE 2 — Duplicate (campaign_id, participant_id) exposure cleanup')
    print('=' * 80)

    campaign_filter = {}
    if args.campaigns:
        cids = [c.strip() for c in args.campaigns.split(',') if c.strip()]
        campaign_filter = {'campaign_id': {'$in': cids}}
        print(f'\nScope: {len(cids)} campaign(s) — {cids}')
    else:
        print(f'\nScope: ALL text-channel campaigns')

    print('Scanning for duplicates...', end='', flush=True)
    pairs = find_dup_pairs(db, campaign_filter)
    print(f' done. Found {len(pairs)} duplicate (campaign_id, participant_id) groups.')

    if not pairs:
        print('\nNothing to clean up.')
        client.close()
        return

    # Per-campaign tally
    per_campaign = Counter(p['campaign_id'] for p in pairs)
    print(f'\nDuplicate groups by campaign:')
    for cid, n in sorted(per_campaign.items(), key=lambda kv: -kv[1]):
        print(f'  {cid}: {n} duplicate group(s)')

    # Detail each pair
    total_to_delete = 0
    delete_ids: list[ObjectId] = []
    print(f'\nPer-pair detail:')
    print('=' * 80)
    for p in pairs:
        kept = p['docs'][0]
        dropped = p['docs'][1:]
        total_to_delete += len(dropped)
        print(f'\n  campaign={p["campaign_id"]}  participant={p["participant_id"]}  total={p["count"]}')
        print(f'    KEEP  _id={kept["_id"]}  created_at={fmt_dt(kept.get("created_at"))} '
              f'sent_at={fmt_dt(kept.get("sent_at"))} status={kept.get("unified_status")}')
        for d in dropped:
            print(f'    DROP  _id={d["_id"]}  created_at={fmt_dt(d.get("created_at"))} '
                  f'sent_at={fmt_dt(d.get("sent_at"))} status={d.get("unified_status")}')
            delete_ids.append(d['_id'])

            # Diff hint: do the docs differ in anything meaningful besides _id/created_at?
            keep_keys = {k for k in kept.keys() if k not in ('_id', 'created_at', '_migration')}
            diffs = []
            for k in keep_keys:
                if kept.get(k) != d.get(k):
                    diffs.append(k)
            if diffs:
                print(f'      ⚠ differs from KEEP in fields: {diffs}')

    print('\n' + '=' * 80)
    print(f'Plan: delete {total_to_delete} exposures across {len(pairs)} duplicate group(s)')
    print(f'After: each (campaign_id, participant_id) pair in scope will be unique.')

    if not args.apply:
        print(f'\n📋 DRY-RUN — no deletes performed. Re-run with --apply.')
        client.close()
        return

    print(f'\n💾 Deleting {total_to_delete} duplicate exposures...')
    started = datetime.utcnow()
    result = db.exposures.delete_many({'_id': {'$in': delete_ids}})
    elapsed = (datetime.utcnow() - started).total_seconds()
    print(f'   deleted_count={result.deleted_count}  ({elapsed:.2f}s)')

    # Verify
    print(f'\nVerification — re-scanning for any remaining dups in scope...')
    remaining = find_dup_pairs(db, campaign_filter)
    print(f'  Remaining duplicate groups: {len(remaining)}  (expected 0)')

    print('\n✅ Stage 2 cleanup complete.')
    client.close()


if __name__ == '__main__':
    main()
