# Need analysis P2: live build results (all 88 counties)

Build date 2026-10-14, branch `feature/need-analysis-p2` at HEAD 21589ce. Rules version 2026-10-13.1, fields registry 2026-10-14.1, database `empower_development`. The build wrote only to `analysis_households`, `analysis_builds` and `analysis_coverage`. No source collection was written. This document holds counts only: no names, addresses, account numbers or `participant_id`.

## Dry runs and live runs

| run | HEAD | result | wall | peak RSS | what resolved it |
|---|---|---|---|---|---|
| dry run 1 | 96db293 | 18 ok / 70 failed (all on the unmapped field/value gate) | 10:02 | 825,012 KB | see Step 2 below |
| dry run 2 | 03c2b0e | 77 ok / 11 failed (only fields awaiting a user decision) | 10:05 | 830,484 KB | user mapping decisions, cc85280 |
| dry run 3 | cc85280 | **88 ok** | 9:40 | 830,512 KB | gate met; live build started |
| live run 1 | cc85280 | **42 ok / 46 failed** (cross-county `_id` collision at swap) | 12:53 | 830,748 KB | user decision: county-scoped hash, 21589ce |
| dry run 4 | 21589ce | 88 ok; statewide id pre-check 0 duplicates in 3,739,643 | 9:44 | 825,568 KB | - |
| **live run 2** | 21589ce | **88 ok, exit 0** | **14:52** | **830,824 KB** | - |

Peak RSS never came near the 4 GB stop.

### Dry run 1 to 2: ignored fields (commit 03c2b0e)

Dry run 1 failed 65 counties on `electrical.merged_ids`. The ElectricalDB repair adds that field to each fold survivor as bookkeeping, and the registry did not list it. Fields that cannot feed any of the six dimensions went to the `ignored` lists, with the roles corrected against the real collections:
- electrical: `merged_ids`, `parcel_zip`, `customer_name`, `zip_code`
- residential: `census_tract`, `res_city`
- demographic: `County`, `income_range`, `occupation`, `gender`, `education`, `ethnic_group`, `parcel_owner`, `parcel_city`

`customer_name` and `parcel_owner` carry PII. The engine never reads them.

`income_range` is redundant: no doc in the counties checked has it without `estimated_income`.

### Dry run 2 to 3: the user's mapping decisions (commit cc85280, fields v2026-10-14.1)
- `home_owner` (8 counties) maps into `owner`: Owner becomes true, Renter becomes false.
- Heat fuel comes from **Ottawa `heating_fuel_type` only**: ELECTRIC → 2, GAS → 3, OIL/SOLAR/GEOTHERMAL/COAL → 4.
  - NONE and the misaligned-row junk values (`"2023"`, one decimal string) → unknown. NaN reads as blank.
  - Athens/Huron `heat_type` `'NA'` (100% of their residential docs) → unknown.
- Ottawa `heating` is ignored, so heat-pump homes count by their fuel (ELECTRIC → level 2, electric resistance). This was the user's choice.
- `dwelling_type`, `land_use` and residential `household_size` are ignored for P2.

### Live run 1 failure and fix (commit 21589ce)

46 counties failed the pre-merge gate `N staged _id(s) already belong to another county`, with 150 ids in total.
- **Cause:** 1,102 surrogate ElectricalDB `_id`s exist in more than one county's collection (1,098 AES, 4 FE). Their readings are mostly disjoint (986), so these are different meters behind one key. The unscoped HMAC sent each shared key to one analysis `_id`, and the county built first alphabetically claimed it.
- **What the user saw:** examples included the `FE:OE:ALL` placeholder present in 25 counties, and AES keys built from street names only.
- **The user's decision:** hash surrogates over `county + '\x1f' + source id`.
- **Why the dry run passed:** the dry-run store never runs the swap, so it never exercised this gate.
- **Effect of the failure:** the collision check runs before `$merge`, and none of the 46 counties had an earlier version, so nothing was partly replaced. Live run 2 rebuilt all 88 counties. The 42 counties from run 1 were re-keyed, and the swap deleted their old unscoped ids.

## Live build stats per county (live run 2)

- Shares are of households.
- Usable fits: `thermal_r2 ≥ 0.5`, `hl_slope ≥ 0`, not multi-unit.
- Fallbacks: `owner_age` filling `senior`.
- Wall: the time from one county's `built_at` to the next. It covers pass 1, pass 2, swap and coverage. Peak RSS is per process: 830,824 KB for the whole run.

| county | households | unlinked | stale | nonres | priced | income known | usable fits | fallbacks (senior) | p99 B | wall |
|---|---|---|---|---|---|---|---|---|---|---|
| Adams | 8,283 | 8,283 | 0 | 174 | 85.8% | 0.0% | 0 | 0 | 264 | 0:01 |
| Allen | 42,643 | 16,985 | 709 | 1,037 | 84.6% | 4.2% | 2,386 | 12 | 537 | 0:10 |
| Ashland | 11,942 | 11,942 | 0 | 369 | 89.9% | 0.0% | 0 | 0 | 266 | 0:02 |
| Ashtabula | 32,700 | 32,700 | 0 | 649 | 91.3% | 0.0% | 0 | 0 | 268 | 0:06 |
| Athens | 24,894 | 17,602 | 941 | 517 | 80.9% | 2.9% | 1,549 | 98 | 491 | 0:05 |
| Auglaize | 3,911 | 3,911 | 0 | 74 | 94.1% | 0.0% | 0 | 0 | 267 | 0:00 |
| Belmont | 22,741 | 9,237 | 1,967 | 487 | 80.4% | 3.7% | 1,335 | 111 | 520 | 0:05 |
| Brown | 13,301 | 13,301 | 0 | 85 | 93.0% | 0.0% | 0 | 0 | 264 | 0:03 |
| Butler | 97,614 | 97,614 | 3 | 155 | 95.5% | 0.0% | 0 | 0 | 265 | 0:21 |
| Carroll | 5,060 | 5,060 | 0 | 136 | 88.6% | 0.0% | 0 | 0 | 266 | 0:01 |
| Champaign | 10,450 | 10,450 | 1 | 172 | 91.1% | 0.0% | 0 | 0 | 268 | 0:02 |
| Clark | 41,054 | 41,054 | 0 | 992 | 90.7% | 0.0% | 0 | 0 | 264 | 0:08 |
| Clermont | 76,974 | 76,974 | 2 | 179 | 95.3% | 0.0% | 0 | 0 | 267 | 0:19 |
| Clinton | 17,462 | 17,462 | 2 | 381 | 91.1% | 0.0% | 0 | 0 | 266 | 0:03 |
| Columbiana | 35,254 | 35,254 | 0 | 852 | 90.1% | 0.0% | 0 | 0 | 269 | 0:07 |
| Coshocton | 16,478 | 7,426 | 5,687 | 250 | 59.8% | 5.1% | 1,676 | 28 | 493 | 0:03 |
| Crawford | 12,456 | 12,456 | 0 | 261 | 89.3% | 0.0% | 0 | 0 | 267 | 0:02 |
| Cuyahoga | 381,313 | 124,461 | 78,708 | 6,493 | 71.9% | 2.3% | 85,895 | 2,715 | 524 | 1:59 |
| Darke | 16,847 | 16,847 | 3 | 389 | 92.9% | 0.0% | 0 | 0 | 264 | 0:03 |
| Defiance | 11,855 | 11,855 | 0 | 282 | 91.1% | 0.0% | 0 | 0 | 267 | 0:02 |
| Delaware | 75,574 | 75,574 | 1 | 1,713 | 87.5% | 0.0% | 0 | 0 | 267 | 0:13 |
| Erie | 27,617 | 27,617 | 0 | 749 | 90.7% | 0.0% | 0 | 0 | 263 | 0:05 |
| Fairfield | 23,806 | 23,806 | 0 | 497 | 86.3% | 0.0% | 0 | 0 | 268 | 0:05 |
| Fayette | 12,782 | 5,514 | 6 | 333 | 72.0% | 4.0% | 749 | 2 | 548 | 0:03 |
| Franklin | 475,204 | 216,700 | 12,177 | 10,620 | 82.4% | 9.2% | 35,976 | 497 | 559 | 2:05 |
| Fulton | 13,954 | 13,954 | 0 | 378 | 91.0% | 0.0% | 0 | 0 | 265 | 0:02 |
| Gallia | 9,139 | 9,139 | 2 | 278 | 85.2% | 0.0% | 0 | 0 | 265 | 0:01 |
| Geauga | 26,192 | 26,192 | 0 | 700 | 92.7% | 0.0% | 0 | 0 | 265 | 0:05 |
| Greene | 67,302 | 67,302 | 3 | 1,176 | 92.8% | 0.0% | 0 | 0 | 265 | 0:13 |
| Guernsey | 15,672 | 7,880 | 2,594 | 350 | 74.8% | 5.3% | 1,498 | 80 | 528 | 0:03 |
| Hamilton | 267,153 | 267,153 | 7 | 768 | 92.6% | 0.0% | 0 | 0 | 267 | 1:08 |
| Hancock | 23,822 | 18,742 | 840 | 563 | 83.8% | 5.5% | 476 | 41 | 557 | 0:05 |
| Hardin | 11,496 | 5,484 | 1,768 | 217 | 72.8% | 0.0% | 1,037 | 0 | 360 | 0:02 |
| Harrison | 8,140 | 4,064 | 2,195 | 150 | 65.0% | 4.5% | 566 | 46 | 512 | 0:01 |
| Henry | 3,332 | 3,332 | 0 | 62 | 93.9% | 0.0% | 0 | 0 | 264 | 0:00 |
| Highland | 11,431 | 11,431 | 1 | 271 | 89.1% | 0.0% | 0 | 0 | 267 | 0:02 |
| Hocking | 9,126 | 9,126 | 0 | 177 | 86.4% | 0.0% | 0 | 0 | 266 | 0:01 |
| Holmes | 14,110 | 5,659 | 7,649 | 310 | 38.9% | 0.5% | 820 | 7 | 392 | 0:02 |
| Huron | 17,035 | 10,454 | 2,898 | 384 | 90.2% | 35.1% | 4,326 | 0 | 492 | 0:04 |
| Jackson | 8,699 | 8,699 | 0 | 119 | 88.8% | 0.0% | 0 | 0 | 266 | 0:01 |
| Jefferson | 28,257 | 28,257 | 0 | 531 | 88.0% | 0.0% | 0 | 0 | 268 | 0:06 |
| Knox | 17,915 | 17,915 | 0 | 425 | 86.4% | 0.0% | 0 | 0 | 263 | 0:03 |
| Lake | 64,269 | 64,269 | 0 | 1,288 | 92.7% | 0.0% | 0 | 0 | 263 | 0:13 |
| Lawrence | 22,095 | 7,487 | 2,281 | 323 | 77.8% | 10.0% | 1,940 | 300 | 538 | 0:05 |
| Licking | 53,036 | 53,036 | 0 | 1,193 | 87.2% | 0.0% | 0 | 0 | 266 | 0:11 |
| Logan | 16,824 | 16,824 | 8 | 325 | 92.3% | 0.0% | 0 | 0 | 264 | 0:03 |
| Lorain | 74,172 | 74,172 | 0 | 1,477 | 90.6% | 0.0% | 0 | 0 | 265 | 0:15 |
| Lucas | 118,030 | 118,030 | 0 | 2,722 | 88.5% | 0.0% | 0 | 0 | 264 | 0:28 |
| Madison | 11,027 | 11,027 | 0 | 309 | 89.4% | 0.0% | 0 | 0 | 266 | 0:02 |
| Mahoning | 71,819 | 71,819 | 0 | 1,732 | 90.2% | 0.0% | 0 | 0 | 267 | 0:14 |
| Marion | 17,140 | 6,363 | 181 | 432 | 85.1% | 6.7% | 5,680 | 34 | 550 | 0:04 |
| Medina | 40,360 | 40,360 | 0 | 971 | 93.1% | 0.0% | 0 | 0 | 265 | 0:08 |
| Meigs | 9,519 | 9,519 | 0 | 122 | 83.7% | 0.0% | 0 | 0 | 264 | 0:01 |
| Mercer | 8,430 | 8,430 | 0 | 262 | 93.3% | 0.0% | 0 | 0 | 265 | 0:01 |
| Miami | 28,121 | 28,121 | 1 | 514 | 92.0% | 0.0% | 0 | 0 | 264 | 0:05 |
| Monroe | 967 | 967 | 0 | 13 | 89.2% | 0.0% | 0 | 0 | 265 | 0:00 |
| Montgomery | 260,061 | 118,365 | 36,241 | 5,000 | 72.9% | 0.0% | 26,931 | 0 | 391 | 1:09 |
| Morgan | 6,659 | 5,201 | 720 | 90 | 80.7% | 2.6% | 233 | 15 | 487 | 0:01 |
| Morrow | 4,563 | 3,328 | 365 | 110 | 84.9% | 5.2% | 181 | 2 | 543 | 0:01 |
| Muskingum | 36,474 | 15,699 | 3,342 | 820 | 79.7% | 4.8% | 3,376 | 157 | 530 | 0:08 |
| Noble | 2,126 | 2,126 | 0 | 53 | 87.0% | 0.0% | 0 | 0 | 264 | 0:00 |
| Ottawa | 22,298 | 10,105 | 3,452 | 390 | 81.6% | 5.7% | 6,571 | 472 | 519 | 0:06 |
| Paulding | 4,976 | 4,976 | 0 | 101 | 86.3% | 0.0% | 0 | 0 | 267 | 0:01 |
| Perry | 12,068 | 12,068 | 0 | 186 | 88.4% | 0.0% | 0 | 0 | 264 | 0:02 |
| Pickaway | 9,066 | 9,066 | 0 | 214 | 86.3% | 0.0% | 0 | 0 | 267 | 0:01 |
| Pike | 9,490 | 9,490 | 0 | 242 | 85.6% | 0.0% | 0 | 0 | 263 | 0:02 |
| Portage | 49,988 | 49,988 | 0 | 1,243 | 91.1% | 0.0% | 0 | 0 | 266 | 0:10 |
| Preble | 15,492 | 15,492 | 5 | 290 | 94.1% | 0.0% | 0 | 0 | 265 | 0:03 |
| Putnam | 11,112 | 8,696 | 1,493 | 197 | 79.7% | 5.9% | 562 | 9 | 550 | 0:02 |
| Richland | 35,498 | 20,853 | 144 | 957 | 82.1% | 3.2% | 6,873 | 20 | 549 | 0:08 |
| Ross | 21,201 | 11,849 | 443 | 532 | 84.5% | 0.0% | 978 | 0 | 381 | 0:04 |
| Sandusky | 20,795 | 20,795 | 0 | 510 | 91.5% | 0.0% | 0 | 0 | 267 | 0:03 |
| Scioto | 34,534 | 23,098 | 3,531 | 697 | 78.3% | 0.0% | 2,440 | 0 | 383 | 0:07 |
| Seneca | 20,218 | 20,218 | 0 | 464 | 87.8% | 0.0% | 0 | 0 | 265 | 0:04 |
| Shelby | 13,915 | 13,915 | 1 | 430 | 91.7% | 0.0% | 0 | 0 | 265 | 0:02 |
| Stark | 140,738 | 140,738 | 0 | 3,236 | 88.8% | 0.0% | 0 | 0 | 264 | 0:27 |
| Summit | 146,192 | 146,192 | 0 | 3,415 | 90.4% | 0.0% | 0 | 0 | 265 | 0:31 |
| Trumbull | 52,441 | 52,441 | 0 | 1,039 | 92.0% | 0.0% | 0 | 0 | 267 | 0:11 |
| Tuscarawas | 30,652 | 30,652 | 0 | 647 | 87.5% | 0.0% | 0 | 0 | 269 | 0:06 |
| Union | 14,920 | 14,920 | 0 | 347 | 90.5% | 0.0% | 0 | 0 | 264 | 0:03 |
| VanWert | 9,117 | 9,117 | 1 | 251 | 87.6% | 0.0% | 0 | 0 | 266 | 0:01 |
| Vinton | 5,068 | 5,068 | 0 | 90 | 87.4% | 0.0% | 0 | 0 | 265 | 0:01 |
| Warren | 74,755 | 74,755 | 2 | 311 | 96.4% | 0.0% | 0 | 0 | 265 | 0:15 |
| Washington | 22,130 | 22,130 | 0 | 440 | 86.5% | 0.0% | 0 | 0 | 269 | 0:04 |
| Wayne | 28,317 | 28,317 | 0 | 720 | 89.2% | 0.0% | 0 | 0 | 264 | 0:05 |
| Williams | 3,694 | 3,694 | 0 | 88 | 92.3% | 0.0% | 0 | 0 | 267 | 0:00 |
| Wood | 26,456 | 26,456 | 0 | 685 | 90.0% | 0.0% | 0 | 0 | 263 | 0:05 |
| Wyandot | 7,830 | 5,784 | 2,036 | 148 | 73.7% | 7.9% | 720 | 12 | 532 | 0:01 |
| **Total** | **3,739,643** | 2,880,884 | 172,411 | 70,331 | 85.2% (3,186,873) | 2.0% (74,954) | 194,774 | 4,658 | max 559 | |

### Statewide level counts (sum of the 88 coverage docs)

```
income_need            high 46,508 · moderate 13,036 · none 15,410 · unknown 3,664,689
energy_burden          high 10,091 · moderate 11,661 · none 52,276 · unknown 3,665,615
building_inefficiency  high 38,976 · moderate 476,198 · none 292,307 · unknown 2,932,162
high_usage             high 280,201 · moderate 420,230 · none 2,100,885 · unknown 938,327
vulnerability          high 16,023 · moderate 44,244 · none 4,835 · unknown 3,674,541
electrification        high 1,848 · moderate 0 · none 16,925 · unknown 3,720,870
Bill assistance candidate                  46,382 of 74,794 known-enough
Weatherization candidate                   45,894 of 73,863 known-enough (36,387 rest on the age proxy)
Electrification candidate                   1,837 of 18,720 known-enough (all Ottawa)
Behavioural / efficiency (no income test)   6,304 of 50,922 known-enough
Likely no benefit                           1,339 of 59,913 known-enough
```

Electrification now has measured level 2 only in Ottawa (1,848). Cuyahoga's `HTP` heat pumps give 7,600 at level 0. Every other county is unknown, and `heat_fuel_source` is `none` in 86 counties.

## Reconcile (sampled)

`python -m src.analysis_engine.cli reconcile` counts meters, linked, stale and nonres independently from the sources and compares them with `analysis_coverage`. Exit 0, wall 0:56.

```
Franklin: ok
Allen: ok
Hamilton: ok
Montgomery: ok
Meigs: ok
```

## Verification (read-only)

- `analysis_builds`: 88 records from live run 2, **88 `ok`**, one per county.
  - Every record has `rules_version` 2026-10-13.1 and `registry_version` (fields) 2026-10-14.1.
  - Each county's latest build is from this run. **No `coverage_error`.**
- `analysis_coverage` holds **88 docs**, all from this run.
  - **85** have `hud_estimated: true`. Adams, Cuyahoga and Franklin have false.
- **No staging collections** remain.
- `analysis_households` holds 3,739,643 docs, which equals the live ElectricalDB total. Docs equal meters in every county.
- **PII check:** 0 docs carry any of `customer_name`, `email`, `address`, `service_address` or `account_id`. 0 carry `participant_id`.
- **Ids.** Hashed ids match P1's pattern `^h[0-9a-f]{32}$` (2,882,042 of them). 0 ids contain `:` or `|`. The rest are 612,616 ObjectIds and 244,985 opaque 32-hex strings.
  - Hashed equals unlinked in every county except five. Montgomery is +1,124, Franklin +15, Cuyahoga +13, Athens +5 and Ottawa +1. Each equals the repair's per-county `promoted` count: linked fold survivors whose source `_id` is a surrogate, hashed as designed.
- **County-scoped id check.** I recomputed `analysis_id(source _id, key, county)` from every county's ElectricalDB. For **each of the 88 counties**, the live doc count equals the count of live ids that match a recomputed id, and equals the source meter count: 3,739,643 of 3,739,643 matched. So no live doc carries an unscoped surrogate hash.

## Step 3: expected deltas

The brief's ranges come from the impl kickoff, and that predates the user's approval of the Jan/Aug cross-delivery fold (FE/AES delivery folds 392,008). Every household drop equals the county's `deleted` count in `20261013_1701_need_analysis_p2_repair.md` exactly. Montgomery also gained 1 created doc.

| check | brief expected | observed | explanation |
|---|---|---|---|
| Cuyahoga households | 396,338 − ~10k | 381,313 (−15,025) | repair deleted 15,025 (158 parcel + 87 address + 14,780 delivery folds) |
| Franklin households | 475,376 − ~1.2k | 475,204 (−172) | repair deleted 172 (167 address + 5 delivery) |
| Huron households | −257 | 17,035 (−515 from 17,550) | 257 parcel + 258 delivery folds |
| Montgomery households | −19k … −31k | 260,061 (−79,273 from 339,334) | 5,910 address + 73,364 delivery folds, +1 created |
| Total nonres | ≈ 59.5k + ~17.8k minus folded | 70,331 (P1 counties 17,287; other 85 counties 53,044) | the pre-repair estimate counted both docs of folded pairs (not verified per county) |
| P1 priced share rises | up | Adams 87.9% → 85.8%; Cuyahoga 74.1% → 71.9%; Franklin 84.6% → 82.4% | it falls: nonres meters no longer get a computed bill (Adams −174 = its nonres). The P1 counties already priced through `county_default_utility`, so the backfill could not raise them |

## Step 4: spot checks (dry run 1, re-confirmed by the unchanged engine logic)

- **Sample:** five random households each in Montgomery (fold survivors only), Holmes and Lucas. Six extra Holmes meters were linked to Demographic, to exercise `senior` and vendor cost.
- **Method:** each household was compared field by field with values recomputed independently from the raw ElectricalDB doc and a direct Demographic query: `annual_kwh` (latest 12 readings over 300–400 days), `last_read`, `nonres` (> 50,000 kWh), `annual_cost` (vendor cost, else kWh × the rate for the doc's utility or the county default, when fresh and not nonres) and `senior` (md_/presence_of_senior, else `owner_age` ≥ 65).
- **Result: 21 of 21 match on every item.**
  - Montgomery survivors carry 19–21 readings (Jan and Aug merged), priced at AES 0.1612.
  - One Lucas meter at 55,147 kWh is nonres with no computed bill.
  - 4 of 5 Holmes samples are stale at 25 months, so they are unpriced.
  - Vendor cost is kept even on stale meters.
  - `senior` was exercised only through the `owner_age` fallback (Holmes has no `md_presence_of_senior`).
- No engine bug was found.
- Live run 2 changed only the hash input of surrogate `_id`s, so the checked values are unaffected.

## Heat-type scan (Task 9)

`scripts/scan_heat_type_fields_tool.py` (read-only, sampling 2,000 docs per county) scanned 25 CountyResidential collections; 21 have no heat field.
- **Cuyahoga `heat_type`:** assessor system codes (FHA, HWS, HTP, GRV, RAD, UNH). These describe the system, not the fuel. Only `HTP` maps (to 1).
- **Athens and Huron `heat_type`:** only `'NA'`.
- **Ottawa:** the only real fuel source. Full-collection `heating_fuel_type`: GAS 13,780, ELECTRIC 2,686, blank 1,469, OIL 486, NONE 5, GEOTHERMAL 4, COAL 4, `"2023"` 3, SOLAR 2, one decimal string.
  - Ottawa residential has about 1,469 all-blank rows and a few misaligned rows.

## For the human

- **Unpriced non-stale meters:** the repair counted 23,648 (by missing `utility`). Re-counted from the live build, there are **22,818** fresh, non-nonres households with an annual kWh and no bill: Montgomery 17,178, Richland 2,857, Fayette 2,362 and Marion 421. Every other county is 0. The difference from 23,648 is meters that are nonres or lack a valid 12-reading year. Montgomery's remainder is likely AES meters with no utility on the doc and no county default.
- **Montgomery AES surrogate keys without a house number:** 28,258 of Montgomery's 119,153 AES surrogate keys have no house number. Each such key may be a within-county union of different meters on one street. This is **unresolved**: county scoping fixes only the cross-county case.
- **CountyKeys:** no disagreements (every listed name equals the conventional collection name). Four names are missing: `HardinCountyDemographic`, `MontgomeryCountyDemographic`, `RossCountyDemographic` and `SciotoCountyDemographic` are listed in CountyKeys but do not exist.
- **Heat type:** measured only in Ottawa.
  - Ottawa: 1,848 at level 2, 9,325 at level 0, 11,125 unknown. Cuyahoga: 7,600 at level 0.
  - Heat pumps count as electric resistance (level 2), by the user's choice to ignore Ottawa `heating`.
  - COAL → 4 (a real fuel, "other"). NONE → unknown (no-heat is not a fuel; unknown is never coerced).
  - Electrification stays unknown in 86 counties.
- **Hancock thermal** (flagged at 70% in planning).
  - 4,988 households link to a thermal doc and 4,361 carry an r². Only 706 reach r² ≥ 0.5, and 1,152 have a negative heating slope.
  - So **usable fits are 476 (2.0% of 23,822 households)**, and Hancock inefficiency rests almost entirely on the age proxy.
- **85 counties use ESTIMATED HUD limits.** These are copies of the Adams row in `rules.json` `tables.hud_low_income_fy2026` (`estimated: true`): Allen, Ashland, Ashtabula, Athens, Auglaize, Belmont, Brown, Butler, Carroll, Champaign, Clark, Clermont, Clinton, Columbiana, Coshocton, Crawford, Darke, Defiance, Delaware, Erie, Fairfield, Fayette, Fulton, Gallia, Geauga, Greene, Guernsey, Hamilton, Hancock, Hardin, Harrison, Henry, Highland, Hocking, Holmes, Huron, Jackson, Jefferson, Knox, Lake, Lawrence, Licking, Logan, Lorain, Lucas, Madison, Mahoning, Marion, Medina, Meigs, Mercer, Miami, Monroe, Montgomery, Morgan, Morrow, Muskingum, Noble, Ottawa, Paulding, Perry, Pickaway, Pike, Portage, Preble, Putnam, Richland, Ross, Sandusky, Scioto, Seneca, Shelby, Stark, Summit, Trumbull, Tuscarawas, Union, VanWert, Vinton, Warren, Washington, Wayne, Williams, Wood and Wyandot.
  - `ami_pct` in these counties is approximate.
  - **Replacement path (Task 4b):** load the real FY2026 HUD income limits per county into the table with `estimated: false`, bump the rules version, and rebuild. `hud_estimated` in coverage then turns false per county.
- **The P1 counties' priced share fell** (Adams 85.8%, Cuyahoga 71.9%, Franklin 82.4%). The cause is the nonres rule (no computed bill above 50,000 kWh), plus Cuyahoga's 15k folded docs. This is expected behaviour, not a regression.
- **Holmes is stale at 25 months.** 7,649 of 14,110 meters are stale; the spot-checked ones last read in 2024-09, one month past the 24-month window at build month 2026-10, so Holmes is priced at 38.9%. Those linked meters also lack `utility`, and Holmes has no county default. A newer delivery is needed. Other counties from the same delivery vintage will cross the line in later months.
- **New scripts not in `script_descriptions.md`** (that file carries the user's uncommitted edits, so it was not touched). Both are documented in `.claude_docs/tools.md`:
  - `scripts/scan_heat_type_fields_tool.py`: a read-only heat/fuel field scan.
  - `scripts/repair_electrical_ingest_tool.py`: the ElectricalDB fold repair, dry by default.
- **Threshold wording** from P1 is still open: `>=` versus `>` at 6% and 10% burden, and the fpl 175 boundary. Coverage `boundary` counts per county carry those numbers (Franklin: burden 6.0 = 267, 10.0 = 83, fpl 175 = 444).
