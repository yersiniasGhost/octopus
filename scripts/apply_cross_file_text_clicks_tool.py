"""Fix #4 — Apply cross-file click evidence to owning campaigns.

The Stage 4b audit identified 103 unique phone+slug pairs where one file's Tags
column attests a contact clicked a link, the owning campaign has an exposure
for that contact, but `text_engagement.clicked` was not set there. This tool
remediates those gaps by aggregating cross-file click evidence and applying it
to the owning campaigns with the same precedence as Stage 4.

This is essentially Stage 4 with the lane-discipline relaxed: the original
Decision 3 said "stay in lane" (each file only writes its own slug to its own
campaign). After the audit revealed ~0.5% data loss from that strict policy,
this tool reverses the decision for the remediation pass.

Per-doc precedence (identical to Stage 4):
  received / no_engagement → promote `unified_status` to 'clicked',
                             set text_engagement.{clicked, clicked_at}
  engaged                  → audit only: set text_engagement.{clicked, clicked_at}
  opted_out                → audit only
  undeliverable            → SKIP (can't click a message that wasn't delivered)
  clicked                  → idempotent no-op

Cross-file evidence: a (phone, slug) claim found in ANY file's Tags column
counts. Multiple sightings for the same (phone, slug) collapse to a single
update. Slug → owning campaign mapping mirrors Stage 4.

Idempotent. Dry-run by default; `--apply` to write.

Usage:
    source venv/bin/activate
    python scripts/apply_cross_file_text_clicks_tool.py
    python scripts/apply_cross_file_text_clicks_tool.py --apply
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

sys.path.insert(0, str(Path(__file__).parent))
from ingest_impact_cold_20260310_campaign_tool import (  # noqa: E402
    aggregate_contacts,
    normalize_phone,
    read_conversations,
)

DATA_DIR = Path('/home/yersinia/devel/octopus/data/campaign-updated-20260512')

# slug → owning campaign_id(s)
SLUG_OWNERS = {
    'lmss': ['text_impact_winter_75', 'text_impact_winter_76'],
    'sMcs': ['text_impact_wcp_77'],
    'lmLs': ['text_impact_wcp_78'],
    'qXJi': ['text_impact_cold_79'],
    'mWaR': ['text_impact_cold_80'],
    'iXJM': ['text_impact_endssoon_81'],
    'Ytxw': ['text_impact_endssoon_82'],
    'pRJQ': ['text_impact_lastday_83', 'text_impact_lastday_84'],
}

FILES = [
    'EmpowerSaves_OH_Text75_Winter_Section1.xlsx',
    'EmpowerSaves_OH_Text76_Winter_Section2.xlsx',
    'EmpowerSaves_OH_Text77_WCP_Section1.xlsx',
    'EmpowerSaves_OH_Text78_WCP_Section2.xlsx',
    'EmpowerSaves_OH_Text79_Cold_Section1.xlsx',
    'EmpowerSaves_OH_Text80_Cold_Section2.xlsx',
    'EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx',
    'EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx',
    'EmpowerSaves_OH_Text83_LastDay_Section1.xlsx',
    'EmpowerSaves_OH_Text84_LastDay_Section2.xlsx',
]


def gather_cross_file_evidence() -> dict:
    """Returns {slug: set(phones_who_clicked_this_slug_anywhere_non_tester)}."""
    evidence = defaultdict(set)
    for filename in FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f'  ⚠ MISSING: {filename}')
            continue
        rows = read_conversations(filepath)
        contacts = aggregate_contacts(rows)
        # Augment with 'Tags' column
        for row in rows:
            phone = normalize_phone(row.get('Phone Number'))
            if not phone or phone not in contacts:
                continue
            for tag in (row.get('Tags') or '').split(','):
                tag = tag.strip()
                if tag:
                    contacts[phone]['all_tags'].add(tag)
            if 'tester' in contacts[phone]['all_tags'] or 'test_phone' in contacts[phone]['all_tags']:
                contacts[phone]['is_tester'] = True
        # Collect by slug
        for phone, c in contacts.items():
            if c['is_tester']:
                continue
            for tag in c['all_tags']:
                if tag.startswith('click_'):
                    slug = tag.replace('click_', '')
                    evidence[slug].add(phone)
    return dict(evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('FIX #4 — Apply cross-file click evidence to owning campaigns')
    print('=' * 80)

    print('\n📥 Gathering cross-file click evidence (all 10 files, 3-column Tags)...')
    evidence = gather_cross_file_evidence()
    print(f'   Found click tokens for {len(evidence)} distinct slugs')
    for slug, phones in sorted(evidence.items(), key=lambda kv: -len(kv[1])):
        owners = SLUG_OWNERS.get(slug)
        print(f'     {slug}: {len(phones)} unique phones  → owners: {owners}')

    print('\n🔍 Identifying gaps (phones who clicked but owning exposure not flagged)...')
    now = datetime.now(timezone.utc)

    all_ops = []
    per_campaign_stats = defaultdict(lambda: defaultdict(int))

    for slug, phones in evidence.items():
        owners = SLUG_OWNERS.get(slug)
        if not owners:
            continue

        # Find exposures in owning campaign(s) for these phones that need an update
        cursor = db.exposures.find({
            'campaign_id': {'$in': owners},
            'contact_snapshot.phone': {'$in': list(phones)},
        }, {
            '_id': 1, 'campaign_id': 1, 'contact_snapshot.phone': 1,
            'unified_status': 1, 'text_engagement': 1,
        })

        for e in cursor:
            cid = e['campaign_id']
            cs = e.get('unified_status')
            te = e.get('text_engagement') or {}
            already = (te.get('clicked') is True)

            if already and cs == 'clicked':
                per_campaign_stats[cid]['already_clicked_skip'] += 1
                continue
            if cs == 'undeliverable':
                per_campaign_stats[cid]['skipped_undeliverable'] += 1
                continue

            if cs in ('received', 'no_engagement', None, ''):
                if already:
                    # Flag was set somewhere but status wasn't — promote status
                    per_campaign_stats[cid]['promoted_status_only'] += 1
                    all_ops.append(UpdateOne({'_id': e['_id']}, {
                        '$set': {'unified_status': 'clicked'}
                    }))
                else:
                    per_campaign_stats[cid]['promoted_to_clicked'] += 1
                    all_ops.append(UpdateOne({'_id': e['_id']}, {
                        '$set': {
                            'unified_status': 'clicked',
                            'text_engagement.clicked': True,
                            'text_engagement.clicked_at': now,
                        }
                    }))
            else:
                # engaged / opted_out — audit only
                if not already:
                    per_campaign_stats[cid]['audit_only'] += 1
                    all_ops.append(UpdateOne({'_id': e['_id']}, {
                        '$set': {
                            'text_engagement.clicked': True,
                            'text_engagement.clicked_at': now,
                        }
                    }))
                else:
                    per_campaign_stats[cid]['audit_already_set'] += 1

    print('\n📋 Plan per campaign:')
    total = defaultdict(int)
    for cid, stats in sorted(per_campaign_stats.items()):
        nonzero = {k: v for k, v in stats.items() if v}
        print(f'  {cid}:')
        for k, v in sorted(nonzero.items()):
            print(f'    {k}: {v}')
            total[k] += v
    print(f'\nTotal ops to apply: {len(all_ops)}')
    print(f'Aggregate counts: {dict(total)}')

    if not all_ops:
        print('\nNothing to do (idempotent).')
        client.close()
        return

    if not args.apply:
        print('\n📋 DRY-RUN — no changes made. Re-run with --apply.')
        client.close()
        return

    print(f'\n💾 Applying {len(all_ops)} bulk_write ops...')
    started = datetime.utcnow()
    result = db.exposures.bulk_write(all_ops, ordered=False)
    elapsed = (datetime.utcnow() - started).total_seconds()
    print(f'   matched={result.matched_count} modified={result.modified_count} ({elapsed:.2f}s)')

    print('\n✅ Fix #4 complete.')
    client.close()


if __name__ == '__main__':
    main()
