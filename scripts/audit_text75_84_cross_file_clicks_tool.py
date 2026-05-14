"""Stage 4b — Cross-file click coverage audit (read-only, no writes).

Per Decision 3 ("stay in lane + verify other slugs properly ingested"), this
tool scans every file's Conversations Tags column for click_<slug> tokens
belonging to OTHER campaigns and verifies the owning campaign has at least
that many `text_engagement.clicked=true` exposures.

Report-only — never modifies the DB. If discrepancies surface, the user decides
case by case whether to investigate further.

For each (file, observed_slug) pair where observed_slug is NOT the file's own
slug:
  1. List the phones in this file's Tags column carrying click_<observed_slug>
  2. Owning campaign(s) for observed_slug: look up by slug → campaign_id mapping
  3. For each owning campaign: count how many of those phones have
     text_engagement.clicked=true in that campaign's exposures
  4. Report:
       - "covered": phones that ARE recorded as having clicked the owning campaign
       - "missing": phones in this file's Tags but NOT recorded in owning campaign
       - "not in owning campaign": phones not in owning campaign at all (probably
         expected — different audience between campaigns)

Usage:
    source venv/bin/activate
    python scripts/audit_text75_84_cross_file_clicks_tool.py
    python scripts/audit_text75_84_cross_file_clicks_tool.py --verbose-missing
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).parent))
from ingest_impact_cold_20260310_campaign_tool import (  # noqa: E402
    aggregate_contacts,
    normalize_phone,
    read_conversations,
)

DATA_DIR = Path('/home/yersinia/devel/octopus/data/campaign-updated-20260512')

# slug → list of owning campaign_ids (Text75/76 share lmss; Text83/84 share pRJQ)
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

FILE_PLAN = [
    ('text75', 'EmpowerSaves_OH_Text75_Winter_Section1.xlsx',    'lmss'),
    ('text76', 'EmpowerSaves_OH_Text76_Winter_Section2.xlsx',    'lmss'),
    ('text77', 'EmpowerSaves_OH_Text77_WCP_Section1.xlsx',       'sMcs'),
    ('text78', 'EmpowerSaves_OH_Text78_WCP_Section2.xlsx',       'lmLs'),
    ('text79', 'EmpowerSaves_OH_Text79_Cold_Section1.xlsx',      'qXJi'),
    ('text80', 'EmpowerSaves_OH_Text80_Cold_Section2.xlsx',      'mWaR'),
    ('text81', 'EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx',  'iXJM'),
    ('text82', 'EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx',  'Ytxw'),
    ('text83', 'EmpowerSaves_OH_Text83_LastDay_Section1.xlsx',   'pRJQ'),
    ('text84', 'EmpowerSaves_OH_Text84_LastDay_Section2.xlsx',   'pRJQ'),
]


def collect_phones_per_click_token(filepath: Path) -> dict:
    """Returns dict {click_<slug>: set(normalized_phones)} for non-testers."""
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

    result = defaultdict(set)
    for phone, c in contacts.items():
        if c['is_tester']:
            continue
        for tag in c['all_tags']:
            if tag.startswith('click_'):
                result[tag].add(phone)
    return dict(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbose-missing', action='store_true',
                        help='Print all missing phones; default prints first 5.')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('STAGE 4b — Cross-file click coverage audit (read-only)')
    print('=' * 80)

    discrepancies = []  # list of {file, slug, owning, missing_phones}
    total_file_sightings = 0
    total_cross_file_sightings = 0

    for key, filename, own_slug in FILE_PLAN:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f'\n⚠ MISSING: {filename}')
            continue
        per_token = collect_phones_per_click_token(filepath)
        own_token = f'click_{own_slug}'

        print(f'\n=== {filename} (own slug = {own_slug}) ===')
        print(f'  Own clicks ({own_token}): {len(per_token.get(own_token, set()))}')

        for tag, phones in sorted(per_token.items(), key=lambda kv: -len(kv[1])):
            total_file_sightings += len(phones)
            if tag == own_token:
                continue  # already handled in Stage 4
            other_slug = tag.replace('click_', '')
            owners = SLUG_OWNERS.get(other_slug)
            if not owners:
                print(f'  ⚠ {tag}: {len(phones)} sightings — slug NOT in our 10-file set')
                continue
            total_cross_file_sightings += len(phones)

            # Coverage check: of these phones, how many have
            # text_engagement.clicked=true in any owning campaign?
            covered = db.exposures.count_documents({
                'campaign_id': {'$in': owners},
                'contact_snapshot.phone': {'$in': list(phones)},
                'text_engagement.clicked': True,
            })
            # Phones not in owning campaign at all (likely different audience)
            present_phones = set()
            for e in db.exposures.find({
                'campaign_id': {'$in': owners},
                'contact_snapshot.phone': {'$in': list(phones)},
            }, {'contact_snapshot.phone': 1, 'text_engagement.clicked': 1}):
                p = (e.get('contact_snapshot') or {}).get('phone')
                if p:
                    present_phones.add(p)
            absent_from_owning = phones - present_phones

            # Missing = present in owning campaign but NOT marked as clicked
            unclicked_in_owning = []
            if present_phones - phones != phones:  # cheap check
                # Build set of clicked-phones in owning campaign for these contacts
                clicked_phones_in_owning = set()
                for e in db.exposures.find({
                    'campaign_id': {'$in': owners},
                    'contact_snapshot.phone': {'$in': list(phones)},
                    'text_engagement.clicked': True,
                }, {'contact_snapshot.phone': 1}):
                    p = (e.get('contact_snapshot') or {}).get('phone')
                    if p:
                        clicked_phones_in_owning.add(p)
                # Of phones present in owning campaign, which are NOT clicked there?
                present_in_owning = phones - absent_from_owning
                unclicked_in_owning = sorted(present_in_owning - clicked_phones_in_owning)

            status_emoji = '✅' if not unclicked_in_owning else '⚠ '
            print(f'  {status_emoji} {tag}: {len(phones)} sightings  → owners: {owners}')
            print(f'      covered in owning campaign(s): {covered}')
            print(f'      absent from owning campaign(s) (different audience): {len(absent_from_owning)}')
            print(f'      present in owning campaign but UNCLICKED there: {len(unclicked_in_owning)}')
            if unclicked_in_owning:
                limit = None if args.verbose_missing else 5
                shown = unclicked_in_owning[:limit] if limit else unclicked_in_owning
                print(f'        examples: {shown}{"..." if limit and len(unclicked_in_owning) > limit else ""}')
                discrepancies.append({
                    'file': filename,
                    'tag': tag,
                    'owners': owners,
                    'unclicked_phones': unclicked_in_owning,
                })

    # Summary
    print('\n' + '=' * 80)
    print('AUDIT SUMMARY')
    print('=' * 80)
    print(f'  Total click token sightings (across all files):       {total_file_sightings}')
    print(f'  Total cross-file sightings (excluding own-slug):      {total_cross_file_sightings}')
    print(f'  Discrepancy groups (cross-file claims not recorded): {len(discrepancies)}')
    if discrepancies:
        total_missing = sum(len(d['unclicked_phones']) for d in discrepancies)
        print(f'  Total unique unclicked-in-owning phones flagged:     {total_missing}')
        print('\n  Per Decision 3: report only — no auto-fix. Review the above to decide')
        print('  whether each discrepancy warrants manual investigation.')
    else:
        print('\n  ✅ No discrepancies — every cross-file click token is corroborated')
        print('     by the owning campaign\'s recorded clicks.')

    client.close()


if __name__ == '__main__':
    main()
