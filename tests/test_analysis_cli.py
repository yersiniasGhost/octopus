"""The CLI wiring: a dry run builds everything, writes nothing, and reports what it would have written."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.cli import parse_args, run_build  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.report import format_report, summarize_build  # noqa: E402
from tests.analysis_fakes import elec, monthly_series  # noqa: E402
from tests.mongo_fakes import FakeNamedDB  # noqa: E402


def test_parse_args_accepts_repeated_counties():
    args = parse_args(['build', '--county', 'Adams', '--county', 'Cuyahoga', '--dry-run'])
    assert args.command == 'build' and args.county == ['Adams', 'Cuyahoga'] and args.dry_run


def test_dry_run_succeeds_and_failure_sets_exit_code(capsys):
    db = FakeNamedDB({'AdamsElectricalDB': [elec('E1', monthly_series(2025, 8, [900.0] * 12), utility='AEP')]})
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    assert run_build(db, ['Adams'], True, load_registry(), now) == 0
    assert 'Adams: ok' in capsys.readouterr().out
    assert run_build(db, ['Adams', 'Nowhere'], True, load_registry(), now) == 1


def test_summarize_build_lists_drift():
    text = summarize_build({'county': 'Adams', 'status': 'ok', 'doc_count': 8283, 'size_p50': 210, 'size_p99': 260,
                            'unmapped_fields': {'electrical': ['new_field']},
                            'unmapped_values': {'owner': [['Maybe', 3]]},
                            'stats': {'unlinked': 8283, 'multi_unit': 0, 'stale': 12, 'duplicates': {}}})
    assert 'Adams: ok' in text and '8,283 households' in text
    assert 'unmapped electrical fields: new_field' in text and 'owner: Maybe (3)' in text


def test_format_report_shows_levels_proxy_and_denominators():
    reg = load_registry()
    dims = {name: {'levels': {}, 'proxy': 0} for name in reg.dims}
    dims['income_need'] = {'levels': {2: 10, 1: 5, -1: 85}, 'proxy': 0}
    dims['building_inefficiency'] = {'levels': {1: 40, 0: 20, -1: 40}, 'proxy': 30}
    archetypes = {name: {'n': 0, 'known': 100} for name in reg.rules['archetypes']}
    archetypes['bill_assistance'] = {'n': 10, 'known': 15}
    text = format_report({'county': 'Adams', 'total': 100, 'dims': dims, 'archetypes': archetypes}, reg)
    assert text.splitlines()[0] == 'Adams: 100 households'
    assert 'high 10 · moderate 5 · none 0 · unknown 85 · proxy 0' in text
    assert 'high 0 · moderate 40 · none 20 · unknown 40 · proxy 30' in text
    assert 'Bill assistance candidate' in text and '10 of 15 known-enough' in text
