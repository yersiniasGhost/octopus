#!/usr/bin/env python3
"""
Ingest program applications from CSV into MongoDB.

This script:
1. Parses application CSV files (from GravityForms export)
2. Normalizes demographics data (income, age, phone)
3. Extracts UTM attribution from source URLs
4. Stores in 'applications' collection
5. Optionally matches to existing participants

Usage:
    python scripts/ingest_applications.py data/applications/APPLICANTS_sign-up-today-2025-09-03.csv

The applications represent conversion events - the ultimate outcome in the
campaign funnel. They're used to:
- Validate clustering effectiveness (which clusters convert?)
- Attribution analysis (which campaigns drove conversions?)
- Compare self-reported vs modeled demographics
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from pymongo import MongoClient
from pymongo.collection import Collection

from src.models.application import (
    Application, ApplicantIdentity, ApplicantAddress,
    SelfReportedDemographics, Attribution, UTMAttribution,
    ParticipantMatch
)
from src.utils.application_parsers import (
    normalize_phone, normalize_income, normalize_age,
    normalize_household_members, parse_utm_from_url,
    parse_housing_status, parse_boolean_field
)
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class ApplicationIngester:
    """Ingest applications from CSV into MongoDB."""

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "empower_development"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.applications: Collection = self.db.applications
        self.participants: Collection = self.db.participants

        # Create indexes
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes on applications collection."""
        self.applications.create_index("application_id", unique=True)
        self.applications.create_index("applicant.email")
        self.applications.create_index("applicant.phone")
        self.applications.create_index("address.county")
        self.applications.create_index("entry_date")
        self.applications.create_index("participant_match.participant_id")
        logger.info("Ensured indexes on applications collection")

    def parse_csv_row(self, row: Dict[str, str], import_batch: str) -> Optional[Application]:
        """Parse a single CSV row into an Application model."""
        try:
            # Skip if no entry ID
            entry_id = row.get('Entry Id', '').strip()
            if not entry_id:
                return None

            # Parse identity
            phone_raw = row.get('Phone', '')
            phone_normalized = normalize_phone(phone_raw)

            applicant = ApplicantIdentity(
                first_name=row.get('Name (First)', '').strip() or None,
                middle_name=row.get('Name (Middle)', '').strip() or None,
                last_name=row.get('Name (Last)', '').strip() or None,
                email=row.get('Email', '').strip().lower() or None,
                phone=phone_normalized,
                phone_raw=phone_raw.strip() or None
            )

            # Parse address - use the cleaner "City" fields which have parsed city/state
            address = ApplicantAddress(
                street=row.get('Address (Street Address)', '').strip() or None,
                city=row.get('City (City)', '').strip() or None,
                state=row.get('City (State / Province)', '').strip() or None,
                zip=row.get('Zip (ZIP / Postal Code)', '').strip() or None,
                county=row.get('County', '').strip() or None
            )

            # Parse self-reported demographics
            age, age_raw = normalize_age(row.get('What is your age?'))
            income, income_raw = normalize_income(row.get('What is your annual household income?'))
            household_members = normalize_household_members(
                row.get('How many household members reside in your residence?')
            )
            housing_status = parse_housing_status(row.get('Rent'), row.get('Own'))

            self_reported = SelfReportedDemographics(
                age=age,
                age_raw=age_raw,
                household_income=income,
                household_income_raw=income_raw,
                household_members=household_members,
                housing_status=housing_status,
                needs_housing_help=parse_boolean_field(
                    row.get('I need help with rent, mortgage, or finding new housing')
                ),
                has_dependent_children=parse_boolean_field(
                    row.get('I have dependent children living in the household')
                ),
                pre_1978_home=parse_boolean_field(row.get('My home was built before 1978'))
            )

            # Parse UTM attribution
            url_with_utm = row.get('URL + UTM', '') or row.get('Source Url', '')
            utm_data = parse_utm_from_url(url_with_utm)

            utm_attribution = UTMAttribution(
                utm_source=utm_data['utm_source'],
                utm_medium=utm_data['utm_medium'],
                utm_campaign=utm_data['utm_campaign'],
                utm_id=utm_data['utm_id'],
                utm_content=utm_data['utm_content'],
                source_url=utm_data['source_url']
            )

            attribution = Attribution(utm=utm_attribution, likely_campaigns=[])

            # Parse entry date
            entry_date = None
            date_str = row.get('Entry Date', '').strip()
            if date_str:
                try:
                    entry_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    logger.warning(f"Could not parse date: {date_str}")

            return Application(
                application_id=entry_id,
                applicant=applicant,
                address=address,
                self_reported=self_reported,
                attribution=attribution,
                participant_match=ParticipantMatch(),
                entry_date=entry_date,
                import_batch=import_batch
            )

        except Exception as e:
            logger.error(f"Error parsing row {row.get('Entry Id', 'unknown')}: {e}")
            return None

    def match_to_participant(self, app: Application) -> ParticipantMatch:
        """Attempt to match application to existing participant.

        Match priority:
        1. Email (highest confidence)
        2. Phone
        3. Name + County (via demographics.customer_name)
        4. Address + ZIP
        """
        import re
        match = ParticipantMatch()

        # Strategy 1: Email match (highest confidence)
        if app.applicant.email:
            participant = self.participants.find_one({
                'email': app.applicant.email
            }, {'participant_id': 1})

            if participant:
                match.participant_id = participant['participant_id']
                match.match_method = 'email'
                match.match_confidence = 0.95
                match.matched_at = datetime.utcnow()
                return match

        # Strategy 2: Phone match
        if app.applicant.phone:
            participant = self.participants.find_one({
                'phone': app.applicant.phone
            }, {'participant_id': 1})

            if participant:
                match.participant_id = participant['participant_id']
                match.match_method = 'phone'
                match.match_confidence = 0.85
                match.matched_at = datetime.utcnow()
                return match

        # Strategy 3: Name + County match (via demographics.customer_name)
        first = app.applicant.first_name
        last = app.applicant.last_name
        county = app.address.county

        if first and last and county:
            # Match "LAST, FIRST" or "FIRST LAST" patterns in customer_name
            name_pattern = f".*{re.escape(first)}.*{re.escape(last)}.*|.*{re.escape(last)}.*{re.escape(first)}.*"
            participant = self.participants.find_one({
                'demographics.customer_name': {'$regex': name_pattern, '$options': 'i'},
                'address.county': {'$regex': re.escape(county), '$options': 'i'}
            }, {'participant_id': 1})

            if participant:
                match.participant_id = participant['participant_id']
                match.match_method = 'name_county'
                match.match_confidence = 0.80
                match.matched_at = datetime.utcnow()
                return match

        # Strategy 4: Address + ZIP match
        street = app.address.street
        zipcode = app.address.zip

        if street and zipcode:
            # Extract house number for matching
            house_match = re.match(r'^(\d+)', street)
            if house_match:
                house_num = house_match.group(1)
                # Match same house number and ZIP
                participant = self.participants.find_one({
                    'address.street': {'$regex': f'^{house_num}\\b', '$options': 'i'},
                    'address.zip': zipcode
                }, {'participant_id': 1})

                if participant:
                    match.participant_id = participant['participant_id']
                    match.match_method = 'address_zip'
                    match.match_confidence = 0.75
                    match.matched_at = datetime.utcnow()
                    return match

        return match

    def ingest_csv(self, csv_path: str, match_participants: bool = True) -> Dict:
        """Ingest applications from CSV file.

        Args:
            csv_path: Path to the CSV file
            match_participants: Whether to attempt participant matching

        Returns:
            Dict with ingestion statistics
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        import_batch = f"{path.stem}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting ingestion: {path.name}, batch: {import_batch}")

        stats = {
            'total_rows': 0,
            'parsed': 0,
            'inserted': 0,
            'skipped_duplicate': 0,
            'skipped_error': 0,
            'matched_participants': 0,
            'match_by_email': 0,
            'match_by_phone': 0,
            'match_by_name_county': 0,
            'match_by_address_zip': 0,
            'has_utm': 0
        }

        # Read CSV with UTF-8 BOM handling
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row in reader:
                stats['total_rows'] += 1

                app = self.parse_csv_row(row, import_batch)
                if not app:
                    stats['skipped_error'] += 1
                    continue

                stats['parsed'] += 1

                # Track UTM presence
                if app.attribution.utm and app.attribution.utm.utm_source:
                    stats['has_utm'] += 1

                # Match to participant
                if match_participants:
                    app.participant_match = self.match_to_participant(app)
                    if app.participant_match.participant_id:
                        stats['matched_participants'] += 1
                        # Track match method
                        method = app.participant_match.match_method
                        if method == 'email':
                            stats['match_by_email'] += 1
                        elif method == 'phone':
                            stats['match_by_phone'] += 1
                        elif method == 'name_county':
                            stats['match_by_name_county'] += 1
                        elif method == 'address_zip':
                            stats['match_by_address_zip'] += 1

                # Upsert to MongoDB
                try:
                    result = self.applications.update_one(
                        {'application_id': app.application_id},
                        {'$set': app.model_dump(by_alias=True, exclude={'id'})},
                        upsert=True
                    )
                    if result.upserted_id:
                        stats['inserted'] += 1
                    else:
                        stats['skipped_duplicate'] += 1
                except Exception as e:
                    logger.error(f"Error inserting application {app.application_id}: {e}")
                    stats['skipped_error'] += 1

        logger.info(f"Ingestion complete: {stats}")
        return stats

    def print_summary(self):
        """Print summary of applications collection."""
        total = self.applications.count_documents({})
        matched = self.applications.count_documents({'participant_match.participant_id': {'$ne': None}})
        has_utm = self.applications.count_documents({'attribution.utm.utm_source': {'$ne': None}})

        # UTM medium distribution
        pipeline = [
            {'$match': {'attribution.utm.utm_medium': {'$ne': None}}},
            {'$group': {'_id': '$attribution.utm.utm_medium', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        medium_dist = list(self.applications.aggregate(pipeline))

        # County distribution
        pipeline = [
            {'$match': {'address.county': {'$ne': None}}},
            {'$group': {'_id': '$address.county', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]
        county_dist = list(self.applications.aggregate(pipeline))

        # Date range
        pipeline = [
            {'$group': {
                '_id': None,
                'min_date': {'$min': '$entry_date'},
                'max_date': {'$max': '$entry_date'}
            }}
        ]
        date_range = list(self.applications.aggregate(pipeline))

        # Match method distribution
        pipeline = [
            {'$match': {'participant_match.match_method': {'$ne': None}}},
            {'$group': {'_id': '$participant_match.match_method', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        match_method_dist = list(self.applications.aggregate(pipeline))

        print("\n" + "=" * 60)
        print("APPLICATIONS COLLECTION SUMMARY")
        print("=" * 60)
        print(f"\nTotal applications: {total}")
        print(f"Matched to participants: {matched} ({100 * matched / total:.1f}%)" if total else "")
        print(f"Has UTM attribution: {has_utm} ({100 * has_utm / total:.1f}%)" if total else "")

        if date_range and date_range[0]['min_date']:
            print(f"\nDate range: {date_range[0]['min_date']} to {date_range[0]['max_date']}")

        print("\nMatch Method Distribution:")
        for item in match_method_dist:
            print(f"  {item['_id']}: {item['count']}")
        unmatched = total - matched
        if unmatched > 0:
            print(f"  unmatched: {unmatched}")

        print("\nUTM Medium Distribution:")
        for item in medium_dist:
            print(f"  {item['_id']}: {item['count']}")

        print("\nTop 10 Counties:")
        for item in county_dist:
            print(f"  {item['_id']}: {item['count']}")

        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Ingest applications from CSV')
    parser.add_argument('csv_path', help='Path to the applications CSV file')
    parser.add_argument('--no-match', action='store_true',
                        help='Skip participant matching')
    parser.add_argument('--summary-only', action='store_true',
                        help='Only print collection summary, skip ingestion')

    args = parser.parse_args()

    ingester = ApplicationIngester()

    if args.summary_only:
        ingester.print_summary()
        return

    stats = ingester.ingest_csv(args.csv_path, match_participants=not args.no_match)

    print("\nIngestion Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    ingester.print_summary()


if __name__ == '__main__':
    main()
