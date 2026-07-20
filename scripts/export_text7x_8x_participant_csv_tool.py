"""Export Text7X/8X (Text75-84) campaign participants to a single CSV.

One row per participant who was targeted by at least one of the selected
Text75-84 campaigns (default: all ten). Combines LOCATE-appended demographics
(Melissa Data), self-reported applicant data, and campaign engagement across
text (Text75-84), direct mail (DM IMPACT), and email (EGE WinterCrisis 2026).

This is a read-only export — it makes no database writes.

Design / review decisions (2026-06-02):
  - Cohort = participants with >=1 exposure in the *selected* Text campaigns.
    `--campaigns` filters which campaigns define the cohort (default all).
    All ten Text columns are always emitted (stable schema); the filter only
    changes *which participants* appear, not which columns.
  - Text cell code (kept from export_participant_master_csv_tool.py):
        received=1, clicked=2, opted_out=3, undeliverable=4, negative_response=5
        blank = participant was not targeted by that campaign.
    (SMS has no "open" event, so the literal 2=opened from the column note
     cannot occur; the richer 1-5 code is used instead.)
  - (locate) demographics are filled from the Melissa Data LOCATE CSV,
    phone-matched to the participant (~79% of this cohort). An applicant's
    self-reported value still overrides the appended value where present.
    "Number of Adults" stays blank — no source has an adult-count field.
  - "Intake likely campaign" prefers a same-day exposure (clicked over
    received) before falling back to the most recent prior send. Exposure
    sent_at is UTC while application entry_date is local Eastern, so a strict
    sent_at<=entry_date test drops same-day clicks; the same-day rule recovers
    them. See infer_intake_campaign().

Usage:
    source venv/bin/activate
    python scripts/export_text7x_8x_participant_csv_tool.py
    python scripts/export_text7x_8x_participant_csv_tool.py --campaigns 75,76,83
    python scripts/export_text7x_8x_participant_csv_tool.py --output /tmp/out.csv
    python scripts/export_text7x_8x_participant_csv_tool.py --locate-csv /path/to/melissa.csv
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project root is importable when run as `python scripts/...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.mongo import get_campaign_db

EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"

# Default LOCATE source. The Melissa Data append CSV lives in the original
# checkout; override with --locate-csv if it has moved.
DEFAULT_LOCATE_CSV = Path(
    "/home/yersinia/devel/oc-orig/octopus/data/demographic/"
    "20260121-frankline/all_not_in_demographic_db_FINAL.csv"
)

# Text75-84 campaigns: (exposure campaign_id slug, CSV column header). The
# trailing Text number is the short key accepted by --campaigns.
TEXT_CAMPAIGNS = [
    ("text_impact_winter_75",   "EmpowerSaves OH Text75 Winter Section1 - IMPACT 2026-01"),
    ("text_impact_winter_76",   "EmpowerSaves OH Text76 Winter Section2 - IMPACT 2026-01"),
    ("text_impact_wcp_77",      "EmpowerSaves OH Text77 WCP Section1 - IMPACT 2026-02"),
    ("text_impact_wcp_78",      "EmpowerSaves OH Text78 WCP Section2 - IMPACT 2026-02"),
    ("text_impact_cold_79",     "EmpowerSaves OH Text79 Cold Section1 - IMPACT 2026-03"),
    ("text_impact_cold_80",     "EmpowerSaves OH Text80 Cold Section2 - IMPACT 2026-03"),
    ("text_impact_endssoon_81", "EmpowerSaves OH Text81 EndsSoon Section1 - IMPACT 2026-04"),
    ("text_impact_endssoon_82", "EmpowerSaves OH Text82 EndsSoon Section2 - IMPACT 2026-04"),
    ("text_impact_lastday_83",  "EmpowerSaves OH Text83 LastDay Section1 - IMPACT 2026-04"),
    ("text_impact_lastday_84",  "EmpowerSaves OH Text84 LastDay Section2 - IMPACT 2026-04"),
]

# Trailing Text number -> slug, for parsing --campaigns tokens.
TEXT_NUM_TO_SLUG = {
    int(re.search(r"_(\d+)$", slug).group(1)): slug for slug, _h in TEXT_CAMPAIGNS
}

# Direct mail campaign slugs (DM IMPACT).
DM_CAMPAIGNS = [
    "dm_impact_clickers_new", "dm_impact_clickers_old",
    "dm_impact_non_clickers_new", "dm_impact_non_clickers_old",
]

# EGE_WinterCrisis_2026_ACEEE Campaign exposure campaign_id (only 2026 email
# campaign; covers ~89% of the Text7X/8X cohort).
EGE_CAMPAIGN_ID = "5187fe36-26ec-11f1-8683-5707f6b7d808"

# Text-column code mapping from exposure unified_status.
TEXT_STATUS_CODES = {
    "received": 1,
    "clicked": 2,
    "opted_out": 3,
    "undeliverable": 4,
    "negative_response": 5,
}

# Age at or above which a participant counts as a senior (fallback when the
# LOCATE senior flag is absent but an age is known).
SENIOR_AGE_THRESHOLD = 60

# Melissa MD_HouseholdIncome bracket -> numeric midpoint. Mirrors
# scripts/ingest_franklin_demographics_tool.py :: INCOME_MAPPING (midpoint only)
# so the appended income column stays numerically comparable with the DB's
# demographics.estimated_income.
INCOME_BRACKET_MIDPOINT = {
    "$0-$15,000": 10000,
    "$15,001-$20,000": 17500,
    "$20,001-$30,000": 25000,
    "$30,001-$40,000": 35000,
    "$40,001-$50,000": 45000,
    "$50,001-$60,000": 55000,
    "$60,001-$75,000": 62500,
    "$75,001-$100,000": 87500,
    "$100,001-$125,000": 112500,
    "$125,001-$150,000": 137500,
    "$150,001+": 175000,
}


# ── small helpers ───────────────────────────────────────────────────────────

def _blank(value):
    """Render None as an empty CSV cell; pass any other value through."""
    return "" if value is None else value


def _num(value):
    """Render a number cleanly: whole floats as ints, None as blank.

    Keeps the numeric columns consistent regardless of whether a value came
    from an int LOCATE midpoint or a float DB field (e.g. 25000 vs 7500.0).
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize_phone(value):
    """Return a 10-digit phone string, or None if the input isn't one."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def locate(applicant_value, appended_value):
    """Prefer an applicant-reported value, falling back to appended data.

    A value of 0 from the applicant is treated as present (only None
    triggers the fallback).
    """
    return applicant_value if applicant_value is not None else appended_value


def first_present(*values):
    """Return the first value that is not None, else None."""
    for value in values:
        if value is not None:
            return value
    return None


def text_status_code(unified_status):
    """Map an exposure unified_status to its 1-5 text-column code.

    Returns None for an unknown status or when the participant was not in
    the campaign (status is None).
    """
    return TEXT_STATUS_CODES.get(unified_status)


def senior_from_age(age):
    """Return 'Y' if age >= threshold, 'N' if below, None if age unknown."""
    if age is None:
        return None
    return "Y" if age >= SENIOR_AGE_THRESHOLD else "N"


def yn_from_yesno(value):
    """Map a 'Yes'/'No' (or 'Y'/'N') presence flag to 'Y'/'N', else None.

    Used for participants.demographics presence flags enriched from
    FranklinCountyDemographic, which store 'Yes'/'No'.
    """
    if value is None:
        return None
    token = str(value).strip().lower()
    if token in ("yes", "y"):
        return "Y"
    if token in ("no", "n"):
        return "N"
    return None


def direct_mail_code(campaign_slugs):
    """Return 2 if any DM '*_new' campaign was received, 1 if any '*_old',
    else 3. `campaign_slugs` is the set of DM slugs for one participant.
    """
    slugs = set(campaign_slugs)
    if any(s.startswith("dm_impact_") and s.endswith("_new") for s in slugs):
        return 2
    if any(s.startswith("dm_impact_") and s.endswith("_old") for s in slugs):
        return 1
    return 3


def email_engagement_flags(exposure):
    """Return (received, opened, clicked) as 1/0 for an EGE email exposure.

    `exposure` is the matched exposure dict, or None if the participant was
    not in the EGE campaign. An undeliverable exposure counts as not received.
    """
    if not exposure:
        return 0, 0, 0
    status = exposure.get("unified_status")
    engagement = exposure.get("email_engagement") or {}
    received = 0 if status == "undeliverable" else 1
    opened = 1 if (engagement.get("opened")
                   or status in ("opened", "clicked")) else 0
    clicked = 1 if (engagement.get("clicked") or status == "clicked") else 0
    return received, opened, clicked


def infer_intake_campaign(application, exposures, campaign_names):
    """Infer which campaign likely drove an application.

    1. UTM source/medium on the application, if present.
    2. Else a campaign engaged on the same calendar day as the intake,
       preferring a clicked exposure, then the latest by send time.
    3. Else the most recent exposure sent on or before the intake date.
    4. Else 'N/A'.

    The same-day step (2) exists because exposure `sent_at` is stored in UTC
    while application `entry_date` is local Eastern: a same-day click can sort
    hours *after* the intake under a strict `sent_at <= entry_date` test, which
    would otherwise drop the very campaign that drove the conversion (yielding
    'N/A', or a stale older campaign for participants with prior history).
    """
    utm = (application.get("attribution") or {}).get("utm") or {}
    source = utm.get("utm_source")
    medium = utm.get("utm_medium")
    if source or medium:
        return " / ".join(part for part in (source, medium) if part)

    entry_date = application.get("entry_date")
    if entry_date is None:
        return "N/A"

    def _campaign_name(exposure):
        slug = exposure.get("campaign_id")
        return campaign_names.get(slug, slug) or "N/A"

    # 2. Same calendar day as the intake: prefer a clicked exposure, else the
    #    latest that day. Tolerates the UTC/Eastern skew between the two times.
    same_day = [e for e in exposures
                if e.get("sent_at") is not None
                and e["sent_at"].date() == entry_date.date()]
    if same_day:
        clicked = [e for e in same_day if e.get("unified_status") == "clicked"]
        pool = clicked or same_day
        return _campaign_name(max(pool, key=lambda e: e["sent_at"]))

    # 3. Otherwise the most recent exposure on or before the intake date.
    prior = [e for e in exposures
             if e.get("sent_at") is not None and e["sent_at"] <= entry_date]
    if not prior:
        return "N/A"
    return _campaign_name(max(prior, key=lambda e: e["sent_at"]))


# ── LOCATE (Melissa Data) demographics ──────────────────────────────────────

def _melissa_age(dob_raw, today):
    """Compute age from a Melissa MD_DateOfBirth 'YYYYMM' string."""
    if not dob_raw:
        return None
    digits = re.sub(r"\D", "", str(dob_raw))
    if len(digits) < 4:
        return None
    birth_year = int(digits[:4])
    if birth_year < 1900 or birth_year > today.year:
        return None
    birth_month = int(digits[4:6]) if len(digits) >= 6 and digits[4:6] != "00" else 1
    age = today.year - birth_year - (1 if today.month < birth_month else 0)
    return age if 0 <= age <= 120 else None


def _melissa_yn(presence_value):
    """Map a Melissa presence string to 'Y' / 'N' / None."""
    if not presence_value:
        return None
    text = str(presence_value).strip().lower()
    if text.startswith("no "):
        return "N"
    if "present" in text:
        return "Y"
    return None


def load_locate_demographics(csv_path, today):
    """Load the Melissa LOCATE CSV into {normalized_phone: demographic dict}.

    Each demographic dict carries: age, children ('Y'/'N'), senior ('Y'/'N'),
    income_append (numeric midpoint), household_size (int). Returns ({}, 0)
    when the CSV is absent so the export can proceed with blank LOCATE columns.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"  WARNING: LOCATE CSV not found at {path} — "
              f"(locate) columns will be blank.")
        return {}, 0

    import pandas as pd

    cols = ["Phone", "MD_MOBILE", "MD_PhoneNumber", "MD_DateOfBirth",
            "MD_HouseholdIncome", "MD_PresenceOfChildren",
            "MD_PresenceOfSenior", "MD_HouseholdSize"]
    frame = pd.read_csv(path, dtype=str, usecols=lambda c: c in cols)
    # Missing cells read back as float NaN even with dtype=str; coerce to None.
    frame = frame.astype(object).where(pd.notna(frame), None)

    by_phone = {}
    for record in frame.to_dict("records"):
        size_raw = record.get("MD_HouseholdSize")
        try:
            household_size = int(float(size_raw)) if size_raw not in (None, "") \
                and not pd.isna(size_raw) else None
        except (TypeError, ValueError):
            household_size = None

        demo = {
            "age": _melissa_age(record.get("MD_DateOfBirth"), today),
            "children": _melissa_yn(record.get("MD_PresenceOfChildren")),
            "senior": _melissa_yn(record.get("MD_PresenceOfSenior")),
            "income_append": INCOME_BRACKET_MIDPOINT.get(
                (record.get("MD_HouseholdIncome") or "").strip()),
            "household_size": household_size,
        }
        # Index the row under every phone column it carries; first row wins.
        for col in ("Phone", "MD_MOBILE", "MD_PhoneNumber"):
            phone = normalize_phone(record.get(col))
            if phone and phone not in by_phone:
                by_phone[phone] = demo
    return by_phone, len(frame)


def participant_phone(participant):
    """Return the participant's normalized phone (from phone or id)."""
    return (normalize_phone(participant.get("phone"))
            or normalize_phone(participant.get("participant_id")))


# ── row assembly ────────────────────────────────────────────────────────────

def header_row():
    """Return the ordered list of 24 CSV column headers."""
    headers = [
        "Participant ID",
        "Primary Resident Age (locate)",
        "Number of Adults (locate)",
        "Children Present (Y/N)",
        "Senior Present (Y/N)",
        "Household size",
        "Household Income Append",
        "Household Income Reported",
    ]
    headers.extend(header for _slug, header in TEXT_CAMPAIGNS)
    headers.extend([
        "Direct Mail (1=old, 2=new, 3=none)",
        "Received email",
        "Opened email",
        "Clicked email",
        "Intake Form",
        "Intake likely campaign",
    ])
    return headers


def build_row(participant, application, text_status_by_slug, dm_slugs,
              ege_exposure, intake_campaign, locate_demo):
    """Assemble the ordered list of 24 CSV cell values for one participant.

    `locate_demo` is the participant's Melissa LOCATE dict, or None.
    """
    demographics = participant.get("demographics") or {}
    self_reported = (application or {}).get("self_reported") or {}
    locate_demo = locate_demo or {}

    # Age: applicant-reported > LOCATE append > participant demographics
    # (owner_age, enriched from FranklinCountyDemographic via parcel_id).
    age = locate(self_reported.get("age"),
                 first_present(locate_demo.get("age"),
                               demographics.get("owner_age")))

    # Children: applicant flag (if populated) overrides the LOCATE flag,
    # then participant demographics (presence_of_children).
    reported_children = self_reported.get("has_dependent_children")
    if reported_children is not None:
        children = "Y" if reported_children else "N"
    else:
        children = first_present(
            locate_demo.get("children"),
            yn_from_yesno(demographics.get("presence_of_children")))

    # Senior: LOCATE flag > demographics flag > derive from resolved age.
    senior = first_present(locate_demo.get("senior"),
                           yn_from_yesno(demographics.get("presence_of_senior")),
                           senior_from_age(age))

    household_size = locate(
        self_reported.get("household_members"),
        first_present(locate_demo.get("household_size"),
                      demographics.get("household_size")),
    )

    # Income (append) is the LOCATE/DB appended value, never self-reported —
    # self-reported income lives in its own "Reported" column.
    income_append = first_present(locate_demo.get("income_append"),
                                  demographics.get("estimated_income"))

    row = [
        str(participant["_id"]),
        _num(age),
        _num(demographics.get("number_of_adults")),  # enriched from FCD
        _blank(children),
        _blank(senior),
        _num(household_size),
        _num(income_append),
        _num(self_reported.get("household_income")),
    ]
    for slug, _header in TEXT_CAMPAIGNS:
        row.append(_blank(text_status_code(text_status_by_slug.get(slug))))
    row.append(direct_mail_code(dm_slugs))
    received, opened, clicked = email_engagement_flags(ege_exposure)
    row.extend([received, opened, clicked])
    if application is not None and application.get("entry_date") is not None:
        row.append(application["entry_date"].strftime("%Y-%m-%d"))
    else:
        row.append("")
    row.append(intake_campaign if application is not None else "")
    return row


# ── DB lookups ──────────────────────────────────────────────────────────────

def _entry_sort_key(application):
    """Sort key for picking the earliest application; None dates sort last."""
    entry_date = application.get("entry_date")
    return entry_date if entry_date is not None else datetime.max


def load_campaign_names(db):
    """Return a dict mapping campaign_id slug -> human-readable name."""
    return {
        c["campaign_id"]: c.get("name", c["campaign_id"])
        for c in db.campaigns.find({}, {"campaign_id": 1, "name": 1})
        if c.get("campaign_id")
    }


def load_text_status(db, slugs):
    """Return {participant_oid: {text_slug: unified_status}} for the cohort.

    The set of keys also defines the cohort (participants in `slugs`).
    """
    result = {}
    cursor = db.exposures.find(
        {"campaign_id": {"$in": slugs}},
        {"participant_oid": 1, "campaign_id": 1, "unified_status": 1},
    )
    for exposure in cursor:
        oid = exposure.get("participant_oid")
        if oid is None:
            continue
        result.setdefault(oid, {})[exposure["campaign_id"]] = \
            exposure.get("unified_status")
    return result


def load_dm_slugs(db, cohort_oids):
    """Return {participant_oid: set of DM campaign slugs received}."""
    result = {}
    cursor = db.exposures.find(
        {"campaign_id": {"$in": DM_CAMPAIGNS},
         "participant_oid": {"$in": cohort_oids}},
        {"participant_oid": 1, "campaign_id": 1},
    )
    for exposure in cursor:
        oid = exposure.get("participant_oid")
        if oid is None:
            continue
        result.setdefault(oid, set()).add(exposure["campaign_id"])
    return result


def load_ege_exposures(db, cohort_oids):
    """Return {participant_oid: EGE exposure dict} (first exposure wins)."""
    result = {}
    cursor = db.exposures.find(
        {"campaign_id": EGE_CAMPAIGN_ID,
         "participant_oid": {"$in": cohort_oids}},
        {"participant_oid": 1, "unified_status": 1, "email_engagement": 1},
    )
    for exposure in cursor:
        oid = exposure.get("participant_oid")
        if oid is not None and oid not in result:
            result[oid] = exposure
    return result


def load_applications(db, cohort_oids):
    """Return {participant_oid: earliest application dict} for cohort apps."""
    result = {}
    cursor = db.applications.find(
        {"participant_match.participant_oid": {"$in": cohort_oids}})
    for application in cursor:
        oid = application["participant_match"]["participant_oid"]
        existing = result.get(oid)
        if existing is None or \
                _entry_sort_key(application) < _entry_sort_key(existing):
            result[oid] = application
    return result


def load_intake_exposures(db, participant_oids):
    """Return {participant_oid: [exposure dicts]} for intake inference."""
    result = {}
    cursor = db.exposures.find(
        {"participant_oid": {"$in": list(participant_oids)}},
        {"participant_oid": 1, "campaign_id": 1, "sent_at": 1,
         "unified_status": 1},
    )
    for exposure in cursor:
        oid = exposure.get("participant_oid")
        if oid is None:
            continue
        result.setdefault(oid, []).append(exposure)
    return result


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_campaigns(raw):
    """Parse a --campaigns token list into ordered Text75-84 slugs.

    Accepts numbers ('75'), 'text75', or full slugs. Raises SystemExit on an
    unrecognised token. None/empty -> all ten campaigns.
    """
    if not raw:
        return [slug for slug, _h in TEXT_CAMPAIGNS]
    selected = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        match = re.search(r"(\d{2})$", token)
        if not match or int(match.group(1)) not in TEXT_NUM_TO_SLUG:
            valid = ", ".join(str(n) for n in sorted(TEXT_NUM_TO_SLUG))
            raise SystemExit(f"Unknown campaign '{token}'. Valid: {valid}")
        slug = TEXT_NUM_TO_SLUG[int(match.group(1))]
        if slug not in selected:
            selected.append(slug)
    # Preserve canonical Text75->84 order.
    return [slug for slug, _h in TEXT_CAMPAIGNS if slug in selected]


def main():
    """Build the Text7X/8X participant CSV."""
    parser = argparse.ArgumentParser(
        description="Export Text75-84 campaign participants to a master CSV.")
    default_out = (EXPORT_DIR /
                   f"text7x_8x_participant_export_{datetime.now():%Y%m%d_%H%M}.csv")
    parser.add_argument("--output", type=Path, default=default_out,
                        help=f"Output CSV path (default: {default_out})")
    parser.add_argument("--campaigns", default=None,
                        help="Comma list of Text campaigns defining the cohort, "
                             "e.g. '75,76,83' (default: all 75-84).")
    parser.add_argument("--locate-csv", type=Path, default=DEFAULT_LOCATE_CSV,
                        help="Melissa Data LOCATE CSV for appended demographics.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap rows written (for testing).")
    args = parser.parse_args()

    slugs = parse_campaigns(args.campaigns)
    today = datetime.now()

    db = get_campaign_db()

    print(f"Cohort campaigns: {', '.join(slugs)}")
    print("Loading lookups...")
    campaign_names = load_campaign_names(db)
    text_status = load_text_status(db, slugs)
    cohort_oids = list(text_status.keys())
    print(f"  cohort participants: {len(cohort_oids)}")

    dm_slugs = load_dm_slugs(db, cohort_oids)
    ege_exposures = load_ege_exposures(db, cohort_oids)
    applications = load_applications(db, cohort_oids)
    intake_exposures = load_intake_exposures(db, applications.keys())

    locate_demo, locate_rows = load_locate_demographics(args.locate_csv, today)
    print(f"  LOCATE rows loaded: {locate_rows} "
          f"({len(locate_demo)} phone keys)")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    counts = {"rows": 0, "applicants": 0, "income_append": 0,
              "income_reported": 0, "household_size": 0,
              "age": 0, "children": 0, "senior": 0, "locate_matched": 0}

    print(f"Writing {args.output}...")
    with args.output.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header_row())
        cursor = db.participants.find({"_id": {"$in": cohort_oids}})
        for participant in cursor:
            if args.limit is not None and counts["rows"] >= args.limit:
                break
            oid = participant["_id"]
            phone = participant_phone(participant)
            participant_locate = locate_demo.get(phone) if phone else None
            if participant_locate:
                counts["locate_matched"] += 1

            application = applications.get(oid)
            if application is not None:
                intake_campaign = infer_intake_campaign(
                    application, intake_exposures.get(oid, []),
                    campaign_names)
            else:
                intake_campaign = ""

            row = build_row(
                participant, application,
                text_status.get(oid, {}), dm_slugs.get(oid, set()),
                ege_exposures.get(oid), intake_campaign, participant_locate,
            )
            writer.writerow(row)

            counts["rows"] += 1
            if application is not None:
                counts["applicants"] += 1
            if row[1] != "":
                counts["age"] += 1
            if row[3] != "":
                counts["children"] += 1
            if row[4] != "":
                counts["senior"] += 1
            if row[5] != "":
                counts["household_size"] += 1
            if row[6] != "":
                counts["income_append"] += 1
            if row[7] != "":
                counts["income_reported"] += 1

    print(f"Done. Wrote {counts['rows']} rows to {args.output}")
    print(f"  applicant matches:     {counts['applicants']}")
    print(f"  LOCATE phone matches:  {counts['locate_matched']}")
    print(f"  age set:               {counts['age']}")
    print(f"  children set:          {counts['children']}")
    print(f"  senior set:            {counts['senior']}")
    print(f"  household size set:    {counts['household_size']}")
    print(f"  income (append) set:   {counts['income_append']}")
    print(f"  income (reported) set: {counts['income_reported']}")


if __name__ == "__main__":
    main()
