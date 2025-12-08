#!/usr/bin/env python3
"""
Ingest text campaign exposures and participants into campaign_data database.

This script:
1. Matches contacts to existing participants (by email, phone, address)
2. Creates new participants for unmatched contacts
3. Creates CampaignExposure records for each outbound message
4. Updates participant engagement summaries

Reads from: data/campaign_texting/compact/messages.csv
Writes to: campaign_data.participants, campaign_data.campaign_exposures

Usage:
    python scripts/ingest_text_exposures.py [--dry-run] [--batch-size N]
"""
import argparse
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
from collections import defaultdict
import re
import sys


# Zip code to county mapping for Ohio
ZIP_TO_COUNTY = {
    # Franklin County (Columbus area)
    '43201': 'FranklinCounty', '43202': 'FranklinCounty', '43203': 'FranklinCounty',
    '43204': 'FranklinCounty', '43205': 'FranklinCounty', '43206': 'FranklinCounty',
    '43207': 'FranklinCounty', '43209': 'FranklinCounty', '43210': 'FranklinCounty',
    '43211': 'FranklinCounty', '43212': 'FranklinCounty', '43213': 'FranklinCounty',
    '43214': 'FranklinCounty', '43215': 'FranklinCounty', '43216': 'FranklinCounty',
    '43217': 'FranklinCounty', '43218': 'FranklinCounty', '43219': 'FranklinCounty',
    '43220': 'FranklinCounty', '43221': 'FranklinCounty', '43222': 'FranklinCounty',
    '43223': 'FranklinCounty', '43224': 'FranklinCounty', '43227': 'FranklinCounty',
    '43228': 'FranklinCounty', '43229': 'FranklinCounty', '43230': 'FranklinCounty',
    '43231': 'FranklinCounty', '43232': 'FranklinCounty', '43235': 'FranklinCounty',
    '43240': 'FranklinCounty', '43251': 'FranklinCounty', '43260': 'FranklinCounty',
    '43266': 'FranklinCounty', '43268': 'FranklinCounty', '43270': 'FranklinCounty',
    '43271': 'FranklinCounty', '43272': 'FranklinCounty', '43279': 'FranklinCounty',
    '43287': 'FranklinCounty', '43291': 'FranklinCounty',
    '43123': 'FranklinCounty', '43125': 'FranklinCounty',  # Grove City, Groveport
    # Allen County (Lima area)
    '45801': 'AllenCounty', '45802': 'AllenCounty', '45804': 'AllenCounty',
    '45805': 'AllenCounty', '45806': 'AllenCounty', '45807': 'AllenCounty',
    '45887': 'AllenCounty',  # Spencerville
    # Fayette County
    '43160': 'FayetteCounty',  # Washington Court House
    # Marion County
    '43302': 'MarionCounty',  # Marion
    '43334': 'MarionCounty',  # Marengo area
    # Richland County
    '44903': 'RichlandCounty', '44904': 'RichlandCounty', '44905': 'RichlandCounty',
    '44906': 'RichlandCounty', '44907': 'RichlandCounty',
    '44875': 'RichlandCounty',  # Shelby
}


def normalize_phone(phone) -> str:
    """Normalize phone number to 10 digits"""
    if pd.isna(phone):
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def normalize_email(email) -> str:
    """Normalize email to lowercase"""
    if pd.isna(email):
        return None
    return str(email).lower().strip()


def normalize_address(street, city, zip_code) -> str:
    """Create normalized address key for matching"""
    if pd.isna(street) or pd.isna(zip_code):
        return None
    street_norm = re.sub(r'\s+', ' ', str(street).upper().strip())
    zip_norm = str(zip_code).strip()[:5]
    return f"{street_norm}|{zip_norm}"


def parse_timestamp(ts_str: str) -> datetime:
    """Parse timestamp string like '2025-05-02 17:16:42 GMT-0000'"""
    if pd.isna(ts_str):
        return None
    try:
        clean = ts_str.replace(' GMT-0000', '').replace(' GMT+0000', '')
        return datetime.strptime(clean, '%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        return None


def parse_cost(cost_str) -> float:
    """Parse cost string like '$62.28 ' to float"""
    if pd.isna(cost_str):
        return None
    try:
        cleaned = re.sub(r'[^\d.]', '', str(cost_str))
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def infer_county(zip_code: str, county_raw: str) -> str:
    """Infer county from zip code or normalize raw county"""
    # If we have county data, normalize it
    if pd.notna(county_raw) and county_raw:
        county = str(county_raw).strip()
        if not county.endswith('County'):
            county = county + 'County'
        return county.replace(' ', '')

    # Try to infer from zip code
    if pd.notna(zip_code):
        zip5 = str(zip_code).strip()[:5]
        if zip5 in ZIP_TO_COUNTY:
            return ZIP_TO_COUNTY[zip5]

    return None


def build_participant_doc(row: pd.Series, phone_norm: str) -> dict:
    """Build new Participant document from contact data"""
    county = infer_county(row.get('Zipcode'), row.get('County'))

    return {
        'participant_id': phone_norm,  # Phone as canonical ID for text-only contacts
        'email': normalize_email(row.get('Email')),
        'phone': phone_norm,
        'address': {
            'street': str(row['Street']).strip() if pd.notna(row.get('Street')) else None,
            'city': str(row['City']).strip() if pd.notna(row.get('City')) else None,
            'zip': str(row['Zipcode']).strip()[:5] if pd.notna(row.get('Zipcode')) else None,
            'county': county,
            'raw': None,
        },
        'linkage': {
            'parcel_id': str(row['Custom4']).strip() if pd.notna(row.get('Custom4')) else None,
            'county_key': county,
            'method': 'text_campaign_import',
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
            'overall_receive_rate': 0.0,
            'overall_engage_rate': 0.0,
        },
        'data_quality': {
            'has_demographics': False,
            'has_residence': False,
            'has_energy_snapshot': False,
            'has_engagement': True,
            'completeness_score': 0.25,
            'analysis_ready': False,
        },
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
        'source_campaigns': [],
    }


def build_exposure_doc(row: pd.Series, participant_id: str, campaign_id: str,
                       is_delivered: bool, replied: bool) -> dict:
    """Build CampaignExposure document"""
    return {
        'participant_id': participant_id,
        'campaign_id': campaign_id,
        'agency': 'Ohio Partners for Affordable Energy',
        'channel': 'text',
        'sent_at': parse_timestamp(row.get('Msg Time')),
        # Email fields (not applicable for text)
        'email_opened': False,
        'email_opened_at': None,
        'email_clicked': False,
        'email_clicked_at': None,
        'email_bounced': False,
        'email_complained': False,
        'email_unsubscribed': False,
        # Text engagement
        'text_delivered': is_delivered,
        'text_read': None,  # We don't have read tracking
        'text_replied': replied,
        # Postal (not applicable)
        'postal_delivered': None,
        'postal_response': None,
        # Unified status
        'unified_status': 'engaged' if replied else ('received' if is_delivered else 'no_engagement'),
        # Snapshots
        'contact_snapshot': {
            'email': normalize_email(row.get('Email')),
            'phone': normalize_phone(row.get('Phone Number')),
            'address': str(row['Street']).strip() if pd.notna(row.get('Street')) else None,
            'city': str(row['City']).strip() if pd.notna(row.get('City')) else None,
            'zip': str(row['Zipcode']).strip()[:5] if pd.notna(row.get('Zipcode')) else None,
        },
        'energy_at_send': {
            'monthly_cost': parse_cost(row.get('Custom1')),
            'monthly_saving': parse_cost(row.get('Custom2')),
            'annual_cost': parse_cost(row.get('Custom3')),
        },
        'created_at': datetime.utcnow(),
    }


def main():
    parser = argparse.ArgumentParser(description='Ingest text exposures into campaign_data')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing to database')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for database operations')
    args = parser.parse_args()

    print("=" * 80)
    print("TEXT EXPOSURE & PARTICIPANT INGESTION")
    print("=" * 80)

    # Connect to database
    client = MongoClient('localhost', 27017)
    db = client['campaign_data']

    # Build action -> campaign_id mapping
    print("\n📥 Building campaign mapping...")
    campaigns = list(db.campaigns.find({'channel': 'text'}, {'campaign_id': 1, '_action_number': 1}))
    action_to_campaign = {c['_action_number']: c['campaign_id'] for c in campaigns}
    print(f"   Found {len(action_to_campaign)} text campaigns")

    if not action_to_campaign:
        print("❌ No text campaigns found. Run ingest_text_campaigns.py first!")
        return 1

    # Load message data
    print("\n📥 Loading message data...")
    messages = pd.read_csv('/home/yersinia/devel/octopus/data/campaign_texting/compact/messages.csv')
    print(f"   Loaded {len(messages)} messages")

    # Split into outbound (sent) and inbound (replies)
    outbound = messages[messages['type'] == 'out'].copy()
    inbound = messages[messages['type'] == 'in'].copy()
    print(f"   Outbound messages: {len(outbound)}")
    print(f"   Inbound replies: {len(inbound)}")

    # Build reply index (phones that replied)
    print("\n📇 Building reply index...")
    inbound['phone_norm'] = inbound['Phone Number'].apply(normalize_phone)
    reply_phones = set(inbound['phone_norm'].dropna())
    print(f"   Phones with replies: {len(reply_phones)}")

    # Build existing participant lookup indexes
    print("\n📊 Building participant lookup indexes...")
    existing = list(db.participants.find({}, {
        'participant_id': 1, 'email': 1, 'phone': 1,
        'address.street': 1, 'address.zip': 1
    }))
    print(f"   Existing participants: {len(existing)}")

    email_index = {}
    phone_index = {}
    address_index = {}

    for p in existing:
        pid = p['participant_id']
        if p.get('email'):
            email_index[p['email'].lower()] = pid
        if p.get('phone'):
            pn = normalize_phone(p['phone'])
            if pn:
                phone_index[pn] = pid
        addr = p.get('address', {})
        if addr.get('street') and addr.get('zip'):
            ak = normalize_address(addr['street'], None, addr['zip'])
            if ak:
                address_index[ak] = pid

    print(f"   Email index: {len(email_index)} entries")
    print(f"   Phone index: {len(phone_index)} entries")
    print(f"   Address index: {len(address_index)} entries")

    # Get unique contacts from outbound messages
    print("\n🔍 Processing unique contacts...")
    outbound['phone_norm'] = outbound['Phone Number'].apply(normalize_phone)
    outbound['email_norm'] = outbound['Email'].apply(normalize_email)
    outbound['address_key'] = outbound.apply(
        lambda r: normalize_address(r.get('Street'), r.get('City'), r.get('Zipcode')), axis=1
    )

    contacts = outbound.drop_duplicates(subset=['phone_norm']).copy()
    print(f"   Unique contacts: {len(contacts)}")

    # Match contacts to participants
    print("\n🔗 Matching contacts to participants...")
    phone_to_participant = {}  # phone_norm -> participant_id
    new_participants = []

    matched_email = 0
    matched_phone = 0
    matched_address = 0
    created_new = 0

    for idx, row in contacts.iterrows():
        phone_norm = row['phone_norm']
        if not phone_norm:
            continue

        matched_pid = None

        # Try email match
        if row['email_norm'] and row['email_norm'] in email_index:
            matched_pid = email_index[row['email_norm']]
            matched_email += 1
        # Try phone match
        elif phone_norm in phone_index:
            matched_pid = phone_index[phone_norm]
            matched_phone += 1
        # Try address match
        elif row['address_key'] and row['address_key'] in address_index:
            matched_pid = address_index[row['address_key']]
            matched_address += 1
        else:
            # Create new participant
            matched_pid = phone_norm  # Use phone as participant_id
            new_participants.append(build_participant_doc(row, phone_norm))
            created_new += 1

        phone_to_participant[phone_norm] = matched_pid

    print(f"\n   Matched by email:   {matched_email}")
    print(f"   Matched by phone:   {matched_phone}")
    print(f"   Matched by address: {matched_address}")
    print(f"   New participants:   {created_new}")

    # Process exposures
    print(f"\n{'📋 DRY-RUN MODE' if args.dry_run else '💾 LIVE MODE'}")
    print("-" * 60)

    if args.dry_run:
        print(f"\n  Would create {len(new_participants)} new participants")
        print(f"  Would create {len(outbound)} campaign exposures")
        print("\n  Run without --dry-run to execute ingestion")
        client.close()
        return 0

    # Insert new participants
    print(f"\n📝 Inserting {len(new_participants)} new participants...")
    if new_participants:
        result = db.participants.insert_many(new_participants)
        print(f"   Inserted: {len(result.inserted_ids)}")

    # Create exposures
    print(f"\n📝 Creating campaign exposures...")
    exposures_created = 0
    exposures_updated = 0
    exposures_skipped = 0
    exposures_errors = 0

    # Track engagement updates per participant
    engagement_updates = defaultdict(lambda: {
        'exposures': 0, 'received': 0, 'engaged': 0,
        'campaigns': set(), 'first_date': None, 'last_date': None
    })

    batch = []
    for idx, row in outbound.iterrows():
        phone_norm = row['phone_norm']
        if not phone_norm or phone_norm not in phone_to_participant:
            exposures_skipped += 1
            continue

        action = row['Contacted in Project']
        if action not in action_to_campaign:
            exposures_skipped += 1
            continue

        participant_id = phone_to_participant[phone_norm]
        campaign_id = action_to_campaign[action]
        is_delivered = row['status'] == 'ok'
        replied = phone_norm in reply_phones

        exposure = build_exposure_doc(row, participant_id, campaign_id, is_delivered, replied)

        # Track engagement
        eng = engagement_updates[participant_id]
        eng['exposures'] += 1
        eng['campaigns'].add(campaign_id)
        if is_delivered:
            eng['received'] += 1
        if replied:
            eng['engaged'] += 1

        sent_at = exposure['sent_at']
        if sent_at:
            if eng['first_date'] is None or sent_at < eng['first_date']:
                eng['first_date'] = sent_at
            if eng['last_date'] is None or sent_at > eng['last_date']:
                eng['last_date'] = sent_at

        batch.append(exposure)

        # Batch insert
        if len(batch) >= args.batch_size:
            try:
                db.campaign_exposures.insert_many(batch, ordered=False)
                exposures_created += len(batch)
            except Exception as e:
                # Handle duplicates gracefully
                if 'duplicate' in str(e).lower():
                    exposures_updated += len(batch)
                else:
                    exposures_errors += len(batch)
                    print(f"   ⚠️ Batch error: {e}")
            batch = []

            if (exposures_created + exposures_updated) % 10000 == 0:
                print(f"   Processed {exposures_created + exposures_updated} exposures...")

    # Final batch
    if batch:
        try:
            db.campaign_exposures.insert_many(batch, ordered=False)
            exposures_created += len(batch)
        except Exception as e:
            if 'duplicate' in str(e).lower():
                exposures_updated += len(batch)
            else:
                exposures_errors += len(batch)

    print(f"\n   Exposures created: {exposures_created}")
    print(f"   Exposures skipped: {exposures_skipped}")
    print(f"   Errors: {exposures_errors}")

    # Update participant engagement summaries
    print(f"\n📊 Updating {len(engagement_updates)} participant engagement summaries...")
    updated_count = 0

    for participant_id, eng in engagement_updates.items():
        try:
            update = {
                '$inc': {
                    'engagement_summary.total_exposures': eng['exposures'],
                    'engagement_summary.by_channel.text.exposures': eng['exposures'],
                    'engagement_summary.by_channel.text.received': eng['received'],
                    'engagement_summary.by_channel.text.engaged': eng['engaged'],
                },
                '$addToSet': {
                    'source_campaigns': {'$each': list(eng['campaigns'])}
                },
                '$set': {
                    'updated_at': datetime.utcnow(),
                    'data_quality.has_engagement': True,
                }
            }

            # Update campaign count and dates
            db.participants.update_one(
                {'participant_id': participant_id},
                update
            )

            # Update unified status if engaged
            if eng['engaged'] > 0:
                db.participants.update_one(
                    {'participant_id': participant_id},
                    {'$set': {
                        'engagement_summary.ever_engaged': True,
                        'engagement_summary.unified_status': 'engaged'
                    }}
                )
            elif eng['received'] > 0:
                db.participants.update_one(
                    {'participant_id': participant_id,
                     'engagement_summary.unified_status': {'$ne': 'engaged'}},
                    {'$set': {
                        'engagement_summary.ever_received': True,
                        'engagement_summary.unified_status': 'received'
                    }}
                )

            updated_count += 1
        except Exception as e:
            print(f"   ⚠️ Error updating {participant_id}: {e}")

    print(f"   Updated: {updated_count}")

    # Final statistics
    print("\n" + "=" * 80)
    print("📊 FINAL STATISTICS")
    print("=" * 80)

    total_participants = db.participants.count_documents({})
    total_exposures = db.campaign_exposures.count_documents({})
    text_exposures = db.campaign_exposures.count_documents({'channel': 'text'})

    print(f"\n  Total participants: {total_participants}")
    print(f"  Total exposures: {total_exposures}")
    print(f"  Text exposures: {text_exposures}")

    client.close()
    print("\n✅ Done!")

    return 0


if __name__ == '__main__':
    sys.exit(main())
