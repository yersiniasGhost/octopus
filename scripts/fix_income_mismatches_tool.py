#!/usr/bin/env python3
"""
fix_income_mismatches_tool.py - Identify and fix income_level/estimated_income mismatches

This script:
1. Analyzes the relationship between income_level and estimated_income
2. Flags records where estimated_income doesn't match the expected range for income_level
3. Exports mismatched records to CSV
4. Optionally fixes estimated_income by setting it to the median for that income_level

Usage:
    python scripts/fix_income_mismatches_tool.py --analyze      # Just analyze, no changes
    python scripts/fix_income_mismatches_tool.py --export       # Export mismatches to CSV
    python scripts/fix_income_mismatches_tool.py --fix          # Fix mismatches in database
    python scripts/fix_income_mismatches_tool.py --fix --dry-run  # Show what would be fixed
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
from collections import defaultdict
import statistics


def get_db_connection():
    """Connect to MongoDB."""
    client = MongoClient('mongodb://localhost:27017')
    return client['empower_development']


def calculate_level_statistics(db):
    """Calculate median and IQR for estimated_income at each income_level."""
    stats = {}

    for level in range(1, 10):
        pipeline = [
            {'$match': {'income_level': float(level), 'estimated_income': {'$gt': 0}}},
            {'$project': {'estimated_income': 1}}
        ]

        incomes = [doc['estimated_income'] for doc in db['FranklinCountyDemographic'].aggregate(pipeline)]

        if incomes:
            incomes_sorted = sorted(incomes)
            median = statistics.median(incomes)
            q1 = incomes_sorted[len(incomes_sorted) // 4]
            q3 = incomes_sorted[3 * len(incomes_sorted) // 4]
            iqr = q3 - q1

            # Define acceptable range as median ± 2*IQR (generous bounds)
            min_acceptable = max(0, q1 - 1.5 * iqr)
            max_acceptable = q3 + 1.5 * iqr

            stats[level] = {
                'median': median,
                'q1': q1,
                'q3': q3,
                'iqr': iqr,
                'min_acceptable': min_acceptable,
                'max_acceptable': max_acceptable,
                'count': len(incomes)
            }

    return stats


def find_mismatches(db, level_stats):
    """Find records where estimated_income doesn't match income_level expectations."""
    mismatches = []

    # Get all demographic collections
    collections = [name for name in db.list_collection_names() if 'Demographic' in name]

    for coll_name in collections:
        for doc in db[coll_name].find({
            'income_level': {'$gte': 1, '$lte': 9},
            'estimated_income': {'$gt': 0}
        }):
            level = int(doc['income_level'])
            income = doc['estimated_income']

            if level in level_stats:
                stats = level_stats[level]

                # Check if income is outside acceptable range
                if income < stats['min_acceptable'] or income > stats['max_acceptable']:
                    mismatches.append({
                        'collection': coll_name,
                        '_id': doc['_id'],
                        'parcel_id': doc.get('parcel_id', ''),
                        'customer_name': doc.get('customer_name', ''),
                        'income_level': level,
                        'estimated_income': income,
                        'expected_median': stats['median'],
                        'expected_min': stats['min_acceptable'],
                        'expected_max': stats['max_acceptable'],
                        'total_energy_burden': doc.get('total_energy_burden'),
                        'annual_kwh_cost': doc.get('annual_kwh_cost', -1),
                        'annual_gas_cost': doc.get('annual_gas_cost', -1)
                    })

    return mismatches


def export_to_csv(mismatches, output_path):
    """Export mismatched records to CSV."""
    if not mismatches:
        print("No mismatches to export.")
        return

    fieldnames = [
        'collection', 'parcel_id', 'customer_name', 'income_level',
        'estimated_income', 'expected_median', 'expected_min', 'expected_max',
        'total_energy_burden', 'annual_kwh_cost', 'annual_gas_cost'
    ]

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(mismatches)

    print(f"Exported {len(mismatches)} mismatched records to {output_path}")


def fix_mismatches(db, mismatches, level_stats, dry_run=False):
    """Fix estimated_income by setting it to the median for the income_level."""
    if not mismatches:
        print("No mismatches to fix.")
        return

    # Group by collection for efficient updates
    by_collection = defaultdict(list)
    for m in mismatches:
        by_collection[m['collection']].append(m)

    total_fixed = 0

    for coll_name, records in by_collection.items():
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {coll_name}: {len(records)} records")

        for record in records:
            level = record['income_level']
            old_income = record['estimated_income']
            new_income = level_stats[level]['median']

            # Recalculate energy burden
            annual_kwh = record['annual_kwh_cost'] if record['annual_kwh_cost'] > 0 else 0
            annual_gas = record['annual_gas_cost'] if record['annual_gas_cost'] > 0 else 0
            total_energy_cost = annual_kwh + annual_gas

            if new_income > 0:
                new_energy_burden = (total_energy_cost / new_income) * 100
            else:
                new_energy_burden = -1

            if dry_run:
                print(f"  Would fix {record['customer_name'][:30]}: "
                      f"income ${old_income:,.0f} → ${new_income:,.0f}, "
                      f"burden {record['total_energy_burden']:.1f}% → {new_energy_burden:.1f}%")
            else:
                db[coll_name].update_one(
                    {'_id': record['_id']},
                    {'$set': {
                        'estimated_income': new_income,
                        'estimated_income_original': old_income,
                        'total_energy_burden': new_energy_burden,
                        'total_energy_burden_original': record['total_energy_burden'],
                        'income_fix_date': datetime.now().isoformat(),
                        'income_fix_reason': 'Mismatch with income_level'
                    }}
                )

            total_fixed += 1

    action = "Would fix" if dry_run else "Fixed"
    print(f"\n{action} {total_fixed} records across {len(by_collection)} collections")


def analyze_data(db):
    """Print analysis of income_level vs estimated_income relationship."""
    print("=" * 70)
    print("INCOME LEVEL vs ESTIMATED INCOME ANALYSIS")
    print("=" * 70)

    level_stats = calculate_level_statistics(db)

    print(f"\n{'Level':<6} {'Count':<8} {'Median':<12} {'Q1':<12} {'Q3':<12} {'Acceptable Range':<25}")
    print("-" * 70)

    for level in range(1, 10):
        if level in level_stats:
            s = level_stats[level]
            range_str = f"${s['min_acceptable']:,.0f} - ${s['max_acceptable']:,.0f}"
            print(f"{level:<6} {s['count']:<8} ${s['median']:>9,.0f} ${s['q1']:>9,.0f} ${s['q3']:>9,.0f} {range_str:<25}")

    # Find and summarize mismatches
    mismatches = find_mismatches(db, level_stats)

    print(f"\n{'=' * 70}")
    print(f"MISMATCH SUMMARY: {len(mismatches)} records with income outside expected range")
    print("=" * 70)

    # Group by collection
    by_coll = defaultdict(int)
    by_level = defaultdict(int)
    for m in mismatches:
        by_coll[m['collection']] += 1
        by_level[m['income_level']] += 1

    print("\nBy Collection:")
    for coll, count in sorted(by_coll.items()):
        print(f"  {coll}: {count}")

    print("\nBy Income Level:")
    for level in sorted(by_level.keys()):
        print(f"  Level {level}: {by_level[level]}")

    # Show sample mismatches
    print("\nSample Mismatches (first 10):")
    print(f"{'Name':<30} {'Level':<6} {'Actual':<12} {'Expected':<12} {'Burden':<10}")
    print("-" * 70)
    for m in mismatches[:10]:
        burden = f"{m['total_energy_burden']:.1f}%" if m['total_energy_burden'] else 'N/A'
        print(f"{m['customer_name'][:30]:<30} {m['income_level']:<6} "
              f"${m['estimated_income']:>9,.0f} ${m['expected_median']:>9,.0f} {burden:<10}")

    return level_stats, mismatches


def main():
    parser = argparse.ArgumentParser(description='Fix income_level/estimated_income mismatches')
    parser.add_argument('--analyze', action='store_true', help='Analyze data and show statistics')
    parser.add_argument('--export', action='store_true', help='Export mismatches to CSV')
    parser.add_argument('--fix', action='store_true', help='Fix mismatches in database')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--output', type=str, default='data/exports/income_mismatches.csv',
                        help='Output CSV path (default: data/exports/income_mismatches.csv)')

    args = parser.parse_args()

    if not any([args.analyze, args.export, args.fix]):
        args.analyze = True  # Default to analyze

    db = get_db_connection()

    # Always calculate stats
    print("Calculating income level statistics...")
    level_stats = calculate_level_statistics(db)

    if args.analyze:
        analyze_data(db)

    if args.export or args.fix:
        print("\nFinding mismatched records...")
        mismatches = find_mismatches(db, level_stats)
        print(f"Found {len(mismatches)} mismatched records")

        if args.export:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            export_to_csv(mismatches, output_path)

        if args.fix:
            fix_mismatches(db, mismatches, level_stats, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
