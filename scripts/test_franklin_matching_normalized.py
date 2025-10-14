#!/usr/bin/env python3
"""
Test address matching with normalized addresses
"""
import sys
sys.path.insert(0, '.')
import pymongo
import re

def normalize_address(address):
    """Normalize address for matching"""
    if not address:
        return ''

    addr = address.upper().strip()

    # Common abbreviation mappings
    replacements = {
        r'\bAVENUE\b': 'AV',
        r'\bAVE\b': 'AV',
        r'\bSTREET\b': 'ST',
        r'\bROAD\b': 'RD',
        r'\bDRIVE\b': 'DR',
        r'\bCOURT\b': 'CT',
        r'\bPLACE\b': 'PL',
        r'\bBOULEVARD\b': 'BLVD',
        r'\bLANE\b': 'LN',
        r'\bCIRCLE\b': 'CIR',
        r'\bTERRACE\b': 'TER',
        r'\bNORTH\b': 'N',
        r'\bSOUTH\b': 'S',
        r'\bEAST\b': 'E',
        r'\bWEST\b': 'W',
    }

    for pattern, replacement in replacements.items():
        addr = re.sub(pattern, replacement, addr)

    # Remove extra whitespace
    addr = ' '.join(addr.split())

    return addr

# Local EmailOctopus database
local_client = pymongo.MongoClient('localhost', 27017)
local_db = local_client['emailoctopus_db']

# Remote demographics database
remote_client = pymongo.MongoClient('192.168.1.156', 27017)
remote_db = remote_client['empower_development']

print('Testing EmailOctopus → Franklin County Matching (Normalized):')
print('=' * 80)

# Get 50 Columbus participants
participants = list(local_db['participants'].find({
    'fields.City': 'COLUMBUS',
    'fields.Address': {'$exists': True, '$ne': ''}
}, {
    'email_address': 1,
    'fields.Address': 1,
    'fields.City': 1,
    'fields.ZIP': 1
}).limit(50))

matches_parcel = 0
matches_demo = 0
total = len(participants)

for i, p in enumerate(participants, 1):
    email = p.get('email_address')
    fields = p.get('fields', {})
    eo_address = fields.get('Address', '')
    eo_zip = fields.get('ZIP', '')

    if not eo_address or not eo_zip:
        continue

    # Normalize address
    normalized_addr = normalize_address(eo_address)

    # Clean ZIP
    eo_zip_clean = str(eo_zip).split('.')[0].split('-')[0]
    try:
        eo_zip_int = int(eo_zip_clean)
    except:
        continue

    # Find matching parcel
    parcel = remote_db['FranklinCountyResidential'].find_one({
        'address': normalized_addr,
        'parcel_zip': eo_zip_int
    })

    if parcel:
        matches_parcel += 1
        parcel_id = parcel.get('parcel_id')

        # Lookup demographics
        demo = remote_db['FranklinCountyDemographic'].find_one({
            'parcel_id': parcel_id
        })

        if demo:
            matches_demo += 1
            customer_name = demo.get('customer_name', '')

            print(f'[{i}/{total}] MATCH!')
            print(f'  Email: {email}')
            print(f'  Address: {eo_address} → {normalized_addr}')
            print(f'  Parcel: {parcel_id}')
            print(f'  Customer: {customer_name}')

            # Parse name (handle "LAST, FIRST" format)
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
print(f'Parcel Match Rate: {matches_parcel}/{total} ({matches_parcel/total*100:.1f}%)')
print(f'Demographic Match Rate: {matches_demo}/{total} ({matches_demo/total*100:.1f}%)')
print(f'Demographics per Parcel: {matches_demo/matches_parcel*100:.1f}%' if matches_parcel > 0 else 'N/A')
