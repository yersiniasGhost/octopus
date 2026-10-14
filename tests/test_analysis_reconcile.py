"""reconcile compares independent source counts with analysis_coverage and flags any difference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine import reconcile as rc  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from tests.mongo_fakes import FakeNamedDB  # noqa: E402

REG = load_registry()


class _Coverage:
    def __init__(self, docs):
        self.docs = docs

    def find_one(self, flt):
        return self.docs.get(flt['_id'])


class _DB:
    def __init__(self, coverage):
        self.coverage = _Coverage(coverage)

    def __getitem__(self, name):
        return self.coverage


def test_match_and_mismatch(monkeypatch):
    monkeypatch.setattr(rc, 'source_counts', lambda db, c, m, r: {'meters': 10, 'linked': 6, 'stale': 1, 'nonres': 2})
    db = _DB({'A': {'meters': 10, 'linked': 6, 'stale': 1, 'nonres': 2},
              'B': {'meters': 9, 'linked': 6, 'stale': 1, 'nonres': 2}})
    rows = rc.reconcile(db, ['A', 'B'], REG, 202610)
    assert [r['ok'] for r in rows] == [True, False] and rows[1]['meters'] == (10, 9)


def test_missing_coverage_is_a_mismatch(monkeypatch):
    monkeypatch.setattr(rc, 'source_counts', lambda db, c, m, r: {'meters': 1, 'linked': 0, 'stale': 0, 'nonres': 0})
    assert rc.reconcile(_DB({}), ['Z'], REG, 202610)[0]['ok'] is False


def test_stale_cutoff_matches_is_fresh_boundary():
    assert rc.stale_cutoff(202610, 24) == '2024-10'  # a read in 202410 is exactly 24 months old: still fresh
    assert rc.stale_cutoff(202601, 24) == '2024-01'
    assert rc.stale_cutoff(202603, 36) == '2023-03'


def test_sample_counties_is_seeded_and_covers_the_kinds():
    docs = lambda n: [{'_id': i} for i in range(n)]  # noqa: E731
    cols = {'FranklinElectricalDB': docs(9), 'MontgomeryElectricalDB': docs(3), 'BigLinkedElectricalDB': docs(7),
            'BigLinkedCountyResidential': docs(1), 'BigUnlinkedElectricalDB': docs(6),
            'OtherAElectricalDB': docs(2), 'OtherBElectricalDB': docs(2), 'OtherCElectricalDB': docs(2)}
    db = FakeNamedDB(cols)
    first = rc.sample_counties(db, 7)
    assert first == rc.sample_counties(db, 7) and len(first) == 5 == len(set(first))
    assert first[:4] == ['Franklin', 'BigLinked', 'BigUnlinked', 'Montgomery']
    assert 'Franklin' in first and 'Montgomery' in first


def test_recounts_at_each_coverage_docs_build_month(monkeypatch):
    from datetime import datetime
    seen = []
    monkeypatch.setattr(rc, 'source_counts', lambda db, c, m, r: seen.append((c, m)) or {k: 1 for k in rc.KEYS})
    cov = {k: 1 for k in rc.KEYS}
    db = _DB({'A': {**cov, 'built_at': datetime(2026, 8, 31)}, 'B': cov})
    rc.reconcile(db, ['A', 'B', 'C'], REG, 202610)
    assert seen == [('A', 202608), ('B', 202610), ('C', 202610)]
