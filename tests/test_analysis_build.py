"""A county build either replaces that county's households completely or leaves them untouched."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.ids import analysis_id  # noqa: E402
from src.analysis_engine.build import build_county, check_gates  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from tests.analysis_fakes import FakeStore, elec, monthly_series  # noqa: E402
from tests.mongo_fakes import FakeNamedDB  # noqa: E402

REG = load_registry()
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
KEY = b'test-key'
SURROGATE = 'AEP:CSP:43002|1 MAIN ST'
YEAR = monthly_series(2025, 8, [900.0] * 12)


def _db():
    return FakeNamedDB({
        'FranklinElectricalDB': [elec('E1', YEAR, parcel_key='K1'), elec('E2', YEAR),
                                 elec('E3', monthly_series(2015, 3, [700.0] * 12)), elec(SURROGATE, YEAR)],
        'FranklinCountyDemographic': [{'_id': 'D1', 'parcel_key': 'K1', 'estimated_income': 30000.0,
                                       'md_householdsize': 2.0, 'md_own_rent': 'Definite Owner'}],
    })


def test_successful_build_replaces_only_its_county():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Franklin'}, {'_id': 'X', 'county': 'Adams'}])
    build = build_county(_db(), store, 'Franklin', REG, NOW, KEY)
    assert build['status'] == 'ok' and build['doc_count'] == 4
    assert set(store.live) == {'E1', 'E2', 'E3', 'X', analysis_id(SURROGATE, KEY, 'Franklin')}
    assert not any(isinstance(i, str) and (':' in i or '|' in i) for i in store.live)
    assert store.live['E1']['dims'][0] == 2 and store.live['E1']['link'] == 1 | 4
    assert build['sources_present'] == ['demographic', 'electrical']
    assert build['source_counts']['electrical'] == 4 and build['cutpoints']['annual_kwh']['n'] == 3
    assert build['unmapped_values'] == {}
    assert {k: build['stats'][k] for k in ('unlinked', 'multi_unit', 'stale', 'duplicates')} == {
        'unlinked': 3, 'multi_unit': 0, 'stale': 1, 'duplicates': {'demographic': 0}}
    assert build['unmapped_fields'] == {}
    assert build['size_p99'] < 1024 and build['registry_version'] == REG.fields_version
    assert store.builds == [build] and store.staging == {}


def test_county_without_electrical_fails_and_changes_nothing():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Nowhere'}])
    build = build_county(FakeNamedDB({}), store, 'Nowhere', REG, NOW, KEY)
    assert build['status'] == 'failed' and 'no ElectricalDB' in build['error']
    assert set(store.live) == {'OLD'} and store.builds == [build]


def test_write_failure_leaves_previous_version_live():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Franklin'}], fail_on_stage=True)
    build = build_county(_db(), store, 'Franklin', REG, NOW, KEY)
    assert build['status'] == 'failed' and 'disk full' in build['error']
    assert set(store.live) == {'OLD'} and store.staging == {}


def test_swap_failure_is_recorded_as_possibly_partial():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Franklin'}], fail_on_swap=True)
    build = build_county(_db(), store, 'Franklin', REG, NOW, KEY)
    assert build['status'] == 'failed'
    assert 'swap failed' in build['error'] and 'connection lost' in build['error']
    assert store.builds == [build]


def test_recorded_error_is_capped():
    store = FakeStore(fail_on_swap=True)
    store.swap = lambda county: (_ for _ in ()).throw(RuntimeError('x' * 5000))
    build = build_county(_db(), store, 'Franklin', REG, NOW, KEY)
    assert build['status'] == 'failed' and len(build['error']) == 1000


def test_gates():
    assert check_gates(3, 3, [300, 400, 500]) == []
    assert check_gates(2, 3, [300, 400]) == ['doc count 2 != source meter count 3']
    assert check_gates(1, 1, [1024]) == ['p99 document size 1024 B is not under 1024 B']
    assert check_gates(3, 3, [300], surrogate_ids=2) == ['2 document _id(s) still carry a readable source id']
    assert check_gates(0, 0, []) == ['no source meters; refusing to replace the county']


def test_gates_p2():
    assert check_gates(3, 3, [100, 100, 100], nonres=(2, 1))[0].startswith('nonres')
    assert 'county' in check_gates(3, 3, [100] * 3, wrong_county=1)[0]
    assert 'unmapped' in check_gates(3, 3, [100] * 3, unmapped={'fields': {'residential': ['land_use']},
                                                                  'values': {}})[0]
    assert check_gates(3, 3, [100] * 3, nonres=(1, 1), unmapped={'fields': {}, 'values': {}}) == []


def test_unmapped_field_fails_only_that_county():
    db = FakeNamedDB({'AElectricalDB': [elec('E1', YEAR, surprise_field=1)], 'BElectricalDB': [elec('E2', YEAR)]})
    store = FakeStore()
    builds = [build_county(db, store, c, REG, NOW, KEY) for c in ('A', 'B')]
    assert [b['status'] for b in builds] == ['failed', 'ok'] and 'surprise_field' in builds[0]['error']


def test_unmapped_value_fails_the_county():
    db = FakeNamedDB({'AElectricalDB': [elec('E1', YEAR, parcel_key='K1')],
                      'ACountyDemographic': [{'_id': 'D1', 'parcel_key': 'K1', 'md_own_rent': 'Maybe'}]})
    build = build_county(db, FakeStore(), 'A', REG, NOW, KEY)
    assert build['status'] == 'failed' and 'Maybe' in build['error'] and build['unmapped_values']


def test_build_stats_count_nonres_and_fallbacks():
    db = FakeNamedDB({
        'TElectricalDB': [elec('E1', monthly_series(2025, 8, [6000.0] * 12), parcel_key='K1'), elec('E2', YEAR)],
        'TCountyDemographic': [{'_id': 'D1', 'parcel_key': 'K1', 'owner_age': 80}]})
    build = build_county(db, FakeStore(), 'T', REG, NOW, KEY)
    stats = build['stats']
    assert stats['nonres'] == 1 and stats['fallbacks'] == {'senior': 1}
    assert stats['priced'] <= 2 and stats['income_known'] == 0 and stats['usable_fit'] == 0
    assert set(stats['boundary']) == {'fpl_pct=175', 'fpl_pct=200', 'ami_pct=80', 'energy_burden=6', 'energy_burden=10'}
    assert len(stats['levels']) == len(REG.dims) and all(sum(row) == 2 for row in stats['levels'])


def test_successful_build_writes_coverage():
    store = FakeStore()
    build_county(_db(), store, 'Franklin', REG, NOW, KEY)
    assert store.coverage['Franklin']['meters'] == 4
    failed = FakeStore()
    build_county(FakeNamedDB({}), failed, 'Nowhere', REG, NOW, KEY)
    assert failed.coverage == {}


def test_coverage_failure_is_isolated_from_the_recorded_build():
    class Boom(FakeStore):
        def write_coverage(self, doc):
            raise IOError('coverage disk')
    build = build_county(_db(), Boom(), 'Franklin', REG, NOW, KEY)
    assert build['status'] == 'ok' and 'coverage disk' in build['coverage_error']


def test_same_surrogate_in_two_counties_builds_distinct_ids():
    db = FakeNamedDB({'AdamsElectricalDB': [elec('FE:OE:ALL', YEAR)], 'AllenElectricalDB': [elec('FE:OE:ALL', YEAR)]})
    store = FakeStore()  # FakeStore keys live by _id and does not simulate MongoStore's cross-county refusal
    for county in ('Adams', 'Allen'):
        assert build_county(db, store, county, REG, NOW, KEY)['status'] == 'ok'
    assert {d['county'] for d in store.live.values()} == {'Adams', 'Allen'} and len(store.live) == 2
    assert set(store.live) == {analysis_id('FE:OE:ALL', KEY, 'Adams'), analysis_id('FE:OE:ALL', KEY, 'Allen')}
