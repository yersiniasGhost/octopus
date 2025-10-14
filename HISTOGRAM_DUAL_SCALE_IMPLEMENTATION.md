# Savings Distribution Histogram - Dual Scale Implementation

## Overview
Updated the Savings Distribution histogram to display **full participant counts** from the exports CSV data with dual y-axes for better visualization of the scale differences between total participants and opened emails.

## Changes Implemented

### Backend Changes (`app/routes/campaigns.py`)

#### 1. Added Exports Data Directory Path
```python
EXPORTS_DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'exports'
```

#### 2. Rewrote Histogram API Endpoint
- **Endpoint**: `/api/campaigns/<campaign_id>/savings-histogram`
- **Data Sources**:
  - **Total Participants**: Read from `data/exports/campaign_{id}_*.csv` (full campaign export)
  - **Opened Participants**: Read from `data/enriched/enriched_campaign_{id}_*.csv` (only opened emails)

#### 3. New Data Processing Logic
- Reads all participants from exports CSV for accurate total counts
- Reads only opened participants from enriched CSV
- Creates 10 bins based on min/max savings from ALL participants
- Populates both datasets into the same bins for comparison

### Frontend Changes (`app/templates/campaigns/detail.html`)

#### 1. Dual Y-Axes Configuration
- **Left Axis (Blue)**: Total Participants - larger scale
- **Right Axis (Green)**: Opened Email - smaller scale
- Color-coded axis labels matching dataset colors
- Independent scaling for each dataset

#### 2. Chart.js Configuration Updates
```javascript
yAxisID: 'y-total'  // Total participants dataset
yAxisID: 'y-opened' // Opened participants dataset
```

#### 3. Enhanced Visualization
- Grid lines only on left axis to avoid clutter
- Color-matched axis titles and tick labels
- Tooltips show percentage for opened emails
- Better interaction mode for hovering over bins

#### 4. Updated Description Text
Changed from "distribution of participants" to "distribution of **all campaign participants**" to clarify full dataset usage.

## Data Verification

### Test Campaign: `02b5a71e-31be-11f0-b6ca-052d9a1dc34e` (OHCAC Daily Cost)

**Data Counts**:
- Total participants: 1,972 (from exports CSV)
- Opened participants: 89 (from enriched CSV)
- Open rate: 4.5%

**Savings Range**:
- Minimum: $511.47
- Maximum: $2,381.40

**Bin Distribution Example**:
```
Bin 1:  $511-$698   | Total:  888 | Opened:  45
Bin 2:  $698-$885   | Total:  483 | Opened:  20
Bin 3:  $885-$1072  | Total:  309 | Opened:  11
Bin 4:  $1072-$1259 | Total:  150 | Opened:   7
Bin 5:  $1259-$1446 | Total:   81 | Opened:   1
Bin 6:  $1446-$1633 | Total:   33 | Opened:   1
Bin 7:  $1633-$1820 | Total:   15 | Opened:   3
Bin 8:  $1820-$2007 | Total:    8 | Opened:   1
Bin 9:  $2007-$2194 | Total:    4 | Opened:   0
Bin 10: $2194-$2381 | Total:    1 | Opened:   0
```

## Key Benefits

### 1. Accurate Representation
- Shows **all** campaign participants, not just those who opened
- Provides true picture of savings distribution across entire campaign

### 2. Better Visualization
- Dual scales prevent small "opened" bars from being invisible
- Each dataset has appropriate scale for its magnitude
- Easy to compare both metrics at a glance

### 3. Data Integrity
- Reads from authoritative source (exports CSV) for total counts
- Maintains opened data from enriched CSV for engagement tracking
- Consistent binning algorithm across both datasets

## Usage

Navigate to any campaign detail page:
```
/campaigns/<campaign_id>
```

Click the **"Savings Distribution"** tab to view the updated histogram with:
- Full participant counts (blue bars, left axis)
- Opened email counts (green bars, right axis)
- Summary statistics showing total participants, savings range, and open rate

## Technical Details

### File Naming Patterns
- **Exports**: `campaign_{campaign_id}_{campaign_name}.csv`
- **Enriched**: `enriched_campaign_{campaign_id}_{campaign_name}.csv`

### CSV Column Mapping
Both files use `annual_savings` column with format: `"$2,002.41"`

### Error Handling
- Returns 404 if exports file not found
- Gracefully handles missing enriched file (opened count = 0)
- Validates savings data parsing and skips invalid rows

## Performance Considerations
- Lazy loading: Chart only renders when tab is clicked
- Efficient CSV parsing with single pass
- Client-side caching: Data loaded once per session
- Separate data processing for total and opened datasets

## Future Enhancements
- Add filter for date ranges
- Export histogram data as CSV
- Add more statistical metrics (median, percentiles)
- Interactive bin selection for detailed participant lists
