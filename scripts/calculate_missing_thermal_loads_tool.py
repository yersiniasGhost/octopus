#!/usr/bin/env python3
"""
Calculate thermal loads for parcels missing from FranklinThermalLoads.

This script identifies parcels in FranklinElectricalDB that don't have corresponding
thermal load calculations in FranklinThermalLoads, and calculates the missing values.

The methodology follows the existing pipeline:
1. Calculate Heating Degree-Hours (HDH) and Cooling Degree-Hours (CDH) for each billing period
2. Perform linear regression: KWH = slope × HDH + intercept
3. Store results in MongoDB

Usage:
    python scripts/calculate_missing_thermal_loads_tool.py --dry-run
    python scripts/calculate_missing_thermal_loads_tool.py --county Franklin
    python scripts/calculate_missing_thermal_loads_tool.py --county Franklin --limit 100

Options:
    --dry-run       Preview without writing to database
    --county NAME   County to process (default: Franklin)
    --limit N       Limit number of parcels to process (for testing)
    --verbose       Show detailed progress
    --weather-file  Path to weather data CSV
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from src.tools.county_weather import (MissingWeatherDataError, UnknownCountyError,
                                      centroid, normalize_county, resolve_weather_file)
from src.tools.mongo import get_empower_db
from src.utils.log_manager import LogManager

# Recorded when a weather file carries no provenance sidecar. Honest, and
# still actionable: 'unknown' sorts as stale for a later refresh.
SOURCE_TAG_UNKNOWN = 'unknown'

logger = LogManager().get_logger(__name__)


class WeatherDataProcessor:
    """Process NOAA weather data for thermal load calculations."""

    def __init__(self, weather_df: pd.DataFrame):
        """
        Initialize with weather dataframe.

        Args:
            weather_df: DataFrame with 'datetime' index and 'T' column (temperature in °F)
        """
        self.weather = weather_df
        # Assuming hourly data
        self.dt = 1.0  # hours

    @classmethod
    def from_noaa_files(cls, file_paths: List[str]) -> 'WeatherDataProcessor':
        """
        Load and combine NOAA weather files.

        Args:
            file_paths: List of paths to NOAA CSV files

        Returns:
            WeatherDataProcessor instance
        """
        dfs = []
        for path in file_paths:
            df = pd.read_csv(path, low_memory=False)
            dfs.append(df)

        combined = pd.concat(dfs, ignore_index=True)

        # Parse NOAA TMP format: "+0083,1" means 8.3°C with quality flag 1
        def parse_temp_to_fahrenheit(tmp_value):
            if pd.isna(tmp_value) or '+9999' in str(tmp_value):
                return np.nan
            try:
                temp_str = str(tmp_value).split(',')[0]
                temp_celsius = float(temp_str) / 10
                return (temp_celsius * 9/5) + 32
            except (ValueError, IndexError):
                return np.nan

        combined['T'] = combined['TMP'].apply(parse_temp_to_fahrenheit)

        # Filter to hourly observations (typically at :51 past each hour)
        combined['datetime'] = pd.to_datetime(combined['DATE'])
        hourly = combined[combined['DATE'].str.endswith(':51:00')].copy()

        # Set index and keep only needed columns
        hourly = hourly.set_index('datetime')[['T']].dropna()
        hourly = hourly.sort_index()

        return cls(hourly)

    @classmethod
    def from_clean_csv(cls, file_path: str) -> 'WeatherDataProcessor':
        """
        Load pre-processed weather file with datetime and T columns.

        Args:
            file_path: Path to clean weather CSV

        Returns:
            WeatherDataProcessor instance
        """
        df = pd.read_csv(file_path)
        # Handle both 'datetime' and 'valid' column names
        dt_col = 'datetime' if 'datetime' in df.columns else 'valid'
        df['datetime'] = pd.to_datetime(df[dt_col])
        df = df.set_index('datetime')[['T']].dropna()
        df = df.sort_index()
        return cls(df)

    def heating_load(self, start: pd.Timestamp, end: pd.Timestamp, threshold: float = 62.0) -> float:
        """
        Calculate heating degree-hours between two timestamps.

        Uses trapezoidal integration for temperatures below threshold.

        Args:
            start: Start timestamp
            end: End timestamp
            threshold: Base temperature (default 62°F)

        Returns:
            Heating degree-hours (positive value)
        """
        tdf = self.weather[(self.weather.index >= start) & (self.weather.index <= end)]

        if len(tdf) < 2:
            return 0.0

        integral = 0.0
        prev_temp = None
        in_heating_period = False

        for idx, row in tdf.iterrows():
            temp = row['T']
            if pd.isna(temp):
                continue

            if temp <= threshold:
                if prev_temp is not None and in_heating_period:
                    # Trapezoidal integration: (threshold - avg_temp) * dt
                    avg_temp = (temp + prev_temp) / 2
                    integral += (threshold - avg_temp) * self.dt
                in_heating_period = True
            else:
                in_heating_period = False

            prev_temp = temp

        return max(0.0, integral)

    def cooling_load(self, start: pd.Timestamp, end: pd.Timestamp, threshold: float = 72.0) -> float:
        """
        Calculate cooling degree-hours between two timestamps.

        Uses trapezoidal integration for temperatures above threshold.

        Args:
            start: Start timestamp
            end: End timestamp
            threshold: Base temperature (default 72°F)

        Returns:
            Cooling degree-hours (positive value)
        """
        tdf = self.weather[(self.weather.index >= start) & (self.weather.index <= end)]

        if len(tdf) < 2:
            return 0.0

        integral = 0.0
        prev_temp = None
        in_cooling_period = False

        for idx, row in tdf.iterrows():
            temp = row['T']
            if pd.isna(temp):
                continue

            if temp > threshold:
                if prev_temp is not None and in_cooling_period:
                    # Trapezoidal integration: (avg_temp - threshold) * dt
                    avg_temp = (temp + prev_temp) / 2
                    integral += (avg_temp - threshold) * self.dt
                in_cooling_period = True
            else:
                in_cooling_period = False

            prev_temp = temp

        return max(0.0, integral)


def get_missing_parcels(db, county: str) -> List[str]:
    """
    Find parcels in ElectricalDB that don't have ThermalLoads records.

    Args:
        db: MongoDB database connection
        county: County name (e.g., 'Franklin')

    Returns:
        List of parcel_ids missing thermal data
    """
    electrical_coll = f"{county}ElectricalDB"
    thermal_coll = f"{county}ThermalLoads"

    # Only parcel-linked records can receive thermal loads -- thermal loads are
    # keyed by parcel. Unlinked utility accounts (parcel_id null/absent) are
    # EXCLUDED here, never deleted: they carry real addresses and real usage and
    # recovering them by address matching is T-14. The $nin filter is a
    # performance optimisation; the truthiness guard is what makes this correct.
    unlinked = db[electrical_coll].count_documents({'parcel_id': {'$in': [None, '']}})
    electrical_parcels = {
        doc.get('parcel_id')
        for doc in db[electrical_coll].find({'parcel_id': {'$nin': [None, '']}},
                                            {'parcel_id': 1})
        if doc.get('parcel_id')
    }

    thermal_parcels = {
        doc.get('parcel_id')
        for doc in db[thermal_coll].find({}, {'parcel_id': 1})
        if doc.get('parcel_id')
    }

    missing = electrical_parcels - thermal_parcels

    logger.info(f"Found {len(electrical_parcels):,} electrical records")
    if unlinked:
        logger.info(f"Excluded {unlinked:,} electrical records with no parcel_id "
                    f"(unmatched utility accounts - see T-14)")
    logger.info(f"Found {len(thermal_parcels):,} thermal records")
    logger.info(f"Missing thermal data: {len(missing):,} parcels")

    return sorted(missing)


def get_electrical_data(db, county: str, parcel_ids: List[str], batch_size: int = 1000) -> Dict[str, Dict]:
    """
    Fetch electrical billing data for specified parcels in batches.

    Args:
        db: MongoDB database connection
        county: County name
        parcel_ids: List of parcel IDs to fetch
        batch_size: Number of IDs per query batch

    Returns:
        Dict mapping parcel_id to billing data
    """
    electrical_coll = f"{county}ElectricalDB"
    data = {}

    # Process in batches to avoid massive $in queries
    for i in range(0, len(parcel_ids), batch_size):
        batch = parcel_ids[i:i + batch_size]
        cursor = db[electrical_coll].find(
            {'parcel_id': {'$in': batch}},
            {'parcel_id': 1, 'time_series_elec': 1}
        )

        for doc in cursor:
            parcel_id = doc['parcel_id']
            time_series = doc.get('time_series_elec', {})

            if time_series and len(time_series) >= 2:
                data[parcel_id] = time_series

    return data


def calculate_thermal_loads_for_parcel(
    weather: WeatherDataProcessor,
    time_series: Dict[str, float]
) -> Tuple[List[Dict], Dict]:
    """
    Calculate thermal loads for a single parcel.

    Args:
        weather: WeatherDataProcessor instance
        time_series: Dict mapping date strings to kWh values

    Returns:
        Tuple of (billing_period_data, slope_data)
    """
    # Sort dates
    dates = sorted(time_series.keys())

    if len(dates) < 2:
        return [], {}

    billing_data = []

    for i in range(len(dates) - 1):
        try:
            d1 = pd.to_datetime(dates[i])
            d2 = pd.to_datetime(dates[i + 1])
            kwh = time_series[dates[i]]

            if pd.isna(kwh) or kwh is None:
                continue

            hl = weather.heating_load(d1, d2)
            cl = weather.cooling_load(d1, d2)

            billing_data.append({
                'date': dates[i],
                'kwh': float(kwh),
                'hl': hl,
                'cl': cl
            })
        except Exception as e:
            logger.debug(f"Error processing billing period {dates[i]}: {e}")
            continue

    if len(billing_data) < 3:
        return billing_data, {}

    # Perform linear regression
    df = pd.DataFrame(billing_data)

    slope_data = {}

    # Heating load regression
    try:
        x_hl = df['hl'].values.reshape(-1, 1)
        y_kwh = df['kwh'].values

        model_hl = LinearRegression()
        model_hl.fit(x_hl, y_kwh)

        predictions_hl = model_hl.predict(x_hl)
        r2_hl = r2_score(y_kwh, predictions_hl)

        slope_data['kwh_hl_slope'] = float(model_hl.coef_[0])
        slope_data['kwh_hl_intercept'] = float(model_hl.intercept_)
        slope_data['kwh_hl_r2'] = float(r2_hl)
    except Exception as e:
        logger.debug(f"Heating regression failed: {e}")
        slope_data['kwh_hl_slope'] = 0.0
        slope_data['kwh_hl_intercept'] = 0.0
        slope_data['kwh_hl_r2'] = 0.0

    # Cooling load regression
    try:
        x_cl = df['cl'].values.reshape(-1, 1)

        model_cl = LinearRegression()
        model_cl.fit(x_cl, y_kwh)

        predictions_cl = model_cl.predict(x_cl)
        r2_cl = r2_score(y_kwh, predictions_cl)

        slope_data['kwh_cl_slope'] = float(model_cl.coef_[0])
        slope_data['kwh_cl_intercept'] = float(model_cl.intercept_)
        slope_data['kwh_cl_r2'] = float(r2_cl)
    except Exception as e:
        logger.debug(f"Cooling regression failed: {e}")
        slope_data['kwh_cl_slope'] = 0.0
        slope_data['kwh_cl_intercept'] = 0.0
        slope_data['kwh_cl_r2'] = 0.0

    return billing_data, slope_data


def load_weather_for_county(county: str, weather_file: Optional[str] = None,
                            weather_dir: Optional[Path] = None) -> Tuple['WeatherDataProcessor', Dict]:
    """Load the weather series for a county and describe where it came from.

    Raises rather than substituting another county's weather. The previous
    behaviour applied one Columbus station file to every county, so a Cleveland
    or Dayton slope was computed against Franklin County degree-hours.
    """
    path = resolve_weather_file(county, weather_file=weather_file, weather_dir=weather_dir)
    processor = WeatherDataProcessor.from_clean_csv(str(path))
    lat, lon = centroid(county)

    meta_path = Path(str(path).replace('.csv', '.meta.json'))
    source = SOURCE_TAG_UNKNOWN
    if meta_path.exists():
        try:
            source = json.loads(meta_path.read_text()).get('source', source)
        except (ValueError, OSError):
            pass
    elif weather_file:
        source = f'file:{Path(weather_file).name}'

    index = processor.weather.index
    provenance = {
        'weather_source': source,
        'weather_location': {'county': normalize_county(county), 'lat': lat, 'lon': lon},
        'weather_range': {
            'start': index.min().isoformat() if len(index) else None,
            'end': index.max().isoformat() if len(index) else None,
            'observations': int(len(index)),
        },
    }
    return processor, provenance


def build_thermal_document(parcel_id: str, billing_data: List[Dict], slope_data: Dict,
                           weather_provenance: Optional[Dict] = None) -> Dict:
    """Assemble the ThermalLoads document.

    NOTE: the gas sentinels and the insert-only write path are known defects
    tracked as T-01 and T-03 in the remediation runbook. They are deliberately
    left alone here; T-00 only adds weather provenance.
    """
    document = {
        'parcel_id': parcel_id,
        'kwh_hl_cl_loads': billing_data,
        'gas_hl_cl_loads': [],  # Not calculated for electric-only
        'kwh_hl_slope': slope_data.get('kwh_hl_slope', 0.0),
        'kwh_hl_intercept': slope_data.get('kwh_hl_intercept', 0.0),
        'kwh_hl_r2': slope_data.get('kwh_hl_r2', 0.0),
        'kwh_cl_slope': slope_data.get('kwh_cl_slope', 0.0),
        'kwh_cl_intercept': slope_data.get('kwh_cl_intercept', 0.0),
        'kwh_cl_r2': slope_data.get('kwh_cl_r2', 0.0),
        'gas_hl_slope': -1,
        'gas_hl_intercept': -1,
        'gas_hl_r2': -1,
        'gas_cl_slope': -1,
        'gas_cl_intercept': -1,
        'gas_cl_r2': -1,
        'calculated_at': datetime.now(),
        'calculation_source': 'calculate_missing_thermal_loads_tool.py',
    }
    if weather_provenance:
        document.update(weather_provenance)
    return document


def insert_thermal_loads(
    db,
    county: str,
    parcel_id: str,
    billing_data: List[Dict],
    slope_data: Dict,
    dry_run: bool = False,
    weather_provenance: Optional[Dict] = None
) -> bool:
    """
    Insert thermal load data into MongoDB.

    Args:
        db: MongoDB database connection
        county: County name
        parcel_id: Parcel ID
        billing_data: List of billing period thermal data
        slope_data: Regression results
        dry_run: If True, don't actually insert

    Returns:
        True if successful
    """
    thermal_coll = f"{county}ThermalLoads"

    document = build_thermal_document(parcel_id, billing_data, slope_data, weather_provenance)

    if dry_run:
        return True

    try:
        db[thermal_coll].insert_one(document)
        return True
    except Exception as e:
        logger.error(f"Failed to insert {parcel_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Calculate thermal loads for parcels missing from ThermalLoads collection'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without writing to database')
    parser.add_argument('--county', type=str, default='Franklin',
                        help='County to process (default: Franklin)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of parcels to process')
    parser.add_argument('--verbose', action='store_true',
                        help='Show detailed progress')
    parser.add_argument('--weather-file', type=str, default=None,
                        help='Path to pre-processed weather CSV (with valid, T columns)')
    args = parser.parse_args()

    print("\n" + "=" * 70, flush=True)
    print("  THERMAL LOAD CALCULATION FOR MISSING PARCELS", flush=True)
    print("=" * 70, flush=True)

    if args.dry_run:
        print("\n  [DRY RUN MODE - No changes will be made]", flush=True)

    # Connect to database
    print(f"\n  County: {args.county}", flush=True)
    print("  Connecting to database...", flush=True)
    db = get_empower_db()

    # Find missing parcels
    print("\n  Identifying parcels missing thermal data...", flush=True)
    missing_parcels = get_missing_parcels(db, args.county)

    if not missing_parcels:
        print("  No missing parcels found!", flush=True)
        return 0

    if args.limit:
        missing_parcels = missing_parcels[:args.limit]
        print(f"  Limited to {args.limit} parcels for processing", flush=True)

    # Load weather data -- the station follows --county, and never falls back
    # to another county's weather (see T-00 in the remediation runbook).
    print("\n  Loading weather data...", flush=True)
    try:
        weather, weather_provenance = load_weather_for_county(args.county, args.weather_file)
    except (UnknownCountyError, MissingWeatherDataError) as exc:
        print(f"\n  ERROR: {exc}\n")
        return 1

    loc = weather_provenance['weather_location']
    rng = weather_provenance['weather_range']
    print(f"  Weather data loaded: {rng['observations']:,} hourly observations", flush=True)
    print(f"  Source: {weather_provenance['weather_source']} "
          f"@ {loc['county']} ({loc['lat']}, {loc['lon']})", flush=True)
    print(f"  Date range: {rng['start']} to {rng['end']}", flush=True)

    # Fetch electrical data for missing parcels
    print("\n  Fetching electrical billing data...", flush=True)
    electrical_data = get_electrical_data(db, args.county, missing_parcels)
    print(f"  Found billing data for {len(electrical_data):,} of {len(missing_parcels):,} parcels", flush=True)

    # Process parcels
    print("\n  Calculating thermal loads...", flush=True)
    stats = {
        'processed': 0,
        'success': 0,
        'failed': 0,
        'insufficient_data': 0
    }

    for i, parcel_id in enumerate(missing_parcels):
        if parcel_id not in electrical_data:
            stats['insufficient_data'] += 1
            continue

        stats['processed'] += 1

        # Progress indicator every 1000 parcels
        if (i + 1) % 1000 == 0:
            print(f"  [{i + 1:,}/{len(missing_parcels):,}] {stats['success']:,} calculated, {stats['insufficient_data']:,} skipped...", flush=True)

        if args.verbose:
            print(f"  [{i + 1}/{len(missing_parcels)}] Processing {parcel_id}...", end=" ")

        time_series = electrical_data[parcel_id]
        billing_data, slope_data = calculate_thermal_loads_for_parcel(weather, time_series)

        if not slope_data:
            stats['insufficient_data'] += 1
            if args.verbose:
                print("insufficient data")
            continue

        if insert_thermal_loads(db, args.county, parcel_id, billing_data, slope_data,
                                args.dry_run, weather_provenance):
            stats['success'] += 1
            if args.verbose:
                hl_slope = slope_data.get('kwh_hl_slope', 0)
                hl_r2 = slope_data.get('kwh_hl_r2', 0)
                print(f"✓ HL slope={hl_slope:.4f}, R²={hl_r2:.3f}")
        else:
            stats['failed'] += 1
            if args.verbose:
                print("✗ insert failed")

    # Print summary
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"\n  Total missing parcels:    {len(missing_parcels):,}")
    print(f"  Processed:                {stats['processed']:,}")
    print(f"  Successfully calculated:  {stats['success']:,}")
    print(f"  Insufficient data:        {stats['insufficient_data']:,}")
    print(f"  Failed inserts:           {stats['failed']:,}")

    if args.dry_run:
        print("\n  [DRY RUN - No changes were made to database]")
    else:
        print(f"\n  {stats['success']:,} new thermal load records inserted into {args.county}ThermalLoads")

    print("\n" + "=" * 70)
    print("  COMPLETE")
    print("=" * 70 + "\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
