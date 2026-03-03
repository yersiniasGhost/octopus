#!/usr/bin/env python3
"""
Export IMPACT Winter 2026-01 campaign data as color-coded CSV files.

Reads both color-coded Excel files, classifies each row by cell background color,
and writes 6 separate CSVs (one per engagement status) to data/campaign-IMPACT-202601/.

Also verifies and fixes:
  - Application → Campaign linkage (63 GREEN rows with empty likely_campaigns)
  - Participant do_not_contact flags (154 RED opted-out rows)

Color Code Mapping:
  - Blank: Received, no click → impact_winter_blank_received.csv
  - Yellow (FFFFFF00): Clicked link, no form → impact_winter_yellow_clicked.csv
  - Green (FF92D050): Filled out form → impact_winter_green_converted.csv
  - Orange (FFFFC000): Nasty/uninterested → impact_winter_orange_negative.csv
  - Red (FFFF0000): Opted out (STOP) → impact_winter_red_opted_out.csv
  - Blue (theme_4): Bad number/undeliverable → impact_winter_blue_undeliverable.csv

Usage:
    python scripts/export_campaign_color_csvs_tool.py [--dry-run] [--skip-db]
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl
from pymongo import MongoClient

# ── Configuration ──────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'campaign-IMPACT-202601'

CAMPAIGN_FILES = {
    'EmpowerSaves_OH_Text75_Winter_Section1_COLORCODED.xlsx': 'text_impact_winter_75',
    'EmpowerSaves_OH_Text76_Winter_Section2_COLOR CODED.xlsx': 'text_impact_winter_76',
}

COLOR_MAPPING = {
    None:       {'color': 'blank',  'label': 'Received, no click',    'status': 'received'},
    'FFFFFF00': {'color': 'yellow', 'label': 'Clicked link, no form', 'status': 'clicked'},
    'FF92D050': {'color': 'green',  'label': 'Filled out form',       'status': 'converted'},
    'FFFFC000': {'color': 'orange', 'label': 'Nasty/uninterested',    'status': 'negative_response'},
    'FFFF0000': {'color': 'red',    'label': 'Opted out (STOP)',      'status': 'opted_out'},
    'theme_4':  {'color': 'blue',   'label': 'Bad number/undeliverable', 'status': 'undeliverable'},
}

CSV_FILES = {
    'blank':  'impact_winter_blank_received.csv',
    'yellow': 'impact_winter_yellow_clicked.csv',
    'green':  'impact_winter_green_converted.csv',
    'orange': 'impact_winter_orange_negative.csv',
    'red':    'impact_winter_red_opted_out.csv',
    'blue':   'impact_winter_blue_undeliverable.csv',
}

CSV_COLUMNS = [
    'source_file', 'campaign_id', 'first_name', 'cell', 'parcel_id',
    'address', 'city', 'state', 'zip', 'customer_name', 'last', 'first',
    'email', 'income', 'senior', 'children', 'annual_kwh', 'energy_burden',
    'color', 'engagement_status',
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_cell_color(cell) -> str:
    """Extract fill color from cell, return color key or None."""
    fill = cell.fill
    if fill.fill_type != 'solid' or not fill.fgColor:
        return None
    color = fill.fgColor
    if color.type == 'rgb' and color.rgb and color.rgb != '00000000':
        return color.rgb
    elif color.type == 'theme':
        return f'theme_{color.theme}'
    return None


def normalize_phone(phone) -> str:
    """Normalize phone number to 10 digits."""
    if phone is None:
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def safe_str(val) -> str:
    """Convert value to string, handling None."""
    if val is None:
        return ''
    return str(val).strip()


def safe_zip(val) -> str:
    """Extract first 5 digits of ZIP."""
    if val is None:
        return ''
    return str(val).strip()[:5]


def read_excel_rows(filepath: Path) -> list[dict]:
    """Read Excel file with color classification, return list of row dicts."""
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    headers = [cell.value for cell in ws[1]]

    rows = []
    for row_idx in range(2, ws.max_row + 1):
        color_key = get_cell_color(ws.cell(row=row_idx, column=1))
        row_data = {}
        for col_idx, header in enumerate(headers, 1):
            if header:
                row_data[header] = ws.cell(row=row_idx, column=col_idx).value
        row_data['_color_key'] = color_key
        rows.append(row_data)

    wb.close()
    return rows


def row_to_csv_dict(row: dict, source_file: str, campaign_id: str, color_info: dict) -> dict:
    """Map Excel row to CSV output columns."""
    return {
        'source_file': source_file,
        'campaign_id': campaign_id,
        'first_name': safe_str(row.get('<VD_FirstName>')),
        'cell': safe_str(row.get('Cell')),
        'parcel_id': safe_str(row.get('parcel_id')),
        'address': safe_str(row.get('ServiceAddress1')),
        'city': safe_str(row.get('ServiceCity')),
        'state': safe_str(row.get('ServiceState')),
        'zip': safe_zip(row.get('ServicePostalCode')),
        'customer_name': safe_str(row.get('CustomerName')),
        'last': safe_str(row.get('LAST')),
        'first': safe_str(row.get('FIRST')),
        'email': safe_str(row.get('Email')),
        'income': safe_str(row.get('MD_HouseholdIncome') or row.get('MD_approx_income2')),
        'senior': safe_str(row.get('MD_PresenceOfSenior')),
        'children': safe_str(row.get('MD_PresenceOfChildren')),
        'annual_kwh': safe_str(row.get('annual_consumption')),
        'energy_burden': safe_str(row.get('total_energy_burden')),
        'color': color_info['color'],
        'engagement_status': color_info['status'],
    }


# ── Step 1: Export CSVs ───────────────────────────────────────────────────────

def export_color_csvs(dry_run: bool = False) -> dict:
    """Read both Excel files, classify by color, write 6 CSVs. Returns phone→campaign_id map for GREEN rows."""
    buckets = defaultdict(list)  # color -> list of csv dicts
    green_phones = {}  # phone -> campaign_id for GREEN rows
    red_phones = {}    # phone -> campaign_id for RED rows
    color_stats = defaultdict(lambda: defaultdict(int))  # file -> color -> count

    for filename, campaign_id in CAMPAIGN_FILES.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  ⚠️  File not found: {filepath}")
            continue

        print(f"\n  📁 Reading: {filename}")
        rows = read_excel_rows(filepath)
        print(f"     {len(rows)} rows loaded")

        for row in rows:
            color_key = row.pop('_color_key')
            color_info = COLOR_MAPPING.get(color_key, COLOR_MAPPING[None])
            color_name = color_info['color']

            csv_row = row_to_csv_dict(row, filename, campaign_id, color_info)
            buckets[color_name].append(csv_row)
            color_stats[filename][color_name] += 1

            # Track GREEN phones for application linkage
            if color_name == 'green':
                phone = normalize_phone(row.get('Cell'))
                if phone:
                    green_phones[phone] = campaign_id

            # Track RED phones for do_not_contact verification
            if color_name == 'red':
                phone = normalize_phone(row.get('Cell'))
                if phone:
                    red_phones[phone] = campaign_id

    # Print distribution
    print("\n  🎨 Color distribution:")
    print(f"     {'Color':<10} {'Text75':>8} {'Text76':>8} {'Total':>8}  Meaning")
    print(f"     {'─'*10} {'─'*8} {'─'*8} {'─'*8}  {'─'*30}")
    for color_key, info in COLOR_MAPPING.items():
        cn = info['color']
        f1 = list(CAMPAIGN_FILES.keys())[0]
        f2 = list(CAMPAIGN_FILES.keys())[1]
        t75 = color_stats.get(f1, {}).get(cn, 0)
        t76 = color_stats.get(f2, {}).get(cn, 0)
        total = len(buckets[cn])
        print(f"     {cn:<10} {t75:>8} {t76:>8} {total:>8}  {info['label']}")

    # Write CSVs
    if dry_run:
        print("\n  📋 DRY-RUN: Would write these CSV files:")
        for color_name, csv_file in CSV_FILES.items():
            print(f"     {csv_file}: {len(buckets[color_name])} rows")
    else:
        print("\n  💾 Writing CSV files:")
        for color_name, csv_file in CSV_FILES.items():
            outpath = DATA_DIR / csv_file
            rows_for_color = buckets[color_name]
            with open(outpath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows_for_color)
            print(f"     ✅ {csv_file}: {len(rows_for_color)} rows")

    return {'green_phones': green_phones, 'red_phones': red_phones}


# ── Step 2: Fix Application → Campaign Linkage ───────────────────────────────

def fix_application_linkage(db, green_phones: dict, dry_run: bool = False):
    """Update Application documents for GREEN rows to link to their source campaigns."""
    print("\n  🔗 Checking application → campaign linkage...")

    # Find applications that match GREEN phone numbers
    apps = list(db.applications.find(
        {'applicant.phone_raw': {'$in': list(green_phones.keys())}},
        {'_id': 1, 'applicant.phone_raw': 1, 'applicant.first_name': 1,
         'attribution.likely_campaigns': 1, 'import_batch': 1}
    ))

    # Also try normalized phone match
    if len(apps) < len(green_phones):
        apps_by_phone = list(db.applications.find(
            {'applicant.phone': {'$in': list(green_phones.keys())}},
            {'_id': 1, 'applicant.phone': 1, 'applicant.phone_raw': 1,
             'applicant.first_name': 1, 'attribution.likely_campaigns': 1, 'import_batch': 1}
        ))
        seen_ids = {a['_id'] for a in apps}
        for a in apps_by_phone:
            if a['_id'] not in seen_ids:
                apps.append(a)

    print(f"     Found {len(apps)} matching applications (expected ~63)")

    needs_update = 0
    already_linked = 0
    updated = 0

    for app in apps:
        phone = app.get('applicant', {}).get('phone_raw') or app.get('applicant', {}).get('phone')
        campaign_id = green_phones.get(phone)
        if not campaign_id:
            continue

        existing = app.get('attribution', {}).get('likely_campaigns', [])
        already_has = any(
            lc.get('campaign_id', '').startswith('text_impact_winter')
            for lc in (existing or [])
        )

        if already_has:
            already_linked += 1
            continue

        needs_update += 1
        if not dry_run:
            new_link = {
                'campaign_id': campaign_id,
                'confidence': 1.0,
                'method': 'excel_color_verified',
            }
            db.applications.update_one(
                {'_id': app['_id']},
                {'$push': {'attribution.likely_campaigns': new_link}}
            )
            updated += 1

    print(f"     Already linked: {already_linked}")
    print(f"     Needs update:   {needs_update}")
    if dry_run:
        print(f"     DRY-RUN: Would update {needs_update} applications")
    else:
        print(f"     Updated:        {updated}")


# ── Step 3: Verify do_not_contact Flags ───────────────────────────────────────

def verify_do_not_contact(db, red_phones: dict, dry_run: bool = False):
    """Verify that RED (opted-out) participants have do_not_contact: True."""
    print("\n  🚫 Verifying do_not_contact flags for opted-out participants...")

    phone_list = list(red_phones.keys())
    total_red = len(phone_list)

    # Find participants with these phones
    participants = list(db.participants.find(
        {'participant_id': {'$in': phone_list}},
        {'participant_id': 1, 'do_not_contact': 1, 'phone': 1}
    ))

    found = len(participants)
    flagged = sum(1 for p in participants if p.get('do_not_contact') is True)
    missing_flag = [p for p in participants if p.get('do_not_contact') is not True]
    not_found = total_red - found

    print(f"     RED phones in Excel:      {total_red}")
    print(f"     Found in participants:    {found}")
    print(f"     Already flagged:          {flagged}")
    print(f"     Missing do_not_contact:   {len(missing_flag)}")
    print(f"     Not found in DB:          {not_found}")

    if missing_flag:
        if dry_run:
            print(f"     DRY-RUN: Would flag {len(missing_flag)} participants as do_not_contact")
        else:
            ids_to_fix = [p['participant_id'] for p in missing_flag]
            result = db.participants.update_many(
                {'participant_id': {'$in': ids_to_fix}},
                {'$set': {'do_not_contact': True, 'updated_at': datetime.utcnow()}}
            )
            print(f"     ✅ Fixed {result.modified_count} participants")
    else:
        print(f"     ✅ All opted-out participants correctly flagged")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Export color-coded campaign CSVs and verify DB linkage')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing files or DB changes')
    parser.add_argument('--skip-db', action='store_true', help='Skip database verification steps')
    args = parser.parse_args()

    print("=" * 80)
    print("IMPACT WINTER 2026-01 — COLOR-CODED CSV EXPORT & DB VERIFICATION")
    print("=" * 80)

    # Step 1: Export CSVs
    print("\n📋 STEP 1: Export color-coded CSVs")
    print("─" * 40)
    result = export_color_csvs(dry_run=args.dry_run)

    if not args.skip_db:
        client = MongoClient('localhost', 27017)
        db = client['empower_development']

        # Step 2: Fix application linkage
        print("\n📋 STEP 2: Fix Application → Campaign linkage")
        print("─" * 40)
        fix_application_linkage(db, result['green_phones'], dry_run=args.dry_run)

        # Step 3: Verify do_not_contact
        print("\n📋 STEP 3: Verify do_not_contact flags")
        print("─" * 40)
        verify_do_not_contact(db, result['red_phones'], dry_run=args.dry_run)

        # Verification queries
        if not args.dry_run:
            print("\n📋 VERIFICATION QUERIES")
            print("─" * 40)

            linked_apps = db.applications.count_documents(
                {'attribution.likely_campaigns.campaign_id': {'$regex': 'text_impact_winter'}}
            )
            print(f"  Applications with IMPACT winter linkage: {linked_apps}")

            dnc_count = db.participants.count_documents({
                'do_not_contact': True,
                'source_campaigns': {'$in': ['text_impact_winter_75', 'text_impact_winter_76']}
            })
            print(f"  Participants with do_not_contact + IMPACT winter: {dnc_count}")

        client.close()

    print("\n" + "=" * 80)
    print("✅ Done!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
