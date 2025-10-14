#!/usr/bin/env python3
"""
Test direct email matching between EmailOctopus and Franklin County demographics
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

print('Direct Email Matching Test:')
print('=' * 80)

# Get all Columbus participants
total_columbus = local_db['participants'].count_documents({'fields.City': 'COLUMBUS'})
print(f'Total Columbus EmailOctopus participants: {total_columbus:,}')

# Test with sample of 100
sample_size = 100
participants = list(local_db['participants'].find({
    'fields.City': 'COLUMBUS'
}, {
    'email_address': 1,
    'fields.Address': 1,
    'fields.ZIP': 1
}).limit(sample_size))

email_matches = 0

print(f'\nTesting {sample_size} participants for direct email match:')
print('=' * 80)

for i, p in enumerate(participants, 1):
    email = p.get('email_address', '').lower().strip()

    if not email:
        continue

    # Look for exact email match in Franklin demographics
    demo = remote_db['FranklinCountyDemographic'].find_one({
        'email': email
    })

    if demo:
        email_matches += 1
        customer_name = demo.get('customer_name', '')
        address = demo.get('address', '')

        print(f'[{i}] EMAIL MATCH!')
        print(f'  Email: {email}')
        print(f'  Customer: {customer_name}')
        print(f'  Address: {address}')

        # Parse name
        if customer_name:
            if ',' in customer_name:
                parts = customer_name.split(',')
                last_name = parts[0].strip().title()
                first_name = parts[1].strip().title() if len(parts) > 1 else ''
            else:
                parts = customer_name.split()
                first_name = parts[0].title() if len(parts) > 0 else ''
                last_name = ' '.join(parts[1:]).title() if len(parts) > 1 else ''

            print(f'  → FirstName: {first_name}')
            print(f'  → LastName: {last_name}')
        print()

print('=' * 80)
print(f'Email Match Rate: {email_matches}/{sample_size} ({email_matches/sample_size*100:.1f}%)')

# Estimate for all Columbus participants
estimated_matches = int((email_matches / sample_size) * total_columbus)
print(f'Estimated matches for all {total_columbus:,} Columbus participants: ~{estimated_matches:,}')
