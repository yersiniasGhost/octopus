"""Stage 4 — Apply click_<slug> tag matches to exposures, all 10 files.

For each file at data/campaign-updated-20260512/:
  1. Read Conversations sheet, collect contacts (by phone) and their Tags
     (reading all 3 tag columns: 'Msg Tags', 'Contact Tags', 'Tags').
  2. Find contacts where the file's own slug appears in tags (e.g.
     'click_lmss' for Text75) and that contact is NOT a tester.
  3. For each such phone, look up matching exposures in THIS file's campaign
     by `contact_snapshot.phone` (NOT participant_id — this correctly handles
     dual-phone contacts where one participant has two phone numbers).
  4. Apply per-exposure precedence (mirrors mark_clicked_from_csv_tool.py):
       received / no_engagement → promote unified_status to 'clicked',
                                  set text_engagement.{clicked, clicked_at}
       engaged                  → keep status; set text_engagement.{clicked, clicked_at}
                                  (audit trail; engaged > clicked)
       opted_out                → keep status; set text_engagement.{clicked, clicked_at}
                                  (audit trail; opted_out > clicked)
       undeliverable            → SKIP (can't click a message that wasn't delivered)
       clicked                  → idempotent no-op

  Strictly stay-in-lane: only the file's own slug is processed. Cross-file
  contamination tokens are reported but not actioned (per Decision 3).

Dry-run by default. `--apply` performs writes. Idempotent.

Usage:
    source venv/bin/activate
    python scripts/apply_text75_84_clicks_tool.py
    python scripts/apply_text75_84_clicks_tool.py --apply
    python scripts/apply_text75_84_clicks_tool.py --files text75,text83 --apply
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# Helpers
sys.path.insert(0, str(Path(__file__).parent))
from ingest_impact_cold_20260310_campaign_tool import (  # noqa: E402
    aggregate_contacts,
    normalize_phone,
    read_conversations,
)

DATA_DIR = Path('/home/yersinia/devel/octopus/data/campaign-updated-20260512')

# Full 10-file plan. campaign_id is what Stage 3 (or previous ingests) created.
FILE_PLAN = [
    {'key': 'text75', 'filename': 'EmpowerSaves_OH_Text75_Winter_Section1.xlsx',
     'campaign_id': 'text_impact_winter_75',    'slug': 'lmss'},
    {'key': 'text76', 'filename': 'EmpowerSaves_OH_Text76_Winter_Section2.xlsx',
     'campaign_id': 'text_impact_winter_76',    'slug': 'lmss'},
    {'key': 'text77', 'filename': 'EmpowerSaves_OH_Text77_WCP_Section1.xlsx',
     'campaign_id': 'text_impact_wcp_77',       'slug': 'sMcs'},
    {'key': 'text78', 'filename': 'EmpowerSaves_OH_Text78_WCP_Section2.xlsx',
     'campaign_id': 'text_impact_wcp_78',       'slug': 'lmLs'},
    {'key': 'text79', 'filename': 'EmpowerSaves_OH_Text79_Cold_Section1.xlsx',
     'campaign_id': 'text_impact_cold_79',      'slug': 'qXJi'},
    {'key': 'text80', 'filename': 'EmpowerSaves_OH_Text80_Cold_Section2.xlsx',
     'campaign_id': 'text_impact_cold_80',      'slug': 'mWaR'},
    {'key': 'text81', 'filename': 'EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx',
     'campaign_id': 'text_impact_endssoon_81',  'slug': 'iXJM'},
    {'key': 'text82', 'filename': 'EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx',
     'campaign_id': 'text_impact_endssoon_82',  'slug': 'Ytxw'},
    {'key': 'text83', 'filename': 'EmpowerSaves_OH_Text83_LastDay_Section1.xlsx',
     'campaign_id': 'text_impact_lastday_83',   'slug': 'pRJQ'},
    {'key': 'text84', 'filename': 'EmpowerSaves_OH_Text84_LastDay_Section2.xlsx',
     'campaign_id': 'text_impact_lastday_84',   'slug': 'pRJQ'},
]


def collect_click_phones(filepath: Path, slug: str) -> tuple[set, dict]:
    """Returns (clicker_phones, all_tag_summary).

    clicker_phones: set of normalized phones where contact has click_<slug>
                    in tags AND is NOT a tester.
    all_tag_summary: dict {tag: count} across all non-tester contacts —
                     for cross-contamination reporting.
    """
    rows = read_conversations(filepath)
    contacts = aggregate_contacts(rows)  # Msg Tags + Contact Tags

    # Augment with the third 'Tags' column
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

    self_token = f'click_{slug}'
    clickers = set()
    tag_summary = defaultdict(int)
    for phone, c in contacts.items():
        if c['is_tester']:
            continue
        for tag in c['all_tags']:
            if tag.startswith('click_'):
                tag_summary[tag] += 1
        if self_token in c['all_tags']:
            clickers.add(phone)
    return clickers, dict(tag_summary)


def process_file(db, plan: dict, apply_changes: bool, now: datetime) -> dict:
    filepath = DATA_DIR / plan['filename']
    out = defaultdict(int)
    out['filename'] = plan['filename']
    out['campaign_id'] = plan['campaign_id']
    out['slug'] = plan['slug']

    if not filepath.exists():
        out['error'] = 'file_missing'
        return out

    self_token = f'click_{plan["slug"]}'
    clickers, tag_summary = collect_click_phones(filepath, plan['slug'])
    out['file_clickers'] = len(clickers)
    out['file_tag_summary'] = tag_summary

    print(f'\n{"=" * 80}')
    print(f'📁 {plan["filename"]}  → {plan["campaign_id"]}  → token={self_token}')
    print('=' * 80)
    print(f'  Contacts in file with {self_token} (non-tester): {len(clickers)}')

    if not clickers:
        print('  Nothing to apply.')
        return out

    # Look up matching exposures by contact_snapshot.phone (dual-phone safe)
    exposures = list(db.exposures.find({
        'campaign_id': plan['campaign_id'],
        'contact_snapshot.phone': {'$in': list(clickers)},
    }, {
        '_id': 1, 'participant_id': 1, 'contact_snapshot.phone': 1,
        'unified_status': 1, 'text_engagement': 1,
    }))
    out['exposures_found'] = len(exposures)

    found_phones = {e['contact_snapshot']['phone'] for e in exposures if e.get('contact_snapshot')}
    phones_no_exposure = clickers - found_phones
    out['phones_without_exposure'] = len(phones_no_exposure)

    # Bucket per current status
    ops = []
    promoted = audited = skipped_undel = already = 0
    for e in exposures:
        cs = e.get('unified_status')
        te = e.get('text_engagement') or {}
        if te.get('clicked') is True and cs == 'clicked':
            already += 1
            continue
        if cs == 'undeliverable':
            skipped_undel += 1
            continue
        if cs in ('received', 'no_engagement', None, ''):
            ops.append(UpdateOne({'_id': e['_id']}, {
                '$set': {
                    'unified_status': 'clicked',
                    'text_engagement.clicked': True,
                    'text_engagement.clicked_at': now,
                },
            }))
            promoted += 1
        else:
            # engaged / opted_out → don't downgrade, just write audit trail
            ops.append(UpdateOne({'_id': e['_id']}, {
                '$set': {
                    'text_engagement.clicked': True,
                    'text_engagement.clicked_at': now,
                },
            }))
            audited += 1

    out['promoted_to_clicked'] = promoted
    out['audit_only_on_terminal'] = audited
    out['skipped_undeliverable'] = skipped_undel
    out['already_clicked_idempotent'] = already

    print(f'  Exposures found by contact_snapshot.phone: {len(exposures)} '
          f'(missing {len(phones_no_exposure)} phones)')
    print(f'    → promote received→clicked: {promoted}')
    print(f'    → audit (engaged/opted_out, no status change): {audited}')
    print(f'    → skip undeliverable: {skipped_undel}')
    print(f'    → already-clicked (idempotent): {already}')

    if phones_no_exposure and len(phones_no_exposure) <= 10:
        print(f'  Phones in file but not in DB exposures: {sorted(phones_no_exposure)}')
    elif phones_no_exposure:
        print(f'  Phones in file but not in DB exposures: {len(phones_no_exposure)} (first 5: {sorted(phones_no_exposure)[:5]})')

    if not ops:
        print('  No ops to apply.')
        return out

    if not apply_changes:
        print(f'  PLAN: bulk_write {len(ops)} updates against db.exposures')
        return out

    result = db.exposures.bulk_write(ops, ordered=False)
    out['bulk_modified'] = result.modified_count
    print(f'  ✓ bulk_write matched={result.matched_count} modified={result.modified_count}')

    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--files', type=str, default=None,
                        help='Comma-separated keys (e.g. text79,text83). Default: all 10.')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('STAGE 4 — Apply click_<slug> matches to Text75-84 exposures')
    print('=' * 80)

    plans = FILE_PLAN
    if args.files:
        wanted = {s.strip() for s in args.files.split(',')}
        plans = [p for p in plans if p['key'] in wanted]
        print(f'Filtered to {len(plans)}/{len(FILE_PLAN)} files')
    else:
        print(f'Processing all {len(plans)} files in plan')

    now = datetime.now(timezone.utc)
    results = []
    for plan in plans:
        result = process_file(db, plan, apply_changes=args.apply, now=now)
        results.append(result)

    # Summary
    print('\n' + '=' * 80)
    print(f'SUMMARY ({"DRY-RUN" if not args.apply else "APPLIED"})')
    print('=' * 80)
    print(f'{"File":<50} {"clickers":>9} {"found":>6} {"promo":>6} {"audit":>6} {"skip":>5} {"idemp":>6}')
    total = defaultdict(int)
    for r in results:
        print(f'{r["filename"][:50]:<50} '
              f'{r.get("file_clickers", 0):>9} '
              f'{r.get("exposures_found", 0):>6} '
              f'{r.get("promoted_to_clicked", 0):>6} '
              f'{r.get("audit_only_on_terminal", 0):>6} '
              f'{r.get("skipped_undeliverable", 0):>5} '
              f'{r.get("already_clicked_idempotent", 0):>6}')
        for k in ('file_clickers', 'exposures_found', 'promoted_to_clicked',
                  'audit_only_on_terminal', 'skipped_undeliverable',
                  'already_clicked_idempotent'):
            total[k] += r.get(k, 0)
    print(f'{"TOTAL":<50} {total["file_clickers"]:>9} {total["exposures_found"]:>6} '
          f'{total["promoted_to_clicked"]:>6} {total["audit_only_on_terminal"]:>6} '
          f'{total["skipped_undeliverable"]:>5} {total["already_clicked_idempotent"]:>6}')

    if not args.apply:
        print('\n📋 DRY-RUN — no changes made. Re-run with --apply.')

    client.close()


if __name__ == '__main__':
    main()
