# Bulk Need Analysis — P1 Implementation Plan (registry + builder: Franklin, Cuyahoga, Adams)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/analysis_engine/` in octopus: a registry with cited threshold tables, plus a two-pass county
builder that writes one sparse, < 1 KB `analysis_households` document per electric meter for Franklin, Cuyahoga and
Adams, with one `analysis_builds` record per build.

**Architecture:** Pure core, thin I/O. `normalize` → `usage` / `features` → `household.assemble` →
`rules.finalize` are pure functions over plain dicts and are unit-tested exhaustively. `sources` reads a county's
collections into in-memory parcel indexes; `build` runs pass 1 (county distributions) and pass 2 (levels, staging),
checks gates, then hands off to a `Store` (`MongoStore` live, `DryRunStore` for `--dry-run`, `FakeStore` in tests).
All thresholds, codes and encodings live in `registry/fields.json` and `registry/rules.json`, which bolt-od will
copy.

**Tech Stack:** Python 3.10 (`venv`), pymongo 4.15.3 (`bson.encode` for sizes), pytest. No new dependencies.

**Spec:** `.claude_docs/20261008_1713_bulk_need_analysis_design.md` (approved 2026-10-12; read §14 amendments
first — gas is excluded, `ami_pct` replaces `smi_pct`, `burden_basis` re-encoded, `last_read` added).

## Global Constraints

- Database `empower_development` via `src.tools.mongo.get_empower_db()`. **Never write to a source collection.**
  Writes go only to `analysis_households`, `analysis_builds`, `analysis_households_staging_{County}`.
- **Gas is excluded entirely**: never read `CuyahogaGasDB`; never add `annual_gas_cost`; never infer fuel.
- **Unknown is never coerced to 0.** A dimension is `-1` unless its inputs are known.
- Document size: p99 < 1024 bytes (`bson.encode`), checked as a pre-swap gate.
- Sparse documents: absent field = missing. Never store `None`, `NaN`, `''` or `-1` as a feature value.
- No names, emails, phone numbers, addresses or `participant_id` in any analysis document.
- Thresholds and tables are read from the registry, never restated as literals in engine code.
- Python style: compact signatures on 1–2 lines (break only past 120 chars); match the docstring density of
  `src/tools/parcel_id.py`.
- Run tests with `source venv/bin/activate && python -m pytest tests/ -q -o addopts=""` (the pyproject `addopts`
  needs pytest-cov, which is not installed). Baseline at plan time: **293 passed**.
- The working tree carries **unrelated uncommitted changes** (`scripts/create_user.py`,
  `scripts/enrich_participants_franklin_demographics_tool.py`, `.gitignore`, `.claude_docs/script_descriptions.md`,
  `schema.md`, several `scripts/*_tool.py`). **Never `git add -A` or `git add .`** — stage exact paths only.
- Branch `feature/need-analysis`. Commit messages end with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **Stale meter** (last reading 2016-02, twelve good readings): `annual_kwh` is stored with `last_read`, but there is
   no `usage_pctile`, `high_usage = -1`, and no rate-computed `annual_cost`. Pinned in Task 5
   (`test_stale_meter_gets_no_computed_cost`) and Task 6 (`test_stale_meter_usage_is_unknown`).
2. **Cuyahoga `NaN` income / `poverty_level_percent = 0`**: income is blank (`missing` carries code 1), income need
   and burden are `-1`, never 0. Pinned in Task 2 (`test_nan_and_tokens_are_blank`) and Task 5
   (`test_nan_income_is_blank_not_zero`).
3. **Negative heating slope with a high r²** (a fit artifact, ~30 % of new thermal docs): not a usable fit; the household
   falls back to the year-built proxy. Pinned in Task 6 (`test_negative_slope_is_not_a_usable_fit`).
4. **Duplicate demographic docs on one parcel** (Franklin: up to 35): the most complete doc wins, independent of cursor
   order. Pinned in Task 8 (`test_most_complete_duplicate_wins_in_any_order`).
5. **Household size absent, zero, fractional or above 8**: absent/zero → income need unknown (no default size);
   `2.6` → 3; 9 extends both the HHS and HUD tables. Pinned in Task 2 (`test_count_transform`) and Task 5
   (`test_household_size_nine_extends_both_tables`, `test_missing_household_size_leaves_income_unknown`).

---

## File map

| File | Responsibility |
|---|---|
| `src/tools/parcel_id.py` (modify) | add `parcel_key_of`, `parcel_id_of`, `ParcelIndex` — shared by thermal tools and the engine |
| `scripts/calculate_missing_thermal_loads_tool.py` (modify) | use the shared helpers instead of private copies |
| `src/analysis_engine/__init__.py` | package marker |
| `src/analysis_engine/normalize.py` | blank detection (7 encodings), transforms, `read_value` |
| `src/analysis_engine/registry/fields.json` | canonical fields, codes, source paths, sentinels, ignored keys |
| `src/analysis_engine/registry/rules.json` | dims, thresholds, cited tables, archetypes |
| `src/analysis_engine/registry.py` | load + validate registry; lookups (`hud`, `rate`, `default_utility`) |
| `src/analysis_engine/usage.py` | meter time series → `months_usage`, `last_read`, `annual_kwh`, `peak_ratio` |
| `src/analysis_engine/features.py` | `fpl_pct`, `ami_pct`, `annual_cost`, `energy_burden`, `hl_per_sqft` |
| `src/analysis_engine/household.py` | `ParcelMatch`, `assemble()` — one meter + matched parcel docs → household doc |
| `src/analysis_engine/rules.py` | percentiles, cutpoints, six level functions, `finalize()` |
| `src/analysis_engine/archetypes.py` | archetype JSON → `$match` + known-enough `$match` |
| `src/analysis_engine/sources.py` | read county collections → `CountySources` (indexes, meter counts, drift tracker) |
| `src/analysis_engine/store.py` | `MongoStore`, `DryRunStore`, index creation |
| `src/analysis_engine/build.py` | two-pass county build, gates, failure handling |
| `src/analysis_engine/report.py` | build summary text; live per-county dimension/archetype counts |
| `src/analysis_engine/cli.py` | `build` / `report` commands |
| `tests/mongo_fakes.py` (modify) | add `FakeNamedDB` |
| `tests/analysis_fakes.py` | `monthly_series`, `elec`, `FakeStore` |
| `tests/test_parcel_index.py`, `tests/test_analysis_*.py` | one test file per module |
| `.claude_docs/tools.md` (modify) | document the CLI |

---

### Task 1: Shared parcel identity helpers

**Files:**
- Modify: `src/tools/parcel_id.py`
- Modify: `scripts/calculate_missing_thermal_loads_tool.py:259-296,314-322`
- Test: `tests/test_parcel_index.py`

**Interfaces:**
- Produces: `parcel_key_of(doc) -> Optional[str]`, `parcel_id_of(doc) -> Optional[str]`,
  `class ParcelIndex` with attributes `by_key: Dict[str, Any]`, `by_id: Dict[str, Any]` and methods
  `add(doc, value) -> None` (first value wins) and `resolve(doc) -> Tuple[Optional[Any], str]` where the string is
  `'parcel_key' | 'parcel_id' | 'unmatched'`.

- [ ] **Step 1: Commit the amended spec and this plan (docs only)**

```bash
git add .claude_docs/20261008_1713_bulk_need_analysis_design.md .claude_docs/20261012_1443_need_analysis_p1_plan.md
git commit -m "docs(need-analysis): amend spec from P1 data profiling, add P1 implementation plan

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing test** — `tests/test_parcel_index.py`

```python
"""ParcelIndex -- the dual parcel_key / parcel_id lookup, shared by the thermal tools and the analysis engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.parcel_id import ParcelIndex, parcel_id_of, parcel_key_of  # noqa: E402


def test_identity_helpers_normalize_and_treat_blank_as_absent():
    assert parcel_key_of({'parcel_key': ' 10-088712-00 '}) == '10-088712-00'
    assert parcel_id_of({'parcel_id': 30324005}) == '30324005'
    assert parcel_key_of({'parcel_key': ''}) is None
    assert parcel_id_of({}) is None


def test_resolve_prefers_parcel_key_then_parcel_id():
    index = ParcelIndex()
    index.add({'parcel_key': 'K1', 'parcel_id': 'I1'}, 'by-key-doc')
    index.add({'parcel_id': 123}, 'by-id-doc')
    assert index.resolve({'parcel_key': 'K1', 'parcel_id': 'zzz'}) == ('by-key-doc', 'parcel_key')
    assert index.resolve({'parcel_key': 'nope', 'parcel_id': '123'}) == ('by-id-doc', 'parcel_id')
    assert index.resolve({'parcel_id': 'I1'}) == ('by-key-doc', 'parcel_id')
    assert index.resolve({'parcel_id': None}) == (None, 'unmatched')


def test_first_value_added_wins():
    index = ParcelIndex()
    index.add({'parcel_key': 'K1'}, 'first')
    index.add({'parcel_key': 'K1'}, 'second')
    assert index.resolve({'parcel_key': 'K1'})[0] == 'first'
```

- [ ] **Step 3: Run it to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_parcel_index.py -q -o addopts=""`
Expected: FAIL — `ImportError: cannot import name 'ParcelIndex'`

- [ ] **Step 4: Implement** — append to `src/tools/parcel_id.py` (and change its typing import to
  `from typing import Any, Dict, Optional, Tuple`)

```python
def parcel_key_of(doc: Dict) -> Optional[str]:
    """The normalized parcel_key of a document, or None when it carries none."""
    return normalize_parcel_id(doc.get('parcel_key'))


def parcel_id_of(doc: Dict) -> Optional[str]:
    """The normalized parcel_id of a document, or None when it carries none."""
    return normalize_parcel_id(doc.get('parcel_id'))


class ParcelIndex:
    """Every spelling a parcel answers to -> one stored value.

    Two tables rather than one chosen key (T-04): parcel_key resolves counties whose sides differ by
    zero-padding, while four counties carry no parcel_key at all. Lookups try parcel_key first, then the
    normalized parcel_id. The first value added under a spelling wins, so callers that must choose among
    duplicates do so before adding.
    """

    def __init__(self):
        self.by_key: Dict[str, Any] = {}
        self.by_id: Dict[str, Any] = {}

    def add(self, doc: Dict, value: Any) -> None:
        key, ident = parcel_key_of(doc), parcel_id_of(doc)
        if key is not None:
            self.by_key.setdefault(key, value)
        if ident is not None:
            self.by_id.setdefault(ident, value)

    def resolve(self, doc: Dict) -> Tuple[Optional[Any], str]:
        key = parcel_key_of(doc)
        if key is not None and key in self.by_key:
            return self.by_key[key], 'parcel_key'
        ident = parcel_id_of(doc)
        if ident is not None and ident in self.by_id:
            return self.by_id[ident], 'parcel_id'
        return None, 'unmatched'
```

- [ ] **Step 5: Point the thermal tool at the shared helpers.** In
  `scripts/calculate_missing_thermal_loads_tool.py`: change the import to
  `from src.tools.parcel_id import ParcelIndex, normalize_parcel_id, parcel_id_of, parcel_key_of`; delete the
  `_key_value` and `_id_value` functions; replace the body of `_thermal_join_index` after its docstring with

```python
    index = ParcelIndex()
    for doc in db[f"{county}ThermalLoads"].find({}, {'parcel_id': 1, 'parcel_key': 1}):
        stored = doc.get('parcel_id')
        if stored not in (None, ''):
            index.add(doc, stored)
    return index.by_key, index.by_id
```

  and in `_resolve_to_thermal` replace `_key_value(doc)` with `parcel_key_of(doc)` and `_id_value(doc)` with
  `parcel_id_of(doc)`. Leave `normalize_parcel_id` imported only if `grep -n normalize_parcel_id` still finds a use
  in the file; otherwise drop it from the import.

- [ ] **Step 6: Run the new and the thermal tests**

Run: `python -m pytest tests/ -q -o addopts=""`
Expected: PASS — 296 passed (293 + 3 new). `tests/test_thermal_join_key.py` must stay green; it is the check that the
refactor preserved T-04 behaviour.

- [ ] **Step 7: Commit**

```bash
git add src/tools/parcel_id.py scripts/calculate_missing_thermal_loads_tool.py tests/test_parcel_index.py
git commit -m "refactor(parcel_id): share parcel_key/parcel_id lookup as ParcelIndex

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Normalization — blank values and transforms

**Files:**
- Create: `src/analysis_engine/__init__.py` (empty), `src/analysis_engine/normalize.py`
- Test: `tests/test_analysis_normalize.py`

**Interfaces:**
- Produces: constants `PRESENT, BLANK, ABSENT, UNMAPPED` (strings); `TRANSFORMS: Dict[str, Callable[[Any], Any]]`
  with keys `number, positive, count, year, money, years_range`; `is_blank(value, sentinels=(), tokens=()) -> bool`;
  `read_value(doc: Dict, source: Dict, tokens) -> Tuple[str, Any]`. A `source` dict has `paths: List[str]`,
  `transform: str`, optional `sentinels: List[number]`, optional `value_map: Dict[str, Any]` (used when
  `transform == 'value_map'`; a mapping to `null` means "known value that carries no information").

- [ ] **Step 1: Write the failing test** — `tests/test_analysis_normalize.py`

```python
"""Missing values arrive at least seven ways; every one of them must read as blank, never as a value."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.normalize import (ABSENT, BLANK, PRESENT, TRANSFORMS, UNMAPPED,  # noqa: E402
                                           is_blank, read_value)

TOKENS = ('nan', 'NaN', 'Unknown')


def test_nan_and_tokens_are_blank():
    for value in (None, float('nan'), '', '   ', 'nan', 'Unknown'):
        assert is_blank(value, (), TOKENS), value
    assert is_blank(-1, (-1,), TOKENS) and is_blank(-1.0, (-1,), TOKENS)
    assert is_blank(0, (0,), TOKENS)  # Cuyahoga poverty_level_percent = 0 co-occurs with NaN income


def test_real_values_are_not_blank():
    for value in (0, 0.0, False, 'No', 42000.0, -0.37):
        assert not is_blank(value, (-1,), TOKENS), value


def test_count_transform():
    count = TRANSFORMS['count']
    assert count(3.0) == 3 and count(2.6) == 3 and count('4') == 4
    assert count(0) is None and count(0.4) is None and count(float('nan')) is None


def test_money_years_and_year_transforms():
    assert TRANSFORMS['money']('$152,000') == 152000.0
    assert TRANSFORMS['money'](154000) == 154000.0
    assert TRANSFORMS['money']('$0') is None
    assert TRANSFORMS['years_range']('15+ years') == 15
    assert TRANSFORMS['years_range']('3-4 years') == 3
    assert TRANSFORMS['years_range']('Less than 1 year') == 0
    assert TRANSFORMS['years_range']('soon') is None
    assert TRANSFORMS['year'](1958) == 1958 and TRANSFORMS['year'](0) is None and TRANSFORMS['year'](1500) is None
    assert TRANSFORMS['positive'](-5) is None and TRANSFORMS['number'](-0.37) == -0.37
    assert TRANSFORMS['number'](True) is None and TRANSFORMS['number']('x') is None


SENIOR = {'paths': ['md_presence_of_senior', 'presence_of_senior'], 'transform': 'value_map',
          'value_map': {'Senior Present': True, 'No Senior Present': False, 'Yes': True, 'No': False}}
INCOME = {'paths': ['estimated_income'], 'transform': 'positive', 'sentinels': [-1]}
HEAT = {'paths': ['heat_type'], 'transform': 'value_map', 'value_map': {'HTP': 1, 'FHA': None}}


def test_read_value_states():
    assert read_value({'estimated_income': 42000.0}, INCOME, TOKENS) == (PRESENT, 42000.0)
    assert read_value({'estimated_income': -1}, INCOME, TOKENS) == (BLANK, None)
    assert read_value({'estimated_income': math.nan}, INCOME, TOKENS) == (BLANK, None)
    assert read_value({'estimated_income': 0}, INCOME, TOKENS) == (BLANK, None)
    assert read_value({}, INCOME, TOKENS) == (ABSENT, None)


def test_blank_first_path_falls_through_to_the_next():
    assert read_value({'md_presence_of_senior': '', 'presence_of_senior': 'Yes'}, SENIOR, TOKENS) == (PRESENT, True)
    assert read_value({'md_presence_of_senior': 'No Senior Present'}, SENIOR, TOKENS) == (PRESENT, False)
    assert read_value({'md_presence_of_senior': ''}, SENIOR, TOKENS) == (BLANK, None)


def test_value_map_misses_are_unmapped_and_null_mappings_absent():
    assert read_value({'md_presence_of_senior': 'Maybe'}, SENIOR, TOKENS) == (UNMAPPED, 'Maybe')
    assert read_value({'heat_type': 'HTP'}, HEAT, TOKENS) == (PRESENT, 1)
    assert read_value({'heat_type': 'FHA'}, HEAT, TOKENS) == (ABSENT, None)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_normalize.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine'`

- [ ] **Step 3: Implement** — `src/analysis_engine/__init__.py` (empty file) and `src/analysis_engine/normalize.py`

```python
"""Source value → canonical value, with every encoding of "missing" reading as blank.

Measured encodings (spec §3): absent field, None, -1, '', float NaN, the strings 'nan' / 'Unknown', and
field-specific sentinels. Per-field sentinels come from fields.json; the string tokens are global.
"""

import math
import re
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

PRESENT, BLANK, ABSENT, UNMAPPED = 'present', 'blank', 'absent', 'unmapped'

_MONEY_STRIP = re.compile(r'[$,\s]')
_LEADING_INT = re.compile(r'^(\d+)')


def is_blank(value: Any, sentinels: Iterable = (), tokens: Iterable[str] = ()) -> bool:
    """True when a raw source value means "no data"."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == '' or stripped in tokens
    return isinstance(value, (int, float)) and value in tuple(sentinels)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _positive(value: Any) -> Optional[float]:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _count(value: Any) -> Optional[int]:
    number = _number(value)
    count = int(round(number)) if number is not None else 0
    return count if count >= 1 else None


def _year(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None and 1700 <= number <= 2100 else None


def _money(value: Any) -> Optional[float]:
    return _positive(_MONEY_STRIP.sub('', value) if isinstance(value, str) else value)


def _years_range(value: Any) -> Optional[int]:
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith('less than'):
            return 0
        match = _LEADING_INT.match(text)
        return int(match.group(1)) if match else None
    number = _number(value)
    return int(number) if number is not None and number >= 0 else None


TRANSFORMS: Dict[str, Callable[[Any], Any]] = {
    'number': _number, 'positive': _positive, 'count': _count,
    'year': _year, 'money': _money, 'years_range': _years_range,
}


def read_value(doc: Dict, source: Dict, tokens: Iterable[str]) -> Tuple[str, Any]:
    """Resolve one canonical field from one source document.

    Paths are tried in priority order and the first usable value wins. A path that exists but holds a blank
    or out-of-range value makes the field BLANK unless a later path supplies a value; no path present at all is
    ABSENT. A value_map miss is UNMAPPED (a drift signal the build reports); a value mapped to None is a known
    value that carries no information, so it reads as ABSENT.
    """
    sentinels, value_map = tuple(source.get('sentinels', ())), source.get('value_map')
    state, unmapped = ABSENT, None
    for path in source['paths']:
        if path not in doc:
            continue
        raw = doc[path]
        if is_blank(raw, sentinels, tokens):
            state = BLANK
            continue
        if value_map is not None:
            key = raw.strip() if isinstance(raw, str) else raw
            if key not in value_map:
                unmapped = raw
                continue
            return (ABSENT, None) if value_map[key] is None else (PRESENT, value_map[key])
        value = TRANSFORMS[source['transform']](raw)
        if value is None:
            state = BLANK
            continue
        return PRESENT, value
    return (UNMAPPED, unmapped) if unmapped is not None else (state, None)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_analysis_normalize.py -q -o addopts=""`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/analysis_engine/__init__.py src/analysis_engine/normalize.py tests/test_analysis_normalize.py
git commit -m "feat(analysis): normalize source values, reading all seven missing encodings as blank

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Registry — fields.json, rules.json (cited tables), loader and validator

**Files:**
- Create: `src/analysis_engine/registry/fields.json`, `src/analysis_engine/registry/rules.json`,
  `src/analysis_engine/registry.py`
- Test: `tests/test_analysis_registry.py`

**Interfaces:**
- Consumes: `TRANSFORMS` from `normalize`.
- Produces: `load_registry(directory: Path = REGISTRY_DIR) -> Registry`; `validate(fields_doc, rules_doc) -> List[str]`;
  `RegistryError(ValueError)`; `SOURCE_ROLES = ('electrical','residential','demographic','thermal','multitenant')`;
  `FieldSpec(name, code, type, stored=True, source=None, round=None, bins=None)` with property `role`;
  `Registry` with attributes `fields_version, rules_version, fields: Tuple[FieldSpec], link_bits: Dict[str,int],
  missing_tokens: Tuple[str], known_keys: Dict[role, FrozenSet[str]], rules: Dict` and methods
  `dims` (property, list of 6 names), `params(name)`, `table(name)`, `fields_for(role)`, `field(name)`,
  `hud(county) -> Optional[Dict]`, `default_utility(county) -> Optional[str]`,
  `rate(utility, county) -> Optional[float]` (USD/kWh; key `"{utility}:{county}"` first, then `utility`).

- [ ] **Step 1: Write `src/analysis_engine/registry/fields.json`**

The `ignored` lists come from a 2,000-document sample per collection (2026-10-12). Anything a live build sees outside
`paths ∪ inputs ∪ ignored` is reported in `analysis_builds.unmapped_fields`, never silently dropped.

```json
{
  "version": "2026-10-12.1",
  "link_bits": {"electrical": 0, "residential": 1, "demographic": 2, "thermal": 3, "gas": 4, "enrollment": 5},
  "missing_tokens": ["nan", "NaN", "Unknown"],
  "inputs": {"electrical": ["time_series_elec", "utility"]},
  "ignored": {
    "electrical": ["_id", "parcel_id", "parcel_key", "monthly_averages", "monthly_minimums", "monthly_maximums",
                   "last_utility_ingest", "account_id", "county", "service_address", "service_city", "service_zip5",
                   "source_delivery", "annual_average"],
    "residential": ["_id", "parcel_id", "parcel_key", "parcel_zip", "parcel_city", "address", "parcel_owner", "rcn",
                    "rcnld", "energy_percentile", "unnamed: 0", "tax_luc_description", "construction_quality",
                    "effective_age", "condition", "air_conditioning", "rooms", "bedrooms", "bathrooms", "half_baths",
                    "garage_size", "living_area_1", "living_area_2"],
    "demographic": ["_id", "parcel_id", "parcel_key", "customer_name", "address", "service_city", "parcel_zip",
                    "email", "mobile", "income_level", "annual_gas_cost", "energy_burden_kwh", "energy_burden_gas",
                    "total_energy_burden", "cars", "number_of_vehicles", "source", "ingested_at", "md_education",
                    "md_marital_status", "md_gender", "md_occupation", "md_median_household_income", "sqft",
                    "year_built", "energy_percentile", "children_age_range", "date_of_birth", "enriched_at",
                    "enriched_from", "marital_status", "number_of_adults", "owner_age", "parcel_id_backfilled_at",
                    "parcel_id_source", "estimated_income_original", "income_fix_date", "income_fix_reason",
                    "total_energy_burden_original", "backfill_at", "backfill_fields", "backfill_from",
                    "poverty_level_percent"],
    "thermal": ["_id", "parcel_id", "parcel_key", "gas_hl_cl_loads", "kwh_hl_cl_loads", "calculated_at",
                "calculation_source", "kwh_intercept", "kwh_model", "kwh_periods", "kwh_periods_dropped",
                "weather_location", "weather_range", "weather_source", "gas_hl_slope", "gas_hl_intercept",
                "gas_hl_r2", "gas_cl_slope", "gas_cl_intercept", "gas_cl_r2", "kwh_hl_intercept", "kwh_hl_r2",
                "kwh_cl_intercept", "kwh_cl_r2"],
    "multitenant": ["_id", "parcel_id", "parcel_zip", "parcel_owner", "parcel_city", "description", "address"]
  },
  "fields": [
    {"name": "income_est", "code": 1, "type": "int",
     "source": {"role": "demographic", "paths": ["estimated_income"], "transform": "positive", "sentinels": [-1]}},
    {"name": "hh_size", "code": 2, "type": "int",
     "source": {"role": "demographic", "paths": ["md_householdsize", "household_size"], "transform": "count",
                "sentinels": [-1]}},
    {"name": "fpl_pct", "code": 3, "type": "int", "derived": true,
     "bins": [0, 50, 100, 138, 150, 175, 200, 250, 300, 400, 500]},
    {"name": "ami_pct", "code": 4, "type": "int", "derived": true, "bins": [0, 30, 50, 60, 80, 100, 120, 150, 200]},
    {"name": "annual_kwh", "code": 5, "type": "int", "derived": true},
    {"name": "annual_cost", "code": 6, "type": "int", "derived": true},
    {"name": "energy_burden", "code": 7, "type": "float", "round": 1, "derived": true,
     "bins": [0, 2, 4, 6, 8, 10, 15, 20, 30]},
    {"name": "burden_basis", "code": 8, "type": "int", "derived": true},
    {"name": "usage_pctile", "code": 9, "type": "int", "derived": true,
     "bins": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]},
    {"name": "peak_ratio", "code": 10, "type": "float", "round": 2, "derived": true},
    {"name": "months_usage", "code": 11, "type": "int", "derived": true},
    {"name": "last_read", "code": 12, "type": "int", "derived": true},
    {"name": "hl_slope", "code": 13, "type": "float", "round": 5,
     "source": {"role": "thermal", "paths": ["kwh_hl_slope"], "transform": "number"}},
    {"name": "cl_slope", "code": 14, "type": "float", "round": 5,
     "source": {"role": "thermal", "paths": ["kwh_cl_slope"], "transform": "number"}},
    {"name": "thermal_r2", "code": 15, "type": "float", "round": 3,
     "source": {"role": "thermal", "paths": ["kwh_r2"], "transform": "number"}},
    {"name": "hl_per_sqft", "code": 16, "type": "float", "round": 8, "derived": true},
    {"name": "year_built", "code": 17, "type": "int",
     "source": {"role": "residential", "paths": ["age"], "transform": "year", "sentinels": [-1]}},
    {"name": "sqft", "code": 18, "type": "int",
     "source": {"role": "residential", "paths": ["living_area_total"], "transform": "positive", "sentinels": [-1]}},
    {"name": "stories", "code": 19, "type": "float", "round": 1,
     "source": {"role": "residential", "paths": ["story_height"], "transform": "positive", "sentinels": [-1]}},
    {"name": "home_value", "code": 20, "type": "int",
     "source": {"role": "demographic", "paths": ["md_estimated_home_value", "estimated_home_value"],
                "transform": "money", "sentinels": [-1]}},
    {"name": "owner", "code": 21, "type": "bool",
     "source": {"role": "demographic", "paths": ["md_own_rent"], "transform": "value_map",
                "value_map": {"Definite Owner": true, "Probable Owner": true,
                              "Definite Renter": false, "Probable Renter": false}}},
    {"name": "senior", "code": 22, "type": "bool",
     "source": {"role": "demographic", "paths": ["md_presence_of_senior", "presence_of_senior"],
                "transform": "value_map",
                "value_map": {"Senior Present": true, "No Senior Present": false, "Yes": true, "No": false}}},
    {"name": "children", "code": 23, "type": "bool",
     "source": {"role": "demographic", "paths": ["md_presence_of_children", "presence_of_children", "children_present"],
                "transform": "value_map",
                "value_map": {"Children Present": true, "No Children Present": false, "Yes": true, "No": false,
                              "Y": true, "N": false}}},
    {"name": "length_residence", "code": 24, "type": "int",
     "source": {"role": "demographic", "paths": ["md_length_of_residence", "length_of_residence"],
                "transform": "years_range"}},
    {"name": "heat_fuel", "code": 25, "type": "int",
     "source": {"role": "residential", "paths": ["heat_type"], "transform": "value_map",
                "value_map": {"HTP": 1, "FHA": null, "HWS": null, "GRV": null, "RAD": null, "UNH": null,
                              "N": null, "OTH": null}}},
    {"name": "multi_unit", "code": 26, "type": "bool", "derived": true},
    {"name": "vendor_kwh_cost", "code": 27, "type": "float", "round": 2, "stored": false,
     "source": {"role": "demographic", "paths": ["annual_kwh_cost"], "transform": "positive", "sentinels": [-1]}}
  ]
}
```

- [ ] **Step 2: Write `src/analysis_engine/registry/rules.json`**

All table values below were fetched from the cited URL on 2026-10-12. Do not edit a number without re-fetching it and
updating `retrieved`.

```json
{
  "version": "2026-10-12.1",
  "dims": ["income_need", "energy_burden", "building_inefficiency", "high_usage", "vulnerability", "electrification"],
  "params": {
    "income_need": {"fpl_high": 175, "fpl_moderate": 200, "ami_moderate": 80,
      "source": "HEAP and PIPP Plus at or below 175% FPG, HWAP at or below 200% FPG: ODJFS https://jfs.ohio.gov/public-assistance/energy-and-community-assistance (administrator since 2026-07-01; retrieved 2026-10-12). 80% AMI = HUD 'Low Income' limit, table hud_low_income_fy2026."},
    "energy_burden": {"high": 10, "moderate": 6,
      "source": "ACEEE, How High Are Household Energy Burdens? (2020): high burden above 6%, severe above 10%. https://www.aceee.org/research-report/u2006"},
    "building_inefficiency": {"r2_min": 0.5, "high_pctile": 80, "moderate_pctile": 60, "proxy_built_before": 1980,
      "source": "Engine choice: spec 20261008_1713 §6 (top 20% / 20-40% of county hl_per_sqft among usable fits)."},
    "high_usage": {"high_pctile": 90, "moderate_pctile": 75, "source": "Engine choice: spec 20261008_1713 §6."},
    "usage": {"max_age_months": 24, "min_span_days": 300, "max_span_days": 400,
      "source": "Engine choice: spec 20261008_1713 §5.4 and §14 amendment 5."},
    "electrification": {"high_fuels": [2],
      "source": "Spec 20261008_1713 §6 and §14 amendments 1-2: measured heat_fuel only, gas excluded."}
  },
  "tables": {
    "fpg_2026": {
      "source": {"title": "HHS Poverty Guidelines 2026, 48 contiguous states and DC",
                 "url": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines",
                 "published": "2026-01-15", "retrieved": "2026-10-12"},
      "base": [15960, 21640, 27320, 33000, 38680, 44360, 50040, 55720],
      "per_additional": 5680
    },
    "hud_low_income_fy2026": {
      "source": {"title": "HUD FY2026 Income Limits for Section 8, 80% 'Low Income' limits and median2026",
                 "url": "https://www.huduser.gov/portal/datasets/il/il26/Section8-FY26.xlsx",
                 "published": "2026-05-01", "retrieved": "2026-10-12",
                 "note": "Sizes above 8 add 8% of the 4-person limit per additional person (HUD methodology)."},
      "extra_person_pct_of_4": 8,
      "counties": {
        "Franklin": {"area": "Columbus, OH HUD Metro FMR Area (METRO18140M18140)", "median_family_income": 111500,
                     "limits": [62450, 71400, 80300, 89200, 96350, 103500, 110650, 117750]},
        "Cuyahoga": {"area": "Cleveland, OH HUD Metro FMR Area (METRO17410N17460)", "median_family_income": 105000,
                     "limits": [58800, 67200, 75600, 84000, 90750, 97450, 104200, 110900]},
        "Adams": {"area": "Adams County, OH (NCNTY39001N39001)", "median_family_income": 67200,
                  "limits": [49150, 56150, 63150, 70150, 75800, 81400, 87000, 92600]}
      }
    },
    "electric_rates_2025": {
      "source": {"title": "EIA-861 2025 final, Sales_Ult_Cust_2025.xlsx sheet States, Part A bundled residential; price = revenue / sales",
                 "url": "https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip",
                 "published": "2026-10-07", "retrieved": "2026-10-12",
                 "note": "Standard-offer bundled price, computed from published revenue and sales; customers on a retail supplier pay that supplier's generation price."},
      "usd_per_kwh": {"AEP": 0.18972406, "FE:Cuyahoga": 0.16217686, "FE": 0.16005921, "DUKE": 0.16826748},
      "eia_utility": {"AEP": "Ohio Power Co (14006)", "FE:Cuyahoga": "Cleveland Electric Illum Co (3755)",
                      "FE": "Ohio Edison Co (13998)", "DUKE": "Duke Energy Ohio Inc (3542)"}
    },
    "county_default_utility": {
      "source": {"title": "Engine assumption for meters with no utility field: dominant investor-owned utility in the county",
                 "url": "spec 20261008_1713 §6", "retrieved": "2026-10-12",
                 "note": "Cuyahoga also has Cleveland Public Power customers; they are priced at CEI's rate."},
      "map": {"Franklin": "AEP", "Cuyahoga": "FE", "Adams": "AEP"}
    }
  },
  "archetypes": {
    "bill_assistance": {"label": "Bill assistance candidate",
                        "all": [{"dim": "income_need", "op": ">=", "value": 2}]},
    "weatherization": {"label": "Weatherization candidate",
                       "all": [{"dim": "income_need", "op": ">=", "value": 1},
                               {"dim": "building_inefficiency", "op": ">=", "value": 1},
                               {"field": "multi_unit", "op": "!=", "value": true}]},
    "electrification": {"label": "Electrification candidate",
                        "all": [{"dim": "electrification", "op": "==", "value": 2},
                                {"field": "owner", "op": "!=", "value": false, "unknown_ok": true}]},
    "behavioural": {"label": "Behavioural / efficiency (no income test)",
                    "all": [{"dim": "high_usage", "op": ">=", "value": 1},
                            {"dim": "income_need", "op": "==", "value": 0}]},
    "likely_no_benefit": {"label": "Likely no benefit", "kind": "no_known_need", "min_known": 4}
  }
}
```

- [ ] **Step 3: Verify the one citation that was not fetched by the research pass**

Run: `curl -sI https://www.aceee.org/research-report/u2006 | head -1`
Expected: `HTTP/2 200` (or a 301 to the report). If it 404s, find the report "How High Are Household Energy
Burdens?" on aceee.org, put its URL in `params.energy_burden.source`, and note the substitution in the commit message.

- [ ] **Step 4: Write the failing test** — `tests/test_analysis_registry.py`

```python
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
```

- [ ] **Step 5: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_registry.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.registry'`

- [ ] **Step 6: Implement** — `src/analysis_engine/registry.py`

```python
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
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_analysis_registry.py -q -o addopts=""`
Expected: PASS (7 tests)

- [ ] **Step 8: Commit**

```bash
git add src/analysis_engine/registry.py src/analysis_engine/registry/fields.json \
        src/analysis_engine/registry/rules.json tests/test_analysis_registry.py
git commit -m "feat(analysis): registry with cited FPG/HUD/EIA tables, loader and validator

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Meter usage summary

**Files:**
- Create: `src/analysis_engine/usage.py`
- Create: `tests/analysis_fakes.py` (the `monthly_series` and `elec` builders; `FakeStore` is added in Task 9)
- Test: `tests/test_analysis_usage.py`

**Interfaces:**
- Produces: `Usage(months_usage: int, last_read: Optional[int], annual_kwh: Optional[int] = None,
  peak_ratio: Optional[float] = None)` (frozen dataclass); `summarize_usage(series, min_span_days, max_span_days)
  -> Usage`; `months_between(earlier: int, later: int) -> int` (both `YYYYMM`);
  `is_fresh(last_read: Optional[int], build_month: int, max_age_months: int) -> bool`.
- Test helpers produced: `monthly_series(start_year, start_month, values) -> Dict[str, float]` (keys
  `'YYYY-MM-15 00:00:00'`, one per month); `elec(_id, series=None, **fields) -> Dict`.

Rules: readings with unparseable dates or non-finite / negative values are dropped. `last_read` is the latest
reading's `YYYYMM`. `months_usage` = distinct months among readings within 365 days of the latest (cap 12).
`annual_kwh` and `peak_ratio` exist only when the latest 12 readings span `min_span_days`–`max_span_days`.

- [ ] **Step 1: Write the test helpers** — `tests/analysis_fakes.py`

```python
"""Builders for analysis_engine tests: meter time series and ElectricalDB documents."""

from typing import Dict, List


def monthly_series(start_year: int, start_month: int, values: List[float]) -> Dict[str, float]:
    """One reading on the 15th of each month, keyed the way ElectricalDB stores time_series_elec."""
    series = {}
    for i, value in enumerate(values):
        year, month = divmod(start_month - 1 + i, 12)
        series[f'{start_year + year}-{month + 1:02d}-15 00:00:00'] = value
    return series


def elec(_id, series=None, **fields) -> Dict:
    """An ElectricalDB document; parcel_id / parcel_key / utility go in fields."""
    return {'_id': _id, 'time_series_elec': series or {}, **fields}
```

- [ ] **Step 2: Write the failing test** — `tests/test_analysis_usage.py`

```python
"""A meter's time series -> how much of a year we have, when it last read, and its annual total."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.usage import is_fresh, months_between, summarize_usage  # noqa: E402
from tests.analysis_fakes import monthly_series  # noqa: E402


def _summary(series):
    return summarize_usage(series, 300, 400)


def test_full_year_gives_annual_total_and_peak_ratio():
    usage = _summary(monthly_series(2025, 8, [900.0] * 11 + [1800.0]))
    assert usage.annual_kwh == 11700 and usage.months_usage == 12 and usage.last_read == 202607
    assert usage.peak_ratio == round(1800 / (11700 / 12), 2)


def test_only_the_latest_twelve_readings_count():
    usage = _summary(monthly_series(2024, 8, [100.0] * 12 + [500.0] * 12))
    assert usage.annual_kwh == 6000 and usage.last_read == 202607


def test_partial_year_has_no_annual_total():
    usage = _summary(monthly_series(2026, 1, [400.0] * 7))
    assert usage.months_usage == 7 and usage.annual_kwh is None and usage.peak_ratio is None


def test_twelve_readings_spread_over_a_gap_have_no_annual_total():
    series = monthly_series(2023, 1, [400.0] * 6)
    series.update(monthly_series(2025, 1, [400.0] * 6))
    assert _summary(series).annual_kwh is None


def test_bad_readings_are_dropped():
    series = monthly_series(2025, 8, [900.0] * 12)
    series['2026-07-15 00:00:00'] = float('nan')
    series['not a date'] = 5.0
    series['2026-06-15 00:00:00'] = -40.0
    usage = _summary(series)
    assert usage.annual_kwh is None and usage.months_usage == 10


def test_empty_series():
    assert _summary({}) == _summary(None)
    assert _summary({}).months_usage == 0 and _summary({}).last_read is None


def test_stale_meter_is_summarized_but_not_fresh():
    usage = _summary(monthly_series(2015, 3, [700.0] * 12))
    assert usage.annual_kwh == 8400 and usage.last_read == 201602
    assert months_between(201602, 202610) == 128
    assert not is_fresh(usage.last_read, 202610, 24)
    assert is_fresh(202607, 202610, 24) and is_fresh(202410, 202610, 24) and not is_fresh(None, 202610, 24)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_usage.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.usage'`

- [ ] **Step 4: Implement** — `src/analysis_engine/usage.py`

```python
"""A meter's time_series_elec -> months covered, last reading, annual kWh and peak ratio.

The raw series is never copied to the household document; only these derived values are (spec §4).
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Usage:
    months_usage: int
    last_read: Optional[int]
    annual_kwh: Optional[int] = None
    peak_ratio: Optional[float] = None


def _yyyymm(day: date) -> int:
    return day.year * 100 + day.month


def months_between(earlier: int, later: int) -> int:
    """Whole months from one YYYYMM to another."""
    return (later // 100 * 12 + later % 100) - (earlier // 100 * 12 + earlier % 100)


def is_fresh(last_read: Optional[int], build_month: int, max_age_months: int) -> bool:
    """True when the meter read within max_age_months of the build month."""
    return last_read is not None and months_between(last_read, build_month) <= max_age_months


def _readings(series: Optional[Dict]) -> List[Tuple[date, float]]:
    rows = []
    for key, value in (series or {}).items():
        try:
            day = datetime.strptime(str(key)[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            continue
        rows.append((day, float(value)))
    return sorted(rows)


def summarize_usage(series: Optional[Dict], min_span_days: int, max_span_days: int) -> Usage:
    """Summarize one meter. Annual values need the latest 12 readings to span a plausible year."""
    rows = _readings(series)
    if not rows:
        return Usage(months_usage=0, last_read=None)
    latest = rows[-1][0]
    months = len({_yyyymm(day) for day, _ in rows if (latest - day).days < 365})
    base = Usage(months_usage=min(months, 12), last_read=_yyyymm(latest))
    year = rows[-12:]
    span = (year[-1][0] - year[0][0]).days
    total = sum(value for _, value in year)
    if len(year) < 12 or not min_span_days <= span <= max_span_days or total <= 0:
        return base
    peak = max(value for _, value in year) / (total / 12)
    return Usage(base.months_usage, base.last_read, int(round(total)), round(peak, 2))
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_analysis_usage.py -q -o addopts=""`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add src/analysis_engine/usage.py tests/analysis_fakes.py tests/test_analysis_usage.py
git commit -m "feat(analysis): summarize meter time series into annual kWh, months covered and last read

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Derived features and household assembly

**Files:**
- Create: `src/analysis_engine/features.py`, `src/analysis_engine/household.py`
- Test: `tests/test_analysis_household.py`

**Interfaces:**
- Consumes: `read_value, PRESENT, BLANK, UNMAPPED` (Task 2); `Registry` (Task 3); `summarize_usage, is_fresh`
  (Task 4); `parcel_key_of` (Task 1).
- Produces (features): `fpl_pct(income, hh_size, fpg: Dict) -> int`;
  `ami_pct(income, hh_size, hud_county: Dict, extra_pct: float) -> int`;
  `annual_cost(vendor_cost, annual_kwh, fresh, rate) -> Tuple[Optional[int], Optional[int]]` (cost, basis);
  `energy_burden(cost, income) -> Optional[float]`; `hl_per_sqft(hl_slope, sqft) -> Optional[float]`.
- Produces (household): `ParcelMatch(residential=None, demographic=None, thermal=None, meters_on_parcel=0,
  multitenant=False, linked=False)` (dataclass); `Assembled(doc: Dict, unmapped_values: List[Tuple[str, Any]])`;
  `assemble(elec: Dict, match: ParcelMatch, county: str, build_month: int, reg: Registry) -> Assembled`.
  The doc has `_id, county, [parcel_key], link, [multi_unit]`, feature fields, `[missing]` — no `dims` yet.

- [ ] **Step 1: Write the failing test** — `tests/test_analysis_household.py`

```python
"""One meter plus whatever parcel documents matched it -> one sparse household document."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.household import ParcelMatch, assemble  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from tests.analysis_fakes import elec, monthly_series  # noqa: E402

REG = load_registry()
BM = 202610
FULL_YEAR = monthly_series(2025, 8, [900.0] * 11 + [1800.0])
STALE_YEAR = monthly_series(2015, 3, [700.0] * 12)


def _linked(**parcels):
    return ParcelMatch(linked=True, meters_on_parcel=1, **parcels)


def _doc(meter, match, county='Franklin'):
    return assemble(meter, match, county, BM, REG).doc


def test_unlinked_meter_is_usage_only():
    doc = _doc(elec('E1', FULL_YEAR, utility='AEP'), ParcelMatch(), 'Adams')
    assert doc['link'] == 1 and 'parcel_key' not in doc and 'multi_unit' not in doc
    assert (doc['annual_kwh'], doc['months_usage'], doc['last_read']) == (11700, 12, 202607)
    assert doc['annual_cost'] == int(round(11700 * 0.18972406)) and doc['burden_basis'] == 0
    assert 'energy_burden' not in doc and 'fpl_pct' not in doc and 'missing' not in doc


def test_meter_without_utility_uses_county_default_rate():
    doc = _doc(elec('E1', FULL_YEAR), ParcelMatch(), 'Cuyahoga')
    assert doc['annual_cost'] == int(round(11700 * 0.16217686))


def test_income_and_size_give_fpl_and_ami():
    demo = {'parcel_key': 'P1', 'estimated_income': 42000.0, 'md_householdsize': 3.0}
    doc = _doc(elec('E2', FULL_YEAR, parcel_key='P1'), _linked(demographic=demo))
    assert doc['fpl_pct'] == round(100 * 42000 / 27320) == 154
    assert doc['ami_pct'] == round(80 * 42000 / 80300) == 42
    assert doc['link'] == 1 | 4 and doc['parcel_key'] == 'P1' and doc['multi_unit'] is False


def test_household_size_nine_extends_both_tables():
    demo = {'estimated_income': 60000.0, 'md_householdsize': 9.0}
    doc = _doc(elec('E3', FULL_YEAR, parcel_id='9'), _linked(demographic=demo))
    assert doc['fpl_pct'] == round(100 * 60000 / (55720 + 5680))
    assert doc['ami_pct'] == round(80 * 60000 / (117750 + 89200 * 0.08))


def test_missing_household_size_leaves_income_unknown():
    demo = {'estimated_income': 42000.0, 'md_householdsize': -1.0}
    doc = _doc(elec('E4', FULL_YEAR, parcel_id='4'), _linked(demographic=demo))
    assert 'hh_size' not in doc and 'fpl_pct' not in doc and 'ami_pct' not in doc
    assert doc['income_est'] == 42000 and 2 in doc['missing']


def test_nan_income_is_blank_not_zero():
    demo = {'estimated_income': math.nan, 'md_householdsize': 2.0, 'poverty_level_percent': 0.0}
    doc = _doc(elec('E5', FULL_YEAR, parcel_id='5'), _linked(demographic=demo), 'Cuyahoga')
    assert 'income_est' not in doc and 'energy_burden' not in doc and 1 in doc['missing']


def test_vendor_cost_wins_and_ignores_staleness():
    demo = {'estimated_income': 42000.0, 'md_householdsize': 3.0, 'annual_kwh_cost': 1720.4}
    doc = _doc(elec('E6', STALE_YEAR, parcel_id='6'), _linked(demographic=demo))
    assert (doc['annual_cost'], doc['burden_basis'], doc['energy_burden']) == (1720, 1, 4.1)
    assert 'vendor_kwh_cost' not in doc


def test_stale_meter_gets_no_computed_cost():
    doc = _doc(elec('E7', STALE_YEAR, utility='AEP'), ParcelMatch(), 'Adams')
    assert doc['annual_kwh'] == 8400 and doc['last_read'] == 201602
    assert 'annual_cost' not in doc and 'burden_basis' not in doc


THERMAL = {'kwh_hl_slope': 0.142, 'kwh_cl_slope': 0.311, 'kwh_r2': 0.82}
RESIDENTIAL = {'living_area_total': 1510.0, 'age': 1958, 'story_height': 1.0, 'heat_type': 'FHA'}


def test_thermal_and_sqft_give_hl_per_sqft():
    doc = _doc(elec('E8', FULL_YEAR, parcel_id='8'), _linked(residential=RESIDENTIAL, thermal=THERMAL))
    assert doc['hl_per_sqft'] == round(0.142 / 1510, 8)
    assert (doc['year_built'], doc['sqft'], doc['stories'], doc['thermal_r2']) == (1958, 1510, 1.0, 0.82)
    assert 'heat_fuel' not in doc and doc['link'] == 1 | 2 | 8


def test_multi_meter_parcel_drops_thermal_but_keeps_link_bit():
    match = ParcelMatch(linked=True, meters_on_parcel=2, residential=RESIDENTIAL, thermal=THERMAL)
    doc = _doc(elec('E9', FULL_YEAR, parcel_id='9'), match)
    assert doc['multi_unit'] is True and doc['link'] & 8
    assert 'hl_slope' not in doc and 'hl_per_sqft' not in doc


def test_multitenant_parcel_is_multi_unit():
    doc = _doc(elec('E10', FULL_YEAR, parcel_id='10'), _linked(multitenant=True))
    assert doc['multi_unit'] is True


def test_heat_pump_is_measured_electric():
    doc = _doc(elec('E11', FULL_YEAR, parcel_id='11'), _linked(residential={'heat_type': 'HTP'}), 'Cuyahoga')
    assert doc['heat_fuel'] == 1


def test_md_blank_falls_back_and_unmapped_values_are_reported():
    demo = {'md_presence_of_senior': '', 'presence_of_senior': 'Yes', 'md_own_rent': 'Maybe'}
    result = assemble(elec('E12', FULL_YEAR, parcel_id='12'), _linked(demographic=demo), 'Franklin', BM, REG)
    assert result.doc['senior'] is True and 'owner' not in result.doc
    assert result.unmapped_values == [('owner', 'Maybe')]
    assert 22 not in result.doc.get('missing', [])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_household.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.household'`

- [ ] **Step 3: Implement** — `src/analysis_engine/features.py`

```python
"""Derived household features. Pure functions; every table they use is passed in from the registry."""

from typing import Dict, Optional, Tuple


def fpl_pct(income: float, hh_size: int, fpg: Dict) -> int:
    """Income as a percent of the HHS poverty guideline; sizes past the table add the per-person increment."""
    base = fpg['base']
    guideline = base[hh_size - 1] if hh_size <= len(base) else base[-1] + fpg['per_additional'] * (hh_size - len(base))
    return int(round(100 * income / guideline))


def ami_pct(income: float, hh_size: int, hud_county: Dict, extra_pct: float) -> int:
    """Income as a percent of AMI, scaled so the HUD 80% 'Low Income' limit for this size reads as 80."""
    limits = hud_county['limits']
    extra = limits[3] * extra_pct / 100 * (hh_size - len(limits))
    limit = limits[hh_size - 1] if hh_size <= len(limits) else limits[-1] + extra
    return int(round(80 * income / limit))


def annual_cost(vendor_cost: Optional[float], annual_kwh: Optional[int], fresh: bool,
                rate: Optional[float]) -> Tuple[Optional[int], Optional[int]]:
    """(cost, burden_basis): vendor cost (basis 1) when supplied, else kWh x rate (basis 0) for a fresh meter."""
    if vendor_cost is not None:
        return int(round(vendor_cost)), 1
    if annual_kwh is not None and fresh and rate is not None:
        return int(round(annual_kwh * rate)), 0
    return None, None


def energy_burden(cost: Optional[int], income: Optional[float]) -> Optional[float]:
    """Electric cost as a percent of income -- a lower bound, since gas is excluded."""
    return round(100 * cost / income, 1) if cost is not None and income else None


def hl_per_sqft(hl_slope: Optional[float], sqft: Optional[float]) -> Optional[float]:
    return round(hl_slope / sqft, 8) if hl_slope is not None and sqft else None
```

- [ ] **Step 4: Implement** — `src/analysis_engine/household.py`

```python
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
    multitenant: bool = False
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
    multi_unit = match.linked and (match.meters_on_parcel > 1 or match.multitenant)
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
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_analysis_household.py -q -o addopts=""`
Expected: PASS (13 tests)

- [ ] **Step 6: Commit**

```bash
git add src/analysis_engine/features.py src/analysis_engine/household.py tests/test_analysis_household.py
git commit -m "feat(analysis): assemble one sparse household document per meter

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Need dimensions — percentiles, levels, finalize

**Files:**
- Create: `src/analysis_engine/rules.py`
- Test: `tests/test_analysis_rules.py`

**Interfaces:**
- Consumes: `is_fresh` (Task 4); household doc shape (Task 5).
- Produces: `Distributions(annual_kwh: List[float], hl_per_sqft: List[float])` (both sorted; build with
  `Distributions.from_values(kwh, hl)`); `percentile_rank(sorted_values, x) -> int`;
  `quantile(sorted_values, pct) -> Optional[float]`; `usage_ok(hh, params, build_month) -> bool`;
  `usable_fit(hh, params) -> bool`; `cutpoints(dist, params) -> Dict`;
  `finalize(hh: Dict, dist: Distributions, rules: Dict, build_month: int) -> Dict` (mutates and returns `hh`, adding
  `usage_pctile` when known, `dims` (6 ints), `proxy` when nonzero, `dim_sum`).
  `params` is `rules['params']`.

- [ ] **Step 1: Write the failing test** — `tests/test_analysis_rules.py`

```python
"""Six need dimensions, each -1 unless its inputs are known. Boundaries are tested on both sides."""

import sys
from pathlib import Path

import bson

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.rules import Distributions, cutpoints, finalize, percentile_rank, quantile  # noqa: E402

RULES = load_registry().rules
BM = 202610
DIST = Distributions.from_values(list(range(100, 10001, 100)), [i / 1e6 for i in range(1, 101)])
FRESH = {'annual_kwh': 5000, 'months_usage': 12, 'last_read': 202607}


def _dims(**hh):
    return finalize(dict(hh), DIST, RULES, BM)['dims']


def test_percentiles_and_quantiles():
    values = list(range(1, 101))
    assert percentile_rank(values, 90) == 90 and percentile_rank(values, 100) == 100 and percentile_rank(values, 0) == 0
    assert quantile(values, 75) == 75 and quantile([], 75) is None


def test_income_need_boundaries():
    assert _dims(fpl_pct=175)[0] == 2
    assert _dims(fpl_pct=176)[0] == 1 and _dims(fpl_pct=200)[0] == 1
    assert _dims(fpl_pct=201, ami_pct=80)[0] == 1
    assert _dims(fpl_pct=201, ami_pct=81)[0] == 0 and _dims(fpl_pct=201)[0] == 0
    assert _dims()[0] == -1


def test_energy_burden_boundaries():
    assert [_dims(energy_burden=b)[1] for b in (10.0, 9.9, 6.0, 5.9)] == [2, 1, 1, 0]
    assert _dims()[1] == -1


def test_high_usage_uses_county_percentile():
    assert _dims(**{**FRESH, 'annual_kwh': 9000})[3] == 2
    assert _dims(**{**FRESH, 'annual_kwh': 7500})[3] == 1
    assert _dims(**{**FRESH, 'annual_kwh': 7400})[3] == 0
    assert finalize(dict(FRESH, annual_kwh=9000), DIST, RULES, BM)['usage_pctile'] == 90


def test_stale_meter_usage_is_unknown():
    hh = finalize({'annual_kwh': 9000, 'months_usage': 12, 'last_read': 201602}, DIST, RULES, BM)
    assert hh['dims'][3] == -1 and 'usage_pctile' not in hh
    assert _dims(annual_kwh=9000, months_usage=11, last_read=202607)[3] == -1


FIT = {'hl_slope': 0.1, 'thermal_r2': 0.8, 'year_built': 1958}


def test_inefficiency_ranks_usable_fits():
    assert _dims(**FIT, hl_per_sqft=0.000081)[2] == 2
    assert _dims(**FIT, hl_per_sqft=0.000061)[2] == 1
    assert _dims(**FIT, hl_per_sqft=0.000010)[2] == 0


def test_negative_slope_is_not_a_usable_fit():
    hh = finalize({'hl_slope': -0.2, 'thermal_r2': 0.9, 'hl_per_sqft': -0.0001, 'year_built': 1958}, DIST, RULES, BM)
    assert hh['dims'][2] == 1 and hh['proxy'] == 1 << 2


def test_inefficiency_proxies_and_unknown():
    assert _dims(hl_slope=0.1, thermal_r2=0.4, hl_per_sqft=0.00009, year_built=1990)[2] == 0
    assert _dims(multi_unit=True, hl_slope=0.1, thermal_r2=0.9, hl_per_sqft=0.00009)[2] == -1
    assert _dims()[2] == -1


def test_vulnerability_counts_modifiers():
    assert _dims(senior=True, children=True)[4] == 2
    assert _dims(senior=True, children=True, owner=False)[4] == 2
    assert _dims(owner=False)[4] == 1 and _dims(multi_unit=True)[4] == 1
    assert _dims(senior=False, children=False, owner=True)[4] == 0
    assert _dims(multi_unit=False)[4] == -1 and _dims()[4] == -1


def test_electrification_uses_measured_fuel_only():
    assert _dims(heat_fuel=2)[5] == 2 and _dims(heat_fuel=1)[5] == 0 and _dims()[5] == -1


def test_unknown_is_never_zero_and_dim_sum_skips_unknown():
    empty = finalize({}, DIST, RULES, BM)
    assert empty['dims'] == [-1] * 6 and empty['dim_sum'] == 0 and 'proxy' not in empty
    assert finalize({'fpl_pct': 100, 'senior': True}, DIST, RULES, BM)['dim_sum'] == 3


def test_cutpoints_record_the_thresholds_used():
    cuts = cutpoints(DIST, RULES['params'])
    assert cuts['annual_kwh'] == {'n': 100, 'p75': 7500, 'p90': 9000}
    assert cuts['hl_per_sqft']['n'] == 100 and cuts['hl_per_sqft']['p80'] == 80 / 1e6


def test_fully_populated_document_is_under_1kb():
    hh = {'_id': 'AEP:CSP:43002|4601 BALDWIN RD WEST SIDE', 'county': 'Franklin', 'parcel_key': '010-123456-00',
          'link': 15, 'multi_unit': False, 'income_est': 42000, 'hh_size': 3, 'fpl_pct': 154, 'ami_pct': 42,
          'annual_kwh': 11840, 'annual_cost': 2246, 'energy_burden': 5.3, 'burden_basis': 0, 'peak_ratio': 1.84,
          'months_usage': 12, 'last_read': 202607, 'hl_slope': 0.14211, 'cl_slope': 0.31102, 'thermal_r2': 0.823,
          'hl_per_sqft': 0.00009411, 'year_built': 1958, 'sqft': 1510, 'stories': 1.5, 'home_value': 154000,
          'owner': True, 'senior': False, 'children': True, 'length_residence': 7, 'heat_fuel': 1,
          'missing': [17, 18, 19, 20, 21, 22, 23, 24]}
    assert len(bson.encode(finalize(hh, DIST, RULES, BM))) < 1024
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_rules.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.rules'`

- [ ] **Step 3: Implement** — `src/analysis_engine/rules.py`

```python
"""Need dimensions: county-relative percentiles, the six level functions, and finalize().

Levels: -1 unknown, 0 none, 1 moderate, 2 high. Unknown is never coerced to 0 (spec §5.4). Each level function
returns (level, is_proxy); proxy levels set the matching bit in `proxy` so the UI can show measured-only.
"""

import math
from bisect import bisect_right
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.analysis_engine.usage import is_fresh

UNKNOWN = -1
Level = Tuple[int, bool]


@dataclass(frozen=True)
class Distributions:
    """County values the percentile dimensions rank against; both lists are sorted."""
    annual_kwh: List[float]
    hl_per_sqft: List[float]

    @classmethod
    def from_values(cls, annual_kwh, hl_per_sqft) -> 'Distributions':
        return cls(sorted(annual_kwh), sorted(hl_per_sqft))


def percentile_rank(sorted_values: List[float], x: float) -> int:
    """Percent of values at or below x."""
    return int(100 * bisect_right(sorted_values, x) / len(sorted_values))


def quantile(sorted_values: List[float], pct: float) -> Optional[float]:
    if not sorted_values:
        return None
    return sorted_values[max(0, math.ceil(pct / 100 * len(sorted_values)) - 1)]


def usage_ok(hh: Dict, params: Dict, build_month: int) -> bool:
    """A full, plausible year from a meter that is still reading."""
    return (hh.get('annual_kwh') is not None and hh.get('months_usage', 0) >= 12
            and is_fresh(hh.get('last_read'), build_month, params['usage']['max_age_months']))


def usable_fit(hh: Dict, params: Dict) -> bool:
    """A thermal fit worth ranking: present, non-negative heating slope, adequate r², single-meter parcel."""
    return (hh.get('hl_per_sqft') is not None and hh.get('hl_slope', -1) >= 0
            and hh.get('thermal_r2', 0) >= params['building_inefficiency']['r2_min'] and not hh.get('multi_unit'))


def cutpoints(dist: Distributions, params: Dict) -> Dict:
    """The county values behind each percentile threshold, stored on analysis_builds for transparency."""
    usage, ineff = params['high_usage'], params['building_inefficiency']
    return {'annual_kwh': {'n': len(dist.annual_kwh), f"p{usage['moderate_pctile']}": quantile(dist.annual_kwh, usage['moderate_pctile']),
                           f"p{usage['high_pctile']}": quantile(dist.annual_kwh, usage['high_pctile'])},
            'hl_per_sqft': {'n': len(dist.hl_per_sqft),
                            f"p{ineff['moderate_pctile']}": quantile(dist.hl_per_sqft, ineff['moderate_pctile']),
                            f"p{ineff['high_pctile']}": quantile(dist.hl_per_sqft, ineff['high_pctile'])}}


def _income(hh: Dict, p: Dict) -> Level:
    fpl, ami = hh.get('fpl_pct'), hh.get('ami_pct')
    if fpl is None:
        return UNKNOWN, False
    if fpl <= p['fpl_high']:
        return 2, False
    return (1 if fpl <= p['fpl_moderate'] or (ami is not None and ami <= p['ami_moderate']) else 0), False


def _burden(hh: Dict, p: Dict) -> Level:
    burden = hh.get('energy_burden')
    if burden is None:
        return UNKNOWN, False
    return (2 if burden >= p['high'] else 1 if burden >= p['moderate'] else 0), False


def _inefficiency(hh: Dict, p: Dict, pctile: Optional[int]) -> Level:
    if pctile is not None:
        return (2 if pctile >= p['high_pctile'] else 1 if pctile >= p['moderate_pctile'] else 0), False
    year = hh.get('year_built')
    if year is None:
        return UNKNOWN, False
    return (1 if year < p['proxy_built_before'] else 0), True


def _usage(pctile: Optional[int], p: Dict) -> Level:
    if pctile is None:
        return UNKNOWN, False
    return (2 if pctile >= p['high_pctile'] else 1 if pctile >= p['moderate_pctile'] else 0), False


def _vulnerability(hh: Dict) -> Level:
    owner, multi = hh.get('owner'), hh.get('multi_unit')
    housing = True if owner is False or multi is True else False if owner is True else None
    modifiers = [hh.get('senior'), hh.get('children'), housing]
    if all(m is None for m in modifiers):
        return UNKNOWN, False
    return min(sum(m is True for m in modifiers), 2), False


def _electrification(hh: Dict, p: Dict) -> Level:
    fuel = hh.get('heat_fuel')
    if fuel is None:
        return UNKNOWN, False
    return (2 if fuel in p['high_fuels'] else 0), False


def finalize(hh: Dict, dist: Distributions, rules: Dict, build_month: int) -> Dict:
    """Add usage_pctile, dims, proxy and dim_sum to an assembled household document."""
    p = rules['params']
    usage_pctile = percentile_rank(dist.annual_kwh, hh['annual_kwh']) \
        if dist.annual_kwh and usage_ok(hh, p, build_month) else None
    hl_pctile = percentile_rank(dist.hl_per_sqft, hh['hl_per_sqft']) \
        if dist.hl_per_sqft and usable_fit(hh, p) else None
    if usage_pctile is not None:
        hh['usage_pctile'] = usage_pctile
    levels = [_income(hh, p['income_need']), _burden(hh, p['energy_burden']),
              _inefficiency(hh, p['building_inefficiency'], hl_pctile), _usage(usage_pctile, p['high_usage']),
              _vulnerability(hh), _electrification(hh, p['electrification'])]
    hh['dims'] = [level for level, _ in levels]
    proxy = sum(1 << i for i, (_, is_proxy) in enumerate(levels) if is_proxy)
    if proxy:
        hh['proxy'] = proxy
    hh['dim_sum'] = sum(level for level in hh['dims'] if level > 0)
    return hh
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_analysis_rules.py -q -o addopts=""`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add src/analysis_engine/rules.py tests/test_analysis_rules.py
git commit -m "feat(analysis): six need dimensions with county percentiles and proxy bits

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Archetype compiler

**Files:**
- Create: `src/analysis_engine/archetypes.py`
- Test: `tests/test_analysis_archetypes.py`

**Interfaces:**
- Consumes: `rules['dims']`, `rules['archetypes']` (Task 3).
- Produces: `compile_archetype(name: str, rules: Dict) -> Tuple[Dict, Dict]` — `(match, known)`: `match` selects the
  archetype's households; `known` selects the denominator (households whose inputs are all known; `{}` means all).
  These filters are the contract bolt-od's TypeScript port must reproduce (spec §6: never stored on documents).

- [ ] **Step 1: Write the failing test** — `tests/test_analysis_archetypes.py`

```python
"""Archetypes are queries, not stored labels. These filters are a contract the bolt-od port must reproduce."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.archetypes import compile_archetype  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402

RULES = load_registry().rules


def test_bill_assistance():
    assert compile_archetype('bill_assistance', RULES) == (
        {'$and': [{'dims.0': {'$gte': 2}}]}, {'$and': [{'dims.0': {'$gte': 0}}]})


def test_weatherization_needs_multi_unit_known():
    match, known = compile_archetype('weatherization', RULES)
    assert match == {'$and': [{'dims.0': {'$gte': 1}}, {'dims.2': {'$gte': 1}}, {'multi_unit': {'$ne': True}}]}
    assert known == {'$and': [{'dims.0': {'$gte': 0}}, {'dims.2': {'$gte': 0}}, {'multi_unit': {'$exists': True}}]}


def test_electrification_allows_unknown_owner():
    match, known = compile_archetype('electrification', RULES)
    assert match == {'$and': [{'dims.5': {'$eq': 2}}, {'owner': {'$ne': False}}]}
    assert known == {'$and': [{'dims.5': {'$gte': 0}}]}


def test_likely_no_benefit_requires_four_known_dims():
    known_count = {'$expr': {'$gte': [{'$size': {'$filter': {'input': '$dims', 'cond': {'$gte': ['$$this', 0]}}}}, 4]}}
    assert compile_archetype('likely_no_benefit', RULES) == (
        {'$and': [known_count, {'dims': {'$not': {'$elemMatch': {'$gte': 1}}}}]}, known_count)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_archetypes.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.archetypes'`

- [ ] **Step 3: Implement** — `src/analysis_engine/archetypes.py`

```python
"""Program archetypes (rules.json) -> MongoDB filters, compiled at query time so tuning needs no rebuild.

Every count is reported against its known-enough denominator: the households for which all of the
archetype's inputs are known (spec §6).
"""

from typing import Dict, Tuple

OPS = {'>=': '$gte', '<=': '$lte', '==': '$eq', '!=': '$ne'}


def _known_dim_count(minimum: int) -> Dict:
    known = {'$size': {'$filter': {'input': '$dims', 'cond': {'$gte': ['$$this', 0]}}}}
    return {'$expr': {'$gte': [known, minimum]}}


def compile_archetype(name: str, rules: Dict) -> Tuple[Dict, Dict]:
    """(match, known) filters for one archetype; known == {} means every household is a valid denominator."""
    spec, dims = rules['archetypes'][name], rules['dims']
    if spec.get('kind') == 'no_known_need':
        known = _known_dim_count(spec['min_known'])
        return {'$and': [known, {'dims': {'$not': {'$elemMatch': {'$gte': 1}}}}]}, known
    match, known = [], []
    for clause in spec['all']:
        if 'dim' in clause:
            path = f"dims.{dims.index(clause['dim'])}"
            match.append({path: {OPS[clause['op']]: clause['value']}})
            known.append({path: {'$gte': 0}})
        else:
            match.append({clause['field']: {OPS[clause['op']]: clause['value']}})
            if not clause.get('unknown_ok'):
                known.append({clause['field']: {'$exists': True}})
    return {'$and': match}, ({'$and': known} if known else {})
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_analysis_archetypes.py -q -o addopts=""`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/analysis_engine/archetypes.py tests/test_analysis_archetypes.py
git commit -m "feat(analysis): compile program archetypes to match and known-enough filters

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: County source loading

**Files:**
- Modify: `tests/mongo_fakes.py` (add `FakeNamedDB`)
- Create: `src/analysis_engine/sources.py`
- Test: `tests/test_analysis_sources.py`

**Interfaces:**
- Consumes: `ParcelIndex, parcel_key_of, parcel_id_of` (Task 1); `read_value, PRESENT` (Task 2); `Registry` (Task 3);
  `ParcelMatch` (Task 5).
- Produces: `COLLECTIONS` (role → `'{}ElectricalDB'` etc.); `collection_name(role, county) -> str`;
  `sources_present(collection_names, county) -> Dict[role, name]`; `identity(doc) -> Optional[Tuple[str, str]]`;
  `choose_most_complete(docs, specs, tokens) -> Dict`; `index_role(docs, specs, tokens) -> Tuple[ParcelIndex, int]`;
  `FieldTracker(reg)` with `observe(role, doc)` and `unmapped() -> Dict[role, List[str]]`;
  `CountySources(present, counts, indexes, multitenant, meters, duplicates, tracker)` with
  `match(elec) -> ParcelMatch`; `iter_electrical(db, county) -> Iterator[Dict]`;
  `load_county_sources(db, county, reg) -> CountySources` (`counts['electrical']` is the gate's source count).
- Test fake produced: `FakeNamedDB(collections: Dict[str, List[Dict]])` with `__getitem__` and
  `list_collection_names()`.

- [ ] **Step 1: Add the fake** — append to `tests/mongo_fakes.py`

```python
class FakeNamedDB:
    """Any set of named collections, for code that discovers which collections a county has."""

    def __init__(self, collections):
        self._cols = {name: FakeCollection(docs) for name, docs in collections.items()}

    def __getitem__(self, name):
        return self._cols[name]

    def list_collection_names(self):
        return list(self._cols)
```

- [ ] **Step 2: Write the failing test** — `tests/test_analysis_sources.py`

```python
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
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_sources.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.sources'`

- [ ] **Step 4: Implement** — `src/analysis_engine/sources.py`

```python
"""Read one county's source collections into in-memory parcel indexes for household assembly.

Parcel-side documents are projected to the paths the registry maps before they are kept, so a county's
indexes stay small. Every key seen in every source document is tracked, so fields the registry neither maps
nor ignores surface in analysis_builds.unmapped_fields instead of disappearing (spec §10).
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from src.analysis_engine.household import PARCEL_ROLES, ParcelMatch
from src.analysis_engine.normalize import PRESENT, read_value
from src.analysis_engine.registry import FieldSpec, Registry
from src.tools.parcel_id import ParcelIndex, parcel_id_of, parcel_key_of

COLLECTIONS = {'electrical': '{}ElectricalDB', 'residential': '{}CountyResidential',
               'demographic': '{}CountyDemographic', 'thermal': '{}ThermalLoads', 'multitenant': '{}MultiTenant'}
ID_KEYS = ('_id', 'parcel_id', 'parcel_key')


def collection_name(role: str, county: str) -> str:
    return COLLECTIONS[role].format(county)


def sources_present(collection_names: Iterable[str], county: str) -> Dict[str, str]:
    names = set(collection_names)
    return {role: collection_name(role, county) for role in COLLECTIONS if collection_name(role, county) in names}


def identity(doc: Dict) -> Optional[Tuple[str, str]]:
    """The spelling a meter is counted under: parcel_key when present, else the normalized parcel_id."""
    key = parcel_key_of(doc)
    if key is not None:
        return 'k', key
    ident = parcel_id_of(doc)
    return ('i', ident) if ident is not None else None


class FieldTracker:
    """Source keys seen per role, minus those the registry maps, reads directly, or ignores."""

    def __init__(self, reg: Registry):
        self._known = reg.known_keys
        self._seen = defaultdict(set)

    def observe(self, role: str, doc: Dict) -> None:
        self._seen[role].update(doc.keys())

    def unmapped(self) -> Dict[str, List[str]]:
        found = {role: sorted(seen - self._known[role]) for role, seen in self._seen.items()}
        return {role: names for role, names in found.items() if names}


def choose_most_complete(docs: List[Dict], specs: List[FieldSpec], tokens) -> Dict:
    """The doc with the most usable mapped fields; ties go to the larger _id, so cursor order never decides."""
    def score(doc: Dict):
        return sum(read_value(doc, f.source, tokens)[0] == PRESENT for f in specs), str(doc.get('_id'))
    return max(docs, key=score)


def index_role(docs: Iterable[Dict], specs: List[FieldSpec], tokens) -> Tuple[ParcelIndex, int]:
    """Group by parcel_key and by parcel_id, keep the most complete doc per group; count parcels with duplicates."""
    by_key, by_id, per_parcel = defaultdict(list), defaultdict(list), Counter()
    for doc in docs:
        key, ident = parcel_key_of(doc), parcel_id_of(doc)
        if key is not None:
            by_key[key].append(doc)
        if ident is not None:
            by_id[ident].append(doc)
        if identity(doc) is not None:
            per_parcel[identity(doc)] += 1
    index = ParcelIndex()
    index.by_key = {k: choose_most_complete(group, specs, tokens) for k, group in by_key.items()}
    index.by_id = {k: choose_most_complete(group, specs, tokens) for k, group in by_id.items()}
    return index, sum(1 for n in per_parcel.values() if n > 1)


@dataclass
class CountySources:
    present: Dict[str, str]
    counts: Dict[str, int]
    indexes: Dict[str, ParcelIndex]
    multitenant: ParcelIndex
    meters: Counter
    duplicates: Dict[str, int]
    tracker: FieldTracker

    def match(self, elec: Dict) -> ParcelMatch:
        ident = identity(elec)
        if ident is None:
            return ParcelMatch()
        found = {role: index.resolve(elec)[0] for role, index in self.indexes.items()}
        return ParcelMatch(linked=True, meters_on_parcel=self.meters[ident],
                           multitenant=self.multitenant.resolve(elec)[0] is True, **found)


def iter_electrical(db, county: str) -> Iterator[Dict]:
    return iter(db[collection_name('electrical', county)].find({}))


def _project(doc: Dict, paths: List[str]) -> Dict:
    return {k: doc[k] for k in (*ID_KEYS, *paths) if k in doc}


def load_county_sources(db, county: str, reg: Registry) -> CountySources:
    """Index every parcel-side source the county has, count meters per parcel, and track source keys."""
    present = sources_present(db.list_collection_names(), county)
    tracker, counts, indexes, duplicates = FieldTracker(reg), {}, {}, {}
    for role in PARCEL_ROLES:
        if role not in present:
            continue
        specs = reg.fields_for(role)
        paths = [p for spec in specs for p in spec.source['paths']]
        docs = []
        for doc in db[present[role]].find({}):
            tracker.observe(role, doc)
            docs.append(_project(doc, paths))
        counts[role] = len(docs)
        indexes[role], duplicates[role] = index_role(docs, specs, reg.missing_tokens)
    multitenant = ParcelIndex()
    if 'multitenant' in present:
        counts['multitenant'] = 0
        for doc in db[present['multitenant']].find({}):
            tracker.observe('multitenant', doc)
            multitenant.add(doc, True)
            counts['multitenant'] += 1
    meters = Counter()
    if 'electrical' in present:
        counts['electrical'] = 0
        for doc in db[present['electrical']].find({}, {'parcel_id': 1, 'parcel_key': 1}):
            counts['electrical'] += 1
            if identity(doc) is not None:
                meters[identity(doc)] += 1
    return CountySources(present, counts, indexes, multitenant, meters, duplicates, tracker)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_analysis_sources.py tests/test_multimeter_exclusion.py -q -o addopts=""`
Expected: PASS (5 new tests; the existing multimeter test confirms `FakeDB` in `mongo_fakes.py` is untouched)

- [ ] **Step 6: Commit**

```bash
git add tests/mongo_fakes.py src/analysis_engine/sources.py tests/test_analysis_sources.py
git commit -m "feat(analysis): load county sources into parcel indexes with drift tracking

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Build orchestration, gates and stores

**Files:**
- Create: `src/analysis_engine/store.py`, `src/analysis_engine/build.py`
- Modify: `tests/analysis_fakes.py` (add `FakeStore`)
- Test: `tests/test_analysis_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces (store): `HOUSEHOLDS = 'analysis_households'`, `BUILDS = 'analysis_builds'`,
  `staging_name(county) -> str`; store protocol `reset_staging(county)`, `stage(county, docs)`, `swap(county)`,
  `discard_staging(county)`, `record_build(build)`; `MongoStore(db)` adds `ensure_indexes(dim_count)`;
  `DryRunStore()` with `staged: Counter`, `builds: List`.
- Produces (build): `BuildError(RuntimeError)`; `doc_size(doc) -> int`;
  `check_gates(doc_count, source_count, sizes_sorted) -> List[str]`;
  `build_county(db, store, county, reg, now: datetime) -> Dict` (the `analysis_builds` document; status `ok` or
  `failed`; never raises).
- Test fake produced: `FakeStore(live=None)` with `live: Dict[_id, doc]`, `staging`, `builds`; optional
  `fail_on_stage=True` to simulate a write failure.

`analysis_builds` document fields: `county, built_at, registry_version, rules_version, status, sources_present
(sorted roles), source_counts, doc_count, size_p50, size_p99, cutpoints, unmapped_fields, unmapped_values
({field: [[value, count], ...]}), stats ({unlinked, multi_unit, stale, duplicates}), error` (on failure).

- [ ] **Step 1: Add the fake store** — append to `tests/analysis_fakes.py`

```python
class FakeStore:
    """In-memory analysis_households with the staging/swap semantics of MongoStore."""

    def __init__(self, live=None, fail_on_stage=False):
        self.live = {doc['_id']: doc for doc in (live or [])}
        self.staging, self.builds, self.fail_on_stage = {}, [], fail_on_stage

    def reset_staging(self, county):
        self.staging[county] = {}

    def stage(self, county, docs):
        if self.fail_on_stage:
            raise IOError('disk full')
        self.staging[county].update({doc['_id']: doc for doc in docs})

    def swap(self, county):
        self.live = {k: d for k, d in self.live.items() if d['county'] != county}
        self.live.update(self.staging.pop(county))

    def discard_staging(self, county):
        self.staging.pop(county, None)

    def record_build(self, build):
        self.builds.append(build)
```

- [ ] **Step 2: Write the failing test** — `tests/test_analysis_build.py`

```python
"""A county build either replaces that county's households completely or leaves them untouched."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.build import build_county, check_gates  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from tests.analysis_fakes import FakeStore, elec, monthly_series  # noqa: E402
from tests.mongo_fakes import FakeNamedDB  # noqa: E402

REG = load_registry()
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
YEAR = monthly_series(2025, 8, [900.0] * 12)


def _db():
    return FakeNamedDB({
        'FranklinElectricalDB': [elec('E1', YEAR, parcel_key='K1'), elec('E2', YEAR),
                                 elec('E3', monthly_series(2015, 3, [700.0] * 12))],
        'FranklinCountyDemographic': [{'_id': 'D1', 'parcel_key': 'K1', 'estimated_income': 30000.0,
                                       'md_householdsize': 2.0, 'md_own_rent': 'Maybe'}],
    })


def test_successful_build_replaces_only_its_county():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Franklin'}, {'_id': 'X', 'county': 'Adams'}])
    build = build_county(_db(), store, 'Franklin', REG, NOW)
    assert build['status'] == 'ok' and build['doc_count'] == 3
    assert set(store.live) == {'E1', 'E2', 'E3', 'X'}
    assert store.live['E1']['dims'][0] == 2 and store.live['E1']['link'] == 1 | 4
    assert build['sources_present'] == ['demographic', 'electrical']
    assert build['source_counts']['electrical'] == 3 and build['cutpoints']['annual_kwh']['n'] == 2
    assert build['unmapped_values'] == {'owner': [['Maybe', 1]]}
    assert build['stats'] == {'unlinked': 2, 'multi_unit': 0, 'stale': 1, 'duplicates': {'demographic': 0}}
    assert build['size_p99'] < 1024 and build['registry_version'] == REG.fields_version
    assert store.builds == [build] and store.staging == {}


def test_county_without_electrical_fails_and_changes_nothing():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Nowhere'}])
    build = build_county(FakeNamedDB({}), store, 'Nowhere', REG, NOW)
    assert build['status'] == 'failed' and 'no ElectricalDB' in build['error']
    assert set(store.live) == {'OLD'} and store.builds == [build]


def test_write_failure_leaves_previous_version_live():
    store = FakeStore(live=[{'_id': 'OLD', 'county': 'Franklin'}], fail_on_stage=True)
    build = build_county(_db(), store, 'Franklin', REG, NOW)
    assert build['status'] == 'failed' and 'disk full' in build['error']
    assert set(store.live) == {'OLD'} and store.staging == {}


def test_gates():
    assert check_gates(3, 3, [300, 400, 500]) == []
    assert check_gates(2, 3, [300, 400]) == ['doc count 2 != source meter count 3']
    assert check_gates(1, 1, [1024]) == ['p99 document size 1024 B is not under 1024 B']
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_build.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.build'`

- [ ] **Step 4: Implement** — `src/analysis_engine/store.py`

```python
"""Where a county build lands: staging, then a swap into analysis_households.

The swap merges staging into the live collection and then deletes the county's live documents that staging no
longer holds. A build that fails before the swap leaves the previous version live (spec §10).
"""

from collections import Counter
from typing import Dict, List

HOUSEHOLDS, BUILDS = 'analysis_households', 'analysis_builds'
_DELETE_BATCH = 10000


def staging_name(county: str) -> str:
    return f'{HOUSEHOLDS}_staging_{county}'


class MongoStore:
    def __init__(self, db):
        self.db = db

    def ensure_indexes(self, dim_count: int) -> None:
        households = self.db[HOUSEHOLDS]
        for keys in ([('county', 1)], [('parcel_key', 1)], [('link', 1)],
                     *([('county', 1), (f'dims.{i}', 1)] for i in range(dim_count))):
            households.create_index(keys)

    def reset_staging(self, county: str) -> None:
        self.db[staging_name(county)].drop()

    def stage(self, county: str, docs: List[Dict]) -> None:
        self.db[staging_name(county)].insert_many(docs, ordered=False)

    def _cross_county_collisions(self, county: str) -> int:
        """Staged _ids already held by another county; a merge would silently move them."""
        pipeline = [{'$lookup': {'from': HOUSEHOLDS, 'localField': '_id', 'foreignField': '_id', 'as': 'live'}},
                    {'$match': {'live.county': {'$exists': True, '$ne': county}}}, {'$count': 'n'}]
        result = list(self.db[staging_name(county)].aggregate(pipeline, allowDiskUse=True))
        return result[0]['n'] if result else 0

    def swap(self, county: str) -> None:
        staging = staging_name(county)
        collisions = self._cross_county_collisions(county)
        if collisions:
            raise RuntimeError(f'{collisions} staged _id(s) already belong to another county')
        self.db[staging].aggregate([{'$merge': {'into': HOUSEHOLDS, 'on': '_id', 'whenMatched': 'replace',
                                                'whenNotMatched': 'insert'}}], allowDiskUse=True)
        stale = [d['_id'] for d in self.db[HOUSEHOLDS].aggregate([
            {'$match': {'county': county}},
            {'$lookup': {'from': staging, 'localField': '_id', 'foreignField': '_id', 'as': 'fresh'}},
            {'$match': {'fresh': {'$size': 0}}}, {'$project': {'_id': 1}}], allowDiskUse=True)]
        for start in range(0, len(stale), _DELETE_BATCH):
            self.db[HOUSEHOLDS].delete_many({'_id': {'$in': stale[start:start + _DELETE_BATCH]}})
        self.db[staging].drop()

    def discard_staging(self, county: str) -> None:
        self.db[staging_name(county)].drop()

    def record_build(self, build: Dict) -> None:
        self.db[BUILDS].insert_one(dict(build))


class DryRunStore:
    """Counts what a build would write and writes nothing."""

    def __init__(self):
        self.staged, self.builds = Counter(), []

    def reset_staging(self, county: str) -> None:
        self.staged[county] = 0

    def stage(self, county: str, docs: List[Dict]) -> None:
        self.staged[county] += len(docs)

    def swap(self, county: str) -> None:
        pass

    def discard_staging(self, county: str) -> None:
        self.staged.pop(county, None)

    def record_build(self, build: Dict) -> None:
        self.builds.append(build)
```

- [ ] **Step 5: Implement** — `src/analysis_engine/build.py`

```python
"""Two-pass county build: pass 1 learns the county's distributions, pass 2 assigns levels and stages documents.

Assembly is deterministic, so pass 2 re-assembles from the in-memory parcel indexes instead of holding a
county's households in memory between passes (Franklin: 475k meters).
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List

import bson

from src.analysis_engine.household import assemble
from src.analysis_engine.registry import Registry
from src.analysis_engine.rules import Distributions, cutpoints, finalize, quantile, usable_fit, usage_ok
from src.analysis_engine.sources import CountySources, identity, iter_electrical, load_county_sources
from src.analysis_engine.usage import is_fresh
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)
MAX_P99_BYTES = 1024
_BATCH = 1000


class BuildError(RuntimeError):
    """A county build was refused before its swap; the previous version stays live."""


def doc_size(doc: Dict) -> int:
    return len(bson.encode(doc))


def check_gates(doc_count: int, source_count: int, sizes_sorted: List[int]) -> List[str]:
    """Pre-swap gates (spec §12, P1): one document per meter, p99 size under 1 KB."""
    failures = []
    if doc_count != source_count:
        failures.append(f'doc count {doc_count} != source meter count {source_count}')
    p99 = quantile(sizes_sorted, 99)
    if p99 is not None and p99 >= MAX_P99_BYTES:
        failures.append(f'p99 document size {p99} B is not under {MAX_P99_BYTES} B')
    return failures


def _distributions(db, county: str, src: CountySources, reg: Registry, build_month: int) -> Distributions:
    params, kwh, hl = reg.rules['params'], [], []
    for meter in iter_electrical(db, county):
        src.tracker.observe('electrical', meter)
        hh = assemble(meter, src.match(meter), county, build_month, reg).doc
        if usage_ok(hh, params, build_month):
            kwh.append(hh['annual_kwh'])
        if usable_fit(hh, params):
            hl.append(hh['hl_per_sqft'])
    return Distributions.from_values(kwh, hl)


def _stage_households(db, store, county: str, src: CountySources, dist: Distributions, reg: Registry,
                      build_month: int, build: Dict) -> List[int]:
    max_age = reg.params('usage')['max_age_months']
    sizes, batch, stats, unmapped = [], [], Counter(), defaultdict(Counter)
    store.reset_staging(county)
    for meter in iter_electrical(db, county):
        assembled = assemble(meter, src.match(meter), county, build_month, reg)
        hh = finalize(assembled.doc, dist, reg.rules, build_month)
        for name, raw in assembled.unmapped_values:
            unmapped[name][str(raw)] += 1
        stats['unlinked'] += identity(meter) is None
        stats['multi_unit'] += hh.get('multi_unit') is True
        stats['stale'] += hh.get('last_read') is not None and not is_fresh(hh['last_read'], build_month, max_age)
        sizes.append(doc_size(hh))
        batch.append(hh)
        if len(batch) >= _BATCH:
            store.stage(county, batch)
            batch = []
    if batch:
        store.stage(county, batch)
    build['stats'] = {**{k: stats[k] for k in ('unlinked', 'multi_unit', 'stale')}, 'duplicates': src.duplicates}
    build['unmapped_values'] = {name: [[value, n] for value, n in counts.most_common()]
                                for name, counts in unmapped.items()}
    return sorted(sizes)


def build_county(db, store, county: str, reg: Registry, now: datetime) -> Dict:
    """Build one county and record the attempt. Never raises: failures are recorded with status 'failed'."""
    build_month = now.year * 100 + now.month
    build = {'county': county, 'built_at': now, 'registry_version': reg.fields_version,
             'rules_version': reg.rules_version, 'status': 'staging'}
    try:
        src = load_county_sources(db, county, reg)
        if 'electrical' not in src.present:
            raise BuildError(f'{county}: no ElectricalDB collection')
        dist = _distributions(db, county, src, reg, build_month)
        sizes = _stage_households(db, store, county, src, dist, reg, build_month, build)
        build.update(sources_present=sorted(src.present), source_counts=src.counts, doc_count=len(sizes),
                     size_p50=quantile(sizes, 50), size_p99=quantile(sizes, 99),
                     cutpoints=cutpoints(dist, reg.rules['params']), unmapped_fields=src.tracker.unmapped())
        failures = check_gates(len(sizes), src.counts['electrical'], sizes)
        if failures:
            raise BuildError('; '.join(failures))
        store.swap(county)
        build['status'] = 'ok'
    except Exception as exc:  # recorded, not swallowed: the build doc carries the error and status 'failed'
        logger.exception(f'{county}: build failed')
        build['status'], build['error'] = 'failed', str(exc)
        store.discard_staging(county)
    store.record_build(build)
    return build
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_analysis_build.py -q -o addopts=""`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add src/analysis_engine/store.py src/analysis_engine/build.py tests/analysis_fakes.py tests/test_analysis_build.py
git commit -m "feat(analysis): two-pass county build with pre-swap gates and atomic replacement

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: CLI, report, and tool documentation

**Files:**
- Create: `src/analysis_engine/report.py`, `src/analysis_engine/cli.py`
- Modify: `.claude_docs/tools.md` (append a section)
- Test: `tests/test_analysis_cli.py`

**Interfaces:**
- Consumes: `build_county`, `MongoStore`, `DryRunStore`, `HOUSEHOLDS`, `compile_archetype`, `load_registry`.
- Produces: `summarize_build(build: Dict) -> str`; `county_report(db, county, reg) -> Dict`;
  `format_report(report: Dict, reg) -> str`; `parse_args(argv) -> Namespace`;
  `run_build(db, counties, dry_run, reg, now=None) -> int`; `main(argv=None, db=None) -> int`.

- [ ] **Step 1: Write the failing test** — `tests/test_analysis_cli.py`

```python
"""The CLI wiring: a dry run builds everything, writes nothing, and reports what it would have written."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.cli import parse_args, run_build  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402
from src.analysis_engine.report import summarize_build  # noqa: E402
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_analysis_cli.py -q -o addopts=""`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis_engine.cli'`

- [ ] **Step 3: Implement** — `src/analysis_engine/report.py`

```python
"""Human-readable build summaries, and live per-county dimension and archetype counts."""

from typing import Dict

from src.analysis_engine.archetypes import compile_archetype
from src.analysis_engine.registry import Registry
from src.analysis_engine.store import HOUSEHOLDS

LEVEL_NAMES = {-1: 'unknown', 0: 'none', 1: 'moderate', 2: 'high'}


def summarize_build(build: Dict) -> str:
    lines = [f"{build['county']}: {build['status']} - {build.get('doc_count', 0):,} households, "
             f"size p50/p99 {build.get('size_p50')}/{build.get('size_p99')} B"]
    if build.get('error'):
        lines.append(f"  error: {build['error']}")
    stats = build.get('stats', {})
    if stats:
        lines.append(f"  unlinked {stats['unlinked']:,} · multi-unit {stats['multi_unit']:,} · "
                     f"stale {stats['stale']:,} · duplicate parcels {stats['duplicates']}")
    for role, names in build.get('unmapped_fields', {}).items():
        lines.append(f"  unmapped {role} fields: {', '.join(names)}")
    for name, pairs in build.get('unmapped_values', {}).items():
        lines.append(f"  unmapped values {name}: " + ', '.join(f'{v} ({n})' for v, n in pairs))
    return '\n'.join(lines)


def county_report(db, county: str, reg: Registry) -> Dict:
    """Level counts per dimension (with proxy counts) and archetype counts with known-enough denominators."""
    households = db[HOUSEHOLDS]
    total = households.count_documents({'county': county})
    dims = {}
    for i, name in enumerate(reg.dims):
        rows = households.aggregate([{'$match': {'county': county}},
                                     {'$group': {'_id': {'$arrayElemAt': ['$dims', i]}, 'n': {'$sum': 1}}}])
        dims[name] = {'levels': {row['_id']: row['n'] for row in rows},
                      'proxy': households.count_documents({'county': county, 'proxy': {'$bitsAllSet': 1 << i}})}
    archetypes = {}
    for name in reg.rules['archetypes']:
        match, known = compile_archetype(name, reg.rules)
        archetypes[name] = {'n': households.count_documents({'$and': [{'county': county}, match]}),
                            'known': households.count_documents({'$and': [{'county': county}, known]})
                            if known else total}
    return {'county': county, 'total': total, 'dims': dims, 'archetypes': archetypes}


def format_report(report: Dict, reg: Registry) -> str:
    lines = [f"{report['county']}: {report['total']:,} households"]
    for name, entry in report['dims'].items():
        levels = ' · '.join(f"{LEVEL_NAMES[lv]} {entry['levels'].get(lv, 0):,}" for lv in (2, 1, 0, -1))
        lines.append(f"  {name:<22} {levels} · proxy {entry['proxy']:,}")
    for name, entry in report['archetypes'].items():
        label = reg.rules['archetypes'][name]['label']
        lines.append(f"  {label:<42} {entry['n']:,} of {entry['known']:,} known-enough")
    return '\n'.join(lines)
```

- [ ] **Step 4: Implement** — `src/analysis_engine/cli.py`

```python
"""Build and report the bulk need-analysis household table.

    python -m src.analysis_engine.cli build --county Adams --county Cuyahoga [--dry-run]
    python -m src.analysis_engine.cli report --county Adams
"""

import argparse
import sys
from datetime import datetime, timezone
from typing import List, Optional

from src.analysis_engine.build import build_county
from src.analysis_engine.registry import Registry, load_registry
from src.analysis_engine.report import county_report, format_report, summarize_build
from src.analysis_engine.store import DryRunStore, MongoStore


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='analysis_engine', description='Bulk household need analysis')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='rebuild analysis_households for the given counties')
    build.add_argument('--county', action='append', required=True)
    build.add_argument('--dry-run', action='store_true', help='compute and validate, write nothing')
    report = sub.add_parser('report', help='dimension and archetype counts from analysis_households')
    report.add_argument('--county', action='append', required=True)
    return parser.parse_args(argv)


def run_build(db, counties: List[str], dry_run: bool, reg: Registry, now: Optional[datetime] = None) -> int:
    store = DryRunStore() if dry_run else MongoStore(db)
    if not dry_run:
        store.ensure_indexes(len(reg.dims))
    failed = 0
    for county in counties:
        build = build_county(db, store, county, reg, now or datetime.now(timezone.utc))
        print(summarize_build(build))
        failed += build['status'] != 'ok'
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None, db=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    reg = load_registry()
    if db is None:
        from src.tools.mongo import get_empower_db
        db = get_empower_db()
    if args.command == 'build':
        return run_build(db, args.county, args.dry_run, reg)
    for county in args.county:
        print(format_report(county_report(db, county, reg), reg))
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -q -o addopts=""`
Expected: PASS — 293 baseline + 3 (Task 1) + 7 + 7 + 7 + 13 + 13 + 4 + 5 + 4 + 3 = **359 passed**

- [ ] **Step 6: Document the tool** — append to `.claude_docs/tools.md`

```markdown
## analysis_engine (bulk need analysis)

**Purpose**: Rebuilds `analysis_households` (one sparse < 1 KB document per electric meter: features, `link`
bitmask, `missing` codes, six need `dims`) and records each county build in `analysis_builds`. Registry data —
field codes, sentinels, thresholds, cited FPG/HUD/EIA tables, archetypes — lives in
`src/analysis_engine/registry/{fields,rules}.json`. Gas is excluded (spec §14).

**Location**: `src/analysis_engine/`

**Usage:**
```bash
source venv/bin/activate
python -m src.analysis_engine.cli build --county Adams --dry-run    # compute + gates, no writes
python -m src.analysis_engine.cli build --county Adams --county Cuyahoga --county Franklin
python -m src.analysis_engine.cli report --county Franklin          # level and archetype counts
```

A build is atomic per county: it stages to `analysis_households_staging_{County}`, checks gates (doc count =
meter count, p99 < 1 KB), then swaps. A failure leaves the previous version live and records `status: failed`.
Source fields the registry neither maps nor ignores appear under `unmapped_fields`. Spec:
`.claude_docs/20261008_1713_bulk_need_analysis_design.md`. Tests: `tests/test_analysis_*.py`.
```

- [ ] **Step 7: Commit**

```bash
git add src/analysis_engine/report.py src/analysis_engine/cli.py tests/test_analysis_cli.py .claude_docs/tools.md
git commit -m "feat(analysis): build/report CLI and tool documentation

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Live P1 build — Adams, Cuyahoga, Franklin

**Files:**
- Possibly modify: `src/analysis_engine/registry/fields.json` (`ignored` lists only, if drift is benign)
- Create: `.claude_docs/<YYYYMMDD_HHMM>_need_analysis_p1_results.md` (timestamp from `date +%Y%m%d_%H%M`)

This task runs against the live `empower_development` database. It writes only the three analysis collections.

**Pre-measured while writing this plan** (plan code materialized in a scratch worktree, `--dry-run`, 2026-10-12):
all 359 tests passed; Adams ok 8,283 households (p99 274 B); Cuyahoga ok 396,338 (p99 524 B, 78,953 stale meters,
duplicate parcels residential 1,879 / demographic 276 / thermal 22); Franklin ok 475,376 (p99 559 B, 12,344 stale).
No unmapped fields or values. Peak RSS ~840 MB; ~1.5 min per large county. Income need is known for ~2 % of
Cuyahoga and ~9 % of Franklin meters; most `building_inefficiency = 1` comes from the pre-1980 proxy. Your numbers
should match these closely; investigate any large difference before Step 5.

- [ ] **Step 1: Confirm the source counts the gates will compare against**

Run:
```bash
source venv/bin/activate && python -c "
from src.tools.mongo import get_empower_db; db = get_empower_db()
for c in ('Adams', 'Cuyahoga', 'Franklin'): print(c, db[f'{c}ElectricalDB'].estimated_document_count())
print('existing analysis collections:', [n for n in db.list_collection_names() if n.startswith('analysis')])"
```
Expected (2026-10-12 profile): Adams 8,283 · Cuyahoga 396,338 · Franklin 475,376; no `analysis*` collections yet.
If counts differ, use the new numbers below — the gate compares against a live count, not these.

- [ ] **Step 2: Dry-run Adams**

Run: `/usr/bin/time -v python -m src.analysis_engine.cli build --county Adams --dry-run 2>&1 | grep -E "Adams|unmapped|unlinked|error|Maximum resident|Elapsed"`
Expected: `Adams: ok - 8,283 households`, `unlinked 8,283` (Adams has no parcel ids), p99 well under 1024 B.

- [ ] **Step 3: Triage drift.** For every `unmapped <role> fields:` line: if the field is identifying or operational
  (names, addresses, ingest metadata), add it to that role's `ignored` list in `fields.json`; if it looks like a real
  household feature (income, size, occupancy, heating), **stop and ask the human** whether to map it. For every
  `unmapped values` line, add the value to that field's `value_map` only if its meaning is unambiguous; otherwise
  ask. Re-run `python -m pytest tests/ -q -o addopts=""` (expect 359 passed) and commit any registry change:

```bash
git add src/analysis_engine/registry/fields.json
git commit -m "chore(analysis): register benign source fields seen in the P1 dry runs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Dry-run Cuyahoga and Franklin** — same command with `--county Cuyahoga --county Franklin`, then repeat
  Step 3. Record elapsed time and peak resident memory for the results doc. If peak memory exceeds ~4 GB, stop and
  report it — the in-memory parcel indexes would need a narrower projection before P2's 88 counties.

- [ ] **Step 5: Build for real**

Run: `python -m src.analysis_engine.cli build --county Adams --county Cuyahoga --county Franklin`
Expected: three `ok` lines; exit code 0.

- [ ] **Step 6: Verify the written data**

Run:
```bash
python -c "
from src.tools.mongo import get_empower_db; db = get_empower_db(); h = db.analysis_households
for c in ('Adams', 'Cuyahoga', 'Franklin'):
    print(c, h.count_documents({'county': c}), 'linked', h.count_documents({'county': c, 'link': {'\$bitsAnySet': 14}}),
          'with dims', h.count_documents({'county': c, 'dims': {'\$size': 6}}))
print('staging left:', [n for n in db.list_collection_names() if 'staging' in n])
print('builds:', [(b['county'], b['status'], b['doc_count']) for b in db.analysis_builds.find({}, {'county': 1, 'status': 1, 'doc_count': 1})])
print('PII check:', h.count_documents({'\$or': [{'email': {'\$exists': True}}, {'customer_name': {'\$exists': True}}, {'address': {'\$exists': True}}]}))
print(h.index_information().keys())"
```
Expected: each county's count equals its meter count; every doc has six dims; no staging collections; three `ok`
builds; PII check `0`; indexes `county_1`, `parcel_key_1`, `link_1`, `county_1_dims.0_1` … `county_1_dims.5_1`.

- [ ] **Step 7: Spot-check five households per county against their sources.** For five random `_id`s per county
  (`h.aggregate([{'$match': {'county': c}}, {'$sample': {'size': 5}}])`), open the source ElectricalDB document and
  any Residential/Demographic/Thermal documents for its parcel, and confirm by hand: `annual_kwh` equals the sum of
  the latest 12 readings, `fpl_pct` matches income and size against the 2026 FPG table, `missing` codes name fields
  that are really blank, and no unknown dimension reads 0. Note any mismatch in the results doc and stop if one is a
  bug.

- [ ] **Step 8: Idempotency** — re-run `python -m src.analysis_engine.cli build --county Adams`. Expected: count
  unchanged, `analysis_builds` now holds two Adams documents, no staging collection left.

- [ ] **Step 9: Report** — run `python -m src.analysis_engine.cli report --county Adams --county Cuyahoga --county Franklin`
  and write `.claude_docs/$(date +%Y%m%d_%H%M)_need_analysis_p1_results.md` with: the three build summaries,
  the report tables, runtime and memory per county, drift found and how it was resolved, spot-check results, and a
  short "for the human" section listing what the numbers suggest about thresholds (e.g. how many households sit
  exactly at a boundary, how many Franklin households are proxy-only for inefficiency, archetype denominators).
  Do not change thresholds — the human decides.

- [ ] **Step 10: Commit**

```bash
git add .claude_docs/*_need_analysis_p1_results.md
git commit -m "docs(need-analysis): P1 build results for Adams, Cuyahoga, Franklin

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
