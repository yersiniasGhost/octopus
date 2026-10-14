"""Build and report the bulk need-analysis household table.

    python -m src.analysis_engine.cli build --county Adams --county Cuyahoga [--dry-run]
    python -m src.analysis_engine.cli build --all --dry-run
    python -m src.analysis_engine.cli report --county Adams
    python -m src.analysis_engine.cli reconcile [--county Adams ...] [--seed 0]
"""

import argparse
import sys
from datetime import datetime, timezone
from typing import List, Optional

from src.analysis_engine.build import build_county
from src.analysis_engine.ids import load_id_key
from src.analysis_engine.registry import Registry, load_registry
from src.analysis_engine.report import county_report, format_report, summarize_build
from src.analysis_engine.reconcile import format_row, reconcile, sample_counties
from src.analysis_engine.sources import all_counties
from src.analysis_engine.store import DryRunStore, MongoStore


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='analysis_engine', description='Bulk household need analysis')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='rebuild analysis_households for the given counties')
    which = build.add_mutually_exclusive_group(required=True)
    which.add_argument('--county', action='append')
    which.add_argument('--all', action='store_true', help='every county that has an ElectricalDB collection')
    build.add_argument('--dry-run', action='store_true', help='compute and validate, write nothing')
    report = sub.add_parser('report', help='dimension and archetype counts from analysis_households')
    report.add_argument('--county', action='append', required=True)
    rec = sub.add_parser('reconcile', help='recount sources independently and compare with analysis_coverage')
    rec.add_argument('--county', action='append', help='default: a seeded sample of five counties')
    rec.add_argument('--seed', type=int, default=0)
    return parser.parse_args(argv)


def run_build(db, counties: List[str], dry_run: bool, reg: Registry, id_key: bytes,
              now: Optional[datetime] = None) -> int:
    store = DryRunStore() if dry_run else MongoStore(db)
    if not dry_run:
        store.ensure_indexes(len(reg.dims))
    failed = 0
    for county in counties:
        build = build_county(db, store, county, reg, now or datetime.now(timezone.utc), id_key)
        print(summarize_build(build))
        failed += build['status'] != 'ok' or bool(build.get('coverage_error'))
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None, db=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    reg = load_registry()
    id_key = load_id_key() if args.command == 'build' else None
    if db is None:
        from src.tools.mongo import get_empower_db
        db = get_empower_db()
    if args.command == 'build':
        return run_build(db, all_counties(db) if args.all else args.county, args.dry_run, reg, id_key)
    if args.command == 'reconcile':
        now = datetime.now(timezone.utc)
        rows = reconcile(db, args.county or sample_counties(db, args.seed), reg, now.year * 100 + now.month)
        print('\n'.join(format_row(r) for r in rows))
        return 0 if all(r['ok'] for r in rows) else 1
    for county in args.county:
        print(format_report(county_report(db, county, reg), reg))
    return 0


if __name__ == '__main__':
    sys.exit(main())
