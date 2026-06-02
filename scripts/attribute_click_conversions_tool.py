#!/usr/bin/env python3
"""Generalized behavioral campaign attribution for converted applications.

Many GravityForms applications on the EmpowerSaves landing page
(reduceenergyburdenohio.com) carry no UTM, so `attribution.likely_campaigns`
is empty even though the applicant demonstrably engaged a campaign right before
applying. This tool infers the driving campaign from the matched participant's
*click* behavior, aligned to the application's entry_date.

Attribution priority (first match wins), confidence calibrated by evidence:
  1. same-day CLICK     -> a campaign the participant clicked, sent the same day
                           the application was submitted. conf 0.95, method
                           `click_same_day_landing`.
  2. windowed CLICK     -> a campaign clicked within --lag-days before the app
                           (most recent wins). conf 0.85, method
                           `click_window_landing`.
  3. same-day RECEIPT   -> a campaign delivered the same day, no click recorded.
                           conf 0.70, method `receipt_same_day_landing`.
                           (disabled unless --include-receipt)

Safety / scope:
  - Only touches applications with an EMPTY likely_campaigns (idempotent).
  - SKIPS applications that already carry a real UTM source/campaign -- those
    belong to a separate `utm_direct` rule and must not be overwritten by a
    behavioral guess (e.g. Majority/Letter direct-mail conversions).
  - SKIPS applications with no matched participant_oid (no exposures to read).
  - The written campaign_id is the campaign *slug* (campaigns.campaign_id), e.g.
    `text_impact_winter_75`; application_id is a STRING in this collection.

Usage:
    source venv/bin/activate
    python scripts/attribute_click_conversions_tool.py                 # dry-run (default)
    python scripts/attribute_click_conversions_tool.py --lag-days 7     # tune window
    python scripts/attribute_click_conversions_tool.py --include-receipt
    python scripts/attribute_click_conversions_tool.py --apply          # write
"""
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pymongo import MongoClient, UpdateOne

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.envvars import EnvVars

SAME_DAY_CLICK = (0.95, "click_same_day_landing")
WINDOW_CLICK = (0.85, "click_window_landing")
SAME_DAY_RECV = (0.70, "receipt_same_day_landing")


def get_db():
    env = EnvVars()
    uri = env.get_env("MONGO_URI", "mongodb://localhost:27017")
    name = env.get_env("MONGODB_OCTOPUS") or "empower_development"
    return MongoClient(uri)[name]


def _clicked(e):
    te = e.get("text_engagement") or {}
    ee = e.get("email_engagement") or {}
    return bool(te.get("clicked") or ee.get("clicked"))


def classify(entry_date, exposures, lag_days, include_receipt):
    """Return (campaign_id, confidence, method, detail) or None."""
    if not entry_date:
        return None
    appday = entry_date.date()
    dated = [e for e in exposures if e.get("sent_at")]
    clicks = [e for e in dated if _clicked(e)]

    # 1. same-day click
    for e in clicks:
        if e["sent_at"].date() == appday:
            conf, method = SAME_DAY_CLICK
            return (e.get("campaign_id"), conf, method, "same-day click")

    # 2. windowed click (clicked campaign sent within [appday-lag, appday]); most recent
    window = [e for e in clicks if 0 <= (appday - e["sent_at"].date()).days <= lag_days]
    if window:
        e = max(window, key=lambda x: x["sent_at"])
        conf, method = WINDOW_CLICK
        days = (appday - e["sent_at"].date()).days
        return (e.get("campaign_id"), conf, method, f"click {days}d before app")

    # 3. same-day receipt (no click)
    if include_receipt:
        for e in dated:
            if e["sent_at"].date() == appday:
                conf, method = SAME_DAY_RECV
                return (e.get("campaign_id"), conf, method, "same-day receipt")

    return None


def has_real_utm(app):
    utm = (app.get("attribution") or {}).get("utm") or {}
    return bool(utm.get("utm_source") or utm.get("utm_campaign") or utm.get("utm_id"))


STATUS_SAME_DAY = "same-day"
STATUS_WINDOWED = "windowed"
STATUS_UTM = "utm-deferred"
STATUS_NOMATCH = "no-match"
STATUS_NOSIGNAL = "no-signal"
STATUS_DONE = "already-attributed"


def status_for(app, db, lag_days):
    """Classify a single application into one export status. Returns dict row fields."""
    oid = (app.get("participant_match") or {}).get("participant_oid")
    pname = ""
    if oid:
        p = db.participants.find_one({"_id": oid}, {"demographics.customer_name": 1, "participant_id": 1})
        if p:
            pname = (p.get("demographics") or {}).get("customer_name") or p.get("participant_id") or ""
    existing = (app.get("attribution") or {}).get("likely_campaigns") or []
    base = dict(
        application_id=app.get("application_id"),
        entry_date=str(app.get("entry_date"))[:10] if app.get("entry_date") else "",
        participant_oid=str(oid) if oid else "",
        participant_name=pname,
        source_url=((app.get("attribution") or {}).get("utm") or {}).get("source_url") or "",
        campaign_id="", confidence="", method="", detail="",
    )
    if existing:
        base.update(status=STATUS_DONE,
                    campaign_id=";".join(lc.get("campaign_id", "") for lc in existing),
                    method=";".join(lc.get("method", "") for lc in existing))
        return base
    if has_real_utm(app):
        base.update(status=STATUS_UTM,
                    detail=((app.get("attribution") or {}).get("utm") or {}).get("utm_source") or "utm")
        return base
    if not oid:
        base.update(status=STATUS_NOMATCH)
        return base
    exposures = list(db.exposures.find({"participant_oid": oid}))
    res = classify(app.get("entry_date"), exposures, lag_days, include_receipt=False)
    if not res:
        base.update(status=STATUS_NOSIGNAL)
        return base
    cid, conf, method, detail = res
    status = STATUS_SAME_DAY if method == "click_same_day_landing" else STATUS_WINDOWED
    base.update(status=status, campaign_id=cid, confidence=conf, method=method, detail=detail)
    return base


def write_csv(db, path, lag_days):
    import csv as _csv
    from collections import Counter as _Counter
    apps = list(db.applications.find({}))
    rows = [status_for(a, db, lag_days) for a in apps]
    rows.sort(key=lambda r: (r["status"], str(r["entry_date"])))
    cols = ["application_id", "entry_date", "status", "campaign_id", "confidence",
            "method", "detail", "participant_name", "participant_oid", "source_url"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} application rows -> {path}")
    print("Status counts:")
    for s, n in _Counter(r["status"] for r in rows).most_common():
        print(f"  {s:20} {n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--lag-days", type=int, default=7, help="max days between click and application (default 7)")
    ap.add_argument("--include-receipt", action="store_true", help="also attribute same-day receipts with no click")
    ap.add_argument("--limit", type=int, default=0, help="cap applications processed (0 = all)")
    ap.add_argument("--csv", metavar="PATH", help="write per-application status CSV (no DB writes) and exit")
    args = ap.parse_args()
    dry = not args.apply
    db = get_db()

    if args.csv:
        write_csv(db, args.csv, args.lag_days)
        return

    cur = db.applications.find({
        "$or": [
            {"attribution.likely_campaigns": {"$exists": False}},
            {"attribution.likely_campaigns": {"$size": 0}},
        ]
    })
    if args.limit:
        cur = cur.limit(args.limit)
    apps = list(cur)

    print(f"{'DRY-RUN' if dry else 'APPLY'} | lag={args.lag_days}d | receipt={'on' if args.include_receipt else 'off'}")
    print(f"applications with empty likely_campaigns: {len(apps)}\n")

    # cache campaign slug -> short label for the report
    camp_label = {}
    for cmp in db.campaigns.find({}, {"campaign_id": 1, "name": 1, "channel": 1}):
        camp_label[cmp["campaign_id"]] = (cmp.get("name") or cmp["campaign_id"])

    ops = []
    by_method = Counter()
    by_campaign = defaultdict(Counter)   # campaign_id -> method counts
    skipped_utm = skipped_nomatch = skipped_nosignal = 0
    examples = []

    for app in apps:
        if has_real_utm(app):
            skipped_utm += 1
            continue
        oid = (app.get("participant_match") or {}).get("participant_oid")
        if not oid:
            skipped_nomatch += 1
            continue
        exposures = list(db.exposures.find({"participant_oid": oid}))
        res = classify(app.get("entry_date"), exposures, args.lag_days, args.include_receipt)
        if not res:
            skipped_nosignal += 1
            continue
        cid, conf, method, detail = res
        by_method[method] += 1
        by_campaign[cid][method] += 1
        if len(examples) < 15:
            examples.append((app.get("application_id"), str(app.get("entry_date"))[:10], method, conf,
                             camp_label.get(cid, cid)[:38], detail))
        link = {"campaign_id": cid, "confidence": conf, "method": method}
        ops.append(UpdateOne({"_id": app["_id"]}, {"$push": {"attribution.likely_campaigns": link}}))

    # ---- report ----
    print("=== would attribute (by method) ===" if dry else "=== attributed (by method) ===")
    for m, n in by_method.most_common():
        print(f"  {m:28} {n}")
    print(f"  {'TOTAL':28} {sum(by_method.values())}")

    short = {"click_same_day_landing": "sameday", "click_window_landing": "window",
             "receipt_same_day_landing": "receipt"}
    print("\n=== by campaign ===")
    for cid, mc in sorted(by_campaign.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(mc.values())
        detail = ", ".join(f"{short.get(m, m)}:{n}" for m, n in mc.items())
        print(f"  {camp_label.get(cid, cid)[:42]:42} {total:4}  ({detail})  [{cid}]")

    print("\n=== skipped ===")
    print(f"  has real UTM (utm_direct's job):   {skipped_utm}")
    print(f"  no matched participant:            {skipped_nomatch}")
    print(f"  no click/receipt signal in window: {skipped_nosignal}")

    print("\n=== sample of attributions ===")
    print(f"  {'app':>6} {'entry':10} {'method':28} {'conf':4} {'campaign':38} detail")
    for aid, d, m, conf, cl, det in examples:
        print(f"  {str(aid):>6} {d:10} {m:28} {conf:<4} {cl:38} {det}")

    if dry:
        print(f"\nDRY-RUN: {len(ops)} writes prepared. Re-run with --apply to commit.")
    else:
        if ops:
            r = db.applications.bulk_write(ops, ordered=False)
            print(f"\nAPPLIED: modified {r.modified_count} applications.")
        else:
            print("\nNothing to write.")


if __name__ == "__main__":
    main()
