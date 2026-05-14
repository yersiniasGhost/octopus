"""Mark exposure records as clicked based on a CSV phone list.

For each phone number in <csv>, find the matching exposure document for the
given campaign_id and set:
    text_clicked      = True
    text_clicked_at   = <now>   (audit field; not in the Pydantic model but
                                  preserved on the document)
    unified_status    = "clicked"  (only when current status is "received";
                                    we never overwrite "undeliverable",
                                    "opted_out", or "engaged")

Designed for color-coded campaign spreadsheets where the yellow group denotes
recipients who clicked the SMS link. Idempotent — safe to re-run.

Usage:
    python scripts/mark_clicked_from_csv_tool.py \\
        --csv data/campaign-IMPACT-20260406/EmpowerSaves_LastDay_Text83_Section1_yellow.csv \\
        --campaign-id text_impact_lastday_83 \\
        --dry-run

Drop --dry-run to apply.
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

PHONE_COL_DEFAULT = "Cell"
CLICKED_STATUS = "clicked"
RECEIVED_STATUS = "received"


def normalize_phone(raw) -> str | None:
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def load_phones(csv_path: Path, phone_col: str) -> list[str]:
    phones = []
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        if phone_col not in reader.fieldnames:
            sys.exit(f"Column '{phone_col}' not found. Available: {reader.fieldnames}")
        for row in reader:
            p = normalize_phone(row.get(phone_col))
            if p:
                phones.append(p)
    return phones


def index_exposures_by_phone(db, campaign_id: str) -> dict[str, dict]:
    out = {}
    cursor = db.exposures.find(
        {"campaign_id": campaign_id},
        {
            "_id": 1,
            "participant_id": 1,
            "contact_snapshot.phone": 1,
            "text_clicked": 1,
            "text_delivered": 1,
            "unified_status": 1,
        },
    )
    for e in cursor:
        phone = normalize_phone(e.get("participant_id")) or normalize_phone(
            (e.get("contact_snapshot") or {}).get("phone")
        )
        if phone:
            out[phone] = e
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--campaign-id", required=True)
    p.add_argument("--phone-column", default=PHONE_COL_DEFAULT)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--allow-undeliverable",
        action="store_true",
        help="By default, skip phones whose exposure has unified_status=undeliverable.",
    )
    args = p.parse_args()

    load_dotenv()
    db = MongoClient(os.getenv("MONGODB_URI"))[os.getenv("MONGODB_CAMPAIGN", "empower_development")]

    phones = load_phones(args.csv, args.phone_column)
    print(f"CSV: {args.csv.name} → {len(phones)} normalized phone numbers")

    exposures = index_exposures_by_phone(db, args.campaign_id)
    print(f"Campaign '{args.campaign_id}': {len(exposures)} exposures indexed by phone")

    actions = Counter()
    ops: list[UpdateOne] = []
    skipped_undeliverable: list[str] = []
    not_found: list[str] = []
    already_clicked: list[str] = []

    now = datetime.now(timezone.utc)

    for phone in phones:
        e = exposures.get(phone)
        if not e:
            actions["no_exposure"] += 1
            not_found.append(phone)
            continue

        current_status = e.get("unified_status")
        if current_status == "undeliverable" and not args.allow_undeliverable:
            actions["skipped_undeliverable"] += 1
            skipped_undeliverable.append(phone)
            continue

        if e.get("text_clicked") is True and current_status == CLICKED_STATUS:
            actions["already_clicked"] += 1
            already_clicked.append(phone)
            continue

        set_doc = {
            "text_clicked": True,
            "text_clicked_at": now,
        }
        # Promote to "clicked" only if currently "received" (or empty); never
        # downgrade an "engaged"/"opted_out" record.
        if current_status in (None, "", RECEIVED_STATUS, "no_engagement"):
            set_doc["unified_status"] = CLICKED_STATUS
            actions["status_promoted_to_clicked"] += 1
        else:
            actions[f"status_left_{current_status}"] += 1

        actions["text_clicked_set_true"] += 1
        ops.append(UpdateOne({"_id": e["_id"]}, {"$set": set_doc}))

    print("\n=== Plan ===")
    for k, v in sorted(actions.items()):
        print(f"  {k}: {v}")
    if skipped_undeliverable:
        print(f"  (skipped undeliverable phones, e.g. {skipped_undeliverable[:3]}…)")
    if not_found:
        print(f"  (phones without exposure record: {len(not_found)}, e.g. {not_found[:3]}…)")

    if not ops:
        print("\nNothing to update.")
        return

    if args.dry_run:
        print(f"\nDRY RUN — would issue {len(ops)} updates against db.exposures")
        return

    result = db.exposures.bulk_write(ops, ordered=False)
    print(f"\nApplied: matched={result.matched_count} modified={result.modified_count}")


if __name__ == "__main__":
    main()
