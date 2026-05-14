#!/usr/bin/env python3
"""
Reformat campaign_list.csv to match BOLT analysis format with 53 columns.

Pulls data from:
- FranklinCountyResidential: property data (year built, sqft, stories)
- FranklinCountyDemographic: contact info and demographics
- FranklinElectricalDB: monthly energy readings

Usage:
    python scripts/reformat_campaign_list_tool.py --dry-run
    python scripts/reformat_campaign_list_tool.py --limit 100
    python scripts/reformat_campaign_list_tool.py
"""

import argparse
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE = 'data/campaign-list-20260120-franklin/campaign_list.csv'
OUTPUT_FILE = 'data/campaign-list-20260120-franklin/campaign_list_bolt_format.csv'
DATABASE = 'empower_development'

# Output columns matching BOLT format (excluding #54 applicant review)
OUTPUT_COLUMNS = [
    'parcel_id', 'ServiceAddress1', 'ServiceCity', 'ServiceState', 'ServicePostalCode',
    'CustomerName', 'LAST', 'FIRST', 'Year Built', 'Stories', 'Area Finished Above Grade',
    'Cell', 'Email', 'Marital Status', 'Number of Adults',
    'Age in Two-Year Increments - 1st Individual', 'MD_HouseholdIncome',
    'MD_PresenceOfChildren', 'MD_PresenceOfSenior', 'MD_EstimatedHomeValue',
    'DATE0_KWH', 'KWH0', 'DATE1_KWH', 'KWH1', 'DATE2_KWH', 'KWH2',
    'DATE3_KWH', 'KWH3', 'DATE4_KWH', 'KWH4', 'DATE5_KWH', 'KWH5',
    'DATE6_KWH', 'KWH6', 'DATE7_KWH', 'KWH7', 'DATE8_KWH', 'KWH8',
    'DATE9_KWH', 'KWH9', 'DATE10_KWH', 'KWH10', 'DATE11_KWH', 'KWH11',
    'annual_consumption', 'annual cost', 'annual savings', 'monthly cost',
    'monthly savings', 'daily cost', 'MD_approx_income2', 'energy_burden_kwh',
    'total_energy_burden'
]


def normalize_address(addr):
    """Normalize address for matching."""
    if pd.isna(addr) or not addr:
        return None
    import re
    addr = str(addr).upper().strip()
    addr = re.sub(r'\s+', ' ', addr)
    addr = re.sub(r'\.$', '', addr)
    # Normalize common abbreviations
    addr = re.sub(r'\bAV\b', 'AVE', addr)
    addr = re.sub(r'\bST\b$', 'ST', addr)  # ST is already standard
    addr = re.sub(r'\bDR\b$', 'DR', addr)
    addr = re.sub(r'\bRD\b$', 'RD', addr)
    addr = re.sub(r'\bCT\b$', 'CT', addr)
    addr = re.sub(r'\bLN\b$', 'LN', addr)
    addr = re.sub(r'\bPL\b$', 'PL', addr)
    addr = re.sub(r'\bBLVD\b', 'BLVD', addr)
    return addr


def build_lookup_dicts(db, parcel_ids):
    """Build lookup dictionaries from MongoDB collections."""
    print("Building lookup dictionaries from MongoDB...")

    # Residential data by parcel_id
    print("  Loading FranklinCountyResidential...")
    residential = {}
    for doc in db['FranklinCountyResidential'].find({'parcel_id': {'$in': list(parcel_ids)}}):
        residential[doc['parcel_id']] = doc
    print(f"    Found {len(residential):,} residential records")

    # Demographic data - index by BOTH parcel_id and address
    print("  Loading FranklinCountyDemographic...")
    demographic_by_parcel = {}
    demographic_by_addr = {}
    for doc in db['FranklinCountyDemographic'].find():
        parcel = doc.get('parcel_id')
        if parcel and parcel != '':
            demographic_by_parcel[parcel] = doc
        addr = doc.get('address')
        if addr:
            demographic_by_addr[addr] = doc
    print(f"    Loaded {len(demographic_by_parcel):,} by parcel_id, {len(demographic_by_addr):,} by address")

    # Electrical data by parcel_id
    print("  Loading FranklinElectricalDB...")
    electrical = {}
    for doc in db['FranklinElectricalDB'].find({'parcel_id': {'$in': list(parcel_ids)}}):
        electrical[doc['parcel_id']] = doc
    print(f"    Found {len(electrical):,} electrical records")

    return residential, demographic_by_parcel, demographic_by_addr, electrical


def get_monthly_readings(elec_doc):
    """Extract monthly readings from electrical document, sorted by date descending."""
    if not elec_doc:
        return []

    readings = []
    time_series = elec_doc.get('time_series_elec', {})

    for date_str, kwh in time_series.items():
        try:
            # Parse date string like '2024-09-25 00:00:00'
            date = datetime.strptime(date_str.split()[0], '%Y-%m-%d')
            readings.append((date, kwh))
        except (ValueError, AttributeError):
            continue

    # Sort by date descending (most recent first)
    readings.sort(key=lambda x: x[0], reverse=True)
    return readings[:12]  # Return up to 12 months


def format_date(dt):
    """Format datetime to YYYY-MM-DD string."""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d')
    return str(dt) if dt else ''


def build_row(parcel_id, campaign_row, residential, demographic_by_parcel, demographic_by_addr, electrical):
    """Build a single output row with all 53 columns."""

    res_doc = residential.get(parcel_id, {})
    elec_doc = electrical.get(parcel_id, {})

    # Try parcel_id first, then fall back to address for demographic lookup
    demo_doc = demographic_by_parcel.get(parcel_id, {})
    address = normalize_address(campaign_row.get('Address'))
    if not demo_doc and address:
        demo_doc = demographic_by_addr.get(address, {})

    # Parse name
    name = str(campaign_row.get('Name', '')).strip()
    if ',' in name:
        parts = name.split(',', 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ''
    else:
        parts = name.split(' ', 1)
        first_name = parts[0].strip()
        last_name = parts[1].strip() if len(parts) > 1 else ''

    # Get monthly readings
    readings = get_monthly_readings(elec_doc)

    # Calculate costs from annual_kwh
    annual_kwh = campaign_row.get('Annual_kWh', 0) or 0
    annual_cost = annual_kwh * 0.15
    annual_savings = annual_cost * 0.30
    monthly_cost = annual_cost / 12
    monthly_savings = annual_savings / 12
    daily_cost = annual_cost / 365

    # Get income for energy burden
    estimated_income = campaign_row.get('Estimated_Income', 0) or 0
    if estimated_income > 0:
        energy_burden = (annual_cost / estimated_income) * 100
    else:
        energy_burden = 0

    # Map marital status
    marital = demo_doc.get('md_marital_status', '')
    if marital == 'Married':
        marital = 'M'
    elif marital == 'Single':
        marital = 'S'

    # Map presence of children/senior
    children = demo_doc.get('md_presence_of_children', '')
    if 'Yes' in str(children) or 'Present' in str(children):
        children = 'Children Present'
    elif 'No' in str(children):
        children = 'No Children Present'

    senior = demo_doc.get('md_presence_of_senior', '')
    if 'Yes' in str(senior) or 'Present' in str(senior):
        senior = 'Senior Present'
    elif 'No' in str(senior):
        senior = 'No Senior Present'

    # Build row
    row = {
        'parcel_id': parcel_id,
        'ServiceAddress1': address or '',
        'ServiceCity': str(campaign_row.get('City', '')).upper(),
        'ServiceState': 'OH',
        'ServicePostalCode': campaign_row.get('Zipcode', ''),
        'CustomerName': name,
        'LAST': last_name,
        'FIRST': first_name,
        'Year Built': campaign_row.get('Year_Built', ''),
        'Stories': res_doc.get('stories', ''),
        'Area Finished Above Grade': campaign_row.get('Sqft', ''),
        'Cell': demo_doc.get('mobile', '') if demo_doc.get('mobile', -1) > 0 else '',
        'Email': demo_doc.get('email', ''),
        'Marital Status': marital,
        'Number of Adults': '',  # Not readily available
        'Age in Two-Year Increments - 1st Individual': '',  # Not readily available
        'MD_HouseholdIncome': demo_doc.get('estimated_income', '') if demo_doc.get('estimated_income', -1) > 0 else '',
        'MD_PresenceOfChildren': children,
        'MD_PresenceOfSenior': senior,
        'MD_EstimatedHomeValue': demo_doc.get('md_estimated_home_value', ''),
    }

    # Add monthly readings (DATE0-11, KWH0-11)
    for i in range(12):
        if i < len(readings):
            row[f'DATE{i}_KWH'] = format_date(readings[i][0])
            row[f'KWH{i}'] = readings[i][1]
        else:
            row[f'DATE{i}_KWH'] = ''
            row[f'KWH{i}'] = ''

    # Add cost calculations
    row['annual_consumption'] = f"{int(annual_kwh):,}" if annual_kwh else ''
    row['annual cost'] = f"${annual_cost:,.2f}" if annual_cost else ''
    row['annual savings'] = f"${annual_savings:,.2f}" if annual_savings else ''
    row['monthly cost'] = f"${monthly_cost:,.2f}" if monthly_cost else ''
    row['monthly savings'] = f"${monthly_savings:,.2f}" if monthly_savings else ''
    row['daily cost'] = f"${daily_cost:,.2f}" if daily_cost else ''
    row['MD_approx_income2'] = estimated_income if estimated_income > 0 else ''
    row['energy_burden_kwh'] = round(energy_burden, 2) if energy_burden else ''
    row['total_energy_burden'] = round(energy_burden, 2) if energy_burden else ''

    return row


def main():
    parser = argparse.ArgumentParser(description='Reformat campaign list to BOLT format')
    parser.add_argument('--input', default=INPUT_FILE, help='Input CSV file')
    parser.add_argument('--output', default=OUTPUT_FILE, help='Output CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--limit', type=int, help='Limit records to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("=" * 70)
    print("REFORMAT CAMPAIGN LIST TO BOLT FORMAT")
    print("=" * 70)
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Dry Run: {args.dry_run}")
    print()

    # Load campaign list
    print("Loading campaign list...")
    df = pd.read_csv(args.input)
    print(f"Loaded {len(df):,} records")

    if args.limit:
        df = df.head(args.limit)
        print(f"Limited to {len(df):,} records")

    # Connect to MongoDB
    client = MongoClient(os.getenv('MONGODB_URI'))
    db = client[DATABASE]

    # Get all parcel IDs
    parcel_ids = set(df['Parcel_ID'].dropna().astype(str))
    print(f"Unique parcel IDs: {len(parcel_ids):,}")

    # Build lookup dictionaries
    residential, demographic_by_parcel, demographic_by_addr, electrical = build_lookup_dicts(db, parcel_ids)

    # Process each row
    print("\nProcessing records...")
    output_rows = []
    stats = {'processed': 0, 'with_cell': 0, 'with_email': 0, 'with_readings': 0}

    for idx, row in df.iterrows():
        parcel_id = str(row['Parcel_ID'])
        output_row = build_row(parcel_id, row, residential, demographic_by_parcel, demographic_by_addr, electrical)
        output_rows.append(output_row)

        stats['processed'] += 1
        if output_row['Cell']:
            stats['with_cell'] += 1
        if output_row['Email']:
            stats['with_email'] += 1
        if output_row['KWH0']:
            stats['with_readings'] += 1

        if stats['processed'] % 5000 == 0:
            print(f"  Processed {stats['processed']:,}...")

        if args.verbose and stats['processed'] <= 3:
            print(f"\nSample row #{stats['processed']}:")
            for k, v in output_row.items():
                if v:
                    print(f"  {k}: {v}")

    # Create output DataFrame
    output_df = pd.DataFrame(output_rows, columns=OUTPUT_COLUMNS)

    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total processed: {stats['processed']:,}")
    print(f"With Cell phone: {stats['with_cell']:,} ({stats['with_cell']/stats['processed']*100:.1f}%)")
    print(f"With Email: {stats['with_email']:,} ({stats['with_email']/stats['processed']*100:.1f}%)")
    print(f"With energy readings: {stats['with_readings']:,} ({stats['with_readings']/stats['processed']*100:.1f}%)")
    print()

    if args.dry_run:
        print("DRY RUN - No file saved")
        print(f"Would save {len(output_df):,} records to {args.output}")
    else:
        output_df.to_csv(args.output, index=False)
        print(f"Saved {len(output_df):,} records to {args.output}")

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)

    client.close()
    return output_df


if __name__ == '__main__':
    main()
