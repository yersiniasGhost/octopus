"""
Click Model Package
===================

Bayesian click-through rate model for email campaign engagement prediction.

This package provides:
- ClickModel: Bayesian logistic regression for click prediction
- SegmentPredictor: Generate predictions for demographic segments
- ClickModelData: Data container for model input
- DataPreprocessor: Standardization for Bayesian modeling
- Segment definitions for common demographic profiles

Usage:
    from src.bayesian_models.click_model import ClickModel, SegmentPredictor, load_data
    from src.bayesian_models.click_model.segments import DEFAULT_SEGMENTS

    # Load data
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
from .segments import DEFAULT_SEGMENTS, INCOME_FOCUSED_SEGMENTS, ENERGY_BURDEN_FOCUSED_SEGMENTS

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
]
