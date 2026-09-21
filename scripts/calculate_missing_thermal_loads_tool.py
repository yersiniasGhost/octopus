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

# Specification marker written on every document. Records without it were
# produced by the superseded two-univariate-regression code.
THERMAL_MODEL = 'hl+cl'
THERMAL_MODEL_PER_DAY = 'hl+cl/day'

# A billing row pairs kWh from the FIRST reading with degree-hours integrated to
# the SECOND. That is only coherent when the two readings are about a month
# apart. A wider span means a reading is missing, and the row then carries one
# month's kWh against a multi-year weather total -- Cuyahoga parcel 30324005 has
# a 2,369-day span holding 471 kWh and 738,887 heating degree-hours, 36x the
# largest legitimate value in its own history. Four such rows out of 39 flip its
# heating coefficient from -0.00637 to +0.00565. These are gaps, not periods.
PERIOD_MIN_DAYS = 25
PERIOD_MAX_DAYS = 40

# Fields the single model replaces. A joint fit has one intercept and one r2,
# so the per-driver pair no longer exists and is removed rather than duplicated.
LEGACY_SLOPE_FIELDS = ('kwh_hl_intercept', 'kwh_cl_intercept',
                       'kwh_hl_r2', 'kwh_cl_r2')

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

    # key=str: Cuyahoga mixes int and str parcel_ids (T-02), which cannot be
    # compared directly. Ordering is only for reproducible batching.
    return sorted(missing, key=str)


def get_target_parcels(db, county: str, recompute_all: bool = False) -> List[str]:
    """Select the parcels to compute for.

    Default: parcels with electrical data and no ThermalLoads record.
    recompute_all: every parcel-linked electrical record, so existing slopes are
    revisited too. That is the mode the single-model migration runs in -- the
    superseded records are updated in place, never duplicated.
    """
    if not recompute_all:
        return get_missing_parcels(db, county)

    electrical_coll = f"{county}ElectricalDB"
    unlinked = db[electrical_coll].count_documents({'parcel_id': {'$in': [None, '']}})
    parcels = {
        doc.get('parcel_id')
        for doc in db[electrical_coll].find({'parcel_id': {'$nin': [None, '']}},
                                            {'parcel_id': 1})
        if doc.get('parcel_id')
    }
    logger.info(f"Recompute mode: {len(parcels):,} parcel-linked electrical records")
    if unlinked:
        logger.info(f"Excluded {unlinked:,} electrical records with no parcel_id "
                    f"(unmatched utility accounts - see T-14)")
    return sorted(parcels, key=str)


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
    dropped = 0

    for i in range(len(dates) - 1):
        try:
            d1 = pd.to_datetime(dates[i])
            d2 = pd.to_datetime(dates[i + 1])
            kwh = time_series[dates[i]]

            if pd.isna(kwh) or kwh is None:
                continue

            span = (d2 - d1).days
            if not PERIOD_MIN_DAYS <= span <= PERIOD_MAX_DAYS:
                dropped += 1
                continue

            hl = weather.heating_load(d1, d2)
            cl = weather.cooling_load(d1, d2)

            billing_data.append({
                'date': dates[i],
                'days': int((d2 - d1).days),
                'kwh': float(kwh),
                'hl': hl,
                'cl': cl
            })
        except Exception as e:
            logger.debug(f"Error processing billing period {dates[i]}: {e}")
            continue

    if dropped:
        logger.debug(f"dropped {dropped} billing period(s) outside "
                     f"{PERIOD_MIN_DAYS}-{PERIOD_MAX_DAYS} days")

    if len(billing_data) < 3:
        return billing_data, {}

    model = fit_thermal_model(billing_data)
    if model:
        model['kwh_periods_dropped'] = dropped
    return billing_data, model


def fit_thermal_model(billing_data: List[Dict], per_day: bool = False) -> Dict:
    """Fit kWh against heating AND cooling degree-hours in one model.

    The previous code fit two separate univariate regressions against the same
    kWh series. In Ohio the cold months are exactly the months with no air
    conditioning, so heating and cooling degree-hours are near-perfect
    opposites: whichever driver was left out got absorbed by the other with the
    wrong sign. That is how 174,067 of 239,068 Franklin records (72.8%) ended up
    with a negative heating slope, and 36,445 (15.2%) with a negative cooling
    slope -- including gas-heated houses whose electricity is driven entirely by
    air conditioning.

    Fitting both terms together lets each driver claim its own share:

        kWh = intercept + kwh_hl_slope * heating_dh + kwh_cl_slope * cooling_dh

    A failed regression returns None plus a reason. It is never coerced to 0.0,
    because a genuine flat house also scores 0.0 and the two must stay
    distinguishable.
    """
    if len(billing_data) < 3:
        return {}

    df = pd.DataFrame(billing_data)
    marker = THERMAL_MODEL_PER_DAY if per_day else THERMAL_MODEL

    if per_day:
        # Degree-hours are integrated between meter readings and kWh is a period
        # total, so both scale with period length -- measured on real Franklin
        # histories, corr(days, heating degree-hours) is +0.916 and periods run
        # 29 to 641 days. Dividing through puts every period on a common daily
        # footing so the fit describes weather response, not billing calendars.
        if 'days' not in df.columns:
            raise ValueError("per-day fit needs a 'days' field on every billing period")
        df = df[df['days'] > 0]
        if len(df) < 3:
            return {}
        hl = df['hl'] / df['days']
        cl = df['cl'] / df['days']
        y = (df['kwh'] / df['days']).values
    else:
        hl, cl = df['hl'], df['cl']
        y = df['kwh'].values

    try:
        X = np.column_stack([hl.values, cl.values])
        model = LinearRegression().fit(X, y)
        return {
            'kwh_hl_slope': float(model.coef_[0]),
            'kwh_cl_slope': float(model.coef_[1]),
            'kwh_intercept': float(model.intercept_),
            'kwh_r2': float(r2_score(y, model.predict(X))),
            'kwh_model': marker,
            'kwh_periods': int(len(df)),
        }
    except Exception as exc:
        logger.debug(f"Thermal regression failed: {exc}")
        return {
            'kwh_hl_slope': None, 'kwh_cl_slope': None,
            'kwh_intercept': None, 'kwh_r2': None,
            'kwh_model': marker, 'kwh_periods': int(len(df)),
            'calculation_error': f"{type(exc).__name__}: {exc}",
        }


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


def build_thermal_document(parcel_id: str, billing_data: List[Dict], model: Dict,
                           weather_provenance: Optional[Dict] = None) -> Dict:
    """Assemble the electric half of a ThermalLoads document.

    Single-model schema: one heating coefficient, one cooling coefficient, one
    shared intercept, one r2. The legacy per-driver intercepts and r2 values are
    not written -- see LEGACY_SLOPE_FIELDS, which thermal_update_ops removes.

    Gas fields are deliberately absent. They are seeded only on insert, so a
    recompute cannot overwrite the 126,987 real gas regressions in Cuyahoga.
    """
    document = {
        'parcel_id': parcel_id,
        'kwh_hl_cl_loads': billing_data,
        'kwh_hl_slope': model.get('kwh_hl_slope'),
        'kwh_cl_slope': model.get('kwh_cl_slope'),
        'kwh_intercept': model.get('kwh_intercept'),
        'kwh_r2': model.get('kwh_r2'),
        'kwh_model': model.get('kwh_model', THERMAL_MODEL),
        'kwh_periods': model.get('kwh_periods', len(billing_data)),
        'kwh_periods_dropped': model.get('kwh_periods_dropped', 0),
        'calculated_at': datetime.now(),
        'calculation_source': 'calculate_missing_thermal_loads_tool.py',
    }
    if model.get('calculation_error'):
        document['calculation_error'] = model['calculation_error']
    if weather_provenance:
        document.update(weather_provenance)
    return document


def thermal_update_ops(document: Dict) -> Dict:
    """Build the update that replaces a parcel's electric slopes in place.

    Replace, never insert a second copy: the collections have no unique index
    (T-03) and Cuyahoga already carries 875 duplicate parcel_ids, so this is
    applied with update_many and every copy receives identical values.

    $set carries the electric fields only. $unset removes the superseded
    per-driver intercepts and r2. $setOnInsert seeds the gas sentinels, so a
    document that already holds real gas regressions keeps them.
    """
    body = {k: v for k, v in document.items() if k != 'parcel_id'}
    return {
        '$set': body,
        '$unset': {f: '' for f in LEGACY_SLOPE_FIELDS},
        '$setOnInsert': {
            # parcel_id is not listed: on an upsert MongoDB takes it from the
            # query filter, and naming it here as well invites a path conflict.
            'gas_hl_cl_loads': [],
            'gas_hl_slope': -1, 'gas_hl_intercept': -1, 'gas_hl_r2': -1,
            'gas_cl_slope': -1, 'gas_cl_intercept': -1, 'gas_cl_r2': -1,
        },
    }


def write_thermal_loads(db, county: str, parcel_id: str, billing_data: List[Dict],
                        model: Dict, dry_run: bool = False,
                        weather_provenance: Optional[Dict] = None) -> bool:
    """Replace a parcel's electric thermal loads in place.

    update_many, not insert_one: the collections carry no unique index on
    parcel_id (T-03) and Cuyahoga already holds 875 duplicates, so every copy of
    a parcel receives identical corrected values rather than a further duplicate
    being appended. upsert=True creates the record when the parcel is new.
    """
    thermal_coll = f"{county}ThermalLoads"
    document = build_thermal_document(parcel_id, billing_data, model, weather_provenance)

    if dry_run:
        return True

    try:
        db[thermal_coll].update_many({'parcel_id': parcel_id},
                                     thermal_update_ops(document), upsert=True)
        return True
    except Exception as exc:
        logger.error(f"Failed to write {parcel_id}: {exc}")
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
    parser.add_argument('--recompute-all', action='store_true',
                        help='Recompute every parcel-linked record, not only missing ones '
                             '(the single-model migration mode)')
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
    if args.recompute_all:
        print("\n  Selecting every parcel-linked record for recomputation...", flush=True)
    else:
        print("\n  Identifying parcels missing thermal data...", flush=True)
    missing_parcels = get_target_parcels(db, args.county, args.recompute_all)

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

        if write_thermal_loads(db, args.county, parcel_id, billing_data, slope_data,
                               args.dry_run, weather_provenance):
            stats['success'] += 1
            if args.verbose:
                hl = slope_data.get('kwh_hl_slope')
                cl = slope_data.get('kwh_cl_slope')
                r2 = slope_data.get('kwh_r2')
                if hl is None:
                    print(f"✗ regression error: {slope_data.get('calculation_error')}")
                else:
                    print(f"✓ heat={hl:+.4f} cool={cl:+.4f} R²={r2:.3f}")
        else:
            stats['failed'] += 1
            if args.verbose:
                print("✗ write failed")

    # Print summary
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    label = "Total target parcels:" if args.recompute_all else "Total missing parcels:"
    print(f"\n  {label:<26}{len(missing_parcels):,}")
    print(f"  Processed:                {stats['processed']:,}")
    print(f"  Successfully calculated:  {stats['success']:,}")
    print(f"  Insufficient data:        {stats['insufficient_data']:,}")
    print(f"  Failed writes:            {stats['failed']:,}")

    if args.dry_run:
        print("\n  [DRY RUN - No changes were made to database]")
    else:
        print(f"\n  {stats['success']:,} records written to {args.county}ThermalLoads "
              f"(model {THERMAL_MODEL})")

    print("\n" + "=" * 70)
    print("  COMPLETE")
    print("=" * 70 + "\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
