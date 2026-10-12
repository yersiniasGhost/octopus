"""Load and validate the analysis registry: canonical fields (fields.json) and need rules (rules.json).

Both files are data shared with bolt-od, which keeps a copy in lib/analysis/registry/. Everything the engine and
the UI must agree on -- link bits, field codes, dimension order, thresholds, cited tables -- is read from here
rather than restated in code.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from src.analysis_engine.normalize import TRANSFORMS

REGISTRY_DIR = Path(__file__).resolve().parent / 'registry'
SOURCE_ROLES = ('electrical', 'residential', 'demographic', 'thermal', 'multitenant')
FIELD_TYPES = ('int', 'float', 'bool')
TABLE_SOURCE_KEYS = ('title', 'url', 'retrieved')
OPS = ('>=', '<=', '==', '!=')


class RegistryError(ValueError):
    """The registry files are inconsistent; the message lists every problem found."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    code: int
    type: str
    stored: bool = True
    source: Optional[Dict[str, Any]] = None
    round: Optional[int] = None
    bins: Optional[Tuple[float, ...]] = None

    @property
    def role(self) -> Optional[str]:
        return self.source['role'] if self.source else None


@dataclass(frozen=True)
class Registry:
    fields_version: str
    rules_version: str
    fields: Tuple[FieldSpec, ...]
    link_bits: Dict[str, int]
    missing_tokens: Tuple[str, ...]
    known_keys: Dict[str, FrozenSet[str]]
    rules: Dict[str, Any]

    @property
    def dims(self) -> List[str]:
        return self.rules['dims']

    def params(self, name: str) -> Dict[str, Any]:
        return self.rules['params'][name]

    def table(self, name: str) -> Dict[str, Any]:
        return self.rules['tables'][name]

    def fields_for(self, role: str) -> List[FieldSpec]:
        return [f for f in self.fields if f.role == role]

    def field(self, name: str) -> FieldSpec:
        return next(f for f in self.fields if f.name == name)

    def hud(self, county: str) -> Optional[Dict[str, Any]]:
        return self.table('hud_low_income_fy2026')['counties'].get(county)

    def default_utility(self, county: str) -> Optional[str]:
        return self.table('county_default_utility')['map'].get(county)

    def rate(self, utility: Optional[str], county: str) -> Optional[float]:
        if not utility:
            return None
        rates = self.table('electric_rates_2025')['usd_per_kwh']
        return rates.get(f'{utility}:{county}', rates.get(utility))


def _field_errors(doc: Dict) -> List[str]:
    errors, names, codes = [], set(), set()
    for raw in doc.get('fields', []):
        name, code = raw.get('name'), raw.get('code')
        if name in names:
            errors.append(f'duplicate field name {name!r}')
        if code in codes:
            errors.append(f'duplicate field code {code} ({name})')
        if not isinstance(code, int) or isinstance(code, bool) or code < 1:
            errors.append(f'{name}: code must be a positive int')
        names.add(name)
        codes.add(code)
        if raw.get('type') not in FIELD_TYPES:
            errors.append(f'{name}: type must be one of {FIELD_TYPES}')
        if raw.get('type') == 'float' and not isinstance(raw.get('round'), int):
            errors.append(f'{name}: float fields need an int "round"')
        source = raw.get('source')
        if source is None:
            if not raw.get('derived'):
                errors.append(f'{name}: needs a source or "derived": true')
            continue
        if source.get('role') not in SOURCE_ROLES:
            errors.append(f'{name}: unknown source role {source.get("role")!r}')
        if not source.get('paths'):
            errors.append(f'{name}: source.paths is empty')
        if source.get('transform') == 'value_map':
            if not isinstance(source.get('value_map'), dict):
                errors.append(f'{name}: value_map transform needs a value_map')
        elif source.get('transform') not in TRANSFORMS:
            errors.append(f'{name}: unknown transform {source.get("transform")!r}')
    bits = doc.get('link_bits', {})
    if len(set(bits.values())) != len(bits):
        errors.append('link_bits values must be unique')
    return errors


def _table_errors(tables: Dict) -> List[str]:
    errors = []
    for name, table in tables.items():
        lacking = [k for k in TABLE_SOURCE_KEYS if not table.get('source', {}).get(k)]
        if lacking:
            errors.append(f'tables.{name}: source lacks {", ".join(lacking)}')
    base = tables.get('fpg_2026', {}).get('base', [])
    if len(base) != 8 or base != sorted(base):
        errors.append('tables.fpg_2026.base must hold 8 ascending amounts')
    for county, entry in tables.get('hud_low_income_fy2026', {}).get('counties', {}).items():
        if len(entry.get('limits', [])) != 8:
            errors.append(f'tables.hud_low_income_fy2026.{county}: limits must hold 8 amounts')
    rates = tables.get('electric_rates_2025', {}).get('usd_per_kwh', {})
    for county, utility in tables.get('county_default_utility', {}).get('map', {}).items():
        if f'{utility}:{county}' not in rates and utility not in rates:
            errors.append(f'county_default_utility.{county}: no rate for {utility}')
    return errors


def _archetype_errors(archetypes: Dict, dims: List[str], field_names: set) -> List[str]:
    errors = []
    for name, spec in archetypes.items():
        if spec.get('kind') == 'no_known_need':
            if not isinstance(spec.get('min_known'), int):
                errors.append(f'archetypes.{name}: min_known must be an int')
            continue
        for clause in spec.get('all', []):
            if 'dim' in clause and clause['dim'] not in dims:
                errors.append(f'archetypes.{name}: unknown dimension {clause["dim"]!r}')
            if 'field' in clause and clause['field'] not in field_names:
                errors.append(f'archetypes.{name}: unknown field {clause["field"]!r}')
            if clause.get('op') not in OPS:
                errors.append(f'archetypes.{name}: unknown op {clause.get("op")!r}')
    return errors


def validate(fields_doc: Dict, rules_doc: Dict) -> List[str]:
    """Every problem in the pair of registry files; empty when they are consistent."""
    dims = rules_doc.get('dims', [])
    errors = _field_errors(fields_doc)
    if len(dims) != 6 or len(set(dims)) != 6:
        errors.append('dims must list six unique dimensions')
    for name, block in rules_doc.get('params', {}).items():
        if not block.get('source'):
            errors.append(f'params.{name}: missing source citation')
    names = {f.get('name') for f in fields_doc.get('fields', [])}
    return errors + _table_errors(rules_doc.get('tables', {})) + \
        _archetype_errors(rules_doc.get('archetypes', {}), dims, names)


def _known_keys(fields_doc: Dict) -> Dict[str, FrozenSet[str]]:
    keys = {role: set(fields_doc.get('ignored', {}).get(role, [])) | set(fields_doc.get('inputs', {}).get(role, []))
            for role in SOURCE_ROLES}
    for raw in fields_doc['fields']:
        if raw.get('source'):
            keys[raw['source']['role']].update(raw['source']['paths'])
    return {role: frozenset(names) for role, names in keys.items()}


def load_registry(directory: Path = REGISTRY_DIR) -> Registry:
    """Read, validate and freeze the registry; raise RegistryError listing every inconsistency."""
    fields_doc = json.loads((directory / 'fields.json').read_text())
    rules_doc = json.loads((directory / 'rules.json').read_text())
    errors = validate(fields_doc, rules_doc)
    if errors:
        raise RegistryError('; '.join(errors))
    specs = tuple(FieldSpec(f['name'], f['code'], f['type'], f.get('stored', True), f.get('source'), f.get('round'),
                            tuple(f['bins']) if f.get('bins') else None) for f in fields_doc['fields'])
    return Registry(fields_doc['version'], rules_doc['version'], specs, dict(fields_doc['link_bits']),
                    tuple(fields_doc.get('missing_tokens', [])), _known_keys(fields_doc), rules_doc)
