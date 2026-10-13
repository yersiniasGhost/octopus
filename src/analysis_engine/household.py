"""One ElectricalDB meter + the parcel documents matched to it -> one sparse household document.

Pure: no database access. Sources are already matched (sources.py) and thresholds come from the registry.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.analysis_engine import features
from src.analysis_engine.normalize import BLANK, PRESENT, UNMAPPED, read_value
from src.analysis_engine.registry import FieldSpec, Registry
from src.analysis_engine.usage import is_fresh, summarize_usage
from src.tools.parcel_id import parcel_key_of

PARCEL_ROLES = ('residential', 'demographic', 'thermal')


@dataclass
class ParcelMatch:
    residential: Optional[Dict] = None
    demographic: Optional[Dict] = None
    thermal: Optional[Dict] = None
    meters_on_parcel: int = 0
    linked: bool = False


@dataclass
class Assembled:
    doc: Dict[str, Any]
    unmapped_values: List[Tuple[str, Any]] = field(default_factory=list)


def _cast(spec: FieldSpec, value: Any) -> Any:
    if spec.type == 'int':
        return int(round(value))
    if spec.type == 'float':
        return round(float(value), spec.round)
    return bool(value)


def _read_sources(match: ParcelMatch, multi_unit: bool, reg: Registry):
    """Canonical values, link bitmask, linked-but-blank codes, and value_map misses from the matched parcels."""
    values, missing, unmapped, link = {}, set(), [], 1 << reg.link_bits['electrical']
    for role in PARCEL_ROLES:
        doc = getattr(match, role)
        if doc is None:
            continue
        link |= 1 << reg.link_bits[role]
        if role == 'thermal' and multi_unit:
            continue  # thermal fits exclude multi-meter parcels (T-06); the link bit still records the match
        for spec in reg.fields_for(role):
            state, value = read_value(doc, spec.source, reg.missing_tokens)
            if state == PRESENT:
                values[spec.name] = value
            elif state == BLANK and spec.stored:
                missing.add(spec.code)
            elif state == UNMAPPED:
                unmapped.append((spec.name, value))
    return values, link, missing, unmapped


def _derive(values: Dict, elec: Dict, county: str, build_month: int, reg: Registry) -> None:
    usage_params = reg.params('usage')
    usage = summarize_usage(elec.get('time_series_elec'), usage_params['min_span_days'],
                            usage_params['max_span_days'])
    fresh = is_fresh(usage.last_read, build_month, usage_params['max_age_months'])
    for name in ('months_usage', 'last_read', 'annual_kwh', 'peak_ratio'):
        if getattr(usage, name):
            values[name] = getattr(usage, name)
    utility = (elec.get('utility') or '').strip() or reg.default_utility(county)
    cost, basis = features.annual_cost(values.pop('vendor_kwh_cost', None), usage.annual_kwh, fresh,
                                       reg.rate(utility, county))
    income, size = values.get('income_est'), values.get('hh_size')
    if cost is not None:
        values['annual_cost'], values['burden_basis'] = cost, basis
        burden = features.energy_burden(cost, income)
        if burden is not None:
            values['energy_burden'] = burden
    if income and size:
        values['fpl_pct'] = features.fpl_pct(income, size, reg.table('fpg_2026'))
        hud = reg.hud(county)
        if hud is not None:
            extra = reg.table('hud_low_income_fy2026')['extra_person_pct_of_4']
            values['ami_pct'] = features.ami_pct(income, size, hud, extra)
    per_sqft = features.hl_per_sqft(values.get('hl_slope'), values.get('sqft'))
    if per_sqft is not None:
        values['hl_per_sqft'] = per_sqft


def assemble(elec: Dict, match: ParcelMatch, county: str, build_month: int, reg: Registry) -> Assembled:
    """Build the household document for one meter (no dims yet; rules.finalize adds them)."""
    multi_unit = match.linked and match.meters_on_parcel > 1
    values, link, missing, unmapped = _read_sources(match, multi_unit, reg)
    _derive(values, elec, county, build_month, reg)
    doc: Dict[str, Any] = {'_id': elec['_id'], 'county': county}
    key = parcel_key_of(elec)
    if key is not None:
        doc['parcel_key'] = key
    doc['link'] = link
    if match.linked:
        doc['multi_unit'] = multi_unit
    for spec in reg.fields:
        if spec.stored and spec.name in values:
            doc[spec.name] = _cast(spec, values[spec.name])
    if missing:
        doc['missing'] = sorted(missing)
    return Assembled(doc, unmapped)
