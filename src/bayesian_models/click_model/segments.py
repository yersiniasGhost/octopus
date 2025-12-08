"""
Click Model Segment Definitions
===============================

Predefined demographic segments for click model analysis and predictions.
These segments represent typical customer profiles for energy program targeting.

Usage:
    from src.bayesian_models.click_model.segments import DEFAULT_SEGMENTS, get_segment_by_name

    predictor.compare_segments(DEFAULT_SEGMENTS)
"""

from typing import Dict, List, Optional


# =============================================================================
# DEFAULT SEGMENT DEFINITIONS
# =============================================================================

DEFAULT_SEGMENTS: List[Dict] = [
    {
        'name': 'Low Income, High Energy Burden',
        'income': 25000,
        'energy_burden': 20,
        'description': 'Low-income households with high energy costs relative to income'
    },
    {
        'name': 'Low Income, Low Energy Burden',
        'income': 25000,
        'energy_burden': 5,
        'description': 'Low-income households with efficient energy usage'
    },
    {
        'name': 'Middle Income, Average',
        'income': 50000,
        'energy_burden': 10,
        'description': 'Middle-income households with typical energy burden'
    },
    {
        'name': 'High Income, High Energy Burden',
        'income': 75000,
        'energy_burden': 15,
        'description': 'Higher-income households with above-average energy costs'
    },
    {
        'name': 'High Income, Low Energy Burden',
        'income': 75000,
        'energy_burden': 5,
        'description': 'Higher-income households with efficient energy usage'
    },
]


# Alternative segment definitions for different analysis scenarios

INCOME_FOCUSED_SEGMENTS: List[Dict] = [
    {'name': 'Very Low Income', 'income': 20000, 'energy_burden': 12},
    {'name': 'Low Income', 'income': 35000, 'energy_burden': 12},
    {'name': 'Middle Income', 'income': 55000, 'energy_burden': 12},
    {'name': 'Upper Middle Income', 'income': 80000, 'energy_burden': 12},
    {'name': 'High Income', 'income': 120000, 'energy_burden': 12},
]


ENERGY_BURDEN_FOCUSED_SEGMENTS: List[Dict] = [
    {'name': 'Very Low Burden (2%)', 'income': 50000, 'energy_burden': 2},
    {'name': 'Low Burden (5%)', 'income': 50000, 'energy_burden': 5},
    {'name': 'Average Burden (10%)', 'income': 50000, 'energy_burden': 10},
    {'name': 'High Burden (15%)', 'income': 50000, 'energy_burden': 15},
    {'name': 'Very High Burden (25%)', 'income': 50000, 'energy_burden': 25},
]


# Segments with age (for future use when age data is available)
SEGMENTS_WITH_AGE: List[Dict] = [
    {'name': 'Young, High Energy Burden', 'age': 30, 'income': 35000, 'energy_burden': 15},
    {'name': 'Young, Low Energy Burden', 'age': 30, 'income': 80000, 'energy_burden': 3},
    {'name': 'Middle Age, Average', 'age': 45, 'income': 55000, 'energy_burden': 6},
    {'name': 'Senior, High Energy Burden', 'age': 70, 'income': 45000, 'energy_burden': 12},
    {'name': 'Senior, Low Energy Burden', 'age': 70, 'income': 90000, 'energy_burden': 3},
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


def create_segment(name: str, income: float, energy_burden: float,
                   age: float = None, description: str = None) -> Dict:
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
    age : float, optional
        Age in years (only used if model includes age)
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
    }
    if age is not None:
        segment['age'] = age
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
        Parameter to vary ('income', 'energy_burden', or 'age')
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
