"""Enrich participants.demographics from FranklinCountyDemographic.

Joins participants to the (now backfilled) FranklinCountyDemographic collection on
`linkage.parcel_id` (direct match, falling back to digits-only normalization) and
fills the null demographic slots that the Text7X/8X export needs.

Non-destructive: a sub-field is written ONLY when the participant value is null/
absent AND the Franklin doc carries a real value. Existing values are preserved.
Idempotent. Every modified participant is stamped with enrichment provenance.

Usage: python scripts/enrich_participants_franklin_demographics_tool.py [--apply]
       (omit --apply for a dry run)
"""
import sys
from datetime import datetime
from pymongo import MongoClient, UpdateOne

APPLY = "--apply" in sys.argv
SOURCE = "FranklinCountyDemographic (IMPACT backfill)"
SENTINELS = {None, "", "-1", "-1.0", "nan", "None"}

def filled(v):
    return v is not None and str(v).strip() not in SENTINELS

def digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())

db = MongoClient("mongodb://localhost:27017")["empower_development"]
participants = db["participants"]
fcd = db["FranklinCountyDemographic"]

# Build Franklin lookup: parcel_id (direct) + digits-only index for stragglers.
fcd_by_id, fcd_by_digits = {}, {}
for d in fcd.find({}):
    fcd_by_id[d["parcel_id"]] = d
    fcd_by_digits[digits(d["parcel_id"])] = d

# participant demographics field <- Franklin field
FIELD_MAP = [
    ("owner_age", "owner_age"),
    ("presence_of_children", "presence_of_children"),
    ("presence_of_senior", "presence_of_senior"),
    ("number_of_adults", "number_of_adults"),
    ("marital_status", "marital_status"),
    ("estimated_income", "estimated_income"),
    ("household_size", "md_householdsize"),
]

cohort = participants.find(
    {"linkage.county_key": {"$in": ["Franklin", "FranklinCounty"]}},
    {"demographics": 1, "linkage": 1},
)

now = datetime.utcnow()
ops = []
set_counts = {pf: 0 for pf, _ in FIELD_MAP}
rows_touched = 0
no_match = 0

for part in cohort:
    pid = (part.get("linkage") or {}).get("parcel_id")
    src = fcd_by_id.get(pid) or fcd_by_digits.get(digits(pid))
    if src is None:
        no_match += 1
        continue
    demo = part.get("demographics") or {}
    updates = {}
    for pfield, sfield in FIELD_MAP:
        if not filled(demo.get(pfield)) and filled(src.get(sfield)):
            val = src[sfield]
            # normalize numeric strings stored in the Franklin docs
            if pfield in ("owner_age", "number_of_adults"):
                val = int(float(str(val)))
            elif pfield in ("estimated_income", "household_size"):
                val = float(str(val))
            updates[f"demographics.{pfield}"] = val
            set_counts[pfield] += 1
    if updates:
        rows_touched += 1
        updates["demographics_enriched_at"] = now
        updates["demographics_enriched_from"] = SOURCE
        updates["demographics_enriched_fields"] = sorted(
            k.split(".", 1)[1] for k in updates if k.startswith("demographics."))
        ops.append(UpdateOne({"_id": part["_id"]}, {"$set": updates}))

print(f"Franklin participants scanned (parcel matched): {rows_touched + no_match - no_match}")
print(f"Participants to update: {rows_touched} | no parcel match: {no_match}")
print("Field-level fills (only where participant slot was null):")
for f, c in set_counts.items():
    print(f"  demographics.{f:22s} +{c}")

if APPLY and ops:
    res = participants.bulk_write(ops, ordered=False)
    print(f"\nAPPLIED. modified={res.modified_count}")
elif ops:
    print("\nDRY RUN — re-run with --apply to write these changes.")
else:
    print("\nNothing to enrich (already complete).")
