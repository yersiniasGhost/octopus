"""
================================================================================
BAYESIAN CLICK-THROUGH MODEL - VERSION 02 (WITH HOUSE AGE)
================================================================================

A Bayesian causal model for predicting click-through behavior based on
contact demographics and house characteristics.

This version adds house_age (years since built) as a predictor to explore
whether older homes correlate with different engagement patterns.

DAG for Version 02:

        House_Age ───────┐
                         │
       Income ───────────┼──────► Click (0/1)
                         │
  Energy_Burden ─────────┘

Mathematical Model:
    Click_i ~ Bernoulli(p_i)
    logit(p_i) = α + β_income * Income_i + β_eb * EnergyBurden_i + β_house_age * HouseAge_i

Priors (weakly informative, following McElreath's Statistical Rethinking):
    α ~ Normal(-3.5, 1.0)         # Centers baseline near 3% click rate
    β_income ~ Normal(0, 0.5)     # Standardized coefficients
    β_eb ~ Normal(0, 0.5)
    β_house_age ~ Normal(0, 0.5)

References:
- McElreath, R. (2020). Statistical Rethinking, 2nd Edition
- PyMC Resources: https://github.com/pymc-devs/pymc-resources/tree/main/Rethinking_2
================================================================================
"""

import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
from typing import Optional, Dict, List, Tuple
import warnings

from .model_data_preprocessor import DataPreprocessor
from .model_data import ClickModelData, load_data

# Configure plotting style
plt.style.use('seaborn-v0_8-whitegrid')
az.style.use("arviz-darkgrid")

# Suppress convergence warnings during development (remove in production)
warnings.filterwarnings('ignore', category=UserWarning)


# =============================================================================
# VERSION 02: DEMOGRAPHICS + HOUSE AGE MODEL
# =============================================================================

class ClickModel:
    """
    Version 02: Demographics + House Age → Click

    This model extends version 01 by adding house age as a predictor.

    DAG:
        House_Age ───────┐
                         │
       Income ───────────┼──────► Click
                         │
    Energy_Burden ───────┘

    This model answers:
    - What is the baseline click probability for different demographic segments?
    - Does house age correlate with click behavior?
    - Which factors are most predictive of clicks?
    - How much uncertainty do we have in these estimates?
    """

    @classmethod
    def describe(cls) -> str:
        description = '''
        Version 02 model that estimates click probability based on
        contact demographics (income, energy burden) and house characteristics (house age).
        '''
        return description

    @classmethod
    def name(cls) -> str:
        return "Click Model 02 (with House Age)"

    def __init__(self, preprocessor: DataPreprocessor = None):
        """
        Initialize the model.

        Parameters
        ----------
        preprocessor : DataPreprocessor, optional
            Preprocessor for standardization. If None, creates new one.
        """
        self.preprocessor = preprocessor or DataPreprocessor()
        self.model: pm.Model = None
        self.trace: az.InferenceData = None
        self._model_built = False
        self._has_owner_age = False  # Owner age (person), not house age

    def build_model(self, data: ClickModelData) -> pm.Model:
        """
        Build the PyMC model.

        Parameters
        ----------
        data : ClickModelData
            Training data

        Returns
        -------
        pm.Model
            Compiled PyMC model
        """
        # Preprocess data
        model_data = self.preprocessor.fit_transform(data)

        # Check if owner age (person's age) is available
        has_owner_age = model_data['age_std'] is not None
        self._has_owner_age = has_owner_age

        with pm.Model() as model:
            # ================================================================
            # DATA
            # ================================================================
            income_std = pm.Data('income_std', model_data['income_std'])
            eb_std = pm.Data('eb_std', model_data['eb_std'])
            house_age_std = pm.Data('house_age_std', model_data['house_age_std'])

            if has_owner_age:
                owner_age_std = pm.Data('owner_age_std', model_data['age_std'])

            # ================================================================
            # PRIORS
            # ================================================================
            # Intercept: centered at logit(0.03) ≈ -3.5 for ~3% baseline CTR
            alpha = pm.Normal('alpha', mu=-3.5, sigma=1.0)

            # Coefficients: weakly informative centered at 0
            # sigma=0.5 means a 1 SD change in the predictor changes
            # log-odds by ~0.5, or odds ratio of ~1.6
            beta_income = pm.Normal('beta_income', mu=0, sigma=0.5)
            beta_eb = pm.Normal('beta_eb', mu=0, sigma=0.5)
            beta_house_age = pm.Normal('beta_house_age', mu=0, sigma=0.5)

            if has_owner_age:
                beta_owner_age = pm.Normal('beta_owner_age', mu=0, sigma=0.5)

            # ================================================================
            # LINEAR MODEL
            # ================================================================
            # Log-odds of clicking
            logit_p = (alpha
                       + beta_income * income_std
                       + beta_eb * eb_std
                       + beta_house_age * house_age_std)

            if has_owner_age:
                logit_p = logit_p + beta_owner_age * owner_age_std

            # Transform to probability
            p = pm.Deterministic('p', pm.math.invlogit(logit_p))

            # ================================================================
            # LIKELIHOOD
            # ================================================================
            # Observed clicks follow Bernoulli distribution
            clicks = pm.Bernoulli('clicks', p=p, observed=model_data['click'])

        self.model = model
        self._model_built = True
        print("✓ Model built successfully (with house age)")

        return model

    def fit(self, draws: int = 2000, tune: int = 1000, chains: int = 4,
            target_accept: float = 0.9, random_seed: int = 42,
            use_gpu: bool = True) -> az.InferenceData:
        """
        Fit the model using MCMC sampling.

        Parameters
        ----------
        draws : int
            Number of samples to draw per chain (after tuning)
        tune : int
            Number of tuning samples (discarded)
        chains : int
            Number of MCMC chains (for convergence diagnostics)
        target_accept : float
            Target acceptance rate for NUTS sampler (higher = more careful)
        random_seed : int
            Random seed for reproducibility
        use_gpu : bool
            If True, use NumPyro JAX backend for GPU acceleration (default).
            If False, use default PyMC CPU sampler with parallel chains.

        Returns
        -------
        az.InferenceData
            ArviZ InferenceData object containing posterior samples
        """
        if not self._model_built:
            raise ValueError("Model not built. Call build_model() first.")

        if use_gpu:
            print(f"Fitting model with {chains} chains × {draws} draws (GPU via NumPyro)...")
        else:
            print(f"Fitting model with {chains} chains × {draws} draws (CPU)...")

        with self.model:
            sample_kwargs = dict(
                draws=draws,
                tune=tune,
                chains=chains,
                target_accept=target_accept,
                random_seed=random_seed,
                return_inferencedata=True,
                progressbar=True
            )

            if use_gpu:
                sample_kwargs["nuts_sampler"] = "numpyro"

            self.trace = pm.sample(**sample_kwargs)

        # Check convergence
        self._check_convergence()

        return self.trace

    def _check_convergence(self):
        """Check MCMC convergence diagnostics."""
        print("\n" + "=" * 60)
        print("CONVERGENCE DIAGNOSTICS")
        print("=" * 60)

        # Determine which parameters exist
        param_names = ['alpha', 'beta_income', 'beta_eb', 'beta_house_age']
        if self._has_owner_age:
            param_names.append('beta_owner_age')

        # R-hat (should be < 1.01)
        rhat = az.rhat(self.trace)
        rhat_values = [rhat[p].values for p in param_names]
        max_rhat = max(rhat_values)
        print(f"Max R-hat: {max_rhat:.3f} {'✓' if max_rhat < 1.01 else '⚠️ WARNING'}")

        # ESS (effective sample size, should be > 400)
        ess = az.ess(self.trace)
        ess_values = [ess[p].values for p in param_names]
        min_ess = min(ess_values)
        print(f"Min ESS: {min_ess:.0f} {'✓' if min_ess > 400 else '⚠️ WARNING'}")

        print("=" * 60 + "\n")

    def summary(self) -> pd.DataFrame:
        """
        Get summary statistics for model parameters.

        Returns
        -------
        pd.DataFrame
            Summary table with posterior means, SDs, and credible intervals
        """
        if self.trace is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Determine which parameters exist
        var_names = ['alpha', 'beta_income', 'beta_eb', 'beta_house_age']
        if self._has_owner_age:
            var_names.append('beta_owner_age')

        return az.summary(self.trace, var_names=var_names, hdi_prob=0.94)

    def plot_trace(self, figsize: Tuple[int, int] = (12, 10)):
        """Plot trace plots for visual convergence assessment."""
        if self.trace is None:
            raise ValueError("Model not fitted. Call fit() first.")

        var_names = ['alpha', 'beta_income', 'beta_eb', 'beta_house_age']
        if self._has_owner_age:
            var_names.append('beta_owner_age')

        az.plot_trace(self.trace, var_names=var_names, figsize=figsize)
        plt.tight_layout()
        return plt.gcf()

    def plot_posterior(self, figsize: Tuple[int, int] = (14, 6)):
        """Plot posterior distributions for parameters."""
        if self.trace is None:
            raise ValueError("Model not fitted. Call fit() first.")

        var_names = ['alpha', 'beta_income', 'beta_eb', 'beta_house_age']
        if self._has_owner_age:
            var_names.append('beta_owner_age')

        az.plot_posterior(self.trace, var_names=var_names, hdi_prob=0.94, figsize=figsize)
        plt.tight_layout()
        return plt.gcf()


# =============================================================================
# INFERENCE: SEGMENT PREDICTIONS
# =============================================================================

class SegmentPredictor:
    """
    Generate predictions for demographic segments.

    This class enables the key inference question:
    "What is the predicted click probability for contacts with
     specific demographic and housing characteristics?"
    """

    def __init__(self, model: ClickModel):
        """
        Initialize predictor with fitted model.

        Parameters
        ----------
        model : ClickModel
            A fitted ClickModel instance
        """
        if model.trace is None:
            raise ValueError("Model must be fitted before creating predictor")
        self.model = model
        self.trace = model.trace
        self.preprocessor = model.preprocessor

    def predict_segment(self, income: float, energy_burden: float, house_age: float,
                        owner_age: float = None) -> Dict[str, float]:
        """
        Predict click probability for a specific demographic segment.

        Parameters
        ----------
        income : float
            Annual income in dollars
        energy_burden : float
            Energy burden as percentage of income
        house_age : float
            Age of house in years
        owner_age : float, optional
            Owner's age in years (only used if model was trained with owner age data)

        Returns
        -------
        dict
            Dictionary with:
            - mean: Posterior mean probability
            - std: Posterior standard deviation
            - hdi_3%: Lower bound of 94% HDI
            - hdi_97%: Upper bound of 94% HDI
            - samples: Full posterior samples (for custom analysis)
        """
        # Standardize inputs
        std_vals = self.preprocessor.transform_new(
            income=income,
            energy_burden=energy_burden,
            house_age=house_age,
            age=owner_age
        )

        # Extract posterior samples
        posterior = self.trace.posterior
        alpha = posterior['alpha'].values.flatten()
        beta_income = posterior['beta_income'].values.flatten()
        beta_eb = posterior['beta_eb'].values.flatten()
        beta_house_age = posterior['beta_house_age'].values.flatten()

        # Compute log-odds for each posterior sample
        logit_p = (alpha
                   + beta_income * std_vals['income_std']
                   + beta_eb * std_vals['eb_std']
                   + beta_house_age * std_vals['house_age_std'])

        # Add owner age effect if available
        if 'beta_owner_age' in posterior and std_vals.get('age_std') is not None:
            beta_owner_age = posterior['beta_owner_age'].values.flatten()
            logit_p = logit_p + beta_owner_age * std_vals['age_std']

        # Transform to probability
        p_samples = 1 / (1 + np.exp(-logit_p))

        # Compute summary statistics
        hdi = az.hdi(p_samples, hdi_prob=0.94)

        return {
            'mean': p_samples.mean(),
            'std': p_samples.std(),
            'hdi_3%': hdi[0],
            'hdi_97%': hdi[1],
            'samples': p_samples
        }

    def compare_segments(self, segments: List[Dict]) -> pd.DataFrame:
        """
        Compare click probabilities across multiple segments.

        Parameters
        ----------
        segments : list of dict
            Each dict should have keys: 'name', 'income', 'energy_burden', 'house_age'
            Optional key: 'owner_age'

        Returns
        -------
        pd.DataFrame
            Comparison table with predictions for each segment
        """
        results = []
        for seg in segments:
            pred = self.predict_segment(
                income=seg['income'],
                energy_burden=seg['energy_burden'],
                house_age=seg['house_age'],
                owner_age=seg.get('owner_age')
            )
            row = {
                'Segment': seg['name'],
                'Income': f"${seg['income']:,}",
                'Energy Burden': f"{seg['energy_burden']}%",
                'House Age': f"{seg['house_age']} yrs",
                'Click Prob (Mean)': f"{pred['mean']:.2%}",
                'Click Prob (94% HDI)': f"[{pred['hdi_3%']:.2%}, {pred['hdi_97%']:.2%}]"
            }
            if 'owner_age' in seg:
                row['Owner Age'] = seg['owner_age']
            results.append(row)

        return pd.DataFrame(results)

    def plot_segment_comparison(self, segments: List[Dict], figsize: Tuple[int, int] = (10, 6)):
        """
        Visualize click probability distributions across segments.

        Parameters
        ----------
        segments : list of dict
            Each dict should have keys: 'name', 'income', 'energy_burden', 'house_age'
        figsize : tuple
            Figure size
        """
        fig, ax = plt.subplots(figsize=figsize)

        # Use distinct colors for each segment
        colors = plt.cm.tab10.colors

        for i, seg in enumerate(segments):
            pred = self.predict_segment(
                income=seg['income'],
                energy_burden=seg['energy_burden'],
                house_age=seg['house_age'],
                owner_age=seg.get('owner_age')
            )

            # Plot density with distinct color
            color = colors[i % len(colors)]
            az.plot_kde(
                pred['samples'],
                ax=ax,
                label=seg['name'],
                plot_kwargs={'alpha': 0.7, 'color': color, 'linewidth': 2}
            )

        ax.set_xlabel('Click Probability')
        ax.set_ylabel('Density')
        ax.set_title('Click Probability by Demographic Segment (with House Age)')
        ax.legend(loc='upper right')
        plt.tight_layout()

        return fig

    def probability_one_segment_higher(self, seg1: Dict, seg2: Dict) -> float:
        """
        Compute probability that segment 1 has higher click rate than segment 2.

        Parameters
        ----------
        seg1, seg2 : dict
            Dictionaries with 'income', 'energy_burden', 'house_age' keys

        Returns
        -------
        float
            Probability that P(click|seg1) > P(click|seg2)
        """
        pred1 = self.predict_segment(
            seg1['income'], seg1['energy_burden'], seg1['house_age'], seg1.get('owner_age')
        )
        pred2 = self.predict_segment(
            seg2['income'], seg2['energy_burden'], seg2['house_age'], seg2.get('owner_age')
        )

        return (pred1['samples'] > pred2['samples']).mean()


# =============================================================================
# EXAMPLE USAGE: FULL WORKFLOW
# =============================================================================

def run_full_analysis():
    """
    Run complete Version 02 analysis workflow.

    This function demonstrates the entire pipeline:
    1. Load data (with house age)
    2. Build model
    3. Fit model
    4. Check diagnostics
    5. Generate segment predictions
    6. Compare segments
    """
    from .segments import DEFAULT_SEGMENTS

    print("=" * 70)
    print("BAYESIAN CLICK MODEL - VERSION 02: WITH HOUSE AGE")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # STEP 1: Load Data
    # -------------------------------------------------------------------------
    print("STEP 1: Loading Data")
    print("-" * 40)
    data = load_data()
    print(f"\n{data.summary()}\n")

    # -------------------------------------------------------------------------
    # STEP 2: Build Model
    # -------------------------------------------------------------------------
    print("\nSTEP 2: Building Model")
    print("-" * 40)
    model = ClickModel()
    model.build_model(data)

    # -------------------------------------------------------------------------
    # STEP 3: Fit Model
    # -------------------------------------------------------------------------
    print("\nSTEP 3: Fitting Model (MCMC Sampling)")
    print("-" * 40)
    trace = model.fit(draws=2000, tune=1000, chains=4, use_gpu=True)

    # -------------------------------------------------------------------------
    # STEP 4: Review Results
    # -------------------------------------------------------------------------
    print("\nSTEP 4: Model Summary")
    print("-" * 40)
    print(model.summary())

    # Interpret coefficients
    print("\nCoefficient Interpretation (on log-odds scale):")
    posterior = trace.posterior

    beta_income_mean = posterior['beta_income'].values.mean()
    beta_eb_mean = posterior['beta_eb'].values.mean()
    beta_house_age_mean = posterior['beta_house_age'].values.mean()

    print(f"  • Income: {beta_income_mean:.3f} → {'higher income = lower' if beta_income_mean < 0 else 'higher income = higher'} click prob")
    print(f"  • Energy Burden: {beta_eb_mean:.3f} → {'higher burden = lower' if beta_eb_mean < 0 else 'higher burden = higher'} click prob")
    print(f"  • House Age: {beta_house_age_mean:.3f} → {'older house = lower' if beta_house_age_mean < 0 else 'older house = higher'} click prob")

    if 'beta_owner_age' in posterior:
        beta_owner_age_mean = posterior['beta_owner_age'].values.mean()
        print(f"  • Owner Age: {beta_owner_age_mean:.3f} → {'older owner = lower' if beta_owner_age_mean < 0 else 'older owner = higher'} click prob")

    # -------------------------------------------------------------------------
    # STEP 5: Segment Predictions
    # -------------------------------------------------------------------------
    print("\nSTEP 5: Segment Predictions")
    print("-" * 40)

    predictor = SegmentPredictor(model)

    print("\nSegment Comparison:")
    comparison = predictor.compare_segments(DEFAULT_SEGMENTS)
    print(comparison.to_string(index=False))

    # -------------------------------------------------------------------------
    # STEP 6: Segment Contrast
    # -------------------------------------------------------------------------
    print("\n\nSTEP 6: Segment Contrasts")
    print("-" * 40)

    seg_old_house = {'income': 50000, 'energy_burden': 10, 'house_age': 60}
    seg_new_house = {'income': 50000, 'energy_burden': 10, 'house_age': 10}

    prob_higher = predictor.probability_one_segment_higher(seg_old_house, seg_new_house)
    print(f"P(Old House (60yr) > New House (10yr) | same income, EB) = {prob_higher:.1%}")

    # -------------------------------------------------------------------------
    # STEP 7: Visualizations
    # -------------------------------------------------------------------------
    print("\n\nSTEP 7: Generating Visualizations")
    print("-" * 40)

    # Plot trace
    model.plot_trace()
    plt.savefig('trace_plot_v02.png', dpi=150, bbox_inches='tight')
    print("  Saved: trace_plot_v02.png")

    # Plot posteriors
    model.plot_posterior()
    plt.savefig('posterior_plot_v02.png', dpi=150, bbox_inches='tight')
    print("  Saved: posterior_plot_v02.png")

    # Plot segment comparison
    predictor.plot_segment_comparison(DEFAULT_SEGMENTS)
    plt.savefig('segment_comparison_v02.png', dpi=150, bbox_inches='tight')
    print("  Saved: segment_comparison_v02.png")

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)

    return model, predictor, data


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Run the full analysis
    model, predictor, data = run_full_analysis()
