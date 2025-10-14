"""
Count engagement from CSV file
"""
import csv

csv_file = 'data/exports/campaign_cf115430-61a1-11f0-89cc-1be24f0429c5_IMPACT_SummerCrisis_20250715.csv'

opened_count = 0
clicked_count = 0
both_count = 0
engaged_count = 0
total_count = 0

combinations = {}

with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)

    for row in reader:
        total_count += 1
        opened = row['opened'].strip()
        clicked = row['clicked'].strip()

        # Track combinations
        combo = f"{opened},{clicked}"
        combinations[combo] = combinations.get(combo, 0) + 1

        is_opened = (opened == 'Yes')
        is_clicked = (clicked == 'Yes')

        if is_opened:
            opened_count += 1
        if is_clicked:
            clicked_count += 1
        if is_opened and is_clicked:
            both_count += 1
        if is_opened or is_clicked:
            engaged_count += 1

print("="*70)
print("CSV ENGAGEMENT COUNTS")
print("="*70)
print(f"Total rows: {total_count}")
print(f"\nEngaged (opened OR clicked): {engaged_count}")
print(f"  - Opened: {opened_count}")
print(f"  - Clicked: {clicked_count}")
print(f"  - Both opened AND clicked: {both_count}")
print(f"\nOpened only: {opened_count - both_count}")
print(f"Clicked only: {clicked_count - both_count}")

print(f"\n{'='*70}")
print("COMBINATIONS")
print(f"{'='*70}")
for combo, count in sorted(combinations.items()):
    print(f"{combo:20s}: {count:5d}")
