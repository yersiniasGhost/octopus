"""Unit tests for the pure logic in backfill_campaign_weather_tool."""
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import backfill_campaign_weather_tool as w  # noqa: E402


def test_compute_window_is_six_inclusive_days():
    start, end = w.compute_window(datetime(2025, 8, 15, 12, 0))
    assert end.isoformat() == "2025-08-15"
    assert start.isoformat() == "2025-08-10"
    assert (end - start).days + 1 == 6


def test_normalize_county_strips_suffixes():
    assert w.normalize_county("Franklin") == "Franklin"
    assert w.normalize_county("FranklinCounty") == "Franklin"
    assert w.normalize_county("Franklin County") == "Franklin"
    assert w.normalize_county("  Ross  ") == "Ross"
    assert w.normalize_county(None) == ""


def test_degree_days_heating():
    # mean temps well below 65 -> HDD accrues, CDD zero
    hdd, cdd = w.degree_days([30.0, 40.0, 50.0])  # deficits 35+25+15
    assert hdd == 75.0
    assert cdd == 0.0


def test_degree_days_cooling():
    hdd, cdd = w.degree_days([75.0, 85.0])  # surplus 10+20
    assert hdd == 0.0
    assert cdd == 30.0


def test_degree_days_ignores_none():
    hdd, cdd = w.degree_days([None, 65.0])  # 65 is exactly base -> both zero
    assert hdd == 0.0
    assert cdd == 0.0


def test_extreme_days_counts_thresholds():
    daily = [
        {"tmin_f": 20.0, "tmax_f": 40.0},   # freezing
        {"tmin_f": 33.0, "tmax_f": 95.0},   # hot
        {"tmin_f": 31.9, "tmax_f": 90.0},   # freezing; 90 is not > 90
    ]
    freezing, hot = w.extreme_days(daily)
    assert freezing == 2
    assert hot == 1


def test_threshold_hours_counts_and_ignores_none():
    hourly = [31.9, 32.0, 10.0, 90.0, 90.1, 95.0, None, 50.0]
    freezing, hot = w.threshold_hours(hourly)
    assert freezing == 2   # 31.9 and 10.0 (< 32); 32.0 is not < 32
    assert hot == 2        # 90.1 and 95.0 (> 90); 90.0 is not > 90


def test_summarize_temps():
    daily = [
        {"tmin_f": 20.0, "tmax_f": 50.0, "tmean_f": 35.0},
        {"tmin_f": 10.0, "tmax_f": 60.0, "tmean_f": 40.0},
    ]
    s = w.summarize_temps(daily)
    assert s == {"mean": 37.5, "min": 10.0, "max": 60.0}


def test_summarize_temps_empty():
    assert w.summarize_temps([]) == {"mean": None, "min": None, "max": None}


def test_dominant_county_picks_top_and_share():
    county, share = w.dominant_county(Counter({"Lawrence": 3, "Scioto": 1}))
    assert county == "Lawrence"
    assert round(share, 2) == 0.75


def test_dominant_county_empty():
    assert w.dominant_county(Counter()) == (None, 0.0)
    assert w.dominant_county(None) == (None, 0.0)


def test_build_weather_doc_structure():
    daily = [
        {"date": "2025-01-10", "tmin_f": 20.0, "tmax_f": 40.0, "tmean_f": 30.0},
        {"date": "2025-01-11", "tmin_f": 25.0, "tmax_f": 45.0, "tmean_f": 35.0},
    ]
    hourly = [20.0, 25.0, 31.0, 40.0, 33.0, 45.0]  # three hours < 32F
    from datetime import date
    doc = w.build_weather_doc("Franklin", 0.82, 39.97, -83.0,
                              date(2025, 1, 10), date(2025, 1, 11), daily, hourly,
                              datetime(2026, 7, 7))
    assert doc["status"] == "ok"
    assert doc["county"] == "Franklin"
    assert doc["county_recipient_share"] == 0.82
    assert doc["window"]["days"] == 2
    assert doc["degree_days"]["hdd_base65"] == 65.0  # (65-30)+(65-35)
    assert doc["degree_days"]["cdd_base65"] == 0.0
    assert doc["extremes"]["freezing_days"] == 2
    assert doc["extremes"]["freezing_hours"] == 3
    assert doc["extremes"]["hot_hours"] == 0
    assert doc["extremes"]["window_hours"] == 6
    assert doc["temp_f"]["min"] == 20.0
    assert len(doc["daily"]) == 2
