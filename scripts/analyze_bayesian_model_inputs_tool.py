"""Live coverage analysis of Bayesian model inputs (companion to the catalog doc).

Answers the model-design questions from
.claude_docs/20260708_0940_bayesian_model_inputs_catalog.md with live numbers:
exposure outcome rates by channel, duplicate-exposure check, campaign weather
coverage and identification variance (within-month HDD spread), participant
covariate coverage, the joined effective-N funnel for the candidate
weather->engagement model, and Text75-84 vs. control conversion counts.

Usage:
    source venv/bin/activate
    python scripts/analyze_bayesian_model_inputs_tool.py
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.mongo import get_campaign_db

# Text75-84 cohort slugs (mirrors scripts/export_text7x_8x_participant_csv_tool.py)
TEXT7X8X_SLUGS = [
    "text_impact_winter_75", "text_impact_winter_76",
    "text_impact_wcp_77", "text_impact_wcp_78",
    "text_impact_cold_79", "text_impact_cold_80",
    "text_impact_endssoon_81", "text_impact_endssoon_82",
    "text_impact_lastday_83", "text_impact_lastday_84",
]

WEATHER_VARS = ["temp_mean_f", "hdd_base65", "cdd_base65", "freezing_hours", "hot_hours"]


def hr(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def pct(n, d):
    return f"{100.0 * n / d:5.1f}%" if d else "  n/a"


def nonnull_coverage(coll, paths, match=None):
    """Count non-null occurrences of each dotted path in one aggregation pass."""
    group = {"_id": None, "n": {"$sum": 1}}
    for p in paths:
        key = p.replace(".", "__")
        group[key] = {"$sum": {"$cond": [{"$ne": [{"$ifNull": [f"${p}", None]}, None]}, 1, 0]}}
    pipeline = ([{"$match": match}] if match else []) + [{"$group": group}]
    doc = next(iter(coll.aggregate(pipeline)), None)
    if not doc:
        return 0, {p: 0 for p in paths}
    return doc["n"], {p: doc[p.replace(".", "__")] for p in paths}


def summarize(values, label):
    v = np.asarray([x for x in values if x is not None], dtype=float)
    if len(v) == 0:
        print(f"  {label:<18} (no data)")
        return
    print(f"  {label:<18} n={len(v):<5} mean={v.mean():8.2f}  sd={v.std():8.2f}  "
          f"min={v.min():8.2f}  p50={np.median(v):8.2f}  max={v.max():8.2f}")


def flatten_weather(c):
    """Pull the five modeling weather vars out of a campaign doc (None if absent)."""
    w = c.get("weather") or {}
    return {
        "temp_mean_f": (w.get("temp_f") or {}).get("mean"),
        "hdd_base65": (w.get("degree_days") or {}).get("hdd_base65"),
        "cdd_base65": (w.get("degree_days") or {}).get("cdd_base65"),
        "freezing_hours": (w.get("extremes") or {}).get("freezing_hours"),
        "hot_hours": (w.get("extremes") or {}).get("hot_hours"),
        "share": w.get("county_recipient_share"),
        "status": w.get("status"),
    }


def analyze_campaigns(db):
    hr("CAMPAIGNS — treatment & weather grain")
    campaigns = list(db.campaigns.find({}, {
        "campaign_id": 1, "channel": 1, "agency": 1, "sent_at": 1,
        "message_types": 1, "weather": 1, "name": 1}))
    print(f"total campaigns: {len(campaigns)}")
    print(f"by channel: {dict(Counter(c.get('channel') for c in campaigns))}")
    print(f"by agency:  {dict(Counter(c.get('agency') for c in campaigns))}")
    print(f"weather.status: {dict(Counter(flatten_weather(c)['status'] for c in campaigns))}")

    ok = [c for c in campaigns if flatten_weather(c)["status"] == "ok"]
    ok_by_channel = Counter(c.get("channel") for c in ok)
    print(f"weather ok by channel: {dict(ok_by_channel)}")

    print("\nweather variable distributions (status=ok campaigns):")
    wx = {v: [flatten_weather(c)[v] for c in ok] for v in WEATHER_VARS}
    for v in WEATHER_VARS:
        summarize(wx[v], v)
    summarize([flatten_weather(c)["share"] for c in ok], "recipient_share")

    # Collinearity between candidate weather predictors
    rows = [[flatten_weather(c)[v] for v in WEATHER_VARS] for c in ok
            if all(flatten_weather(c)[v] is not None for v in WEATHER_VARS)]
    if len(rows) > 3:
        m = np.corrcoef(np.array(rows, dtype=float).T)
        print("\ncorrelation matrix (weather vars, ok campaigns):")
        print("  " + "".join(f"{v[:12]:>14}" for v in WEATHER_VARS))
        for i, v in enumerate(WEATHER_VARS):
            print(f"  {v[:12]:<12}" + "".join(f"{m[i, j]:14.2f}" for j in range(len(WEATHER_VARS))))

    # Identification currency: within-month HDD spread (weather effect is
    # estimated from variance left over after adjusting for season)
    by_month = defaultdict(list)
    for c in ok:
        if c.get("sent_at") and flatten_weather(c)["hdd_base65"] is not None:
            by_month[c["sent_at"].strftime("%Y-%m")].append(flatten_weather(c)["hdd_base65"])
    print("\nHDD by send month (n campaigns, mean, within-month sd):")
    for month in sorted(by_month):
        v = np.array(by_month[month])
        print(f"  {month}: n={len(v):<4} mean={v.mean():7.1f}  sd={v.std():6.1f}")

    print(f"\nmessage_types frequency (campaigns): "
          f"{dict(Counter(mt for c in campaigns for mt in (c.get('message_types') or [])))}")
    return {c["campaign_id"]: c for c in campaigns}


def analyze_exposures(db, campaign_map):
    hr("EXPOSURES — outcome grain")
    total = db.exposures.count_documents({})
    dupes = list(db.exposures.aggregate([
        {"$group": {"_id": {"p": "$participant_id", "c": "$campaign_id"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$group": {"_id": None, "pairs": {"$sum": 1}, "extra_rows": {"$sum": {"$subtract": ["$n", 1]}}}},
    ], allowDiskUse=True))
    d = dupes[0] if dupes else {"pairs": 0, "extra_rows": 0}
    print(f"total exposures: {total}   duplicate (participant,campaign) pairs: "
          f"{d['pairs']} (+{d['extra_rows']} extra rows)")

    per_channel = list(db.exposures.aggregate([
        {"$group": {
            "_id": "$channel", "n": {"$sum": 1},
            "opened": {"$sum": {"$cond": [{"$eq": ["$email_engagement.opened", True]}, 1, 0]}},
            "eclick": {"$sum": {"$cond": [{"$eq": ["$email_engagement.clicked", True]}, 1, 0]}},
            "tclick": {"$sum": {"$cond": [{"$eq": ["$text_engagement.clicked", True]}, 1, 0]}},
            "replied": {"$sum": {"$cond": [{"$eq": ["$text_engagement.replied", True]}, 1, 0]}},
            "optout": {"$sum": {"$cond": [{"$eq": ["$text_engagement.opted_out", True]}, 1, 0]}},
        }},
        {"$sort": {"n": -1}},
    ], allowDiskUse=True))
    print(f"\n{'channel':<16}{'n':>8}{'opened':>10}{'e-click':>10}{'t-click':>10}{'replied':>10}{'opt-out':>10}")
    for r in per_channel:
        print(f"{str(r['_id']):<16}{r['n']:>8}"
              f"{pct(r['opened'], r['n']):>10}{pct(r['eclick'], r['n']):>10}"
              f"{pct(r['tclick'], r['n']):>10}{pct(r['replied'], r['n']):>10}{pct(r['optout'], r['n']):>10}")

    status_counts = {r["_id"]: r["n"] for r in db.exposures.aggregate(
        [{"$group": {"_id": "$unified_status", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}])}
    print(f"\nunified_status counts: {status_counts}")

    matched = db.exposures.count_documents({"campaign_id": {"$in": list(campaign_map)}})
    print(f"exposures whose campaign_id exists in campaigns: {matched}/{total} ({pct(matched, total)})")


def analyze_participants(db):
    hr("PARTICIPANTS — covariate grain")
    demo_paths = [
        "demographics.income_level", "demographics.estimated_income",
        "demographics.total_energy_burden", "demographics.household_size",
        "demographics.annual_kwh_cost", "demographics.annual_gas_cost",
        "demographics.owner_age", "demographics.number_of_adults",
        "residence.living_area_sqft", "residence.year_built",
        "thermal.kwh_hl_slope", "thermal.kwh_cl_slope", "thermal.kwh_hl_r2",
        "linkage.county_key", "linkage.confidence", "energy_snapshot.annual_cost",
    ]
    n, cov = nonnull_coverage(db.participants, demo_paths)
    print(f"total participants: {n}\ncoverage (non-null):")
    for p in demo_paths:
        print(f"  {p:<38} {cov[p]:>6}  {pct(cov[p], n)}")

    counties = Counter(r["_id"] for r in db.participants.aggregate(
        [{"$group": {"_id": "$linkage.county_key"}}]))
    top = list(db.participants.aggregate([
        {"$group": {"_id": "$linkage.county_key", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]))
    print(f"\ndistinct county_key values: {len(counties)}")
    for r in top[:12]:
        print(f"  {str(r['_id']):<24} {r['n']:>6}")

    r2 = [d["thermal"]["kwh_hl_r2"] for d in db.participants.find(
        {"thermal.kwh_hl_r2": {"$ne": None}}, {"thermal.kwh_hl_r2": 1})]
    if r2:
        v = np.array(r2)
        print(f"\nkwh_hl_r2: n={len(v)}  p50={np.median(v):.2f}  share>=0.5: {pct((v >= 0.5).sum(), len(v))}")
    slopes = [d["thermal"]["kwh_hl_slope"] for d in db.participants.find(
        {"thermal.kwh_hl_slope": {"$ne": None}}, {"thermal.kwh_hl_slope": 1})]
    summarize(slopes, "kwh_hl_slope")


def weather_model_funnel(db, campaign_map):
    """Effective-N funnel for the weather->engagement candidate model."""
    hr("JOIN FUNNEL — weather -> engagement model (exposure grain)")
    parts = {}
    for p in db.participants.find({}, {
            "participant_id": 1, "linkage.county_key": 1, "thermal.kwh_hl_slope": 1,
            "demographics.estimated_income": 1, "demographics.income_level": 1,
            "demographics.total_energy_burden": 1, "demographics.household_size": 1}):
        demo = p.get("demographics") or {}
        parts[p.get("participant_id")] = (
            (p.get("linkage") or {}).get("county_key"),
            (p.get("thermal") or {}).get("kwh_hl_slope"),
            demo.get("estimated_income"), demo.get("income_level"),
            demo.get("total_energy_burden"), demo.get("household_size"),
        )

    stages = Counter()
    covs = Counter()  # independent covariate availability at the base stage
    base = {"campaigns": set(), "counties": set(), "outcomes": Counter()}
    dose = {"campaigns": set(), "counties": Counter(), "outcomes": Counter(),
            "months": Counter(), "hdd": [], "cdd": []}
    seen_pairs = set()
    cursor = db.exposures.find({}, {
        "participant_id": 1, "campaign_id": 1, "channel": 1,
        "text_engagement.clicked": 1, "text_engagement.replied": 1,
        "email_engagement.opened": 1, "email_engagement.clicked": 1})

    def tally(bucket, e, county):
        bucket["campaigns"].add(e.get("campaign_id"))
        te, ee = e.get("text_engagement") or {}, e.get("email_engagement") or {}
        ch = e.get("channel")
        bucket["outcomes"][f"{ch}:n"] += 1
        for flag, label in ((te.get("clicked"), "t_click"), (te.get("replied"), "replied"),
                            (ee.get("opened"), "opened"), (ee.get("clicked"), "e_click")):
            if flag:
                bucket["outcomes"][f"{ch}:{label}"] += 1

    for e in cursor:
        stages["0 all exposures"] += 1
        pair = (e.get("participant_id"), e.get("campaign_id"))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        stages["1 deduped"] += 1
        c = campaign_map.get(e.get("campaign_id"))
        if not c or flatten_weather(c)["status"] != "ok" or flatten_weather(c)["hdd_base65"] is None:
            continue
        stages["2 weather ok"] += 1
        pr = parts.get(e.get("participant_id"))
        if not pr or not pr[0]:
            continue
        stages["3 base: participant + county"] += 1
        county, slope, est_income, income_lvl, burden, hh_size = pr
        base["counties"].add(county)
        tally(base, e, county)
        # independent covariate availability among base rows
        for present, name in ((est_income is not None, "estimated_income"),
                              (income_lvl is not None, "income_level"),
                              (burden is not None, "total_energy_burden"),
                              (hh_size is not None, "household_size"),
                              (slope is not None, "kwh_hl_slope")):
            if present:
                covs[name] += 1
        if est_income is not None and burden is not None and slope is not None:
            covs["dose set: est_income+burden+slope"] += 1
            dose["counties"][county] += 1
            tally(dose, e, county)
            w = flatten_weather(c)
            dose["months"][c["sent_at"].strftime("%Y-%m") if c.get("sent_at") else "?"] += 1
            dose["hdd"].append(w["hdd_base65"])
            dose["cdd"].append(w["cdd_base65"] or 0.0)

    for k in sorted(stages):
        print(f"  {k:<38} {stages[k]:>8}")
    n_base = stages["3 base: participant + county"]
    print(f"\n  independent covariate availability among base rows (n={n_base}):")
    for k, v in covs.most_common():
        print(f"    {k:<40} {v:>8}  {pct(v, n_base)}")
    print(f"\n  BASE model rows: campaigns={len(base['campaigns'])}  counties={len(base['counties'])}")
    print(f"    outcomes: {dict(base['outcomes'])}")
    print(f"\n  DOSE subset (est_income+burden+slope): campaigns={len(dose['campaigns'])}")
    print(f"    counties: {dict(dose['counties'].most_common(8))}")
    print(f"    outcomes: {dict(dose['outcomes'])}")
    print(f"    rows by send month: {dict(sorted(dose['months'].items()))}")
    hdd, cdd = np.array(dose["hdd"]), np.array(dose["cdd"])
    if len(hdd):
        print(f"    campaign HDD across dose rows: sd={hdd.std():.1f}  rows hdd>50: {(hdd > 50).sum()}"
              f"  rows hdd>100: {(hdd > 100).sum()}")
        print(f"    campaign CDD across dose rows: sd={cdd.std():.1f}  rows cdd>30: {(cdd > 30).sum()}")


def analyze_conversions(db):
    hr("CONVERSIONS — applications & Text75-84 cohort")
    n_apps = db.applications.count_documents({})
    n_matched = db.applications.count_documents({"participant_match.participant_id": {"$ne": None}})
    methods = Counter()
    for a in db.applications.find({}, {"attribution.likely_campaigns": 1}):
        for lc in (a.get("attribution") or {}).get("likely_campaigns") or []:
            methods[lc.get("method")] += 1
    print(f"applications: {n_apps}   matched to participant: {n_matched} ({pct(n_matched, n_apps)})")
    print(f"attribution edges by method: {dict(methods)}")

    cohort = db.exposures.distinct("participant_id", {"campaign_id": {"$in": TEXT7X8X_SLUGS}})
    cohort = {p for p in cohort if p}
    app_pids = {a["participant_match"]["participant_id"] for a in db.applications.find(
        {"participant_match.participant_id": {"$ne": None}}, {"participant_match.participant_id": 1})}
    converted = cohort & app_pids
    print(f"\nText75-84 cohort (distinct exposed participants): {len(cohort)}")
    print(f"  with application: {len(converted)} ({pct(len(converted), len(cohort))})")

    all_text = db.exposures.distinct("participant_id", {"channel": {"$regex": "^text"}})
    never_texted = app_pids - set(all_text)
    print(f"  applications from participants never texted (any text campaign): {len(never_texted)}")


def main():
    db = get_campaign_db()
    campaign_map = analyze_campaigns(db)
    analyze_exposures(db, campaign_map)
    analyze_participants(db)
    weather_model_funnel(db, campaign_map)
    analyze_conversions(db)
    print("\nDone.")


if __name__ == "__main__":
    main()
