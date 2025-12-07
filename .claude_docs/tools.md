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
