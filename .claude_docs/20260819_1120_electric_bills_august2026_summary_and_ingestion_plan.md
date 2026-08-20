# August 2026 Electric Utility Files — Summary & Ingestion Plan

**Date**: 2026-08-19
**Source files**: `data/electric-bills/*August*.zip` (received 2026-08-18)
**Target**: `empower_development` MongoDB — `{County}ElectricalDB` collections

---

## 1. What arrived (August 2026 delivery)

Five outer zips, four utilities, **7 data files, ~4.15M residential account rows, ~3.7 GB uncompressed**.

| Outer zip | Utility | Inner data file(s) | Rows | Format | Latest readings |
|---|---|---|---|---|---|
| `AEP August 2026x.zip` | AEP Ohio | `staging/CSP_CCI.TXT` (Columbus Southern) | 812,579 | fixed-width | ~2026-07 |
| | | `staging/OPCO_CCI.TXT` (Ohio Power) | 718,751 | fixed-width | ~2026-07 |
| `AES August 2026.zip` | AES Ohio (Dayton) | `Customerdata.txt` | 417,773 | comma-delimited, no header | 2026-07-16 |
| `Duke August 2026.zip` | Duke Energy Ohio | `Electric_Residential_20260719.csv` | 680,825 | CSV w/ header (BOM) | 2026-06/07 |
| `First Energy August 2026.zip` | FirstEnergy | `cmb_ce_elig_lst_07_2026.txt` (CEI/Cleveland) | 534,186 | `]`-delimited w/ header | 2026-06 |
| | | `cmb_oe_elig_lst_07_2026.txt` (Ohio Edison) | 764,006 | `]`-delimited | 2026-06 |
| | | `cmb_te_elig_lst_07_2026.txt` (Toledo Edison) | 219,350 | `]`-delimited | 2026-06 |

**⚠ Mislabeled archive**: `AEP August 2026.zip` (60.7 MB) is a byte-for-byte duplicate of the AES payload (`August 2026/AES/AES_CUSTDATA.zip` + spec PDF). The real AEP data is only in `AEP August 2026x.zip`. Do not ingest the mislabeled one — it would double-count AES.

### Row structure (common shape across all four formats)
Each row = one residential account: customer name, service address, mailing address, rate code / meter type / load profile, then **up to 12 monthly billing periods inline** (meter-read date, billed kWh, and for Duke/FE, billed kW demand; Duke also carries a Read-vs-Estimated flag).

**Format specs shipped alongside the data**:
- AEP: `staging/OHPreEnrollList Data Format.xlsx` (fixed-width column map — required for parsing)
- AES: `PRE_ENROLLMENT_LIST_Specs.pdf`
- Duke: `Elec Pre-enrollment list structure-new.208fc7f7.doc`
- FirstEnergy: header row embedded in each file

### Geographic coverage (sampled service cities)
- **AEP**: Columbus + central/southeastern Ohio (Franklin and surrounding counties)
- **AES**: Dayton metro — Dayton, Xenia, Huber Heights, Troy, Centerville (Montgomery/Greene/Miami counties)
- **Duke**: Cincinnati metro — Cincinnati, Middletown, Hamilton, Mason (Hamilton/Butler/Warren/Clermont)
- **FE-CEI**: Cleveland metro (Cuyahoga/Lake); **FE-OE**: Akron/Youngstown region; **FE-TE**: Toledo (Lucas)

### PII note
Files contain customer names + addresses. Keep zips out of git (already under `data/`, verify `.gitignore`), avoid copying extracts into tracked paths.

---

## 2. What's in MongoDB today

- **Schema**: `{County}ElectricalDB` per county (25 counties), documents shaped per `src/models/county_electrical_data.py`:
  `{ parcel_id, time_series_elec: {date_str: kWh}, monthly_averages, monthly_minimums, monthly_maximums }`
- **Volume**: ~1.35M electrical docs total — Franklin 242k, Cuyahoga 245k, Montgomery 118k, plus 22 smaller counties. (Cuyahoga also has `CuyahogaGasDB`, 167k docs — gas, out of scope here.)
- **Staleness (sampled max reading dates)**:
  - Franklin: 2024-09 · Allen: 2024-09 · Montgomery: 2024-08 · Cuyahoga: 2024-02 · Huron: 2024-02
- **Implication**: the **January 2026 delivery sitting in the same folder was never ingested** into `ElectricalDB` (no 2025 readings present). The August 2026 files cover roughly the trailing 12 months (mid-2025 → mid-2026), so ingesting January 2026 + August 2026 together closes most of the 2024→2026 gap; August alone still leaves a hole from late-2024 to mid-2025 for some accounts.
- **Key mismatch**: Mongo is keyed by `parcel_id`; utility files are keyed by account + service address. Address→parcel matching is required. Reusable normalization logic already exists in `scripts/enrich_residential_from_utility_tool.py` (`normalize_address`), matched against `{County}CountyResidential`.

---

## 3. Ingestion plan

### Phase 0 — Prep & constraints
- **Disk is 99% full (15 GB free)**: never fully extract; stream inner files with Python `zipfile` (nested: outer zip → inner zip → text stream).
- Parse the three format specs (AEP xlsx is mandatory for fixed-width offsets; Duke .doc and AES .pdf confirm column meanings).
- Skip `AEP August 2026.zip` (mislabeled AES duplicate).

### Phase 1 — Parsers (one module per utility format)
`src/tools/utility_bills/` package with `parse_aep.py`, `parse_aes.py`, `parse_duke.py`, `parse_firstenergy.py`, all yielding a common record:
```python
{utility, operating_co, account_id, customer_name, service_address, city, state, zip5,
 readings: [(read_date, kwh, kw_demand|None, estimated_flag|None)]}
```
- Zero-usage / placeholder periods (dates `00000000`, kWh 0 filler) dropped at parse time.
- Validate each parser against first ~1,000 rows + spec docs before full runs.

### Phase 2 — County routing + address→parcel matching
1. Map each record to county via service zip5 (zip→county lookup; `CountyKeys` collection may already serve this).
2. Extract `normalize_address` from `enrich_residential_from_utility_tool.py` into a shared util (DRY) and match `normalized(service_address) + zip5` against `{County}CountyResidential` to resolve `parcel_id`.
3. Emit match-rate report per utility × county; park unmatched rows in a sidecar file for review (expect apartments/units and PO-box-style service addresses to dominate misses).

### Phase 3 — Merge & upsert into `{County}ElectricalDB`
- For matched parcels: **union** new `(date, kwh)` pairs into `time_series_elec` (never overwrite history), then recompute `monthly_averages/minimums/maximums` from the merged series.
- Insert new documents for parcels present in Residential but absent from ElectricalDB.
- Bulk writes (`UpdateOne` batches), `--dry-run` and `--county` / `--limit` flags matching existing tool conventions.
- **Recommendation**: run the January 2026 files through the same pipeline first (older data first), then August 2026 — fills 2025 gap and exercises the pipeline twice.

### Phase 4 — Validation & downstream refresh
- Before/after per county: doc counts, % parcels with ≥1 reading in 2026, latest-reading-date histogram.
- Spot-check ~20 parcels per utility against raw rows.
- Refresh derivatives: `scripts/calculate_missing_thermal_loads_tool.py` (billing-aligned HDH/CDH) and energy percentiles (`calculate_energy_percentiles_tool.py`) consume ElectricalDB and will need reruns.

### Open decisions (need input)
1. **County scope**: only the 25 counties with existing collections, or create new `{County}ElectricalDB` collections for Duke's Hamilton/Butler/Warren/Clermont and FE-OE/TE territories (mostly absent today)?
2. **kW demand + estimated-read flags** (Duke/FE): store them (schema extension) or drop to keep the current model?
3. **Customer-name enrichment**: re-run parcel_owner enrichment from these fresher files while we're at it?

---

## 4. Decisions (2026-08-19) & implementation status

1. **Scope**: ingest ALL data — new `{County}ElectricalDB` collections are created for counties without Residential collections; unmatched addresses are stored with `parcel_id: null`, a deterministic surrogate `_id`, and the service address/zip so they can be parcel-matched later.
2. **kW demand**: NOT stored. Available in raw files if ever needed: kW peak demand (all four utilities), KVAR + on-peak splits (AES), read-vs-estimated flags (Duke).
3. **Dry run**: default mode of `scripts/ingest_electric_bills_tool.py`; produces per-county refresh summary (docs updated / created, readings added, match rate, new collections) before any write.

**Implemented**: `src/tools/utility_bills/` (parsers for all 4 formats validated against real data; AEP fixed-width offsets empirically confirmed), `src/tools/address_normalization.py` (extracted from enrich tool, now shared), `scripts/ingest_electric_bills_tool.py`.

**Corrupt archive**: `AEP-3_January 2026.zip` fails with BadZipFile (truncated) — January backfill covers AES/Duke/FirstEnergy only; AEP needs a re-send from the utility.

**Current DB size (measured 2026-08-19)**: `empower_development` = 2.49 GB uncompressed BSON, **0.87 GB on disk** (0.78 storage + 0.09 indexes), 3.46M docs. ElectricalDB subset: 806k docs, 0.65 GB data, 0.22 GB storage (avg 845 B/doc).

**Growth estimate (jan2026 + aug2026)**: ~0.5–0.6M existing docs gain ~12–24 readings (+~0.5 GB data); ~3.3–3.5M new docs (mostly unmatched/new-county accounts) at ~1.3–1.8 KB each (+~4.5–6 GB data). Expected end state ≈ **8–9.5 GB uncompressed data, ~3–3.5 GB on disk** (WiredTiger ~3× compression) — roughly a 4× database size increase. Exact counts come from the full dry-run report: `.claude_docs/20260819_1230_electric_bills_dryrun_report.md`.

## 5. Full dry-run results (2026-08-19, report: 20260819_1230_electric_bills_dryrun_report.md)

| | jan2026 (AES/Duke/FE) | aug2026 (all 4) |
|---|---|---|
| Records ingested (OH) | 2,761,196 | 4,126,468 |
| Matched to parcels | 309,948 | 649,200 |
| Existing docs updated | 274,930 | 599,798 |
| New docs (parcel-matched) | 35,006 | 46,577 |
| New docs (unmatched, surrogate id) | 1,886,953 | 2,758,489 |
| Readings → existing docs | 3.25M | 7.0M |
| Readings → new docs | 23.3M | 33.3M |
| New county collections | 49 | 63 |

Note: both deliveries were diffed against the *current* DB, so their counts overlap
(~half of jan's readings also appear in aug's trailing window). Sequential execute
(jan → aug) deduplicates naturally via the union-by-date merge.

**Revised growth estimate from measured counts** (avg ~12 readings/account, not the
24 assumed earlier): ~3.0–3.2M new docs, ~45–55M unique new readings →
dataSize 2.49 GB → **~6.5–7 GB uncompressed**; on disk 0.87 GB → **~2.3–2.7 GB**
(≈3× database size). Duke parser fix applied: periods 2–12 use Oracle alias
`TO_CHAR_Meter_Reading_Date{i}__mm_dd_yyyy__`, not `METERDATE{i}`.

## 6. EXECUTED 2026-08-19 (~13:00) — verified results

Jan then Aug ingested via `scripts/ingest_electric_bills_tool.py --execute`
(report: `20260819_1300_electric_bills_execute_report.md`). Pre-ingest backup:
`backups/empower_development_20260819_pre_electric_ingest.archive.gz` (323 MB).

- jan2026: 2.76M records → 274,930 docs updated, 1,921,959 created (+26.5M readings)
- aug2026: 4.13M records → 1,993,976 docs updated (incl. jan-created docs — sequential dedup), 1,410,882 created (+30.5M readings)
- DB after: 170 collections, 6.79M objects, 6.36 GB data / **2.75 GB on disk** (was 0.87 GB)
- ElectricalDB: **4,138,839 docs across 88 collections** (was 806k / 25)
- Freshness verified: Franklin 2026-07-31, Cuyahoga 2026-06-17, Hamilton 2026-07-16, Summit 2026-06-16
- Merge integrity spot-checked: parcel 010-000002-00 kept 2023-24 history, now 24 readings through 2026-07

**Remaining**: rerun thermal loads + energy percentiles tools; AEP Jan re-send (2024-10→2025-06 AEP gap).
