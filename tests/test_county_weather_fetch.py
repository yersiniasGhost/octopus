"""Pure logic in fetch_county_weather_hourly_tool.

The fetch covers 2015-01-01 onward because Cuyahoga electrical readings start
2015-02-13. An eleven-year hourly pull is chunked by calendar year so a single
failure costs one year, not the whole county.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import fetch_county_weather_hourly_tool as f  # noqa: E402


# --- chunking ----------------------------------------------------------------

def test_year_chunks_splits_a_multi_year_span_on_calendar_boundaries():
    chunks = f.year_chunks(date(2024, 3, 1), date(2026, 2, 10))

    assert chunks == [
        (date(2024, 3, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 2, 10)),
    ]


def test_year_chunks_within_one_year_is_a_single_chunk():
    assert f.year_chunks(date(2026, 1, 5), date(2026, 8, 9)) == [
        (date(2026, 1, 5), date(2026, 8, 9))
    ]


def test_year_chunks_covering_the_full_thermal_span_is_one_chunk_per_year():
    chunks = f.year_chunks(date(2015, 1, 1), date(2026, 9, 16))

    assert len(chunks) == 12
    assert chunks[0][0] == date(2015, 1, 1)
    assert chunks[-1][1] == date(2026, 9, 16)


# --- payload parsing ----------------------------------------------------------

def test_rows_from_payload_pairs_each_timestamp_with_its_temperature():
    payload = {'hourly': {'time': ['2026-01-05T00:00', '2026-01-05T01:00'],
                          'temperature_2m': [31.5, 30.2]}}

    assert f.rows_from_archive_payload(payload) == [
        ('2026-01-05T00:00', 31.5),
        ('2026-01-05T01:00', 30.2),
    ]


def test_rows_from_payload_drops_hours_with_no_temperature():
    """A null must not become a zero; a zero is a real Ohio January reading."""
    payload = {'hourly': {'time': ['2026-01-05T00:00', '2026-01-05T01:00', '2026-01-05T02:00'],
                          'temperature_2m': [31.5, None, 30.2]}}

    rows = f.rows_from_archive_payload(payload)

    assert len(rows) == 2
    assert [t for _, t in rows] == [31.5, 30.2]


def test_rows_from_payload_keeps_a_genuine_zero_reading():
    payload = {'hourly': {'time': ['2026-01-05T00:00'], 'temperature_2m': [0.0]}}

    assert f.rows_from_archive_payload(payload) == [('2026-01-05T00:00', 0.0)]


def test_rows_from_payload_with_no_hourly_block_returns_empty():
    assert f.rows_from_archive_payload({}) == []
    assert f.rows_from_archive_payload({'hourly': {}}) == []


# --- metadata sidecar ---------------------------------------------------------

def test_build_meta_records_source_centroid_range_and_count():
    rows = [('2015-01-01T00:00', 20.0), ('2026-09-16T23:00', 70.0)]

    meta = f.build_meta('Cuyahoga', (41.48, -81.68), rows, fetched_at='2026-09-16T14:00:00')

    assert meta['county'] == 'Cuyahoga'
    assert meta['source'] == f.SOURCE_TAG
    assert meta['lat'] == 41.48
    assert meta['lon'] == -81.68
    assert meta['observations'] == 2
    assert meta['start'] == '2015-01-01T00:00'
    assert meta['end'] == '2026-09-16T23:00'
    assert meta['fetched_at'] == '2026-09-16T14:00:00'


def test_build_meta_on_an_empty_fetch_reports_zero_observations():
    meta = f.build_meta('Morrow', (40.52, -82.79), [], fetched_at='2026-09-16T14:00:00')

    assert meta['observations'] == 0
    assert meta['start'] is None
    assert meta['end'] is None
