#!/usr/bin/env python3
"""UTM-direct campaign attribution for direct-mail conversions.

Applications submitted on the EmpowerSaves landing page carry a UTM that names
the direct-mail variant the applicant responded to, e.g.
`?utm_source=mail&utm_campaign=Control-Click`. These were deferred by
`attribute_click_conversions_tool.py` (behavioral attribution must not overwrite
a UTM). This tool maps the UTM to the real `dm_impact_*` letter campaign.

Verified mapping (March 2026 IMPACT direct-mail A/B drop):
    utm_campaign = "<copy>-<audience>"
      copy:     Test    -> new   (NEW copy)
                Control -> old   (OLD copy)
      audience: Click   -> clickers       (prior text-clickers)
                View    -> non_clickers   (prior non-clickers)
    => campaign_id = f"dm_impact_{audience}_{copy}"
e.g. Test-Click -> dm_impact_clickers_new ; Control-View -> dm_impact_non_clickers_old

Confidence is double-keyed:
  - 0.99 method `utm_direct_verified`: UTM maps to a campaign AND the matched
    participant is actually in that campaign's letter exposures (independent
    confirmation).
  - 0.90 method `utm_direct`: UTM maps to a campaign but no exposure cross-check
    (no participant_oid, or participant not found in that letter audience).

Skips:
  - applications already carrying any likely_campaigns (idempotent)
  - UTMs with no known campaign mapping (e.g. utm_source=Majority / "Letter") ->
    reported as needing a campaign record, not guessed.

Usage:
    source venv/bin/activate
    python scripts/attribute_utm_direct_tool.py            # dry-run (default)
    python scripts/attribute_utm_direct_tool.py --apply    # write
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from pymongo import UpdateOne

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.attribute_click_conversions_tool import get_db, has_real_utm

COPY_MAP = {"test": "new", "control": "old"}
AUD_MAP = {"click": "clickers", "view": "non_clickers"}


def map_utm_to_campaign(utm):
    """Return campaign_id slug for a mappable mail UTM, else None."""
    src = (utm.get("utm_source") or "").strip().lower()
    camp = (utm.get("utm_campaign") or "").strip()
    if src != "mail" or "-" not in camp:
        return None
    copy_part, _, aud_part = camp.partition("-")
    copy_seg = COPY_MAP.get(copy_part.strip().lower())
    aud_seg = AUD_MAP.get(aud_part.strip().lower())
    if not copy_seg or not aud_seg:
        return None
    return f"dm_impact_{aud_seg}_{copy_seg}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()
    dry = not args.apply
    db = get_db()

    # valid target campaign ids that actually exist
    valid = {c["campaign_id"] for c in db.campaigns.find(
        {"campaign_id": {"$regex": "^dm_impact_"}}, {"campaign_id": 1})}

    apps = list(db.applications.find({
        "$or": [
            {"attribution.likely_campaigns": {"$exists": False}},
            {"attribution.likely_campaigns": {"$size": 0}},
        ]
    }))
    utm_apps = [a for a in apps if has_real_utm(a)]
    print(f"{'DRY-RUN' if dry else 'APPLY'} | UTM-bearing unattributed applications: {len(utm_apps)}\n")

    ops = []
    by_method = Counter()
    by_campaign = Counter()
    unmapped = []
    rows = []
    for a in utm_apps:
        utm = (a.get("attribution") or {}).get("utm") or {}
        cid = map_utm_to_campaign(utm)
        if not cid or cid not in valid:
            unmapped.append((a.get("application_id"), utm.get("utm_source"), utm.get("utm_campaign")))
            continue
        oid = (a.get("participant_match") or {}).get("participant_oid")
        verified = bool(oid) and db.exposures.count_documents(
            {"participant_oid": oid, "campaign_id": cid}) > 0
        conf, method = (0.99, "utm_direct_verified") if verified else (0.90, "utm_direct")
        by_method[method] += 1
        by_campaign[cid] += 1
        rows.append((a.get("application_id"), utm.get("utm_campaign"), cid, conf, method))
        link = {"campaign_id": cid, "confidence": conf, "method": method}
        ops.append(UpdateOne({"_id": a["_id"]}, {"$push": {"attribution.likely_campaigns": link}}))

    print("=== mapping (utm_campaign -> dm campaign) ===")
    for aid, uc, cid, conf, method in sorted(rows, key=lambda r: str(r[2])):
        print(f"  app {str(aid):>4}  {str(uc):14} -> {cid:30} {conf}  {method}")

    print("\n=== by method ===")
    for m, n in by_method.most_common():
        print(f"  {m:22} {n}")
    print(f"  {'TOTAL':22} {sum(by_method.values())}")
    print("\n=== by campaign ===")
    for cid, n in by_campaign.most_common():
        print(f"  {cid:30} {n}")

    print(f"\n=== unmapped (need a campaign record) : {len(unmapped)} ===")
    for aid, s, c in unmapped:
        print(f"  app {aid}: utm_source={s} utm_campaign={c}")

    if dry:
        print(f"\nDRY-RUN: {len(ops)} writes prepared. Re-run with --apply.")
    else:
        if ops:
            r = db.applications.bulk_write(ops, ordered=False)
            print(f"\nAPPLIED: modified {r.modified_count} applications.")
        else:
            print("\nNothing to write.")


if __name__ == "__main__":
    main()
