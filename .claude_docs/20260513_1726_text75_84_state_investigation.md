# Stage 1 — Text75–84 State Investigation


## Per-file summary table

| File | File contacts | DB candidates | Existing campaign_ids | Best-match exposures |
|---|---:|---:|---|---:|
| EmpowerSaves_OH_Text75_Winter_Section1.xlsx | 3710 | 1 | `761dc8cf-b8d6-43c4-b76e-d6d6cdc99d6e` | 3820 |
| EmpowerSaves_OH_Text76_Winter_Section2.xlsx | 3714 | 1 | `1fae2148-a61a-4cf7-ab16-6873db90838c` | 3821 |
| EmpowerSaves_OH_Text77_WCP_Section1.xlsx | 3173 | 0 | _(none)_ | 0 |
| EmpowerSaves_OH_Text78_WCP_Section2.xlsx | 3213 | 0 | _(none)_ | 0 |
| EmpowerSaves_OH_Text79_Cold_Section1.xlsx | 3062 | 1 | `text_impact_cold_79` | 3059 |
| EmpowerSaves_OH_Text80_Cold_Section2.xlsx | 3080 | 1 | `text_impact_cold_80` | 3077 |
| EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx | 2980 | 1 | `text_impact_endssoon_81` | 2977 |
| EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx | 2977 | 1 | `text_impact_endssoon_82` | 2974 |
| EmpowerSaves_OH_Text83_LastDay_Section1.xlsx | 2911 | 1 | `text_impact_lastday_83` | 2908 |
| EmpowerSaves_OH_Text84_LastDay_Section2.xlsx | 2911 | 1 | `text_impact_lastday_84` | 2906 |

**Generated:** 2026-05-13 17:26
**Source:** `/home/yersinia/devel/octopus/data/campaign-updated-20260512/`
**DB:** `empower_development`
**Mode:** read-only — no writes performed.

## EmpowerSaves_OH_Text75_Winter_Section1.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `75`  Action: `76`  Slug: `lmss`  Reply tag: `replied76`
- sent_time: `2026-01-23 21:12:46 GMT-0000`
- target=`3279` sent=`3710` delivered=`3186` dnd=`73` bad=`26` err=`524` replies=`12`
- Proposed campaign_id (if creating fresh): `text_impact_winter_75`

**File-side click tokens:**
- `click_lmss` (this campaign): 1053
- No cross-contamination detected.

**File-side contacts:** 3710 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`761dc8cf-b8d6-43c4-b76e-d6d6cdc99d6e`** — name=`EmpowerSaves OH Text75 Winter Section1 - IMPACT 2026-01` channel=`text` sent_at=`2026-01-01 00:00` source_file=`EmpowerSaves_OH_Text75_Winter_Section1_COLORCODED.xlsx` group=`None`
  - exposures: **3820** (received=2170, clicked=1009, undeliverable=524, opted_out=66, converted=44, negative_response=7)
  - sent_at range: `2026-01-01 00:00` .. `2026-01-01 00:00`
  - delta vs file sent count: `+110` (3820/3710 = 103.0%)
  - participant_oid populated: 3820/3820 (100%)
  - participants with `source_campaigns == [this campaign only]`: 0
  - phones in file but not in this campaign's exposures: 246
  - phones in this campaign's exposures but not in file: 16

## EmpowerSaves_OH_Text76_Winter_Section2.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `76`  Action: `77`  Slug: `lmss`  Reply tag: `replied77`
- sent_time: `2026-01-23 21:32:02 GMT-0000`
- target=`3294` sent=`3714` delivered=`3200` dnd=`93` bad=`30` err=`514` replies=`23`
- Proposed campaign_id (if creating fresh): `text_impact_winter_76`

**File-side click tokens:**
- `click_lmss` (this campaign): 1020
- No cross-contamination detected.

**File-side contacts:** 3714 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`1fae2148-a61a-4cf7-ab16-6873db90838c`** — name=`EmpowerSaves OH Text76 Winter Section2 - IMPACT 2026-01` channel=`text` sent_at=`2026-01-01 00:00` source_file=`EmpowerSaves_OH_Text76_Winter_Section2_COLOR CODED.xlsx` group=`None`
  - exposures: **3821** (received=2192, clicked=996, undeliverable=514, opted_out=88, converted=19, negative_response=12)
  - sent_at range: `2026-01-01 00:00` .. `2026-01-01 00:00`
  - delta vs file sent count: `+107` (3821/3714 = 102.9%)
  - participant_oid populated: 3821/3821 (100%)
  - participants with `source_campaigns == [this campaign only]`: 0
  - phones in file but not in this campaign's exposures: 263
  - phones in this campaign's exposures but not in file: 19

## EmpowerSaves_OH_Text77_WCP_Section1.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `77`  Action: `79`  Slug: `sMcs`  Reply tag: `replied79`
- sent_time: `2026-02-04 23:28:44 GMT-0000`
- target=`3154` sent=`3173` delivered=`3041` dnd=`42` bad=`0` err=`132` replies=`8`
- Proposed campaign_id (if creating fresh): `text_impact_wcp_77`

**File-side click tokens:**
- `click_sMcs` (this campaign): 1008
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_lmss`: 1012  → owned by text_impact_winter_75, text_impact_winter_76

**File-side contacts:** 3173 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 0
- _none — this campaign is not yet in `db.campaigns`_

## EmpowerSaves_OH_Text78_WCP_Section2.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `78`  Action: `78`  Slug: `lmLs`  Reply tag: `replied78`
- sent_time: `2026-02-04 23:18:00 GMT-0000`
- target=`3213` sent=`3213` delivered=`3063` dnd=`87` bad=`4` err=`150` replies=`7`
- Proposed campaign_id (if creating fresh): `text_impact_wcp_78`

**File-side click tokens:**
- `click_lmLs` (this campaign): 991
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_lmss`: 1004  → owned by text_impact_winter_75, text_impact_winter_76

**File-side contacts:** 3213 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 0
- _none — this campaign is not yet in `db.campaigns`_

## EmpowerSaves_OH_Text79_Cold_Section1.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `79`  Action: `80`  Slug: `qXJi`  Reply tag: `replied80`
- sent_time: `2026-02-27 21:37:18 GMT-0000`
- target=`3072` sent=`3062` delivered=`2935` dnd=`48` bad=`2` err=`127` replies=`8`
- Proposed campaign_id (if creating fresh): `text_impact_cold_79`

**File-side click tokens:**
- `click_qXJi` (this campaign): 956
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_lmss`: 998  → owned by text_impact_winter_75, text_impact_winter_76
  - `click_sMcs`: 974  → owned by text_impact_wcp_77

**File-side contacts:** 3062 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`text_impact_cold_79`** — name=`EmpowerSaves OH Text79 Cold Section1 - IMPACT 2026-03` channel=`text` sent_at=`2026-02-27 21:37` source_file=`EmpowerSaves_OH_Text79_Cold_Section1.xlsx` group=`IMPACT-Cold-202603`
  - exposures: **3059** (received=2883, undeliverable=127, opted_out=43, negative_response=6)
  - sent_at range: `2026-02-27 21:37` .. `2026-02-27 21:37`
  - delta vs file sent count: `-3` (3059/3062 = 99.9%)
  - participant_oid populated: 3059/3059 (100%)
  - ⚠ duplicate (participant_id, campaign_id) pairs: **1** (e.g. ['6145078892 (2x)'])
  - participants with `source_campaigns == [this campaign only]`: 0
  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): 5 (e.g. ['2067885176 (also email-keyed @ 1110tthompson@gmail.com)', '6144770299 (also email-keyed @ 11justin26@gmail.com)', '6146385429 (also email-keyed @ 1awest34@gmail.com)'])
  - phones in file but not in this campaign's exposures: 225
  - phones in this campaign's exposures but not in file: 1

## EmpowerSaves_OH_Text80_Cold_Section2.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `80`  Action: `81`  Slug: `mWaR`  Reply tag: `replied81`
- sent_time: `2026-02-27 21:37:07 GMT-0000`
- target=`3089` sent=`3080` delivered=`2947` dnd=`44` bad=`5` err=`133` replies=`13`
- Proposed campaign_id (if creating fresh): `text_impact_cold_80`

**File-side click tokens:**
- `click_mWaR` (this campaign): 1011
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_lmss`: 989  → owned by text_impact_winter_75, text_impact_winter_76
  - `click_lmLs`: 977  → owned by text_impact_wcp_78

**File-side contacts:** 3080 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`text_impact_cold_80`** — name=`EmpowerSaves OH Text80 Cold Section2 - IMPACT 2026-03` channel=`text` sent_at=`2026-02-27 21:37` source_file=`EmpowerSaves_OH_Text80_Cold_Section2.xlsx` group=`IMPACT-Cold-202603`
  - exposures: **3077** (received=2892, undeliverable=135, opted_out=41, negative_response=9)
  - sent_at range: `2026-02-27 21:37` .. `2026-02-27 21:37`
  - delta vs file sent count: `-3` (3077/3080 = 99.9%)
  - participant_oid populated: 3077/3077 (100%)
  - participants with `source_campaigns == [this campaign only]`: 0
  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): 5 (e.g. ['6146384181 (also email-keyed @ 1367rlsmith@gmail.com)', '6142948481 (also email-keyed @ 1701oakst@gmail.com)', '6148094418 (also email-keyed @ 1972rudeboy@gmail.com)'])
  - phones in file but not in this campaign's exposures: 232
  - phones in this campaign's exposures but not in file: 1

## EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `81`  Action: `82`  Slug: `iXJM`  Reply tag: `replied82`
- sent_time: `2026-03-27 20:17:48 GMT-0000`
- target=`2990` sent=`2980` delivered=`2858` dnd=`25` bad=`1` err=`122` replies=`2`
- Proposed campaign_id (if creating fresh): `text_impact_endssoon_81`

**File-side click tokens:**
- `click_iXJM` (this campaign): 955
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_lmss`: 984  → owned by text_impact_winter_75, text_impact_winter_76
  - `click_sMcs`: 959  → owned by text_impact_wcp_77
  - `click_pRJQ`: 945  → owned by text_impact_lastday_83, text_impact_lastday_84
  - `click_qXJi`: 944  → owned by text_impact_cold_79

**File-side contacts:** 2980 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`text_impact_endssoon_81`** — name=`EmpowerSaves OH Text81 EndsSoon Section1 - IMPACT 2026-04` channel=`text` sent_at=`2026-03-27 20:17` source_file=`EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx` group=`IMPACT-EndsSoon-LastDay-202604`
  - exposures: **2977** (received=2830, undeliverable=122, opted_out=24, negative_response=1)
  - sent_at range: `2026-03-27 20:17` .. `2026-03-27 20:17`
  - delta vs file sent count: `-3` (2977/2980 = 99.9%)
  - participant_oid populated: 2977/2977 (100%)
  - ⚠ duplicate (participant_id, campaign_id) pairs: **1** (e.g. ['6145078892 (2x)'])
  - participants with `source_campaigns == [this campaign only]`: 0
  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): 5 (e.g. ['2067885176 (also email-keyed @ 1110tthompson@gmail.com)', '6144770299 (also email-keyed @ 11justin26@gmail.com)', '6146385429 (also email-keyed @ 1awest34@gmail.com)'])
  - phones in file but not in this campaign's exposures: 221
  - phones in this campaign's exposures but not in file: 1

## EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `82`  Action: `83`  Slug: `Ytxw`  Reply tag: `replied83`
- sent_time: `2026-03-27 20:27:56 GMT-0000`
- target=`2987` sent=`2977` delivered=`2838` dnd=`28` bad=`5` err=`139` replies=`10`
- Proposed campaign_id (if creating fresh): `text_impact_endssoon_82`

**File-side click tokens:**
- `click_Ytxw` (this campaign): 961
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_mWaR`: 986  → owned by text_impact_cold_80
  - `click_lmss`: 981  → owned by text_impact_winter_75, text_impact_winter_76
  - `click_pRJQ`: 978  → owned by text_impact_lastday_83, text_impact_lastday_84
  - `click_lmLs`: 968  → owned by text_impact_wcp_78

**File-side contacts:** 2977 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`text_impact_endssoon_82`** — name=`EmpowerSaves OH Text82 EndsSoon Section2 - IMPACT 2026-04` channel=`text` sent_at=`2026-03-27 20:27` source_file=`EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx` group=`IMPACT-EndsSoon-LastDay-202604`
  - exposures: **2974** (received=2799, undeliverable=141, opted_out=27, negative_response=7)
  - sent_at range: `2026-03-27 20:27` .. `2026-03-27 20:27`
  - delta vs file sent count: `-3` (2974/2977 = 99.9%)
  - participant_oid populated: 2974/2974 (100%)
  - participants with `source_campaigns == [this campaign only]`: 0
  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): 5 (e.g. ['6146384181 (also email-keyed @ 1367rlsmith@gmail.com)', '6142948481 (also email-keyed @ 1701oakst@gmail.com)', '6148094418 (also email-keyed @ 1972rudeboy@gmail.com)'])
  - phones in file but not in this campaign's exposures: 227
  - phones in this campaign's exposures but not in file: 1

## EmpowerSaves_OH_Text83_LastDay_Section1.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `83`  Action: `84`  Slug: `pRJQ`  Reply tag: `replied84`
- sent_time: `2026-03-31 12:13:27 GMT-0000`
- target=`2921` sent=`2911` delivered=`2802` dnd=`27` bad=`0` err=`109` replies=`1`
- Proposed campaign_id (if creating fresh): `text_impact_lastday_83`

**File-side click tokens:**
- `click_pRJQ` (this campaign): 945
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_lmss`: 971  → owned by text_impact_winter_75, text_impact_winter_76
  - `click_sMcs`: 947  → owned by text_impact_wcp_77
  - `click_qXJi`: 937  → owned by text_impact_cold_79
  - `click_iXJM`: 935  → owned by text_impact_endssoon_81

**File-side contacts:** 2911 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`text_impact_lastday_83`** — name=`EmpowerSaves OH Text83 LastDay Section1 - IMPACT 2026-04` channel=`text` sent_at=`2026-03-31 12:13` source_file=`EmpowerSaves_OH_Text83_LastDay_Section1.xlsx` group=`IMPACT-EndsSoon-LastDay-202604`
  - exposures: **2908** (received=1639, clicked=1134, undeliverable=109, opted_out=25, negative_response=1)
  - sent_at range: `2026-03-31 12:13` .. `2026-03-31 12:13`
  - delta vs file sent count: `-3` (2908/2911 = 99.9%)
  - participant_oid populated: 2908/2908 (100%)
  - ⚠ duplicate (participant_id, campaign_id) pairs: **1** (e.g. ['6145078892 (2x)'])
  - legacy off-model `text_clicked: true` count: 1134
  - participants with `source_campaigns == [this campaign only]`: 0
  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): 5 (e.g. ['2067885176 (also email-keyed @ 1110tthompson@gmail.com)', '6144770299 (also email-keyed @ 11justin26@gmail.com)', '6146385429 (also email-keyed @ 1awest34@gmail.com)'])
  - phones in file but not in this campaign's exposures: 217
  - phones in this campaign's exposures but not in file: 1

## EmpowerSaves_OH_Text84_LastDay_Section2.xlsx

**Source-of-truth (Stats sheet):**
- Text #: `84`  Action: `85`  Slug: `pRJQ`  Reply tag: `replied85`
- sent_time: `2026-03-31 19:19:30 GMT-0000`
- target=`2921` sent=`2911` delivered=`2802` dnd=`34` bad=`2` err=`109` replies=`5`
- Proposed campaign_id (if creating fresh): `text_impact_lastday_84`

**File-side click tokens:**
- `click_pRJQ` (this campaign): 978
- Cross-contamination (other-campaign clicks present in this file's Tags):
  - `click_mWaR`: 982  → owned by text_impact_cold_80
  - `click_lmss`: 973  → owned by text_impact_winter_75, text_impact_winter_76
  - `click_lmLs`: 962  → owned by text_impact_wcp_78
  - `click_Ytxw`: 952  → owned by text_impact_endssoon_82

**File-side contacts:** 2911 unique phones from Conversations sheet

**Candidate campaign docs in DB:** 1

- **`text_impact_lastday_84`** — name=`EmpowerSaves OH Text84 LastDay Section2 - IMPACT 2026-04` channel=`text` sent_at=`2026-03-31 19:19` source_file=`EmpowerSaves_OH_Text84_LastDay_Section2.xlsx` group=`IMPACT-EndsSoon-LastDay-202604`
  - exposures: **2906** (received=2761, undeliverable=111, opted_out=31, negative_response=3)
  - sent_at range: `2026-03-31 19:19` .. `2026-03-31 19:19`
  - delta vs file sent count: `-5` (2906/2911 = 99.8%)
  - participant_oid populated: 2906/2906 (100%)
  - participants with `source_campaigns == [this campaign only]`: 0
  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): 5 (e.g. ['6146384181 (also email-keyed @ 1367rlsmith@gmail.com)', '6142948481 (also email-keyed @ 1701oakst@gmail.com)', '6148094418 (also email-keyed @ 1972rudeboy@gmail.com)'])
  - phones in file but not in this campaign's exposures: 225
  - phones in this campaign's exposures but not in file: 1


## Per-file decisions required

For each file, please respond with one of:
- **keep** — existing campaign + exposures look correct; only add clicks in Stage 4
- **augment** — keep campaign doc; update specific exposure fields (specify which)
- **wipe-and-reingest** — delete all exposures for this campaign_id, re-create from xlsx
- **create-fresh** — no existing doc; create new from xlsx

Also flag any duplicate-participant cleanups you want done in Stage 2.
