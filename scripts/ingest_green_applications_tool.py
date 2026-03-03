#!/usr/bin/env python3
"""
Ingest GREEN (converted) rows from IMPACT 20260110 campaign as Application documents.

The text_impact_20260110 campaign has 54 GREEN rows (form completed) but only 4
matched existing application records. This script creates Application documents
for the remaining rows, with participant matching via parcel_id (primary) or
phone (fallback).

Data source: data/campaign-IMPACT-20260110/impact_20260110_green_converted.csv

Usage:
    source venv/bin/activate
    python scripts/ingest_green_applications_tool.py --dry-run
    python scripts/ingest_green_applications_tool.py
"""
import argparse
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient

from src.utils.application_parsers import normalize_phone, normalize_income


CSV_PATH = "data/campaign-IMPACT-20260110/impact_20260110_green_converted.csv"
CAMPAIGN_ENTRY_DATE = datetime(2026, 1, 10)
COUNTY = "Franklin"

# Income bracket mapping for string-format income values (e.g. "$15,001-$20,000")
INCOME_BRACKET_MAP = {
    "$0-$15,000": 10000.0,
    "$15,001-$20,000": 17500.0,
    "$20,001-$30,000": 25000.0,
    "$30,001-$40,000": 35000.0,
    "$40,001-$50,000": 45000.0,
    "$50,001-$60,000": 55000.0,
    "$60,001-$75,000": 62500.0,
    "$75,001-$100,000": 87500.0,
    "$100,001-$125,000": 112500.0,
    "$125,001+": 150000.0,
}


def parse_income_value(raw: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """Parse income from CSV — handles both numeric and bracket formats."""
    if not raw or not str(raw).strip():
        return None, None
    raw_str = str(raw).strip()

    # Check bracket format first (e.g. "$15,001-$20,000")
    if raw_str in INCOME_BRACKET_MAP:
        return INCOME_BRACKET_MAP[raw_str], raw_str

    # Fall through to standard numeric parser
    return normalize_income(raw_str)


def build_participant_indexes(db) -> Tuple[Dict, Dict]:
    """Build in-memory parcel_id and phone indexes for fast participant lookup."""
    existing = list(db.participants.find({}, {
        'participant_id': 1, 'phone': 1, 'linkage.parcel_id': 1
    }))

    parcel_index = {}  # parcel_id -> participant_id
    phone_index = {}   # phone -> participant_id

    for p in existing:
        pid = p.get('participant_id')
        if not pid:
            continue
        phone = p.get('phone')
        if phone:
            phone_index[phone] = pid
        parcel_id = p.get('linkage', {}).get('parcel_id')
        if parcel_id:
            parcel_index[parcel_id] = pid

    return parcel_index, phone_index


def match_participant(row: Dict, parcel_index: Dict, phone_index: Dict) -> Dict:
    """Match a CSV row to existing participant. Parcel_id first, then phone."""
    match = {
        'participant_id': None,
        'match_method': None,
        'match_confidence': 0.0,
        'matched_at': None,
    }

    # Strategy 1: parcel_id match (highest confidence for this dataset)
    parcel_id = row.get('parcel_id', '').strip()
    if parcel_id and parcel_id in parcel_index:
        match['participant_id'] = parcel_index[parcel_id]
        match['match_method'] = 'parcel_id'
        match['match_confidence'] = 0.90
        match['matched_at'] = datetime.utcnow()
        return match

    # Strategy 2: phone match
    phone_raw = row.get('cell', '').strip()
    phone_norm = normalize_phone(phone_raw)
    if phone_norm and phone_norm in phone_index:
        match['participant_id'] = phone_index[phone_norm]
        match['match_method'] = 'phone'
        match['match_confidence'] = 0.85
        match['matched_at'] = datetime.utcnow()
        return match

    return match


def build_application_doc(row: Dict, import_batch: str) -> Optional[Dict]:
    """Build an Application document from a CSV row."""
    campaign_id = row.get('campaign_id', '').strip()
    phone_raw = row.get('cell', '').strip()
    phone_norm = normalize_phone(phone_raw)

    if not campaign_id or not phone_raw:
        return None

    # Deterministic application_id
    phone_key = phone_norm or re.sub(r'\D', '', phone_raw)
    application_id = f"green_{campaign_id}_{phone_key}"

    # Parse names
    first_name = row.get('first', '').strip() or None
    last_name = row.get('last', '').strip() or None
    email_raw = row.get('email', '').strip()
    email = email_raw.lower() if email_raw else None

    # Parse address — handle "NAN" city values from the CSV
    city = row.get('city', '').strip()
    if city.upper() == 'NAN':
        city = None

    # Parse income
    income, income_raw = parse_income_value(row.get('income'))

    # Parse senior/children flags
    senior_raw = row.get('senior', '').strip()
    children_raw = row.get('children', '').strip()
    has_senior = senior_raw.lower() == 'senior present' if senior_raw else None
    has_children = children_raw.lower() == 'children present' if children_raw else None

    return {
        'application_id': application_id,
        'applicant': {
            'first_name': first_name,
            'middle_name': None,
            'last_name': last_name,
            'email': email,
            'phone': phone_norm,
            'phone_raw': phone_raw,
        },
        'address': {
            'street': row.get('address', '').strip() or None,
            'city': city,
            'state': row.get('state', '').strip() or None,
            'zip': row.get('zip', '').strip() or None,
            'county': COUNTY,
        },
        'self_reported': {
            'age': None,
            'age_raw': None,
            'household_income': income,
            'household_income_raw': income_raw,
            'household_members': None,
            'housing_status': None,
            'needs_housing_help': None,
            'has_dependent_children': has_children,
            'pre_1978_home': None,
        },
        'attribution': {
            'utm': None,
            'likely_campaigns': [{
                'campaign_id': campaign_id,
                'confidence': 1.0,
                'method': 'excel_color_verified',
            }],
        },
        'participant_match': {},  # filled in after matching
        'cluster_assignment': {
            'phase1_cluster': None,
            'phase2_cluster': None,
            'phase3_cluster': None,
            'assigned_at': None,
        },
        'entry_date': CAMPAIGN_ENTRY_DATE,
        'created_at': datetime.utcnow(),
        'import_batch': import_batch,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Ingest GREEN (converted) campaign rows as Application documents')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without writing to database')
    parser.add_argument('--csv', default=CSV_PATH,
                        help=f'Path to green CSV (default: {CSV_PATH})')
    args = parser.parse_args()

    client = MongoClient("mongodb://localhost:27017")
    db = client['empower_development']

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    import_batch = f"green_conversions_20260110_{timestamp}"

    # Build participant lookup indexes
    print("📊 Building participant lookup indexes...")
    parcel_index, phone_index = build_participant_indexes(db)
    print(f"   Parcel index: {len(parcel_index)} entries")
    print(f"   Phone index:  {len(phone_index)} entries")

    # Check existing applications to avoid phone-level duplicates
    existing_phones = set()
    for app in db.applications.find({'applicant.phone': {'$ne': None}}, {'applicant.phone': 1}):
        existing_phones.add(app['applicant']['phone'])
    print(f"   Existing application phones: {len(existing_phones)}")

    # Read CSV
    print(f"\n📂 Reading {args.csv}...")
    rows = []
    with open(args.csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print(f"   Found {len(rows)} rows")

    if args.dry_run:
        print("\n📋 DRY-RUN MODE — no changes will be made\n")

    # Process rows
    stats = {
        'total': len(rows),
        'inserted': 0,
        'skipped_dup_app_id': 0,
        'skipped_dup_phone': 0,
        'skipped_error': 0,
        'matched_parcel': 0,
        'matched_phone': 0,
        'unmatched': 0,
    }

    for row in rows:
        doc = build_application_doc(row, import_batch)
        if not doc:
            stats['skipped_error'] += 1
            continue

        # Check phone-level duplicate against existing applications
        phone = doc['applicant']['phone']
        if phone and phone in existing_phones:
            stats['skipped_dup_phone'] += 1
            if args.dry_run:
                name = f"{doc['applicant']['first_name']} {doc['applicant']['last_name']}"
                print(f"  SKIP (existing phone): {name} {phone}")
            continue

        # Participant matching
        match = match_participant(row, parcel_index, phone_index)
        doc['participant_match'] = match

        if match['match_method'] == 'parcel_id':
            stats['matched_parcel'] += 1
        elif match['match_method'] == 'phone':
            stats['matched_phone'] += 1
        else:
            stats['unmatched'] += 1

        if args.dry_run:
            name = f"{doc['applicant']['first_name']} {doc['applicant']['last_name']}"
            method = match['match_method'] or 'none'
            pid = match['participant_id'] or '—'
            income_str = f"${doc['self_reported']['household_income']:,.0f}" if doc['self_reported']['household_income'] else 'N/A'
            print(f"  INSERT: {name:<25} match={method:<10} pid={pid:<15} income={income_str}")
        else:
            try:
                result = db.applications.update_one(
                    {'application_id': doc['application_id']},
                    {'$set': doc},
                    upsert=True
                )
                if result.upserted_id:
                    stats['inserted'] += 1
                else:
                    stats['skipped_dup_app_id'] += 1
            except Exception as e:
                print(f"  ERROR: {doc['application_id']}: {e}")
                stats['skipped_error'] += 1
                continue

        # Track phone so we don't double-insert within this batch
        if phone:
            existing_phones.add(phone)

    # Summary
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    print(f"  Total rows:              {stats['total']}")
    if args.dry_run:
        would_insert = stats['total'] - stats['skipped_dup_phone'] - stats['skipped_error']
        print(f"  Would insert:            {would_insert}")
    else:
        print(f"  Inserted:                {stats['inserted']}")
        print(f"  Skipped (dup app_id):    {stats['skipped_dup_app_id']}")
    print(f"  Skipped (existing phone): {stats['skipped_dup_phone']}")
    print(f"  Skipped (error):         {stats['skipped_error']}")
    print(f"  Matched by parcel_id:    {stats['matched_parcel']}")
    print(f"  Matched by phone:        {stats['matched_phone']}")
    print(f"  Unmatched:               {stats['unmatched']}")
    print(f"  Import batch:            {import_batch}")
    print("=" * 60)

    if args.dry_run:
        print("\nRun without --dry-run to execute ingestion.")


if __name__ == '__main__':
    main()
