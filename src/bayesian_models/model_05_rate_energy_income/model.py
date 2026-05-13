"""
Model 05: Click Rate by Energy Cost × Income Category
======================================================

A Bayesian hierarchical model for predicting click-through rates using
energy cost and income category as separate predictors with interaction.

Design Rationale:
    Energy burden = energy_cost / income is a derived variable where income
    is already categorical. Discretizing the burden ratio compounds information
    loss. Instead, we model the components separately with an interaction term
    that captures the burden relationship implicitly.

Mathematical Model:
    click_i ~ Bernoulli(p_i)
    logit(p_i) = α + β_energy·energy_cost_i + γ[income_cat_i] + δ[income_cat_i]·energy_cost_i

    The varying slope δ[k] allows each income category to have a different
    relationship between energy cost and click probability - this IS the
    energy burden effect modeled flexibly.

Hierarchical Structure:
    γ[k] ~ Normal(0, σ_γ)           # Income category effects (sum-to-zero)
    δ[k] ~ Normal(μ_δ, σ_δ)         # Varying slopes with partial pooling
    σ_γ ~ HalfNormal(0.5)           # Regularization on category effects
    μ_δ ~ Normal(0, 0.25)           # Population mean slope modifier
    σ_δ ~ HalfNormal(0.25)          # Between-category slope variation

Priors:
    α ~ Normal(-3.7, 0.5)           # Centers baseline near 2.5% click rate
    β_energy ~ Normal(0, 0.5)       # Effect per SD of energy cost

References:
- McElreath, R. (2020). Statistical Rethinking, Ch. 13 (Varying Slopes)
- Gelman et al. (2013). Bayesian Data Analysis, Ch. 5 (Hierarchical Models)
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt

from src.bayesian_models.base_model import BaseBayesianModel
from src.utils.engagement import attach_engagement_summaries
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

# Number of income categories
N_INCOME_CATEGORIES = 10

# Income category labels for display
INCOME_CATEGORY_LABELS = [
    "< $15k", "$15k-$25k", "$25k-$35k", "$35k-$50k", "$50k-$65k",
    "$65k-$80k", "$80k-$100k", "$100k-$125k", "$125k-$150k", "> $150k"
]


class ClickRateEnergyIncomeModel(BaseBayesianModel):
    """
    Model 05: Click Rate with Energy Cost × Income Category Interaction

    This model predicts click probability using:
    - Energy cost (continuous) - monthly average in dollars
    - Income category (categorical) - 10 ordered categories
    - Interaction term - varying slopes for energy cost by income

    The hierarchical structure provides:
    - Partial pooling across income categories (regularization)
    - Varying slopes that capture how energy cost effect differs by income
    - Implicit modeling of energy burden without information loss
    """

    def __init__(self, model_dir: Optional[Path] = None):
        """Initialize the model."""
        if model_dir is None:
            model_dir = Path(__file__).parent
        super().__init__(model_dir)

        self.pymc_model = None
        self.trace = None
        self._scaler_params = None
        self._income_mapping = None  # Maps raw income values to category indices

    def load_data(self, **kwargs) -> Dict[str, np.ndarray]:
        """
        Load and prepare data for model training.

        Kwargs:
            collection: MongoDB collection name (default: 'participants')
            filters: Query filters for data selection

        Returns:
            Dictionary with:
                - energy_cost_scaled: Standardized energy cost
                - income_cat_idx: Income category indices (0-9)
                - y_clicked: Binary click outcomes
                - n_obs: Number of observations
                - n_categories: Number of income categories
        """
        from src.tools.mongo import get_campaign_db

        db = get_campaign_db()
        collection_name = kwargs.get('collection', 'participants')

        # Load data from MongoDB
        query = kwargs.get('filters', {})
        projection = {
            'participant_id': 1,
            'demographics.income_level': 1,
            'demographics.annual_kwh_cost': 1,
        }

        cursor = db[collection_name].find(query, projection)
        records = list(cursor)
        attach_engagement_summaries(db, records)
        logger.info(f"Loaded {len(records)} records from {collection_name}")

        # Extract and process data
        data_rows = []
        for doc in records:
            demographics = doc.get('demographics', {}) or {}
            engagement = doc.get('engagement_summary', {}) or {}

            income_level = demographics.get('income_level')
            annual_kwh_cost = demographics.get('annual_kwh_cost')

            # Get engagement from any channel
            by_channel = engagement.get('by_channel', {})
            email_engaged = by_channel.get('email', {}).get('engaged', 0) or 0
            text_engaged = by_channel.get('text', {}).get('engaged', 0) or 0
            text_morning = by_channel.get('text_morning', {}).get('engaged', 0) or 0
            text_evening = by_channel.get('text_evening', {}).get('engaged', 0) or 0
            # Also check unified status
            ever_engaged = engagement.get('ever_engaged', False)
            # Consider engaged if ANY channel has engagement
            any_engaged = (email_engaged > 0 or text_engaged > 0 or
                          text_morning > 0 or text_evening > 0 or ever_engaged)
            clicked = 1 if any_engaged else 0

            # Only include records with complete numeric data
            if income_level is not None and annual_kwh_cost is not None:
                # Handle income as categorical index
                if isinstance(income_level, (int, float)) and isinstance(annual_kwh_cost, (int, float)):
                    # Convert annual cost to monthly
                    monthly_cost = float(annual_kwh_cost) / 12.0

                    # DB stores income_level as 1-9, convert to 0-8 for model indexing
                    # DB level 1 = lowest income = our index 0 ("< $15k")
                    income_cat = int(income_level) - 1
                    if 0 <= income_cat < N_INCOME_CATEGORIES:
                        data_rows.append({
                            'energy_cost': monthly_cost,
                            'income_cat': income_cat,
                            'clicked': clicked
                        })

        df = pd.DataFrame(data_rows)
        logger.info(f"After filtering: {len(df)} records with complete data")

        if len(df) == 0:
            raise ValueError("No valid data found. Check database fields.")

        # Log statistics
        click_rate = df['clicked'].mean()
        logger.info(f"Click rate: {click_rate:.2%} ({df['clicked'].sum()}/{len(df)})")
        logger.info(f"Energy cost range: ${df['energy_cost'].min():.2f} - ${df['energy_cost'].max():.2f}")
        logger.info(f"Income categories present: {sorted(df['income_cat'].unique())}")

        # Log category distribution
        cat_counts = df['income_cat'].value_counts().sort_index()
        logger.info(f"Category distribution:\n{cat_counts}")

        # Standardize energy cost
        energy_mean = df['energy_cost'].mean()
        energy_std = df['energy_cost'].std()

        # Store scaler params for inference
        self._scaler_params = {
            'energy_mean': float(energy_mean),
            'energy_std': float(energy_std),
            'n_categories': N_INCOME_CATEGORIES
        }

        # Prepare model data
        data = {
            'energy_cost_scaled': ((df['energy_cost'] - energy_mean) / energy_std).values,
            'income_cat_idx': df['income_cat'].values.astype(int),
            'y_clicked': df['clicked'].values.astype(int),
            'n_obs': len(df),
            'n_categories': N_INCOME_CATEGORIES
        }

        return data

    def _build_model(self, data: Dict[str, np.ndarray]) -> pm.Model:
        """
        Build the PyMC model with hierarchical varying slopes.

        Model Structure:
            logit(p) = α + β·energy + γ[income] + δ[income]·energy

        The varying slopes δ[k] capture how the effect of energy cost
        differs by income category - this implicitly models energy burden.
        """
        n_categories = data['n_categories']

        with pm.Model() as model:
            # ================================================================
            # DATA
            # ================================================================
            energy_cost = pm.Data("energy_cost", data['energy_cost_scaled'])
            income_cat = pm.Data("income_cat", data['income_cat_idx'])

            # ================================================================
            # HYPERPRIORS (Hierarchical Structure)
            # ================================================================
            # Between-category variation for intercepts
            sigma_gamma = pm.HalfNormal("sigma_gamma", sigma=0.5)

            # Hierarchical structure for varying slopes
            mu_delta = pm.Normal("mu_delta", mu=0, sigma=0.25)
            sigma_delta = pm.HalfNormal("sigma_delta", sigma=0.25)

            # ================================================================
            # PRIORS
            # ================================================================
            # Intercept: centered on logit(0.025) ≈ -3.66 for 2.5% base rate
            alpha = pm.Normal("alpha", mu=-3.7, sigma=0.5)

            # Main effect of energy cost (average across income categories)
            beta_energy = pm.Normal("beta_energy", mu=0, sigma=0.5)

            # Income category effects (hierarchical, non-centered)
            # Using non-centered parameterization for better sampling
            gamma_raw = pm.Normal("gamma_raw", mu=0, sigma=1, shape=n_categories)
            gamma = pm.Deterministic("gamma", gamma_raw * sigma_gamma)

            # Varying slopes for energy cost by income category (non-centered)
            delta_raw = pm.Normal("delta_raw", mu=0, sigma=1, shape=n_categories)
            delta = pm.Deterministic("delta", mu_delta + delta_raw * sigma_delta)

            # ================================================================
            # LINEAR MODEL
            # ================================================================
            # Log-odds of clicking with varying slopes
            logit_p = (alpha
                      + beta_energy * energy_cost
                      + gamma[income_cat]
                      + delta[income_cat] * energy_cost)

            # Transform to probability
            p = pm.Deterministic("p", pm.math.invlogit(logit_p))

            # ================================================================
            # LIKELIHOOD
            # ================================================================
            y = pm.Bernoulli("y_click", p=p, observed=data['y_clicked'])

        self.pymc_model = model
        return model

    def train(self, data: Any, **kwargs) -> Dict[str, Any]:
        """
        Train the Bayesian model.

        Args:
            data: Prepared data from load_data()
            **kwargs: Additional training parameters
                - draws: Number of posterior samples (default: 2000)
                - tune: Number of tuning samples (default: 1000)
                - chains: Number of MCMC chains (default: 4)
                - target_accept: Target acceptance rate (default: 0.9)
                - use_gpu: Whether to use GPU via NumPyro (default: True)

        Returns:
            Dictionary with training results and metrics
        """
        self.ensure_output_dirs()

        draws = kwargs.get('draws', 2000)
        tune = kwargs.get('tune', 1000)
        chains = kwargs.get('chains', 4)
        target_accept = kwargs.get('target_accept', 0.9)
        random_seed = kwargs.get('random_seed', 42)
        use_gpu = kwargs.get('use_gpu', True)

        # Build model if not already built
        if self.pymc_model is None:
            self._build_model(data)

        logger.info(f"Training {self.metadata.name}")
        logger.info(f"Observations: {data['n_obs']}")
        logger.info(f"Click rate: {data['y_clicked'].mean():.2%}")
        logger.info(f"Income categories: {data['n_categories']}")
        logger.info(f"Sampling: {draws} draws × {chains} chains (tune={tune})")

        # Sample
        with self.pymc_model:
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
                logger.info("Using NumPyro backend (GPU if available)")

            self.trace = pm.sample(**sample_kwargs)

            # Add posterior predictive samples
            logger.info("Generating posterior predictive samples...")
            pm.sample_posterior_predictive(
                self.trace,
                extend_inferencedata=True,
                random_seed=random_seed
            )

        # Generate results
        results = self._generate_training_results()

        # Save artifacts
        self._save_training_artifacts(results)

        logger.info("Training complete!")
        return results

    def _generate_training_results(self) -> Dict[str, Any]:
        """Generate training results and diagnostics."""
        # Core parameters
        core_vars = ["alpha", "beta_energy", "mu_delta", "sigma_gamma", "sigma_delta"]
        summary = az.summary(self.trace, var_names=core_vars, hdi_prob=0.94)

        # Hierarchical parameters (category-level)
        gamma_summary = az.summary(self.trace, var_names=["gamma"], hdi_prob=0.94)
        delta_summary = az.summary(self.trace, var_names=["delta"], hdi_prob=0.94)

        # Diagnostics
        all_vars = core_vars + ["gamma", "delta"]
        full_summary = az.summary(self.trace, var_names=all_vars)

        diagnostics = {
            'r_hat_max': float(full_summary['r_hat'].max()),
            'ess_bulk_min': float(full_summary['ess_bulk'].min()),
            'ess_tail_min': float(full_summary['ess_tail'].min()),
            'divergences': int(self.trace.sample_stats['diverging'].sum().item())
        }

        # Extract odds ratios for main effects
        beta_mean = summary.loc['beta_energy', 'mean']
        beta_lower = summary.loc['beta_energy', 'hdi_3%']
        beta_upper = summary.loc['beta_energy', 'hdi_97%']

        main_effects = {
            'beta_energy': {
                'coefficient': float(beta_mean),
                'odds_ratio': float(np.exp(beta_mean)),
                'or_lower': float(np.exp(beta_lower)),
                'or_upper': float(np.exp(beta_upper)),
                'effect_pct': float((np.exp(beta_mean) - 1) * 100),
                'credibly_nonzero': bool((beta_lower > 0 and beta_upper > 0) or
                                         (beta_lower < 0 and beta_upper < 0))
            }
        }

        # Category-level effects summary
        category_effects = {}
        for i in range(N_INCOME_CATEGORIES):
            gamma_i = gamma_summary.loc[f'gamma[{i}]', 'mean']
            delta_i = delta_summary.loc[f'delta[{i}]', 'mean']
            category_effects[INCOME_CATEGORY_LABELS[i]] = {
                'gamma': float(gamma_i),
                'delta': float(delta_i),
                'total_slope': float(beta_mean + delta_i)
            }

        # Hypothesis: Does energy cost effect vary by income?
        sigma_delta_mean = summary.loc['sigma_delta', 'mean']
        sigma_delta_lower = summary.loc['sigma_delta', 'hdi_3%']

        if sigma_delta_lower > 0.05:
            slope_variation = {
                'supported': True,
                'sigma_delta': float(sigma_delta_mean),
                'interpretation': 'Energy cost effect varies meaningfully across income categories'
            }
        else:
            slope_variation = {
                'supported': False,
                'sigma_delta': float(sigma_delta_mean),
                'interpretation': 'Energy cost effect is similar across income categories'
            }

        return {
            'summary': summary.to_dict(),
            'gamma_summary': gamma_summary.to_dict(),
            'delta_summary': delta_summary.to_dict(),
            'main_effects': main_effects,
            'category_effects': category_effects,
            'slope_variation': slope_variation,
            'diagnostics': diagnostics,
            'scaler_params': self._scaler_params,
            'trained_at': datetime.now().isoformat()
        }

    def _save_training_artifacts(self, results: Dict[str, Any]) -> None:
        """Save trace, reports, and visualizations."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save trace
        trace_path = self.traces_dir / f'trace_{timestamp}.nc'
        self.trace.to_netcdf(trace_path)
        logger.info(f"Trace saved to {trace_path}")

        # Save scaler params for inference
        scaler_path = self.checkpoints_dir / 'scaler_params.json'
        with open(scaler_path, 'w') as f:
            json.dump(self._scaler_params, f)

        # Save results summary
        results_path = self.reports_dir / f'results_{timestamp}.json'
        serializable_results = self._make_serializable(results)
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2)

        # Generate and save plots
        self._generate_plots(timestamp)

        # Generate DAG
        self._generate_dag()

    def _make_serializable(self, obj: Any) -> Any:
        """Convert numpy types to Python types for JSON."""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(v) for v in obj]
        elif isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    def _generate_plots(self, timestamp: str) -> None:
        """Generate diagnostic and posterior plots."""
        # Trace plot for core parameters
        core_vars = ["alpha", "beta_energy", "mu_delta", "sigma_gamma", "sigma_delta"]
        az.plot_trace(self.trace, var_names=core_vars)
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'trace_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Posterior plot
        az.plot_posterior(self.trace, var_names=core_vars, hdi_prob=0.94, ref_val=0)
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'posterior_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Forest plot for varying slopes (delta)
        az.plot_forest(self.trace, var_names=["delta"], combined=True, hdi_prob=0.94)
        plt.title("Varying Slopes: Energy Cost Effect by Income Category")
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'forest_delta_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Forest plot for income category effects (gamma)
        az.plot_forest(self.trace, var_names=["gamma"], combined=True, hdi_prob=0.94)
        plt.title("Income Category Effects on Click Rate")
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'forest_gamma_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Custom plot: Predicted click probability by energy cost for each income category
        self._plot_income_energy_interaction(timestamp)

        logger.info(f"Plots saved to {self.diagrams_dir}")

    def _plot_income_energy_interaction(self, timestamp: str) -> None:
        """Plot predicted click probability curves by income category."""
        fig, ax = plt.subplots(figsize=(12, 8))

        # Extract posterior samples
        posterior = self.trace.posterior
        alpha = posterior['alpha'].values.mean()
        beta = posterior['beta_energy'].values.mean()
        gamma = posterior['gamma'].values.mean(axis=(0, 1))  # Average across chains/draws
        delta = posterior['delta'].values.mean(axis=(0, 1))

        # Energy cost range (in scaled units)
        energy_range = np.linspace(-2, 2, 100)

        # Plot each income category
        colors = plt.cm.viridis(np.linspace(0, 1, N_INCOME_CATEGORIES))

        for k in range(N_INCOME_CATEGORIES):
            logit_p = alpha + beta * energy_range + gamma[k] + delta[k] * energy_range
            p = 1 / (1 + np.exp(-logit_p))
            ax.plot(energy_range, p * 100, color=colors[k],
                   label=INCOME_CATEGORY_LABELS[k], linewidth=2)

        ax.set_xlabel('Energy Cost (Standardized)', fontsize=12)
        ax.set_ylabel('Click Probability (%)', fontsize=12)
        ax.set_title('Click Probability by Energy Cost and Income Category\n(Varying Slopes Model)',
                    fontsize=14, fontweight='bold')
        ax.legend(title='Income Category', bbox_to_anchor=(1.02, 1), loc='upper left')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-2, 2)

        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'interaction_{timestamp}.png',
                   dpi=150, bbox_inches='tight')
        plt.close()

    def _generate_dag(self) -> None:
        """Generate DAG visualization."""
        try:
            self._generate_matplotlib_dag()
            logger.info(f"DAG saved to {self.diagrams_dir / 'dag.png'}")
        except Exception as e:
            logger.warning(f"Could not generate DAG visualization: {e}")
            self._generate_text_dag()

    def _generate_matplotlib_dag(self) -> None:
        """Create a DAG visualization using matplotlib."""
        fig, ax = plt.subplots(1, 1, figsize=(16, 12))
        ax.set_xlim(-1, 17)
        ax.set_ylim(-2, 14)
        ax.set_aspect('equal')
        ax.axis('off')

        # Node positions
        nodes = {
            # Hyperpriors (top)
            'sigma_gamma': (3, 12),
            'mu_delta': (9, 12),
            'sigma_delta': (12, 12),
            # Category-level priors
            'gamma': (3, 9),
            'delta': (10, 9),
            # Fixed effects
            'alpha': (1, 6),
            'beta_energy': (6, 6),
            # Data
            'energy_cost': (6, 3),
            'income_cat': (10, 3),
            # Deterministic
            'logit_p': (8, 5),
            'p': (11, 5),
            # Likelihood
            'y_click': (14, 5),
        }

        # Node styles
        hyper_style = dict(boxstyle='round,pad=0.3', facecolor='lavender', edgecolor='purple', linewidth=2)
        prior_style = dict(boxstyle='round,pad=0.3', facecolor='lightblue', edgecolor='blue', linewidth=2)
        data_style = dict(boxstyle='round,pad=0.3', facecolor='lightgray', edgecolor='gray', linewidth=2)
        det_style = dict(boxstyle='round,pad=0.3', facecolor='lightyellow', edgecolor='orange', linewidth=2)
        obs_style = dict(boxstyle='round,pad=0.3', facecolor='lightgreen', edgecolor='green', linewidth=2)

        # Node labels
        node_labels = {
            'sigma_gamma': 'σ_γ\n~ HalfNormal(0.5)',
            'mu_delta': 'μ_δ\n~ Normal(0, 0.25)',
            'sigma_delta': 'σ_δ\n~ HalfNormal(0.25)',
            'gamma': 'γ[k]\n~ Normal(0, σ_γ)\n[10 categories]',
            'delta': 'δ[k]\n~ Normal(μ_δ, σ_δ)\n[10 varying slopes]',
            'alpha': 'α\n~ Normal(-3.7, 0.5)',
            'beta_energy': 'β_energy\n~ Normal(0, 0.5)',
            'energy_cost': 'energy_cost\n(data, scaled)',
            'income_cat': 'income_cat\n(data, 0-9)',
            'logit_p': 'logit(p)\n(linear)',
            'p': 'p\n(deterministic)',
            'y_click': 'y_click\n~ Bernoulli(p)',
        }

        styles = {
            'sigma_gamma': hyper_style, 'mu_delta': hyper_style, 'sigma_delta': hyper_style,
            'gamma': prior_style, 'delta': prior_style,
            'alpha': prior_style, 'beta_energy': prior_style,
            'energy_cost': data_style, 'income_cat': data_style,
            'logit_p': det_style, 'p': det_style,
            'y_click': obs_style,
        }

        for name, (x, y) in nodes.items():
            ax.text(x, y, node_labels[name], ha='center', va='center',
                   fontsize=8, bbox=styles[name], fontweight='bold')

        # Arrows
        arrows = [
            ('sigma_gamma', 'gamma'),
            ('mu_delta', 'delta'),
            ('sigma_delta', 'delta'),
            ('alpha', 'logit_p'),
            ('beta_energy', 'logit_p'),
            ('gamma', 'logit_p'),
            ('delta', 'logit_p'),
            ('energy_cost', 'logit_p'),
            ('income_cat', 'gamma'),
            ('income_cat', 'delta'),
            ('logit_p', 'p'),
            ('p', 'y_click'),
        ]

        for start, end in arrows:
            x1, y1 = nodes[start]
            x2, y2 = nodes[end]
            dx = x2 - x1
            dy = y2 - y1
            ax.annotate('', xy=(x2 - dx*0.15, y2 - dy*0.15),
                       xytext=(x1 + dx*0.15, y1 + dy*0.15),
                       arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

        # Title
        ax.set_title('Click Rate Model: Energy Cost × Income Category (Varying Slopes)',
                    fontsize=14, fontweight='bold', pad=20)

        # Legend
        legend_items = [
            ('Hyperprior', 'lavender', 'purple'),
            ('Prior', 'lightblue', 'blue'),
            ('Data', 'lightgray', 'gray'),
            ('Deterministic', 'lightyellow', 'orange'),
            ('Observed', 'lightgreen', 'green'),
        ]
        for i, (label, fc, ec) in enumerate(legend_items):
            ax.add_patch(plt.Rectangle((14, 12 - i*0.7), 0.4, 0.4,
                                       facecolor=fc, edgecolor=ec, linewidth=2))
            ax.text(14.6, 12.2 - i*0.7, label, fontsize=9, va='center')

        # Model equation
        eq = "logit(p) = α + β·energy_cost + γ[income] + δ[income]·energy_cost"
        ax.text(8, -1, eq, ha='center', fontsize=10, style='italic',
               bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray'))

        plt.tight_layout()
        plt.savefig(self.diagrams_dir / 'dag.png', dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()

    def _generate_text_dag(self) -> None:
        """Create a text-based DAG representation as fallback."""
        dag_text = """
Model DAG: Click Rate - Energy Cost × Income Category
======================================================

Hyperpriors:
  σ_γ ~ HalfNormal(0.5)        # Between-category variance for intercepts
  μ_δ ~ Normal(0, 0.25)        # Population mean for varying slopes
  σ_δ ~ HalfNormal(0.25)       # Between-category variance for slopes

Category-Level Priors (k = 0..9):
  γ[k] ~ Normal(0, σ_γ)        # Income category intercept effects
  δ[k] ~ Normal(μ_δ, σ_δ)      # Varying slopes for energy cost

Fixed Effect Priors:
  α ~ Normal(-3.7, 0.5)        # Baseline (2.5% click rate)
  β_energy ~ Normal(0, 0.5)    # Main energy cost effect

Linear Model:
  logit(p) = α + β·energy_cost + γ[income_cat] + δ[income_cat]·energy_cost

Likelihood:
  y_click ~ Bernoulli(p)

Graph Structure:
                σ_γ ──────────────────┐
                                      ↓
  μ_δ ─────┬──→ δ[k] ───────────────→ logit(p)
           │                    ↗    ↗   ↘
  σ_δ ─────┘                   │    │     ↘
                               │    │      ↘
  α ───────────────────────────┘    │       → p ──→ y_click
  β_energy ─────────────────────────┤      ↗
  energy_cost ──────────────────────┼─────┘
  income_cat ───→ γ[k] ─────────────┘

Key Insight: The varying slope δ[k] captures how energy cost effect
differs by income category - this IS the energy burden relationship
modeled flexibly without information loss from discretization.
"""
        with open(self.diagrams_dir / 'dag.txt', 'w') as f:
            f.write(dag_text)

    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run inference with the trained model.

        Args:
            inference_params: Dictionary with:
                - income_category: Income category index (0-9) as string
                - energy_cost: Monthly energy cost in dollars
                - credible_interval: HDI width (optional, default 0.94)

        Returns:
            Dictionary with prediction results
        """
        # Validate parameters
        is_valid, error = self.validate_inference_params(inference_params)
        if not is_valid:
            return {'error': error}

        # Load trained model if needed
        if self.trace is None:
            if not self._load_latest_model():
                return {'error': 'No trained model found. Please train the model first.'}

        # Load scaler params
        if self._scaler_params is None:
            scaler_path = self.checkpoints_dir / 'scaler_params.json'
            if scaler_path.exists():
                with open(scaler_path, 'r') as f:
                    self._scaler_params = json.load(f)
            else:
                return {'error': 'Scaler parameters not found. Please retrain the model.'}

        # Parse and standardize inputs
        income_cat = int(inference_params['income_category'])
        energy_cost = float(inference_params['energy_cost'])

        energy_scaled = (energy_cost - self._scaler_params['energy_mean']) / self._scaler_params['energy_std']

        # Extract posterior samples
        posterior = self.trace.posterior
        alpha = posterior['alpha'].values.flatten()
        beta_energy = posterior['beta_energy'].values.flatten()
        gamma = posterior['gamma'].values  # shape: (chains, draws, categories)
        delta = posterior['delta'].values

        # Get category-specific parameters
        gamma_k = gamma[:, :, income_cat].flatten()
        delta_k = delta[:, :, income_cat].flatten()

        # Compute predicted probabilities
        logit_p = alpha + beta_energy * energy_scaled + gamma_k + delta_k * energy_scaled
        prob = 1 / (1 + np.exp(-logit_p))

        # Summary statistics
        ci = float(inference_params.get('credible_interval', 0.94))
        lower_q = (1 - ci) / 2
        upper_q = 1 - lower_q

        return {
            'mean_probability': float(np.mean(prob)),
            'median_probability': float(np.median(prob)),
            'std_probability': float(np.std(prob)),
            'credible_interval': {
                'lower': float(np.quantile(prob, lower_q)),
                'upper': float(np.quantile(prob, upper_q)),
                'level': ci
            },
            'input_values': {
                'income_category': income_cat,
                'income_label': INCOME_CATEGORY_LABELS[income_cat],
                'energy_cost': energy_cost,
                'energy_scaled': float(energy_scaled)
            },
            'model_components': {
                'alpha_mean': float(np.mean(alpha)),
                'beta_energy_mean': float(np.mean(beta_energy)),
                'gamma_k_mean': float(np.mean(gamma_k)),
                'delta_k_mean': float(np.mean(delta_k)),
                'total_energy_slope': float(np.mean(beta_energy) + np.mean(delta_k))
            },
            'interpretation': self._generate_interpretation(
                np.mean(prob), income_cat, np.mean(beta_energy) + np.mean(delta_k)
            )
        }

    def _load_latest_model(self) -> bool:
        """Load the most recent trained model."""
        latest_trace = self.get_latest_trace()
        if latest_trace is None:
            return False

        self.trace = az.from_netcdf(latest_trace)
        logger.info(f"Loaded trace from {latest_trace}")
        return True

    def _generate_interpretation(self, prob: float, income_cat: int, total_slope: float) -> str:
        """Generate human-readable interpretation of prediction."""
        income_label = INCOME_CATEGORY_LABELS[income_cat]

        # Base interpretation
        if prob >= 0.05:
            engagement = "above average"
        elif prob >= 0.025:
            engagement = "average"
        else:
            engagement = "below average"

        # Slope interpretation
        if total_slope > 0.1:
            slope_desc = "Higher energy costs strongly increase click likelihood for this income bracket."
        elif total_slope > 0:
            slope_desc = "Higher energy costs modestly increase click likelihood for this income bracket."
        elif total_slope > -0.1:
            slope_desc = "Energy costs have minimal impact on click likelihood for this income bracket."
        else:
            slope_desc = "Higher energy costs decrease click likelihood for this income bracket."

        return (f"For income category {income_label}: {engagement} engagement expected "
                f"({prob:.2%} click probability). {slope_desc}")

    def compare_income_categories(self, energy_cost: float = 150.0) -> pd.DataFrame:
        """
        Compare predicted click probabilities across all income categories.

        Args:
            energy_cost: Monthly energy cost in dollars

        Returns:
            DataFrame with predictions for each income category
        """
        if self.trace is None:
            if not self._load_latest_model():
                raise ValueError("No trained model found")

        if self._scaler_params is None:
            scaler_path = self.checkpoints_dir / 'scaler_params.json'
            with open(scaler_path, 'r') as f:
                self._scaler_params = json.load(f)

        results = []
        for k in range(N_INCOME_CATEGORIES):
            pred = self.predict({
                'income_category': str(k),
                'energy_cost': energy_cost
            })

            if 'error' not in pred:
                results.append({
                    'Income Category': INCOME_CATEGORY_LABELS[k],
                    'Click Prob (Mean)': f"{pred['mean_probability']:.2%}",
                    'Click Prob (94% HDI)': f"[{pred['credible_interval']['lower']:.2%}, {pred['credible_interval']['upper']:.2%}]",
                    'Energy Slope': f"{pred['model_components']['total_energy_slope']:.3f}"
                })

        return pd.DataFrame(results)
