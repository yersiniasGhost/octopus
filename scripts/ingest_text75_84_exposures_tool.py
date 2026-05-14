"""Stage 3 — Wipe/create/reset Text75-84 exposures from data/campaign-updated-20260512/.

Per-file decisions from Stage 1 investigation:

  - Text75/76 (Winter): WIPE the old UUID-keyed campaign docs + exposures (stale
    COLORCODED data; +110/+107 surplus), then CREATE fresh as
    text_impact_winter_75/76 from the new file.

  - Text77/78 (WCP): CREATE fresh (no prior ingest). New campaign docs
    text_impact_wcp_77/78 with full exposures.

  - Text79-82 (Cold, EndsSoon) and Text84 (LastDay S2): NO exposure changes here
    (Stage 4 will add clicks). Skipped by this tool.

  - Text83 (LastDay S1): RESET CLICKS. Downgrade all 1,134 'clicked' exposures
    back to 'received' (clearing text_engagement.clicked + clicked_at). Stage 4
    will re-mark 945 clicks from the new file (net: -189).

Conventions:
  - Each new exposure has BOTH `participant_id` (natural key) and
    `participant_oid` (surrogate FK) set at insert time. No follow-up backfill.
  - Reads ALL THREE tag columns from Conversations sheet ('Msg Tags',
    'Contact Tags', 'Tags' — the third is what the existing impact-cold helper
    missed and what carries click_<slug> tokens).
  - Does NOT write `participants.engagement_summary` (removed 2026-05-13). The
    helper at src/utils/engagement.py computes on demand.
  - Does NOT populate `text_engagement.clicked` here — Stage 4 owns that.

Dry-run by default. `--apply` performs the writes.

Usage:
    source venv/bin/activate
    python scripts/ingest_text75_84_exposures_tool.py
    python scripts/ingest_text75_84_exposures_tool.py --apply
    python scripts/ingest_text75_84_exposures_tool.py --files text75,text83 --apply
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

# Reuse stable helpers from the existing impact tool.
sys.path.insert(0, str(Path(__file__).parent))
from ingest_impact_cold_20260310_campaign_tool import (  # noqa: E402
    aggregate_contacts,
    classify_engagement,
    normalize_email,
    normalize_phone,
    parse_sent_date,
    read_conversations,
    read_stats_sheet,
    safe_str,
    safe_zip,
)

DATA_DIR = Path('/home/yersinia/devel/octopus/data/campaign-updated-20260512')

# Per-file plan. Order matches Stage 1 report.
#
# Schema:
#   key            : short flag for --files filter
#   filename       : xlsx file in DATA_DIR
#   action         : one of {'wipe', 'create', 'reset_clicks'}
#   new_id         : campaign_id to write the new doc as
#   old_id         : campaign_id to DELETE (only for 'wipe'); None otherwise
#   name           : campaign name string
#   text_num       : Text# (for source-file linkage)
#   action_num     : RumbleUp action # (for documentation; matched against Stats.action)
#   slug           : the file's own click_<slug>
#   reply_tag      : the file's own replied<N>
#   campaign_group : grouping label
FILE_PLAN = [
    {'key': 'text75', 'filename': 'EmpowerSaves_OH_Text75_Winter_Section1.xlsx',
     'action': 'wipe', 'new_id': 'text_impact_winter_75',
     'old_id': '761dc8cf-b8d6-43c4-b76e-d6d6cdc99d6e',
     'name': 'EmpowerSaves OH Text75 Winter Section1 - IMPACT 2026-01',
     'text_num': 75, 'action_num': 76, 'slug': 'lmss', 'reply_tag': 'replied76',
     'campaign_group': 'IMPACT-Winter-202601'},
    {'key': 'text76', 'filename': 'EmpowerSaves_OH_Text76_Winter_Section2.xlsx',
     'action': 'wipe', 'new_id': 'text_impact_winter_76',
     'old_id': '1fae2148-a61a-4cf7-ab16-6873db90838c',
     'name': 'EmpowerSaves OH Text76 Winter Section2 - IMPACT 2026-01',
     'text_num': 76, 'action_num': 77, 'slug': 'lmss', 'reply_tag': 'replied77',
     'campaign_group': 'IMPACT-Winter-202601'},
    {'key': 'text77', 'filename': 'EmpowerSaves_OH_Text77_WCP_Section1.xlsx',
     'action': 'create', 'new_id': 'text_impact_wcp_77', 'old_id': None,
     'name': 'EmpowerSaves OH Text77 WCP Section1 - IMPACT 2026-02',
     'text_num': 77, 'action_num': 79, 'slug': 'sMcs', 'reply_tag': 'replied79',
     'campaign_group': 'IMPACT-WCP-202602'},
    {'key': 'text78', 'filename': 'EmpowerSaves_OH_Text78_WCP_Section2.xlsx',
     'action': 'create', 'new_id': 'text_impact_wcp_78', 'old_id': None,
     'name': 'EmpowerSaves OH Text78 WCP Section2 - IMPACT 2026-02',
     'text_num': 78, 'action_num': 78, 'slug': 'lmLs', 'reply_tag': 'replied78',
     'campaign_group': 'IMPACT-WCP-202602'},
    {'key': 'text83', 'filename': 'EmpowerSaves_OH_Text83_LastDay_Section1.xlsx',
     'action': 'reset_clicks', 'new_id': 'text_impact_lastday_83', 'old_id': None,
     'name': 'EmpowerSaves OH Text83 LastDay Section1 - IMPACT 2026-04',
     'text_num': 83, 'action_num': 84, 'slug': 'pRJQ', 'reply_tag': 'replied84',
     'campaign_group': 'IMPACT-EndsSoon-LastDay-202604'},
]


# ───────────────────── Helpers ─────────────────────────


def aggregate_contacts_with_all_tags(rows: list[dict]) -> dict:
    """Like the inherited aggregate_contacts but also reads the 'Tags' column
    (the third tag-bearing field on RumbleUp Conversations sheets).
    Tester re-check uses the full tag set."""
    contacts = aggregate_contacts(rows)  # Msg Tags + Contact Tags
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
    return contacts


def build_participant_doc(contact_data: dict, phone_norm: str) -> dict:
    """Create a new Participant. NO engagement_summary (removed 2026-05-13)."""
    email = normalize_email(contact_data.get('Email'))
    return {
        'participant_id': phone_norm,
        'email': email,
        'phone': phone_norm,
        'first_name': safe_str(contact_data.get('First Name')),
        'last_name': safe_str(contact_data.get('Last Name')),
        'address': {
            'street': safe_str(contact_data.get('Street')),
            'city': safe_str(contact_data.get('City')),
            'state': safe_str(contact_data.get('State')),
            'zip': safe_zip(contact_data.get('Zipcode')),
            'county': safe_str(contact_data.get('County')),
            'raw': None,
        },
        'linkage': {
            'parcel_id': None,
            'county_key': safe_str(contact_data.get('County')),
            'method': 'rumbleup_text_import_20260512',
            'confidence': 0.0,
            'matched_at': None,
        },
        'demographics': {},
        'residence': {},
        'energy_snapshot': {},
        'do_not_contact': False,
        'data_quality': {
            'has_demographics': False,
            'has_residence': False,
            'has_energy_snapshot': False,
            'has_engagement': True,
            'completeness_score': 0.25,
            'analysis_ready': False,
        },
        'source_campaigns': [],
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }


def build_campaign_doc(plan: dict, stats: dict, sent_at: datetime) -> dict:
    return {
        'campaign_id': plan['new_id'],
        'name': plan['name'],
        'name_variants': [plan['name']],
        'agency': 'IMPACT Community Action',
        'channel': 'text',
        'campaign_type': None,
        'message_type': 'SMS',
        'target_audience': 'IMPACT',
        'campaign_group': plan['campaign_group'],
        'sent_at': sent_at,
        'source_system': 'rumbleup_xlsx_20260512',
        'source_file': plan['filename'],
        'sms_provider': 'rumbleup',
        'platform_stats': {
            'target':    stats.get('target'),
            'sent':      stats.get('sent'),
            'delivered': stats.get('delivered'),
            'dnd':       stats.get('dnd'),
            'bad':       stats.get('bad'),
            'err':       stats.get('err'),
            'replies':   stats.get('replies'),
            'cid':       stats.get('cid'),
            'action':    stats.get('action'),
            'live_time': stats.get('live_time'),
            'sent_time': stats.get('sent_time'),
        },
        'statistics': {
            'total_sent': 0, 'delivered': 0, 'undeliverable': 0,
            'clicked': 0, 'opted_out': 0, 'negative_response': 0, 'converted': 0,
        },
        'created_at': datetime.utcnow(),
        'synced_at': datetime.utcnow(),
    }


def build_exposure_doc(contact_data: dict, participant_id: str, participant_oid,
                       campaign_id: str, engagement: dict, sent_at: datetime) -> dict:
    """Build a fresh exposure. Stage 4 will set text_engagement.clicked later."""
    return {
        'participant_id':  participant_id,
        'participant_oid': participant_oid,
        'campaign_id':     campaign_id,
        'agency':  'IMPACT Community Action',
        'channel': 'text',
        'sent_at': sent_at,
        'email_engagement': {
            'opened': None, 'opened_at': None,
            'clicked': None, 'clicked_at': None,
            'bounced': None, 'complained': None, 'unsubscribed': None,
        },
        'text_engagement': {
            'delivered':  engagement['text_delivered'],
            'read':       None,
            'replied':    engagement['text_replied'],
            'opted_out':  engagement['text_opted_out'],
            'failed':     not engagement['text_delivered'] and not engagement['text_replied']
                          and not engagement['text_opted_out'] and engagement['unified_status'] == 'undeliverable',
            'clicked':    None,
            'clicked_at': None,
        },
        'postal_engagement': {'delivered': None, 'response': None},
        'unified_status': engagement['unified_status'],
        'contact_snapshot': {
            'email':   normalize_email(contact_data.get('Email')),
            'phone':   normalize_phone(contact_data.get('Phone Number')),
            'address': safe_str(contact_data.get('Street')),
            'city':    safe_str(contact_data.get('City')),
            'zip':     safe_zip(contact_data.get('Zipcode')),
        },
        'energy_at_send': {
            'kwh': None, 'monthly_cost': None, 'monthly_saving': None,
            'annual_cost': None, 'annual_savings': None, 'daily_cost': None,
        },
        'created_at': datetime.utcnow(),
    }


# ───────────────────── Per-file processors ──────────────


def process_file(db, plan: dict, indexes: dict, apply_changes: bool) -> dict:
    """Returns a stats dict summarizing ops for this file."""
    filepath = DATA_DIR / plan['filename']
    stats_out = defaultdict(int)
    stats_out['file'] = plan['filename']
    stats_out['action'] = plan['action']
    stats_out['campaign_id'] = plan['new_id']

    if not filepath.exists():
        stats_out['error'] = 'file_missing'
        print(f'  ⚠ FILE MISSING: {filepath}')
        return stats_out

    print(f'\n{"=" * 80}')
    print(f'📁 {plan["filename"]}  → {plan["action"].upper()}  → campaign_id={plan["new_id"]}')
    print('=' * 80)

    # Read source xlsx
    stats_sheet = read_stats_sheet(filepath)
    sent_at = parse_sent_date(stats_sheet)
    rows = read_conversations(filepath)
    contacts = aggregate_contacts_with_all_tags(rows)

    # Classify engagement per contact
    classified = {}
    tester_count = 0
    for phone, c in contacts.items():
        eng = classify_engagement(c)
        if eng is None:
            tester_count += 1
        else:
            classified[phone] = (c, eng)
    stats_out['testers_skipped'] = tester_count
    print(f'  source: sent_at={sent_at}  contacts={len(contacts)}  '
          f'classified={len(classified)}  testers_skipped={tester_count}')

    # ─── action: reset_clicks ───
    if plan['action'] == 'reset_clicks':
        cid = plan['new_id']
        current_clicked = db.exposures.count_documents({
            'campaign_id': cid,
            'unified_status': 'clicked',
        })
        print(f'  Currently `unified_status=clicked` in DB: {current_clicked}')
        if not apply_changes:
            print(f'  PLAN: db.exposures.update_many({{campaign_id: {cid!r}, unified_status: clicked}}, '
                  f'{{$set: {{unified_status: "received"}}, $unset: {{"text_engagement.clicked": "", "text_engagement.clicked_at": ""}}}})')
            stats_out['planned_resets'] = current_clicked
        else:
            result = db.exposures.update_many(
                {'campaign_id': cid, 'unified_status': 'clicked'},
                {'$set': {'unified_status': 'received'},
                 '$unset': {'text_engagement.clicked': '', 'text_engagement.clicked_at': ''}},
            )
            stats_out['reset_count'] = result.modified_count
            print(f'  Reset: matched={result.matched_count} modified={result.modified_count}')
        return stats_out

    # ─── action: wipe or create — both end with a fresh ingest ───
    if plan['action'] == 'wipe':
        old_id = plan['old_id']
        old_exposures = db.exposures.count_documents({'campaign_id': old_id})
        old_campaigns = db.campaigns.count_documents({'campaign_id': old_id})
        print(f'  OLD campaign_id={old_id} → exposures={old_exposures} campaigns={old_campaigns}')
        if not apply_changes:
            print(f'  PLAN: db.exposures.delete_many({{campaign_id: {old_id!r}}})  (will remove {old_exposures})')
            print(f'  PLAN: db.campaigns.delete_one({{campaign_id: {old_id!r}}})  (will remove {old_campaigns})')
            stats_out['planned_delete_exposures'] = old_exposures
            stats_out['planned_delete_campaigns'] = old_campaigns
        else:
            res_e = db.exposures.delete_many({'campaign_id': old_id})
            res_c = db.campaigns.delete_one({'campaign_id': old_id})
            stats_out['deleted_exposures'] = res_e.deleted_count
            stats_out['deleted_campaigns'] = res_c.deleted_count
            print(f'  Wiped: exposures deleted={res_e.deleted_count} campaigns deleted={res_c.deleted_count}')

    # Build new campaign + exposures + participants
    new_campaign = build_campaign_doc(plan, stats_sheet, sent_at)

    matched_email = matched_phone = created = 0
    new_participants = []
    exposures_to_insert = []
    engagement_dist = defaultdict(int)
    opt_out_pids = []

    for phone, (contact, engagement) in classified.items():
        contact_data = contact['contact_data']
        if contact_data is None:
            stats_out['skipped_no_outbound'] += 1
            continue

        email_norm = normalize_email(contact_data.get('Email'))

        # Match
        if email_norm and email_norm in indexes['email']:
            participant_id = indexes['email'][email_norm]
            participant_oid = indexes['oid'].get(participant_id)
            matched_email += 1
        elif phone in indexes['phone']:
            participant_id = indexes['phone'][phone]
            participant_oid = indexes['oid'].get(participant_id)
            matched_phone += 1
        else:
            participant_id = phone
            participant_oid = None  # will be filled after insert
            np_doc = build_participant_doc(contact_data, phone)
            new_participants.append(np_doc)
            indexes['phone'][phone] = participant_id
            if email_norm:
                indexes['email'][email_norm] = participant_id
            created += 1

        exp = build_exposure_doc(contact_data, participant_id, participant_oid,
                                  plan['new_id'], engagement, sent_at)
        exposures_to_insert.append((exp, participant_id))
        engagement_dist[engagement['unified_status']] += 1
        if engagement.get('text_opted_out'):
            opt_out_pids.append(participant_id)

    print(f'  Engagement dist: {dict(engagement_dist)}')
    print(f'  Match: email={matched_email} phone={matched_phone}  new participants={created}')
    stats_out['matched_email'] = matched_email
    stats_out['matched_phone'] = matched_phone
    stats_out['new_participants'] = created
    stats_out['exposures_to_write'] = len(exposures_to_insert)
    stats_out['opt_outs'] = len(opt_out_pids)

    if not apply_changes:
        print(f'  PLAN: db.campaigns.update_one({{campaign_id: {plan["new_id"]!r}}}, $set={{...}}, upsert=True)')
        print(f'  PLAN: db.participants.insert_many(...) for {created} new docs')
        print(f'  PLAN: db.exposures.insert_many(...) for {len(exposures_to_insert)} docs')
        if opt_out_pids:
            print(f'  PLAN: db.participants.update_many($in opt_outs, $set: do_not_contact=true) — {len(opt_out_pids)}')
        return stats_out

    # Apply: upsert campaign
    db.campaigns.update_one({'campaign_id': plan['new_id']}, {'$set': new_campaign}, upsert=True)
    print(f'  ✓ campaign upserted')

    # Apply: insert new participants and capture their _ids for participant_oid
    if new_participants:
        res = db.participants.insert_many(new_participants)
        for doc, oid in zip(new_participants, res.inserted_ids):
            indexes['oid'][doc['participant_id']] = oid
        print(f'  ✓ inserted {len(res.inserted_ids)} new participants')

    # Backfill participant_oid on queued exposures whose participant was just inserted
    final_exposures = []
    missing_oid = 0
    for exp, pid in exposures_to_insert:
        if exp['participant_oid'] is None:
            exp['participant_oid'] = indexes['oid'].get(pid)
            if exp['participant_oid'] is None:
                missing_oid += 1
        final_exposures.append(exp)
    if missing_oid:
        print(f'  ⚠ {missing_oid} exposures have no participant_oid — should be 0')

    if final_exposures:
        res = db.exposures.insert_many(final_exposures, ordered=False)
        stats_out['inserted_exposures'] = len(res.inserted_ids)
        print(f'  ✓ inserted {len(res.inserted_ids)} new exposures')

    # Update source_campaigns + do_not_contact for participants in this campaign
    touched_pids = list({pid for _, pid in exposures_to_insert})
    db.participants.update_many(
        {'participant_id': {'$in': touched_pids}},
        {'$addToSet': {'source_campaigns': plan['new_id']},
         '$set': {'updated_at': datetime.utcnow(), 'data_quality.has_engagement': True}},
    )
    if opt_out_pids:
        db.participants.update_many(
            {'participant_id': {'$in': opt_out_pids}},
            {'$set': {'do_not_contact': True, 'updated_at': datetime.utcnow()}},
        )
        print(f'  ✓ flagged {len(opt_out_pids)} opt-outs')

    # Update campaign.statistics
    db.campaigns.update_one(
        {'campaign_id': plan['new_id']},
        {'$set': {
            'statistics.total_sent': sum(engagement_dist.values()),
            'statistics.delivered': engagement_dist.get('received', 0) + engagement_dist.get('negative_response', 0) + engagement_dist.get('opted_out', 0),
            'statistics.undeliverable': engagement_dist.get('undeliverable', 0),
            'statistics.opted_out': engagement_dist.get('opted_out', 0),
            'statistics.negative_response': engagement_dist.get('negative_response', 0),
            'statistics.clicked': 0,  # Stage 4 will update
            'statistics.converted': 0,
        }},
    )

    return stats_out


# ───────────────────── main ─────────────────────────


def build_indexes(db) -> dict:
    print('📊 Building participant indexes...')
    phone_idx, email_idx, oid_idx = {}, {}, {}
    for p in db.participants.find({}, {'_id': 1, 'participant_id': 1, 'email': 1, 'phone': 1}):
        pid = p['participant_id']
        oid_idx[pid] = p['_id']
        if p.get('phone'):
            pn = normalize_phone(p['phone'])
            if pn:
                phone_idx[pn] = pid
        if p.get('email'):
            email_idx[str(p['email']).lower()] = pid
    print(f'   phone={len(phone_idx)}  email={len(email_idx)}  oid={len(oid_idx)}')
    return {'phone': phone_idx, 'email': email_idx, 'oid': oid_idx}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Execute the plan. Default is dry-run.')
    parser.add_argument('--files', type=str, default=None,
                        help='Comma-separated keys (e.g. text75,text83) to limit. Default: all 5.')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]

    print('=' * 80)
    print('STAGE 3 — Text75-84 exposure wipe/create/reset')
    print('=' * 80)

    plans = FILE_PLAN
    if args.files:
        wanted = {s.strip() for s in args.files.split(',')}
        plans = [p for p in plans if p['key'] in wanted]
        print(f'Filtered to {len(plans)}/{len(FILE_PLAN)} files: {[p["key"] for p in plans]}')
    else:
        print(f'Processing all {len(plans)} files in plan')

    indexes = build_indexes(db)

    results = []
    for plan in plans:
        result = process_file(db, plan, indexes, apply_changes=args.apply)
        results.append(result)

    # Summary
    print('\n' + '=' * 80)
    print(f'SUMMARY ({"DRY-RUN" if not args.apply else "APPLIED"})')
    print('=' * 80)
    for r in results:
        print(f'\n  {r["file"]}  action={r["action"]}  cid={r["campaign_id"]}')
        for k, v in r.items():
            if k in ('file', 'action', 'campaign_id'):
                continue
            print(f'    {k}: {v}')

    if not args.apply:
        print('\n📋 DRY-RUN — no changes made. Re-run with --apply.')

    client.close()


if __name__ == '__main__':
    main()
