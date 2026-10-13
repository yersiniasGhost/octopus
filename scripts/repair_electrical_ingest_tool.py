#!/usr/bin/env python3
"""
Fold the 2026-08-19 ingest's duplicate {County}ElectricalDB docs into their pre-ingest doc and delete them.

Requires a fresh backup; see the P2 plan Task 3. DRY RUN BY DEFAULT: without --execute nothing is written.
Reports print counts only (no addresses, names or account ids).

Usage:
    python scripts/repair_electrical_ingest_tool.py --county Franklin
    python scripts/repair_electrical_ingest_tool.py --execute --report /tmp/repair.md
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.tools.mongo import get_empower_db
from src.tools.utility_bills.repair import COUNTERS, repair_county
from ingest_electric_bills_tool import fmt_table


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--county', action='append', help='county to repair; repeat for several (default: all)')
    ap.add_argument('--execute', action='store_true', help='actually write to MongoDB (default: dry run)')
    ap.add_argument('--report', help='write the counters to this markdown file')
    args = ap.parse_args()

    db = get_empower_db()
    suffix = 'ElectricalDB'
    counties = args.county or sorted(n[:-len(suffix)] for n in db.list_collection_names() if n.endswith(suffix))
    mode = 'DRY RUN' if not args.execute else 'EXECUTE'
    rows = []
    for county in counties:
        rows.append({'county': county, **repair_county(db, county, dry_run=not args.execute)})
        print(f"  {county}: " + ', '.join(f"{k}={rows[-1][k]}" for k in COUNTERS if rows[-1][k]))
    rows.append({'county': 'TOTAL', **{k: sum(r[k] for r in rows) for k in COUNTERS}})
    out = f"# ElectricalDB ingest repair {mode} - {datetime.now():%Y-%m-%d %H:%M}\n\n```\n" \
          f"{fmt_table(rows, ['county'] + COUNTERS)}\n```\n"
    print(out)
    if args.report:
        Path(args.report).write_text(out)


if __name__ == '__main__':
    main()
