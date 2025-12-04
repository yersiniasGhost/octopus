"""
Bayesian Models for Email Engagement Prediction

This package contains hierarchical Bayesian models for predicting
email engagement (opens and clicks) based on energy burden, demographics,
and property characteristics.

Available Models:
- Model 1: Baseline (cost + savings)
- Model 2: Energy Burden (primary hypothesis)
- Model 3-10: Progressive complexity (see MODEL_PROGRESSION_SUMMARY.md)
"""

from .model_01_baseline import BaselineOpenModel
from .model_02_energy_burden import EnergyBurdenOpenModel

__all__ = [
    'BaselineOpenModel',
    'EnergyBurdenOpenModel',
]

__version__ = '0.1.0'
