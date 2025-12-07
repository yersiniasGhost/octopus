"""
Click Model 02 Segment Definitions
==================================

Predefined demographic segments for click model analysis and predictions.
These segments represent typical customer profiles for energy program targeting.

Version 02 adds house_age as a required field in all segments.

Usage:
    from src.bayesian_models.click_model_02.segments import DEFAULT_SEGMENTS, get_segment_by_name

    predictor.compare_segments(DEFAULT_SEGMENTS)
"""

from typing import Dict, List, Optional


# =============================================================================
# DEFAULT SEGMENT DEFINITIONS
# =============================================================================

# Typical house ages by segment:
# - Older homes (50+ years): Built before 1975, often less energy efficient
# - Middle-age homes (25-50 years): Built 1975-2000
# - Newer homes (<25 years): Built after 2000, better insulation/efficiency

DEFAULT_SEGMENTS: List[Dict] = [
    {
        'name': 'Low Income, High Burden, Older Home',
        'income': 25000,
        'energy_burden': 20,
        'house_age': 55,
        'description': 'Low-income in older, less efficient homes'
    },
    {
        'name': 'Low Income, Low Burden, Newer Home',
        'income': 25000,
        'energy_burden': 5,
        'house_age': 15,
        'description': 'Low-income in newer, efficient homes'
    },
    {
        'name': 'Middle Income, Average, Mid-Age Home',
        'income': 50000,
        'energy_burden': 10,
        'house_age': 35,
        'description': 'Middle-income in typical mid-age homes'
    },
    {
        'name': 'High Income, High Burden, Older Home',
        'income': 75000,
        'energy_burden': 15,
        'house_age': 60,
        'description': 'Higher-income in older homes with high energy costs'
    },
    {
        'name': 'High Income, Low Burden, Newer Home',
        'income': 75000,
        'energy_burden': 5,
        'house_age': 10,
        'description': 'Higher-income in newer, efficient homes'
    },
]


# Alternative segment definitions for different analysis scenarios

INCOME_FOCUSED_SEGMENTS: List[Dict] = [
    {'name': 'Very Low Income', 'income': 20000, 'energy_burden': 12, 'house_age': 40},
    {'name': 'Low Income', 'income': 35000, 'energy_burden': 12, 'house_age': 40},
    {'name': 'Middle Income', 'income': 55000, 'energy_burden': 12, 'house_age': 40},
    {'name': 'Upper Middle Income', 'income': 80000, 'energy_burden': 12, 'house_age': 40},
    {'name': 'High Income', 'income': 120000, 'energy_burden': 12, 'house_age': 40},
]


ENERGY_BURDEN_FOCUSED_SEGMENTS: List[Dict] = [
    {'name': 'Very Low Burden (2%)', 'income': 50000, 'energy_burden': 2, 'house_age': 35},
    {'name': 'Low Burden (5%)', 'income': 50000, 'energy_burden': 5, 'house_age': 35},
    {'name': 'Average Burden (10%)', 'income': 50000, 'energy_burden': 10, 'house_age': 35},
    {'name': 'High Burden (15%)', 'income': 50000, 'energy_burden': 15, 'house_age': 35},
    {'name': 'Very High Burden (25%)', 'income': 50000, 'energy_burden': 25, 'house_age': 35},
]


# NEW: Segments focused on house age variations
HOUSE_AGE_FOCUSED_SEGMENTS: List[Dict] = [
    {'name': 'New Construction (<10 years)', 'income': 50000, 'energy_burden': 10, 'house_age': 5},
    {'name': 'Recent Build (10-25 years)', 'income': 50000, 'energy_burden': 10, 'house_age': 18},
    {'name': 'Mid-Age Home (25-40 years)', 'income': 50000, 'energy_burden': 10, 'house_age': 32},
    {'name': 'Older Home (40-60 years)', 'income': 50000, 'energy_burden': 10, 'house_age': 50},
    {'name': 'Historic Home (60+ years)', 'income': 50000, 'energy_burden': 10, 'house_age': 75},
]


# Segments with owner age (for use when owner age data is available)
SEGMENTS_WITH_OWNER_AGE: List[Dict] = [
    {'name': 'Young Owner, Older Home', 'age': 30, 'income': 35000, 'energy_burden': 15, 'house_age': 50},
    {'name': 'Young Owner, Newer Home', 'age': 30, 'income': 80000, 'energy_burden': 3, 'house_age': 10},
    {'name': 'Middle Age Owner, Mid-Age Home', 'age': 45, 'income': 55000, 'energy_burden': 6, 'house_age': 30},
    {'name': 'Senior Owner, Older Home', 'age': 70, 'income': 45000, 'energy_burden': 12, 'house_age': 55},
    {'name': 'Senior Owner, Newer Home', 'age': 70, 'income': 90000, 'energy_burden': 3, 'house_age': 15},
]


# =============================================================================
# SEGMENT UTILITIES
# =============================================================================

def get_segment_by_name(name: str, segment_list: List[Dict] = None) -> Optional[Dict]:
    """
    Find a segment by name (case-insensitive).

    Parameters
    ----------
    name : str
        Segment name to search for
    segment_list : List[Dict], optional
        List of segments to search (default: DEFAULT_SEGMENTS)

    Returns
    -------
    Dict or None
        Matching segment or None if not found
    """
    if segment_list is None:
        segment_list = DEFAULT_SEGMENTS

    name_lower = name.lower()
    for seg in segment_list:
        if seg['name'].lower() == name_lower:
            return seg
    return None


def create_segment(name: str, income: float, energy_burden: float, house_age: float,
                   owner_age: float = None, description: str = None) -> Dict:
    """
    Create a new segment definition.

    Parameters
    ----------
    name : str
        Segment display name
    income : float
        Annual income in dollars
    energy_burden : float
        Energy burden as percentage of income
    house_age : float
        Age of house in years (required for click_model_02)
    owner_age : float, optional
        Owner age in years (only used if model includes owner age)
    description : str, optional
        Description of the segment

    Returns
    -------
    Dict
        Segment definition ready for use with SegmentPredictor
    """
    segment = {
        'name': name,
        'income': income,
        'energy_burden': energy_burden,
        'house_age': house_age,
    }
    if owner_age is not None:
        segment['age'] = owner_age
    if description is not None:
        segment['description'] = description
    return segment


def create_comparison_pair(base_segment: Dict, varied_param: str, values: List) -> List[Dict]:
    """
    Create a list of segments varying one parameter from a base segment.

    Parameters
    ----------
    base_segment : Dict
        Base segment to vary from
    varied_param : str
        Parameter to vary ('income', 'energy_burden', 'house_age', or 'age')
    values : List
        Values for the varied parameter

    Returns
    -------
    List[Dict]
        List of segment definitions
    """
    segments = []
    for val in values:
        seg = base_segment.copy()
        seg[varied_param] = val
        seg['name'] = f"{varied_param}={val}"
        segments.append(seg)
    return segments
