#!/usr/bin/env python3
"""
Ingest utility pre-enrollment electric usage into {County}ElectricalDB.

DRY-RUN BY DEFAULT: without --execute, nothing is written; instead a summary
of what WOULD be refreshed (per county: docs updated / created, readings
added, match rates) is printed and optionally written to a report file.

Source registry (deliveries, formats, known-bad archives):
    src/tools/utility_bills/sources.py

kW peak demand, KVAR / on-peak splits (AES) and read-vs-estimated flags
(Duke) exist in the raw files but are NOT stored (decision 2026-08-19).

Usage:
    python scripts/ingest_electric_bills_tool.py --delivery aug2026 --limit 5000
    python scripts/ingest_electric_bills_tool.py --delivery jan2026 --delivery aug2026
    python scripts/ingest_electric_bills_tool.py --delivery aug2026 --utility fe --execute
    python scripts/ingest_electric_bills_tool.py --delivery jan2026 --delivery aug2026 --exclude AES:jan2026

--exclude UTILITY:DELIVERY (repeatable) skips that utility's sources in that delivery entirely (not parsed, not
merged); e.g. AES:jan2026, whose account column holds customer names.
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.tools.mongo import get_empower_db
from src.tools.utility_bills.ingest import parse_all, process_county
from src.tools.utility_bills.sources import SOURCES

COUNTY_COLS = ['county', 'records', 'unique_addresses', 'matched_parcels',
               'docs_updated', 'docs_created_parcel', 'docs_created_unmatched',
               'unchanged', 'utility_set', 'skipped_multi_preingest', 'surrogate_collision',
               'readings_added_existing', 'readings_added_new', 'ambiguous_address', 'new_collection', 'date_range']
TOTAL_COLS = [c for c in COUNTY_COLS if c not in ('county', 'new_collection', 'date_range')]


def parse_excludes(specs):
    """['AES:jan2026', ...] -> {'jan2026': {'aes'}}."""
    out = {}
    for spec in specs or []:
        utility, _, delivery = spec.partition(':')
        if delivery not in SOURCES:
            raise SystemExit(f"--exclude {spec!r}: expected UTILITY:DELIVERY with delivery in {list(SOURCES)}")
        out.setdefault(delivery, set()).add(utility.lower())
    return out


def fmt_table(rows, cols):
    widths = {c: max(len(c), *(len(str(r.get(c, ''))) for r in rows)) for c in cols}
    lines = [' | '.join(c.ljust(widths[c]) for c in cols),
             '-|-'.join('-' * widths[c] for c in cols)]
    for r in rows:
        lines.append(' | '.join(str(r.get(c, '')).ljust(widths[c]) for c in cols))
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--delivery', action='append', choices=list(SOURCES), required=True,
                    help='delivery to ingest; repeat for several (processed oldest data first)')
    ap.add_argument('--utility', action='append', choices=['aep', 'aes', 'duke', 'fe'],
                    help='restrict to specific utilities')
    ap.add_argument('--exclude', action='append', metavar='UTILITY:DELIVERY',
                    help='skip a utility within one delivery, e.g. AES:jan2026; repeatable')
    ap.add_argument('--limit', type=int, help='max records per source file (for testing)')
    ap.add_argument('--execute', action='store_true', help='actually write to MongoDB (default: dry run)')
    ap.add_argument('--report', help='write the summary to this markdown file')
    args = ap.parse_args()

    excludes = parse_excludes(args.exclude)
    dry = not args.execute
    db = get_empower_db()
    existing_colls = set(db.list_collection_names())
    mode = 'DRY RUN' if dry else 'EXECUTE'
    out = [f"# Electric bills ingestion {mode} — {datetime.now():%Y-%m-%d %H:%M}",
           f"Deliveries: {', '.join(args.delivery)}  |  limit={args.limit or 'none'}",
           "kW demand / KVAR / estimated-read flags present in source but not stored.", ""]
    print(f"=== {mode}: {', '.join(args.delivery)} ===")

    for delivery in sorted(args.delivery, key=lambda d: (d != 'jan2026', d)):
        t0 = time.time()
        print(f"--- parsing {delivery} ---")
        by_county, parse_stats = parse_all(delivery, args.utility, args.limit, exclude=excludes.get(delivery, ()))
        out.append(f"## {delivery} — parse stats")
        for label, s in parse_stats.items():
            out.append(f"- {label}: {s}")
        out.append("")

        county_rows = []
        for county in sorted(by_county, key=lambda c: -len(by_county[c])):
            st = process_county(db, county, by_county[county], delivery, dry, existing_colls)
            county_rows.append(st)
            print(f"  {county}: {st['records']:,} recs, matched {st.get('matched_parcels', 0):,}, "
                  f"upd {st.get('docs_updated', 0):,}, new-parcel {st.get('docs_created_parcel', 0):,}, "
                  f"new-unmatched {st.get('docs_created_unmatched', 0):,}"
                  f"{' [NEW COLLECTION]' if st['new_collection'] else ''}")
            if not dry and st['new_collection']:
                existing_colls.add(f"{county}ElectricalDB")

        out.append(f"## {delivery} — per-county refresh summary ({mode})")
        out.append('```')
        out.append(fmt_table(county_rows, COUNTY_COLS))
        out.append('```')
        tot = {k: sum(r.get(k, 0) for r in county_rows) for k in TOTAL_COLS}
        new_colls = sorted(r['county'] for r in county_rows if r['new_collection'])
        out += [f"**Totals**: {tot}", f"**New collections ({len(new_colls)})**: {', '.join(new_colls)}",
                f"Elapsed: {round(time.time() - t0, 1)}s", ""]
        print(f"  {delivery} totals: {tot}")

    out.append("## Downstream refresh needed after execute")
    out.append("- `scripts/calculate_missing_thermal_loads_tool.py` (HDH/CDH per updated county)")
    out.append("- `scripts/calculate_energy_percentiles_tool.py` (percentiles shift with new readings)")

    report = '\n'.join(out)
    if args.report:
        Path(args.report).write_text(report)
        print(f"report written: {args.report}")


if __name__ == '__main__':
    main()
