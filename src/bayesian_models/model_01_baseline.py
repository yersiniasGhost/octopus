"""
Model 1: Baseline Engagement Model

Predicts email opens based on:
- Annual energy cost
- Annual savings potential

This is the simplest model to establish baseline predictive performance
before adding energy burden and demographic confounders.

Research Question:
"Does energy cost and savings potential predict email open rates?"
"""

import numpy as np
import pymc as pm
import arviz as az
from typing import Dict, Optional
import matplotlib.pyplot as plt


class BaselineOpenModel:
    """Model 1: Baseline logistic regression for email opens."""

    def __init__(self, name: str = "Model_1_Baseline_Open"):
        """Initialize the model."""
        self.name = name
        self.model = None
        self.trace = None

    def build_model(self, data: Dict[str, np.ndarray]) -> pm.Model:
        """
        Build the PyMC model.

        Args:
            data: Dictionary with keys:
                - 'annual_cost': Annual energy cost (scaled)
                - 'annual_savings': Annual savings potential (scaled)
                - 'y_opened': Binary outcome (0/1)

        Returns:
            PyMC Model object
        """
        with pm.Model() as model:
            # Data containers (PyMC v5 API)
            annual_cost = pm.Data("annual_cost", data['annual_cost'])
            annual_savings = pm.Data("annual_savings", data['annual_savings'])

            # Priors
            # Intercept: weakly informative prior centered at 0
            # (logit scale, so exp(0) = 0.5 probability)
            α = pm.Normal("intercept", mu=0, sigma=2)

            # Coefficients: weakly informative priors
            # Expected positive effect of savings, uncertain effect of cost
            β_cost = pm.Normal("beta_cost", mu=0, sigma=1)
            β_savings = pm.Normal("beta_savings", mu=0, sigma=1)

            # Linear model (logit scale)
            logit_p = α + β_cost * annual_cost + β_savings * annual_savings

            # Likelihood
            y = pm.Bernoulli("y_open", logit_p=logit_p, observed=data['y_opened'])

        self.model = model
        return model

    def fit(self,
           data: Dict[str, np.ndarray],
           draws: int = 2000,
           tune: int = 1000,
           chains: int = 4,
           target_accept: float = 0.95,
           random_seed: int = 42) -> az.InferenceData:
        """
        Fit the model using MCMC sampling.

        Args:
            data: Data dictionary
            draws: Number of posterior samples per chain
            tune: Number of tuning/burn-in samples
            chains: Number of MCMC chains
            target_accept: Target acceptance rate
            random_seed: Random seed for reproducibility

        Returns:
            ArviZ InferenceData object with trace
        """
        if self.model is None:
            self.build_model(data)

        print(f"\n{'='*60}")
        print(f"Fitting {self.name}")
        print(f"{'='*60}")
        print(f"Observations: {len(data['y_opened'])}")
        print(f"Open rate: {data['y_opened'].mean():.2%}")
        print(f"Sampling: {draws} draws × {chains} chains (tune={tune})")
        print(f"{'='*60}\n")

        with self.model:
            self.trace = pm.sample(
                draws=draws,
                tune=tune,
                chains=chains,
                target_accept=target_accept,
                random_seed=random_seed,
                return_inferencedata=True,
            )

            # Add posterior predictive samples
            print("\nGenerating posterior predictive samples...")
            pm.sample_posterior_predictive(
                self.trace,
                extend_inferencedata=True,
                random_seed=random_seed,
            )

        print("✅ Sampling complete!")
        return self.trace

    def summarize(self, hdi_prob: float = 0.95) -> None:
        """
        Print model summary with coefficient interpretations.

        Args:
            hdi_prob: Probability for HDI intervals
        """
        if self.trace is None:
            raise ValueError("Model must be fit before summarizing")

        print(f"\n{'='*60}")
        print(f"{self.name} - SUMMARY")
        print(f"{'='*60}\n")

        # Extract summary statistics
        summary = az.summary(
            self.trace,
            var_names=["intercept", "beta_cost", "beta_savings"],
            hdi_prob=hdi_prob
        )

        print(summary)

        # Interpret coefficients on odds ratio scale
        print(f"\n{'='*60}")
        print("COEFFICIENT INTERPRETATION (Odds Ratios)")
        print(f"{'='*60}\n")

        for var in ['beta_cost', 'beta_savings']:
            mean_coef = summary.loc[var, 'mean']
            lower_ci = summary.loc[var, f'hdi_{(1-hdi_prob)/2*100:.1f}%']
            upper_ci = summary.loc[var, f'hdi_{100-(1-hdi_prob)/2*100:.1f}%']

            or_mean = np.exp(mean_coef)
            or_lower = np.exp(lower_ci)
            or_upper = np.exp(upper_ci)

            effect_pct = (or_mean - 1) * 100

            print(f"{var}:")
            print(f"  Coefficient: {mean_coef:.3f} [{lower_ci:.3f}, {upper_ci:.3f}]")
            print(f"  Odds Ratio: {or_mean:.3f} [{or_lower:.3f}, {or_upper:.3f}]")
            print(f"  Effect: {effect_pct:+.1f}% change in odds per SD increase")

            # Check if credibly non-zero
            credible = (lower_ci > 0 and upper_ci > 0) or (lower_ci < 0 and upper_ci < 0)
            print(f"  Credibly non-zero: {'✅ Yes' if credible else '❌ No'}")
            print()

    def predict(self,
               data: Dict[str, np.ndarray],
               credible_interval: float = 0.95) -> Dict[str, np.ndarray]:
        """
        Generate predictions for new data.

        Args:
            data: Data dictionary with annual_cost and annual_savings
            credible_interval: Probability for credible intervals

        Returns:
            Dictionary with predictions and intervals
        """
        if self.trace is None:
            raise ValueError("Model must be fit before predicting")

        with self.model:
            # Update data
            pm.set_data({
                "annual_cost": data['annual_cost'],
                "annual_savings": data['annual_savings'],
            })

            # Generate posterior predictive samples
            posterior_pred = pm.sample_posterior_predictive(
                self.trace,
                var_names=["y_open"],
                return_inferencedata=False,
            )

        # Calculate predictions
        y_pred_samples = posterior_pred['y_open']
        y_pred_mean = y_pred_samples.mean(axis=0)

        # Calculate credible intervals
        lower_prob = (1 - credible_interval) / 2
        upper_prob = 1 - lower_prob
        y_pred_lower = np.percentile(y_pred_samples, lower_prob * 100, axis=0)
        y_pred_upper = np.percentile(y_pred_samples, upper_prob * 100, axis=0)

        return {
            'mean': y_pred_mean,
            'lower': y_pred_lower,
            'upper': y_pred_upper,
            'samples': y_pred_samples,
        }

    def plot_coefficients(self, save_path: Optional[str] = None):
        """
        Plot posterior distributions of coefficients.

        Args:
            save_path: Optional path to save figure
        """
        if self.trace is None:
            raise ValueError("Model must be fit before plotting")

        fig = az.plot_posterior(
            self.trace,
            var_names=["intercept", "beta_cost", "beta_savings"],
            figsize=(12, 4),
            hdi_prob=0.95,
            ref_val=0,
        )

        plt.suptitle(f"{self.name} - Posterior Distributions", y=1.02)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")

        return fig

    def save_trace(self, filepath: str):
        """Save trace to NetCDF file."""
        if self.trace is None:
            raise ValueError("Model must be fit before saving")

        self.trace.to_netcdf(filepath)
        print(f"Trace saved to {filepath}")

    def load_trace(self, filepath: str):
        """Load trace from NetCDF file."""
        self.trace = az.from_netcdf(filepath)
        print(f"Trace loaded from {filepath}")


# Example usage
if __name__ == "__main__":
    # This would be run with actual data
    print(f"Model 1: Baseline Open Model")
    print(f"This script defines the model class.")
    print(f"Use bayesian_scripts/bayes_fit_model_01.py to fit with real data.")
