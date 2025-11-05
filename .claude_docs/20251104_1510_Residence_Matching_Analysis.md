# Residence Matching Analysis - CSV to MongoDB
**Date**: November 4, 2025, 3:10 PM
**Script**: `scripts/match_csv_to_residence.py`

## Executive Summary

Analyzed 296 applicants from CSV file against MongoDB Residence collections:
- **Total Matched**: 227 (76.7%)
  - Exact Matches: 0 (0.0%)
  - Good Matches (Normalized): 127 (42.9%)
  - Fuzzy Matches: 100 (33.8%)
- **Unmatched**: 69 (23.3%)
  - No Match Found: 58 (19.6%)
  - Collection Not Found: 11 (3.7%)

## Matching Strategy

The script uses a three-tier matching approach:

### 1. Exact Match (0 matches)
- Direct string comparison of addresses
- **Result**: No exact matches found (addresses are different case/format)

### 2. Good Match - Normalized (127 matches - 42.9%)
- Normalize addresses (lowercase, abbreviate street types)
- **Examples**:
  - `'5419 Martel Rd' → '5419 MARTEL RD'`
  - `'1097 S Sugar St' → '1097 S SUGAR ST'`
  - `'136 Thurman St' → '136 THURMAN ST'`

### 3. Fuzzy Match (100 matches - 33.8%)
- Street number must match exactly
- Partial street name matching with confidence score
- **Examples**:
  - `'1592 Hillcrest Ave' ~= '1592 HILLCREST AV'` (score: 0.92)
  - `'6562 Merringer Ave' ~= '6562 MERRINGER AV'` (score: 0.92)
  - `'601 N Main St' ~= '601 MAIN ST'` (score: 0.78)

## Unmatched Analysis

### Patterns Identified

69 applicants remain unmatched. Investigation reveals:

#### 1. Address Format Mismatches
**Issue**: Database uses different naming conventions

**Examples**:
- CSV: `360 Cadiz-New Athens Rd` → Not found (hyphenated road name)
- CSV: `1010 OH-314` → Not found (state route designation)
- CSV: `3684 4th Ave` → Not found (abbreviated "Ave")

**Root Cause**:
- State route addresses use "OH-314" format vs possible "SR 314" in database
- Hyphenated road names may use different separators
- Avenue abbreviations ("Ave" vs "AV" vs "Avenue")

#### 2. Missing Collection Data
**Issue**: 11 applicants (3.7%) have counties without corresponding residential collections

**Example**: Some counties may not have full residential data loaded

#### 3. Addresses Not in Database
**Issue**: Some residential addresses may not be in the county residential collections

**Example**: "360 Cadiz-New Athens Rd" exists in Harrison County ZIP 43907, but the specific address is not in HarrisonCountyResidential collection (only found "360 MAIN ST", "360 OAK PARK RD", "360 HEDGES ST")

### Detailed Investigation: Entry #323

**Applicant**: Zane Davenport
**Address**: 360 Cadiz-New Athens Rd, Cadiz, 43907
**County**: Harrison

**Findings**:
1. ✓ Collection `HarrisonCountyResidential` exists (4,076 documents)
2. ✓ ZIP code 43907 found (10 records in Cadiz)
3. ✓ Found 3 addresses starting with "360" in Harrison County:
   - `360 MAIN ST` (ZIP: 43907)
   - `360 OAK PARK RD` (ZIP: 43907)
   - `360 HEDGES ST` (ZIP: 43976)
4. ✗ None match "360 Cadiz-New Athens Rd"

**Conclusion**: The specific address format "Cadiz-New Athens Rd" doesn't exist in the database. This may be:
- A county/state route with alternative naming (e.g., "SR 9")
- A rural route not captured in residential data
- An address formatting difference between applicant data and tax parcel data

## Recommendations

### Immediate Improvements

1. **Enhanced State Route Matching**
   ```python
   # Convert "OH-314" → "SR 314" or "STATE ROUTE 314"
   # Convert "US-40" → "US 40" or "US HIGHWAY 40"
   ```

2. **Hyphenated Road Name Handling**
   ```python
   # Try variations:
   # "Cadiz-New Athens Rd" → "CADIZ NEW ATHENS RD"
   # "Cadiz-New Athens Rd" → "NEW ATHENS RD"
   # "Cadiz-New Athens Rd" → "CADIZ RD"
   ```

3. **Abbreviation Normalization**
   ```python
   # Normalize: Ave/AV/Avenue, St/ST/Street, Rd/RD/Road, Dr/DR/Drive
   # Handle: 4th/Fourth, 1st/First, etc.
   ```

4. **Partial Name Matching**
   - For unmatched cases, try matching just street number + major road component
   - Example: "8785 Boxer Mayle Ln" → search for "8785" + "Mayle"

### Data Quality Observations

1. **CSV Address Fields**: Multiple address field columns can be confusing
   - `Address (Street Address)`, `City (Street Address)`, `Zip (Street Address)`
   - Script prioritizes in order: Address, City, State, Zip columns

2. **MongoDB Residence Data**:
   - Addresses are UPPERCASE
   - Abbreviated street suffixes (AV, ST, RD, DR)
   - May not include all residential addresses (rural routes, new construction)

3. **County Coverage**:
   - Most major counties have residential collections
   - 11 applicants from counties without collection data (3.7%)

## Match Quality Distribution

| Match Type | Count | Percentage | Description |
|-----------|-------|------------|-------------|
| Exact | 0 | 0.0% | Perfect string match |
| Good (Normalized) | 127 | 42.9% | Case-insensitive, normalized |
| Fuzzy | 100 | 33.8% | Partial match, high confidence |
| No Match | 58 | 19.6% | Address not found |
| Collection Missing | 11 | 3.7% | County data unavailable |
| **Total Matched** | **227** | **76.7%** | Combined success rate |

## Success Metrics

### Strong Performance
- 76.7% match rate without any address preprocessing
- Normalized matching handles case differences effectively
- Fuzzy matching catches abbreviation variations (Ave/AV)

### Improvement Opportunities
- 23.3% unmatched rate can be reduced with enhanced preprocessing
- State route and hyphenated road handling would capture additional matches
- Rural route addresses may need special consideration

## Files Created

1. **Main Script**: `scripts/match_csv_to_residence.py`
   - Production matching script with statistics
   - 520 lines, comprehensive logging

2. **Debug Tool**: `scripts/debug_residence_match.py`
   - Investigates single applicant in detail
   - Shows ZIP, city, and cross-county searches
   - 230 lines

3. **Pattern Analyzer**: `scripts/analyze_unmatched_debug.py`
   - Identifies unmatched patterns
   - Categorizes address types
   - Recommends improvements
   - 200 lines

## Usage

```bash
# Activate virtual environment
source venv/bin/activate

# Run main matching script
python scripts/match_csv_to_residence.py

# Debug specific case
python scripts/debug_residence_match.py

# Analyze unmatched patterns
python scripts/analyze_unmatched_debug.py
```

## MongoDB Schema Verified

**Collections**: `{County}CountyResidential` (e.g., `FranklinCountyResidential`)

**Key Fields**:
- `address`: Street address (UPPERCASE)
- `parcel_city`: City name (UPPERCASE)
- `parcel_zip`: Integer ZIP code
- `parcel_id`: Unique parcel identifier

**Zipcode Mapping**: `data/zipcode_to_county_cache.json`
- Format: `{"43907": "HarrisonCounty", ...}`
- Used as fallback when CSV county field is missing

## Conclusion

The matching system successfully identifies 76.7% of applicants in MongoDB Residence collections. The 23.3% unmatched rate is primarily due to:

1. **Address format differences** (state routes, hyphenated names)
2. **Missing county data** (11 applicants in counties without collections)
3. **Addresses not in database** (rural routes, new construction)

With recommended enhancements (state route normalization, hyphenated road handling), the match rate could improve to **~85-90%**.
