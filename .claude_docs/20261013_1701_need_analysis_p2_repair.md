# Need Analysis P2: ElectricalDB repair and utility backfill, results

**Status: LIVE-APPLIED to `empower_development` on 2026-10-13 (HEAD 2d5e626).** The repair and the utility backfill
(`--exclude AES:jan2026`) were run live; every counter matched rehearsal v3. See "Live run (2026-10-13)" at the end.
The scratch DBs `empower_p2_rehearsal` and `empower_p2_rehearsal2` have been dropped. The sections below record the pre-gate work.

Branch feature/need-analysis-p2, HEAD 1f24940. Run on 2026-10-13. **Pre-gate sections: nothing was written to `empower_development`** (the live run is at the end).
Pre-gate writes went only to the throwaway DB `empower_p2_rehearsal` (dropped after the live run). The doc shows counts and ids only.

**Update (rehearsal v3, HEAD 2d5e626): B7 failure FIXED by 2d5e626; see "Rehearsal v3" below. Original v2 status follows.**

**Status: rehearsal complete. B6 PASS, B7 FAIL.** The repair (B1–B3) and the backfill (B4–B6) behave as designed.
However, in the planned order (repair, then backfill with only `--exclude AES:jan2026`), the jan2026 **FE** ingest re-creates the 163,661 FE jan
surrogate docs that the repair's cross-delivery fold deleted, and a second repair dry run (B7) would fold 163,631 of them again.
See "Surprises" item 1. A decision is needed before going live.

## Decisions recorded
- **FE in the cross-delivery fold (type d): approved by the user on 2026-10-13.** The fold appends: verified on 1,969 Summit FE
  pairs (all jan+aug readings kept, 1,912 gained earlier months). The repair rehearsal B1–B3 stands as run.
- **Why January docs are deleted** (the user's question): the January doc's readings are copied into the August doc first, and only the
  duplicate container is then removed. The user chose to continue with copy-then-delete. The loss is limited to the January doc's
  metadata (its `_id`, `account_id`, `service_city`), which the backup
  (backups/empower_development_20261013_pre_p2_repair.archive.gz) keeps.

## Backup
- Path: backups/empower_development_20261013_pre_p2_repair.archive.gz (git-ignored), 768,275,255 bytes (733 MiB).
- mongodump 100.x has no `--nsInclude`. The archive was made with `--db empower_development --gzip --archive=...` plus one
  `--excludeCollection` per non-ElectricalDB collection (86 of 174 excluded, 88 ElectricalDB kept).
- Verified twice. First, a `--dryRun --nsInclude 'empower_development.*ElectricalDB'` found 88 namespaces. Second, it was **restored in full
  into `empower_p2_rehearsal`** (mongorestore 100.14.1; `--nsInclude 'empower_development.*ElectricalDB' --nsFrom
  'empower_development.*' --nsTo 'empower_p2_rehearsal.*'`): 88 collections, 4,138,839 docs, and per-collection counts identical
  to `empower_development`.

## Safety
- S1 (DB pinning): `src/utils/envvars.py` loads `~/.env` and then `./.env` with `override=True`, so setting `MONGODB_DATABASE` in the shell alone is
  clobbered. The wrapper `scratchpad/task3/v2/run_tool_on_db.py <db> <script> [args]` constructs the `EnvVars` singleton
  first, sets `MONGODB_DATABASE`, clears its cache, asserts `get_empower_db().name == <db>` (aborting otherwise), and then
  `runpy`s the tool. Every rehearsal log starts with `[wrapper] get_empower_db().name = empower_p2_rehearsal`. No tracked
  file or `.env` was edited.
- S2: `empower_development` ElectricalDB totals around both `--execute` runs (B2 repair, B5 backfill):
  before and after each = 88 collections, 4,138,839 docs total, Montgomery 339,334, Greene 112,140, Huron 17,550. **Unchanged.**
- R2: all 25 `*CountyResidential` collections were copied into the rehearsal DB (1,128,212 docs, 0 count mismatches).

## Real repair dry run on empower_development (A1)
Totals: parcel_folds 415, address_folds 6,802, **delivery_folds 392,008**, promoted 1,158, utility_from_fold 4,795,
**deleted 399,225**. Skips: multi_preingest 10, conflict 11,719, multi_candidate 11,337, none 4,199,
cross_delivery 0, promote_multi 58. The ElectricalDB total would go from 4,138,839 to 3,739,614 docs.

Counties with any non-zero counter (17 counties are all zero):

| county | parcel_folds | address_folds | delivery_folds | promoted | utility_from_fold | deleted | skipped_multi_preingest | skipped_conflict | skipped_multi_candidate | skipped_none | skipped_cross_delivery | skipped_promote_multi |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Allen | 0 | 0 | 14 | 0 | 0 | 14 | 0 | 1 | 47 | 0 | 0 | 0 |
| Ashland | 0 | 0 | 7890 | 0 | 0 | 7890 | 0 | 100 | 0 | 0 | 0 | 0 |
| Ashtabula | 0 | 0 | 208 | 0 | 0 | 208 | 0 | 47 | 0 | 0 | 0 | 0 |
| Athens | 0 | 561 | 0 | 5 | 561 | 561 | 0 | 0 | 216 | 33 | 0 | 0 |
| Auglaize | 0 | 0 | 1966 | 0 | 0 | 1966 | 0 | 58 | 0 | 0 | 0 | 0 |
| Belmont | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| Butler | 0 | 0 | 394 | 0 | 0 | 394 | 0 | 10 | 0 | 0 | 0 | 0 |
| Champaign | 0 | 0 | 6813 | 0 | 0 | 6813 | 0 | 215 | 0 | 0 | 0 | 0 |
| Clark | 0 | 0 | 3863 | 0 | 0 | 3863 | 0 | 135 | 0 | 0 | 0 | 0 |
| Clermont | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Clinton | 0 | 0 | 10170 | 0 | 0 | 10170 | 0 | 328 | 0 | 0 | 0 | 0 |
| Columbiana | 0 | 0 | 139 | 0 | 0 | 139 | 0 | 17 | 0 | 0 | 0 | 0 |
| Coshocton | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 78 | 0 | 0 |
| Crawford | 0 | 0 | 1412 | 0 | 0 | 1412 | 0 | 32 | 0 | 0 | 0 | 0 |
| Cuyahoga | 158 | 87 | 14780 | 13 | 244 | 15025 | 0 | 1077 | 792 | 138 | 0 | 0 |
| Darke | 0 | 0 | 10579 | 0 | 0 | 10579 | 0 | 257 | 0 | 0 | 0 | 0 |
| Defiance | 0 | 0 | 4026 | 0 | 0 | 4026 | 0 | 38 | 0 | 0 | 0 | 0 |
| Delaware | 0 | 0 | 239 | 0 | 0 | 239 | 0 | 6 | 0 | 0 | 0 | 0 |
| Erie | 0 | 0 | 4828 | 0 | 0 | 4828 | 0 | 103 | 0 | 0 | 0 | 0 |
| Fayette | 0 | 2 | 3253 | 0 | 1 | 3255 | 0 | 117 | 13 | 9 | 0 | 0 |
| Franklin | 0 | 167 | 5 | 15 | 167 | 172 | 8 | 0 | 307 | 580 | 0 | 0 |
| Fulton | 0 | 0 | 7171 | 0 | 0 | 7171 | 0 | 130 | 0 | 0 | 0 | 0 |
| Geauga | 0 | 0 | 6705 | 0 | 0 | 6705 | 0 | 103 | 0 | 0 | 0 | 0 |
| Greene | 0 | 0 | 44838 | 0 | 0 | 44838 | 0 | 1155 | 0 | 0 | 0 | 0 |
| Guernsey | 0 | 2 | 0 | 0 | 2 | 2 | 0 | 0 | 34 | 40 | 0 | 0 |
| Hamilton | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 3 | 0 | 0 | 0 | 0 |
| Hancock | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Hardin | 0 | 0 | 77 | 0 | 0 | 77 | 0 | 5 | 0 | 0 | 0 | 0 |
| Harrison | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 34 | 47 | 0 | 0 |
| Henry | 0 | 0 | 2104 | 0 | 0 | 2104 | 0 | 23 | 0 | 0 | 0 | 0 |
| Highland | 0 | 0 | 3229 | 0 | 0 | 3229 | 0 | 91 | 0 | 0 | 0 | 0 |
| Holmes | 0 | 0 | 7 | 0 | 0 | 7 | 0 | 0 | 4 | 6 | 0 | 0 |
| Huron | 257 | 0 | 258 | 0 | 257 | 515 | 0 | 25 | 164 | 0 | 0 | 0 |
| Knox | 0 | 0 | 120 | 0 | 0 | 120 | 0 | 1 | 0 | 0 | 0 | 0 |
| Lake | 0 | 0 | 5841 | 0 | 0 | 5841 | 0 | 163 | 0 | 0 | 0 | 0 |
| Lawrence | 0 | 2 | 0 | 0 | 2 | 2 | 0 | 0 | 6 | 4 | 0 | 0 |
| Logan | 0 | 0 | 11007 | 0 | 0 | 11007 | 0 | 285 | 0 | 0 | 0 | 0 |
| Lorain | 0 | 0 | 17100 | 0 | 0 | 17100 | 0 | 383 | 0 | 0 | 0 | 0 |
| Lucas | 0 | 0 | 11765 | 0 | 0 | 11765 | 0 | 488 | 0 | 0 | 0 | 0 |
| Madison | 0 | 0 | 804 | 0 | 0 | 804 | 0 | 38 | 0 | 0 | 0 | 0 |
| Mahoning | 0 | 0 | 10636 | 0 | 0 | 10636 | 0 | 253 | 0 | 0 | 0 | 0 |
| Marion | 0 | 3 | 40 | 0 | 3 | 43 | 1 | 26 | 16 | 0 | 0 | 0 |
| Medina | 0 | 0 | 896 | 0 | 0 | 896 | 0 | 59 | 0 | 0 | 0 | 0 |
| Mercer | 0 | 0 | 5680 | 0 | 0 | 5680 | 0 | 93 | 0 | 0 | 0 | 0 |
| Miami | 0 | 0 | 19380 | 0 | 0 | 19380 | 0 | 444 | 0 | 0 | 0 | 0 |
| Montgomery | 0 | 5910 | 73364 | 1124 | 3491 | 79274 | 0 | 3296 | 7432 | 3209 | 0 | 58 |
| Morgan | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 2 | 0 | 0 |
| Morrow | 0 | 0 | 48 | 0 | 0 | 48 | 0 | 7 | 0 | 0 | 0 | 0 |
| Muskingum | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 39 | 51 | 0 | 0 |
| Ottawa | 0 | 67 | 86 | 1 | 66 | 153 | 0 | 13 | 167 | 1 | 0 | 0 |
| Pickaway | 0 | 0 | 529 | 0 | 0 | 529 | 0 | 14 | 0 | 0 | 0 | 0 |
| Portage | 0 | 0 | 1018 | 0 | 0 | 1018 | 0 | 70 | 0 | 0 | 0 | 0 |
| Preble | 0 | 0 | 10150 | 0 | 0 | 10150 | 0 | 208 | 0 | 0 | 0 | 0 |
| Putnam | 0 | 0 | 59 | 0 | 0 | 59 | 0 | 1 | 0 | 0 | 0 | 0 |
| Richland | 0 | 1 | 5042 | 0 | 1 | 5043 | 1 | 147 | 899 | 0 | 0 | 0 |
| Ross | 0 | 0 | 29 | 0 | 0 | 29 | 0 | 0 | 13 | 1 | 0 | 0 |
| Sandusky | 0 | 0 | 224 | 0 | 0 | 224 | 0 | 16 | 0 | 0 | 0 | 0 |
| Scioto | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1142 | 0 | 0 | 0 |
| Seneca | 0 | 0 | 6 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| Shelby | 0 | 0 | 9344 | 0 | 0 | 9344 | 0 | 214 | 0 | 0 | 0 | 0 |
| Stark | 0 | 0 | 8862 | 0 | 0 | 8862 | 0 | 162 | 0 | 0 | 0 | 0 |
| Summit | 0 | 0 | 38952 | 0 | 0 | 38952 | 0 | 737 | 0 | 0 | 0 | 0 |
| Trumbull | 0 | 0 | 2498 | 0 | 0 | 2498 | 0 | 64 | 0 | 0 | 0 | 0 |
| Tuscarawas | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Union | 0 | 0 | 7175 | 0 | 0 | 7175 | 0 | 109 | 0 | 0 | 0 | 0 |
| VanWert | 0 | 0 | 419 | 0 | 0 | 419 | 0 | 8 | 0 | 0 | 0 | 0 |
| Warren | 0 | 0 | 5423 | 0 | 0 | 5423 | 0 | 90 | 0 | 0 | 0 | 0 |
| Wayne | 0 | 0 | 2916 | 0 | 0 | 2916 | 0 | 60 | 0 | 0 | 0 | 0 |
| Williams | 0 | 0 | 1768 | 0 | 0 | 1768 | 0 | 39 | 0 | 0 | 0 | 0 |
| Wood | 0 | 0 | 5854 | 0 | 0 | 5854 | 0 | 155 | 0 | 0 | 0 | 0 |
| Wyandot | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| **TOTAL** | **415** | **6802** | **392008** | **1158** | **4795** | **399225** | **10** | **11719** | **11337** | **4199** | **0** | **58** |

## Rehearsal on empower_p2_rehearsal
| Step | Expectation | Result |
|---|---|---|
| B1 repair dry | equals A1 exactly | **PASS**: report body byte-identical to A1 (diff empty) |
| B2 repair `--execute` | counters = B1; S2 unchanged | **PASS**: same counters; 399,225 docs removed (4,138,839 to 3,739,614); dev unchanged |
| B3 repair dry again | zero action counters | **PASS**: all six action counters 0. Skips unchanged (10 / 11,719 / 11,337 / 4,199 / 0 / 58) |
| B4 backfill dry | expected live numbers | done; see below |
| B5 backfill `--execute` | S2 unchanged | done; dev unchanged; rehearsal total 3,739,614 to 3,903,275 (+163,661 docs created) |
| B6 backfill dry again | docs_updated, docs_created_*, utility_set = 0 | **PASS**: all 0 in both deliveries (collisions 4,736 / 4,937 and multi_preingest 10 persist, as they should) |
| B7 repair dry again | zero action counters | **FAIL**: delivery_folds 163,631, deleted 163,631; all other actions 0; skips unchanged. **Fixed by 2d5e626** (v3 steps 5 and 7 pass) |

B7 per county (delivery_folds, 47 counties non-zero), top: Summit 38,952, Lorain 17,100, Cuyahoga 14,779, Lucas 11,764,
Mahoning 10,636, Stark 8,862, Ashland 7,890, Fulton 7,171, Geauga 6,705, Wood 5,854, Lake 5,841. These are the same counties and
nearly the same counts as the FE part of A1's delivery_folds. Three sample `_id`s (Summit, FE jan2026, unlinked) are stored in
scratchpad `task3/v2/B7_sample_ids.txt`. They are 17-character strings that look like account numbers, so they are not copied here.
Full report: `task3/v2/B7_repair_dry.md`.

What the repair changed, by (utility, source_delivery, linkage), rehearsal before minus after:
AES jan2026 unlinked -231,839; FE jan2026 unlinked -163,792; AES aug2026 unlinked -3,571; AEP aug2026 unlinked -753;
FE jan2026 linked -393; pre-ingest docs (no utility) -4,795. Gains (utility newly set on a pre-ingest doc via a fold,
or promoted): AES +3,492, AEP +733, FE +570 on pre-ingest docs; AES aug2026 linked +888, AES jan2026 linked +235.

## Real backfill dry run on empower_development (A2, informational, pre-repair)
`--delivery jan2026 --delivery aug2026 --exclude AES:jan2026`. These numbers are cumulative within one dry run: the aug pass does not
see the jan pass's unwritten changes, so utility_set double counts across the two passes.
- jan2026: records 2,200,657; matched_parcels 203,753; docs_updated 576; docs_created_parcel 0; docs_created_unmatched 29;
  utility_set 191,502; skipped_multi_preingest 0; surrogate_collision 4,737; readings_added_existing 6,959; readings_added_new 406.
- aug2026: records 4,126,468; matched_parcels 653,731; docs_updated 3,963; docs_created_parcel 0; docs_created_unmatched 0;
  utility_set 603,760; skipped_multi_preingest 10; surrogate_collision 4,938; readings_added_existing 47,735.
- Report: scratchpad `task3/v2/backfill_dry_real.md`.

## Expected live backfill numbers (B4 dry run; B5 actuals)
| Counter | B4 jan2026 | B4 aug2026 | B5 execute jan2026 | B5 execute aug2026 |
|---|---|---|---|---|
| utility_set | 190,946 | 599,798 | 190,946 | 413,970 |
| docs_updated | 20 | 5 | 20 | 6 |
| docs_created_parcel | 0 | 0 | 0 | 0 |
| docs_created_unmatched | **163,661** | 9 | **163,661** | 0 |
| skipped_multi_preingest | 0 | 10 | 0 | 10 |
| surrogate_collision | 4,736 | 4,929 | 4,736 | 4,937 |
| readings_added_existing | 151 | 52 | 151 | 49 |
| readings_added_new | 1,920,653 | 97 | 1,920,653 | 0 |
| ambiguous_address | 2,217 | 13,302 | 2,217 | 13,302 |

- **The live utility_set is 604,916** (B5: 190,946 + 413,970). The B4 dry-run sum of 790,744 double counts, because the aug pass re-sets docs that the
  jan pass only planned to set.
- utility_set top counties (jan2026): Cuyahoga 163,879, Richland 8,090, Ottawa 7,856, Marion 7,797, Huron 3,302.
  (aug2026): Franklin 230,110, Cuyahoga 161,279, Montgomery 60,791, Allen 24,949, Muskingum 17,431, Lawrence 12,317,
  Belmont 11,537, Richland 11,391.
- docs_created_unmatched in jan2026 (163,661) are the FE jan surrogates the repair folded away: Summit 38,952, Lorain 17,100,
  Cuyahoga 14,779, Lucas 11,765, Mahoning 10,636, Stark 8,862, Ashland 7,890, Fulton 7,171, and others.
- surrogate_collision top: Cuyahoga 3,127/3,108, Lake 584/582, Ashtabula 257/261, Geauga 174/176, Lorain 99/113 (jan/aug).
- skipped_multi_preingest (aug2026): Franklin 8, Richland 1, Marion 1.
- docs_updated: jan2026 Warren 9, Union 4, Butler 2, Delaware 2, Cuyahoga 1, Clark 1, Clinton 1; aug2026 Montgomery 4, Cuyahoga 1.

## Post-rehearsal state (B8, after B5)
- Total docs: 3,903,275 (originally 4,138,839; after the repair 3,739,614; +163,661 from B5).
- Docs lacking `utility`: 196,287, down from 801,203. Non-stale (last reading in or after 2024-10): **23,648**, down from 628,563. Per county:
  Montgomery 17,451, Richland 2,938, Fayette 2,590, Marion 669; every other county is 0. Montgomery's remainder plausibly comes from AES
  meters reachable only via the excluded AES jan2026 file; this was not verified.
- AES jan2026 unlinked surrogate docs remaining (`parcel_id` null): Greene 15,456, Montgomery 28,218 (unchanged by B5,
  since AES jan2026 is excluded).
- `_id` check: only 29 `_id`s in the rehearsal are absent from `empower_development`. These are the 29 docs_created_unmatched that the real dry run (A2) also predicts.
  The other 163,632 created docs reuse the original FE jan `_id`s that the repair deleted. Shape classes are unchanged
  (non-hex strings 3,290,659, ObjectId 612,616; no new type).

## Run times and peak RSS
| Step | Wall | Peak RSS |
|---|---|---|
| R1 mongorestore (88 colls) | 29.7 s | 0.32 GiB |
| A1 repair dry, real | 41.8 s | 2.41 GiB |
| A2 backfill dry, real | 3:33.6 | 16.27 GiB |
| B1 repair dry | 41.2 s | 2.41 GiB |
| B2 repair execute | 48.9 s | 2.41 GiB |
| B3 repair dry | 30.7 s | 2.35 GiB |
| B4 backfill dry | 3:32.4 | 16.26 GiB |
| B5 backfill execute | 3:47.6 | 16.29 GiB |
| B6 backfill dry | 3:32.6 | 16.10 GiB |
| B7 repair dry | 34.9 s | 2.46 GiB |
| B8 state scan | 11.1 s | 0.26 GiB |

## Surprises versus expectations
1. **[FIXED by 2d5e626 `merged_ids` aliases; see Rehearsal v3]** **The repair and the jan2026 FE ingest are not idempotent together.** The fold keeps the aug `_id` and deletes the FE jan doc. A later
   ingest of jan2026 FE then finds no doc under the jan surrogate key and re-creates it (163,661 docs, 163,632 of them with their original `_id`).
   The next repair folds them again (B7). The readings are not lost (the fold appends), but every re-ingest re-creates the duplicates. Options
   for the user: run the live backfill with `--exclude FE:jan2026` as well (FE jan readings are already folded into the aug docs), or have the ingest
   look up the fold survivor. **No code was changed.** In the meantime, the live order must not be "repair then backfill with AES-only exclude".
2. delivery_folds is 392,008, not ~125k, because FE pairs are folded too. The user approved this (see Decisions). The fold appends: verified on 1,969
   Summit FE pairs (all jan+aug readings kept, 1,912 gained earlier months).
3. 43,674 AES jan2026 name-keyed surrogate docs survive (Greene 15,456, Montgomery 28,218). Their name-bearing `_id`s are not retired.
4. 11,719 skipped_conflict pairs (series disagree) stay as duplicates.
5. utility_set is 604,916 live, against an estimate of ~624k. docs_created_parcel is 0 as expected, but docs_created_unmatched is 163,661 (item 1).
   23,648 non-stale docs still lack utility (mostly Montgomery).

## Rehearsal v3 (after commit 2d5e626, merged_ids aliases)
Run 2026-10-13 on branch feature/need-analysis-p2, HEAD 2d5e626, against a **fresh** scratch DB `empower_p2_rehearsal2`
(the first rehearsal DB `empower_p2_rehearsal` was left untouched; both DBs are kept). Every tool run went through the
DB-pinning wrapper (`scratchpad/task3/v3/run_tool_on_db.py`). Reports and logs are in scratchpad `task3/v3/`.

**Safety.**
- S1: `[wrapper] get_empower_db().name = empower_p2_rehearsal2` was checked before every write and appears at the top of every run log.
- S2: `empower_development` was measured before and after each of the four `--execute` runs (steps 2, 4, 7a, 7b). Every time it was 88 collections, **4,138,839** docs,
  Montgomery 339,334, Greene 112,140, Summit 185,144, Huron 17,550. **It never changed.**
- S3: before each backfill run, 28–29 GiB were available, above the 20 GiB floor.

**Build.**
- R1: the backup was restored into `empower_p2_rehearsal2` (nsFrom/nsTo). Result: 88 collections, 4,138,839 docs, and 0 per-collection count mismatches against `empower_development`.
- R2: 25 `*CountyResidential` collections were copied in, 1,128,212 docs, with 0 mismatches.

| Step | Expectation | Result |
|---|---|---|
| 1 repair dry | = A1: 415 / 6,802 / 392,008 / 1,158 / deleted 399,225 | **PASS**: report body byte-identical to A1 (diff empty), so all skip counters match too |
| 2 repair `--execute` | counters = step 1 | **PASS**: same counters; 4,138,839 to 3,739,614 docs. 396,803 survivors carry `merged_ids`, 399,225 aliases (= deleted) |
| 3 backfill dry | (informational) | jan2026: utility_set 190,946, docs_updated 20, created_unmatched **29** (v2: 163,661), created_parcel 0; aug2026: utility_set 599,798 (double-counts jan), docs_updated 5, created 0 |
| 4 backfill `--execute` | (informational) | jan2026: utility_set 190,946, docs_updated 20, created_unmatched 29; aug2026: utility_set 413,970, docs_updated 5, created 0. Total 3,739,614 to 3,739,643 (+29) |
| 5 repair dry | all six action counters 0 | **PASS**: all six 0. Skips unchanged (10 / 11,719 / 11,337 / 4,199 / 0 / 58) |
| 6 backfill dry | docs_updated, docs_created_parcel, docs_created_unmatched, utility_set = 0 | **PASS**: all 0 in both deliveries, and readings_added_* 0 |
| 7a repair `--execute` again | zero actions, zero writes | **PASS**: all action counters 0; total 3,739,643 unchanged |
| 7b backfill `--execute` again | zero actions, zero writes | **PASS**: all write counters 0; `dbHash` of the 88 ElectricalDB collections identical before and after; per-collection counts identical; total 3,739,643 unchanged |

**Step 8, final state of `empower_p2_rehearsal2`.**
- Total docs: **3,739,643**. The original was 4,138,839, so the change is -399,196 (= -399,225 deleted, +29 created).
- Per-county delta vs the original: 65 counties changed, none grew. The largest drops: Montgomery -79,273, Greene -44,838, Summit -38,952, Miami -19,380,
  Lorain -17,100, Cuyahoga -15,025, Lucas -11,765, Logan -11,007, Mahoning -10,636, Darke -10,579, Clinton -10,170, Preble -10,149.
  Each equals the county's A1 `deleted`, plus that county's share of the 29 created docs.
- Non-stale docs (last reading 2024-10 or later) lacking `utility`: **23,648**. By county: Montgomery 17,451, Richland 2,938, Fayette 2,590, Marion 669; every other county is 0.
  All docs lacking `utility`: 196,287. No doc has `utility: null`.
- Docs carrying `merged_ids`: **396,803**, holding **399,225** aliases in total, which equals the deleted count. Steps 4–7 left these unchanged.
- AES jan2026 unlinked docs remaining: Greene **15,456**, Montgomery **28,218**. This is the same as v2; AES jan2026 is excluded from the backfill.
- surrogate_collision (steps 3 and 4 identical): jan2026 4,737 (Cuyahoga 3,127, Lake 584, Ashtabula 257, Geauga 174, Lorain 99),
  aug2026 4,938 (Cuyahoga 3,108, Lake 582, Ashtabula 261, Geauga 176, Lorain 113). This is +1 in each delivery vs v2 (4,736 / 4,937).
  skipped_multi_preingest: jan2026 0, aug2026 10 (Franklin 8, Richland 1, Marion 1).
- The 29 created docs (Warren 9, Union 7, Butler 4, Delaware 4, Clark 2, Madison 1, Montgomery 1, Preble 1) are the same 29 that A2 predicts.
  They are the only `_id`s absent from `empower_development`.
- Sanity check vs the first rehearsal DB after its repair (v2 B2, 3,739,614): per-county counts match exactly, except for the 8 counties above,
  each higher by its created docs (+29 in total). By contrast, the first rehearsal DB as it stands now (after its B5) differs in 47 collections. Those are the 163,661 re-created
  FE jan docs that v3 no longer creates.

**Run times and peak RSS (v3).**

| Step | Wall | Peak RSS |
|---|---|---|
| R1 mongorestore | 41.6 s | 0.33 GiB |
| 1 repair dry | 41.3 s | 2.42 GiB |
| 2 repair execute | 50.1 s | 2.42 GiB |
| 3 backfill dry | 3:33.4 | 16.27 GiB |
| 4 backfill execute | 3:47.0 | 16.27 GiB |
| 5 repair dry | 30.7 s | 2.39 GiB |
| 6 backfill dry | 3:35.1 | 16.27 GiB |
| 7a repair execute | 30.8 s | 2.39 GiB |
| 7b backfill execute | 3:35.5 | 16.09 GiB |
| 8 state scan | 10.7 s | 0.26 GiB |

**Notes.**
- The v2 post-state script under-counted "AES jan2026 unlinked" as 0 because `parcel_id` is present but null, not absent. The figures above
  come from a group-by on `parcel_id` type, and they agree with the v2 doc's 15,456 / 28,218.
- The +1 surrogate_collision per delivery vs v2 is consistent with the alias rule (an alias claimed by two docs is not used).
  It was not traced to a specific doc.

### Expected live numbers (from v3)
- Repair: parcel_folds 415, address_folds 6,802, delivery_folds 392,008, promoted 1,158, utility_from_fold 4,795,
  deleted 399,225 (ElectricalDB 4,138,839 to 3,739,614); `merged_ids` on 396,803 survivors, 399,225 aliases.
- Backfill (`--delivery jan2026 --delivery aug2026 --exclude AES:jan2026`), as written: utility_set **604,916**
  (jan 190,946 + aug 413,970), docs_updated 25 (20 + 5), docs_created_unmatched 29, docs_created_parcel 0; total afterwards 3,739,643.
- A second repair or backfill pass afterwards does nothing.
- Remaining unpriced non-stale docs (no `utility`): 23,648. By county: Montgomery 17,451, Richland 2,938, Fayette 2,590, Marion 669.

Artifacts: scratchpad `task3/v2/` (A1/A2 and B1–B7 reports and logs, s2_log.txt, bd_pre.json, bd_post_repair.json,
post_repair_state.json, post_backfill_state.json, B7_sample_ids.txt).

## Live run (2026-10-13)
Applied to `empower_development` on branch feature/need-analysis-p2, HEAD 2d5e626, after the user's go-ahead. The tools ran directly
(`python scripts/<tool>.py ...` from the repo root, venv active), with no wrapper. Each run was timed with `/usr/bin/time -v`. Reports and logs
are in scratchpad `task3/live/`.

**Preconditions.**
- P1: invoked the same way as the tools (repo root, `load_dotenv()`, `src.tools.mongo`): `get_empower_db().name = empower_development`.
- P2: before any write, `empower_development` had 88 ElectricalDB collections and 4,138,839 docs (Montgomery 339,334, Greene 112,140,
  Summit 185,144, Huron 17,550), matching the backup. The backup `backups/empower_development_20261013_pre_p2_repair.archive.gz` exists
  (768,275,255 bytes).
- P3: 28 GiB available before L3, 27 GiB before L4, 28 GiB before L5b (floor 20 GiB).

| Step | Expectation | Result |
|---|---|---|
| L1 repair dry | report body byte-identical to v3 step 1 | **PASS**: diff empty (only the timestamped title differs). 415 / 6,802 / 392,008 / promoted 1,158 / utility_from_fold 4,795 / deleted 399,225 |
| L2 repair `--execute` | total 3,739,614 | **PASS**: counters identical to v3 step 2. Total 4,138,839 to **3,739,614**. 396,803 survivors carry `merged_ids`, 399,225 aliases |
| L3 backfill dry | within 0.1% of v3 step 3 | **PASS**: every counter table identical. Only the parse `secs` timings differ |
| L4 backfill `--execute` | total 3,739,643 | **PASS**: counters identical to v3 step 4 (jan2026 utility_set 190,946, docs_updated 20, created_unmatched 29; aug2026 utility_set 413,970, docs_updated 5, created 0). Total 3,739,614 to **3,739,643** |
| L5a repair dry | zero action counters | **PASS**: all six action counters 0; skips 10 / 11,719 / 11,337 / 4,199 / 0 / 58. Body identical to v3 step 5 |
| L5b backfill dry | docs_updated, docs_created_*, utility_set = 0 | **PASS**: all 0 in both deliveries. Body identical to v3 step 6, apart from timings |
| L7 drop scratch DBs | only after L5/L6 match | done: `empower_p2_rehearsal` and `empower_p2_rehearsal2` dropped. Each name was asserted to differ from `empower_development` before its drop. `empower_development` is still 3,739,643 afterwards |

**Totals.** Before: 4,138,839 (Montgomery 339,334, Greene 112,140, Summit 185,144, Huron 17,550). After L2: 3,739,614.
After L4 and still after L7: **3,739,643** (Montgomery 260,061, Greene 67,302, Summit 146,192, Huron 17,035).

**L6 final checks** (all equal rehearsal v3 step 8).
- Docs carrying `merged_ids`: **396,803**, holding **399,225** aliases in total (= deleted).
- Non-stale docs (last reading 2024-10 or later) lacking `utility`: **23,648**. By county: Montgomery 17,451, Richland 2,938, Fayette 2,590, Marion 669.
  All docs lacking `utility`: 196,287. Docs with `utility: null`: 0.
- AES jan2026 docs by `parcel_id` type: Greene null 15,456; Montgomery null 28,218, string 22,600 (linked). No doc has `parcel_id` missing,
  so the unlinked remainder is Greene 15,456 and Montgomery 28,218, as in v3.
- `scripts/check_preingest_meter_duplication_tool.py` (the user's read-only tool, run unmodified, 25 counties with no-utility docs):
  196,287 no-utility (NU) docs, 18,685 of them merged in place by the ingest; 662,472 post-ingest linked, 687,036 post-ingest unlinked.
  Parcel overlap between NU and linked: 5,552. NU docs whose residential address matches a post-ingest unlinked doc: 42,219
  (5,617 via the surrogate-id address, 34,604 via the service-address field). Of 12,087 sampled pairs, only 212 share any reading date
  (210 of those with every shared reading equal, mostly Richland). The month gaps from NU last read to PU first read are mostly positive
  (modes 11, 1, 5, 10). The address-matched pairs therefore look like series continuations, not double-counted readings.
  The tool's `addr_overlap_ambiguous` column equals `addr_overlap_addronly` in every county; this looks like a quirk of the tool and was not investigated.

**§15.3.4 against the skip counters (added 2026-10-14, read-only, post-repair state).** The tool counts a parcel as overlapping when it holds a
no-utility doc and a doc with `utility`. After the backfill that includes pre-ingest docs that gained `utility`, so the overlap is not the
same as an ingest duplicate. Each overlapping parcel group, and each address-matched NU doc, was classified against a dry `repair_county` on
the current data (zero planned actions, as in L5a). The skip reason of each doc was read from the repair's own plan. Grouping used
`group_by_identity`, the address match the tool's own helpers, and staleness `is_fresh` at build month 2026-10 with the registry's 24 months.
Categories were tested in order, first match wins.

| Parcel overlap (5,552) | Parcels | NU doc(s) stale |
|---|---|---|
| (a) a doc in the group skipped as `skipped_conflict` | 0 | – |
| (b) ≥ 2 pre-ingest docs on the parcel (multi-meter) | **5,552** | 5,305 |
| (c) stale pre-ingest doc beside an ingest doc (§15.1) | 0 | – |
| (d) anything else | **0** | – |

None of the 5,552 groups holds an ingest-created doc (`source_delivery`). Each is a parcel with several pre-ingest meters, where the backfill
matched one meter and gave it `utility` and the others did not. These are the parcels the repair leaves alone by rule (`merge_target` is None),
not duplicates the ingest made. Measured as "parcel holding an NU doc and an ingest doc", the parcel overlap is 0, as §15.3.4 asks.

| Address overlap (42,219 NU docs) | NU docs | matched PU on same zip | NU doc stale |
|---|---|---|---|
| PU doc skipped `skipped_multi_candidate` | 40,061 | 33,148 | 37,392 |
| PU doc skipped `skipped_none` | 1,687 | 1,004 | 1,658 |
| PU doc skipped `skipped_conflict` | 445 | 434 | 414 |
| PU doc skipped `skipped_multi_preingest` | 26 | 18 | 25 |
| PU doc not skipped by the repair | **0** | – | – |

When an NU doc matches several PU docs, the reason shown is the first in the table's order. Every address match lands on a PU doc that the repair
skipped, so the address overlaps are "only the skipped cases" (§15.3.4). 39,489 of the 42,219 NU docs (93.5%) are stale. None of them was merged
in place by the ingest. Where one of these pairs is the same meter, the household is counted twice: once stale, on the parcel (usage unknown, no computed bill),
and once unlinked with fresh usage. The repair cannot settle which parcel the address belongs to, or whether the series agree, so these stay as they are.

**Run times and peak RSS (live).**

| Step | Wall | Peak RSS |
|---|---|---|
| L1 repair dry | 41.8 s | 2.42 GiB |
| L2 repair execute | 51.2 s | 2.42 GiB |
| L3 backfill dry | 3:34.2 | 16.27 GiB |
| L4 backfill execute | 3:46.3 | 16.27 GiB |
| L5a repair dry | 30.8 s | 2.39 GiB |
| L5b backfill dry | 3:32.0 | 16.27 GiB |
| L6 state scan | 4.6 s | 0.02 GiB |
| L6 duplication check | 32.2 s | 2.22 GiB |

**Deviations:** none.
