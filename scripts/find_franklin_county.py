#!/usr/bin/env python3
"""
Search for Franklin County demographic data
"""
import sys
sys.path.insert(0, '.')
import pymongo

client = pymongo.MongoClient('localhost', 27017)

print('Searching all databases for Franklin County data:')
print('=' * 80)

# Search all databases
for db_name in client.list_database_names():
    if db_name in ['admin', 'config', 'local']:
        continue

    db = client[db_name]

    # Look for Franklin in collection names
    franklin_colls = [c for c in db.list_collection_names() if 'franklin' in c.lower()]
    if franklin_colls:
        print(f'\n{db_name}:')
        for coll in franklin_colls:
            count = db[coll].count_documents({})
            print(f'  {coll}: {count:,} documents')
            # Show sample
            sample = db[coll].find_one({})
            if sample:
                print(f'    Sample fields: {list(sample.keys())[:15]}')

# Also check for Columbus or general residential data that might include Franklin
print('\n' + '=' * 80)
print('Checking for Columbus/Franklin references in collections:')
print('=' * 80)

for db_name in client.list_database_names():
    if db_name in ['admin', 'config', 'local', 'emailoctopus_db']:
        continue

    db = client[db_name]
    for coll_name in db.list_collection_names():
        # Sample documents mentioning Columbus or Franklin
        sample = db[coll_name].find_one({'$or': [
            {'city': {'$regex': 'COLUMBUS', '$options': 'i'}},
            {'parcel_city': {'$regex': 'COLUMBUS', '$options': 'i'}},
            {'service_city': {'$regex': 'COLUMBUS', '$options': 'i'}}
        ]})
        if sample:
            city_field = sample.get('city') or sample.get('parcel_city') or sample.get('service_city')
            count = db[coll_name].count_documents({'$or': [
                {'city': {'$regex': 'COLUMBUS', '$options': 'i'}},
                {'parcel_city': {'$regex': 'COLUMBUS', '$options': 'i'}},
                {'service_city': {'$regex': 'COLUMBUS', '$options': 'i'}}
            ]})
            print(f'\n{db_name}.{coll_name}:')
            print(f'  Found {count:,} Columbus records')
            print(f'  Sample city: {city_field}')

            # Show structure
            print(f'  Fields: {list(sample.keys())[:15]}')

print('\n' + '=' * 80)
print('Search complete')
