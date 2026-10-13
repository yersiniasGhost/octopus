# Need analysis P1: live build results (Adams, Cuyahoga, Franklin)

Build date 2026-10-12, registry/rules version 2026-10-12.1, database `empower_development`. Writes went only to `analysis_households` and `analysis_builds`.

## Build summaries

```
Adams: ok - 8,283 households, size p50/p99 264/264 B
  unlinked 8,283 · multi-unit 0 · stale 0 · duplicate parcels {}
Cuyahoga: ok - 396,338 households, size p50/p99 371/524 B
  unlinked 139,341 · multi-unit 1,570 · stale 78,953 · duplicate parcels {'residential': 1879, 'demographic': 276, 'thermal': 22}
Franklin: ok - 475,376 households, size p50/p99 350/559 B
  unlinked 216,887 · multi-unit 1,272 · stale 12,344 · duplicate parcels {'residential': 71, 'demographic': 64, 'thermal': 0}
```

Runtime and memory (all three counties in one process): dry run 2:59 wall, 831 MB peak RSS; real build 3:51 wall, 831 MB peak RSS (the 4 GB stop threshold was not approached). Per-county times were not printed separately. Adams rebuild (idempotency run) completed in well under a minute.

## Drift

No `unmapped fields` or `unmapped values` lines in any dry run or build. `fields.json` was not edited. Against the pre-fix baseline the only change is the expected one: Cuyahoga multi-unit fell from 2,875 to 1,570 (MultiTenant no longer read); Franklin stayed at 1,272.

## Verification (Step 6)

- Per county: documents equal source meter counts (8,283 / 396,338 / 475,376); every document has six dims.
- Linked (bitmask 14): Adams 0, Cuyahoga 256,997, Franklin 258,489.
- Hashed ids `^h[0-9a-f]{32}$`: 8,283 / 139,341 / 216,887, equal to each county's unlinked count. Ids containing `:` or `|`: 0.
- No staging collections remain; three `ok` builds; no `|` in any build's error/unmapped_values; PII check (email, customer_name, address): 0.
- Indexes: county_1, parcel_key_1, link_1, county_1_dims.0_1 to county_1_dims.5_1.

## Spot checks (Step 7)

Five random households per county, plus ten extra per county-group drawn from households that carry `fpl_pct` and from households that carry `missing` codes (to cover linked records, since random samples in Adams and Franklin were all unlinked).

- `annual_kwh` equals the sum of the latest 12 source readings in every case; `last_read` matches. Where the household stores no annual_kwh the source has no 12-reading year inside the 300 to 400 day span (one such case, Franklin, has 12 readings but a span outside the window; not reproduced to the day).
- `fpl_pct` equals ceil(income / FPG(size)) from the 2026 table in all 15 checked cases (e.g. 45,000 / 4 persons = 136.4 stored 137). Where household size is `nan` or -1, or income is -1, `fpl_pct`, `hh_size`/`income_est` are absent and `missing` names code 2 or 1.
- `missing` codes name fields that are really blank in the matching source documents (codes 21 to 24 checked: owner, senior, children, length_residence).
- `year_built` and `sqft` match the Residential source. No unknown dimension reads 0 (unlinked homes show -1 for income, burden, inefficiency, vulnerability, electrification).
- No mismatch or bug found.

## Idempotency (Step 8)

Inserted a `probe-stale` Adams document, re-ran `build --county Adams`: the probe was removed by the rebuild, Adams count unchanged at 8,283, `analysis_builds` holds two Adams documents (both ok, 8,283), no staging collection left.

## Report tables

```
Adams: 8,283 households
  income_need            high 0 · moderate 0 · none 0 · unknown 8,283 · proxy 0
  energy_burden          high 0 · moderate 0 · none 0 · unknown 8,283 · proxy 0
  building_inefficiency  high 0 · moderate 0 · none 0 · unknown 8,283 · proxy 0
  high_usage             high 597 · moderate 895 · none 4,473 · unknown 2,318 · proxy 0
  vulnerability          high 0 · moderate 0 · none 0 · unknown 8,283 · proxy 0
  electrification        high 0 · moderate 0 · none 0 · unknown 8,283 · proxy 0
  Bill assistance candidate                  0 of 0 known-enough
  Weatherization candidate                   0 of 0 known-enough
  Electrification candidate                  0 of 0 known-enough
  Behavioural / efficiency (no income test)  0 of 0 known-enough
  Likely no benefit                          0 of 0 known-enough
Cuyahoga: 396,338 households
  income_need            high 3,743 · moderate 1,765 · none 3,324 · unknown 387,506 · proxy 0
  energy_burden          high 531 · moderate 567 · none 8,133 · unknown 387,107 · proxy 0
  building_inefficiency  high 17,170 · moderate 137,056 · none 75,896 · unknown 166,216 · proxy 144,306
  high_usage             high 25,064 · moderate 37,605 · none 187,970 · unknown 145,699 · proxy 0
  vulnerability          high 0 · moderate 6,257 · none 2,997 · unknown 387,084 · proxy 0
  electrification        high 0 · moderate 0 · none 7,600 · unknown 388,738 · proxy 0
  Bill assistance candidate                  3,743 of 8,832 known-enough
  Weatherization candidate                   5,006 of 8,832 known-enough
  Electrification candidate                  0 of 7,600 known-enough
  Behavioural / efficiency (no income test)  1,744 of 6,849 known-enough
  Likely no benefit                          68 of 8,727 known-enough
Franklin: 475,376 households
  income_need            high 25,321 · moderate 10,057 · none 8,276 · unknown 431,722 · proxy 0
  energy_burden          high 5,186 · moderate 6,062 · none 30,948 · unknown 433,180 · proxy 0
  building_inefficiency  high 7,197 · moderate 134,465 · none 115,567 · unknown 218,147 · proxy 221,253
  high_usage             high 31,563 · moderate 47,348 · none 236,681 · unknown 159,784 · proxy 0
  vulnerability          high 12,013 · moderate 8,948 · none 2,684 · unknown 451,731 · proxy 0
  electrification        high 0 · moderate 0 · none 0 · unknown 475,376 · proxy 0
  Bill assistance candidate                  25,321 of 43,654 known-enough
  Weatherization candidate                   28,615 of 43,634 known-enough
  Electrification candidate                  0 of 0 known-enough
  Behavioural / efficiency (no income test)  3,553 of 31,657 known-enough
  Likely no benefit                          837 of 35,498 known-enough
```

## Per-county measures

| | Adams | Cuyahoga | Franklin |
|---|---|---|---|
| multi_unit households | 0 | 1,570 | 1,272 |
| max annual_kwh | 11,998,000 | 433,857,536 | 3,583,305,000 |
| annual_kwh > 50,000 | 174 | 6,999 | 10,622 |
| annual_kwh > 100,000 | 75 | 4,224 | 6,183 |
| households with income_est | 0 | 9,232 | 44,811 |
| households with fpl_pct | 0 | 8,832 | 43,654 |
| burden_basis 0 / 1 | 7,281 / 0 | 283,887 / 9,622 | 374,781 / 27,336 |

The annual_kwh maxima are implausible for homes (gigawatt-hours), and thousands of meters exceed 50,000 kWh. These are likely commercial or bad meters sitting inside the household percentile distributions. P2 question: filter them, cap them, or leave them. The p90/p75 cut points are barely moved by them but the top tail is not household usage.

## Electrification is structurally empty in P1

`heat_fuel` comes only from Cuyahoga auditor `HTP` mapped to 1. No household can reach level 2, so the Electrification archetype is 0 by construction. Its only known denominator is the heat-pump homes: 7,600 in Cuyahoga (all level 0), none in Franklin or Adams (heat_fuel is unmapped there, so dimension is unknown for every household).

## Inefficiency: measured versus proxy

| level-1 households | Adams | Cuyahoga | Franklin |
|---|---|---|---|
| proxy-only (built before 1980) | 0 | 119,895 | 127,269 |
| measured (thermal percentile) | 0 | 17,161 | 7,196 |
| level 2 (always measured) | 0 | 17,170 | 7,197 |
| level 0 by proxy (built 1980 or later) | 0 | 24,411 | 93,984 |

In Franklin, 94.7% of level-1 inefficiency is proxy-only (127,269 of 134,465); in Cuyahoga 87.5% (119,895 of 137,056). The Weatherization archetype counts level 1 or above, so it is dominated by the age proxy. Adams has no residential data, so inefficiency is unknown for all 8,283.

## Boundary counts for threshold wording

ACEEE cites "above 6%" and "above 10%"; the rules use `>=`. `fpl_pct` and `ami_pct` are stored with ceil, so a stored 175 means a true value in (174, 175], and the rules compare `<=`, which treats such households as at or below 175 only when the stored integer is 175 or less. Burden is stored as a rounded 1-decimal percent.

| | Cuyahoga | Franklin |
|---|---|---|
| energy_burden exactly 6.0 | 23 | 267 |
| energy_burden exactly 10.0 | 4 | 83 |
| fpl_pct exactly 175 | 460 | 444 |
| fpl_pct exactly 200 | 0 | 0 |
| ami_pct exactly 80 | 0 | 0 |

Zero households sit at fpl 200 or ami 80, which is odd given 460 at 175; the income estimates appear to cluster on bin values (e.g. 45,000 / 57,500 / 112,500). The human should decide `>=` versus `>` for burden (about 290 Franklin and 27 Cuyahoga households move) and whether the 175 boundary households (904 total) belong in the high tier.

## Decisions taken this session (from the user)

- Surrogate meter ids are HMAC-hashed (key `ANALYSIS_ID_KEY`); linked meters keep opaque source ids.
- CuyahogaMultiTenant is dropped for P1; multi_unit derives only from several meters on one parcel.
- `owner_age` is not used for senior in P1.

## For the human

- Thresholds were not changed. Decide the `>=` / `>` wording for 6% and 10% burden.
- Income need is known for about 2% of Cuyahoga (8,832 of 396,338) and 9% of Franklin (43,654 of 475,376); all archetype denominators rest on those.
- Decide how P2 treats very large annual_kwh meters.
- Decide whether to map a heat fuel source for Franklin and Adams, otherwise the Electrification archetype stays empty.
