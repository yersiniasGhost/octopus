"""
================================================================================
BAYESIAN CLICK-THROUGH MODEL - VERSION 0
================================================================================

A Bayesian causal model for predicting click-through behavior based on
contact demographics. This is the simplest model in our progression,
establishing baseline click probabilities conditioned on demographics only.

Model Progression:
- Version 0 (this file): Demographics → Click (baseline model)
- Version 1 (next): Demographics + Channel → Click
- Version 2 (later): Demographics + Channel + Framing + Timing → Click

DAG for Version 0:

        Age ─────────┐
                     │
       Income ───────┼──────► Click (0/1)
                     │
  Energy_Burden ────┘

Mathematical Model:
    Click_i ~ Bernoulli(p_i)
    logit(p_i) = α + β_age * Age_i + β_income * Income_i + β_eb * EnergyBurden_i

Priors (weakly informative, following McElreath's Statistical Rethinking):
    α ~ Normal(-3.5, 1.0)      # Centers baseline near 3% click rate
    β_age ~ Normal(0, 0.5)     # Standardized coefficients
    β_income ~ Normal(0, 0.5)
    β_eb ~ Normal(0, 0.5)

References:
- McElreath, R. (2020). Statistical Rethinking, 2nd Edition
- PyMC Resources: https://github.com/pymc-devs/pymc-resources/tree/main/Rethinking_2

Author: [Your Name]
Date: 2024
================================================================================
"""

import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
from typing import Optional, Dict, List, Tuple
import warnings

from .click_mode_data_preprocessor import DataPreprocessor
from .click_model_data import ClickModelData, load_data

# Configure plotting style
plt.style.use('seaborn-v0_8-whitegrid')
az.style.use("arviz-darkgrid")

# Suppress convergence warnings during development (remove in production)
warnings.filterwarnings('ignore', category=UserWarning)


# =============================================================================
# VERSION 0: DEMOGRAPHICS-ONLY MODEL
# =============================================================================

class ClickModel:
    """
    Version 0: Demographics → Click

    This is our baseline model that estimates click probability based solely
    on contact demographics (age, income, energy burden).

    DAG:
        Age ─────────┐
                     │
       Income ───────┼──────► Click
                     │
    Energy_Burden ───┘

    This model answers:
    - What is the baseline click probability for different demographic segments?
    - Which demographic factors are associated with higher/lower click rates?
    - How much uncertainty do we have in these estimates?

    This model does NOT answer (yet):
    - What is the effect of channel/timing/framing? (Version 1+)
    - What is the optimal treatment for a given contact? (Version 1+)
    """

    @classmethod
    def describe(cls) -> str:
        description = '''    
        This is our baseline model that estimates click probability based solely
        on contact demographics (age, income, energy burden).
        '''
        return description

    @classmethod
    def name(cls) -> str:
        return "Click Model 01"


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

        with pm.Model() as model:
            # ================================================================
            # DATA
            # ================================================================
            # Store data in model for later reference
            age_std = pm.Data('age_std', model_data['age_std'])
            income_std = pm.Data('income_std', model_data['income_std'])
            eb_std = pm.Data('eb_std', model_data['eb_std'])

            # ================================================================
            # PRIORS
            # ================================================================
            # Intercept: centered at logit(0.03) ≈ -3.5 for ~3% baseline CTR
            # The prior std of 1.0 allows the intercept to range from
            # ~0.5% to ~15% CTR at ±2 SD, which is reasonable uncertainty
            alpha = pm.Normal('alpha', mu=-3.5, sigma=1.0)

            # Coefficients: weakly informative centered at 0
            # sigma=0.5 means a 1 SD change in the predictor changes
            # log-odds by ~0.5, or odds ratio of ~1.6
            # This is a moderate effect size prior
            beta_age = pm.Normal('beta_age', mu=0, sigma=0.5)
            beta_income = pm.Normal('beta_income', mu=0, sigma=0.5)
            beta_eb = pm.Normal('beta_eb', mu=0, sigma=0.5)

            # ================================================================
            # LINEAR MODEL
            # ================================================================
            # Log-odds of clicking
            logit_p = (
                    alpha
                    + beta_age * age_std
                    + beta_income * income_std
                    + beta_eb * eb_std
            )

            # Transform to probability
            p = pm.Deterministic('p', pm.math.invlogit(logit_p))

            # ================================================================
            # LIKELIHOOD
            # ================================================================
            # Observed clicks follow Bernoulli distribution
            clicks = pm.Bernoulli('clicks', p=p, observed=model_data['click'])

        self.model = model
        self._model_built = True
        print("✓ Model built successfully")

        return model



    def fit(self,
            draws: int = 2000,
            tune: int = 1000,
            chains: int = 4,
            target_accept: float = 0.9,
            random_seed: int = 42) -> az.InferenceData:
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

        Returns
        -------
        az.InferenceData
            ArviZ InferenceData object containing posterior samples
        """
        if not self._model_built:
            raise ValueError("Model not built. Call build_model() first.")

        print(f"Fitting model with {chains} chains × {draws} draws...")

        with self.model:
            self.trace = pm.sample(
                draws=draws,
                tune=tune,
                chains=chains,
                target_accept=target_accept,
                random_seed=random_seed,
                return_inferencedata=True,
                progressbar=True
            )

        # Check convergence
        self._check_convergence()

        return self.trace



    def _check_convergence(self):
        """Check MCMC convergence diagnostics."""
        print("\n" + "=" * 60)
        print("CONVERGENCE DIAGNOSTICS")
        print("=" * 60)

        # R-hat (should be < 1.01)
        rhat = az.rhat(self.trace)
        max_rhat = max(rhat['alpha'].values, rhat['beta_age'].values,
                       rhat['beta_income'].values, rhat['beta_eb'].values)
        print(f"Max R-hat: {max_rhat:.3f} {'✓' if max_rhat < 1.01 else '⚠️ WARNING'}")

        # ESS (effective sample size, should be > 400)
        ess = az.ess(self.trace)
        min_ess = min(ess['alpha'].values, ess['beta_age'].values,
                      ess['beta_income'].values, ess['beta_eb'].values)
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

        return az.summary(
            self.trace,
            var_names=['alpha', 'beta_age', 'beta_income', 'beta_eb'],
            hdi_prob=0.94  # 94% HDI following McElreath
        )



    def plot_trace(self, figsize: Tuple[int, int] = (12, 8)):
        """Plot trace plots for visual convergence assessment."""
        if self.trace is None:
            raise ValueError("Model not fitted. Call fit() first.")

        az.plot_trace(
            self.trace,
            var_names=['alpha', 'beta_age', 'beta_income', 'beta_eb'],
            figsize=figsize
        )
        plt.tight_layout()
        return plt.gcf()



    def plot_posterior(self, figsize: Tuple[int, int] = (12, 6)):
        """Plot posterior distributions for parameters."""
        if self.trace is None:
            raise ValueError("Model not fitted. Call fit() first.")

        az.plot_posterior(
            self.trace,
            var_names=['alpha', 'beta_age', 'beta_income', 'beta_eb'],
            hdi_prob=0.94,
            figsize=figsize
        )
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
     specific demographic characteristics?"
    """



    def __init__(self, model: ClickModel):
        """
        Initialize predictor with fitted model.

        Parameters
        ----------
        model : ClickModelV0
            A fitted ClickModelV0 instance
        """
        if model.trace is None:
            raise ValueError("Model must be fitted before creating predictor")
        self.model = model
        self.trace = model.trace
        self.preprocessor = model.preprocessor



    def predict_segment(self,
                        age: float,
                        income: float,
                        energy_burden: float) -> Dict[str, float]:
        """
        Predict click probability for a specific demographic segment.

        Parameters
        ----------
        age : float
            Age in years
        income : float
            Annual income in dollars
        energy_burden : float
            Energy burden as percentage of income

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
        std_vals = self.preprocessor.transform_new(age, income, energy_burden)

        # Extract posterior samples
        posterior = self.trace.posterior
        alpha = posterior['alpha'].values.flatten()
        beta_age = posterior['beta_age'].values.flatten()
        beta_income = posterior['beta_income'].values.flatten()
        beta_eb = posterior['beta_eb'].values.flatten()

        # Compute log-odds for each posterior sample
        logit_p = (
                alpha
                + beta_age * std_vals['age_std']
                + beta_income * std_vals['income_std']
                + beta_eb * std_vals['eb_std']
        )

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
            Each dict should have keys: 'name', 'age', 'income', 'energy_burden'

        Returns
        -------
        pd.DataFrame
            Comparison table with predictions for each segment

        Example
        -------
        >>> segments = [
        ...     {'name': 'Young, High EB', 'age': 30, 'income': 40000, 'energy_burden': 12},
        ...     {'name': 'Old, Low EB', 'age': 65, 'income': 80000, 'energy_burden': 4},
        ... ]
        >>> predictor.compare_segments(segments)
        """
        results = []
        for seg in segments:
            pred = self.predict_segment(
                age=seg['age'],
                income=seg['income'],
                energy_burden=seg['energy_burden']
            )
            results.append({
                'Segment': seg['name'],
                'Age': seg['age'],
                'Income': f"${seg['income']:,}",
                'Energy Burden': f"{seg['energy_burden']}%",
                'Click Prob (Mean)': f"{pred['mean']:.2%}",
                'Click Prob (94% HDI)': f"[{pred['hdi_3%']:.2%}, {pred['hdi_97%']:.2%}]"
            })

        return pd.DataFrame(results)



    def plot_segment_comparison(self, segments: List[Dict], figsize: Tuple[int, int] = (10, 6)):
        """
        Visualize click probability distributions across segments.

        Parameters
        ----------
        segments : list of dict
            Each dict should have keys: 'name', 'age', 'income', 'energy_burden'
        figsize : tuple
            Figure size
        """
        fig, ax = plt.subplots(figsize=figsize)

        for i, seg in enumerate(segments):
            pred = self.predict_segment(
                age=seg['age'],
                income=seg['income'],
                energy_burden=seg['energy_burden']
            )

            # Plot density
            az.plot_kde(
                pred['samples'],
                ax=ax,
                label=seg['name'],
                plot_kwargs={'alpha': 0.7}
            )

        ax.set_xlabel('Click Probability')
        ax.set_ylabel('Density')
        ax.set_title('Click Probability by Demographic Segment')
        ax.legend()
        plt.tight_layout()

        return fig



    def probability_one_segment_higher(self,
                                       seg1: Dict,
                                       seg2: Dict) -> float:
        """
        Compute probability that segment 1 has higher click rate than segment 2.

        This answers questions like: "How confident are we that young, high
        energy burden contacts click more than old, low energy burden contacts?"

        Parameters
        ----------
        seg1, seg2 : dict
            Dictionaries with 'age', 'income', 'energy_burden' keys

        Returns
        -------
        float
            Probability that P(click|seg1) > P(click|seg2)
        """
        pred1 = self.predict_segment(seg1['age'], seg1['income'], seg1['energy_burden'])
        pred2 = self.predict_segment(seg2['age'], seg2['income'], seg2['energy_burden'])

        # Compute proportion of samples where seg1 > seg2
        return (pred1['samples'] > pred2['samples']).mean()


# =============================================================================
# EXAMPLE USAGE: FULL WORKFLOW
# =============================================================================

def run_full_analysis():
    """
    Run complete Version 0 analysis workflow.

    This function demonstrates the entire pipeline:
    1. Load data
    2. Build model
    3. Fit model
    4. Check diagnostics
    5. Generate segment predictions
    6. Compare segments
    """
    print("=" * 70)
    print("BAYESIAN CLICK MODEL - VERSION 0: DEMOGRAPHICS ONLY")
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
    trace = model.fit(draws=2000, tune=1000, chains=4)

    # -------------------------------------------------------------------------
    # STEP 4: Review Results
    # -------------------------------------------------------------------------
    print("\nSTEP 4: Model Summary")
    print("-" * 40)
    print(model.summary())

    # Interpret coefficients
    print("\nCoefficient Interpretation (on log-odds scale):")
    posterior = trace.posterior

    beta_age_mean = posterior['beta_age'].values.mean()
    beta_income_mean = posterior['beta_income'].values.mean()
    beta_eb_mean = posterior['beta_eb'].values.mean()

    print(f"  • Age: {beta_age_mean:.3f} → {'older = lower' if beta_age_mean < 0 else 'older = higher'} click prob")
    print(
        f"  • Income: {beta_income_mean:.3f} → {'higher income = lower' if beta_income_mean < 0 else 'higher income = higher'} click prob")
    print(
        f"  • Energy Burden: {beta_eb_mean:.3f} → {'higher burden = lower' if beta_eb_mean < 0 else 'higher burden = higher'} click prob")

    # -------------------------------------------------------------------------
    # STEP 5: Segment Predictions
    # -------------------------------------------------------------------------
    print("\nSTEP 5: Segment Predictions")
    print("-" * 40)

    predictor = SegmentPredictor(model)

    # Define interesting segments to compare
    segments = [
        {'name': 'Young, High Energy Burden', 'age': 30, 'income': 35000, 'energy_burden': 15},
        {'name': 'Young, Low Energy Burden', 'age': 30, 'income': 80000, 'energy_burden': 3},
        {'name': 'Middle Age, Average', 'age': 45, 'income': 55000, 'energy_burden': 6},
        {'name': 'Senior, High Energy Burden', 'age': 70, 'income': 45000, 'energy_burden': 12},
        {'name': 'Senior, Low Energy Burden', 'age': 70, 'income': 90000, 'energy_burden': 3},
    ]

    print("\nSegment Comparison:")
    comparison = predictor.compare_segments(segments)
    print(comparison.to_string(index=False))

    # -------------------------------------------------------------------------
    # STEP 6: Segment Contrast
    # -------------------------------------------------------------------------
    print("\n\nSTEP 6: Segment Contrasts")
    print("-" * 40)

    seg_high_eb = {'age': 35, 'income': 40000, 'energy_burden': 15}
    seg_low_eb = {'age': 35, 'income': 40000, 'energy_burden': 3}

    prob_higher = predictor.probability_one_segment_higher(seg_high_eb, seg_low_eb)
    print(f"P(High Energy Burden > Low Energy Burden | same age, income) = {prob_higher:.1%}")

    # -------------------------------------------------------------------------
    # STEP 7: Visualizations
    # -------------------------------------------------------------------------
    print("\n\nSTEP 7: Generating Visualizations")
    print("-" * 40)

    # Plot trace
    model.plot_trace()
    plt.savefig('trace_plot_v0.png', dpi=150, bbox_inches='tight')
    print("  Saved: trace_plot_v0.png")

    # Plot posteriors
    model.plot_posterior()
    plt.savefig('posterior_plot_v0.png', dpi=150, bbox_inches='tight')
    print("  Saved: posterior_plot_v0.png")

    # Plot segment comparison
    predictor.plot_segment_comparison(segments)
    plt.savefig('segment_comparison_v0.png', dpi=150, bbox_inches='tight')
    print("  Saved: segment_comparison_v0.png")

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)

    return model, predictor, data


# =============================================================================
# FUTURE: TREATMENT EFFECT PREDICTIONS (Version 1+ Preview)
# =============================================================================

def preview_version1_interface():
    """
    Preview of the interface we'll build in Version 1.

    This shows what you'll be able to do once we add treatments:

    >>> # Given a contact's demographics, find optimal treatment
    >>> optimal = predictor.find_optimal_treatment(
    ...     age=35,
    ...     income=45000,
    ...     energy_burden=12
    ... )
    >>> print(optimal)
    {
        'best_channel': 'text',
        'best_timing': 'evening',
        'best_framing': 'urgent',
        'expected_click_prob': 0.052,
        'lift_over_average': 0.023
    }

    >>> # Compare treatments for a segment
    >>> treatment_effects = predictor.compare_treatments(
    ...     age=35, income=45000, energy_burden=12
    ... )
    >>> print(treatment_effects)
                    Channel   Click Prob   95% CI
    0               email     0.032       [0.028, 0.036]
    1               text      0.052       [0.045, 0.059]
    2               mailer    0.041       [0.035, 0.048]
    """
    print("""
    ══════════════════════════════════════════════════════════════════════
    COMING IN VERSION 1: TREATMENT EFFECTS
    ══════════════════════════════════════════════════════════════════════

    Version 1 will add:

    1. CHANNEL EFFECTS
       - Estimate the causal effect of email vs. text vs. mailer
       - Account for demographic confounding

    2. OPTIMAL TREATMENT SELECTION
       - Given demographics, find the channel with highest click probability
       - Quantify uncertainty in the recommendation

    3. TREATMENT EFFECT HETEROGENEITY  
       - Does text work better for young people?
       - Does urgent messaging work better for high energy burden?

    4. COUNTERFACTUAL PREDICTIONS
       - "If we had sent text instead of email, how many more clicks?"

    To enable this, make sure your data includes:
       - channel: ['email', 'text', 'mailer']
       - timing: ['morning', 'afternoon', 'evening']  
       - framing: ['hopeful', 'funny', 'urgent']
    ══════════════════════════════════════════════════════════════════════
    """)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Run the full analysis
    model, predictor, data = run_full_analysis()

    # Show what's coming in Version 1
    preview_version1_interface()