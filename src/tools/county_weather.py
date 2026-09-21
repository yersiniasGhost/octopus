"""County weather geography and file conventions, shared by the weather tools.

`COUNTY_CENTROIDS` and `normalize_county` were originally private to
`scripts/backfill_campaign_weather_tool.py`. They live here because
`scripts/fetch_county_weather_hourly_tool.py` and
`scripts/calculate_missing_thermal_loads_tool.py` need the identical mapping —
two tables of Ohio county coordinates that could drift apart is exactly the
class of bug that put Columbus weather on Cleveland parcels.
"""

from pathlib import Path
from typing import Optional, Tuple

# Approximate geographic centroids (lat, lon) for the 25 Ohio counties in
# CountyKeys. County-level weather does not need parcel precision.
COUNTY_CENTROIDS = {
    "Allen": (40.77, -84.11), "Athens": (39.33, -82.05), "Belmont": (40.02, -80.99),
    "Coshocton": (40.30, -81.92), "Cuyahoga": (41.48, -81.68), "Fayette": (39.56, -83.46),
    "Franklin": (39.97, -83.01), "Guernsey": (40.05, -81.49), "Hancock": (41.00, -83.67),
    "Hardin": (40.66, -83.66), "Harrison": (40.29, -81.09), "Holmes": (40.56, -81.93),
    "Huron": (41.14, -82.60), "Lawrence": (38.60, -82.53), "Marion": (40.59, -83.16),
    "Montgomery": (39.75, -84.29), "Morgan": (39.62, -81.85), "Morrow": (40.52, -82.79),
    "Muskingum": (39.96, -81.94), "Ottawa": (41.53, -82.94), "Putnam": (41.02, -84.13),
    "Richland": (40.77, -82.53), "Ross": (39.34, -82.94), "Scioto": (38.80, -83.02),
    "Wyandot": (40.84, -83.30),
}

# Open-Meteo historical archive: free, no API key, hourly data from 1940 to ~5 days ago.
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_TAG = "open-meteo-archive"

# Where fetch_county_weather_hourly_tool.py writes, and the calculation tool reads.
DEFAULT_WEATHER_DIR = Path(__file__).resolve().parents[2] / 'data' / 'weather'

FETCH_TOOL = 'scripts/fetch_county_weather_hourly_tool.py'


class UnknownCountyError(KeyError):
    """The county has no centroid, so no weather can be attributed to it."""


class MissingWeatherDataError(FileNotFoundError):
    """The county is known but its weather has not been fetched yet."""


def normalize_county(county_key: str) -> str:
    """Normalize a linkage.county_key to a COUNTY_CENTROIDS key.

    Handles values like 'Franklin', 'FranklinCounty', 'Franklin County'."""
    if not county_key:
        return ""
    name = str(county_key).strip()
    for suffix in (" County", "County"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def centroid(county: str) -> Tuple[float, float]:
    """Return (lat, lon) for a county, or raise. Never falls back to a default."""
    name = normalize_county(county)
    if name not in COUNTY_CENTROIDS:
        raise UnknownCountyError(
            f"no weather centroid for county '{county}'. Add it to COUNTY_CENTROIDS "
            f"in src/tools/county_weather.py. Weather is never substituted from "
            f"another county."
        )
    return COUNTY_CENTROIDS[name]


def weather_csv_path(county: str, weather_dir: Optional[Path] = None) -> Path:
    """The conventional hourly weather CSV path for a county."""
    base = Path(weather_dir) if weather_dir is not None else DEFAULT_WEATHER_DIR
    return base / f"{normalize_county(county)}_hourly.csv"


def resolve_weather_file(county: str, weather_file: Optional[str] = None,
                         weather_dir: Optional[Path] = None) -> Path:
    """Resolve which weather CSV to use for a county.

    An explicit weather_file wins. Otherwise the county's fetched file is used.
    An unmapped county or an unfetched county raises -- there is deliberately no
    fallback, because a silent fallback is what applied Columbus degree-hours to
    Cleveland, Dayton and Appalachian southeast Ohio.
    """
    if weather_file:
        path = Path(weather_file)
        if not path.exists():
            raise MissingWeatherDataError(f"--weather-file not found: {path}")
        return path

    centroid(county)  # raises UnknownCountyError before any path is considered
    path = weather_csv_path(county, weather_dir)
    if not path.exists():
        raise MissingWeatherDataError(
            f"no weather data for {normalize_county(county)} at {path}. "
            f"Fetch it first:\n"
            f"    python {FETCH_TOOL} --county {normalize_county(county)} --execute"
        )
    return path
