"""
Model 3: Demographics Model

Predicts email opens based on:
- Total energy burden (energy cost / income)
- Income level (confounder)
- Household size (confounder)
- Annual kWh usage (NEW - usage intensity/salience)

This model tests whether electricity usage intensity predicts engagement
beyond energy burden and demographics.

Research Question:
"Does electricity usage level predict email open rates, controlling for
energy burden, income level, and household size?"

Expected Effects:
- Energy burden: POSITIVE (high burden → more need → higher engagement)
- Income level: NEGATIVE (lower income → target population → higher engagement)
- Household size: POSITIVE (more people → more impact → higher engagement)
- kWh usage: POSITIVE (higher usage → higher bills → more salience)
"""

import numpy as np
import pymc as pm
import arviz as az
from typing import Dict, Optional
import matplotlib.pyplot as plt


class DemographicsOpenModel:
    """Model 3: Demographics model for email opens."""

    def __init__(self, name: str = "Model_3_Demographics_Open"):
        """Initialize the model."""
        self.name = name
        self.model = None
        self.trace = None

    def build_model(self, data: Dict[str, np.ndarray]) -> pm.Model:
        """
        Build the PyMC model.

        Args:
            data: Dictionary with keys:
                - 'energy_burden': Total energy burden (scaled)
                - 'income_level': Income level 0-9 (scaled)
                - 'household_size': Household size (scaled)
                - 'kwh_usage': Annual kWh usage (scaled)
                - 'y_opened': Binary outcome (0/1)

        Returns:
            PyMC Model object
        """
        with pm.Model() as model:
            # Data containers (PyMC v5 API)
            energy_burden = pm.Data("energy_burden", data['energy_burden'])
            income_level = pm.Data("income_level", data['income_level'])
            household_size = pm.Data("household_size", data['household_size'])
            kwh_usage = pm.Data("kwh_usage", data['kwh_usage'])

            # Priors
            # Intercept: weakly informative prior centered at 0
            α = pm.Normal("intercept", mu=0, sigma=2)

            # Energy burden coefficient: weakly informative prior with slight positive bias
            β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)

            # Income coefficient: weakly informative prior
            β_income = pm.Normal("beta_income", mu=0, sigma=1)

            # Household size coefficient: weakly informative prior
            β_hhsize = pm.Normal("beta_hhsize", mu=0, sigma=1)

            # kWh usage coefficient: weakly informative prior
            # Expected positive effect (higher usage → higher salience)
            β_kwh = pm.Normal("beta_kwh", mu=0, sigma=1)

            # Linear model (logit scale)
            logit_p = (α +
                      β_burden * energy_burden +
                      β_income * income_level +
                      β_hhsize * household_size +
                      β_kwh * kwh_usage)

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
        print(f"\nData characteristics:")
        print(f"  Energy burden mean: {data['energy_burden'].mean():.3f} (SD: {data['energy_burden'].std():.3f})")
        print(f"  Income level mean: {data['income_level'].mean():.3f} (SD: {data['income_level'].std():.3f})")
        print(f"  Household size mean: {data['household_size'].mean():.3f} (SD: {data['household_size'].std():.3f})")
        print(f"  kWh usage mean: {data['kwh_usage'].mean():.3f} (SD: {data['kwh_usage'].std():.3f})")
        print(f"\nSampling: {draws} draws × {chains} chains (tune={tune})")
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
            var_names=["intercept", "beta_burden", "beta_income", "beta_hhsize", "beta_kwh"],
            hdi_prob=hdi_prob
        )

        print(summary)

        # Interpret coefficients on odds ratio scale
        print(f"\n{'='*60}")
        print("COEFFICIENT INTERPRETATION (Odds Ratios)")
        print(f"{'='*60}\n")

        interpretations = {
            'beta_burden': 'Energy Burden',
            'beta_income': 'Income Level',
            'beta_hhsize': 'Household Size',
            'beta_kwh': 'kWh Usage',
        }

        for var, label in interpretations.items():
            mean_coef = summary.loc[var, 'mean']
            lower_ci = summary.loc[var, f'hdi_{(1-hdi_prob)/2*100:.1f}%']
            upper_ci = summary.loc[var, f'hdi_{100-(1-hdi_prob)/2*100:.1f}%']

            or_mean = np.exp(mean_coef)
            or_lower = np.exp(lower_ci)
            or_upper = np.exp(upper_ci)

            effect_pct = (or_mean - 1) * 100

            print(f"{label} ({var}):")
            print(f"  Coefficient: {mean_coef:.3f} [{lower_ci:.3f}, {upper_ci:.3f}]")
            print(f"  Odds Ratio: {or_mean:.3f} [{or_lower:.3f}, {or_upper:.3f}]")
            print(f"  Effect: {effect_pct:+.1f}% change in odds per SD increase")

            # Check if credibly non-zero
            credible = (lower_ci > 0 and upper_ci > 0) or (lower_ci < 0 and upper_ci < 0)
            print(f"  Credibly non-zero: {'✅ Yes' if credible else '❌ No'}")
            print()

        # Hypothesis test summary
        print(f"{'='*60}")
        print("HYPOTHESIS TEST RESULTS")
        print(f"{'='*60}\n")

        kwh_coef = summary.loc['beta_kwh', 'mean']
        kwh_lower = summary.loc['beta_kwh', f'hdi_{(1-hdi_prob)/2*100:.1f}%']
        kwh_upper = summary.loc['beta_kwh', f'hdi_{100-(1-hdi_prob)/2*100:.1f}%']

        print("Model 3 NEW HYPOTHESIS:")
        if kwh_lower > 0:
            print("✅ HYPOTHESIS SUPPORTED:")
            print("   Higher kWh usage predicts higher open rates")
            print(f"   Effect is credibly positive: [{kwh_lower:.3f}, {kwh_upper:.3f}]")
        elif kwh_upper < 0:
            print("❌ HYPOTHESIS REJECTED:")
            print("   Higher kWh usage predicts LOWER open rates")
            print(f"   Effect is credibly negative: [{kwh_lower:.3f}, {kwh_upper:.3f}]")
        else:
            print("⚠️  HYPOTHESIS INCONCLUSIVE:")
            print("   kWh usage effect includes zero")
            print(f"   Credible interval: [{kwh_lower:.3f}, {kwh_upper:.3f}]")

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
            var_names=["intercept", "beta_burden", "beta_income", "beta_hhsize", "beta_kwh"],
            figsize=(15, 6),
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
    print(f"Model 3: Demographics Open Model")
    print(f"This script defines the model class.")
    print(f"Use bayesian_scripts/bayes_fit_model_03.py to fit with real data.")
