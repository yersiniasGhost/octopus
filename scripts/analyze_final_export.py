"""
Comprehensive analysis of the final export
"""
import csv

csv_file = 'data/exports/matched_participants_20251010_000125.csv'

total = 0
matched = 0
with_name = 0
with_income = 0
with_year_built = 0
with_all_data = 0

counties = {}
campaigns = {}

sample_complete = []
sample_matched = []

with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)

    for row in reader:
        total += 1

        name = row['Name']
        county = row['County']
        campaign = row['Campaign']
        income = row['Income']
        year_built = row['YearBuilt']

        # Track counties
        if county:
            if county not in counties:
                counties[county] = {'total': 0, 'matched': 0}
            counties[county]['total'] += 1

            if name:
                counties[county]['matched'] += 1

        # Track campaigns
        if campaign not in campaigns:
            campaigns[campaign] = {'total': 0, 'matched': 0}
        campaigns[campaign]['total'] += 1
        if name:
            campaigns[campaign]['matched'] += 1

        # Count matched records
        if name:
            matched += 1
            with_name += 1

            if len(sample_matched) < 5:
                sample_matched.append(row)

        if income:
            with_income += 1
        if year_built:
            with_year_built += 1

        if name and income and year_built:
            with_all_data += 1
            if len(sample_complete) < 5:
                sample_complete.append(row)

print("="*80)
print("FINAL EXPORT ANALYSIS")
print("="*80)
print(f"Total participants: {total}")
print(f"Matched to county data: {matched} ({matched/total*100:.1f}%)")
print(f"  - With names: {with_name}")
print(f"  - With income: {with_income}")
print(f"  - With year built: {with_year_built}")
print(f"  - With ALL data (name + income + year_built): {with_all_data}")

print(f"\n{'='*80}")
print("MATCH RATE BY COUNTY")
print(f"{'='*80}")
for county in sorted(counties.keys()):
    stats = counties[county]
    pct = stats['matched'] / stats['total'] * 100 if stats['total'] > 0 else 0
    print(f"{county:20s}: {stats['matched']:4d}/{stats['total']:4d} matched ({pct:5.1f}%)")

print(f"\n{'='*80}")
print("TOP 10 CAMPAIGNS BY MATCH RATE")
print(f"{'='*80}")
# Sort by match rate
campaign_list = []
for campaign, stats in campaigns.items():
    if stats['total'] > 0:
        pct = stats['matched'] / stats['total'] * 100
        campaign_list.append((campaign, stats['matched'], stats['total'], pct))

campaign_list.sort(key=lambda x: x[3], reverse=True)

for campaign, matched, total, pct in campaign_list[:10]:
    print(f"{campaign[:50]:50s}: {matched:3d}/{total:3d} ({pct:5.1f}%)")

print(f"\n{'='*80}")
print("SAMPLE MATCHED RECORDS")
print(f"{'='*80}")
for i, row in enumerate(sample_matched, 1):
    print(f"\n{i}. {row['Name']}")
    print(f"   Campaign: {row['Campaign']}")
    print(f"   County: {row['County']}")
    print(f"   Opened: {row['Opened']}, Clicked: {row['Clicked']}, Applied: {row['Applied']}")
    print(f"   Income: ${row['Income']}, Year Built: {row['YearBuilt']}")

print(f"\n{'='*80}")
print("SAMPLE COMPLETE RECORDS (with all data)")
print(f"{'='*80}")
for i, row in enumerate(sample_complete, 1):
    print(f"\n{i}. {row['Name']}")
    print(f"   Campaign: {row['Campaign']}")
    print(f"   County: {row['County']}")
    print(f"   Opened: {row['Opened']}, Clicked: {row['Clicked']}, Applied: {row['Applied']}")
    print(f"   Age: {row['Age']}, Income: ${row['Income']}, Year Built: {row['YearBuilt']}")
