#!/usr/bin/env python3
"""
Find which counties have matching participants between EmailOctopus and Demographics
"""
import sys
sys.path.insert(0, '.')
import pymongo
import math

client = pymongo.MongoClient('localhost', 27017)
octopus_db = client['emailoctopus_db']
demo_db = client['empower_development']

print('Analyzing County Coverage:')
print('=' * 80)

# Get all demographic/residential collections
demo_collections = [
    ('CuyahogaCountyResidential', 'parcel_zip'),
    ('OttawaResidential', 'zip_code')
]

for coll_name, zip_field in demo_collections:
    print(f'\n{coll_name}:')
    print('-' * 80)

    # Get ZIP codes from this collection
    zip_docs = list(demo_db[coll_name].find({zip_field: {'$exists': True}}, {zip_field: 1}).limit(1000))

    county_zips = set()
    for doc in zip_docs:
        zip_val = doc.get(zip_field)
        if zip_val and not (isinstance(zip_val, float) and math.isnan(zip_val)):
            # Convert to string, handle floats
            try:
                if isinstance(zip_val, (int, float)):
                    zip_str = str(int(zip_val))
                else:
                    zip_str = str(zip_val).split('.')[0]
                county_zips.add(zip_str)
            except:
                pass

    print(f'  ZIP codes in county data: {len(county_zips)}')
    print(f'  Sample ZIPs: {", ".join(sorted(list(county_zips)[:10]))}')

    # Check for matches in EmailOctopus
    total_matches = 0
    matching_zips = {}

    for zip_code in county_zips:
        count = octopus_db['participants'].count_documents({'fields.ZIP': zip_code})
        if count > 0:
            matching_zips[zip_code] = count
            total_matches += count

    if matching_zips:
        print(f'\n  ✓ MATCHES FOUND!')
        print(f'  Matching ZIPs: {len(matching_zips)}')
        print(f'  Total participants: {total_matches:,}')
        print(f'\n  Top matching ZIPs:')
        for zip_code in sorted(matching_zips.keys(), key=lambda x: matching_zips[x], reverse=True)[:10]:
            print(f'    {zip_code}: {matching_zips[zip_code]:,} participants')
    else:
        print(f'  ✗ No participants found in this county')

print('\n' + '=' * 80)
print('Summary: Search complete')
