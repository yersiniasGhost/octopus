#!/usr/bin/env python3
"""
Ingest IMPACT Cold 2026-03 text campaign data from conversation-format Excel files.

This format differs from color-coded campaigns:
  - Excel has two sheets: 'Stats' (campaign metadata) and 'Conversations' (messages)
  - Conversations have multiple rows per contact (outbound + inbound messages)
  - Engagement is determined by message tags, not cell colors
  - Stats sheet provides pre-computed delivery metrics

Tag-Based Engagement Mapping:
  - tester/test_phone in tags → SKIP (exclude from ingestion)
  - STOP or dnd in tags → unified_status: 'opted_out'
  - 'bad' in contact tags → unified_status: 'undeliverable'
  - All outbound status != 'ok' → unified_status: 'undeliverable'
  - replied (non-STOP, non-bad) → unified_status: 'negative_response'
  - Default (sent, delivered) → unified_status: 'received'

Reads from: data/campaign-IMPACT-20260310/*.xlsx
Writes to: empower_development campaigns, participants, exposures

Usage:
    python scripts/ingest_impact_cold_20260310_campaign_tool.py [--dry-run]
"""
import argparse
import re
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import openpyxl
from pymongo import MongoClient

# Campaign configuration - keyed by Excel filename
CAMPAIGN_CONFIG = {
    'EmpowerSaves_OH_Text79_Cold_Section1.xlsx': {
        'campaign_id': 'text_impact_cold_79',
        'name': 'EmpowerSaves OH Text79 Cold Section1 - IMPACT 2026-03',
        'description': 'Cold 2026 IMPACT campaign - Section 1 (Text79)',
    },
    'EmpowerSaves_OH_Text80_Cold_Section2.xlsx': {
        'campaign_id': 'text_impact_cold_80',
        'name': 'EmpowerSaves OH Text80 Cold Section2 - IMPACT 2026-03',
        'description': 'Cold 2026 IMPACT campaign - Section 2 (Text80)',
    },
}

# Tag-based engagement mapping (replaces COLOR_MAPPING for conversation format)
TAG_ENGAGEMENT = {
    'opted_out': {
        'text_delivered': True, 'text_clicked': False, 'text_form_completed': False,
        'text_replied': True, 'text_opted_out': True, 'unified_status': 'opted_out',
    },
    'undeliverable': {
        'text_delivered': False, 'text_clicked': False, 'text_form_completed': False,
        'text_replied': False, 'text_opted_out': False, 'unified_status': 'undeliverable',
    },
    'negative_response': {
        'text_delivered': True, 'text_clicked': False, 'text_form_completed': False,
        'text_replied': True, 'text_opted_out': False, 'unified_status': 'negative_response',
    },
    'received': {
        'text_delivered': True, 'text_clicked': False, 'text_form_completed': False,
        'text_replied': False, 'text_opted_out': False, 'unified_status': 'received',
    },
}


def normalize_phone(phone) -> str:
    """Normalize phone number to 10 digits."""
    if phone is None:
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def normalize_email(email) -> str:
    """Normalize email to lowercase."""
    if email is None or str(email).strip() == '':
        return None
    return str(email).lower().strip()


def safe_str(val) -> str:
    """Convert to stripped string or None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def safe_zip(val) -> str:
    """Extract first 5 digits from zip."""
    if val is None:
        return None
    digits = re.sub(r'\D', '', str(val))
    return digits[:5] if len(digits) >= 5 else None


def read_stats_sheet(filepath: Path) -> dict:
    """Read campaign-level stats from the Stats sheet."""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb['Stats']
    headers = [cell.value for cell in ws[1]]
    values = [cell.value for cell in ws[2]]
    wb.close()
    return dict(zip(headers, values))


def read_conversations(filepath: Path) -> list[dict]:
    """Read Conversations sheet and return all rows as dicts."""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb['Conversations']
    headers = [cell.value for cell in ws[1]]

    rows = []
    for row_idx in range(2, ws.max_row + 1):
        row = {}
        for col_idx, header in enumerate(headers):
            if header:
                row[header] = ws.cell(row=row_idx, column=col_idx + 1).value
        rows.append(row)

    wb.close()
    return rows


def aggregate_contacts(rows: list[dict]) -> dict:
    """Aggregate conversation rows into per-contact records.

    Returns dict keyed by normalized phone with:
      - contact_data: first outbound row (has name, address, etc.)
      - all_tags: union of Msg Tags and Contact Tags across all rows
      - has_inbound: whether any inbound messages exist
      - outbound_statuses: list of delivery statuses for outbound messages
      - is_tester: whether contact is a tester
    """
    contacts = {}

    for row in rows:
        phone_raw = row.get('Phone Number')
        phone = normalize_phone(phone_raw)
        if not phone:
            continue

        if phone not in contacts:
            contacts[phone] = {
                'contact_data': None,
                'all_tags': set(),
                'has_inbound': False,
                'outbound_statuses': [],
                'is_tester': False,
            }

        c = contacts[phone]

        # Collect tags from both fields
        for tag_field in ('Msg Tags', 'Contact Tags'):
            for tag in (row.get(tag_field) or '').split(','):
                tag = tag.strip()
                if tag:
                    c['all_tags'].add(tag)

        if row.get('type') == 'out':
            # First outbound row has the contact data
            if c['contact_data'] is None:
                c['contact_data'] = row
            c['outbound_statuses'].append(row.get('status', ''))
        elif row.get('type') == 'in':
            c['has_inbound'] = True

        # Check tester
        if 'tester' in c['all_tags'] or 'test_phone' in c['all_tags']:
            c['is_tester'] = True

    return contacts


def classify_engagement(contact: dict) -> dict:
    """Classify contact engagement from tags and statuses.

    Priority order:
      1. tester → skip (returns None)
      2. STOP/dnd → opted_out
      3. 'bad' in tags → undeliverable
      4. All outbound undelivered → undeliverable
      5. replied (non-STOP) → negative_response
      6. Default → received
    """
    tags = contact['all_tags']

    if contact['is_tester']:
        return None

    if 'STOP' in tags or 'dnd' in tags:
        return TAG_ENGAGEMENT['opted_out']

    if 'bad' in tags:
        return TAG_ENGAGEMENT['undeliverable']

    out_statuses = contact['outbound_statuses']
    if out_statuses and all(s != 'ok' for s in out_statuses):
        return TAG_ENGAGEMENT['undeliverable']

    if contact['has_inbound']:
        return TAG_ENGAGEMENT['negative_response']

    return TAG_ENGAGEMENT['received']


def parse_sent_date(stats: dict) -> datetime:
    """Parse sent_time from Stats sheet into datetime."""
    raw = stats.get('sent_time', '')
    if not raw:
        return datetime(2026, 2, 27)
    # Format: "2026-02-27 21:37:18 GMT-0000"
    try:
        return datetime.strptime(str(raw).split(' GMT')[0], '%Y-%m-%d %H:%M:%S')
    except (ValueError, IndexError):
        return datetime(2026, 2, 27)


def build_campaign_doc(config: dict, stats: dict) -> dict:
    """Build Campaign document using config + Stats sheet metadata."""
    sent_at = parse_sent_date(stats)

    return {
        'campaign_id': config['campaign_id'],
        'name': config['name'],
        'description': config.get('description', ''),
        'agency': 'IMPACT Community Action',
        'channel': 'text',
        'target_audience': 'IMPACT',
        'campaign_group': 'IMPACT-Cold-202603',
        'message_type': 'SMS',
        'sent_at': sent_at,
        'source_system': 'conversation_import',
        'source_file': config.get('source_file', ''),
        'platform_stats': {
            'target': stats.get('target'),
            'sent': stats.get('sent'),
            'delivered': stats.get('delivered'),
            'dnd': stats.get('dnd'),
            'bad': stats.get('bad'),
            'err': stats.get('err'),
            'replies': stats.get('replies'),
        },
        'statistics': {
            'total_sent': 0,
            'delivered': 0,
            'undeliverable': 0,
            'clicked': 0,
            'converted': 0,
            'negative_response': 0,
            'opted_out': 0,
        },
        'created_at': datetime.utcnow(),
        'synced_at': datetime.utcnow(),
    }


def build_participant_doc(contact_data: dict, phone_norm: str) -> dict:
    """Build new Participant document from conversation contact data."""
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
            'county': 'FranklinCounty',
            'raw': None,
        },
        'linkage': {
            'parcel_id': None,
            'county_key': 'FranklinCounty',
            'method': 'impact_cold_import',
            'confidence': 0.0,
            'matched_at': None,
        },
        'demographics': {},
        'residence': {},
        'energy_snapshot': {},
        'engagement_summary': {
            'total_campaigns': 0,
            'total_exposures': 0,
            'by_channel': {
                'email': {'exposures': 0, 'received': 0, 'engaged': 0},
                'text': {'exposures': 0, 'received': 0, 'engaged': 0},
                'mailer': {'exposures': 0, 'received': 0, 'engaged': 0},
                'letter': {'exposures': 0, 'received': 0, 'engaged': 0},
            },
            'unified_status': 'no_engagement',
            'ever_received': False,
            'ever_engaged': False,
            'first_campaign_date': None,
            'last_campaign_date': None,
        },
        'do_not_contact': False,
        'data_quality': {
            'has_demographics': False,
            'has_residence': False,
            'has_energy_snapshot': False,
            'has_engagement': True,
            'completeness_score': 0.25,
        },
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
        'source_campaigns': [],
    }


def build_exposure_doc(contact_data: dict, participant_id: str,
                       campaign_id: str, engagement: dict, sent_at: datetime) -> dict:
    """Build Exposure document from contact data and engagement classification."""
    return {
        'participant_id': participant_id,
        'campaign_id': campaign_id,
        'agency': 'IMPACT Community Action',
        'channel': 'text',
        'sent_at': sent_at,
        # Email fields (not applicable)
        'email_opened': False,
        'email_clicked': False,
        'email_bounced': False,
        'email_complained': False,
        'email_unsubscribed': False,
        # Text engagement
        'text_delivered': engagement['text_delivered'],
        'text_clicked': engagement['text_clicked'],
        'text_form_completed': engagement['text_form_completed'],
        'text_replied': engagement['text_replied'],
        'text_opted_out': engagement['text_opted_out'],
        'text_read': None,
        # Postal (not applicable)
        'postal_delivered': None,
        'postal_response': None,
        # Unified status
        'unified_status': engagement['unified_status'],
        # Contact snapshot
        'contact_snapshot': {
            'email': normalize_email(contact_data.get('Email')),
            'phone': normalize_phone(contact_data.get('Phone Number')),
            'address': safe_str(contact_data.get('Street')),
            'city': safe_str(contact_data.get('City')),
            'zip': safe_zip(contact_data.get('Zipcode')),
        },
        # No energy data in conversation format
        'energy_at_send': {},
        'created_at': datetime.utcnow(),
    }


def main():
    parser = argparse.ArgumentParser(description='Ingest IMPACT Cold 2026-03 campaign data')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing to database')
    args = parser.parse_args()

    print("=" * 80)
    print("IMPACT COLD 2026-03 CAMPAIGN INGESTION (Conversation Format)")
    print("=" * 80)

    data_dir = Path('/home/yersinia/devel/octopus/data/campaign-IMPACT-20260310')

    # Connect to database
    client = MongoClient('localhost', 27017)
    db = client['empower_development']

    # Build existing participant lookup indexes
    print("\n📊 Building participant lookup indexes...")
    existing = list(db.participants.find({}, {
        'participant_id': 1, 'email': 1, 'phone': 1, 'linkage.parcel_id': 1
    }))
    print(f"   Existing participants: {len(existing)}")

    phone_index = {}
    email_index = {}
    parcel_index = {}

    for p in existing:
        pid = p['participant_id']
        if p.get('phone'):
            pn = normalize_phone(p['phone'])
            if pn:
                phone_index[pn] = pid
        if p.get('email'):
            email_index[p['email'].lower()] = pid
        parcel_id = p.get('linkage', {}).get('parcel_id')
        if parcel_id:
            parcel_index[parcel_id] = pid

    print(f"   Phone index: {len(phone_index)} entries")
    print(f"   Email index: {len(email_index)} entries")
    print(f"   Parcel index: {len(parcel_index)} entries")

    # Process each Excel file
    total_stats = {
        'campaigns_created': 0,
        'participants_matched': 0,
        'participants_created': 0,
        'exposures_created': 0,
        'opt_outs_flagged': 0,
        'testers_skipped': 0,
    }

    for filename, config in CAMPAIGN_CONFIG.items():
        filepath = data_dir / filename
        if not filepath.exists():
            print(f"\n⚠️  File not found: {filepath}")
            continue

        print(f"\n{'=' * 80}")
        print(f"📁 Processing: {filename}")
        print(f"   Campaign ID: {config['campaign_id']}")
        print("=" * 80)

        # Read Stats sheet for campaign metadata
        print("\n📊 Reading Stats sheet...")
        stats = read_stats_sheet(filepath)
        sent_at = parse_sent_date(stats)
        print(f"   Account: {stats.get('account')}")
        print(f"   Sent at: {sent_at}")
        print(f"   Platform stats: target={stats.get('target')}, sent={stats.get('sent')}, "
              f"delivered={stats.get('delivered')}, dnd={stats.get('dnd')}, "
              f"bad={stats.get('bad')}, err={stats.get('err')}")

        # Read and aggregate conversations
        print("\n📥 Reading Conversations sheet...")
        rows = read_conversations(filepath)
        print(f"   Total rows: {len(rows)}")

        contacts = aggregate_contacts(rows)
        print(f"   Unique contacts: {len(contacts)}")

        # Classify engagement and show distribution
        engagement_dist = defaultdict(int)
        testers_skipped = 0

        for phone, contact in contacts.items():
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
            label = status_labels.get(status, status)
            print(f"   {label}: {count}")
        print(f"   Testers skipped: {testers_skipped}")
        total_stats['testers_skipped'] += testers_skipped

        if args.dry_run:
            print(f"\n📋 DRY-RUN MODE - No changes will be made")
            continue

        # Create campaign
        print("\n💾 Creating campaign...")
        config['source_file'] = filename
        campaign_doc = build_campaign_doc(config, stats)

        result = db.campaigns.update_one(
            {'campaign_id': config['campaign_id']},
            {'$set': campaign_doc},
            upsert=True
        )
        if result.upserted_id:
            total_stats['campaigns_created'] += 1
            print(f"   Created campaign: {config['campaign_id']}")
        else:
            print(f"   Updated campaign: {config['campaign_id']}")

        # Process participants and exposures
        print("\n👥 Processing participants and exposures...")

        new_participants = []
        exposures = []
        engagement_updates = defaultdict(lambda: {
            'exposures': 0, 'received': 0, 'engaged': 0, 'clicked': 0, 'converted': 0
        })
        opt_out_participants = []
        campaign_stats = defaultdict(int)
        matched = 0
        created = 0

        for phone, contact in contacts.items():
            engagement = classify_engagement(contact)
            if engagement is None:
                continue  # Skip testers

            contact_data = contact['contact_data']
            if contact_data is None:
                campaign_stats['skipped_no_outbound'] += 1
                continue

            email_norm = normalize_email(contact_data.get('Email'))

            # Match participant (3-level cascade)
            participant_id = None

            if phone in phone_index:
                participant_id = phone_index[phone]
                matched += 1
            elif email_norm and email_norm in email_index:
                participant_id = email_index[email_norm]
                matched += 1
            else:
                # Create new participant
                participant_id = phone
                participant_doc = build_participant_doc(contact_data, phone)
                new_participants.append(participant_doc)
                phone_index[phone] = participant_id
                if email_norm:
                    email_index[email_norm] = participant_id
                created += 1

            # Build exposure
            exposure = build_exposure_doc(
                contact_data, participant_id, config['campaign_id'], engagement, sent_at
            )
            exposures.append(exposure)

            # Track stats
            status = engagement['unified_status']
            campaign_stats[status] += 1

            # Track engagement updates
            eng = engagement_updates[participant_id]
            eng['exposures'] += 1
            if engagement['text_delivered']:
                eng['received'] += 1
            if engagement['text_replied']:
                eng['engaged'] += 1

            # Track opt-outs
            if engagement['text_opted_out']:
                opt_out_participants.append(participant_id)

        print(f"   Matched existing: {matched}")
        print(f"   New participants: {created}")

        # Insert new participants
        if new_participants:
            print(f"\n📝 Inserting {len(new_participants)} new participants...")
            result = db.participants.insert_many(new_participants)
            total_stats['participants_created'] += len(result.inserted_ids)
            print(f"   Inserted: {len(result.inserted_ids)}")

        total_stats['participants_matched'] += matched

        # Insert exposures
        print(f"\n📝 Inserting {len(exposures)} exposures...")
        if exposures:
            try:
                result = db.exposures.insert_many(exposures, ordered=False)
                total_stats['exposures_created'] += len(result.inserted_ids)
                print(f"   Inserted: {len(result.inserted_ids)}")
            except Exception as e:
                if 'duplicate' in str(e).lower():
                    print(f"   Some duplicates skipped")
                else:
                    print(f"   ⚠️ Error: {e}")

        # Update campaign statistics
        print("\n📊 Updating campaign statistics...")
        db.campaigns.update_one(
            {'campaign_id': config['campaign_id']},
            {'$set': {
                'statistics.total_sent': sum(engagement_dist.values()),
                'statistics.delivered': campaign_stats.get('received', 0) +
                                        campaign_stats.get('negative_response', 0) +
                                        campaign_stats.get('opted_out', 0),
                'statistics.undeliverable': campaign_stats.get('undeliverable', 0),
                'statistics.clicked': campaign_stats.get('clicked', 0),
                'statistics.converted': campaign_stats.get('converted', 0),
                'statistics.negative_response': campaign_stats.get('negative_response', 0),
                'statistics.opted_out': campaign_stats.get('opted_out', 0),
            }}
        )

        # Update participant engagement summaries
        print(f"\n📊 Updating {len(engagement_updates)} participant engagement summaries...")
        for participant_id, eng in engagement_updates.items():
            update = {
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
                }
            }
            db.participants.update_one({'participant_id': participant_id}, update)

        # Flag opt-outs globally
        if opt_out_participants:
            print(f"\n🚫 Flagging {len(opt_out_participants)} opt-outs (do_not_contact)...")
            result = db.participants.update_many(
                {'participant_id': {'$in': opt_out_participants}},
                {'$set': {
                    'do_not_contact': True,
                    'engagement_summary.unified_status': 'opted_out',
                    'updated_at': datetime.utcnow(),
                }}
            )
            total_stats['opt_outs_flagged'] += result.modified_count
            print(f"   Flagged: {result.modified_count}")

        print(f"\n✅ Completed: {config['campaign_id']}")
        print(f"   Status breakdown: {dict(campaign_stats)}")

    # Final summary
    print("\n" + "=" * 80)
    print("📊 INGESTION SUMMARY")
    print("=" * 80)

    if args.dry_run:
        print("\n  DRY-RUN MODE - No changes were made")
        print("  Run without --dry-run to execute ingestion")
    else:
        print(f"\n  Campaigns created:     {total_stats['campaigns_created']}")
        print(f"  Participants matched:  {total_stats['participants_matched']}")
        print(f"  Participants created:  {total_stats['participants_created']}")
        print(f"  Exposures created:     {total_stats['exposures_created']}")
        print(f"  Opt-outs flagged:      {total_stats['opt_outs_flagged']}")
        print(f"  Testers skipped:       {total_stats['testers_skipped']}")

        # Verify totals
        print("\n  Database totals:")
        print(f"    Total campaigns:    {db.campaigns.count_documents({})}")
        print(f"    Total participants: {db.participants.count_documents({})}")
        print(f"    Total exposures:    {db.exposures.count_documents({})}")

    client.close()
    print("\n✅ Done!")

    return 0


if __name__ == '__main__':
    sys.exit(main())
