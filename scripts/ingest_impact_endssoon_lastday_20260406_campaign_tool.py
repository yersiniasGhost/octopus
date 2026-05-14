#!/usr/bin/env python3
"""
Ingest IMPACT EndsSoon/LastDay 2026-04-06 text campaigns (Text81-84).

Reuses the conversation-format ingestion logic from
`ingest_impact_cold_20260310_campaign_tool.py` (DRY).

Reads from: data/campaign-IMPACT-20260406/*.xlsx
Writes to: empower_development campaigns, participants, exposures

Usage:
    python scripts/ingest_impact_endssoon_lastday_20260406_campaign_tool.py [--dry-run]
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient

from ingest_impact_cold_20260310_campaign_tool import (
    aggregate_contacts,
    build_campaign_doc,
    build_exposure_doc,
    build_participant_doc,
    classify_engagement,
    normalize_email,
    normalize_phone,
    parse_sent_date,
    read_conversations,
    read_stats_sheet,
)

DATA_DIR = Path('/home/yersinia/devel/octopus/data/campaign-IMPACT-20260406')
CAMPAIGN_GROUP = 'IMPACT-EndsSoon-LastDay-202604'

CAMPAIGN_CONFIG = {
    'EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx': {
        'campaign_id': 'text_impact_endssoon_81',
        'name': 'EmpowerSaves OH Text81 EndsSoon Section1 - IMPACT 2026-04',
        'description': 'EndsSoon 2026 IMPACT campaign - Section 1 (Text81)',
    },
    'EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx': {
        'campaign_id': 'text_impact_endssoon_82',
        'name': 'EmpowerSaves OH Text82 EndsSoon Section2 - IMPACT 2026-04',
        'description': 'EndsSoon 2026 IMPACT campaign - Section 2 (Text82)',
    },
    'EmpowerSaves_OH_Text83_LastDay_Section1.xlsx': {
        'campaign_id': 'text_impact_lastday_83',
        'name': 'EmpowerSaves OH Text83 LastDay Section1 - IMPACT 2026-04',
        'description': 'LastDay 2026 IMPACT campaign - Section 1 (Text83)',
    },
    'EmpowerSaves_OH_Text84_LastDay_Section2.xlsx': {
        'campaign_id': 'text_impact_lastday_84',
        'name': 'EmpowerSaves OH Text84 LastDay Section2 - IMPACT 2026-04',
        'description': 'LastDay 2026 IMPACT campaign - Section 2 (Text84)',
    },
}


def main():
    parser = argparse.ArgumentParser(description='Ingest IMPACT EndsSoon/LastDay 2026-04 campaigns')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing to database')
    args = parser.parse_args()

    print("=" * 80)
    print("IMPACT ENDSSOON/LASTDAY 2026-04 CAMPAIGN INGESTION")
    print("=" * 80)

    client = MongoClient('localhost', 27017)
    db = client['empower_development']

    print("\n📊 Building participant lookup indexes...")
    existing = list(db.participants.find({}, {'participant_id': 1, 'email': 1, 'phone': 1}))
    print(f"   Existing participants: {len(existing)}")

    phone_index, email_index = {}, {}
    for p in existing:
        pid = p['participant_id']
        if p.get('phone'):
            pn = normalize_phone(p['phone'])
            if pn:
                phone_index[pn] = pid
        if p.get('email'):
            email_index[p['email'].lower()] = pid
    print(f"   Phone index: {len(phone_index)} | Email index: {len(email_index)}")

    total_stats = {
        'campaigns_created': 0, 'participants_matched': 0,
        'participants_created': 0, 'exposures_created': 0,
        'opt_outs_flagged': 0, 'testers_skipped': 0,
    }

    for filename, config in CAMPAIGN_CONFIG.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"\n⚠️  File not found: {filepath}")
            continue

        # Pre-existing campaign check (idempotency surfacing)
        already = db.campaigns.count_documents({'campaign_id': config['campaign_id']})
        already_exposures = db.exposures.count_documents({'campaign_id': config['campaign_id']})

        print(f"\n{'=' * 80}")
        print(f"📁 Processing: {filename}")
        print(f"   Campaign ID: {config['campaign_id']}")
        if already:
            print(f"   ⚠️  Campaign already in DB ({already_exposures} existing exposures)")
        print("=" * 80)

        print("\n📊 Reading Stats sheet...")
        stats = read_stats_sheet(filepath)
        sent_at = parse_sent_date(stats)
        print(f"   Account: {stats.get('account')}")
        print(f"   Sent at: {sent_at}")
        print(f"   Platform stats: target={stats.get('target')}, sent={stats.get('sent')}, "
              f"delivered={stats.get('delivered')}, dnd={stats.get('dnd')}, "
              f"bad={stats.get('bad')}, err={stats.get('err')}")

        print("\n📥 Reading Conversations sheet...")
        rows = read_conversations(filepath)
        print(f"   Total rows: {len(rows)}")

        contacts = aggregate_contacts(rows)
        print(f"   Unique contacts: {len(contacts)}")

        engagement_dist = defaultdict(int)
        testers_skipped = 0
        for _, contact in contacts.items():
            eng = classify_engagement(contact)
            if eng is None:
                testers_skipped += 1
            else:
                engagement_dist[eng['unified_status']] += 1

        print(f"\n📋 Engagement distribution:")
        status_labels = {
            'received': 'Received (no action)',
            'undeliverable': 'Undeliverable (bad/err)',
            'opted_out': 'Opted out (STOP/dnd)',
            'negative_response': 'Replied (non-STOP)',
        }
        for status, count in sorted(engagement_dist.items(), key=lambda x: -x[1]):
            print(f"   {status_labels.get(status, status)}: {count}")
        print(f"   Testers skipped: {testers_skipped}")
        total_stats['testers_skipped'] += testers_skipped

        if args.dry_run:
            print(f"\n📋 DRY-RUN MODE - No changes will be made")
            continue

        print("\n💾 Creating campaign...")
        config['source_file'] = filename
        campaign_doc = build_campaign_doc(config, stats)
        # Override the campaign_group to this batch (build_campaign_doc bakes in the Cold group)
        campaign_doc['campaign_group'] = CAMPAIGN_GROUP

        result = db.campaigns.update_one(
            {'campaign_id': config['campaign_id']},
            {'$set': campaign_doc},
            upsert=True,
        )
        if result.upserted_id:
            total_stats['campaigns_created'] += 1
            print(f"   Created campaign: {config['campaign_id']}")
        else:
            print(f"   Updated campaign: {config['campaign_id']}")

        print("\n👥 Processing participants and exposures...")
        new_participants, exposures = [], []
        engagement_updates = defaultdict(lambda: {'exposures': 0, 'received': 0, 'engaged': 0})
        opt_out_participants = []
        campaign_stats = defaultdict(int)
        matched, created = 0, 0

        for phone, contact in contacts.items():
            engagement = classify_engagement(contact)
            if engagement is None:
                continue

            contact_data = contact['contact_data']
            if contact_data is None:
                campaign_stats['skipped_no_outbound'] += 1
                continue

            email_norm = normalize_email(contact_data.get('Email'))

            if phone in phone_index:
                participant_id = phone_index[phone]
                matched += 1
            elif email_norm and email_norm in email_index:
                participant_id = email_index[email_norm]
                matched += 1
            else:
                participant_id = phone
                new_participants.append(build_participant_doc(contact_data, phone))
                phone_index[phone] = participant_id
                if email_norm:
                    email_index[email_norm] = participant_id
                created += 1

            exposures.append(build_exposure_doc(
                contact_data, participant_id, config['campaign_id'], engagement, sent_at
            ))

            campaign_stats[engagement['unified_status']] += 1
            eng = engagement_updates[participant_id]
            eng['exposures'] += 1
            if engagement['text_delivered']:
                eng['received'] += 1
            if engagement['text_replied']:
                eng['engaged'] += 1
            if engagement['text_opted_out']:
                opt_out_participants.append(participant_id)

        print(f"   Matched existing: {matched}")
        print(f"   New participants: {created}")

        if new_participants:
            print(f"\n📝 Inserting {len(new_participants)} new participants...")
            res = db.participants.insert_many(new_participants)
            total_stats['participants_created'] += len(res.inserted_ids)

        total_stats['participants_matched'] += matched

        print(f"\n📝 Inserting {len(exposures)} exposures...")
        if exposures:
            try:
                res = db.exposures.insert_many(exposures, ordered=False)
                total_stats['exposures_created'] += len(res.inserted_ids)
                print(f"   Inserted: {len(res.inserted_ids)}")
            except Exception as e:
                if 'duplicate' in str(e).lower():
                    print(f"   Some duplicates skipped")
                else:
                    print(f"   ⚠️ Error: {e}")

        print("\n📊 Updating campaign statistics...")
        db.campaigns.update_one(
            {'campaign_id': config['campaign_id']},
            {'$set': {
                'statistics.total_sent': sum(engagement_dist.values()),
                'statistics.delivered': (campaign_stats.get('received', 0) +
                                         campaign_stats.get('negative_response', 0) +
                                         campaign_stats.get('opted_out', 0)),
                'statistics.undeliverable': campaign_stats.get('undeliverable', 0),
                'statistics.clicked': 0,
                'statistics.converted': 0,
                'statistics.negative_response': campaign_stats.get('negative_response', 0),
                'statistics.opted_out': campaign_stats.get('opted_out', 0),
            }},
        )

        print(f"\n📊 Updating {len(engagement_updates)} participant engagement summaries...")
        for participant_id, eng in engagement_updates.items():
            db.participants.update_one(
                {'participant_id': participant_id},
                {
                    '$inc': {
                        'engagement_summary.total_exposures': eng['exposures'],
                        'engagement_summary.by_channel.text.exposures': eng['exposures'],
                        'engagement_summary.by_channel.text.received': eng['received'],
                        'engagement_summary.by_channel.text.engaged': eng['engaged'],
                    },
                    '$addToSet': {'source_campaigns': config['campaign_id']},
                    '$set': {
                        'updated_at': datetime.utcnow(),
                        'data_quality.has_engagement': True,
                    },
                },
            )

        if opt_out_participants:
            print(f"\n🚫 Flagging {len(opt_out_participants)} opt-outs (do_not_contact)...")
            res = db.participants.update_many(
                {'participant_id': {'$in': opt_out_participants}},
                {'$set': {
                    'do_not_contact': True,
                    'engagement_summary.unified_status': 'opted_out',
                    'updated_at': datetime.utcnow(),
                }},
            )
            total_stats['opt_outs_flagged'] += res.modified_count

        print(f"\n✅ Completed: {config['campaign_id']}")
        print(f"   Status breakdown: {dict(campaign_stats)}")

    print("\n" + "=" * 80)
    print("📊 INGESTION SUMMARY")
    print("=" * 80)
    if args.dry_run:
        print("\n  DRY-RUN MODE - No changes were made")
    else:
        print(f"\n  Campaigns created/updated: {total_stats['campaigns_created']}")
        print(f"  Participants matched:      {total_stats['participants_matched']}")
        print(f"  Participants created:      {total_stats['participants_created']}")
        print(f"  Exposures created:         {total_stats['exposures_created']}")
        print(f"  Opt-outs flagged:          {total_stats['opt_outs_flagged']}")
        print(f"  Testers skipped:           {total_stats['testers_skipped']}")
        print("\n  Database totals:")
        print(f"    Total campaigns:    {db.campaigns.count_documents({})}")
        print(f"    Total participants: {db.participants.count_documents({})}")
        print(f"    Total exposures:    {db.exposures.count_documents({})}")

    client.close()
    print("\n✅ Done!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
