#!/usr/bin/env python3
"""
Test address matching between EmailOctopus participants and Franklin County demographics
"""
import sys
sys.path.insert(0, '.')
import pymongo

# Local EmailOctopus database
local_client = pymongo.MongoClient('localhost', 27017)
local_db = local_client['emailoctopus_db']

# Remote demographics database
remote_client = pymongo.MongoClient('192.168.1.156', 27017)
remote_db = remote_client['empower_development']

print('Testing EmailOctopus → Franklin County Matching:')
print('=' * 80)

# Get 10 Columbus participants from EmailOctopus
participants = list(local_db['participants'].find({
    'fields.City': 'COLUMBUS'
}, {
    'email_address': 1,
    'fields.Address': 1,
    'fields.City': 1,
    'fields.ZIP': 1
}).limit(10))

matches = 0
total = len(participants)

for i, p in enumerate(participants, 1):
    email = p.get('email_address')
    fields = p.get('fields', {})
    eo_address = fields.get('Address', '').upper()
    eo_zip = fields.get('ZIP', '')
    eo_city = fields.get('City', '')

    print(f'\n[{i}/{total}] EmailOctopus Contact:')
    print(f'  Email: {email}')
    print(f'  Address: {eo_address}')
    print(f'  City: {eo_city}')
    print(f'  ZIP: {eo_zip}')

    if not eo_address or not eo_zip:
        print('  ✗ Missing address or ZIP')
        continue

    # Clean ZIP code
    eo_zip_clean = str(eo_zip).split('.')[0].split('-')[0]

    try:
        eo_zip_int = int(eo_zip_clean)
    except:
        print(f'  ✗ Invalid ZIP: {eo_zip}')
        continue

    # Find matching parcel in Franklin County Residential
    parcel = remote_db['FranklinCountyResidential'].find_one({
        'address': eo_address,
        'parcel_zip': eo_zip_int
    })

    if parcel:
        parcel_id = parcel.get('parcel_id')
        print(f'  ✓ PARCEL FOUND: {parcel_id}')

        # Lookup demographics
        demo = remote_db['FranklinCountyDemographic'].find_one({
            'parcel_id': parcel_id
        })

        if demo:
            customer_name = demo.get('customer_name', '')
            print(f'  ✓ DEMOGRAPHICS FOUND!')
            print(f'    Customer Name: {customer_name}')

            # Parse name
            if customer_name:
                parts = customer_name.split()
                if len(parts) >= 2:
                    first_name = parts[0].title()
                    last_name = ' '.join(parts[1:]).title()
                    print(f'    → FirstName: {first_name}')
                    print(f'    → LastName: {last_name}')
                    matches += 1
                else:
                    print(f'    ⚠ Cannot parse name: {customer_name}')
        else:
            print(f'  ✗ No demographics for parcel_id {parcel_id}')
    else:
        print(f'  ✗ No matching parcel found')

print(f'\n' + '=' * 80)
print(f'Match Rate: {matches}/{total} ({matches/total*100:.1f}%)')
