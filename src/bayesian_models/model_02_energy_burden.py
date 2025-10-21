"""
Model 2: Energy Burden Model

Predicts email opens based on:
- Total energy burden (energy cost / income) - PRIMARY HYPOTHESIS
- Income level (confounder)
- Household size (confounder)

This model tests the primary hypothesis: households with high energy burden
(>6% of income) have higher email open rates, controlling for income and
household size.

Research Question:
"Do households with high energy burden have higher email open rates,
controlling for income level and household size?"

Expected Effects:
- Energy burden: POSITIVE (high burden → more need → higher engagement)
- Income level: NEGATIVE (lower income → target population → higher engagement)
- Household size: POSITIVE (more people → more impact → higher engagement)
"""

import numpy as np
import pymc as pm
import arviz as az
from typing import Dict, Optional
import matplotlib.pyplot as plt


class EnergyBurdenOpenModel:
    """Model 2: Energy burden model for email opens."""

    def __init__(self, name: str = "Model_2_EnergyBurden_Open"):
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
                - 'y_opened': Binary outcome (0/1)

        Returns:
            PyMC Model object
        """
        with pm.Model() as model:
            # Data containers (PyMC v5 API)
            energy_burden = pm.Data("energy_burden", data['energy_burden'])
            income_level = pm.Data("income_level", data['income_level'])
            household_size = pm.Data("household_size", data['household_size'])

            # Priors
            # Intercept: weakly informative prior centered at 0
            α = pm.Normal("intercept", mu=0, sigma=2)

            # Energy burden coefficient: weakly informative prior with slight positive bias
            # Expected positive effect (high burden → high engagement)
            β_burden = pm.Normal("beta_burden", mu=0.5, sigma=1)

            # Income coefficient: weakly informative prior
            # Expected negative effect (lower income → higher engagement)
            β_income = pm.Normal("beta_income", mu=0, sigma=1)

            # Household size coefficient: weakly informative prior
            # Expected positive effect (larger household → higher engagement)
            β_hhsize = pm.Normal("beta_hhsize", mu=0, sigma=1)

            # Linear model (logit scale)
            logit_p = (α +
                      β_burden * energy_burden +
                      β_income * income_level +
                      β_hhsize * household_size)

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
            var_names=["intercept", "beta_burden", "beta_income", "beta_hhsize"],
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

        burden_coef = summary.loc['beta_burden', 'mean']
        burden_lower = summary.loc['beta_burden', f'hdi_{(1-hdi_prob)/2*100:.1f}%']
        burden_upper = summary.loc['beta_burden', f'hdi_{100-(1-hdi_prob)/2*100:.1f}%']

        if burden_lower > 0:
            print("✅ PRIMARY HYPOTHESIS SUPPORTED:")
            print("   High energy burden predicts higher open rates")
            print(f"   Effect is credibly positive: [{burden_lower:.3f}, {burden_upper:.3f}]")
        elif burden_upper < 0:
            print("❌ PRIMARY HYPOTHESIS REJECTED:")
            print("   High energy burden predicts LOWER open rates")
            print(f"   Effect is credibly negative: [{burden_lower:.3f}, {burden_upper:.3f}]")
        else:
            print("⚠️  PRIMARY HYPOTHESIS INCONCLUSIVE:")
            print("   Energy burden effect includes zero")
            print(f"   Credible interval: [{burden_lower:.3f}, {burden_upper:.3f}]")

    def predict(self,
               data: Dict[str, np.ndarray],
               credible_interval: float = 0.95) -> Dict[str, np.ndarray]:
        """
        Generate predictions for new data.

        Args:
            data: Data dictionary with energy_burden, income_level, household_size
            credible_interval: Probability for credible intervals

        Returns:
            Dictionary with predictions and intervals
        """
        if self.trace is None:
            raise ValueError("Model must be fit before predicting")

        with self.model:
            # Update data
            pm.set_data({
                "energy_burden": data['energy_burden'],
                "income_level": data['income_level'],
                "household_size": data['household_size'],
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
            var_names=["intercept", "beta_burden", "beta_income", "beta_hhsize"],
            figsize=(12, 6),
            hdi_prob=0.95,
            ref_val=0,
        )

        plt.suptitle(f"{self.name} - Posterior Distributions", y=1.02)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")

        return fig

    def plot_marginal_effects(self,
                            data: Dict[str, np.ndarray],
                            save_path: Optional[str] = None):
        """
        Plot marginal effects of energy burden on open probability.

        Args:
            data: Original data dictionary
            save_path: Optional path to save figure
        """
        if self.trace is None:
            raise ValueError("Model must be fit before plotting")

        # Create range of energy burden values
        burden_range = np.linspace(
            data['energy_burden'].min(),
            data['energy_burden'].max(),
            100
        )

        # Hold other predictors at their means
        income_mean = data['income_level'].mean()
        hhsize_mean = data['household_size'].mean()

        # Generate predictions
        pred_data = {
            'energy_burden': burden_range,
            'income_level': np.full_like(burden_range, income_mean),
            'household_size': np.full_like(burden_range, hhsize_mean),
        }

        predictions = self.predict(pred_data)

        # Plot
        fig, ax = plt.subplots(figsize=(10, 6))

        ax.plot(burden_range, predictions['mean'], 'b-', linewidth=2,
               label='Mean prediction')
        ax.fill_between(burden_range,
                        predictions['lower'],
                        predictions['upper'],
                        alpha=0.3,
                        label='95% credible interval')

        ax.set_xlabel('Energy Burden (scaled)', fontsize=12)
        ax.set_ylabel('Predicted P(Open)', fontsize=12)
        ax.set_title('Marginal Effect of Energy Burden on Open Probability', fontsize=14)
        ax.legend()
        ax.grid(alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Marginal effects plot saved to {save_path}")

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
    print(f"Model 2: Energy Burden Open Model")
    print(f"This script defines the model class.")
    print(f"Use bayesian_scripts/bayes_fit_model_02.py to fit with real data.")
