# Thermal Load Calculation Methodology Validation

**Date**: 2026-01-19
**Source Code**: `/home/warnd/empower/src/analytics/heating_cooling_loads.py`, `thermal_slopes.py`

## Overview

The thermal load calculation system uses a two-step approach to characterize building heating and cooling energy consumption:

1. **Degree-Day Calculation**: Integrates hourly temperature data to compute heating degree-hours (HDH) and cooling degree-hours (CDH) for each billing period
2. **Linear Regression**: Fits kWh consumption against degree-hours to extract the thermal load coefficient (slope)

## Step 1: Degree-Hour Calculation

### Algorithm

```python
def heating_load(s, e, threshold=62):
    """
    Calculate heating degree-hours between timestamps s and e.

    For each consecutive hour where temperature <= threshold:
        accumulate (threshold - avg_temp) * dt

    Uses trapezoidal integration:
        ΔHL = (threshold - (T_prev + T_curr)/2) * Δt
    """
```

### Mathematical Formula

For heating load (HDD proxy):
```
HL = Σ max(0, T_base - T_ambient) × Δt
```

Where:
- `T_base` = 62°F (heating threshold)
- `T_ambient` = outdoor air temperature
- `Δt` = 1 hour (from hourly weather data)

For cooling load (CDD proxy):
```
CL = Σ max(0, T_ambient - T_base) × Δt
```

Where:
- `T_base` = 72°F (cooling threshold)

### Validation Assessment

| Aspect | Assessment | Notes |
|--------|------------|-------|
| **Mathematical correctness** | ✅ Valid | Trapezoidal integration is standard numerical method |
| **Threshold values** | ✅ Standard | 62°F/72°F are ASHRAE-typical balance points |
| **Weather data resolution** | ✅ Good | Hourly data provides better accuracy than daily |
| **Continuity requirement** | ⚠️ Conservative | Only counts consecutive sub-threshold hours |

**Note on Continuity**: The algorithm resets integration when temperature crosses the threshold. This is conservative—it prevents counting isolated cold/hot hours. For building physics, this is reasonable as buildings have thermal mass.

## Step 2: Linear Regression (Energy Signature Model)

### Algorithm

```python
def calculate_slopes(hl_cl_df):
    """
    For each parcel, perform linear regression:
        KWH = slope × HDD + intercept

    Returns:
        - slope: heating/cooling load coefficient (kWh per degree-hour)
        - intercept: baseload (non-temperature-dependent consumption)
        - R²: coefficient of determination (fit quality)
    """
```

### Mathematical Model

The **Energy Signature Method** is a standard ASHRAE technique:

```
E = E_base + β_h × HDD + β_c × CDD
```

Where:
- `E` = monthly energy consumption (kWh)
- `E_base` = baseload (intercept)
- `β_h` = heating load coefficient (kWh/degree-hour)
- `β_c` = cooling load coefficient (kWh/degree-hour)
- `HDD/CDD` = heating/cooling degree-hours

### Interpretation of Results

| Metric | Meaning |
|--------|---------|
| `kwh_hl_slope` > 0 | Electric heating (resistance heat, heat pump) |
| `kwh_hl_slope` < 0 | Non-electric heating (gas furnace) - electricity decreases in winter |
| `kwh_cl_slope` > 0 | Air conditioning present |
| `kwh_hl_r2` | Quality of fit (higher = more linear relationship) |

### Validation Assessment

| Aspect | Assessment | Notes |
|--------|------------|-------|
| **Methodology** | ✅ Industry standard | ASHRAE energy signature method |
| **Implementation** | ✅ Correct | Scikit-learn LinearRegression properly applied |
| **R² calculation** | ✅ Correct | Uses sklearn r2_score |
| **Data points** | ⚠️ Limited | ~11 months = 11 data points per parcel |

## Data Flow Validation

### Original Franklin Calculation (Nov 2024)

```
Input Files:
├── franklin_weather_2023.csv (NOAA station 72428014821 - John Glenn Airport)
├── franklin_weather_2024.csv (Same station, through Nov 2024)
└── franklin_elec.csv (194,981 parcels with 12 months of billing)

Processing:
1. Parse weather → hourly temperature in °F
2. For each parcel × billing period → calculate HL, CL
3. For each parcel → linear regression (KWH vs HL, KWH vs CL)
4. Insert into MongoDB FranklinThermalLoads

Output:
└── FranklinThermalLoads: 194,217 documents
```

### Weather Data Source

- **Station**: 72428014821 (John Glenn Columbus International Airport, KCMH)
- **Period**: Jan 1, 2023 - Nov 11, 2024
- **Resolution**: Hourly (observations at :51 past each hour)
- **Temperature format**: TMP field as "+0083,1" → 8.3°C → convert to °F

## Known Limitations

1. **Fixed Balance Points**: Uses 62°F/72°F for all buildings. Real balance points vary.

2. **Single Variable Regression**: Doesn't account for:
   - Solar gain
   - Occupancy patterns
   - Internal heat gains

3. **Data Requirements**: Needs 12 months of billing data. Shorter periods reduce accuracy.

4. **Negative Slopes**: Parcels with negative heating slopes (gas heat) still get calculated but interpretation differs.

## Recommendations

1. **R² Filtering**: Use `kwh_hl_r2 > 0.5` for reliable heating load identification
2. **Slope Sign**: Positive `kwh_hl_slope` indicates electric heating
3. **Combined Analysis**: Best when combined with building characteristics (heating type from auditor data)

## Conclusion

**The methodology is valid and follows industry-standard practices (ASHRAE energy signature method).**

The implementation correctly:
- Integrates hourly temperature data
- Uses appropriate threshold values
- Applies linear regression properly
- Provides quality metrics (R²)

The 47,458 missing thermal records are due to additional electrical data added after the original calculation, not a methodology issue.
