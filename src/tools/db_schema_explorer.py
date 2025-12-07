#!/usr/bin/env python3
"""
Database Schema Explorer - Diagnostic tool for understanding MongoDB collections.

Explores participants, demographic, and residential collections to identify
available fields for clustering aggregation.

Usage:
    python src/tools/db_schema_explorer.py
"""
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tools.mongo import Mongo


def explore_collections():
    """List all collections and categorize them."""
    mongo = Mongo()
    db = mongo.database

    collections = db.list_collection_names()

    categories = defaultdict(list)
    for name in sorted(collections):
        if 'Demographic' in name:
            categories['demographic'].append(name)
        elif 'Residential' in name:
            categories['residential'].append(name)
        elif name in ['participants', 'campaigns']:
            categories['core'].append(name)
        else:
            categories['other'].append(name)

    print("=" * 60)
    print("DATABASE COLLECTIONS")
    print("=" * 60)

    for category, names in categories.items():
        print(f"\n{category.upper()} ({len(names)}):")
        for name in names:
            count = db[name].count_documents({})
            print(f"  - {name}: {count:,} documents")

    return categories


def sample_collection_fields(db, collection_name: str, sample_size: int = 5):
    """Get all field names from a collection sample."""
    collection = db[collection_name]

    # Get sample documents
    samples = list(collection.find().limit(sample_size))

    # Collect all unique fields
    all_fields = set()
    for doc in samples:
        all_fields.update(doc.keys())

    return sorted(all_fields), samples


def explore_demographic_fields():
    """Explore demographic collection fields, especially age-related."""
    mongo = Mongo()
    db = mongo.database

    collections = db.list_collection_names()
    demographic_collections = [c for c in collections if 'Demographic' in c]

    print("\n" + "=" * 60)
    print("DEMOGRAPHIC COLLECTION FIELDS")
    print("=" * 60)

    # Sample from first demographic collection
    if demographic_collections:
        sample_coll = demographic_collections[0]
        fields, samples = sample_collection_fields(db, sample_coll)

        print(f"\nFields from {sample_coll}:")
        for field in fields:
            # Get sample value
            sample_val = samples[0].get(field) if samples else None
            val_type = type(sample_val).__name__
            print(f"  - {field}: {val_type} (e.g., {repr(sample_val)[:50]})")

        # Look for age-related fields
        print("\n  Age-related fields found:")
        age_fields = [f for f in fields if 'age' in f.lower()]
        for f in age_fields:
            print(f"    → {f}")


def explore_residential_fields():
    """Explore residential collection fields."""
    mongo = Mongo()
    db = mongo.database

    collections = db.list_collection_names()
    residential_collections = [c for c in collections if 'Residential' in c]

    print("\n" + "=" * 60)
    print("RESIDENTIAL COLLECTION FIELDS")
    print("=" * 60)

    if residential_collections:
        sample_coll = residential_collections[0]
        fields, samples = sample_collection_fields(db, sample_coll)

        print(f"\nFields from {sample_coll}:")
        for field in fields:
            sample_val = samples[0].get(field) if samples else None
            val_type = type(sample_val).__name__
            print(f"  - {field}: {val_type} (e.g., {repr(sample_val)[:50]})")


def explore_participants():
    """Explore participant collection and reference integrity."""
    mongo = Mongo()
    db = mongo.database

    print("\n" + "=" * 60)
    print("PARTICIPANTS COLLECTION")
    print("=" * 60)

    participants = db['participants']
    total = participants.count_documents({})

    # Check reference integrity
    with_residence = participants.count_documents({'residence_ref': {'$exists': True, '$ne': None}})
    with_demographic = participants.count_documents({'demographic_ref': {'$exists': True, '$ne': None}})

    # Count engagements
    pipeline = [
        {'$project': {'engagement_count': {'$size': {'$ifNull': ['$engagements', []]}}}},
        {'$group': {
            '_id': None,
            'total_engagements': {'$sum': '$engagement_count'},
            'avg_engagements': {'$avg': '$engagement_count'},
            'max_engagements': {'$max': '$engagement_count'}
        }}
    ]
    engagement_stats = list(participants.aggregate(pipeline))

    print(f"\nTotal participants: {total:,}")
    print(f"With residence_ref: {with_residence:,} ({with_residence/total*100:.1f}%)")
    print(f"With demographic_ref: {with_demographic:,} ({with_demographic/total*100:.1f}%)")
    print(f"Missing residence_ref: {total - with_residence:,}")
    print(f"Missing demographic_ref: {total - with_demographic:,}")

    if engagement_stats:
        stats = engagement_stats[0]
        print(f"\nEngagement statistics:")
        print(f"  Total engagements: {stats.get('total_engagements', 0):,}")
        print(f"  Avg per participant: {stats.get('avg_engagements', 0):.1f}")
        print(f"  Max per participant: {stats.get('max_engagements', 0)}")

    # Sample participant structure
    sample = participants.find_one()
    if sample:
        print("\nSample participant fields:")
        for key in sorted(sample.keys()):
            val = sample[key]
            if key == 'engagements' and isinstance(val, list):
                print(f"  - {key}: list[{len(val)}]")
                if val:
                    print(f"      First engagement keys: {list(val[0].keys())}")
            elif key in ['residence_ref', 'demographic_ref'] and val:
                print(f"  - {key}: {list(val.keys()) if isinstance(val, dict) else type(val).__name__}")
            else:
                print(f"  - {key}: {type(val).__name__}")


def explore_campaigns():
    """Explore campaign types."""
    mongo = Mongo()
    db = mongo.database

    print("\n" + "=" * 60)
    print("CAMPAIGNS COLLECTION")
    print("=" * 60)

    campaigns = db['campaigns']

    # Count by type
    pipeline = [
        {'$group': {'_id': '$campaign_type', 'count': {'$sum': 1}}}
    ]
    type_counts = list(campaigns.aggregate(pipeline))

    print("\nCampaign types:")
    for item in type_counts:
        print(f"  - {item['_id']}: {item['count']}")

    # Sample campaign
    sample = campaigns.find_one()
    if sample:
        print("\nSample campaign fields:")
        for key in sorted(sample.keys()):
            print(f"  - {key}")


def main():
    print("Database Schema Explorer")
    print("Exploring MongoDB collections for clustering aggregation...")

    explore_collections()
    explore_participants()
    explore_campaigns()
    explore_demographic_fields()
    explore_residential_fields()

    print("\n" + "=" * 60)
    print("EXPLORATION COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    main()
