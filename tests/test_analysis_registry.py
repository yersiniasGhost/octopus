"""The registry is data shared with bolt-od; the loader must refuse an inconsistent pair of files."""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.registry import REGISTRY_DIR, RegistryError, load_registry  # noqa: E402


def _copy(tmp_path):
    for name in ('fields.json', 'rules.json'):
        shutil.copy(REGISTRY_DIR / name, tmp_path / name)
    return (json.loads((tmp_path / 'fields.json').read_text()), json.loads((tmp_path / 'rules.json').read_text()))


def _save(tmp_path, fields, rules):
    (tmp_path / 'fields.json').write_text(json.dumps(fields))
    (tmp_path / 'rules.json').write_text(json.dumps(rules))


def test_shipped_registry_loads():
    reg = load_registry()
    assert reg.dims == ['income_need', 'energy_burden', 'building_inefficiency', 'high_usage', 'vulnerability',
                        'electrification']
    assert reg.link_bits['thermal'] == 3 and reg.link_bits['enrollment'] == 5


def test_field_codes_are_pinned():
    reg = load_registry()
    assert {f.name: f.code for f in reg.fields if f.name in ('income_est', 'hh_size', 'heat_fuel')} == \
        {'income_est': 1, 'hh_size': 2, 'heat_fuel': 25}


def test_lookups():
    reg = load_registry()
    assert reg.rate('FE', 'Cuyahoga') == 0.16217686
    assert reg.rate('FE', 'Franklin') == 0.16005921
    assert reg.rate(None, 'Adams') is None and reg.rate('XYZ', 'Adams') is None
    assert reg.default_utility('Adams') == 'AEP' and reg.default_utility('Testville') is None
    assert reg.hud('Franklin')['limits'][2] == 80300 and reg.hud('Testville') is None


def test_known_keys_cover_paths_inputs_and_ignored():
    reg = load_registry()
    assert {'md_householdsize', 'customer_name'} <= reg.known_keys['demographic']
    assert {'time_series_elec', 'utility', 'monthly_averages'} <= reg.known_keys['electrical']


def test_duplicate_code_is_refused(tmp_path):
    fields, rules = _copy(tmp_path)
    fields['fields'][1]['code'] = fields['fields'][0]['code']
    _save(tmp_path, fields, rules)
    with pytest.raises(RegistryError, match='duplicate field code'):
        load_registry(tmp_path)


def test_uncited_threshold_is_refused(tmp_path):
    fields, rules = _copy(tmp_path)
    del rules['params']['energy_burden']['source']
    rules['tables']['fpg_2026']['source'].pop('url')
    _save(tmp_path, fields, rules)
    with pytest.raises(RegistryError) as err:
        load_registry(tmp_path)
    assert 'params.energy_burden: missing source citation' in str(err.value)
    assert 'tables.fpg_2026: source lacks url' in str(err.value)


def test_archetype_with_unknown_dimension_is_refused(tmp_path):
    fields, rules = _copy(tmp_path)
    rules['archetypes']['bill_assistance']['all'][0]['dim'] = 'happiness'
    _save(tmp_path, fields, rules)
    with pytest.raises(RegistryError, match="unknown dimension 'happiness'"):
        load_registry(tmp_path)
