"""
Model 05: Click Rate by Energy Cost × Income Category

A Bayesian hierarchical model for predicting click-through rates using
energy cost and income category as separate predictors with interaction.

Key Features:
- Varying slopes for energy cost effect by income category
- Hierarchical partial pooling across 10 income categories
- Implicit modeling of energy burden without discretization losses

Usage:
    from src.bayesian_models.model_05_rate_energy_income import ClickRateEnergyIncomeModel

    model = ClickRateEnergyIncomeModel()
    data = model.load_data()
    results = model.train(data)
    prediction = model.predict({'income_category': '3', 'energy_cost': 150})
"""

from .model import ClickRateEnergyIncomeModel, INCOME_CATEGORY_LABELS, N_INCOME_CATEGORIES

__all__ = [
    'ClickRateEnergyIncomeModel',
    'INCOME_CATEGORY_LABELS',
    'N_INCOME_CATEGORIES'
]
