"""
Analyze the exported CSV file
"""
import csv

csv_file = 'data/exports/matched_participants_20251009_222956.csv'

total = 0
with_county = 0
with_age = 0
with_income = 0
with_year_built = 0
with_all_county_data = 0
sample_complete = []

with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)

    for row in reader:
        total += 1

        county = row['County']
        age = row['Age']
        income = row['Income']
        year_built = row['YearBuilt']

        if county:
            with_county += 1
        if age:
            with_age += 1
        if income:
            with_income += 1
        if year_built:
            with_year_built += 1

        if age and income and year_built:
            with_all_county_data += 1
            if len(sample_complete) < 5:
                sample_complete.append(row)

print("="*70)
print("EXPORT ANALYSIS")
print("="*70)
print(f"Total rows: {total}")
print(f"Rows with county: {with_county}")
print(f"Rows with age: {with_age}")
print(f"Rows with income: {with_income}")
print(f"Rows with year built: {with_year_built}")
print(f"Rows with ALL county data (age + income + year_built): {with_all_county_data}")

print(f"\n{'='*70}")
print("SAMPLE COMPLETE ROWS")
print(f"{'='*70}")
for i, row in enumerate(sample_complete, 1):
    print(f"\nRow {i}:")
    for key, value in row.items():
        print(f"  {key:15s}: {value}")
