"""Backfill missing demographic fields into FranklinCountyDemographic from the
IMPACT_franklin_2500 source file.

Non-destructive: a field is written ONLY when the DB value is missing/sentinel
AND the source file carries a real value. Existing good values are preserved.
Creates the new `presence_of_children` field (parallel to `presence_of_senior`).
Every modified document is stamped with backfill provenance for auditability.

Matched on parcel_id. Idempotent: re-running fills nothing new.

Usage: python scripts/backfill_franklin_impact_demographics_tool.py [--apply]
       (omit --apply for a dry run)
"""
import sys
from datetime import datetime
import pandas as pd
from pymongo import MongoClient, UpdateOne

CSV = "/home/yersinia/devel/oc-orig/octopus/data/demographic/20260121-frankline/IMPACT_franklin_2500_final.csv"
SOURCE_NAME = "IMPACT_franklin_2500_final.xlxs"
APPLY = "--apply" in sys.argv

SENTINELS = {"", "nan", "NaN", "-1", "-1.0", "None", None}

def filled(v):
    return str(v).strip() not in SENTINELS

def db_missing(doc, field):
    if field not in doc:
        return True
    return str(doc[field]).strip() in SENTINELS

def to_int(v):
    return int(float(str(v).strip()))

SENIOR_MAP = {"Senior Present": "Yes", "No Senior Present": "No"}
CHILD_MAP = {"Children Present": "Yes", "No Children Present": "No"}
CHILD_YN = {"Y": "Yes", "N": "No"}
MARITAL_MAP = {"S": "Single", "M": "Married"}  # A/B passed through unchanged

def marital(v):
    s = str(v).strip()
    return MARITAL_MAP.get(s, s)

def children_value(row):
    v = row.get("MD_PresenceOfChildren")
    if filled(v) and str(v).strip() in CHILD_MAP:
        return CHILD_MAP[str(v).strip()]
    v = row.get("Presence of Children")
    if filled(v) and str(v).strip() in CHILD_YN:
        return CHILD_YN[str(v).strip()]
    return None

df = pd.read_csv(CSV, dtype=str)
db = MongoClient("mongodb://localhost:27017")["empower_development"]["FranklinCountyDemographic"]
parcels = df["parcel_id"].tolist()
docs = {d["parcel_id"]: d for d in db.find({"parcel_id": {"$in": parcels}})}
now = datetime.utcnow()

# (db_field, source_col, transform)
EXISTING = [
    ("presence_of_senior", "MD_PresenceOfSenior", lambda v: SENIOR_MAP.get(str(v).strip())),
    ("owner_age", "Age in Two-Year Increments - 1st Individual", to_int),
    ("number_of_adults", "Number of Adults", to_int),
    ("marital_status", "Marital Status", marital),
    ("estimated_home_value", "MD_EstimatedHomeValue", to_int),
]

ops = []
set_counts = {f: 0 for f, _, _ in EXISTING}
set_counts["presence_of_children"] = 0
rows_touched = 0

for _, row in df.iterrows():
    pid = row["parcel_id"]
    doc = docs.get(pid)
    if doc is None:
        continue
    updates = {}
    for field, src, fn in EXISTING:
        if db_missing(doc, field) and filled(row.get(src)):
            val = fn(row[src])
            if val is not None and str(val).strip() not in SENTINELS:
                updates[field] = val
                set_counts[field] += 1
    if db_missing(doc, "presence_of_children"):
        cv = children_value(row)
        if cv is not None:
            updates["presence_of_children"] = cv
            set_counts["presence_of_children"] += 1
    if updates:
        rows_touched += 1
        updates["backfill_at"] = now
        updates["backfill_from"] = SOURCE_NAME
        updates["backfill_fields"] = sorted(k for k in updates if k not in
                                            ("backfill_at", "backfill_from"))
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": updates}))

print(f"Source rows: {len(df)} | matched DB docs: {len(docs)}")
print(f"Documents to update: {rows_touched}")
print("Field-level fills (only where DB was missing the value):")
for f, c in set_counts.items():
    print(f"  {f:22s} +{c}")

if APPLY and ops:
    res = db.bulk_write(ops, ordered=False)
    print(f"\nAPPLIED. modified={res.modified_count}")
elif ops:
    print("\nDRY RUN — re-run with --apply to write these changes.")
else:
    print("\nNothing to backfill (already complete).")
