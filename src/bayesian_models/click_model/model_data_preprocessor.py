"""
Click Model Data Preprocessor
=============================

Preprocessor that standardizes variables for Bayesian modeling.
Standardization enables interpretable priors and efficient MCMC sampling.
"""

from typing import Dict
import numpy as np
from .model_data import ClickModelData


# =============================================================================
# DATA PREPROCESSING
# =============================================================================

class DataPreprocessor:
    """
    Preprocessor that standardizes variables for modeling.

    Standardization is crucial for:
    1. Interpretable priors (we can use the same prior for all β coefficients)
    2. Efficient MCMC sampling (similar scales help the sampler)
    3. Meaningful coefficient comparison (all on same scale)

    Stores transformation parameters for later use in prediction.
    """

    def __init__(self):
        self.age_mean: float = None
        self.age_std: float = None
        self.income_mean: float = None
        self.income_std: float = None
        self.eb_mean: float = None
        self.eb_std: float = None
        self._fitted = False

    def fit(self, data: ClickModelData) -> 'DataPreprocessor':
        """
        Compute standardization parameters from training data.

        Parameters
        ----------
        data : ClickModelData
            Training data to compute means and standard deviations

        Returns
        -------
        self
            Fitted preprocessor
        """
        # Age is optional - may not be available in real data
        if data.age is not None:
            self.age_mean = data.age.mean()
            self.age_std = data.age.std()
        else:
            self.age_mean = None
            self.age_std = None

        self.income_mean = data.income.mean()
        self.income_std = data.income.std()
        self.eb_mean = data.energy_burden.mean()
        self.eb_std = data.energy_burden.std()
        self._fitted = True

        print(f"Preprocessor fitted:")
        if self.age_mean is not None:
            print(f"  Age: μ={self.age_mean:.1f}, σ={self.age_std:.1f}")
        else:
            print(f"  Age: not available")
        print(f"  Income: μ=${self.income_mean:,.0f}, σ=${self.income_std:,.0f}")
        print(f"  Energy Burden: μ={self.eb_mean:.1f}%, σ={self.eb_std:.1f}%")

        return self

    def transform(self, data: ClickModelData) -> Dict[str, np.ndarray]:
        """
        Transform data to standardized scale.

        Parameters
        ----------
        data : ClickModelData
            Data to transform

        Returns
        -------
        dict
            Dictionary with standardized variables ready for PyMC
        """
        if not self._fitted:
            raise ValueError("Preprocessor not fitted. Call fit() first.")

        result = {
            'income_std': (data.income - self.income_mean) / self.income_std,
            'eb_std': (data.energy_burden - self.eb_mean) / self.eb_std,
            'click': data.click
        }
        # Age is optional
        if data.age is not None and self.age_mean is not None:
            result['age_std'] = (data.age - self.age_mean) / self.age_std
        else:
            result['age_std'] = None
        return result

    def fit_transform(self, data: ClickModelData) -> Dict[str, np.ndarray]:
        """Fit and transform in one step."""
        return self.fit(data).transform(data)

    def transform_new(self, age: float, income: float, energy_burden: float) -> Dict[str, float]:
        """
        Transform new observation(s) for prediction.

        Parameters
        ----------
        age : float or array, optional
            Age in years (can be None if age not used in model)
        income : float or array
            Income in dollars
        energy_burden : float or array
            Energy burden as percentage

        Returns
        -------
        dict
            Standardized values
        """
        if not self._fitted:
            raise ValueError("Preprocessor not fitted. Call fit() first.")

        result = {
            'income_std': (income - self.income_mean) / self.income_std,
            'eb_std': (energy_burden - self.eb_mean) / self.eb_std
        }

        # Age is optional
        if age is not None and self.age_mean is not None:
            result['age_std'] = (age - self.age_mean) / self.age_std
        else:
            result['age_std'] = None

        return result
