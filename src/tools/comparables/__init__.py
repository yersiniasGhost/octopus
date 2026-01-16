"""
Comparable Residence Finder Tools

Tools for finding comparable residences based on property characteristics,
demographics, and energy consumption patterns.

Usage:
    from src.tools.comparables import ComparableFinder, EnergyPercentileCalculator

    # Find similar properties
    finder = ComparableFinder(db, county='FranklinCounty')
    comparables = finder.find_comparables(
        parcel_id='12345',
        n_results=10,
        filters=ComparableFilters(
            same_zip=True,
            story_height_tolerance=0.5,
            sqft_tolerance=500
        )
    )

    # Calculate energy percentile
    calculator = EnergyPercentileCalculator(db, county='Franklin')
    result = calculator.calculate_percentile(parcel_id='010-000002-00')
    print(f"Uses more electricity than {result.percentile_rank:.1f}% of comparable homes")
"""
from .finder import ComparableFinder
from .filters import ComparableFilters
from .models import ComparableResult, ComparableScore
from .percentile import EnergyPercentileCalculator, PercentileResult, TieredFilterConfig

__all__ = [
    'ComparableFinder',
    'ComparableFilters',
    'ComparableResult',
    'ComparableScore',
    'EnergyPercentileCalculator',
    'PercentileResult',
    'TieredFilterConfig'
]
