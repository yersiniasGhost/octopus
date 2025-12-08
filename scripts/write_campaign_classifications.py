#!/usr/bin/env python3
"""
Write campaign message_types classifications to the database.

Maps campaign IDs to their message_types based on template classification,
then updates the campaigns collection in MongoDB.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient
from src.utils.envvars import EnvVars


def load_classifications():
    """Load classification data from JSON files."""
    base_dir = project_root / 'data' / 'exports' / 'campaign_messages'

    # Load templates with campaign IDs
    templates_file = base_dir / '_templates_for_classification.json'
    with open(templates_file, 'r') as f:
        templates_data = json.load(f)

    # Load classifications
    classifications_file = base_dir / '_classifications.json'
    with open(classifications_file, 'r') as f:
        classifications_data = json.load(f)

    return templates_data, classifications_data


def build_campaign_id_mapping(templates_data, classifications_data):
    """Build mapping from campaign_id to message_types."""
    # Create template name -> message_types mapping
    template_to_types = {}
    for classification in classifications_data['template_classifications']:
        template_name = classification['template_name']
        message_types = classification['message_types']
        template_to_types[template_name] = message_types

    # Build campaign_id -> message_types mapping
    campaign_id_to_types = {}
    for template in templates_data['templates']:
        template_name = template['template_name']
        campaign_ids = template['campaign_ids']
        message_types = template_to_types.get(template_name, [])

        for campaign_id in campaign_ids:
            campaign_id_to_types[campaign_id] = message_types

    return campaign_id_to_types


def update_database(campaign_id_to_types, dry_run=True):
    """Update campaigns in MongoDB with message_types."""
    env = EnvVars()
    client = MongoClient(env.get_env('MONGODB_URI'))
    db = client['campaign_data']  # Correct database name
    campaigns_collection = db.campaigns

    print(f"\n{'DRY RUN - ' if dry_run else ''}Updating {len(campaign_id_to_types)} campaigns...")

    updated = 0
    not_found = 0
    errors = 0

    for campaign_id, message_types in campaign_id_to_types.items():
        try:
            if dry_run:
                # Check if campaign exists
                existing = campaigns_collection.find_one({'campaign_id': campaign_id})
                if existing:
                    print(f"  [DRY RUN] Would update {campaign_id}: {message_types}")
                    updated += 1
                else:
                    print(f"  [DRY RUN] Campaign not in DB: {campaign_id}")
                    not_found += 1
            else:
                # Actually update
                result = campaigns_collection.update_one(
                    {'campaign_id': campaign_id},
                    {'$set': {
                        'message_types': message_types,
                        'synced_at': datetime.now()
                    }}
                )
                if result.matched_count > 0:
                    print(f"  ✅ Updated {campaign_id}: {message_types}")
                    updated += 1
                else:
                    print(f"  ⚠️  Campaign not found: {campaign_id}")
                    not_found += 1

        except Exception as e:
            print(f"  ❌ Error updating {campaign_id}: {e}")
            errors += 1

    print(f"\nSummary:")
    print(f"  Updated: {updated}")
    print(f"  Not found in DB: {not_found}")
    print(f"  Errors: {errors}")

    return updated, not_found, errors


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Write campaign classifications to database')
    parser.add_argument('--execute', action='store_true', help='Actually write to database (default is dry run)')
    args = parser.parse_args()

    print("=" * 60)
    print("Campaign Classification Database Update")
    print("=" * 60)

    # Load data
    print("\nLoading classification data...")
    templates_data, classifications_data = load_classifications()

    # Build mapping
    print("Building campaign ID -> message_types mapping...")
    campaign_id_to_types = build_campaign_id_mapping(templates_data, classifications_data)

    print(f"\nTotal campaigns to classify: {len(campaign_id_to_types)}")

    # Show classification summary
    print("\nClassification Summary:")
    type_counts = {}
    for types in campaign_id_to_types.values():
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1

    for type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {type_name}: {count} campaigns")

    # Save mapping to JSON for reference
    output_file = project_root / 'data' / 'exports' / 'campaign_messages' / '_campaign_id_to_types.json'
    with open(output_file, 'w') as f:
        json.dump(campaign_id_to_types, f, indent=2)
    print(f"\nSaved mapping to: {output_file}")

    # Update database
    dry_run = not args.execute
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("Run with --execute to actually update the database")
        print("=" * 60)

    update_database(campaign_id_to_types, dry_run=dry_run)


if __name__ == '__main__':
    main()
