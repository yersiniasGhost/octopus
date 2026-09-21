"""Weather selection and loading for the thermal load calculator.

The defect these guard against: the tool applied one Franklin County station
file (KCMH, Columbus) to every county it was pointed at, and silently fell back
to a hardcoded path in another user's home directory when that file was absent.
Whatever weather it happened to load was applied to Cleveland, Dayton and
Appalachian southeast Ohio alike, producing slopes that look valid and are wrong.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import calculate_missing_thermal_loads_tool as calc  # noqa: E402

from src.tools.county_weather import (  # noqa: E402
    COUNTY_CENTROIDS,
    MissingWeatherDataError,
    UnknownCountyError,
    resolve_weather_file,
    weather_csv_path,
)


def _write_weather_csv(path, rows):
    """Write a weather CSV in the shape the fetch tool produces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=['datetime', 'T']).to_csv(path, index=False)
    return path


def _flat_day(temp, hours=24, start='2026-01-05T00:00:00'):
    """A constant-temperature hourly series, for hand-checkable integrals."""
    stamps = pd.date_range(start=start, periods=hours, freq='h')
    return [(s.isoformat(), temp) for s in stamps]


# --- file selection follows the county ---------------------------------------

def test_each_county_resolves_to_its_own_weather_file(tmp_path):
    """The whole point of T-00: the station must follow --county."""
    _write_weather_csv(tmp_path / 'Montgomery_hourly.csv', _flat_day(40.0))
    _write_weather_csv(tmp_path / 'Franklin_hourly.csv', _flat_day(40.0))

    montgomery = resolve_weather_file('Montgomery', weather_dir=tmp_path)
    franklin = resolve_weather_file('Franklin', weather_dir=tmp_path)

    assert montgomery.name == 'Montgomery_hourly.csv'
    assert franklin.name == 'Franklin_hourly.csv'
    assert montgomery != franklin


def test_an_unmapped_county_raises_and_never_falls_back_to_franklin(tmp_path):
    """Silently substituting Columbus weather is the bug, not the fallback."""
    _write_weather_csv(tmp_path / 'Franklin_hourly.csv', _flat_day(40.0))

    with pytest.raises(UnknownCountyError) as exc:
        resolve_weather_file('Nowhere', weather_dir=tmp_path)

    assert 'Franklin' not in str(exc.value)
    assert 'Nowhere' in str(exc.value)


def test_a_mapped_county_with_no_fetched_file_raises_and_names_the_fetch_tool(tmp_path):
    """Failing loudly is the replacement for the /home/warnd/ hardcode."""
    with pytest.raises(MissingWeatherDataError) as exc:
        resolve_weather_file('Ottawa', weather_dir=tmp_path)

    assert 'Ottawa' in str(exc.value)
    assert 'fetch_county_weather_hourly_tool' in str(exc.value)


def test_an_explicit_weather_file_overrides_the_county_default(tmp_path):
    explicit = _write_weather_csv(tmp_path / 'custom.csv', _flat_day(40.0))
    _write_weather_csv(tmp_path / 'Athens_hourly.csv', _flat_day(40.0))

    assert resolve_weather_file('Athens', weather_file=str(explicit),
                                weather_dir=tmp_path) == explicit


def test_every_thermal_county_has_a_centroid():
    """All 25 *ThermalLoads counties must be mappable, or T-09 cannot refresh them."""
    thermal_counties = {
        'Allen', 'Athens', 'Belmont', 'Coshocton', 'Cuyahoga', 'Fayette', 'Franklin',
        'Guernsey', 'Hancock', 'Hardin', 'Harrison', 'Holmes', 'Huron', 'Lawrence',
        'Marion', 'Montgomery', 'Morgan', 'Morrow', 'Muskingum', 'Ottawa', 'Putnam',
        'Richland', 'Ross', 'Scioto', 'Wyandot',
    }

    assert thermal_counties - set(COUNTY_CENTROIDS) == set()


def test_weather_csv_path_is_stable_for_a_county(tmp_path):
    assert weather_csv_path('Cuyahoga', tmp_path) == tmp_path / 'Cuyahoga_hourly.csv'


# --- the loader reads what the fetch tool writes ------------------------------

def test_from_clean_csv_parses_the_fetched_format(tmp_path):
    path = _write_weather_csv(tmp_path / 'Holmes_hourly.csv', _flat_day(48.5, hours=6))

    processor = calc.WeatherDataProcessor.from_clean_csv(str(path))

    assert len(processor.weather) == 6
    assert list(processor.weather.columns) == ['T']
    assert processor.weather['T'].iloc[0] == 48.5
    assert str(processor.weather.index[0]) == '2026-01-05 00:00:00'


def test_load_weather_for_county_returns_provenance(tmp_path):
    """A slope must be traceable to the weather that produced it."""
    _write_weather_csv(tmp_path / 'Montgomery_hourly.csv', _flat_day(30.0))

    _, provenance = calc.load_weather_for_county('Montgomery', weather_dir=tmp_path)

    assert provenance['weather_source']
    assert provenance['weather_location']['county'] == 'Montgomery'
    assert provenance['weather_location']['lat'] == COUNTY_CENTROIDS['Montgomery'][0]
    assert provenance['weather_range']['observations'] == 24


def test_provenance_distinguishes_two_counties(tmp_path):
    _write_weather_csv(tmp_path / 'Montgomery_hourly.csv', _flat_day(30.0))
    _write_weather_csv(tmp_path / 'Cuyahoga_hourly.csv', _flat_day(30.0))

    _, dayton = calc.load_weather_for_county('Montgomery', weather_dir=tmp_path)
    _, cleveland = calc.load_weather_for_county('Cuyahoga', weather_dir=tmp_path)

    assert dayton['weather_location'] != cleveland['weather_location']


# --- degree-hour integration, hand-checked ------------------------------------

def test_heating_load_over_a_flat_24_hour_window():
    """24 hourly readings at 52F, base 62F: 23 consecutive pairs x 10F x 1h = 230."""
    processor = calc.WeatherDataProcessor(
        pd.DataFrame({'T': [52.0] * 24},
                     index=pd.date_range('2026-01-05', periods=24, freq='h')))

    load = processor.heating_load(pd.Timestamp('2026-01-05 00:00'),
                                  pd.Timestamp('2026-01-05 23:00'))

    assert load == pytest.approx(230.0)


def test_cooling_load_over_a_flat_24_hour_window():
    """24 hourly readings at 82F, base 72F: 23 pairs x 10F x 1h = 230."""
    processor = calc.WeatherDataProcessor(
        pd.DataFrame({'T': [82.0] * 24},
                     index=pd.date_range('2026-07-05', periods=24, freq='h')))

    load = processor.cooling_load(pd.Timestamp('2026-07-05 00:00'),
                                  pd.Timestamp('2026-07-05 23:00'))

    assert load == pytest.approx(230.0)


def test_heating_load_only_accrues_across_consecutive_sub_threshold_hours():
    """A warm hour breaks the run; the hour after it starts a new one.

    Series 60,60,70,60,60 at base 62 gives two accruing pairs: 2.0 + 2.0.
    """
    processor = calc.WeatherDataProcessor(
        pd.DataFrame({'T': [60.0, 60.0, 70.0, 60.0, 60.0]},
                     index=pd.date_range('2026-01-05', periods=5, freq='h')))

    load = processor.heating_load(pd.Timestamp('2026-01-05 00:00'),
                                  pd.Timestamp('2026-01-05 04:00'))

    assert load == pytest.approx(4.0)


def test_a_window_with_no_weather_coverage_returns_zero_not_an_error():
    """Documents the fail-open behaviour that made stale weather silent.

    This is why T-00 must land before T-07 and T-09: an uncovered billing period
    contributes a zero degree-hour reading to the regression rather than raising.
    """
    processor = calc.WeatherDataProcessor(
        pd.DataFrame({'T': [52.0] * 24},
                     index=pd.date_range('2024-01-05', periods=24, freq='h')))

    assert processor.heating_load(pd.Timestamp('2026-07-01'),
                                  pd.Timestamp('2026-07-31')) == 0.0


# --- the written document carries its weather source --------------------------

def test_built_document_carries_weather_provenance():
    provenance = {
        'weather_source': 'open-meteo-archive',
        'weather_location': {'county': 'Athens', 'lat': 39.33, 'lon': -82.05},
        'weather_range': {'start': '2015-01-01T00:00:00', 'end': '2026-09-15T23:00:00',
                          'observations': 102_552},
    }

    doc = calc.build_thermal_document('P1', [], {}, weather_provenance=provenance)

    assert doc['weather_source'] == 'open-meteo-archive'
    assert doc['weather_location']['county'] == 'Athens'
    assert doc['weather_range']['observations'] == 102_552


def test_built_document_without_provenance_omits_the_weather_fields():
    doc = calc.build_thermal_document('P1', [], {})

    assert 'weather_source' not in doc
