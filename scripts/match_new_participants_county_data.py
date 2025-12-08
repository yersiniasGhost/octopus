#!/usr/bin/env python3
"""
Match new text campaign participants to county residential/demographic data.

Uses the existing ResidenceMatcher tool with 8-strategy matching logic to find
matching records in empower_development database county collections.

Reads from: campaign_data.participants (phone-based participant_ids)
Writes to: campaign_data.participants (updates linkage, demographics, residence)

Usage:
    python scripts/match_new_participants_county_data.py [--dry-run] [--limit N]
"""
import argparse
import re
from datetime import datetime
from pymongo import MongoClient
from collections import defaultdict
import sys

# Add project root to path
sys.path.insert(0, '/home/yersinia/devel/octopus')

from src.tools.residence_matcher import ResidenceMatcher
from src.models.campaign_data import Demographics, Residence


# Zip code to county mapping
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
    '43123': 'FranklinCounty', '43125': 'FranklinCounty',
    # Allen County (Lima area)
    '45801': 'AllenCounty', '45802': 'AllenCounty', '45804': 'AllenCounty',
    '45805': 'AllenCounty', '45806': 'AllenCounty', '45807': 'AllenCounty',
    '45887': 'AllenCounty',
    # Fayette County
    '43160': 'FayetteCounty',
    # Marion County
    '43302': 'MarionCounty', '43334': 'MarionCounty',
    # Richland County
    '44903': 'RichlandCounty', '44904': 'RichlandCounty', '44905': 'RichlandCounty',
    '44906': 'RichlandCounty', '44907': 'RichlandCounty', '44875': 'RichlandCounty',
    # Lawrence County
    '45638': 'LawrenceCounty', '45669': 'LawrenceCounty',
    # Muskingum County
    '43701': 'MuskingumCounty', '43731': 'MuskingumCounty',
    # Athens County
    '45701': 'AthensCounty',
    # Belmont County
    '43906': 'BelmontCounty', '43947': 'BelmontCounty',
    # Coshocton County
    '43812': 'CoshoctonCounty',
    # Guernsey County
    '43725': 'GuernseyCounty',
    # Harrison County
    '43907': 'HarrisonCounty',
    # Morgan County
    '43756': 'MorganCounty',
    # Morrow County
    '43338': 'MorrowCounty',
    # Holmes County
    '44654': 'HolmesCounty',
}


def infer_county(address_doc: dict) -> str:
    """Infer county from participant address data"""
    # Check if county already set
    county = address_doc.get('county')
    if county and county != 'Unknown':
        # Ensure it ends with 'County'
        if not county.endswith('County'):
            county = county + 'County'
        return county.replace(' ', '')

    # Try to infer from zip code
    zipcode = address_doc.get('zip')
    if zipcode:
        zip5 = str(zipcode).strip()[:5]
        if zip5 in ZIP_TO_COUNTY:
            return ZIP_TO_COUNTY[zip5]

    return None


def get_full_records(county_db, county: str, parcel_id: str) -> tuple:
    """Fetch full residential and demographic records for a parcel"""
    residential_coll = f"{county}Residential"
    demographic_coll = f"{county}Demographic"

    residential_doc = None
    demographic_doc = None

    if residential_coll in county_db.list_collection_names():
        residential_doc = county_db[residential_coll].find_one({'parcel_id': parcel_id})

    if demographic_coll in county_db.list_collection_names():
        demographic_doc = county_db[demographic_coll].find_one({'parcel_id': parcel_id})

    return residential_doc, demographic_doc


def main():
    parser = argparse.ArgumentParser(description='Match new participants to county data')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--limit', type=int, default=0, help='Limit participants to process (0=all)')
    args = parser.parse_args()

    print("=" * 80)
    print("MATCHING NEW PARTICIPANTS TO COUNTY DATA")
    print("=" * 80)

    # Connect to databases
    client = MongoClient('localhost', 27017)
    campaign_db = client['campaign_data']
    county_db = client['empower_development']

    # Find new participants (phone-based participant_id = 10 digits)
    query = {'participant_id': {'$regex': r'^\d{10}$'}}

    new_participants = list(campaign_db.participants.find(query))
    print(f"\n📊 Found {len(new_participants)} new text-only participants")

    if args.limit > 0:
        new_participants = new_participants[:args.limit]
        print(f"   Processing first {args.limit} only")

    # Statistics
    stats = {
        'total': len(new_participants),
        'matched': 0,
        'matched_residential': 0,
        'matched_demographic': 0,
        'no_county': 0,
        'no_match': 0,
        'errors': 0,
        'by_method': defaultdict(int),
        'by_county': defaultdict(int),
    }

    print(f"\n{'📋 DRY-RUN MODE' if args.dry_run else '💾 LIVE MODE'}")
    print("-" * 60)

    for i, participant in enumerate(new_participants, 1):
        pid = participant['participant_id']
        address = participant.get('address', {})

        # Infer county
        county = infer_county(address)
        if not county:
            stats['no_county'] += 1
            if i <= 10:
                print(f"  [{i}] {pid}: No county - zip={address.get('zip')}")
            continue

        stats['by_county'][county] += 1

        # Get contact info for matching
        phone = participant.get('phone')
        email = participant.get('email')
        street = address.get('street')
        zipcode = address.get('zip')

        # Parse name from any source campaigns' exposures if available
        first_name = None
        last_name = None

        try:
            # Use ResidenceMatcher
            matcher = ResidenceMatcher(county_db, county)
            residence_ref, demographic_ref, match_method = matcher.match(
                phone=phone,
                email=email,
                first_name=first_name,
                last_name=last_name,
                address=street,
                zipcode=zipcode
            )

            if residence_ref or demographic_ref:
                stats['matched'] += 1
                stats['by_method'][match_method] += 1

                # Get parcel_id from whichever ref we have
                parcel_id = None
                if residence_ref:
                    parcel_id = residence_ref.parcel_id
                    stats['matched_residential'] += 1
                if demographic_ref:
                    parcel_id = parcel_id or demographic_ref.parcel_id
                    stats['matched_demographic'] += 1

                if i <= 20:
                    print(f"  [{i}] {pid}: ✅ {match_method} → {parcel_id[:20] if parcel_id else 'N/A'}...")

                if not args.dry_run and parcel_id:
                    # Fetch full records
                    res_doc, demo_doc = get_full_records(county_db, county, parcel_id)

                    # Build update
                    update = {
                        'linkage.parcel_id': parcel_id,
                        'linkage.county_key': county,
                        'linkage.method': match_method,
                        'linkage.confidence': 0.9 if 'exact' in match_method or match_method in ['email', 'phone'] else 0.7,
                        'linkage.matched_at': datetime.utcnow(),
                        'address.county': county,
                        'updated_at': datetime.utcnow(),
                    }

                    # Add residential data
                    if res_doc:
                        residence = Residence.from_county_record(res_doc)
                        update['residence'] = residence.model_dump()
                        update['data_quality.has_residence'] = True

                    # Add demographic data
                    if demo_doc:
                        demographics = Demographics.from_county_record(demo_doc)
                        update['demographics'] = demographics.model_dump()
                        update['data_quality.has_demographics'] = True

                    # Update completeness score
                    completeness = 0.25  # Base
                    if res_doc:
                        completeness += 0.25
                    if demo_doc:
                        completeness += 0.25
                    completeness += 0.25  # Has engagement
                    update['data_quality.completeness_score'] = completeness
                    update['data_quality.analysis_ready'] = completeness >= 0.75

                    # Apply update
                    campaign_db.participants.update_one(
                        {'_id': participant['_id']},
                        {'$set': update}
                    )
            else:
                stats['no_match'] += 1
                if i <= 10:
                    print(f"  [{i}] {pid}: ❌ No match in {county}")

        except Exception as e:
            stats['errors'] += 1
            print(f"  [{i}] {pid}: ⚠️ Error: {e}")

        # Progress update
        if i % 50 == 0:
            print(f"  ... processed {i}/{len(new_participants)}")

    # Summary
    print("\n" + "=" * 80)
    print("📊 MATCHING SUMMARY")
    print("=" * 80)

    print(f"\n  Total processed: {stats['total']}")
    print(f"  Matched:         {stats['matched']} ({stats['matched']/stats['total']*100:.1f}%)")
    print(f"    - Residential: {stats['matched_residential']}")
    print(f"    - Demographic: {stats['matched_demographic']}")
    print(f"  No county:       {stats['no_county']}")
    print(f"  No match:        {stats['no_match']}")
    print(f"  Errors:          {stats['errors']}")

    print("\n  By Match Method:")
    for method, count in sorted(stats['by_method'].items(), key=lambda x: -x[1]):
        print(f"    {method}: {count}")

    print("\n  By County:")
    for county, count in sorted(stats['by_county'].items(), key=lambda x: -x[1]):
        print(f"    {county}: {count}")

    if args.dry_run:
        print("\n  Run without --dry-run to apply updates")

    client.close()
    print("\n✅ Done!")

    return 0


if __name__ == '__main__':
    sys.exit(main())
