#!/usr/bin/env python3
"""
Dry-run script to analyze participant matching for text campaign ingestion.

This script:
1. Loads unique contacts from text campaign data
2. Attempts to match against existing participants in campaign_data database
3. Reports match rates by method (email, phone, address)
4. Identifies new participants that need to be created
5. Analyzes county distribution for residential/demographic data lookup

Usage:
    python scripts/dryrun_text_participant_matching.py
"""
import pandas as pd
from pymongo import MongoClient
from collections import defaultdict
import re


def normalize_phone(phone: str) -> str:
    """Normalize phone number to 10 digits"""
    if pd.isna(phone):
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def normalize_email(email: str) -> str:
    """Normalize email to lowercase"""
    if pd.isna(email):
        return None
    return str(email).lower().strip()


def normalize_address(street: str, city: str, zip_code: str) -> str:
    """Create normalized address key for matching"""
    if pd.isna(street) or pd.isna(zip_code):
        return None
    street_norm = re.sub(r'\s+', ' ', str(street).upper().strip())
    zip_norm = str(zip_code).strip()[:5]
    return f"{street_norm}|{zip_norm}"


def main():
    print("=" * 80)
    print("TEXT CAMPAIGN PARTICIPANT MATCHING DRY-RUN")
    print("=" * 80)

    # Connect to campaign_data database
    client = MongoClient('localhost', 27017)
    db = client['campaign_data']

    # Load text campaign data
    print("\n📥 Loading text campaign data...")
    messages = pd.read_csv('/home/yersinia/devel/octopus/data/campaign_texting/compact/messages.csv')

    # Get unique contacts (by phone number)
    contacts = messages.drop_duplicates(subset=['Phone Number']).copy()
    print(f"   Total unique contacts in text campaigns: {len(contacts)}")

    # Normalize contact data
    contacts['phone_norm'] = contacts['Phone Number'].apply(normalize_phone)
    contacts['email_norm'] = contacts['Email'].apply(normalize_email)
    contacts['address_key'] = contacts.apply(
        lambda r: normalize_address(r['Street'], r['City'], r['Zipcode']), axis=1
    )

    # Load existing participants
    print("\n📊 Loading existing participants from database...")
    existing = list(db.participants.find({}, {
        'participant_id': 1, 'email': 1, 'phone': 1,
        'address.street': 1, 'address.zip': 1, 'address.city': 1
    }))
    print(f"   Existing participants: {len(existing)}")

    # Build lookup indexes
    email_index = {}
    phone_index = {}
    address_index = {}

    for p in existing:
        pid = p['participant_id']

        # Email index
        if p.get('email'):
            email_index[p['email'].lower()] = pid

        # Phone index
        if p.get('phone'):
            phone_norm = normalize_phone(p['phone'])
            if phone_norm:
                phone_index[phone_norm] = pid

        # Address index
        addr = p.get('address', {})
        if addr.get('street') and addr.get('zip'):
            addr_key = normalize_address(addr['street'], addr.get('city'), addr['zip'])
            if addr_key:
                address_index[addr_key] = pid

    print(f"\n📇 Built lookup indexes:")
    print(f"   Email index: {len(email_index)} entries")
    print(f"   Phone index: {len(phone_index)} entries")
    print(f"   Address index: {len(address_index)} entries")

    # Matching analysis
    print("\n🔍 MATCHING ANALYSIS")
    print("-" * 60)

    matched_by_email = []
    matched_by_phone = []
    matched_by_address = []
    not_matched = []

    for idx, row in contacts.iterrows():
        match_found = False
        match_method = None
        matched_pid = None

        # Try email match first (most reliable)
        if row['email_norm'] and row['email_norm'] in email_index:
            matched_by_email.append(row)
            match_found = True
            match_method = 'email'
            matched_pid = email_index[row['email_norm']]

        # Try phone match
        elif row['phone_norm'] and row['phone_norm'] in phone_index:
            matched_by_phone.append(row)
            match_found = True
            match_method = 'phone'
            matched_pid = phone_index[row['phone_norm']]

        # Try address match
        elif row['address_key'] and row['address_key'] in address_index:
            matched_by_address.append(row)
            match_found = True
            match_method = 'address'
            matched_pid = address_index[row['address_key']]

        if not match_found:
            not_matched.append(row)

    total = len(contacts)
    print(f"\n✅ MATCHED: {len(matched_by_email) + len(matched_by_phone) + len(matched_by_address)} ({(len(matched_by_email) + len(matched_by_phone) + len(matched_by_address))/total*100:.1f}%)")
    print(f"   By email:   {len(matched_by_email):>5} ({len(matched_by_email)/total*100:.1f}%)")
    print(f"   By phone:   {len(matched_by_phone):>5} ({len(matched_by_phone)/total*100:.1f}%)")
    print(f"   By address: {len(matched_by_address):>5} ({len(matched_by_address)/total*100:.1f}%)")
    print(f"\n❌ NOT MATCHED: {len(not_matched)} ({len(not_matched)/total*100:.1f}%)")

    # Analyze unmatched contacts
    if not_matched:
        print("\n📋 UNMATCHED CONTACTS ANALYSIS")
        print("-" * 60)

        not_matched_df = pd.DataFrame(not_matched)

        # Check what data we have for unmatched
        has_email = not_matched_df['email_norm'].notna().sum()
        has_address = not_matched_df['address_key'].notna().sum()
        has_county = not_matched_df['County'].notna().sum()

        print(f"   With email:   {has_email} ({has_email/len(not_matched)*100:.1f}%)")
        print(f"   With address: {has_address} ({has_address/len(not_matched)*100:.1f}%)")
        print(f"   With county:  {has_county} ({has_county/len(not_matched)*100:.1f}%)")

        # County distribution for residential/demographic lookup
        print("\n📍 COUNTY DISTRIBUTION (for residential/demographic lookup):")
        county_counts = not_matched_df['County'].value_counts()
        for county, count in county_counts.head(15).items():
            print(f"   {county if pd.notna(county) else 'Unknown'}: {count}")

        # Zip code distribution
        print("\n📮 ZIP CODE DISTRIBUTION (top 15):")
        zip_counts = not_matched_df['Zipcode'].value_counts()
        for zipcode, count in zip_counts.head(15).items():
            print(f"   {zipcode}: {count}")

        # City distribution
        print("\n🏙️ CITY DISTRIBUTION (top 15):")
        city_counts = not_matched_df['City'].value_counts()
        for city, count in city_counts.head(15).items():
            print(f"   {city}: {count}")

    # Summary for ingestion planning
    print("\n" + "=" * 80)
    print("📊 INGESTION PLANNING SUMMARY")
    print("=" * 80)
    print(f"\nTotal unique contacts to process: {total}")
    print(f"  → Can link to existing participants: {len(matched_by_email) + len(matched_by_phone) + len(matched_by_address)}")
    print(f"  → Need to create new participants: {len(not_matched)}")
    print(f"\nNew participants will need:")
    print(f"  → Residential data lookup by address")
    print(f"  → Demographic data linkage by parcel/address")

    # Export unmatched for further analysis
    if not_matched:
        not_matched_df = pd.DataFrame(not_matched)
        export_cols = ['Phone Number', 'Email', 'First Name', 'Last Name',
                       'Street', 'City', 'County', 'Zipcode', 'ContactID']
        export_df = not_matched_df[[c for c in export_cols if c in not_matched_df.columns]]
        export_path = '/home/yersinia/devel/octopus/data/campaign_texting/compact/unmatched_contacts.csv'
        export_df.to_csv(export_path, index=False)
        print(f"\n📁 Exported unmatched contacts to: {export_path}")

    client.close()
    print("\n✅ Dry-run complete!")


if __name__ == '__main__':
    main()
