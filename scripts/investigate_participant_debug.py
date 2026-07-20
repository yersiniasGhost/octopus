"""One-off investigation: dump everything we know about a single participant.

Looks up the participant document, their text/email/DM exposures, any
application, and whether the Melissa LOCATE CSV has a phone-matching row —
reusing the export tool's own normalization/matching helpers so the answer
matches what the export would have produced.

Usage:
    source venv/bin/activate
    python scripts/investigate_participant_debug.py 69a61c0f9595ac4823aea84a
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId

from src.tools.mongo import get_campaign_db
from scripts.export_text7x_8x_participant_csv_tool import (
    DEFAULT_LOCATE_CSV, normalize_phone, participant_phone,
)


def dump(label, value):
    print(f"  {label}: {value!r}")


def main():
    raw_id = sys.argv[1] if len(sys.argv) > 1 else "69a61c0f9595ac4823aea84a"
    db = get_campaign_db()

    print("=" * 72)
    print(f"PARTICIPANT {raw_id}")
    print("=" * 72)

    participant = db.participants.find_one({"_id": ObjectId(raw_id)})
    if participant is None:
        print("  NOT FOUND in participants collection.")
        return

    print("\n[participant document]")
    for key in sorted(participant):
        dump(key, participant[key])

    phone = participant_phone(participant)
    print(f"\n[normalized phone used for LOCATE match]: {phone!r}")

    # Exposures for this participant (any campaign).
    print("\n[exposures]")
    exposures = list(db.exposures.find({"participant_oid": participant["_id"]}))
    if not exposures:
        print("  none")
    for exposure in sorted(exposures, key=lambda e: str(e.get("campaign_id"))):
        print(f"  - campaign_id={exposure.get('campaign_id')!r} "
              f"status={exposure.get('unified_status')!r} "
              f"sent_at={exposure.get('sent_at')}")

    # Application, if any.
    print("\n[application]")
    application = db.applications.find_one(
        {"participant_match.participant_oid": participant["_id"]})
    if application is None:
        print("  none")
    else:
        dump("entry_date", application.get("entry_date"))
        dump("self_reported", application.get("self_reported"))
        dump("attribution.utm", (application.get("attribution") or {}).get("utm"))

    # FranklinCountyDemographic (the ingested Melissa data) by phone.
    print("\n[FranklinCountyDemographic match by mobile]")
    if phone:
        franklin = db.FranklinCountyDemographic.find_one({"mobile": int(phone)})
        if franklin is None:
            print(f"  no row with mobile={phone}")
        else:
            for key in ("customer_name", "address", "mobile", "email",
                        "estimated_income", "md_householdsize",
                        "md_presence_of_children", "md_presence_of_senior"):
                dump(key, franklin.get(key))
    else:
        print("  no normalized phone to match on")

    # Raw Melissa LOCATE CSV match by phone.
    print("\n[Melissa LOCATE CSV match by phone]")
    if not phone:
        print("  no normalized phone to match on")
    elif not DEFAULT_LOCATE_CSV.exists():
        print(f"  CSV not found at {DEFAULT_LOCATE_CSV}")
    else:
        import pandas as pd
        frame = pd.read_csv(DEFAULT_LOCATE_CSV, dtype=str, low_memory=False)
        phone_cols = [c for c in ("Phone", "MD_MOBILE", "MD_PhoneNumber")
                      if c in frame.columns]
        hit = None
        for _idx, record in frame.iterrows():
            for col in phone_cols:
                if normalize_phone(record.get(col)) == phone:
                    hit = record
                    break
            if hit is not None:
                break
        if hit is None:
            print(f"  no CSV row across {phone_cols} matches phone {phone}")
        else:
            for col in ("Name", "First Name", "Last Name", "Address",
                        "Phone", "MD_MOBILE", "MD_PhoneNumber",
                        "MD_DateOfBirth", "MD_HouseholdIncome",
                        "MD_HouseholdSize", "MD_PresenceOfChildren",
                        "MD_PresenceOfSenior"):
                if col in frame.columns:
                    dump(col, hit.get(col))


if __name__ == "__main__":
    main()
