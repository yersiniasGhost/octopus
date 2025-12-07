"""
Click Model 02 Package
======================

Bayesian click-through rate model for email campaign engagement prediction.
Version 02 adds house_age (year built) as a predictor variable.

This package provides:
- ClickModel: Bayesian logistic regression with income, energy_burden, and house_age
- SegmentPredictor: Generate predictions for demographic segments
- ClickModelData: Data container with house_age field
- DataPreprocessor: Standardization for Bayesian modeling
- Segment definitions including house age profiles

Usage:
    from src.bayesian_models.click_model_02 import ClickModel, SegmentPredictor, load_data
    from src.bayesian_models.click_model_02.segments import DEFAULT_SEGMENTS

    # Load data (includes house age from Residential collection)
    data = load_data()

    # Build and fit model
    model = ClickModel()
    model.build_model(data)
    trace = model.fit()

    # Make predictions
    predictor = SegmentPredictor(model)
    comparison = predictor.compare_segments(DEFAULT_SEGMENTS)
"""

from .model import ClickModel, SegmentPredictor
from .model_data import ClickModelData, load_data, diagnose_match_coverage
from .model_data_preprocessor import DataPreprocessor
from .segments import (
    DEFAULT_SEGMENTS,
    INCOME_FOCUSED_SEGMENTS,
    ENERGY_BURDEN_FOCUSED_SEGMENTS,
    HOUSE_AGE_FOCUSED_SEGMENTS,
    SEGMENTS_WITH_OWNER_AGE,
)

__all__ = [
    # Core model classes
    'ClickModel',
    'SegmentPredictor',
    'DataPreprocessor',

    # Data classes and functions
    'ClickModelData',
    'load_data',
    'diagnose_match_coverage',

    # Segment definitions
    'DEFAULT_SEGMENTS',
    'INCOME_FOCUSED_SEGMENTS',
    'ENERGY_BURDEN_FOCUSED_SEGMENTS',
    'HOUSE_AGE_FOCUSED_SEGMENTS',
    'SEGMENTS_WITH_OWNER_AGE',
]
