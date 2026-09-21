#!/usr/bin/env python3
"""
Fetch hourly temperatures per Ohio county from the Open-Meteo historical archive.

Produces the per-county weather files the thermal load calculator reads:

    data/weather/{County}_hourly.csv        datetime,T   (T in Fahrenheit)
    data/weather/{County}_hourly.meta.json  source, centroid, range, count

Why this exists: the calculator previously loaded a single Franklin County
station file (KCMH, Columbus) and applied it to whatever --county it was given,
falling back to a hardcoded path in another user's home directory. Those files
cover 2023 and part of 2024, while electrical billing periods now run from
2015-02-13 (Cuyahoga) through 2026-08-09. Uncovered periods integrate to a
silent 0.0 degree-hours rather than an error, so the slopes looked fine.

Dry-run by default. --execute writes files.

Usage:
    source venv/bin/activate

    python scripts/fetch_county_weather_hourly_tool.py --county Franklin --dry-run
    python scripts/fetch_county_weather_hourly_tool.py --county Franklin --execute
    python scripts/fetch_county_weather_hourly_tool.py --all --execute
    python scripts/fetch_county_weather_hourly_tool.py --all --start 2015-01-01 --end 2026-09-16 --execute
"""

import argparse
import csv
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.county_weather import (ARCHIVE_URL, COUNTY_CENTROIDS,  # noqa: E402
                                      DEFAULT_WEATHER_DIR, SOURCE_TAG, centroid,
                                      normalize_county, weather_csv_path)

# Cuyahoga electrical readings start 2015-02-13; everything else is later.
DEFAULT_START = date(2015, 1, 1)
TIMEZONE = "America/New_York"
PAUSE_SECONDS = 1.0     # courtesy pacing against a free API


def year_chunks(start: date, end: date) -> List[Tuple[date, date]]:
    """Split a span into one chunk per calendar year.

    An eleven-year hourly pull is a large single request; chunking means a
    failure costs one year rather than the whole county.
    """
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(date(cursor.year, 12, 31), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def rows_from_archive_payload(payload: dict) -> List[Tuple[str, float]]:
    """Pair each timestamp with its temperature, dropping hours with no reading.

    A null is dropped rather than zeroed: 0.0F is a real Ohio January reading.
    """
    hourly = (payload or {}).get('hourly') or {}
    times = hourly.get('time') or []
    temps = hourly.get('temperature_2m') or []
    return [(t, v) for t, v in zip(times, temps) if v is not None]


def build_meta(county: str, latlon: Tuple[float, float], rows: List[Tuple[str, float]],
               fetched_at: str) -> dict:
    """Provenance sidecar: what was fetched, from where, covering what."""
    lat, lon = latlon
    return {
        'county': county, 'source': SOURCE_TAG, 'lat': lat, 'lon': lon,
        'timezone': TIMEZONE, 'observations': len(rows),
        'start': rows[0][0] if rows else None,
        'end': rows[-1][0] if rows else None,
        'fetched_at': fetched_at,
    }


def fetch_chunk(session, lat: float, lon: float, start: date, end: date) -> List[Tuple[str, float]]:
    """One archive request for one date span."""
    params = {
        'latitude': lat, 'longitude': lon,
        'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'hourly': 'temperature_2m', 'temperature_unit': 'fahrenheit',
        'timezone': TIMEZONE,
    }
    resp = session.get(ARCHIVE_URL, params=params, timeout=90)
    resp.raise_for_status()
    return rows_from_archive_payload(resp.json())


def fetch_county(county: str, start: date, end: date, verbose: bool = False) -> List[Tuple[str, float]]:
    """Fetch every hourly reading for a county across the span."""
    lat, lon = centroid(county)
    session = requests.Session()
    rows: List[Tuple[str, float]] = []
    chunks = year_chunks(start, end)
    for i, (c_start, c_end) in enumerate(chunks, 1):
        got = fetch_chunk(session, lat, lon, c_start, c_end)
        rows.extend(got)
        if verbose:
            print(f"      [{i}/{len(chunks)}] {c_start} -> {c_end}: {len(got):,} hours", flush=True)
        if i < len(chunks):
            time.sleep(PAUSE_SECONDS)
    session.close()
    rows.sort(key=lambda r: r[0])
    return rows


def write_outputs(county: str, rows: List[Tuple[str, float]], meta: dict, weather_dir: Path) -> Path:
    """Write the CSV the calculator reads plus its provenance sidecar."""
    path = weather_csv_path(county, weather_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['datetime', 'T'])
        writer.writerows(rows)
    path.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2))
    return path


def parse_date(value: str) -> date:
    return datetime.strptime(value, '%Y-%m-%d').date()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--county', help='single county, e.g. Franklin')
    group.add_argument('--all', action='store_true', dest='all_counties',
                       help='every county in COUNTY_CENTROIDS')
    p.add_argument('--start', type=parse_date, default=DEFAULT_START)
    p.add_argument('--end', type=parse_date, default=None,
                   help='default: 6 days ago (the archive lags real time)')
    p.add_argument('--weather-dir', type=Path, default=DEFAULT_WEATHER_DIR)
    p.add_argument('--dry-run', action='store_true', default=True)
    p.add_argument('--execute', action='store_true', help='actually fetch and write files')
    p.add_argument('--verbose', action='store_true')
    a = p.parse_args()

    end = a.end or (date.today() - timedelta(days=6))
    counties = sorted(COUNTY_CENTROIDS) if a.all_counties else [normalize_county(a.county)]
    execute = a.execute
    chunks = len(year_chunks(a.start, end))

    print()
    print('=' * 70)
    print(f"  Hourly weather fetch - {SOURCE_TAG}")
    print('=' * 70)
    print(f"  span        {a.start} -> {end}  ({chunks} yearly request(s) per county)")
    print(f"  counties    {len(counties)}")
    print(f"  output      {a.weather_dir}")
    print(f"  mode        {'EXECUTE' if execute else 'DRY RUN (no files written)'}")
    print()

    if not execute:
        for county in counties:
            lat, lon = centroid(county)
            path = weather_csv_path(county, a.weather_dir)
            state = 'exists, would overwrite' if path.exists() else 'would create'
            print(f"  {county:<12} ({lat:>6.2f}, {lon:>7.2f})  {chunks} request(s)  ->  {path.name}  [{state}]")
        print(f"\n  DRY RUN: nothing fetched, nothing written. Re-run with --execute.\n")
        return 0

    total = 0
    for county in counties:
        lat, lon = centroid(county)
        print(f"  {county:<12} ({lat:>6.2f}, {lon:>7.2f})", flush=True)
        rows = fetch_county(county, a.start, end, verbose=a.verbose)
        meta = build_meta(county, (lat, lon), rows, fetched_at=datetime.now().isoformat())
        path = write_outputs(county, rows, meta, a.weather_dir)
        total += len(rows)
        print(f"      {len(rows):,} hourly observations  {meta['start']} -> {meta['end']}")
        print(f"      -> {path}", flush=True)

    print(f"\n  {total:,} observations across {len(counties)} county file(s)\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
