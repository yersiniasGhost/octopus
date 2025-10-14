"""
Analyze unmatched participants to understand why they didn't match
"""
import csv
from collections import Counter

debug_csv = 'data/exports/unmatched_debug_20251010_003725.csv'

total = 0
by_county = Counter()
with_address = 0
with_phone = 0
with_both = 0
no_address = 0
no_phone = 0

with open(debug_csv, 'r') as f:
    reader = csv.DictReader(f)

    for row in reader:
        total += 1

        county = row['County_Lookup']
        address = row['Address']
        phone = row['Cell']

        by_county[county] += 1

        if address:
            with_address += 1
        else:
            no_address += 1

        if phone:
            with_phone += 1
        else:
            no_phone += 1

        if address and phone:
            with_both += 1

print("="*70)
print("UNMATCHED PARTICIPANTS ANALYSIS (First 50)")
print("="*70)
print(f"Total unmatched in sample: {total}")
print()
print(f"With address: {with_address} ({with_address/total*100:.1f}%)")
print(f"With phone:   {with_phone} ({with_phone/total*100:.1f}%)")
print(f"With both:    {with_both} ({with_both/total*100:.1f}%)")
print(f"No address:   {no_address}")
print(f"No phone:     {no_phone}")

print()
print("By County Lookup:")
for county, count in by_county.most_common():
    print(f"  {county:20s}: {count}")

print()
print("Sample unmatched records:")
print("="*70)

with open(debug_csv, 'r') as f:
    reader = csv.DictReader(f)

    count = 0
    for row in reader:
        if count < 5:
            print(f"\n{count+1}. Email: {row['Email']}")
            print(f"   Address: {row['Address']}")
            print(f"   City: {row['City']}, ZIP: {row['ZIP']}")
            print(f"   Phone: {row['Cell']}")
            print(f"   County: {row['County_Lookup']}")
            count += 1
