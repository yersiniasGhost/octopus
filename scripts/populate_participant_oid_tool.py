"""Backfill a participant_oid (ObjectId reference to `participants._id`) onto
documents in any collection that holds a participant natural-key reference.

Operates side-by-side with the existing natural key — does NOT modify the
natural-key field. Idempotent: only touches documents missing the surrogate.

Defaults backfill `exposures.participant_oid` from `exposures.participant_id`.
For nested fields, use dotted paths.

Usage:
    source venv/bin/activate

    # Default: exposures.participant_id  ->  exposures.participant_oid
    python scripts/populate_participant_oid_tool.py --dry-run
    python scripts/populate_participant_oid_tool.py --apply

    # applications.participant_match.participant_id  ->  applications.participant_match.participant_oid
    python scripts/populate_participant_oid_tool.py \\
        --collection applications \\
        --natural-key-field participant_match.participant_id \\
        --surrogate-key-field participant_match.participant_oid \\
        --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from pymongo import MongoClient, UpdateMany
from dotenv import load_dotenv


def build_participant_oid_map(db) -> dict[str, "ObjectId"]:
    """Build {participant_id: ObjectId} from the participants collection."""
    out = {}
    for p in db.participants.find({}, {"_id": 1, "participant_id": 1}):
        pid = p.get("participant_id")
        if pid:
            out[pid] = p["_id"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Plan only, no writes (default).")
    group.add_argument("--apply", dest="dry_run", action="store_false",
                       help="Actually issue the bulk_write ops.")
    parser.add_argument("--collection", default="exposures",
                        help="Target collection (default: exposures).")
    parser.add_argument("--natural-key-field", default="participant_id",
                        help="Field that holds the natural-key string. Supports "
                             "dotted paths for nested fields (default: participant_id).")
    parser.add_argument("--surrogate-key-field", default="participant_oid",
                        help="Field to populate with the ObjectId reference. "
                             "Supports dotted paths (default: participant_oid).")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Number of UpdateMany ops per bulk_write call (default 500).")
    args = parser.parse_args()

    load_dotenv()
    uri = os.getenv("MONGODB_URI") or f"mongodb://{os.getenv('MONGODB_HOST','localhost')}:{os.getenv('MONGODB_PORT','27017')}"
    db_name = os.getenv("MONGODB_DATABASE", "empower_development")
    db = MongoClient(uri)[db_name]

    coll = db[args.collection]
    nk = args.natural_key_field    # e.g. "participant_id" or "participant_match.participant_id"
    sk = args.surrogate_key_field  # e.g. "participant_oid" or "participant_match.participant_oid"

    print(f"Target:    {uri} / {db_name}")
    print(f"Collection: {args.collection}")
    print(f"Mapping:    {nk!r}  ->  {sk!r}")
    print(f"Mode:       {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    # 1. Build the lookup map (always from `participants` — that's the source of truth).
    t0 = time.time()
    pid_to_oid = build_participant_oid_map(db)
    print(f"Loaded {len(pid_to_oid):>7,} participant_id -> _id mappings in {time.time()-t0:.2f}s.")

    # 2. Plan: count what would change.
    total = coll.estimated_document_count()
    already_set = coll.count_documents({sk: {"$exists": True}})
    needs_set_filter = {sk: {"$exists": False}, nk: {"$exists": True, "$nin": [None, ""]}}
    needs_set = coll.count_documents(needs_set_filter)

    # Distinct natural-key values that still need backfill
    distinct_pids_to_set = [v for v in coll.distinct(nk, needs_set_filter) if v not in (None, "")]
    matched = [p for p in distinct_pids_to_set if p in pid_to_oid]
    orphans = [p for p in distinct_pids_to_set if p not in pid_to_oid]

    print()
    print(f"Total documents in {args.collection}:              {total:>9,}")
    print(f"Already have {sk}:                                  {already_set:>9,}")
    print(f"Missing {sk} (and have a populated {nk}):           {needs_set:>9,}")
    print(f"Distinct natural-key values to backfill:            {len(distinct_pids_to_set):>9,}")
    print(f"  Matched to a participant:                         {len(matched):>9,}")
    print(f"  Orphan (no matching participant):                 {len(orphans):>9,}")
    if orphans:
        print(f"  Sample orphans: {orphans[:5]}")

    if not matched:
        print("\nNothing to do.")
        return 0

    # 3. Build the UpdateMany ops, batched.
    ops = [
        UpdateMany(
            {nk: pid, sk: {"$exists": False}},
            {"$set": {sk: pid_to_oid[pid]}},
        )
        for pid in matched
    ]
    print(f"\nPrepared {len(ops):,} UpdateMany ops (batch size {args.batch_size}).")

    if args.dry_run:
        print("\nDRY RUN - no writes performed. Pass --apply to execute.")
        return 0

    # 4. Execute in batches.
    total_matched = 0
    total_modified = 0
    t0 = time.time()
    for i in range(0, len(ops), args.batch_size):
        chunk = ops[i:i + args.batch_size]
        result = coll.bulk_write(chunk, ordered=False)
        total_matched += result.matched_count
        total_modified += result.modified_count
        print(f"  batch {i//args.batch_size + 1:>3}/{(len(ops)-1)//args.batch_size + 1:<3}  "
              f"+matched={result.matched_count:>6,}  +modified={result.modified_count:>6,}  "
              f"elapsed={time.time()-t0:>5.1f}s")

    print(f"\nDone. Total matched={total_matched:,} modified={total_modified:,} "
          f"in {time.time()-t0:.1f}s.")

    # 5. Post-verify counts.
    remaining = coll.count_documents({sk: {"$exists": False}, nk: {"$exists": True, "$nin": [None, ""]}})
    print(f"Documents still missing {sk} after run (excluding null natural keys): {remaining:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
