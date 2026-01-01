"""
Bayesian Models for Email Engagement Prediction

This package contains hierarchical Bayesian models for predicting
email engagement (opens and clicks) based on energy burden, demographics,
and property characteristics.

Directory Structure:
    {model_id}/           - Model directory with registry support
        config.yaml       - Metadata and inference parameters
        model.py          - Model implementation (extends BaseBayesianModel)
        __init__.py       - Package exports

Use the model_registry to discover and load models:
    from src.bayesian_models.model_registry import get_registry
    registry = get_registry()
    model = registry.load_model_instance('model_01_baseline')

Available Models (with config.yaml):
- model_01_baseline: Baseline Email Open Model
- model_02_energy_burden: Energy Burden Email Open Model
- model_03_demographics: Demographics Email Open Model (with kWh usage)
- click_model: Campaign Click Probability Model
- click_model_02: Enhanced Click Model

Legacy Models (standalone files, not registry-compatible):
- messaging_effectiveness_model.py
"""

# Don't auto-import models to avoid dependency issues
# Models are loaded dynamically through the registry

from .base_model import BaseBayesianModel, ModelMetadata, InferenceParameter
from .model_registry import get_registry, ModelRegistry

__all__ = [
    'BaseBayesianModel',
    'ModelMetadata',
    'InferenceParameter',
    'get_registry',
    'ModelRegistry',
]

__version__ = '0.2.0'
