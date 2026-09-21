# Reusable Tools

Documentation for reusable Python tools in `src/tools/` directory.

## residence_matcher.py

**Purpose**: Reusable residence/demographic matching with 8 sophisticated strategies for linking contacts to county data.

**Location**: `src/tools/residence_matcher.py`

### Classes

#### `ResidenceMatcher`
Main matching class with 8-strategy cascade.

**Usage:**
```python
from src.tools.residence_matcher import ResidenceMatcher

# Initialize for specific county
matcher = ResidenceMatcher(db, county='FranklinCounty')

# Match contact using available data
residence_ref, demographic_ref, match_method = matcher.match(
    phone='6145551234',
    email='john@example.com',
    first_name='John',
    last_name='Doe',
    address='123 Main St',
    zipcode='43210'
)

if match_method != 'no_match':
    print(f"Matched via {match_method}")
    print(f"Residence: {residence_ref}")
    print(f"Demographic: {demographic_ref}")
```

**Matching Strategies (in priority order):**
1. **Email** - Fastest, most reliable match via demographic.email
2. **Name** - Fuzzy name matching with normalization (removes suffixes, handles first+last combos)
3. **Phone** - Normalized phone comparison (handles 10/11 digit formats)
4. **Exact Address** - Direct string match in residential data
5. **Normalized Address** - Street/directional abbreviations (St→st, North→n)
6. **State Route Variations** - OH-314 → ["OH 314", "SR 314", "STATE ROUTE 314"]
7. **Hyphenated Roads** - "Cadiz-New Athens Rd" → ["CADIZ NEW ATHENS RD", "NEW ATHENS RD"]
8. **Fuzzy Address** - Similarity scoring with threshold (70%+)

**Returns:**
- `residence_ref`: ResidenceReference or None
- `demographic_ref`: DemographicReference or None
- `match_method`: String indicating which strategy succeeded

**Match Methods:**
- `email` - Matched via email in demographic
- `name_exact` - Exact name match
- `name_fuzzy` - Fuzzy name match
- `phone` - Phone number match
- `address_exact` - Exact address match
- `address_normalized` - Normalized address match
- `state_route` - State route variation match
- `hyphenated` - Hyphenated road variation match
- `fuzzy_X.XX` - Fuzzy address match with score
- `no_match` - No match found
- `collection_not_found` - County collections don't exist

#### `PhoneNormalizer`
Phone number normalization utilities.

**Usage:**
```python
from src.tools.residence_matcher import PhoneNormalizer

# Normalize to 10 digits
normalized = PhoneNormalizer.normalize('(614) 555-1234')
# Result: '6145551234'

# Handle 11-digit (strips leading 1)
normalized = PhoneNormalizer.normalize('1-614-555-1234')
# Result: '6145551234'

# Compare phones
if PhoneNormalizer.match(phone1, phone2):
    print("Phones match!")
```

#### `AddressNormalizer`
Address normalization and matching utilities.

**Usage:**
```python
from src.tools.residence_matcher import AddressNormalizer

# Normalize address
normalized = AddressNormalizer.normalize('123 North Main Street')
# Result: '123 n main st'

# State route variations
variations = AddressNormalizer.normalize_state_route('OH-314')
# Result: ['OH 314', 'SR 314', 'STATE ROUTE 314', 'OH-314']

# Hyphenated roads
variations = AddressNormalizer.normalize_hyphenated('Cadiz-New Athens Rd')
# Result: ['CADIZ NEW ATHENS RD', 'NEW ATHENS RD', 'CADIZ RD']

# Exact match after normalization
if AddressNormalizer.exact_match(addr1, addr2):
    print("Addresses match!")

# Fuzzy match with score
is_match, score = AddressNormalizer.fuzzy_match(addr1, addr2)
if is_match:
    print(f"Fuzzy match with {score:.2f} confidence")
```

#### `NameMatcher`
Name normalization and fuzzy matching.

**Usage:**
```python
from src.tools.residence_matcher import NameMatcher

# Normalize name (removes suffixes, lowercase, extra spaces)
normalized = NameMatcher.normalize_name('John Doe Jr.')
# Result: 'john doe'

# Match first/last against full name
is_match, match_type = NameMatcher.match(
    first='John',
    last='Doe',
    full_name='John Q. Doe Jr.'
)
# Result: (True, 'exact')
```

### Integration with Models

The matcher automatically creates `ResidenceReference` and `DemographicReference` instances using the `from_record()` class methods:

```python
# ResidenceMatcher handles this internally:
residence_ref = ResidenceReference.from_record(county, residence_doc)
demographic_ref = DemographicReference.from_record(county, demographic_doc)
```

### Performance Considerations

- **Email matching**: Indexed lookup, very fast
- **Phone matching**: Full collection scan, slower but reliable
- **Name matching**: ZIP-filtered scan when possible
- **Address matching**: ZIP-filtered when zipcode provided
- **State route/hyphenated**: Multiple variation scans, slowest

**Optimization Tips:**
- Always provide email when available (fastest strategy)
- Include zipcode for address matching (enables filtering)
- Phone matching scans entire demographic collection (consider indexing mobile field)

### Used By

- `scripts/import_text_conversations_tool.py` - Text campaign participant import
- `scripts/match_csv_to_residence_enhanced.py` - Enhanced applicant matching

### Testing

Test the matcher with dry-run mode:
```bash
# Test with first 100 records
python scripts/import_text_conversations_tool.py \
    --campaign-id 690b05a3365ec7dfe278c9cd \
    --dry-run --verbose --limit 100
```

---

## db_schema_explorer.py

**Purpose**: Diagnostic tool for exploring MongoDB collections to understand schema, data quality, and linkage integrity. Useful for pre-analysis data discovery.

**Location**: `src/tools/db_schema_explorer.py`

### Usage

```bash
python src/tools/db_schema_explorer.py
```

### Output Sections

1. **DATABASE COLLECTIONS** - Lists all collections categorized by type (demographic, residential, core, other) with document counts

2. **PARTICIPANTS COLLECTION** - Analyzes:
   - Total records vs unique contact_ids
   - Reference linkage rates (residence_ref, demographic_ref)
   - Engagement statistics (total, avg, max per participant)
   - Sample document structure

3. **CAMPAIGNS COLLECTION** - Shows campaign type distribution and sample fields

4. **DEMOGRAPHIC COLLECTION FIELDS** - Lists all fields with types and sample values from first demographic collection, highlights age-related fields

5. **RESIDENTIAL COLLECTION FIELDS** - Lists all fields from first residential collection

### Use Cases

- Pre-clustering data quality assessment
- Understanding linkage gaps between collections
- Discovering available demographic/residential fields
- Verifying engagement data structure

### Related

- Created during clustering project data exploration (2025-12-07)
- See: `.claude_docs/20251207_data_issues_and_schema_proposal.md`

---

*Last updated: 2025-12-07*

## backup_mongo_collections_tool.py

**Purpose**: Labelled MongoDB checkpoint backups so a multi-step migration can roll back to any point.

**Location**: `src/scripts/backup_mongo_collections_tool.py`

Wraps `mongodump`/`mongorestore`. Note: `mongodump` has **no `--nsInclude`** flag (that is mongorestore only), so collections matching a suffix are enumerated and dumped one at a time — do not "simplify" this back to a pattern flag.

### Actions

| Action | Effect |
|---|---|
| `create <label>` | Dump collections matching `--suffix` (default `ThermalLoads`), or `--full` for a single whole-database archive. Refuses an existing label. |
| `list` | Show every checkpoint with timestamp, size and collection count. |
| `verify <label>` | Restore into a scratch database and compare document counts per collection. Production untouched; scratch dropped afterwards. |
| `restore <label>` | Roll production back. Destructive — drops before restoring. `--collection NAME` or `--all`, with a typed confirmation unless `--yes`. |

**Usage:**
```bash
source venv/bin/activate

python src/scripts/backup_mongo_collections_tool.py create cp03-pre-dedupe --suffix ThermalLoads
python src/scripts/backup_mongo_collections_tool.py create cp00-baseline --full
python src/scripts/backup_mongo_collections_tool.py list
python src/scripts/backup_mongo_collections_tool.py verify cp03-pre-dedupe
python src/scripts/backup_mongo_collections_tool.py restore cp03-pre-dedupe --collection CuyahogaThermalLoads
```

**Checkpoint root**: `~/backups/octopus-thermal/<label>/`, override with `OCTOPUS_BACKUP_ROOT`. Each checkpoint carries a `manifest.json` recording database, mode, collection list, timing and size.

**Measured cost (2026-09-16)**: all 25 `*ThermalLoads` = 135 MB / 21s. Whole `empower_development` = 957 MB / 94s. Disk free 197 GB.

**Tested**: create, list, verify (all 25 collections matched), duplicate-label guard, and a `mongorestore` round trip confirming document-identical restore including index metadata. `restore` against production was proven by the Task 0 rollback drill on 2026-09-16: `MorrowThermalLoads` was dropped and restored from `cp00-thermal` and came back byte-identical — 1,124 documents, content hash `175b5e56…` unchanged, and both `_id_` and `parcel_key_1` rebuilt (verified with `collection_fingerprint_tool.py`).

## collection_fingerprint_tool.py

**Purpose**: Read-only fingerprint of a MongoDB collection — document count, index definitions and a content hash — so a rollback can be proven rather than assumed.

**Location**: `src/scripts/collection_fingerprint_tool.py`

`mongorestore --drop` drops a collection *and its indexes*, then rebuilds them from the dump's metadata. A check that compares only document counts would score a restore that silently lost an index, or returned different documents, as a pass. This captures all three so the claim "the collection is what it was" is checkable.

**Never writes to MongoDB.** There is no `--execute` flag because there is nothing to execute; the only file it writes is the JSON capture you ask for.

### Actions

| Action | Effect |
|---|---|
| `capture <Collection>` | Print count, index names and content hash. `--out PATH` also writes the capture as JSON. |
| `compare <before.json> <after.json>` | Diff two captures. Prints `IDENTICAL` and exits 0, or lists each difference and exits 1. |

**Usage:**
```bash
source venv/bin/activate

python src/scripts/collection_fingerprint_tool.py capture MorrowThermalLoads --out exports/morrow_before.json
# ... destructive operation ...
python src/scripts/collection_fingerprint_tool.py capture MorrowThermalLoads --out exports/morrow_after.json
python src/scripts/collection_fingerprint_tool.py compare exports/morrow_before.json exports/morrow_after.json
```

**Content hash**: each document is canonicalised with `bson.json_util` (which handles `ObjectId`, `datetime` and the rest of BSON) and hashed; the per-document digests are then sorted before the final hash. Sorting the digests makes the hash independent of document *and* key order, because `mongorestore` gives no ordering guarantee — hashing in cursor order would flag every restore as changed.

**Cost**: streams and hashes every document. Instant on Morrow (1,124 docs); expect a few seconds on Cuyahoga (260,939). Intended for targeted rollback proofs, not routine monitoring.

**Tested**: `tests/test_collection_fingerprint.py`, 13 tests — order independence, BSON type handling, detection of a dropped index, an added index, a lost `unique` flag, a count change, and changed content at an identical count. Exercised for real in the Task 0 rollback drill.

## county_weather.py

**Purpose**: Ohio county weather geography and file conventions, shared by every tool that attributes weather to a county.

**Location**: `src/tools/county_weather.py`

Holds `COUNTY_CENTROIDS` (the 25 counties in CountyKeys), `normalize_county`, the Open-Meteo `ARCHIVE_URL` and `SOURCE_TAG`, and the weather-file conventions used by the thermal pipeline. These were originally private to `scripts/backfill_campaign_weather_tool.py`; they live here because `scripts/fetch_county_weather_hourly_tool.py` and `scripts/calculate_missing_thermal_loads_tool.py` need the identical mapping. Two tables of Ohio county coordinates that could drift apart is the same class of bug as the one this module exists to prevent.

| Function | Effect |
|---|---|
| `normalize_county(key)` | `'Franklin County'`, `'FranklinCounty'`, `'  Franklin  '` → `'Franklin'`. |
| `centroid(county)` | `(lat, lon)`, or raises `UnknownCountyError`. Never returns a default. |
| `weather_csv_path(county, dir=None)` | `data/weather/{County}_hourly.csv`. |
| `resolve_weather_file(county, weather_file=None, weather_dir=None)` | Explicit file wins; otherwise the county's fetched file; otherwise raises `UnknownCountyError` or `MissingWeatherDataError` naming the fetch tool. |

**There is deliberately no fallback.** A silent fallback is what applied Columbus degree-hours to Cleveland, Dayton and Appalachian southeast Ohio. `centroid()` is checked before any path is considered, so an unmapped county reports "no centroid" rather than the misleading "file not found".

**Tested**: `tests/test_thermal_weather_selection.py` (selection, provenance, centroid coverage for all 25 thermal counties) and `tests/test_campaign_weather.py` (the original consumer, still green after extraction).

## parcel_id.py

**Purpose**: Parcel identifier normalization, shared by every tool that joins on `parcel_id`.

**Location**: `src/tools/parcel_id.py`

`normalize_parcel_id(value)` renders a parcel identifier as the string form used for joins: `int` and `bson.Int64` become their decimal string; strings keep their leading zeros and punctuation, losing only surrounding whitespace; absence (`None`, empty, whitespace-only) stays absent rather than becoming a joinable `""`.

It was private to `scripts/audit_thermal_load_coverage_tool.py` as `_norm`. It lives here because `scripts/normalize_thermal_parcel_id_types_tool.py` (T-02) *writes* the strings the audit then verifies — if the two definitions drifted, the audit would stop verifying the thing that was written.

**This is deliberately not the normalization in `scripts/enrich_demographics_from_bolt.py`**, which strips dashes and spaces for fuzzy CSV matching. Applying that here would turn `"24-01889-000"` into `"2401889000"` and break the very join T-02 repairs. Normalization here does exactly one thing: render the value as its string form.

**Tested**: `tests/test_parcel_id_normalization.py` — int, `Int64`, leading zeros, embedded punctuation, whitespace, and the three shapes of absence. The audit was re-run after extraction and all eleven runbook baseline numbers were byte-identical.
