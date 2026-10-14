"""One coverage document per county, built from the build's own counters."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.coverage import coverage_doc  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.sources import countykeys_collections  # noqa: E402
from tests.mongo_fakes import FakeNamedDB  # noqa: E402

REG = load_registry()
BUILD = {'_id': 'b1', 'county': 'Hardin', 'built_at': datetime(2026, 10, 13, tzinfo=timezone.utc), 'doc_count': 10,
         'stats': {'unlinked': 4, 'stale': 1, 'nonres': 2, 'priced': 5, 'income_known': 3, 'usable_fit': 1,
                   'boundary': {'fpl_pct=175': 1}, 'fallbacks': {'senior': 2},
                   'levels': [[10, 0, 0, 0]] * 6}}


def test_coverage_shares_and_counts():
    doc = coverage_doc(BUILD, None, {}, {'electrical': 'HardinElectricalDB'}, REG.rules)
    assert doc['_id'] == 'Hardin' and doc['linked'] == 6 and doc['priced_share'] == 0.5
    assert doc['heat_fuel_source'] == 'none' and 'archetypes' not in doc
    assert doc['levels']['income_need'] == {-1: 10, 0: 0, 1: 0, 2: 0}


def test_countykeys_missing_collection_is_reported():
    doc = coverage_doc(BUILD, None, {'demographic': 'HardinCountyDemographic'},
                       {'electrical': 'HardinElectricalDB'}, REG.rules)
    assert doc['countykeys'] == {'missing': ['HardinCountyDemographic'], 'disagree': []}


def test_archetypes_come_from_the_report():
    report = {'archetypes': {'weatherization': {'n': 3, 'known': 5, 'proxy': 2}}}
    assert coverage_doc(BUILD, report, {}, {}, REG.rules)['archetypes']['weatherization']['proxy'] == 2


def test_hud_estimated_flag_follows_the_rules_table():
    estimated = coverage_doc(BUILD, None, {}, {}, REG.rules)
    assert estimated['hud_estimated'] is True
    assert coverage_doc({**BUILD, '_id': 'b2', 'county': 'Adams'}, None, {}, {}, REG.rules)['hud_estimated'] is False
    assert coverage_doc({**BUILD, 'county': 'Nowhere'}, None, {}, {}, REG.rules)['hud_estimated'] is False


def test_countykeys_collections_roles_by_normalized_county():
    db = FakeNamedDB({'CountyKeys': [{'county': 'Hardin County', 'residential_data': 'HardinCountyResidential',
                                      'demographic_data': 'HardinCountyDemographic'}]})
    assert countykeys_collections(db, 'Hardin') == {'residential': 'HardinCountyResidential',
                                                    'demographic': 'HardinCountyDemographic'}
    assert countykeys_collections(db, 'Adams') == {}
