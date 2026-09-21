#!/usr/bin/env python3
"""Backfill an embedded ``weather`` sub-document onto each campaign.

For every campaign in ``empower_development.campaigns`` this tool:
  1. Resolves the *dominant* county from its recipients
     (exposures.campaign_id -> exposures.participant_oid ->
      participants.linkage.county_key), picking the county with the most
     recipients and recording that county's recipient share.
  2. Fetches daily historical weather for the county centroid over the
     window [sent_at - 5 days, sent_at] (6 inclusive days) from the
     Open-Meteo archive API (free, no key), in Fahrenheit.
  3. Computes temp mean/min/max, HDD/CDD (base 65F), and extreme-day counts,
     then writes the embedded ``weather`` field.

Design: .claude_docs/20260707_1551_campaign_weather_design.md

Usage:
    python scripts/backfill_campaign_weather_tool.py [--force] [--dry-run] [--limit N]

Idempotent: campaigns that already have a ``weather`` field are skipped unless
--force is given. Weather fetches are cached per (county, start, end) so
campaigns sharing a county+window reuse a single API call.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.county_weather import (ARCHIVE_URL, COUNTY_CENTROIDS,  # noqa: E402
                                      SOURCE_TAG, normalize_county)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WINDOW_DAYS = 5          # days prior to send; window = [sent_at - 5d, sent_at] => 6 records
HDD_BASE_F = 65.0
CDD_BASE_F = 65.0
FREEZE_THRESHOLD_F = 32.0
HOT_THRESHOLD_F = 90.0



# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_campaign_weather.py)
# ---------------------------------------------------------------------------

def compute_window(sent_at: datetime, days_prior: int = WINDOW_DAYS):
    """Return (start_date, end_date) covering the send day and `days_prior`
    preceding calendar days. end is the send date; start is end - days_prior."""
    end = sent_at.date()
    start = end - timedelta(days=days_prior)
    return start, end


def degree_days(daily_means):
    """Sum HDD and CDD (base 65F) from a list of daily mean temps (F)."""
    hdd = sum(max(0.0, HDD_BASE_F - t) for t in daily_means if t is not None)
    cdd = sum(max(0.0, t - CDD_BASE_F) for t in daily_means if t is not None)
    return round(hdd, 1), round(cdd, 1)


def extreme_days(daily):
    """Count freezing days (tmin < 32F) and hot days (tmax > 90F).

    `daily` is a list of dicts with tmin_f / tmax_f keys."""
    freezing = sum(1 for d in daily if d.get("tmin_f") is not None and d["tmin_f"] < FREEZE_THRESHOLD_F)
    hot = sum(1 for d in daily if d.get("tmax_f") is not None and d["tmax_f"] > HOT_THRESHOLD_F)
    return freezing, hot


def threshold_hours(hourly_f):
    """Count hours below the freezing / above the hot threshold.

    `hourly_f` is a flat list of hourly temperatures (F) over the window."""
    freezing = sum(1 for t in hourly_f if t is not None and t < FREEZE_THRESHOLD_F)
    hot = sum(1 for t in hourly_f if t is not None and t > HOT_THRESHOLD_F)
    return freezing, hot


def summarize_temps(daily):
    """Return {'mean','min','max'} over a list of daily records (F)."""
    means = [d["tmean_f"] for d in daily if d.get("tmean_f") is not None]
    mins = [d["tmin_f"] for d in daily if d.get("tmin_f") is not None]
    maxes = [d["tmax_f"] for d in daily if d.get("tmax_f") is not None]
    return {
        "mean": round(sum(means) / len(means), 1) if means else None,
        "min": round(min(mins), 1) if mins else None,
        "max": round(max(maxes), 1) if maxes else None,
    }


def build_weather_doc(county, share, lat, lon, start, end, daily, hourly_f, fetched_at):
    """Assemble the embedded `weather` sub-document from fetched daily+hourly data."""
    hdd, cdd = degree_days([d.get("tmean_f") for d in daily])
    freezing, hot = extreme_days(daily)
    freezing_hrs, hot_hrs = threshold_hours(hourly_f)
    return {
        "status": "ok",
        "county": county,
        "county_recipient_share": round(share, 4),
        "window": {
            "start": datetime(start.year, start.month, start.day),
            "end": datetime(end.year, end.month, end.day),
            "days": (end - start).days + 1,
        },
        "source": SOURCE_TAG,
        "latitude": lat,
        "longitude": lon,
        "fetched_at": fetched_at,
        "temp_f": summarize_temps(daily),
        "degree_days": {"hdd_base65": hdd, "cdd_base65": cdd},
        "extremes": {
            "freezing_days": freezing,
            "hot_days": hot,
            "freezing_hours": freezing_hrs,
            "hot_hours": hot_hrs,
            "window_hours": len(hourly_f),
            "freeze_threshold_f": FREEZE_THRESHOLD_F,
            "hot_threshold_f": HOT_THRESHOLD_F,
        },
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------

def resolve_campaign_counties(db):
    """One pass over participants + exposures -> {campaign_id: Counter(county)}."""
    oid_county = {}
    for p in db.participants.find({}, {"linkage.county_key": 1}):
        ck = (p.get("linkage") or {}).get("county_key")
        if ck:
            oid_county[str(p["_id"])] = normalize_county(ck)

    camp_counties = defaultdict(Counter)
    for e in db.exposures.find({}, {"campaign_id": 1, "participant_oid": 1}):
        cid = e.get("campaign_id")
        county = oid_county.get(str(e.get("participant_oid")))
        if cid and county:
            camp_counties[cid][county] += 1
    return camp_counties


def dominant_county(counter):
    """Return (county, share) for the top county, or (None, 0.0)."""
    if not counter:
        return None, 0.0
    total = sum(counter.values())
    county, n = counter.most_common(1)[0]
    return county, n / total


def fetch_weather(lat, lon, start, end, session):
    """Fetch archive weather; return {'daily': [...], 'hourly_f': [...]}.

    daily: list of {date,tmin_f,tmax_f,tmean_f}; hourly_f: flat list of hourly
    temperatures (F) across the window, used for threshold-hour counts."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean",
        "hourly": "temperature_2m",
        "temperature_unit": "fahrenheit",
        "timezone": "America/New_York",
    }
    resp = session.get(ARCHIVE_URL, params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    d = body.get("daily", {})
    dates = d.get("time", [])
    tmax = d.get("temperature_2m_max", [])
    tmin = d.get("temperature_2m_min", [])
    tmean = d.get("temperature_2m_mean", [])
    daily = []
    for i, day in enumerate(dates):
        daily.append({
            "date": day,
            "tmin_f": tmin[i] if i < len(tmin) else None,
            "tmax_f": tmax[i] if i < len(tmax) else None,
            "tmean_f": tmean[i] if i < len(tmean) else None,
        })
    hourly_f = [t for t in body.get("hourly", {}).get("temperature_2m", []) if t is not None]
    return {"daily": daily, "hourly_f": hourly_f}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Backfill embedded campaign weather.")
    ap.add_argument("--force", action="store_true", help="Recompute campaigns that already have weather")
    ap.add_argument("--dry-run", action="store_true", help="Print intended writes without mutating the DB")
    ap.add_argument("--limit", type=int, default=0, help="Process at most N campaigns (0 = all)")
    args = ap.parse_args()

    load_dotenv()
    dbname = os.getenv("MONGODB_OCTOPUS", "empower_development")
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"),
                         serverSelectionTimeoutMS=5000)
    db = client[dbname]

    print(f"Resolving recipient counties for all campaigns in {dbname} ...")
    camp_counties = resolve_campaign_counties(db)
    print(f"  resolved county data for {len(camp_counties)} campaigns")

    session = requests.Session()
    weather_cache = {}  # (county, start, end) -> daily list
    counts = Counter()

    query = {} if args.force else {"weather": {"$exists": False}}
    campaigns = list(db.campaigns.find(query, {"campaign_id": 1, "name": 1, "sent_at": 1}))
    if args.limit:
        campaigns = campaigns[: args.limit]
    print(f"Processing {len(campaigns)} campaign(s){' (dry-run)' if args.dry_run else ''} ...\n")

    for c in campaigns:
        cid = c.get("campaign_id")
        name = c.get("name", "?")
        sent_at = c.get("sent_at")

        if not sent_at:
            weather = {"status": "no_send_date"}
            counts["no_send_date"] += 1
        else:
            county, share = dominant_county(camp_counties.get(cid))
            centroid = COUNTY_CENTROIDS.get(county) if county else None
            if not centroid:
                weather = {"status": "no_county"}
                counts["no_county"] += 1
            else:
                start, end = compute_window(sent_at)
                lat, lon = centroid
                key = (county, start, end)
                try:
                    if key not in weather_cache:
                        weather_cache[key] = fetch_weather(lat, lon, start, end, session)
                        time.sleep(0.2)  # be polite to the free API
                    fetched = weather_cache[key]
                    weather = build_weather_doc(county, share, lat, lon, start, end,
                                                fetched["daily"], fetched["hourly_f"],
                                                datetime.utcnow())
                    counts["ok"] += 1
                except Exception as exc:  # noqa: BLE001 - record and continue
                    weather = {"status": "fetch_failed", "error": str(exc)[:200]}
                    counts["fetch_failed"] += 1

        status = weather["status"]
        extra = ""
        if status == "ok":
            extra = (f" {weather['county']}({weather['county_recipient_share']:.0%}) "
                     f"mean={weather['temp_f']['mean']}F "
                     f"HDD={weather['degree_days']['hdd_base65']} "
                     f"CDD={weather['degree_days']['cdd_base65']} "
                     f"freeze={weather['extremes']['freezing_days']}d/{weather['extremes']['freezing_hours']}h "
                     f"hot={weather['extremes']['hot_days']}d/{weather['extremes']['hot_hours']}h")
        print(f"  [{status:13}] {name[:42]:42}{extra}")

        if not args.dry_run:
            db.campaigns.update_one({"_id": c["_id"]}, {"$set": {"weather": weather}})

    print("\nSummary:")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")
    print(f"  unique (county,window) weather fetches: {len(weather_cache)}")
    if args.dry_run:
        print("  (dry-run: no documents were modified)")


if __name__ == "__main__":
    main()
