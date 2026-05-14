#!/usr/bin/env python3
"""
Ingest EMPOWER-IMPACT LEADS_20260414.xlsx into the `applications` collection.

This is a hand-tracked CRM-style sheet of people who joined the IMPACT campaign
outreach pipeline. Schema differs from the GravityForms applications CSV:
- No Entry Id (we synthesize a deterministic application_id from email/phone)
- No UTM/source URL (we stamp synthetic IMPACT attribution)
- No entry Date column populated
- Adds lead-tracking fields: FPL %, Impact ZIP?, Called, Notes

Source columns:
    Full Name, Email, Street Address, City, State, ZIP Code, Phone,
    Age, Annual Income, MoH, FPL %, Impact ZIP?, Called, Date, Notes

The same `Application` model is reused; IMPACT-only fields are stored under
a `lead_tracking` sub-document (alongside existing precedents like
`energy_at_application` on IMPACT_Winter_2026_Converted records).

Usage:
    source venv/bin/activate
    python scripts/ingest_impact_leads_20260414_tool.py --dry-run
    python scripts/ingest_impact_leads_20260414_tool.py
    python scripts/ingest_impact_leads_20260414_tool.py --no-match
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

# Make repo root importable when invoked as `python scripts/...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.application import (
    Application, ApplicantIdentity, ApplicantAddress,
    SelfReportedDemographics, Attribution, UTMAttribution,
    ParticipantMatch,
)
from src.utils.application_parsers import (
    normalize_age, normalize_household_members, normalize_income, normalize_phone,
)
from src.utils.log_manager import LogManager
from scripts.ingest_applications import ApplicationIngester

logger = LogManager().get_logger(__name__)


class IndexTolerantIngester(ApplicationIngester):
    """ApplicationIngester variant that tolerates pre-existing non-unique indexes.

    The historical applications collection has a non-unique index on
    application_id (mixed int/string ids from earlier migrations). The parent
    class tries to recreate it as unique on startup and crashes; we rely on
    deterministic application_ids + upsert-by-filter for idempotency instead.
    """

    def _ensure_indexes(self):
        return None

DEFAULT_XLSX = Path(__file__).resolve().parent.parent / 'data' / 'EMPOWER-IMPACT LEADS_20260414.xlsx'
CAMPAIGN_TAG = 'impact_leads_20260414'

EXPECTED_HEADERS = [
    'Full Name', 'Email', 'Street Address', 'City', 'State', 'ZIP Code', 'Phone',
    'Age', 'Annual Income', 'MoH', 'FPL %', 'Impact ZIP?', 'Called', 'Date', 'Notes',
]


def split_full_name(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Split 'First Middle Last' into (first, middle, last)."""
    if not full_name:
        return None, None, None
    parts = [p for p in str(full_name).strip().split() if p]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], ' '.join(parts[1:-1]), parts[-1]


def normalize_zip(zip_raw: Any) -> Optional[str]:
    """Normalize ZIP from numeric or string input to a 5-digit string."""
    if zip_raw is None or zip_raw == '':
        return None
    if isinstance(zip_raw, float) and zip_raw.is_integer():
        zip_str = str(int(zip_raw))
    else:
        zip_str = str(zip_raw).strip()
    digits = ''.join(c for c in zip_str if c.isdigit())
    if len(digits) >= 5:
        return digits[:5]
    return digits or None


def parse_yes_flag(value: Any) -> Optional[bool]:
    """Parse 'Yes' / 'yes' / blank → True/None for flag-style columns."""
    if value is None:
        return None
    val = str(value).strip().lower()
    if not val:
        return None
    if val in ('y', 'yes', 'true', '1', 'x'):
        return True
    if val in ('n', 'no', 'false', '0'):
        return False
    return None


def parse_fpl_percent(value: Any) -> Optional[float]:
    """FPL % comes as a fraction (0.52 = 52% of FPL)."""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def synth_application_id(email: Optional[str], phone: Optional[str], row_index: int) -> str:
    """Generate deterministic application_id so re-runs upsert cleanly."""
    if email:
        key = email.strip().lower()
    elif phone:
        key = phone
    else:
        key = f'row{row_index}'
    return f'impact_lead_20260414_{key}'


def read_xlsx(xlsx_path: Path) -> List[Dict[str, Any]]:
    """Read the leads xlsx into a list of header→value dicts."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb['Sheet1']
    raw_rows = list(ws.iter_rows(values_only=True))
    if not raw_rows:
        return []

    header = list(raw_rows[0])
    last_idx = max((i for i, v in enumerate(header) if v is not None), default=-1)
    header = header[:last_idx + 1]
    if header[:len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
        logger.warning(f'Unexpected headers: {header}')

    rows: List[Dict[str, Any]] = []
    for row in raw_rows[1:]:
        trimmed = list(row[:last_idx + 1])
        if not any(c is not None and str(c).strip() for c in trimmed):
            continue
        record = {h: trimmed[i] if i < len(trimmed) else None for i, h in enumerate(header)}
        rows.append(record)
    return rows


def build_application(row: Dict[str, Any], import_batch: str, row_index: int) -> Tuple[Application, Dict[str, Any]]:
    """Convert a row dict into (Application, lead_tracking extras)."""
    first, middle, last = split_full_name(row.get('Full Name'))

    email_raw = row.get('Email')
    email = str(email_raw).strip().lower() if email_raw else None

    phone_raw = row.get('Phone')
    phone_str = str(phone_raw).strip() if phone_raw is not None else None
    phone_normalized = normalize_phone(phone_str)

    applicant = ApplicantIdentity(
        first_name=first, middle_name=middle, last_name=last,
        email=email or None,
        phone=phone_normalized,
        phone_raw=phone_str or None,
    )

    address = ApplicantAddress(
        street=(str(row['Street Address']).strip() if row.get('Street Address') else None),
        city=(str(row['City']).strip() if row.get('City') else None),
        state=(str(row['State']).strip() if row.get('State') else None),
        zip=normalize_zip(row.get('ZIP Code')),
        county=None,  # Not provided in source
    )

    age, age_raw = normalize_age(row.get('Age'))
    income, income_raw = normalize_income(row.get('Annual Income'))
    members = normalize_household_members(row.get('MoH'))

    self_reported = SelfReportedDemographics(
        age=age, age_raw=age_raw,
        household_income=income, household_income_raw=income_raw,
        household_members=members,
    )

    utm = UTMAttribution(
        utm_source='IMPACT',
        utm_medium='Lead',
        utm_campaign=CAMPAIGN_TAG,
        utm_content='Lead_Tracking_Sheet_20260414',
    )
    attribution = Attribution(utm=utm, likely_campaigns=[])

    app = Application(
        application_id=synth_application_id(email, phone_normalized, row_index),
        applicant=applicant,
        address=address,
        self_reported=self_reported,
        attribution=attribution,
        participant_match=ParticipantMatch(),
        entry_date=None,  # Source 'Date' column is empty for all rows
        import_batch=import_batch,
    )

    lead_tracking: Dict[str, Any] = {
        'source_file': 'EMPOWER-IMPACT LEADS_20260414.xlsx',
        'campaign_tag': CAMPAIGN_TAG,
        'fpl_percent': parse_fpl_percent(row.get('FPL %')),
        'impact_zip': parse_yes_flag(row.get('Impact ZIP?')),
        'called': parse_yes_flag(row.get('Called')),
        'notes': (str(row['Notes']).strip() if row.get('Notes') else None),
        'row_index': row_index,
    }
    return app, lead_tracking


def ingest(xlsx_path: Path, dry_run: bool, match_participants: bool) -> Dict[str, int]:
    rows = read_xlsx(xlsx_path)
    import_batch = f'IMPACT_Leads_20260414_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}'
    logger.info(f'Read {len(rows)} rows from {xlsx_path.name}; batch={import_batch}; dry_run={dry_run}')

    ingester: Optional[ApplicationIngester] = None if dry_run else IndexTolerantIngester()

    stats = {
        'total_rows': len(rows),
        'parsed': 0,
        'inserted': 0,
        'updated': 0,
        'skipped_error': 0,
        'matched_participants': 0,
        'match_by_email': 0,
        'match_by_phone': 0,
        'match_by_name_county': 0,
        'match_by_address_zip': 0,
        'has_called_flag': 0,
        'has_impact_zip': 0,
        'has_notes': 0,
    }

    for idx, row in enumerate(rows, start=1):
        try:
            app, lead_tracking = build_application(row, import_batch, idx)
        except Exception as exc:
            logger.error(f'Row {idx}: failed to build application: {exc}')
            stats['skipped_error'] += 1
            continue

        stats['parsed'] += 1
        if lead_tracking.get('called'):
            stats['has_called_flag'] += 1
        if lead_tracking.get('impact_zip'):
            stats['has_impact_zip'] += 1
        if lead_tracking.get('notes'):
            stats['has_notes'] += 1

        if match_participants and ingester is not None:
            app.participant_match = ingester.match_to_participant(app)
            if app.participant_match.participant_id:
                stats['matched_participants'] += 1
                method_key = f"match_by_{app.participant_match.match_method}"
                if method_key in stats:
                    stats[method_key] += 1

        if dry_run:
            continue

        doc = app.model_dump(by_alias=True, exclude={'id'})
        doc['lead_tracking'] = lead_tracking
        try:
            result = ingester.applications.update_one(
                {'application_id': app.application_id},
                {'$set': doc},
                upsert=True,
            )
            if result.upserted_id:
                stats['inserted'] += 1
            else:
                stats['updated'] += 1
        except Exception as exc:
            logger.error(f"Row {idx}: upsert failed for {app.application_id}: {exc}")
            stats['skipped_error'] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('xlsx_path', nargs='?', default=str(DEFAULT_XLSX),
                        help=f'Path to the leads xlsx (default: {DEFAULT_XLSX.name})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and report without writing to MongoDB')
    parser.add_argument('--no-match', action='store_true',
                        help='Skip participant matching')
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx_path)
    if not xlsx_path.exists():
        parser.error(f'File not found: {xlsx_path}')

    stats = ingest(xlsx_path, dry_run=args.dry_run, match_participants=not args.no_match)

    print('\nIMPACT Leads 20260414 Ingestion')
    print('=' * 50)
    for key, value in stats.items():
        print(f'  {key}: {value}')
    if args.dry_run:
        print('\n(dry-run: no documents written)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
