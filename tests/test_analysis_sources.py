"""Reading a county's collections into parcel indexes: duplicates, spellings, meter counts, drift."""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.sources import (choose_most_complete, load_county_sources,  # noqa: E402
                                         sources_present)
from tests.mongo_fakes import FakeNamedDB  # noqa: E402

REG = load_registry()
DEMO_SPECS = REG.fields_for('demographic')


def test_sources_present_lists_only_existing_collections():
    names = ['TestvilleElectricalDB', 'TestvilleCountyDemographic', 'OtherElectricalDB']
    assert sources_present(names, 'Testville') == {'electrical': 'TestvilleElectricalDB',
                                                   'demographic': 'TestvilleCountyDemographic'}


def test_most_complete_duplicate_wins_in_any_order():
    sparse = {'_id': 'a', 'estimated_income': -1, 'md_householdsize': 2.0}
    rich = {'_id': 'b', 'estimated_income': 50000.0, 'md_householdsize': 2.0, 'md_own_rent': 'Definite Owner'}
    tie = {'_id': 'c', 'estimated_income': 51000.0, 'md_householdsize': 3.0, 'md_own_rent': 'Probable Owner'}
    for order in itertools.permutations([sparse, rich, tie]):
        assert choose_most_complete(list(order), DEMO_SPECS, REG.missing_tokens)['_id'] == 'c'


def _db():
    return FakeNamedDB({
        'TestvilleElectricalDB': [
            {'_id': 'E1', 'parcel_key': 'K1', 'parcel_id': 'K1'},
            {'_id': 'E2', 'parcel_key': 'K1', 'parcel_id': 'K1'},
            {'_id': 'E3', 'parcel_id': 30324005},
            {'_id': 'E4', 'parcel_id': None},
        ],
        'TestvilleCountyResidential': [{'_id': 'R1', 'parcel_key': 'K1', 'age': 1958, 'brand_new_field': 1},
                                       {'_id': 'R2', 'parcel_id': '30324005', 'age': 2001}],
        'TestvilleCountyDemographic': [{'_id': 'D1', 'parcel_key': 'K1', 'estimated_income': -1},
                                       {'_id': 'D2', 'parcel_key': 'K1', 'estimated_income': 40000.0}],
        'TestvilleMultiTenant': [{'_id': 'M1', 'parcel_id': '30324005'}],
    })


def test_load_counts_meters_and_resolves_spellings():
    src = load_county_sources(_db(), 'Testville', REG)
    assert src.counts == {'electrical': 4, 'residential': 2, 'demographic': 2, 'multitenant': 1}
    shared = src.match({'_id': 'E1', 'parcel_key': 'K1'})
    assert shared.linked and shared.meters_on_parcel == 2 and shared.residential['age'] == 1958
    assert shared.demographic['_id'] == 'D2' and shared.thermal is None and not shared.multitenant
    by_int_id = src.match({'_id': 'E3', 'parcel_id': 30324005})
    assert by_int_id.residential['age'] == 2001 and by_int_id.multitenant and by_int_id.meters_on_parcel == 1
    assert src.match({'_id': 'E4', 'parcel_id': None}).linked is False


def test_duplicates_and_unmapped_fields_are_reported():
    src = load_county_sources(_db(), 'Testville', REG)
    assert src.duplicates == {'residential': 0, 'demographic': 1}
    assert src.tracker.unmapped() == {'residential': ['brand_new_field']}


def test_indexed_docs_are_projected_to_mapped_fields():
    src = load_county_sources(_db(), 'Testville', REG)
    assert 'brand_new_field' not in src.match({'_id': 'E1', 'parcel_key': 'K1'}).residential
