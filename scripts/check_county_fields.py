"""
Check what fields are actually in county demographic records
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

# Connect to county DB
host = os.getenv('MONGODB_HOST_RM', 'localhost')
port = int(os.getenv('MONGODB_PORT_RM', '27017'))
db_name = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

client = MongoClient(host, port)
db = client[db_name]

# Check RichlandCounty since it had good matches
collection_name = 'RichlandCountyDemographic'

print(f"Checking collection: {collection_name}")

# Get one sample document
sample = db[collection_name].find_one()

if sample:
    print("\nSample document fields:")
    print("="*70)
    for key in sorted(sample.keys()):
        value = sample[key]
        # Truncate long values
        if isinstance(value, str) and len(value) > 50:
            value = value[:50] + "..."
        print(f"{key:50s}: {value}")

    print("\n" + "="*70)
    print("Looking for age-related fields:")
    print("="*70)
    for key in sample.keys():
        if 'age' in key.lower():
            print(f"  {key}: {sample[key]}")

client.close()
