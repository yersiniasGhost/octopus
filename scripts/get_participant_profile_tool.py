"""Reusable tool: gather a full participant profile by _id, phone, or name.

Resolves the given identifier (in order: 24-hex Mongo ObjectId, normalized
phone number, then case-insensitive substring match on
demographics.customer_name) and prints everything known about the matching
participant(s): the participant document, campaign exposures, applications
(both the `applications` and legacy `applicants` pipelines), county-specific
demographic/residential/electrical/thermal enrichment (including energy
burden figures), and a Melissa LOCATE CSV phone match.

Generalizes scripts/investigate_participant_debug.py (Franklin-only, ID-only)
to all ~30 ingested counties and to phone/name lookups. See
.claude/skills/participant-profile/SKILL.md for the county-collection-naming
quirks and field-meaning notes that motivated this tool.

Usage:
    source venv/bin/activate
    python scripts/get_participant_profile_tool.py 69a61c0f9595ac4823aeb4b4
    python scripts/get_participant_profile_tool.py 6142640950
    python scripts/get_participant_profile_tool.py "Tuan Nguyen"
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId

from src.tools.mongo import get_campaign_db
from scripts.export_text7x_8x_participant_csv_tool import (
    DEFAULT_LOCATE_CSV, normalize_phone, participant_phone,
)

OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")
MAX_NAME_MATCHES_TO_PROFILE = 5


def county_collection_names(county_key):
    """Map a participant's address.county (e.g. 'FranklinCounty') to its
    county-specific collection names.

    Naming is inconsistent across the ~30 county collections in
    empower_development: Demographic/Residential collections keep the
    'County' suffix (FranklinCountyDemographic) but ElectricalDB/ThermalLoads/
    GasDB/MultiTenant drop it (FranklinElectricalDB, not FranklinCountyElectricalDB).
    """
    if not county_key:
        return {}
    base = county_key[:-len("County")] if county_key.endswith("County") else county_key
    return {
        "demographic": f"{base}CountyDemographic",
        "residential": f"{base}CountyResidential",
        "electrical": f"{base}ElectricalDB",
        "thermal": f"{base}ThermalLoads",
        "gas": f"{base}GasDB",
        "multi_tenant": f"{base}MultiTenant",
    }


def resolve_participants(db, identifier):
    """Resolve an identifier to a list of participant documents."""
    identifier = identifier.strip()

    if OBJECT_ID_RE.match(identifier):
        doc = db.participants.find_one({"_id": ObjectId(identifier)})
        return [doc] if doc else []

    phone = normalize_phone(identifier)
    if phone:
        return list(db.participants.find(
            {"$or": [{"phone": phone}, {"participant_id": phone}]}))

    pattern = re.compile(re.escape(identifier), re.IGNORECASE)
    return list(db.participants.find({"demographics.customer_name": pattern}))


def dump(label, value, indent="  "):
    print(f"{indent}{label}: {value!r}")


def print_section(title):
    print(f"\n[{title}]")


def gather_county_enrichment(db, county_names, parcel_id, phone):
    """Pull demographic/residential/electrical/thermal/gas/multi-tenant docs
    for a parcel from the appropriate county-specific collections."""
    result = {"demographic": None, "residential": None, "electrical": None,
              "thermal": None, "gas": None, "multi_tenant": None}
    if not county_names:
        return result

    query = {"parcel_id": parcel_id} if parcel_id else None

    if query:
        result["demographic"] = db[county_names["demographic"]].find_one(query)
    if result["demographic"] is None and phone:
        try:
            result["demographic"] = db[county_names["demographic"]].find_one(
                {"mobile": int(phone)})
        except (TypeError, ValueError):
            pass

    if query:
        result["residential"] = db[county_names["residential"]].find_one(query)
        result["electrical"] = db[county_names["electrical"]].find_one(query)
        result["thermal"] = db[county_names["thermal"]].find_one(query)
        result["gas"] = db[county_names["gas"]].find_one(query)
        result["multi_tenant"] = db[county_names["multi_tenant"]].find_one(query)

    return result


def melissa_locate_match(phone, locate_csv=DEFAULT_LOCATE_CSV):
    if not phone or not locate_csv.exists():
        return None
    import pandas as pd
    frame = pd.read_csv(locate_csv, dtype=str, low_memory=False)
    phone_cols = [c for c in ("Phone", "MD_MOBILE", "MD_PhoneNumber") if c in frame.columns]
    for _idx, record in frame.iterrows():
        for col in phone_cols:
            if normalize_phone(record.get(col)) == phone:
                return record
    return None


def print_profile(db, participant):
    pid = participant["_id"]
    name = (participant.get("demographics") or {}).get("customer_name", "name unknown")

    print("=" * 72)
    print(f"PARTICIPANT {pid}  ({name})")
    print("=" * 72)

    print_section("participant document")
    for key in sorted(participant):
        dump(key, participant[key])

    phone = participant_phone(participant)
    print(f"\n[normalized phone]: {phone!r}")

    print_section("exposures")
    exposures = list(db.exposures.find({"participant_oid": pid}))
    if not exposures:
        print("  none")
    for exposure in sorted(exposures, key=lambda e: str(e.get("campaign_id"))):
        print(f"  - campaign_id={exposure.get('campaign_id')!r} "
              f"status={exposure.get('unified_status')!r} "
              f"sent_at={exposure.get('sent_at')}")

    print_section("application (applications collection / ingest_applications.py)")
    application = db.applications.find_one({"participant_match.participant_oid": pid})
    if application is None:
        print("  none")
    else:
        dump("entry_date", application.get("entry_date"))
        dump("self_reported", application.get("self_reported"))
        dump("attribution.utm", (application.get("attribution") or {}).get("utm"))

    print_section("applicants (legacy applicants collection / populate_applicants_db_v3.py)")
    applicant = db.applicants.find_one({"phone": phone}) if phone else None
    if applicant is None:
        print("  none")
    else:
        for key in ("entry_id", "first_name", "last_name", "address", "match_info"):
            dump(key, applicant.get(key))

    county_key = (participant.get("address") or {}).get("county")
    county_names = county_collection_names(county_key)
    parcel_id = (participant.get("linkage") or {}).get("parcel_id")

    print_section(f"county enrichment ({county_key or 'unknown county'})")
    if not county_names:
        print("  participant has no address.county -- cannot resolve county collections")
    else:
        enrichment = gather_county_enrichment(db, county_names, parcel_id, phone)

        demographic = enrichment["demographic"]
        print(f"  -- {county_names['demographic']} --")
        if demographic is None:
            print("    no match")
        else:
            for key in ("customer_name", "address", "mobile", "email",
                        "estimated_income", "income_level", "md_householdsize",
                        "md_presence_of_children", "md_presence_of_senior",
                        "annual_kwh_cost", "annual_gas_cost",
                        "energy_burden_kwh", "energy_burden_gas",
                        "total_energy_burden"):
                if key in demographic:
                    dump(key, demographic[key], indent="    ")

        residential = enrichment["residential"]
        print(f"  -- {county_names['residential']} --")
        if residential is None:
            print("    no match")
        else:
            for key in ("age", "living_area_total", "story_height", "rcn",
                        "energy_percentile"):
                if key in residential:
                    dump(key, residential[key], indent="    ")

        electrical = enrichment["electrical"]
        print(f"  -- {county_names['electrical']} --")
        if electrical is None:
            print("    no match")
        else:
            dump("monthly_averages", electrical.get("monthly_averages"), indent="    ")

        thermal = enrichment["thermal"]
        print(f"  -- {county_names['thermal']} --")
        if thermal is None:
            print("    no match")
        else:
            for key in ("kwh_hl_slope", "kwh_hl_intercept", "kwh_hl_r2",
                        "kwh_cl_slope", "kwh_cl_intercept", "kwh_cl_r2"):
                if key in thermal:
                    dump(key, thermal[key], indent="    ")
            dump("kwh_hl_cl_loads (n readings)",
                 len(thermal.get("kwh_hl_cl_loads") or []), indent="    ")
            dump("gas_hl_cl_loads (n readings)",
                 len(thermal.get("gas_hl_cl_loads") or []), indent="    ")

        for label in ("gas", "multi_tenant"):
            doc = enrichment[label]
            print(f"  -- {county_names[label]} --")
            if doc is None:
                print("    no match")
            else:
                for key in sorted(doc):
                    if key not in ("_id", "parcel_id"):
                        dump(key, doc[key], indent="    ")

        print("\n  -- energy burden verdict --")
        burden = demographic.get("total_energy_burden") if demographic else None
        if burden is None:
            print("    no burden figure available")
        elif burden < 0:
            print(f"    sentinel value ({burden}) -- burden not computable "
                  "(missing cost/income data)")
        else:
            flag = "HIGH BURDEN (>6%)" if burden > 6 else "normal/low burden"
            print(f"    total_energy_burden = {burden:.2f}%  -> {flag}")

    print_section("Melissa LOCATE CSV match by phone")
    if not phone:
        print("  no normalized phone to match on")
    elif not DEFAULT_LOCATE_CSV.exists():
        print(f"  CSV not found at {DEFAULT_LOCATE_CSV}")
    else:
        hit = melissa_locate_match(phone)
        if hit is None:
            print(f"  no CSV row matches phone {phone}")
        else:
            for col in ("Name", "First Name", "Last Name", "Address",
                        "Phone", "MD_MOBILE", "MD_PhoneNumber",
                        "MD_DateOfBirth", "MD_HouseholdIncome",
                        "MD_HouseholdSize", "MD_PresenceOfChildren",
                        "MD_PresenceOfSenior"):
                if col in hit.index:
                    dump(col, hit.get(col))


def main():
    parser = argparse.ArgumentParser(
        description="Gather a full participant profile by _id, phone, or name.")
    parser.add_argument(
        "identifier",
        help="Participant _id (24-hex ObjectId), phone number, or name (substring match)")
    args = parser.parse_args()

    db = get_campaign_db()
    matches = resolve_participants(db, args.identifier)

    if not matches:
        print(f"No participant found matching {args.identifier!r}")
        return

    if len(matches) > MAX_NAME_MATCHES_TO_PROFILE:
        print(f"{len(matches)} participants match {args.identifier!r} -- narrow your "
              "search (re-run with a phone number, _id, or fuller name). Candidates:")
        max_listed = 30
        for p in matches[:max_listed]:
            demo = p.get("demographics") or {}
            print(f"  - {p['_id']}  {demo.get('customer_name', '?')}  "
                  f"phone={p.get('phone')}  "
                  f"county={(p.get('address') or {}).get('county')}")
        if len(matches) > max_listed:
            print(f"  ... and {len(matches) - max_listed} more (not shown)")
        return

    for participant in matches:
        print_profile(db, participant)
        print()


if __name__ == "__main__":
    main()
