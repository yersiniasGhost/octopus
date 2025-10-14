#!/usr/bin/env python3
"""
Test EmailOctopus address matching to Parcel and Demographics
"""
import sys
sys.path.insert(0, '.')

import pymongo
from src.tools.emailoctopus_client import EmailOctopusClient

# Get EmailOctopus data
client = EmailOctopusClient()
campaigns = client.get_campaigns(limit=1)
campaign_id = campaigns['data'][0]['id']

result = client.get_campaign_report_contacts(campaign_id, 'sent', limit=5)

# Connect to demographics
mongo_client = pymongo.MongoClient('localhost', 27017)
db = mongo_client['empower_development']

print('Testing EmailOctopus → Parcel → Demographics Matching:')
print('=' * 80)

matches = 0
total = 0

for item in result.get('data', [])[:5]:
    total += 1
    contact = item.get('contact', {})
    email = contact.get('email_address')
    fields = contact.get('fields', {})

    eo_address = fields.get('Address', '')
    eo_zip = fields.get('ZIP', '')
    eo_city = fields.get('City', '')

    print(f'\n[{total}] EmailOctopus Contact:')
    print(f'  Email: {email}')
    print(f'  Address: {eo_address}')
    print(f'  City: {eo_city}')
    print(f'  ZIP: {eo_zip}')

    # Normalize ZIP (remove decimals if present)
    if eo_zip:
        eo_zip_clean = str(eo_zip).split('.')[0]

        # Try to find matching parcel - exact address match
        parcel = db['CuyahogaCountyResidential'].find_one({
            'address': eo_address.upper(),
            'parcel_zip': {'$in': [eo_zip_clean, f'{eo_zip_clean}.0', float(eo_zip_clean)]}
        })

        if parcel:
            print(f'  ✓ PARCEL FOUND: {parcel.get("parcel_id")}')

            # Lookup demographics
            demo = db['CuyahogaCountyDemographic'].find_one({'parcel_id': parcel.get('parcel_id')})
            if demo:
                customer_name = demo.get('customer name', '')
                print(f'  ✓ DEMOGRAPHICS FOUND!')
                print(f'    Customer Name: {customer_name}')

                # Parse name
                parts = customer_name.split()
                if len(parts) >= 2:
                    first_name = parts[0].title()
                    last_name = ' '.join(parts[1:]).title()
                    print(f'    → FirstName: {first_name}')
                    print(f'    → LastName: {last_name}')
                    matches += 1
            else:
                print(f'  ✗ No demographics found for parcel_id {parcel.get("parcel_id")}')
        else:
            print(f'  ✗ No matching parcel found')

print(f'\n' + '=' * 80)
print(f'Match Rate: {matches}/{total} ({matches/total*100:.1f}%)')
